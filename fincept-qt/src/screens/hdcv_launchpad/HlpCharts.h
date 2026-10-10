// src/screens/hdcv_launchpad/HlpCharts.h
// The four graphics of panels.js as custom nodes: spark() (SVG polyline sparkline + lo/hi labels),
// sigmaBar() (.bandbar with 4 zones + amber marker + σ labels), ruler() (.ruler: every ticker as a
// dot on one σ axis, click = setCtx, hover = title tooltip), wdChart() (WiData line/area chart with
// grid, amber reference line, dots, y labels in the left gutter, x labels, hover crosshair + tip).
// Geometry and colours follow the SVG/CSS in panels.js exactly (SPEC §5).
#pragma once

#include "screens/hdcv_launchpad/HlpDom.h"

#include <QJsonArray>
#include <QJsonObject>
#include <QString>
#include <QVector>

#include <functional>
#include <optional>

namespace fincept::screens::hlp::charts {

/// spark(series,w=300,h=46): `series` = [[ts,val],…]. <2 points → `<div class="nd">[CẦN DATA] chuỗi giá</div>`.
/// Returns a block node: the 46px-high polyline (stroke 1.4 non-scaling, up if last≥first else down,
/// preserveAspectRatio none → stretches to the full content width) followed by the mono 9.5px
/// lo/hi row (space-between, ink3).
NodeP spark(const QJsonArray& series, float h = 46.0f);

/// sigmaBar(s): null → ND span. Else the 20px `.bandbar` (bg2, radius 2, margin 5px 0 2px) with zones
/// [0,20%) cheap α.2 · [20,40%) cheap α.1(×.2) · [60,80%) rich α.1(×.2) · [80,100%] rich α.2 and the
/// amber 2px marker at p = clamp((s+2.5)/5·100) spanning top−3 → bottom+3, then the 9px mono label
/// row "−2σ −1σ μ +1σ +2σ" (space-between, ink3).
NodeP sigmaBar(std::optional<double> s);

struct RulerDot {
    QString t;       ///< ticker
    double sig = 0;  ///< pe_sig
};
/// .ruler (height 30, margin 14px 0 6px): axis at y=15 (1px line2), grid ticks at −2…+2σ
/// (1×15px line2 at y=8) with 9px mono labels at y=−2 (centred), dots 7×7 at y=11 centred on
/// p=clamp((σ+2.5)/5), colours cheap(≤−1)/rich(≥1)/neutral, opacity .72; the dot of `ctx` (".me")
/// and the hovered dot get opacity 1 + ring (2px panel + 1px amber). Dots are drawn in data order
/// (later dots on top). Click → onPick(ticker). Tooltip "TICKER −1.23σ".
NodeP ruler(const QVector<RulerDot>& dots, const QString& ctx, std::function<void(const QString&)> onPick);

/// WiData chart state shared with the panel (range key: "m3" | "m6" | "y1" | "all").
/// Builds the `.wd-plot` block (height 210, margin 6px 0 2px + left gutter, 1px left/bottom
/// border line2) + the `.wd-x` label row, exactly as wdChartHtml()/wdHover() in panels.js:
///  - <2 points in range → `<div class="nd" style="margin:24px 0">[CẦN DATA] chuỗi mới có N điểm — …</div>`
///  - gutter = max(len(wdFmt(label)))·5.6+8; plot margin-left = max(0, gutter−34)
///  - hover: crosshair 1px ink3 + tip "DD/MM/YY · value" (mono 10px, panel bg, 1px line2, radius r),
///    tip flips to the left of the cursor when x > 60%.
NodeP wdChart(const QJsonObject& series, const QString& range);

} // namespace fincept::screens::hlp::charts
