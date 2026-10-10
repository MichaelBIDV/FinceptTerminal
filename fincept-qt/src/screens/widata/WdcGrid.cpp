// WdcGrid.cpp: react-grid-layout positions (calcGridItemPosition, Math.round) and page geometry. Package E.
#include "WdcGrid.h"

#include <algorithm>
#include <cmath>

namespace fincept::screens::wdc {

double jsRound(double v) { return std::floor(v + 0.5); }

GridGeom gridGeom(double colBasisW, double rowBasisW) {
    GridGeom g;
    g.colBasis = colBasisW;
    g.rowBasis = rowBasisW;
    g.cw = (colBasisW - kGridMargin * (kGridCols - 1)) / kGridCols;
    g.rh = (rowBasisW - kGridMargin * (kGridCols - 1)) / kGridCols;   // dynamic-layout: square rows
    return g;
}

QRectF gridCellRect(const GridGeom& g, int x, int y, int w, int h) {
    const double left = jsRound((g.cw + kGridMargin) * x);
    const double top = jsRound((g.rh + kGridMargin) * y);
    const double width = jsRound(g.cw * w + kGridMargin * (w - 1));
    const double height = jsRound(g.rh * h + kGridMargin * (h - 1));
    return {left, top, width, height};
}

double gridHeight(const GridGeom& g, int maxRow) {
    return maxRow > 0 ? maxRow * (g.rh + kGridMargin) - kGridMargin : 0;
}

PageGeom pageGeom(double gridW, double gridH) {
    PageGeom p;
    p.gridW = gridW;
    p.gridH = gridH;
    p.addBlock = QRectF(kPadX, gridH + kAddBlockTop, gridW, kAddBtnTop + kAddBtnH + kAddBlockPadBottom);
    p.addBtn = QRectF(kPadX + (gridW - kAddBtnW) / 2, p.addBlock.top() + kAddBtnTop, kAddBtnW, kAddBtnH);
    p.contentH = p.addBlock.bottom();
    return p;
}

double gridWidthForPanel(double panelW) { return std::max(0.0, panelW - 2 * kPadX - kScrollbarW); }

} // namespace fincept::screens::wdc
