#pragma once
// WdcGrid.h: react-grid-layout math of the WiData dashboard (12 columns, margin 4, padding 0, square rows)
// and the page geometry around it. Package E. UI §1.3, §2.1, §2.2; DESIGN §6. Pure, no Qt widgets.
//
// WiData mixes two widths (FACT, UI §2.1, re-measured 04/10 on the 108 cards of CAP): the column width uses
// the integer offsetWidth (1311) and the square row height the real width (1311.46). In the app both are the
// same integer width; the harness passes the two CAP widths to reproduce the capture exactly.
#include <QRectF>

namespace fincept::screens::wdc {

inline constexpr int kGridCols = 12;
inline constexpr double kGridMargin = 4;      // [4, 4]
inline constexpr double kShellH = 64;         // 16 + tab bar 32 + 16 (UI §1.2: grid top at 63.99)
inline constexpr double kPadX = 8;            // scroll frame padding 0 8 (UI §1.3)
inline constexpr double kScrollbarW = 4;      // ::-webkit-scrollbar width 4 (UI §1.3, DESIGN §6.1)
inline constexpr double kAddBlockTop = 12;    // "+ Thêm biểu đồ" block margin-top (UI §2.2)
inline constexpr double kAddBtnTop = 24;      // button margin-top inside the block
inline constexpr double kAddBtnW = 400, kAddBtnH = 38;
inline constexpr double kAddBlockPadBottom = 400;

double jsRound(double v);                     // Math.round: half up

struct GridGeom {
    double colBasis = 0, rowBasis = 0;        // widths used for column width and row height
    double cw = 0, rh = 0;                    // column width, row height
};

GridGeom gridGeom(double colBasisW, double rowBasisW);
QRectF gridCellRect(const GridGeom& g, int x, int y, int w, int h);   // relative to the grid origin, integers
double gridHeight(const GridGeom& g, int maxRow);                       // maxRow*(rh+4)-4, 0 when empty

// Page (content of the scroll frame, origin = top-left of the frame, i.e. panel y 64).
struct PageGeom {
    double gridX = kPadX, gridW = 0, gridH = 0;
    QRectF addBlock, addBtn;                  // block (gridW wide) and its centred 400 x 38 button
    double contentH = 0;                      // grid + block (incl. 400 px bottom padding)
};
PageGeom pageGeom(double gridW, double gridH);

// Inner width of the grid for a panel (= view) width: panel - 2*8 - scrollbar.
double gridWidthForPanel(double panelW);

} // namespace fincept::screens::wdc
