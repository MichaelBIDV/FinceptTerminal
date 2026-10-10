// ChbLayoutTable.cpp — table auto layout: grid of rows/cells (colSpan/rowSpan), column min/max widths,
// width distribution, row heights, cell vertical-align, border-collapse conflict resolution.
#include "screens/chaebol_map/ChbLayout_p.h"

#include <cmath>
#include <cstdint>

namespace fincept::screens::chb {

namespace {

struct ChbtbRow {
    Box* row = nullptr;
    Box* group = nullptr;
    std::vector<Box*> cells;
};

struct ChbtbGrid {
    std::vector<ChbtbRow> rows;
    int ncols = 0;
    std::vector<Box*> cells; // all cells (with row/col/span set)
    std::vector<Box*> groups;
};

int chbtb_span_attr(const Box* cell, QStringView a, QStringView b) {
    if (!cell->node || !cell->node->src) return 1;
    const QString* v = cell->node->src->attr(a);
    if (!v) v = cell->node->src->attr(b);
    if (!v) return 1;
    bool ok = false;
    const int n = v->toInt(&ok);
    return ok ? std::clamp(n, 1, 1000) : 1;
}

void chbtb_collect(Box* t, ChbtbGrid* g) {
    std::vector<Box*> head, body, foot;
    for (Box* k : t->kids) {
        if (k->outOfFlow) continue;
        if (k->kind == BoxKind::RowGroup) {
            const Display d = k->st->display;
            (d == Display::TableHeaderGroup ? head : d == Display::TableFooterGroup ? foot : body).push_back(k);
        } else if (k->kind == BoxKind::Row) {
            body.push_back(k);
        }
    }
    std::vector<Box*> order;
    order.insert(order.end(), head.begin(), head.end());
    order.insert(order.end(), body.begin(), body.end());
    order.insert(order.end(), foot.begin(), foot.end());
    for (Box* k : order) {
        if (k->kind == BoxKind::RowGroup) {
            g->groups.push_back(k);
            for (Box* r : k->kids)
                if (r->kind == BoxKind::Row) g->rows.push_back(ChbtbRow{r, k, {}});
        } else {
            g->rows.push_back(ChbtbRow{k, nullptr, {}});
        }
    }
    // occupancy
    std::vector<std::vector<char>> occ(g->rows.size());
    for (size_t r = 0; r < g->rows.size(); ++r) {
        int c = 0;
        for (Box* cell : g->rows[r].row->kids) {
            if (cell->kind != BoxKind::Cell) continue;
            while (c < int(occ[r].size()) && occ[r][size_t(c)]) ++c;
            cell->colSpan = chbtb_span_attr(cell, u"colSpan", u"colspan");
            cell->rowSpan = std::min(chbtb_span_attr(cell, u"rowSpan", u"rowspan"), int(g->rows.size() - r));
            cell->row = int(r);
            cell->col = c;
            for (int rr = int(r); rr < int(r) + cell->rowSpan; ++rr) {
                auto& o = occ[size_t(rr)];
                if (int(o.size()) < c + cell->colSpan) o.resize(size_t(c + cell->colSpan), 0);
                for (int cc = c; cc < c + cell->colSpan; ++cc) o[size_t(cc)] = 1;
            }
            g->rows[r].cells.push_back(cell);
            g->cells.push_back(cell);
            c += cell->colSpan;
            g->ncols = std::max(g->ncols, c);
        }
    }
}

// ---- border-collapse conflict resolution
struct ChbtbEdge {
    float w = 0;
    BStyle s = BStyle::None;
    QColor c;
    int origin = 0; // 4 cell, 3 row, 2 group, 1 table
    bool hidden = false;
};

int chbtb_style_rank(BStyle s) {
    switch (s) {
    case BStyle::Double: return 8;
    case BStyle::Solid: return 7;
    case BStyle::Dashed: return 6;
    case BStyle::Dotted: return 5;
    case BStyle::Ridge: return 4;
    case BStyle::Outset: return 3;
    case BStyle::Groove: return 2;
    case BStyle::Inset: return 1;
    default: return 0;
    }
}

void chbtb_consider(ChbtbEdge* e, const Box* b, int side, int origin) {
    if (!b || !b->st) return;
    const ComputedStyle& s = *b->st;
    const BStyle st = s.borderS[size_t(side)];
    if (st == BStyle::Hidden) { e->hidden = true; return; }
    if (st == BStyle::None) return;
    const float w = s.borderW[size_t(side)];
    const bool better = w > e->w || (w == e->w && chbtb_style_rank(st) > chbtb_style_rank(e->s)) ||
                        (w == e->w && st == e->s && origin > e->origin);
    if (better) {
        e->w = w;
        e->s = st;
        e->c = s.borderColor(side);
        e->origin = origin;
    }
}

void chbtb_resolve_collapse(Box* t, ChbtbGrid& g) {
    const int nr = int(g.rows.size()), nc = g.ncols;
    // cell lookup
    std::vector<std::vector<Box*>> at(size_t(nr), std::vector<Box*>(size_t(nc), nullptr));
    for (Box* c : g.cells)
        for (int r = c->row; r < c->row + c->rowSpan && r < nr; ++r)
            for (int k = c->col; k < c->col + c->colSpan && k < nc; ++k) at[size_t(r)][size_t(k)] = c;
    auto groupOf = [&](int r) { return (r >= 0 && r < nr) ? g.rows[size_t(r)].group : nullptr; };
    auto rowOf = [&](int r) { return (r >= 0 && r < nr) ? g.rows[size_t(r)].row : nullptr; };
    for (Box* c : g.cells) {
        const int r0 = c->row, r1 = c->row + c->rowSpan, c0 = c->col, c1 = c->col + c->colSpan;
        for (int side = 0; side < 4; ++side) {
            ChbtbEdge e;
            chbtb_consider(&e, c, side, 4);
            if (side == 0) { // top
                const Box* above = r0 > 0 ? at[size_t(r0 - 1)][size_t(c0)] : nullptr;
                chbtb_consider(&e, above, 2, 4);
                chbtb_consider(&e, rowOf(r0), 0, 3);
                if (r0 > 0) chbtb_consider(&e, rowOf(r0 - 1), 2, 3);
                if (groupOf(r0) && (r0 == 0 || groupOf(r0 - 1) != groupOf(r0))) chbtb_consider(&e, groupOf(r0), 0, 2);
                if (r0 > 0 && groupOf(r0 - 1) && groupOf(r0 - 1) != groupOf(r0)) chbtb_consider(&e, groupOf(r0 - 1), 2, 2);
                if (r0 == 0) chbtb_consider(&e, t, 0, 1);
            } else if (side == 2) { // bottom
                const Box* below = r1 < nr ? at[size_t(r1)][size_t(c0)] : nullptr;
                chbtb_consider(&e, below, 0, 4);
                chbtb_consider(&e, rowOf(r1 - 1), 2, 3);
                if (r1 < nr) chbtb_consider(&e, rowOf(r1), 0, 3);
                if (groupOf(r1 - 1) && (r1 == nr || groupOf(r1) != groupOf(r1 - 1))) chbtb_consider(&e, groupOf(r1 - 1), 2, 2);
                if (r1 < nr && groupOf(r1) && groupOf(r1) != groupOf(r1 - 1)) chbtb_consider(&e, groupOf(r1), 0, 2);
                if (r1 == nr) chbtb_consider(&e, t, 2, 1);
            } else if (side == 3) { // left
                const Box* left = c0 > 0 ? at[size_t(r0)][size_t(c0 - 1)] : nullptr;
                chbtb_consider(&e, left, 1, 4);
                if (c0 == 0) {
                    chbtb_consider(&e, rowOf(r0), 3, 3);
                    chbtb_consider(&e, groupOf(r0), 3, 2);
                    chbtb_consider(&e, t, 3, 1);
                }
            } else { // right
                const Box* right = c1 < nc ? at[size_t(r0)][size_t(c1)] : nullptr;
                chbtb_consider(&e, right, 3, 4);
                if (c1 >= nc) {
                    chbtb_consider(&e, rowOf(r0), 1, 3);
                    chbtb_consider(&e, groupOf(r0), 1, 2);
                    chbtb_consider(&e, t, 1, 1);
                }
            }
            const float w = e.hidden ? 0.0f : e.w;
            c->collapsedB[side] = w;
            c->collapsedS[side] = e.hidden ? BStyle::None : e.s;
            c->collapsedC[side] = e.c;
        }
        // painting ownership: every cell paints bottom+right, first row/col also top/left
        c->collapsePaint[0] = r0 == 0;
        c->collapsePaint[3] = c0 == 0;
        c->collapsePaint[1] = true;
        c->collapsePaint[2] = true;
        c->bt = c->collapsedB[0] / 2;
        c->bb = c->collapsedB[2] / 2;
        c->bl = c->collapsedB[3] / 2;
        c->br = c->collapsedB[1] / 2;
    }
}

/// Horizontal border+padding of a cell as the table algorithm sees it (collapsed borders = the cell's halves).
float chbtb_cell_bp(const Box* cell) {
    const ComputedStyle& s = *cell->st;
    const float border = s.borderCollapse == BorderCollapse::Collapse ? cell->bl + cell->br : s.usedBorder(1) + s.usedBorder(3);
    return lc_len(s.padding[1], -1) + lc_len(s.padding[3], -1) + border;
}

/// Content min/max-content of a cell (border box). Collapsed borders replace the cell's own.
void chbtb_cell_intrinsic(LayoutCtx& c, Box* cell, float* mn, float* mx) {
    lc_intrinsic(c, cell, mn, mx);
    const ComputedStyle& s = *cell->st;
    if (s.borderCollapse == BorderCollapse::Collapse) {
        const float own = s.usedBorder(1) + s.usedBorder(3);
        const float used = cell->bl + cell->br;
        *mn += used - own;
        *mx += used - own;
    }
}

void chbtb_shift_content(Box* b, float dy) {
    if (dy == 0) return;
    for (Box* k : b->kids)
        if (!k->outOfFlow && k->kind != BoxKind::Text && k->kind != BoxKind::Inline && k->kind != BoxKind::Br) k->y += dy;
    if (b->ifc) {
        for (auto& l : b->ifc->lines) { l.top += dy; l.baseline += dy; }
        for (auto& f : b->ifc->frags) {
            f.top += dy;
            f.baseline += dy;
            if (f.type == InlineFrag::Atomic && f.box) f.box->y = f.top;
        }
    }
    if (!std::isnan(b->firstBaseline)) b->firstBaseline += dy;
    if (!std::isnan(b->lastBaseline)) b->lastBaseline += dy;
}

struct ChbtbCols {
    std::vector<float> mn, mx, pct;
    std::vector<char> fixed; ///< "constrained" column: a single-span cell has a fixed (non-%) width
};

/// Blink TablesNG cell inline constraint (NGTableTypes::CreateCellInlineConstraint, auto layout): width/min/max
/// px values are border-box sizes (+ border/padding for content-box). min = max(min-content, min-width);
/// max = width if set, else max-content, capped by max-width (which also caps min); percent kept apart.
struct ChbtbCellC {
    float mn = 0, mx = 0, pct = 0;
    bool constrained = false;
};

ChbtbCellC chbtb_cell_constraint(const Box* cell, float contentMin, float contentMaxW) {
    const ComputedStyle& s = *cell->st;
    const float bp = chbtb_cell_bp(cell);
    const bool contentBox = s.boxSizing != BoxSizing::BorderBox;
    auto fixedPx = [&](const Len& l, float* out) {
        if (l.kind != Len::Val || l.hasPct()) return false;
        *out = contentBox ? l.px + bp : std::max(l.px, bp);
        return true;
    };
    ChbtbCellC k;
    float cssW = 0, cssMin = 0, cssMax = 0;
    const bool hasW = fixedPx(s.width, &cssW);
    const bool hasMin = fixedPx(s.minW, &cssMin);
    bool hasMax = fixedPx(s.maxW, &cssMax);
    if (hasMax && hasMin) cssMax = std::max(cssMax, cssMin);
    k.mn = std::max(contentMin, hasMin ? cssMin : 0.0f);
    float contentMax = hasW ? cssW : contentMaxW;
    if (hasMax) {
        contentMax = std::min(contentMax, cssMax);
        k.mn = std::min(k.mn, cssMax);
    }
    k.mx = std::max(k.mn, contentMax);
    k.constrained = hasW;
    if (s.width.kind == Len::Val && s.width.hasPct()) k.pct = s.width.pct;
    return k;
}

void chbtb_columns(LayoutCtx& c, ChbtbGrid& g, float spacing, ChbtbCols* cols) {
    const int nc = g.ncols;
    cols->mn.assign(size_t(nc), 0.0f);
    cols->mx.assign(size_t(nc), 0.0f);
    cols->pct.assign(size_t(nc), 0.0f);
    cols->fixed.assign(size_t(nc), 0);
    std::vector<char> seen(size_t(nc), 0);
    std::vector<std::pair<const Box*, ChbtbCellC>> multi;
    for (Box* cell : g.cells) {
        float mn = 0, mx = 0;
        chbtb_cell_intrinsic(c, cell, &mn, &mx); // (kept local: cell->min/maxContent is lc_intrinsic's cache)
        const ChbtbCellC k = chbtb_cell_constraint(cell, mn, mx);
        if (cell->colSpan > 1) { multi.emplace_back(cell, k); continue; }
        const size_t j = size_t(cell->col);
        // Blink NGTableTypes::CellInlineConstraint::Encompass: a constrained (fixed-width) column keeps the max of
        // its constrained cells; unconstrained cells only raise its min.
        if (!seen[j]) {
            cols->mn[j] = k.mn;
            cols->mx[j] = k.mx;
            cols->fixed[j] = k.constrained;
            seen[j] = 1;
        } else {
            cols->mn[j] = std::max(cols->mn[j], k.mn);
            if (bool(cols->fixed[j]) == k.constrained) cols->mx[j] = std::max(cols->mx[j], k.mx);
            else if (k.constrained) cols->mx[j] = k.mx;
            cols->fixed[j] = cols->fixed[j] || k.constrained;
            cols->mx[j] = std::max(cols->mx[j], cols->mn[j]);
        }
        cols->pct[j] = std::max(cols->pct[j], k.pct);
    }
    std::stable_sort(multi.begin(), multi.end(), [](const auto& a, const auto& b) { return a.first->colSpan < b.first->colSpan; });
    for (const auto& [cell, k] : multi) {
        const int c0 = cell->col, c1 = std::min(nc, cell->col + cell->colSpan);
        const float sp = spacing * float(c1 - c0 - 1);
        float smn = sp, smx = sp;
        for (int j = c0; j < c1; ++j) { smn += cols->mn[size_t(j)]; smx += cols->mx[size_t(j)]; }
        auto spread = [&](std::vector<float>& v, float extra, float total) {
            for (int j = c0; j < c1; ++j) {
                const float share = total > 0 ? cols->mx[size_t(j)] / total : 1.0f / float(c1 - c0);
                v[size_t(j)] += extra * share;
            }
        };
        const float totMx = smx - sp;
        if (k.mn > smn) spread(cols->mn, k.mn - smn, totMx);
        if (k.mx > smx) spread(cols->mx, k.mx - smx, totMx);
    }
    for (int j = 0; j < nc; ++j) cols->mx[size_t(j)] = std::max(cols->mx[size_t(j)], cols->mn[size_t(j)]);
}

// ---- Blink LayoutUnit arithmetic (1/64 px) for the column distribution
constexpr double kLu = 64.0;
inline std::int64_t chbtb_lu(float v) { return std::int64_t(std::floor(double(v) * kLu + 1e-6)); }
inline float chbtb_px(std::int64_t raw) { return float(double(raw) / kLu); }
inline std::int64_t chbtb_muldiv(std::int64_t a, std::int64_t m, std::int64_t d) { return d ? a * m / d : 0; }

/// Blink DistributeInlineSizeToComputedInlineSizeAuto (CSS Tables 3 §3.9.2 width distribution): pick the first
/// of the min / percentage / specified / max guesses that reaches the target and grow the columns of that step
/// in proportion to their increase (remainder to the last one); above max, auto columns grow ∝ their max.
std::vector<float> chbtb_distribute(const ChbtbCols& cols, float targetPx) {
    const size_t nc = cols.mn.size();
    std::vector<std::int64_t> mn(nc), mx(nc), out(nc, 0);
    for (size_t j = 0; j < nc; ++j) {
        mn[j] = chbtb_lu(cols.mn[j]);
        mx[j] = std::max(mn[j], chbtb_lu(cols.mx[j]));
    }
    std::int64_t target = chbtb_lu(targetPx);
    auto pctSize = [&](size_t j, std::int64_t t) {
        return std::max(mn[j], std::int64_t(double(cols.pct[j]) * double(t) / 100.0));
    };
    enum { kMin, kPct, kSpec, kMax, kAbove };
    std::int64_t guess[4] = {0, 0, 0, 0}, inc[4] = {0, 0, 0, 0};
    std::int64_t autoMax = 0, fixedMax = 0;
    int autoN = 0, fixedN = 0, pctN = 0;
    float pctTotal = 0;
    // percentages resolve against the target, which the min guess may raise first
    std::int64_t minSum = 0;
    for (size_t j = 0; j < nc; ++j) minSum += mn[j];
    target = std::max(target, minSum);
    for (size_t j = 0; j < nc; ++j) {
        if (cols.pct[j] > 0) {
            ++pctN;
            pctTotal += cols.pct[j];
            const std::int64_t p = pctSize(j, target);
            guess[kMin] += mn[j];
            guess[kPct] += p;
            guess[kSpec] += p;
            guess[kMax] += p;
            inc[kPct] += p - mn[j];
        } else if (cols.fixed[j]) {
            ++fixedN;
            fixedMax += mx[j];
            guess[kMin] += mn[j];
            guess[kPct] += mn[j];
            guess[kSpec] += mx[j];
            guess[kMax] += mx[j];
            inc[kSpec] += mx[j] - mn[j];
        } else {
            ++autoN;
            autoMax += mx[j];
            guess[kMin] += mn[j];
            guess[kPct] += mn[j];
            guess[kSpec] += mn[j];
            guess[kMax] += mx[j];
            inc[kMax] += mx[j] - mn[j];
        }
    }
    int start = kAbove;
    for (int i = kMin; i < kAbove; ++i)
        if (guess[i] >= target) { start = i; break; }
    std::int64_t distributed = 0, total = 0;
    long last = -1;
    auto grow = [&](size_t j, std::int64_t base, std::int64_t delta) {
        out[j] = base + delta;
        distributed += delta;
        last = long(j);
    };
    switch (start) {
    case kMin:
        for (size_t j = 0; j < nc; ++j) out[j] = mn[j];
        break;
    case kPct:
        total = target - guess[kMin];
        for (size_t j = 0; j < nc; ++j) {
            if (cols.pct[j] > 0) grow(j, mn[j], chbtb_muldiv(total, pctSize(j, target) - mn[j], inc[kPct]));
            else out[j] = mn[j];
        }
        break;
    case kSpec:
        total = target - guess[kPct];
        for (size_t j = 0; j < nc; ++j) {
            if (cols.pct[j] > 0) out[j] = pctSize(j, target);
            else if (cols.fixed[j]) grow(j, mn[j], chbtb_muldiv(total, mx[j] - mn[j], inc[kSpec]));
            else out[j] = mn[j];
        }
        break;
    case kMax:
        total = target - guess[kSpec];
        for (size_t j = 0; j < nc; ++j) {
            if (cols.pct[j] > 0) out[j] = pctSize(j, target);
            else if (cols.fixed[j]) out[j] = mx[j];
            else grow(j, mn[j], inc[kMax] ? chbtb_muldiv(total, mx[j] - mn[j], inc[kMax]) : total / std::max(1, autoN));
        }
        break;
    default: {
        total = target - guess[kMax];
        for (size_t j = 0; j < nc; ++j) {
            if (cols.pct[j] > 0) out[j] = pctSize(j, target);
            else out[j] = mx[j];
        }
        if (autoN > 0) {
            for (size_t j = 0; j < nc; ++j)
                if (cols.pct[j] <= 0 && !cols.fixed[j])
                    grow(j, mx[j], autoMax > 0 ? chbtb_muldiv(total, mx[j], autoMax) : total / autoN);
        } else if (fixedN > 0) {
            for (size_t j = 0; j < nc; ++j)
                if (cols.pct[j] <= 0 && cols.fixed[j])
                    grow(j, mx[j], fixedMax > 0 ? chbtb_muldiv(total, mx[j], fixedMax) : total / fixedN);
        } else if (pctN > 0) {
            for (size_t j = 0; j < nc; ++j)
                if (cols.pct[j] > 0)
                    grow(j, out[j], pctTotal > 0 ? std::int64_t(double(total) * cols.pct[j] / pctTotal) : total / pctN);
        }
        break;
    }
    }
    if (last >= 0) out[size_t(last)] += total - distributed;
    std::vector<float> w(nc);
    for (size_t j = 0; j < nc; ++j) w[j] = chbtb_px(out[j]);
    return w;
}

} // namespace

void lc_table_intrinsic(LayoutCtx& c, Box* t, float* minW, float* maxW) {
    ChbtbGrid g;
    chbtb_collect(t, &g);
    const ComputedStyle& s = *t->st;
    const bool collapse = s.borderCollapse == BorderCollapse::Collapse;
    if (collapse) chbtb_resolve_collapse(t, g);
    const float sp = collapse ? 0.0f : s.borderSpacingH;
    ChbtbCols cols;
    chbtb_columns(c, g, sp, &cols);
    float mn = 0, mx = 0;
    for (int j = 0; j < g.ncols; ++j) { mn += cols.mn[size_t(j)]; mx += cols.mx[size_t(j)]; }
    const float extra = (g.ncols > 0 ? sp * float(g.ncols + 1) : 0.0f) +
                        (collapse ? 0.0f : lc_len(s.padding[1], -1) + lc_len(s.padding[3], -1) + s.usedBorder(1) + s.usedBorder(3));
    mn += extra;
    mx += extra;
    const Len& w = s.width;
    if (w.kind == Len::Val && !w.hasPct()) {
        mn = std::max(mn, w.px);
        mx = std::max(mn, w.px);
    }
    if (s.minW.kind == Len::Val && !s.minW.hasPct()) {
        mn = std::max(mn, s.minW.px);
        mx = std::max(mx, s.minW.px);
    }
    *minW = mn;
    *maxW = std::max(mn, mx);
}

void lc_table(LayoutCtx& c, Box* t, float availW, float forcedW, float cbH) {
    Q_UNUSED(cbH);
    const ComputedStyle& s = *t->st;
    ChbtbGrid g;
    chbtb_collect(t, &g);
    const bool collapse = s.borderCollapse == BorderCollapse::Collapse;
    const float spH = collapse ? 0.0f : s.borderSpacingH;
    const float spV = collapse ? 0.0f : s.borderSpacingV;
    for (Box* cell : g.cells) {
        lc_edges(cell, availW);
        cell->mt = cell->mr = cell->mb = cell->ml = 0; // margins do not apply to table cells
    }
    if (collapse) {
        chbtb_resolve_collapse(t, g);
        // the table's own border box holds half of the outer collapsed borders
        float top = 0, bot = 0, left = 0, right = 0;
        for (Box* cell : g.cells) {
            if (cell->row == 0) top = std::max(top, cell->collapsedB[0]);
            if (cell->row + cell->rowSpan >= int(g.rows.size())) bot = std::max(bot, cell->collapsedB[2]);
            if (cell->col == 0) left = std::max(left, cell->collapsedB[3]);
            if (cell->col + cell->colSpan >= g.ncols) right = std::max(right, cell->collapsedB[1]);
        }
        t->bt = top / 2; t->bb = bot / 2; t->bl = left / 2; t->br = right / 2;
        t->pt = t->pr = t->pb = t->pl = 0;
    }
    ChbtbCols cols;
    chbtb_columns(c, g, spH, &cols);
    const int nc = g.ncols;
    const float hbp = t->bl + t->br + t->pl + t->pr;
    const float spacingTotal = nc > 0 ? spH * float(nc + 1) : 0.0f;
    float sumMin = 0, sumMax = 0;
    for (int j = 0; j < nc; ++j) { sumMin += cols.mn[size_t(j)]; sumMax += cols.mx[size_t(j)]; }
    const float minW = sumMin + spacingTotal + hbp, maxW = sumMax + spacingTotal + hbp;
    float W;
    const float specW = lc_spec_width(c, t, availW);
    if (forcedW >= 0) W = std::max(forcedW, minW);
    else if (specW >= 0) W = std::max(specW, minW);
    else W = std::max(minW, std::min(availW, maxW));
    if (forcedW < 0) W = std::max(minW, lc_clamp_w(c, t, W, availW)); // min-width / max-width on the table box
    t->w = W;
    // distribute
    const float avail = W - spacingTotal - hbp;
    const std::vector<float> w = nc > 0 ? chbtb_distribute(cols, avail) : std::vector<float>{};
    std::vector<float> colX(size_t(nc) + 1, 0.0f);
    {
        float x = t->bl + t->pl + spH;
        for (int j = 0; j < nc; ++j) {
            colX[size_t(j)] = x;
            x += w[size_t(j)] + spH;
        }
        colX[size_t(nc)] = x;
    }
    const float innerW = W - hbp;
    // row heights
    const int nr = int(g.rows.size());
    std::vector<float> rowH(size_t(nr), 0.0f), rowBase(size_t(nr), -1.0f);
    auto cellWidth = [&](const Box* cell) {
        float cw = 0;
        for (int j = cell->col; j < cell->col + cell->colSpan && j < nc; ++j) cw += w[size_t(j)];
        return cw + spH * float(std::max(0, cell->colSpan - 1));
    };
    for (Box* cell : g.cells) {
        const float cw = cellWidth(cell);
        cell->w = cw;
        cell->definiteH = -1;
        const float ch = lc_layout_inside(c, cell, nullptr);
        cell->h = std::max(ch + lc_vbp(cell), lc_spec_height(cell, -1));
        if (cell->st->valign == VAlign::Baseline) {
            const float fb = lc_first_baseline(cell);
            const float base = std::isnan(fb) ? cell->h - cell->bb - cell->pb : fb;
            rowBase[size_t(cell->row)] = std::max(rowBase[size_t(cell->row)], base);
        }
    }
    for (int r = 0; r < nr; ++r) {
        const float spec = lc_spec_height(g.rows[size_t(r)].row, -1);
        if (spec > 0) rowH[size_t(r)] = spec;
    }
    for (Box* cell : g.cells) {
        if (cell->rowSpan != 1) continue;
        float need = cell->h;
        if (cell->st->valign == VAlign::Baseline && rowBase[size_t(cell->row)] >= 0) {
            const float fb = lc_first_baseline(cell);
            const float base = std::isnan(fb) ? cell->h - cell->bb - cell->pb : fb;
            need = rowBase[size_t(cell->row)] - base + cell->h;
        }
        rowH[size_t(cell->row)] = std::max(rowH[size_t(cell->row)], need);
    }
    for (Box* cell : g.cells) {
        if (cell->rowSpan <= 1) continue;
        float sum = spV * float(cell->rowSpan - 1);
        for (int r = cell->row; r < cell->row + cell->rowSpan; ++r) sum += rowH[size_t(r)];
        if (cell->h > sum) rowH[size_t(cell->row + cell->rowSpan - 1)] += cell->h - sum;
    }
    std::vector<float> rowY(size_t(nr) + 1, 0.0f);
    float y = t->bt + t->pt + spV;
    for (int r = 0; r < nr; ++r) {
        rowY[size_t(r)] = y;
        y += rowH[size_t(r)] + spV;
    }
    rowY[size_t(nr)] = y;
    float h = y - spV + (nr > 0 ? spV : 0.0f) + t->pb + t->bb;
    if (nr == 0) h = t->bt + t->pt + t->pb + t->bb;
    const float specH = lc_spec_height(t, cbH);
    if (specH > h) {
        // extra height goes to the rows proportionally (Chrome: to all rows equally when none are fixed)
        if (nr > 0) {
            const float add = (specH - h) / float(nr);
            float acc = 0;
            for (int r = 0; r < nr; ++r) {
                rowY[size_t(r)] += acc;
                rowH[size_t(r)] += add;
                acc += add;
            }
            rowY[size_t(nr)] += acc;
        }
        h = specH;
    }
    t->h = h;
    // position cells / rows / groups (relative to the table border box)
    for (Box* cell : g.cells) {
        float ch = spV * float(cell->rowSpan - 1);
        for (int r = cell->row; r < cell->row + cell->rowSpan; ++r) ch += rowH[size_t(r)];
        const float contentH = cell->h - lc_vbp(cell);
        cell->ref = t;
        cell->x = colX[size_t(cell->col)];
        cell->y = rowY[size_t(cell->row)];
        const float inner = ch - lc_vbp(cell);
        float dy = 0;
        switch (cell->st->valign) {
        case VAlign::Middle: dy = (inner - contentH) / 2; break;
        case VAlign::Bottom: dy = inner - contentH; break;
        case VAlign::Baseline: {
            const float fb = lc_first_baseline(cell);
            const float base = std::isnan(fb) ? cell->h - cell->bb - cell->pb : fb;
            if (rowBase[size_t(cell->row)] >= 0) dy = rowBase[size_t(cell->row)] - base;
            break;
        }
        default: break;
        }
        cell->h = ch;
        chbtb_shift_content(cell, std::max(0.0f, dy));
    }
    const float rowX = t->bl + t->pl + spH;
    const float rowW = std::max(0.0f, innerW - 2 * spH);
    for (int r = 0; r < nr; ++r) {
        Box* row = g.rows[size_t(r)].row;
        row->ref = t;
        row->x = rowX;
        row->y = rowY[size_t(r)];
        row->w = rowW;
        row->h = rowH[size_t(r)];
    }
    for (Box* grp : g.groups) {
        float top = kInf, bot = -kInf;
        for (const ChbtbRow& r : g.rows)
            if (r.group == grp) { top = std::min(top, r.row->y); bot = std::max(bot, r.row->y + r.row->h); }
        grp->ref = t;
        grp->x = rowX;
        grp->w = rowW;
        grp->y = std::isfinite(top) ? top : 0.0f;
        grp->h = std::isfinite(top) ? bot - top : 0.0f;
    }
    // Cells/rows are children of rows/groups in the box tree but positioned relative to the table:
    // finalize uses `ref`, so their document position is exact.
    t->firstBaseline = std::numeric_limits<float>::quiet_NaN();
    for (Box* cell : g.cells)
        if (cell->row == 0) {
            const float fb = lc_first_baseline(cell);
            t->firstBaseline = cell->y + (std::isnan(fb) ? cell->h : fb);
            break;
        }
    t->lastBaseline = t->firstBaseline;
}

} // namespace fincept::screens::chb
