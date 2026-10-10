// src/screens/hdcv_launchpad/HlpDomTable.cpp
// Launchpad CSS engine — auto table layout (TablesNG): column min/max-content with colspan
// distribution, surplus by max / deficit by (max − min), LayoutUnit columns, collapsed borders split
// half/half between rows, vertical-align: middle cells; and table painting (backgrounds, collapsed
// borders, cell content, sticky header cells).
#include "screens/hdcv_launchpad/HlpDom.h"

#include "screens/hdcv_launchpad/HlpDomLayout_p.h"

#include <QApplication>
#include <QDesktopServices>
#include <QHash>
#include <QJsonArray>
#include <QJsonDocument>
#include <QJsonObject>
#include <QCursor>
#include <QHelpEvent>
#include <QMouseEvent>
#include <QPaintEvent>
#include <QResizeEvent>
#include <QPainter>
#include <QPainterPath>
#include <QPointer>
#include <QTextBoundaryFinder>
#include <QToolTip>
#include <QUrl>
#include <QWheelEvent>

#include <algorithm>
#include <cmath>
#include <limits>

namespace fincept::screens::hlp::hlpdom {

namespace {

/// A column for Blink's auto distribution, in LayoutUnit raw units (1/kLU px).
struct hlptb_Col {
    qint64 mn = 0, mx = 0;
    bool constrained = false; ///< a cell of the column has a fixed width
};

qint64 hlptb_raw(float v) {
    return qint64(std::llround(double(v) * double(kLU)));
}

/// LayoutUnit::MulDiv: 64-bit product, truncating division.
qint64 hlptb_mulDiv(qint64 v, qint64 m, qint64 d) {
    return d == 0 ? 0 : (v * m) / d;
}

/// Blink table_layout_utils.cc DistributeInlineSizeToComputedInlineSizeAuto (no percent columns):
/// the min / specified / max guesses, proportional growth by MulDiv, the last growing column takes
/// the rounding remainder.
QVector<qint64> hlptb_distribute(qint64 target, const QVector<hlptb_Col>& cols, bool treatConstrained) {
    const int n = int(cols.size());
    QVector<qint64> out(n, 0);
    qint64 gMin = 0, gSpec = 0, gMax = 0, incSpec = 0, incMax = 0, autoMax = 0, fixedMax = 0;
    int nAuto = 0, nFixed = 0;
    for (const hlptb_Col& c : cols) {
        gMin += c.mn;
        gMax += c.mx;
        if (c.constrained) {
            ++nFixed;
            fixedMax += c.mx;
            gSpec += c.mx;
            incSpec += c.mx - c.mn;
        } else {
            ++nAuto;
            autoMax += c.mx;
            gSpec += c.mn;
            incMax += c.mx - c.mn;
        }
    }
    target = std::max(target, gMin);
    if (gMin >= target) {
        for (int i = 0; i < n; ++i)
            out[i] = cols[i].mn;
    } else if (gSpec >= target) { // fixed columns grow
        const qint64 dist = target - gMin;
        qint64 rem = dist;
        int last = -1;
        for (int i = 0; i < n; ++i) {
            if (!cols[i].constrained) {
                out[i] = cols[i].mn;
                continue;
            }
            last = i;
            const qint64 d = incSpec > 0 ? hlptb_mulDiv(dist, cols[i].mx - cols[i].mn, incSpec) : dist / nFixed;
            rem -= d;
            out[i] = cols[i].mn + d;
        }
        if (rem && last >= 0)
            out[last] += rem;
    } else if (gMax >= target) { // auto columns grow from min towards max
        const qint64 dist = target - gSpec;
        const bool exact = target == gMax;
        qint64 rem = exact ? 0 : dist;
        int last = -1;
        for (int i = 0; i < n; ++i) {
            if (cols[i].constrained || exact) {
                out[i] = cols[i].mx;
                continue;
            }
            last = i;
            const qint64 d = incMax > 0 ? hlptb_mulDiv(dist, cols[i].mx - cols[i].mn, incMax) : dist / nAuto;
            rem -= d;
            out[i] = cols[i].mn + d;
        }
        if (rem && last >= 0)
            out[last] += rem;
    } else { // above max
        const qint64 dist = target - gMax;
        qint64 rem = dist;
        int last = -1;
        const bool growAuto = nAuto > 0;
        for (int i = 0; i < n; ++i) {
            const bool grows = growAuto ? !cols[i].constrained : (treatConstrained && cols[i].constrained);
            if (!grows) {
                out[i] = cols[i].mx;
                continue;
            }
            last = i;
            const qint64 total = growAuto ? autoMax : fixedMax;
            const qint64 d = total > 0 ? hlptb_mulDiv(dist, cols[i].mx, total) : dist / (growAuto ? nAuto : nFixed);
            rem -= d;
            out[i] = cols[i].mx + d;
        }
        if (rem && last >= 0)
            out[last] += rem;
    }
    return out;
}

} // namespace

float Layout::cellHPad(Box* c) {
    const Style* s = c->st;
    return s ? s->pl + s->pr + (s->bw[1] + s->bw[3]) / 2.0f : 0.0f;
}

void Layout::buildTable(Box* t, TableModel& tm) {
    tm.rows.clear();
    tm.nCols = 0;
    for (Box* r : t->kids) {
        if (r->kind != BK::Row)
            continue;
        QVector<Box*> cells;
        int c = 0;
        for (Box* cell : r->kids) {
            cell->col = c;
            cell->span = cell->st ? std::max(1, cell->st->colspan) : 1;
            c += cell->span;
            cells.push_back(cell);
        }
        tm.nCols = std::max(tm.nCols, c);
        tm.rows.push_back(cells);
    }
    tm.colMin.fill(0.0f, tm.nCols);
    tm.colMax.fill(0.0f, tm.nCols);
    // single-column cells first
    for (auto& cells : tm.rows)
        for (Box* cell : cells) {
            if (cell->span != 1)
                continue;
            cellIntrinsic(cell);
            tm.colMin[cell->col] = std::max(tm.colMin[cell->col], cell->minC);
            tm.colMax[cell->col] = std::max(tm.colMax[cell->col], cell->maxC);
        }
    tm.colFixed.fill(false, tm.nCols);
    for (auto& cells : tm.rows)
        for (Box* cell : cells)
            if (cell->span == 1 && cell->st && !std::isnan(cell->st->width))
                tm.colFixed[cell->col] = true;
    // spanning cells, Blink's way (DistributeColspanCellToColumnsAuto): sorted by span then start
    // column; the cell's min, then its max, go through the auto distribution over its columns
    QVector<Box*> wide;
    for (auto& cells : tm.rows)
        for (Box* cell : cells)
            if (cell->span > 1)
                wide.push_back(cell);
    std::stable_sort(wide.begin(), wide.end(), [](Box* a, Box* b) {
        return a->span == b->span ? a->col < b->col : a->span < b->span;
    });
    for (Box* cell : wide) {
        cellIntrinsic(cell);
        const int a = cell->col, e = std::min(tm.nCols, cell->col + cell->span);
        if (a >= e)
            continue;
        QVector<hlptb_Col> span;
        for (int c = a; c < e; ++c)
            span.push_back({hlptb_raw(tm.colMin[c]), hlptb_raw(tm.colMax[c]), bool(tm.colFixed[c])});
        const bool fixed = cell->st && !std::isnan(cell->st->width);
        QVector<qint64> got = hlptb_distribute(hlptb_raw(cell->minC), span, true);
        for (int i = 0; i < span.size(); ++i)
            span[i].mn = std::max(span[i].mn, got[i]);
        got = hlptb_distribute(hlptb_raw(cell->maxC), span, fixed);
        for (int i = 0; i < span.size(); ++i) {
            span[i].mx = std::max(std::max(span[i].mn, span[i].mx), got[i]);
            tm.colMin[a + i] = float(double(span[i].mn) / double(kLU));
            tm.colMax[a + i] = float(double(span[i].mx) / double(kLU));
            if (fixed)
                tm.colFixed[a + i] = true;
        }
    }
}

void Layout::cellIntrinsic(Box* cell) {
    if (cell->intrinsicDone)
        return;
    cell->intrinsicDone = true;
    float mn = 0, mx = 0;
    if (cell->ifc)
        ifcIntrinsic(cell, mn, mx);
    else
        for (Box* k : cell->kids) {
            intrinsic(k);
            const float m = k->st ? k->st->ml + k->st->mr : 0;
            mn = std::max(mn, k->minC + m);
            mx = std::max(mx, k->maxC + m);
        }
    const float hp = cellHPad(cell);
    cell->minC = luCeil(mn + hp);
    cell->maxC = luCeil(std::max(mn, mx) + hp);
    // TablesNG: a cell's max-width caps its column contributions (measured: songuon td
    // max-width 210/150 → columns 533.1 / 380.8 = 210:150), the cell itself still fills the column.
    if (const Style* st = cell->st) {
        if (!std::isnan(st->maxWidth)) {
            cell->maxC = std::min(cell->maxC, st->maxWidth);
            cell->minC = std::min(cell->minC, st->maxWidth);
        }
        if (!std::isnan(st->width)) {
            cell->minC = std::max(cell->minC, st->width);
            cell->maxC = std::max(cell->minC, st->width);
        }
    }
}

float Layout::layoutTable(Box* t, float cw, float pl, float pt) {
    TableModel tm;
    buildTable(t, tm);
    const int nc = tm.nCols;
    QVector<float> cols(nc, 0.0f);
    float sMin = 0;
    for (int c = 0; c < nc; ++c)
        sMin += tm.colMin[c];
    float tw = cw; // table content width (width:100% → the table box width)
    if (tw < sMin)
        tw = sMin;
    {
        // SynchronizeAssignableTableInlineSizeAndColumns → the auto distribution, in LayoutUnits
        QVector<hlptb_Col> cc;
        for (int c = 0; c < nc; ++c)
            cc.push_back({hlptb_raw(tm.colMin[c]), hlptb_raw(tm.colMax[c]), bool(tm.colFixed[c])});
        const QVector<qint64> got = hlptb_distribute(hlptb_raw(tw), cc, true);
        for (int c = 0; c < nc; ++c)
            cols[c] = float(double(got[c]) / double(kLU));
    }
    if (tw > cw)
        t->w = tw + (t->w - cw); // table grows to its min-content
    QVector<float> colX(nc + 1, 0.0f);
    for (int c = 0; c < nc; ++c)
        colX[c + 1] = colX[c] + cols[c];

    // collapsed horizontal edges: width between rows = max(bottom of above, top of below)
    const int nr = int(tm.rows.size());
    auto bottomW = [](Box* cell) { return cell->st ? cell->st->bw[2] : 0.0f; };
    auto topW = [](Box* cell) { return cell->st ? cell->st->bw[0] : 0.0f; };
    QVector<QVector<float>> edge(nr + 1, QVector<float>(nc, 0.0f));
    for (int r = 0; r < nr; ++r)
        for (Box* cell : tm.rows[r])
            for (int c = cell->col; c < std::min(nc, cell->col + cell->span); ++c) {
                edge[r][c] = std::max(edge[r][c], topW(cell));
                edge[r + 1][c] = std::max(edge[r + 1][c], bottomW(cell));
            }
    float tableTopHalf = 0, tableBotHalf = 0;
    for (int c = 0; c < nc; ++c) {
        tableTopHalf = std::max(tableTopHalf, edge[0][c] / 2.0f);
        tableBotHalf = std::max(tableBotHalf, edge[nr][c] / 2.0f);
    }
    float y = tableTopHalf;
    int ri = 0;
    for (Box* r : t->kids) {
        if (r->kind != BK::Row)
            continue;
        const QVector<Box*>& cells = tm.rows[ri];
        float rowH = 0;
        for (Box* cell : cells) {
            float ht = 0, hb = 0;
            for (int c = cell->col; c < std::min(nc, cell->col + cell->span); ++c) {
                ht = std::max(ht, edge[ri][c] / 2.0f);
                hb = std::max(hb, edge[ri + 1][c] / 2.0f);
            }
            cell->halfTop = ht;
            cell->halfBot = hb;
            const float w = colX[std::min(nc, cell->col + cell->span)] - colX[cell->col];
            layoutCell(cell, w);
            rowH = std::max(rowH, cell->h);
        }
        for (Box* cell : cells) {
            const float intrinsicH = cell->h;
            const float shift = luFloor((rowH - intrinsicH) / 2.0f); // vertical-align: middle
            cell->contentShiftY = shift;
            if (shift != 0.0f) {
                if (cell->ifc) {
                    for (Line& L : cell->ifc->lines) {
                        L.top += shift;
                        L.baseline += shift;
                        for (Frag& fr : L.frags)
                            if (fr.box->kind == BK::Atomic)
                                fr.box->y += shift;
                    }
                } else {
                    for (Box* k : cell->kids)
                        k->y += shift;
                }
            }
            cell->h = rowH;
            cell->x = colX[cell->col];
            cell->y = 0;
        }
        r->x = pl;
        r->y = pt + y;
        r->w = colX[nc];
        r->h = rowH;
        y += rowH;
        ++ri;
    }
    t->halfTop = tableTopHalf;
    t->halfBot = tableBotHalf;
    return y + tableBotHalf;
}

void Layout::layoutCell(Box* cell, float w) {
    const Style* st = cell->st;
    cell->w = w;
    const float pl = (st ? st->pl + st->bw[3] / 2.0f : 0), pr = (st ? st->pr + st->bw[1] / 2.0f : 0);
    const float pt = (st ? st->pt : 0) + cell->halfTop, pb = (st ? st->pb : 0) + cell->halfBot;
    const float cw = std::max(0.0f, w - pl - pr);
    float ch;
    if (cell->ifc)
        ch = layoutLines(cell, cw, pl, pt);
    else
        ch = layoutFlowCell(cell, cw, pl, pt);
    cell->h = ch + pt + pb;
    cell->mTop = {};
    cell->mBot = {};
}

float Layout::layoutFlowCell(Box* cell, float cw, float pl, float pt) {
    // cells are BFC roots: children margins stay inside
    Box::MSet pending;
    float cursor = 0;
    bool first = true;
    for (Box* k : cell->kids) {
        layoutBox(k, cw, NAN);
        k->x = pl + (k->st ? k->st->ml : 0);
        Box::MSet top = pending;
        top.add(k->mTop);
        k->y = pt + cursor + (first ? k->mTop.value() : top.value());
        cursor = k->y - pt + k->h;
        pending = k->mBot;
        first = false;
    }
    return cursor + pending.value();
}

// ---- painting (the table's part of HlpDomPaint.cpp) ----
/// Chrome's order: row + cell backgrounds, then the table's collapsed borders, then cell content;
/// sticky cells (th) are positioned layers painted last — their opaque background covers the upper
/// half of the header's bottom border (measured: only the lower half-pixel row shows).
void ViewImpl::paintTable(QPainter& p, Box* t, const QColor& color, bool ul, const QRectF& clip) {
    auto visible = [&](Box* r) { return !(r->ay > clip.bottom() + 1 || r->ay + r->h < clip.top() - 1); };
    auto isSticky = [&](Box* c) { return c->st && c->st->sticky; };
    for (Box* r : t->kids) {
        if (r->kind != BK::Row || !visible(r))
            continue;
        const QColor rc = colorOf(r, color);
        paintBoxDecor(p, r, QRectF(r->ax, r->ay, r->w, r->h), rc, false);
        for (Box* cell : r->kids)
            if (!isSticky(cell))
                paintBoxDecor(p, cell, QRectF(cell->ax, cell->ay, cell->w, cell->h), colorOf(cell, rc), true, DecorBg);
    }
    for (Box* r : t->kids) {
        if (r->kind != BK::Row || !visible(r))
            continue;
        const QColor rc = colorOf(r, color);
        for (Box* cell : r->kids)
            paintBoxDecor(p, cell, QRectF(cell->ax, cell->ay, cell->w, cell->h), colorOf(cell, rc), true, DecorBorder);
    }
    QVector<QPair<Box*, QColor>> stickyCells;
    for (Box* r : t->kids) {
        if (r->kind != BK::Row)
            continue;
        const QColor rc = colorOf(r, color);
        for (Box* cell : r->kids) {
            if (isSticky(cell)) {
                stickyCells.push_back({cell, rc});
                continue;
            }
            if (visible(r))
                paintCellContent(p, cell, rc, ul, clip);
        }
    }
    for (const auto& sc : stickyCells) {
        Box* cell = sc.first;
        const float shift = stickyShift(cell);
        p.save();
        p.translate(0, shift);
        // a sticky cell is its own composited layer: Chrome snaps its edges to whole pixels of the
        // scroller's contents layer (half-pixel snap, then down: floor(snap(v)) — measured on 200 probes
        // of th{position:sticky} + collapsed border-bottom, 27/09), then the compositor moves it by
        // (shift − scroll) unsnapped. The cell rect ends at the CENTRE of its collapsed bottom border, so
        // this decides whether the header line shows fully, half or not at all. Across the row the
        // background starts on the whole pixel at or after its snapped left edge and ends on the snapped
        // right edge (a .5 → half coverage): the header line shows under the .5 table edge and at half
        // strength under a .5 column boundary (tien VN-INDEX 1511.5 / 1603.6, SỔ NGUỒN 512.3, 27/09).
        auto ry = [&](float v) { return std::floor(snap(v + poy)) - poy; };
        const float lx = std::ceil(snap(cell->ax + pox)) - pox, rxe = snap(cell->ax + cell->w + pox) - pox;
        const QRectF lr(lx, ry(cell->ay), rxe - lx, ry(cell->ay + cell->h) - ry(cell->ay));
        paintBoxDecor(p, cell, lr, colorOf(cell, sc.second), true, DecorBg);
        paintCellContent(p, cell, sc.second, ul, clip.translated(0, -shift));
        p.restore();
    }
}

void ViewImpl::paintCellContent(QPainter& p, Box* cell, const QColor& inherited, bool ulInh, const QRectF& clip) {
    const QColor color = colorOf(cell, inherited);
    const bool ul = ulInh || (cell->st && (cell->st->underline || (cell->st->hoverUnderline && hovered(cell))));
    if (cell->ifc)
        paintIfc(p, cell, color, ul, clip);
    else
        for (Box* k : cell->kids)
            paintBox(p, k, color, ul, clip);
}

} // namespace fincept::screens::hlp::hlpdom
