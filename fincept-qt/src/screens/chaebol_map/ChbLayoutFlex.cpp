// ChbLayoutFlex.cpp — flexbox (CSS Flexbox 1): base sizes, automatic minimum, lines, flexible lengths (§9.7),
// cross sizes with stretch/baseline, justify-content, align-content, auto margins, reverse directions.
#include "screens/chaebol_map/ChbLayout_p.h"

#include <cmath>

namespace fincept::screens::chb {

namespace {

struct ChbfxItem {
    Box* b = nullptr;
    float mMainS = 0, mMainE = 0, mCrossS = 0, mCrossE = 0;
    bool aMainS = false, aMainE = false, aCrossS = false, aCrossE = false;
    float base = 0, hypo = 0, minMain = 0, maxMain = kInf, target = 0;
    bool frozen = false;
    float cross = 0;      // border-box cross size
    float baseline = 0;   // from the cross-start margin edge (row: top)
    Align align = Align::Stretch;
    float outerMainHypo() const { return hypo + mMainS + mMainE; }
    float outerMainTarget() const { return target + mMainS + mMainE; }
    float outerCross() const { return cross + mCrossS + mCrossE; }
};

struct ChbfxLine {
    std::vector<ChbfxItem*> items;
    float cross = 0;
    float maxBaseline = 0;
    float offset = 0; // cross offset from content start
};

Align chbfx_align_self(const Box* container, const Box* item) {
    Align a = item->st->alignSelf;
    if (a == Align::Auto) a = container->st->alignItems;
    if (a == Align::Normal) a = Align::Stretch;
    if (a == Align::Start || a == Align::SelfStart) a = Align::FlexStart;
    if (a == Align::End || a == Align::SelfEnd) a = Align::FlexEnd;
    return a;
}

float chbfx_gap(const Len& g, float base) {
    if (g.kind != Len::Val) return 0;
    return lc_len(g, base);
}

} // namespace

void lc_flex_intrinsic(LayoutCtx& c, Box* b, float* minW, float* maxW) {
    const ComputedStyle& s = *b->st;
    const bool row = s.flexDir == FlexDir::Row || s.flexDir == FlexDir::RowReverse;
    const float gap = row ? chbfx_gap(s.colGap, -1) : 0.0f;
    float mn = 0, mx = 0;
    int n = 0;
    for (Box* k : b->kids) {
        if (k->outOfFlow || k->kind == BoxKind::Text) continue;
        const float kmn = lc_min_contribution(c, k), kmx = lc_max_contribution(c, k);
        if (row) {
            mx += kmx;
            if (s.flexWrap == FlexWrap::NoWrap) mn += kmn;
            else mn = std::max(mn, kmn);
        } else {
            mx = std::max(mx, kmx);
            mn = std::max(mn, kmn);
        }
        ++n;
    }
    if (row && n > 1) {
        mx += gap * float(n - 1);
        if (s.flexWrap == FlexWrap::NoWrap) mn += gap * float(n - 1);
    }
    *minW = mn;
    *maxW = std::max(mn, mx);
}

float lc_flex(LayoutCtx& c, Box* b, float cw, float ch) {
    const ComputedStyle& s = *b->st;
    const bool row = s.flexDir == FlexDir::Row || s.flexDir == FlexDir::RowReverse;
    const bool reverse = s.flexDir == FlexDir::RowReverse || s.flexDir == FlexDir::ColumnReverse;
    const bool wrap = s.flexWrap != FlexWrap::NoWrap;
    const float mainAvail = row ? cw : ch;
    const float crossAvail = row ? ch : cw;
    const float gapMain = chbfx_gap(row ? s.colGap : s.rowGap, row ? cw : ch);
    const float gapCross = chbfx_gap(row ? s.rowGap : s.colGap, row ? ch : cw);

    std::vector<ChbfxItem> items;
    for (Box* k : b->kids) {
        if (k->outOfFlow) {
            k->staticParent = b;
            k->staticX = b->contentX();
            k->staticY = b->contentY();
            continue;
        }
        if (k->kind == BoxKind::Text) continue;
        ChbfxItem it;
        it.b = k;
        items.push_back(it);
    }
    std::stable_sort(items.begin(), items.end(), [](const ChbfxItem& a, const ChbfxItem& d) { return a.b->st->order < d.b->st->order; });

    // ---- base sizes
    for (ChbfxItem& it : items) {
        Box* k = it.b;
        lc_edges(k, cw);
        const ComputedStyle& ks = *k->st;
        const int ms = row ? 3 : 0, me = row ? 1 : 2, cs = row ? 0 : 3, ce = row ? 2 : 1;
        auto marg = [&](int side) { return side == 0 ? k->mt : side == 1 ? k->mr : side == 2 ? k->mb : k->ml; };
        it.mMainS = marg(ms);
        it.mMainE = marg(me);
        it.mCrossS = marg(cs);
        it.mCrossE = marg(ce);
        it.aMainS = ks.margin[size_t(ms)].isAuto();
        it.aMainE = ks.margin[size_t(me)].isAuto();
        it.aCrossS = ks.margin[size_t(cs)].isAuto();
        it.aCrossE = ks.margin[size_t(ce)].isAuto();
        it.align = chbfx_align_self(b, k);

        // column items: width first (needed for their content height)
        float colW = -1;
        if (!row) {
            colW = lc_spec_width(c, k, cw);
            if (colW < 0) {
                const float avail = cw - it.mCrossS - it.mCrossE;
                if (it.align == Align::Stretch && !it.aCrossS && !it.aCrossE) colW = avail;
                else colW = lc_shrink_to_fit(c, k, avail);
            }
            colW = std::max(0.0f, lc_clamp_w(c, k, colW, cw));
        }
        auto contentMain = [&]() -> float {
            if (row) {
                float mn = 0, mx = 0;
                lc_intrinsic(c, k, &mn, &mx);
                return mx;
            }
            lc_layout_sized(c, k, colW, -1, cw, -1);
            return k->h;
        };
        const Len& basis = ks.flexBasis;
        float base = -1;
        const float hbp = lc_hbp(k), vbp = lc_vbp(k);
        const float bp = row ? hbp : vbp;
        if (basis.kind == Len::Val && !(basis.hasPct() && mainAvail < 0)) {
            const float v = lc_len(basis, mainAvail);
            base = ks.boxSizing == BoxSizing::BorderBox ? std::max(v, bp) : v + bp;
        } else if (basis.kind == Len::Auto) {
            const float spec = row ? lc_spec_width(c, k, cw) : lc_spec_height(k, ch);
            if (spec >= 0) base = spec;
        }
        const bool contentBased = base < 0;
        if (contentBased) base = contentMain();
        it.base = base;
        // min / max main (automatic minimum size for non-scroll containers)
        const Len& minL = row ? ks.minW : ks.minH;
        if (minL.kind == Len::Auto && !k->clips) {
            float autoMin;
            if (row) {
                float mn = 0, mx = 0;
                lc_intrinsic(c, k, &mn, &mx);
                autoMin = mn;
                const float spec = lc_spec_width(c, k, cw);
                if (spec >= 0) autoMin = std::min(autoMin, spec);
                autoMin = std::min(autoMin, lc_max_width(c, k, cw));
            } else {
                autoMin = contentBased ? base : (lc_layout_sized(c, k, colW, -1, cw, -1), k->h);
                const float spec = lc_spec_height(k, ch);
                if (spec >= 0) autoMin = std::min(autoMin, spec);
            }
            it.minMain = autoMin;
        } else {
            it.minMain = row ? lc_min_width(c, k, cw) : lc_min_height(k, ch);
        }
        it.maxMain = row ? lc_max_width(c, k, cw) : lc_max_height(k, ch);
        it.hypo = std::max(it.minMain, std::min(it.base, it.maxMain));
        if (!row) it.cross = colW;
    }

    // ---- lines
    std::vector<ChbfxLine> lines;
    {
        ChbfxLine cur;
        float used = 0;
        for (ChbfxItem& it : items) {
            const float add = it.outerMainHypo() + (cur.items.empty() ? 0.0f : gapMain);
            if (wrap && mainAvail >= 0 && !cur.items.empty() && used + add > mainAvail + 0.01f) {
                lines.push_back(cur);
                cur = ChbfxLine();
                used = 0;
            }
            used += cur.items.empty() ? it.outerMainHypo() : it.outerMainHypo() + gapMain;
            cur.items.push_back(&it);
        }
        if (!cur.items.empty() || lines.empty()) lines.push_back(cur);
    }

    // ---- flexible lengths
    float containerMain = mainAvail;
    if (containerMain < 0) {
        float mx = 0;
        for (const ChbfxLine& l : lines) {
            float u = 0;
            for (size_t i = 0; i < l.items.size(); ++i) u += l.items[i]->outerMainHypo() + (i ? gapMain : 0.0f);
            mx = std::max(mx, u);
        }
        containerMain = mx;
    }
    for (ChbfxLine& l : lines) {
        const float gaps = l.items.size() > 1 ? gapMain * float(l.items.size() - 1) : 0.0f;
        float sumHypo = 0;
        for (ChbfxItem* it : l.items) sumHypo += it->outerMainHypo();
        const float initialFree = containerMain - sumHypo - gaps;
        const bool grow = initialFree > 0;
        for (ChbfxItem* it : l.items) {
            const ComputedStyle& ks = *it->b->st;
            it->frozen = false;
            it->target = it->hypo;
            if ((grow ? ks.flexGrow : ks.flexShrink) == 0 || (grow && it->base > it->hypo) || (!grow && it->base < it->hypo))
                it->frozen = true;
        }
        for (int iter = 0; iter < 64; ++iter) {
            bool any = false;
            for (ChbfxItem* it : l.items) any = any || !it->frozen;
            if (!any) break;
            float used = gaps, sumGrow = 0, sumScaled = 0;
            for (ChbfxItem* it : l.items) {
                used += it->frozen ? it->outerMainTarget() : it->base + it->mMainS + it->mMainE;
                if (!it->frozen) {
                    sumGrow += it->b->st->flexGrow;
                    sumScaled += it->b->st->flexShrink * it->base;
                }
            }
            float remaining = containerMain - used;
            if (grow && sumGrow < 1) remaining = std::min(remaining, initialFree * sumGrow);
            if (!grow && sumGrow < 1) {
                float sumShrink = 0;
                for (ChbfxItem* it : l.items)
                    if (!it->frozen) sumShrink += it->b->st->flexShrink;
                if (sumShrink < 1) remaining = std::max(remaining, initialFree * sumShrink);
            }
            float violation = 0;
            for (ChbfxItem* it : l.items) {
                if (it->frozen) continue;
                float t = it->base;
                if (grow && sumGrow > 0) t = it->base + remaining * it->b->st->flexGrow / sumGrow;
                else if (!grow && sumScaled > 0) t = it->base + remaining * (it->b->st->flexShrink * it->base) / sumScaled;
                const float cl = std::max(it->minMain, std::min(t, it->maxMain));
                violation += cl - t;
                it->target = std::max(0.0f, cl);
            }
            for (ChbfxItem* it : l.items) {
                if (it->frozen) continue;
                if (violation == 0) it->frozen = true;
                else if (violation > 0 && it->target <= it->minMain + 1e-4f) it->frozen = true;
                else if (violation < 0 && it->target >= it->maxMain - 1e-4f) it->frozen = true;
            }
            if (std::fabs(violation) < 1e-4f)
                for (ChbfxItem* it : l.items) it->frozen = true;
        }
    }

    // ---- item layout at the main size → hypothetical cross sizes
    for (ChbfxLine& l : lines) {
        for (ChbfxItem* it : l.items) {
            Box* k = it->b;
            if (row) {
                lc_layout_sized(c, k, it->target, -1, cw, ch);
                it->cross = k->h;
                const float fb = lc_first_baseline(k);
                it->baseline = it->mCrossS + (std::isnan(fb) ? k->h : fb);
            } else {
                lc_layout_sized(c, k, it->cross, it->target, cw, ch);
                it->baseline = it->mCrossS + it->cross;
            }
        }
    }

    // ---- line cross sizes
    const bool singleLine = !wrap;
    for (ChbfxLine& l : lines) {
        float mx = 0, maxBase = 0, maxBelow = 0;
        bool anyBase = false;
        for (ChbfxItem* it : l.items) {
            if (row && it->align == Align::Baseline && !it->aCrossS && !it->aCrossE) {
                anyBase = true;
                maxBase = std::max(maxBase, it->baseline);
                maxBelow = std::max(maxBelow, it->outerCross() - it->baseline);
            } else {
                mx = std::max(mx, it->outerCross());
            }
        }
        l.maxBaseline = maxBase;
        l.cross = anyBase ? std::max(mx, maxBase + maxBelow) : mx;
        if (singleLine && crossAvail >= 0) l.cross = crossAvail;
    }
    float linesTotal = 0;
    for (size_t i = 0; i < lines.size(); ++i) linesTotal += lines[i].cross + (i ? gapCross : 0.0f);
    const float containerCross = crossAvail >= 0 ? crossAvail : linesTotal;

    // ---- align-content
    {
        float free = containerCross - linesTotal;
        float start = 0, between = gapCross;
        Align ac = s.alignContent;
        if (!singleLine && lines.size() > 0) {
            if ((ac == Align::Normal || ac == Align::Stretch) && free > 0) {
                const float add = free / float(lines.size());
                for (auto& l : lines) l.cross += add;
                free = 0;
            } else if (ac == Align::FlexEnd || ac == Align::End) start = free;
            else if (ac == Align::Center) start = free / 2;
            else if (ac == Align::SpaceBetween && lines.size() > 1 && free > 0) between += free / float(lines.size() - 1);
            else if (ac == Align::SpaceAround && free > 0) { start = free / float(lines.size()) / 2; between += free / float(lines.size()); }
            else if (ac == Align::SpaceEvenly && free > 0) { start = free / float(lines.size() + 1); between += start; }
        }
        float off = start;
        for (auto& l : lines) {
            l.offset = off;
            off += l.cross + between;
        }
    }

    // ---- stretch
    for (ChbfxLine& l : lines) {
        for (ChbfxItem* it : l.items) {
            Box* k = it->b;
            const bool autoCross = row ? k->st->height.kind == Len::Auto : k->st->width.kind == Len::Auto;
            if (it->align != Align::Stretch || !autoCross || it->aCrossS || it->aCrossE) continue;
            float target = l.cross - it->mCrossS - it->mCrossE;
            if (row) {
                target = std::max(0.0f, lc_clamp_h(k, target, ch));
                if (std::fabs(target - k->h) > 0.001f) lc_layout_sized(c, k, it->target, target, cw, ch);
                it->cross = k->h;
            } else {
                target = std::max(0.0f, lc_clamp_w(c, k, target, cw));
                if (std::fabs(target - k->w) > 0.001f) lc_layout_sized(c, k, target, it->target, cw, ch);
                it->cross = k->w;
            }
        }
    }

    // ---- main axis placement
    const float mainContent = mainAvail >= 0 ? mainAvail : containerMain;
    for (ChbfxLine& l : lines) {
        const size_t n = l.items.size();
        float used = n > 1 ? gapMain * float(n - 1) : 0.0f;
        int autos = 0;
        for (ChbfxItem* it : l.items) {
            used += it->outerMainTarget();
            autos += int(it->aMainS) + int(it->aMainE);
        }
        float free = mainContent - used;
        float autoEach = 0;
        if (autos > 0 && free > 0) {
            autoEach = free / float(autos);
            free = 0;
        }
        float start = 0, between = gapMain;
        Align jc = s.justifyContent;
        switch (jc) {
        case Align::FlexEnd: case Align::End: case Align::Right: start = free; break;
        case Align::Center: start = free / 2; break;
        case Align::SpaceBetween: if (n > 1 && free > 0) between += free / float(n - 1); break;
        case Align::SpaceAround:
            if (free > 0) { start = free / float(n) / 2; between += free / float(n); }
            else start = free / 2;
            break;
        case Align::SpaceEvenly:
            if (free > 0) { start = free / float(n + 1); between += start; }
            else start = free / 2;
            break;
        default: break;
        }
        float pos = start;
        for (size_t i = 0; i < n; ++i) {
            ChbfxItem* it = l.items[i];
            Box* k = it->b;
            pos += it->mMainS + (it->aMainS ? autoEach : 0.0f);
            const float mainSize = row ? k->w : k->h;
            float mainPos = pos;
            if (reverse) mainPos = mainContent - pos - mainSize;
            pos += mainSize + it->mMainE + (it->aMainE ? autoEach : 0.0f) + between;
            // cross placement
            float co = 0;
            const float outer = it->outerCross();
            const float freeC = l.cross - outer;
            if (it->aCrossS || it->aCrossE) {
                if (it->aCrossS && it->aCrossE) co = std::max(0.0f, freeC) / 2;
                else if (it->aCrossS) co = std::max(0.0f, freeC);
            } else {
                switch (it->align) {
                case Align::FlexEnd: co = freeC; break;
                case Align::Center: co = freeC / 2; break;
                case Align::Baseline: co = row ? l.maxBaseline - it->baseline : 0.0f; break;
                default: co = 0; break;
                }
            }
            const float crossPos = l.offset + co + it->mCrossS;
            k->ref = b;
            if (row) {
                k->x = b->contentX() + mainPos;
                k->y = b->contentY() + crossPos;
            } else {
                k->x = b->contentX() + crossPos;
                k->y = b->contentY() + mainPos;
            }
        }
    }

    // ---- baselines (first line: first baseline-aligned item, else the first item)
    if (!lines.empty() && !lines.front().items.empty()) {
        const ChbfxLine& l = lines.front();
        const ChbfxItem* pick = nullptr;
        if (row)
            for (const ChbfxItem* it : l.items)
                if (it->align == Align::Baseline) { pick = it; break; }
        if (!pick) pick = l.items.front();
        const float fb = lc_first_baseline(pick->b);
        b->firstBaseline = pick->b->y + (std::isnan(fb) ? pick->b->h : fb);
        const ChbfxLine& ll = lines.back();
        const ChbfxItem* lp = ll.items.empty() ? pick : ll.items.front();
        const float lb = !std::isnan(lp->b->lastBaseline) ? lp->b->lastBaseline : lc_first_baseline(lp->b);
        b->lastBaseline = lp->b->y + (std::isnan(lb) ? lp->b->h : lb);
    }
    if (row) return containerCross;
    return mainAvail >= 0 ? mainAvail : containerMain;
}

} // namespace fincept::screens::chb
