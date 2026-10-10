#pragma once
// WdcIcons_p.h: icons and decorations of the WiData clone (package D), drawn with QPainter only (no QtSvg).
//
// 16 icons of widata_clone_spec/analysis/assets/icons (UI §6) + ChevronLeft (mirror of ChevronRight, button "<"
// of DESIGN §6.1) + Percent and InsertLinkRounded of the chart page (DESIGN §16 C4, capture vimo). Path data is
// embedded in WdcIcons.cpp; the parser is adapted from screens/chaebol_map/ChbSvgPath.cpp (no call into chb).
// The WiData watermark is deliberately absent (DESIGN §16 C7).
#include <QColor>
#include <QImage>
#include <QPainterPath>
#include <QRectF>
#include <QString>
#include <QStringView>

#include <vector>

class QPainter;

namespace fincept::screens::wdc {

enum class Icon {
    CalendarTodayOutlined, // card header: range button (16)
    CropFreeRounded,       // card header: expand (16)
    Settings,              // card header: gear (16); chart page "Tuỳ chỉnh"
    Cached,                // [macro] card header: sync (20)
    InfoRounded,           // legend info (16, #A6B0C3)
    RestartAlt,            // legend reset (18, white)
    ResizeHandleDiagonal,  // kept for completeness; never drawn in wave 1 (DESIGN §6.1)
    Add,
    AddRounded,            // "+ Thêm" (18), "Thêm biểu đồ" (20)
    ArrowDropDown,         // selected tab (20)
    ChevronRight,          // tab strip ">" (18)
    ChevronLeft,           // tab strip "<" (18), DESIGN §6.1
    Cancel,                // expanded close (24)
    CalendarExpanded20,    // expanded calendar box (20, viewBox 20)
    Share,                 // expanded "Chia sẻ" (16)
    FileDownloadOutlined,  // "Tải về" (18 / 20)
    Fullscreen,            // chart page (18)
    Percent,               // chart page "So sánh biến động" (18)
    InsertLinkRounded,     // chart page "Sao chép liên kết" (18)
    Count
};

/// SVG path data -> QPainterPath (M L H V C S Q T A Z, absolute/relative, implicit repeats, compact numbers and
/// arc flags). Fill rule is set to nonzero (Qt::WindingFill) as SVG. On a syntax error the part parsed so far is
/// returned and *ok is false.
QPainterPath parseSvgPathData(QStringView d, bool* ok = nullptr);

const QPainterPath& iconPath(Icon icon); // in viewBox units
qreal iconViewBox(Icon icon);           // 24, except CalendarExpanded20 (20) and ResizeHandleDiagonal (19)
QString iconName(Icon icon);
/// Fills the icon scaled from its viewBox into `target` (square) with `color`.
void paintIcon(QPainter& p, Icon icon, const QRectF& target, const QColor& color);

// ---- decorations ---------------------------------------------------------------------------------------------
/// One CSS box-shadow layer: offset, blur radius (CSS, Gaussian sigma = blur / 2), spread, colour.
struct ShadowLayer { qreal dx, dy, blur, spread; QColor color; };
const std::vector<ShadowLayer>& shadowCircleBtn(); // UI §5.1 shadow.circleBtn (3 layers)
const std::vector<ShadowLayer>& shadowReset();     // UI §5.1 shadow.reset
const std::vector<ShadowLayer>& shadowHeaderBtn(); // HOVER_CSS.md: card header button hover, rgba(33,35,46,.06) 0 0 6px
/// Paints the shadow of a rounded rect (radius < 0: ellipse). Rendered once per size into a cached QImage.
void paintBoxShadow(QPainter& p, const QRectF& box, qreal radius, const std::vector<ShadowLayer>& layers, qreal dpr);
/// Margin a widget needs around a box so that the shadow is not clipped.
qreal shadowExtent(const std::vector<ShadowLayer>& layers);
/// Border of one device pixel inside `r` (CSS border-box), optional fill, radius in CSS px.
void paintHairlineBox(QPainter& p, const QRectF& r, qreal radius, const QColor& fill, const QColor& border, qreal dpr);
/// Popover frame of DESIGN §6.1: shadow.circleBtn, white, 1 device px #DEDEDE, radius 4.
void paintPopoverFrame(QPainter& p, const QRectF& r, qreal dpr);

} // namespace fincept::screens::wdc
