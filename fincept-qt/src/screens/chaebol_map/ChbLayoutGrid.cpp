// ChbLayoutGrid.cpp — CSS grid: track lists (px/%/fr/auto/min|max-content/minmax/fit-content/repeat,
// auto-fill/auto-fit), line-based + row-major auto placement, track sizing (intrinsic, maximize, flexible,
// stretch), implicit auto rows, item stretch/alignment.
#include "screens/chaebol_map/ChbLayout_p.h"

#include <cmath>

namespace fincept::screens::chb {

namespace {

struct ChbgItem {
    Box* b = nullptr;
    int c0 = 0, c1 = 1, r0 = 0, r1 = 1;
    float minC = 0, maxC = 0; // outer contributions
};

struct ChbgTrack {
    TrackSize::Kind minK = TrackSize::Auto, maxK = TrackSize::Auto;
    float minPx = 0, maxPx = 0, fr = 0;
    float base = 0, limit = kInf;
    bool repeated = false; // from an auto-fit repeat (collapsible)
    bool collapsed = false; // empty auto-fit track: size 0 and its gutters collapse
    bool used = false;
};

void chbg_decompose(const TrackSize& t, float base, ChbgTrack* o) {
    auto simple = [&](const TrackSize& s, TrackSize::Kind* k, float* px) {
        *k = s.kind;
        if (s.kind == TrackSize::Fixed || s.kind == TrackSize::FitContent) {
            if (s.len.hasPct() && base < 0) *k = TrackSize::Auto;
            else *px = lc_len(s.len, base);
        }
    };
    if (t.kind == TrackSize::MinMax && t.mn && t.mx) {
        simple(*t.mn, &o->minK, &o->minPx);
        simple(*t.mx, &o->maxK, &o->maxPx);
        if (t.mx->kind == TrackSize::Fr) o->fr = t.mx->fr;
    } else if (t.kind == TrackSize::Fr) {
        o->minK = TrackSize::Auto;
        o->maxK = TrackSize::Fr;
        o->fr = t.fr;
    } else if (t.kind == TrackSize::FitContent) {
        o->minK = TrackSize::Auto;
        o->maxK = TrackSize::FitContent;
        if (!(t.len.hasPct() && base < 0)) o->maxPx = lc_len(t.len, base);
    } else {
        simple(t, &o->minK, &o->minPx);
        simple(t, &o->maxK, &o->maxPx);
    }
}

/// Explicit columns for a content width (auto-repeat count resolved). base < 0 = indefinite.
std::vector<ChbgTrack> chbg_columns(const ComputedStyle& s, float base, float gap) {
    std::vector<ChbgTrack> out;
    const TrackList* tl = s.gridCols.get();
    if (!tl || tl->none) return out;
    auto push = [&](const std::vector<TrackSize>& v, bool rep) {
        for (const TrackSize& t : v) {
            ChbgTrack k;
            chbg_decompose(t, base, &k);
            k.repeated = rep && tl->autoRepeat == 2;
            out.push_back(k);
        }
    };
    push(tl->before, false);
    if (tl->autoRepeat) {
        int count = 1;
        if (base >= 0) {
            float fixed = 0;
            int nFixedTracks = 0;
            for (const auto* v : {&tl->before, &tl->after})
                for (const TrackSize& t : *v) {
                    ChbgTrack k;
                    chbg_decompose(t, base, &k);
                    fixed += k.maxK == TrackSize::Fixed ? k.maxPx : (k.minK == TrackSize::Fixed ? k.minPx : 0.0f);
                    ++nFixedTracks;
                }
            float rep = 0;
            for (const TrackSize& t : tl->repeat) {
                ChbgTrack k;
                chbg_decompose(t, base, &k);
                rep += k.maxK == TrackSize::Fixed ? k.maxPx : (k.minK == TrackSize::Fixed ? k.minPx : 0.0f);
            }
            const int pat = int(tl->repeat.size());
            if (rep > 0) {
                // largest count with fixed + count·rep + (tracks − 1)·gap ≤ base
                count = 1;
                for (int k2 = 2; k2 < 10000; ++k2) {
                    const int tracks = nFixedTracks + k2 * pat;
                    if (fixed + float(k2) * rep + float(tracks - 1) * gap > base + 0.01f) break;
                    count = k2;
                }
            }
        }
        for (int i = 0; i < count; ++i) push(tl->repeat, true);
    }
    push(tl->after, false);
    return out;
}

int chbg_line_index(const GridLine& g, int explicitTracks) {
    if (g.line > 0) return g.line - 1;
    if (g.line < 0) return std::max(0, explicitTracks + 1 + g.line);
    return 0;
}

/// Resolve [start,end) on one axis; returns false when the start is auto (auto-placed), with *span set.
bool chbg_axis(const GridLine& s, const GridLine& e, int explicitTracks, int* a, int* b, int* span) {
    *span = 1;
    const bool sLine = !s.isAuto && s.span == 0, eLine = !e.isAuto && e.span == 0;
    if (sLine && eLine) {
        *a = chbg_line_index(s, explicitTracks);
        *b = chbg_line_index(e, explicitTracks);
        if (*b < *a) std::swap(*a, *b);
        if (*b == *a) *b = *a + 1;
        *span = *b - *a;
        return true;
    }
    if (sLine) {
        *a = chbg_line_index(s, explicitTracks);
        *span = (!e.isAuto && e.span > 0) ? e.span : 1;
        *b = *a + *span;
        return true;
    }
    if (eLine) {
        *b = chbg_line_index(e, explicitTracks);
        *span = (!s.isAuto && s.span > 0) ? s.span : 1;
        *a = std::max(0, *b - *span);
        if (*b <= *a) *b = *a + 1;
        return true;
    }
    *span = (!s.isAuto && s.span > 0) ? s.span : ((!e.isAuto && e.span > 0) ? e.span : 1);
    return false;
}

struct ChbgGrid {
    std::vector<std::vector<char>> occ; // [row][col]
    int cols = 0;
    bool free(int r, int c0, int c1, int rs) {
        for (int r2 = r; r2 < r + rs; ++r2) {
            if (r2 >= int(occ.size())) continue;
            for (int c = c0; c < c1; ++c)
                if (c < int(occ[size_t(r2)].size()) && occ[size_t(r2)][size_t(c)]) return false;
        }
        return true;
    }
    void mark(int r0, int r1, int c0, int c1) {
        while (int(occ.size()) < r1) occ.emplace_back(size_t(cols), 0);
        for (int r = r0; r < r1; ++r) {
            if (int(occ[size_t(r)].size()) < c1) occ[size_t(r)].resize(size_t(c1), 0);
            for (int c = c0; c < c1; ++c) occ[size_t(r)][size_t(c)] = 1;
        }
    }
};

void chbg_place(const ComputedStyle& s, std::vector<ChbgItem>& items, int* nCols, int* nRows) {
    const int explicitCols = *nCols;
    int explicitRows = (s.gridRows && !s.gridRows->none) ? int(s.gridRows->before.size() + s.gridRows->after.size()) : 0;
    ChbgGrid g;
    g.cols = std::max(1, explicitCols);
    int maxCol = g.cols;
    // pass 1: fully definite items
    std::vector<char> placed(items.size(), 0);
    for (size_t i = 0; i < items.size(); ++i) {
        ChbgItem& it = items[i];
        const ComputedStyle& ks = *it.b->st;
        int ca, cb, cs, ra, rb, rs;
        const bool cDef = chbg_axis(ks.colStart, ks.colEnd, explicitCols, &ca, &cb, &cs);
        const bool rDef = chbg_axis(ks.rowStart, ks.rowEnd, explicitRows, &ra, &rb, &rs);
        if (cDef && rDef) {
            it.c0 = ca; it.c1 = cb; it.r0 = ra; it.r1 = rb;
            maxCol = std::max(maxCol, cb);
            g.cols = maxCol;
            g.mark(ra, rb, ca, cb);
            placed[i] = 1;
        }
    }
    // pass 2: row-locked items (definite row, auto column)
    for (size_t i = 0; i < items.size(); ++i) {
        if (placed[i]) continue;
        ChbgItem& it = items[i];
        const ComputedStyle& ks = *it.b->st;
        int ca, cb, cs, ra, rb, rs;
        const bool cDef = chbg_axis(ks.colStart, ks.colEnd, explicitCols, &ca, &cb, &cs);
        const bool rDef = chbg_axis(ks.rowStart, ks.rowEnd, explicitRows, &ra, &rb, &rs);
        if (!rDef || cDef) continue;
        cs = std::min(cs, maxCol);
        int c = 0;
        while (c + cs <= maxCol && !g.free(ra, c, c + cs, rb - ra)) ++c;
        if (c + cs > maxCol) { c = maxCol; maxCol += cs; g.cols = maxCol; }
        it.c0 = c; it.c1 = c + cs; it.r0 = ra; it.r1 = rb;
        g.mark(ra, rb, it.c0, it.c1);
        placed[i] = 1;
    }
    // pass 3: auto placement (row flow, sparse)
    int curR = 0, curC = 0;
    for (size_t i = 0; i < items.size(); ++i) {
        if (placed[i]) continue;
        ChbgItem& it = items[i];
        const ComputedStyle& ks = *it.b->st;
        int ca, cb, cs, ra, rb, rs;
        const bool cDef = chbg_axis(ks.colStart, ks.colEnd, explicitCols, &ca, &cb, &cs);
        chbg_axis(ks.rowStart, ks.rowEnd, explicitRows, &ra, &rb, &rs);
        if (cDef) {
            if (ca < curC) ++curR;
            curC = ca;
            while (!g.free(curR, ca, cb, rs)) ++curR;
            it.c0 = ca; it.c1 = cb;
            maxCol = std::max(maxCol, cb);
            g.cols = maxCol;
        } else {
            cs = std::min(cs, std::max(1, maxCol));
            for (int guard = 0; guard < 100000; ++guard) {
                if (curC + cs > maxCol) { curC = 0; ++curR; continue; }
                if (g.free(curR, curC, curC + cs, rs)) break;
                ++curC;
            }
            it.c0 = curC; it.c1 = curC + cs;
        }
        it.r0 = curR; it.r1 = curR + rs;
        g.mark(it.r0, it.r1, it.c0, it.c1);
        curC = it.c1;
    }
    int rows = explicitRows;
    for (const auto& it : items) rows = std::max(rows, it.r1);
    *nCols = maxCol;
    *nRows = rows;
}

void chbg_size_columns(LayoutCtx& c, std::vector<ChbgTrack>& T, std::vector<ChbgItem>& items, float avail, float gap,
                       Align justify) {
    Q_UNUSED(c);
    const int n = int(T.size());
    for (auto& t : T) {
        t.base = t.minK == TrackSize::Fixed ? t.minPx : 0.0f;
        t.limit = (t.maxK == TrackSize::Fixed) ? t.maxPx : kInf;
        if (t.limit < t.base) t.limit = t.base;
    }
    auto spansFlex = [&](const ChbgItem& it) {
        for (int i = it.c0; i < it.c1 && i < n; ++i)
            if (T[size_t(i)].maxK == TrackSize::Fr) return true;
        return false;
    };
    // single-span items
    std::vector<float> maxFromItems(size_t(n), -1.0f);
    for (const ChbgItem& it : items) {
        if (it.c1 - it.c0 != 1 || it.c0 >= n) continue;
        ChbgTrack& t = T[size_t(it.c0)];
        t.used = true;
        if (t.minK == TrackSize::Auto || t.minK == TrackSize::MinContent) t.base = std::max(t.base, it.minC);
        else if (t.minK == TrackSize::MaxContent) t.base = std::max(t.base, it.maxC);
        float want = -1;
        if (t.maxK == TrackSize::Auto || t.maxK == TrackSize::MaxContent) want = it.maxC;
        else if (t.maxK == TrackSize::MinContent) want = it.minC;
        else if (t.maxK == TrackSize::FitContent) want = std::min(it.maxC, std::max(t.maxPx, it.minC));
        if (want >= 0) maxFromItems[size_t(it.c0)] = std::max(maxFromItems[size_t(it.c0)], want);
    }
    for (int i = 0; i < n; ++i) {
        ChbgTrack& t = T[size_t(i)];
        if (t.maxK != TrackSize::Fixed && t.maxK != TrackSize::Fr) t.limit = maxFromItems[size_t(i)] >= 0 ? maxFromItems[size_t(i)] : t.base;
        if (t.maxK == TrackSize::Fr) t.limit = t.base;
        if (t.limit < t.base) t.limit = t.base;
    }
    // multi-span items (not spanning flexible tracks): grow intrinsic bases/limits equally
    for (const ChbgItem& it : items) {
        const int span = it.c1 - it.c0;
        if (span < 2 || spansFlex(it)) continue;
        float sumBase = gap * float(span - 1), sumLimit = gap * float(span - 1);
        std::vector<int> intr;
        for (int i = it.c0; i < it.c1 && i < n; ++i) {
            T[size_t(i)].used = true;
            sumBase += T[size_t(i)].base;
            sumLimit += T[size_t(i)].limit;
            if (T[size_t(i)].minK != TrackSize::Fixed) intr.push_back(i);
        }
        if (intr.empty()) continue;
        if (it.minC > sumBase) {
            const float add = (it.minC - sumBase) / float(intr.size());
            for (int i : intr) {
                T[size_t(i)].base += add;
                T[size_t(i)].limit = std::max(T[size_t(i)].limit, T[size_t(i)].base);
            }
        }
        if (it.maxC > sumLimit) {
            const float add = (it.maxC - sumLimit) / float(intr.size());
            for (int i : intr)
                if (T[size_t(i)].maxK != TrackSize::Fixed) T[size_t(i)].limit += add;
        }
    }
    for (const ChbgItem& it : items)
        for (int i = it.c0; i < it.c1 && i < n; ++i) T[size_t(i)].used = true;
    int live = 0;
    for (const auto& t : T) live += t.collapsed ? 0 : 1;
    const float gaps = live > 1 ? gap * float(live - 1) : 0.0f;
    if (avail < 0) {
        for (auto& t : T) t.base = std::max(t.base, t.maxK == TrackSize::Fr ? t.base : t.limit);
        return;
    }
    // maximize tracks (non-flexible)
    auto sumBase = [&]() {
        float s = gaps;
        for (const auto& t : T) s += t.base;
        return s;
    };
    for (int iter = 0; iter < 8; ++iter) {
        float free = avail - sumBase();
        if (free <= 0.001f) break;
        std::vector<int> grow;
        for (int i = 0; i < n; ++i)
            if (T[size_t(i)].maxK != TrackSize::Fr && T[size_t(i)].base < T[size_t(i)].limit - 0.001f) grow.push_back(i);
        if (grow.empty()) break;
        const float each = free / float(grow.size());
        for (int i : grow) T[size_t(i)].base = std::min(T[size_t(i)].limit, T[size_t(i)].base + each);
    }
    // expand flexible tracks
    bool anyFr = false;
    for (const auto& t : T) anyFr = anyFr || t.maxK == TrackSize::Fr;
    if (anyFr) {
        std::vector<char> inflexible(size_t(n), 0);
        for (int iter = 0; iter < 32; ++iter) {
            float left = avail - gaps, sumFr = 0;
            for (int i = 0; i < n; ++i) {
                const ChbgTrack& t = T[size_t(i)];
                if (t.maxK == TrackSize::Fr && !inflexible[size_t(i)]) sumFr += t.fr;
                else left -= t.base;
            }
            const float frSize = left / std::max(1.0f, sumFr);
            bool changed = false;
            for (int i = 0; i < n; ++i) {
                ChbgTrack& t = T[size_t(i)];
                if (t.maxK != TrackSize::Fr || inflexible[size_t(i)]) continue;
                if (t.base > frSize * t.fr) {
                    inflexible[size_t(i)] = 1;
                    changed = true;
                }
            }
            if (!changed) {
                for (int i = 0; i < n; ++i) {
                    ChbgTrack& t = T[size_t(i)];
                    if (t.maxK == TrackSize::Fr && !inflexible[size_t(i)]) t.base = std::max(t.base, frSize * t.fr);
                }
                break;
            }
        }
    }
    // stretch auto tracks
    if (justify == Align::Normal || justify == Align::Stretch) {
        const float free = avail - sumBase();
        if (free > 0.001f) {
            std::vector<int> autos;
            for (int i = 0; i < n; ++i)
                if (T[size_t(i)].maxK == TrackSize::Auto) autos.push_back(i);
            if (!autos.empty())
                for (int i : autos) T[size_t(i)].base += free / float(autos.size());
        }
    }
}

std::vector<ChbgItem> chbg_items(const Box* b) {
    std::vector<ChbgItem> items;
    for (Box* k : b->kids) {
        if (k->outOfFlow || k->kind == BoxKind::Text) continue;
        ChbgItem it;
        it.b = k;
        items.push_back(it);
    }
    std::stable_sort(items.begin(), items.end(), [](const ChbgItem& a, const ChbgItem& d) { return a.b->st->order < d.b->st->order; });
    return items;
}

void chbg_collapse_autofit(std::vector<ChbgTrack>& T, const std::vector<ChbgItem>& items) {
    std::vector<char> used(T.size(), 0);
    for (const auto& it : items)
        for (int i = it.c0; i < it.c1 && i < int(T.size()); ++i) used[size_t(i)] = 1;
    for (size_t i = 0; i < T.size(); ++i)
        if (T[i].repeated && !used[i]) {
            T[i].minK = T[i].maxK = TrackSize::Fixed;
            T[i].minPx = T[i].maxPx = 0;
            T[i].fr = 0;
            T[i].collapsed = true;
        }
}

} // namespace

void lc_grid_intrinsic(LayoutCtx& c, Box* b, float* minW, float* maxW) {
    const ComputedStyle& s = *b->st;
    const float gap = s.colGap.kind == Len::Val ? lc_len(s.colGap, -1) : 0.0f;
    std::vector<ChbgTrack> T = chbg_columns(s, -1, gap);
    std::vector<ChbgItem> items = chbg_items(b);
    int nc = int(T.size()), nr = 0;
    chbg_place(s, items, &nc, &nr);
    while (int(T.size()) < nc) T.push_back(ChbgTrack{});
    for (auto& it : items) {
        it.minC = lc_min_contribution(c, it.b);
        it.maxC = lc_max_contribution(c, it.b);
    }
    float mn = 0, mx = 0;
    for (int pass = 0; pass < 2; ++pass) {
        std::vector<ChbgTrack> TT = T;
        std::vector<ChbgItem> II = items;
        if (pass == 0)
            for (auto& it : II) it.maxC = it.minC;
        chbg_size_columns(c, TT, II, -1, gap, Align::Start);
        float sum = TT.size() > 1 ? gap * float(TT.size() - 1) : 0.0f;
        for (const auto& t : TT) sum += t.base;
        (pass == 0 ? mn : mx) = sum;
    }
    *minW = mn;
    *maxW = std::max(mn, mx);
}

float lc_grid(LayoutCtx& c, Box* b, float cw, float ch) {
    const ComputedStyle& s = *b->st;
    const float colGap = s.colGap.kind == Len::Val ? lc_len(s.colGap, cw) : 0.0f;
    const float rowGap = s.rowGap.kind == Len::Val ? lc_len(s.rowGap, ch) : 0.0f;
    for (Box* k : b->kids)
        if (k->outOfFlow) {
            k->staticParent = b;
            k->staticX = b->contentX();
            k->staticY = b->contentY();
        }
    std::vector<ChbgTrack> T = chbg_columns(s, cw, colGap);
    std::vector<ChbgItem> items = chbg_items(b);
    int nc = int(T.size()), nr = 0;
    chbg_place(s, items, &nc, &nr);
    while (int(T.size()) < nc) {
        ChbgTrack t;
        if (s.gridAutoCols) chbg_decompose(*s.gridAutoCols, cw, &t);
        T.push_back(t);
    }
    if (s.gridCols && s.gridCols->autoRepeat == 2) chbg_collapse_autofit(T, items);
    for (auto& it : items) {
        lc_edges(it.b, cw);
        it.minC = lc_min_contribution(c, it.b);
        it.maxC = lc_max_contribution(c, it.b);
    }
    Align jc = s.justifyContent;
    chbg_size_columns(c, T, items, cw, colGap, jc);
    // collapsed auto-fit tracks also drop their gaps
    std::vector<float> colX(T.size() + 1, 0.0f);
    {
        float x = 0;
        for (size_t i = 0; i < T.size(); ++i) {
            colX[i] = x;
            bool last = true; // no live track after this one → no gutter
            for (size_t j = i + 1; j < T.size() && last; ++j) last = T[j].collapsed;
            x += T[i].base + (T[i].collapsed || last ? 0.0f : colGap);
        }
        colX[T.size()] = x;
    }
    auto areaW = [&](const ChbgItem& it) {
        float w = 0;
        for (int i = it.c0; i < it.c1 && i < int(T.size()); ++i) w += T[size_t(i)].base;
        return w + colGap * float(std::max(0, it.c1 - it.c0 - 1));
    };
    // rows
    std::vector<ChbgTrack> R;
    if (s.gridRows && !s.gridRows->none) {
        for (const auto* v : {&s.gridRows->before, &s.gridRows->after})
            for (const TrackSize& t : *v) {
                ChbgTrack k;
                chbg_decompose(t, ch, &k);
                R.push_back(k);
            }
    }
    while (int(R.size()) < nr) {
        ChbgTrack t;
        if (s.gridAutoRows) chbg_decompose(*s.gridAutoRows, ch, &t);
        R.push_back(t);
    }
    // lay out items at their column width (auto height)
    for (auto& it : items) {
        Box* k = it.b;
        const ComputedStyle& ks = *k->st;
        const float aw = areaW(it);
        Align js = ks.justifySelf;
        if (js == Align::Auto) js = s.justifyItems;
        float w = lc_spec_width(c, k, aw);
        if (w < 0) {
            const bool stretch = (js == Align::Normal || js == Align::Stretch) && !ks.margin[1].isAuto() && !ks.margin[3].isAuto();
            w = stretch ? aw - k->ml - k->mr : lc_shrink_to_fit(c, k, aw - k->ml - k->mr);
        }
        w = std::max(0.0f, lc_clamp_w(c, k, w, aw));
        lc_layout_sized(c, k, w, -1, aw, -1);
    }
    // first-baseline alignment (align-self / align-items: baseline): items starting in the same row share one
    // baseline — each moves down so its first baseline (synthesized from the border-box bottom when it has none)
    // meets the group's lowest, and the row grows to hold the shifted items (CSS Grid §11.5, Box Alignment §9.3;
    // Blink aligns the p08 "90px 1fr 1fr 1fr" cards this way).
    auto alignOf = [&](const Box* k) {
        Align as = k->st->alignSelf;
        if (as == Align::Auto) as = s.alignItems;
        return as == Align::Normal ? Align::Stretch : as;
    };
    auto isBaseItem = [&](const ChbgItem& it) {
        const ComputedStyle& ks = *it.b->st;
        return alignOf(it.b) == Align::Baseline && !ks.margin[0].isAuto() && !ks.margin[2].isAuto() &&
               it.r0 < int(R.size());
    };
    auto itemBase = [](const Box* k) {
        const float fb = lc_first_baseline(k);
        return k->mt + (std::isnan(fb) ? k->h : fb);
    };
    std::vector<float> rowAbove(R.size(), -1.0f);
    for (const auto& it : items)
        if (isBaseItem(it)) rowAbove[size_t(it.r0)] = std::max(rowAbove[size_t(it.r0)], itemBase(it.b));
    auto baseShift = [&](const ChbgItem& it) { return isBaseItem(it) ? rowAbove[size_t(it.r0)] - itemBase(it.b) : 0.0f; };
    // row sizes
    for (auto& r : R) {
        r.base = r.minK == TrackSize::Fixed ? r.minPx : 0.0f;
        if (r.maxK == TrackSize::Fixed) r.base = std::max(r.base, r.maxPx);
    }
    for (const auto& it : items) {
        if (it.r1 - it.r0 != 1 || it.r0 >= int(R.size())) continue;
        ChbgTrack& r = R[size_t(it.r0)];
        if (r.maxK == TrackSize::Fixed && r.minK == TrackSize::Fixed) continue;
        r.base = std::max(r.base, baseShift(it) + it.b->mt + it.b->h + it.b->mb);
    }
    for (const auto& it : items) {
        const int span = it.r1 - it.r0;
        if (span < 2) continue;
        float sum = rowGap * float(span - 1);
        for (int i = it.r0; i < it.r1 && i < int(R.size()); ++i) sum += R[size_t(i)].base;
        const float need = baseShift(it) + it.b->mt + it.b->h + it.b->mb;
        if (need > sum && it.r1 - 1 < int(R.size())) R[size_t(it.r1 - 1)].base += need - sum;
    }
    float rowsTotal = R.size() > 1 ? rowGap * float(R.size() - 1) : 0.0f;
    for (const auto& r : R) rowsTotal += r.base;
    if (ch >= 0 && rowsTotal < ch && (s.alignContent == Align::Normal || s.alignContent == Align::Stretch)) {
        std::vector<int> autos;
        for (size_t i = 0; i < R.size(); ++i)
            if (R[i].maxK == TrackSize::Auto) autos.push_back(int(i));
        if (!autos.empty()) {
            const float add = (ch - rowsTotal) / float(autos.size());
            for (int i : autos) R[size_t(i)].base += add;
            rowsTotal = ch;
        }
    }
    std::vector<float> rowY(R.size() + 1, 0.0f);
    {
        float y = 0;
        for (size_t i = 0; i < R.size(); ++i) {
            rowY[i] = y;
            y += R[i].base + (i + 1 == R.size() ? 0.0f : rowGap);
        }
        rowY[R.size()] = y;
    }
    // place + stretch + align
    for (auto& it : items) {
        Box* k = it.b;
        const ComputedStyle& ks = *k->st;
        const float aw = areaW(it);
        float ah = 0;
        for (int i = it.r0; i < it.r1 && i < int(R.size()); ++i) ah += R[size_t(i)].base;
        ah += rowGap * float(std::max(0, it.r1 - it.r0 - 1));
        const Align as = alignOf(k);
        const bool autoMT = ks.margin[0].isAuto(), autoMB = ks.margin[2].isAuto();
        if (as == Align::Stretch && ks.height.kind == Len::Auto && !autoMT && !autoMB) {
            const float target = std::max(0.0f, lc_clamp_h(k, ah - k->mt - k->mb, ah));
            if (std::fabs(target - k->h) > 0.001f) lc_layout_sized(c, k, k->w, target, aw, ah);
        }
        Align js = ks.justifySelf;
        if (js == Align::Auto) js = s.justifyItems;
        float dx = 0, dy = 0;
        const float freeX = aw - (k->ml + k->w + k->mr), freeY = ah - (k->mt + k->h + k->mb);
        if (ks.margin[3].isAuto() && ks.margin[1].isAuto()) dx = freeX / 2;
        else if (ks.margin[3].isAuto()) dx = freeX;
        else if (js == Align::Center) dx = freeX / 2;
        else if (js == Align::End || js == Align::FlexEnd || js == Align::Right) dx = freeX;
        if (autoMT && autoMB) dy = freeY / 2;
        else if (autoMT) dy = freeY;
        else if (as == Align::Center) dy = freeY / 2;
        else if (as == Align::End || as == Align::FlexEnd) dy = freeY;
        else if (as == Align::Baseline) dy = baseShift(it);
        k->ref = b;
        k->x = b->contentX() + colX[size_t(std::min(it.c0, int(T.size())))] + k->ml + dx;
        k->y = b->contentY() + rowY[size_t(std::min(it.r0, int(R.size())))] + k->mt + dy;
    }
    // baseline: the first row's baseline-aligned group if any, else its first item
    const ChbgItem* pick = nullptr;
    for (const auto& it : items)
        if (it.r0 == 0 && (!pick || (isBaseItem(it) && !isBaseItem(*pick)))) pick = &it;
    if (pick) {
        const float fb = lc_first_baseline(pick->b);
        b->firstBaseline = pick->b->y + (std::isnan(fb) ? pick->b->h : fb);
    }
    return ch >= 0 ? ch : rowsTotal;
}

} // namespace fincept::screens::chb
