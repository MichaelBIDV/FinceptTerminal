// src/screens/hdcv_launchpad/HlpDomLayout.cpp
// Launchpad CSS engine — box layout: block flow with margin collapsing, flex row (§9.7 resolution,
// align-items/align-self), grid (fixed/fr/auto-fit tracks), intrinsic min/max-content sizes and the
// final absolute positions (incl. inline-box line rects).
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

void Layout::run(float width) {
    Box* r = d_.root;
    if (!r)
        return;
    layoutBox(r, width, NAN);
    // the view is a BFC: margins of the root stay inside
    r->x = r->st ? r->st->ml : 0;
    r->y = r->mTop.value();
    contentHeight = r->y + r->h + r->mBot.value();
    overflowRight = 0;
    finalize(r, 0, 0);
}

// ---- intrinsic sizes ----
void Layout::intrinsic(Box* b) {
    if (b->intrinsicDone)
        return;
    b->intrinsicDone = true;
    float mn = 0, mx = 0;
    const Style* st = b->st;
    const float hp = st ? st->pl + st->pr + st->bw[1] + st->bw[3] : 0;
    if (b->widget) {
        const float w = st && !std::isnan(st->width) ? st->width
                                                     : float(b->node->widget->sizeHint().width());
        mn = mx = w;
    } else if (b->custom) {
        mn = mx = (st && !std::isnan(st->width)) ? st->width : 0.0f;
    } else if (b->ifc) {
        ifcIntrinsic(b, mn, mx);
        mn += hp;
        mx += hp;
    } else if (b->kind == BK::Table) {
        TableModel tm;
        buildTable(b, tm);
        for (int c = 0; c < tm.nCols; ++c) {
            mn += tm.colMin[c];
            mx += tm.colMax[c];
        }
        mn += hp;
        mx += hp;
    } else if (b->kind == BK::Flex) {
        float sMin = 0, sMax = 0, bMin = 0;
        const float gap = st ? st->gap : 0;
        int n = 0;
        for (Box* k : b->kids) {
            intrinsic(k);
            const float m = k->st ? k->st->ml + k->st->mr : 0;
            const float kmin = (k->st && k->st->flexShrink == 0.0f) ? k->maxC : k->minC;
            sMin += kmin + m;
            sMax += k->maxC + m;
            bMin = std::max(bMin, k->minC + m);
            ++n;
        }
        if (n > 1) {
            sMax += gap * float(n - 1);
            sMin += gap * float(n - 1);
        }
        mn = (st && st->flexWrap) ? bMin : sMin;
        mx = sMax;
        mn += hp;
        mx += hp;
    } else if (b->kind == BK::Grid) {
        const GridSpec& g = st->grid;
        float itMin = 0, itMax = 0;
        int n = 0;
        for (Box* k : b->kids) {
            intrinsic(k);
            itMin = std::max(itMin, k->minC);
            itMax = std::max(itMax, k->maxC);
            ++n;
        }
        if (g.autoFitMin > 0) {
            mn = std::max(g.autoFitMin, itMin);
            mx = n ? std::max(g.autoFitMin, itMax) * float(n) + g.colGap * float(n - 1) : 0;
        } else {
            const int nc = std::max<int>(1, int(g.cols.size()));
            for (int c = 0; c < nc; ++c) {
                const Track t = c < g.cols.size() ? g.cols[c] : Track{};
                float cMin = 0, cMax = 0;
                for (int i = c; i < b->kids.size(); i += nc) {
                    cMin = std::max(cMin, b->kids[i]->minC);
                    cMax = std::max(cMax, b->kids[i]->maxC);
                }
                if (t.px >= 0) {
                    cMin = cMax = t.px;
                }
                mn += cMin;
                mx += cMax;
            }
            mn += g.colGap * float(nc - 1);
            mx += g.colGap * float(nc - 1);
        }
        mn += hp;
        mx += hp;
    } else {
        for (Box* k : b->kids) {
            intrinsic(k);
            const float m = k->st ? k->st->ml + k->st->mr : 0;
            mn = std::max(mn, k->minC + m);
            mx = std::max(mx, k->maxC + m);
        }
        mn += hp;
        mx += hp;
    }
    if (st) {
        if (!std::isnan(st->width)) {
            mn = mx = st->width;
        }
        if (!std::isnan(st->maxWidth)) {
            mn = std::min(mn, st->maxWidth);
            mx = std::min(mx, st->maxWidth);
        }
        if (!std::isnan(st->minWidth)) {
            mn = std::max(mn, st->minWidth);
            mx = std::max(mx, st->minWidth);
        }
    }
    b->minC = luCeil(mn);
    b->maxC = luCeil(std::max(mn, mx));
}

// ---------------------------------------------------------------------------------------
// Box layout
// ---------------------------------------------------------------------------------------
float Layout::usedWidth(Box* b, float cbW) {
    const Style* st = b->st;
    if (!st)
        return cbW;
    float w;
    if (!std::isnan(st->width))
        w = st->width;
    else if (!std::isnan(st->widthPct))
        w = luFloor(cbW * st->widthPct / 100.0f);
    else
        w = cbW - st->ml - st->mr;
    if (!std::isnan(st->maxWidth))
        w = std::min(w, st->maxWidth);
    if (!std::isnan(st->minWidth))
        w = std::max(w, st->minWidth);
    return std::max(0.0f, w);
}

/// Lay out `b` in a containing block of width cbW (forcedW = border-box width decided by the parent).
void Layout::layoutBox(Box* b, float cbW, float forcedW) {
    const Style* st = b->st;
    b->mTop = {};
    b->mBot = {};
    if (st) {
        b->mTop.add(st->mt);
        b->mBot.add(st->mb);
    }
    b->w = std::isnan(forcedW) ? usedWidth(b, cbW) : forcedW;
    const float pl = st ? st->pl + st->bw[3] : 0, pr = st ? st->pr + st->bw[1] : 0;
    const float pt = st ? st->pt + st->bw[0] : 0, pb = st ? st->pb + st->bw[2] : 0;
    const float cw = std::max(0.0f, b->w - pl - pr);
    float ch = 0;
    b->selfCollapsing = false;
    if (b->widget) {
        ch = st && !std::isnan(st->height) ? st->height - pt - pb
                                           : float(b->node->widget->sizeHint().height()) - pt - pb;
    } else if (b->custom) {
        ch = b->node->customHeight ? b->node->customHeight(cw) : 0.0f;
    } else if (b->ifc) {
        ch = layoutLines(b, cw, pl, pt);
    } else if (b->kind == BK::Flex) {
        ch = layoutFlex(b, cw, pl, pt);
    } else if (b->kind == BK::Grid) {
        ch = layoutGrid(b, cw, pl, pt);
    } else if (b->kind == BK::Table) {
        ch = layoutTable(b, cw, pl, pt);
    } else {
        ch = layoutFlow(b, cw, pl, pt, pb);
    }
    float h = ch + pt + pb;
    if (st && !std::isnan(st->height))
        h = st->height;
    if (st && !std::isnan(st->maxHeight))
        h = std::min(h, st->maxHeight);
    b->h = std::max(0.0f, h);
    b->baseline = -1;
}

float Layout::layoutFlow(Box* b, float cw, float pl, float pt, float pb) {
    const Style* st = b->st;
    const bool collapseTop = !b->bfcRoot && pt == 0.0f;
    const bool collapseBot = !b->bfcRoot && pb == 0.0f && (!st || std::isnan(st->height));
    Box::MSet pending;
    float cursor = 0;
    bool first = true;
    bool anyInFlow = false;
    for (Box* k : b->kids) {
        layoutBox(k, cw, NAN);
        const Style* ks = k->st;
        float xoff = ks ? ks->ml : 0;
        if (ks && ks->mlAuto)
            xoff = cw - k->w - ks->mr;
        k->x = pl + xoff;
        // self-collapsing (empty) block: its margins collapse through
        const bool empty = k->h == 0.0f && !k->ifc && k->kids.isEmpty() && !k->custom && !k->widget &&
                           k->kind == BK::Block;
        if (empty) {
            pending.add(k->mTop);
            pending.add(k->mBot);
            k->y = pt + cursor;
            continue;
        }
        Box::MSet top = pending;
        top.add(k->mTop);
        if (first && collapseTop) {
            b->mTop.add(top);
            k->y = pt;
            cursor = k->h;
        } else {
            k->y = pt + cursor + top.value();
            cursor = k->y - pt + k->h;
        }
        pending = k->mBot;
        first = false;
        anyInFlow = true;
    }
    if (!anyInFlow) {
        if (collapseTop && collapseBot) {
            b->mTop.add(pending);
            b->selfCollapsing = true;
        }
        return 0;
    }
    if (collapseBot) {
        b->mBot.add(pending);
        return cursor;
    }
    return cursor + pending.value();
}

// ---- flex (row) ----
float Layout::layoutFlex(Box* b, float cw, float pl, float pt) {
    const Style* st = b->st;
    const float gap = st->gap;
    struct It {
        Box* b;
        float base, hyp, mn, mx, target, ml, mr, mt, mb, grow, shrink;
        bool frozen;
    };
    QVector<It> items;
    for (Box* k : b->kids) {
        intrinsic(k);
        const Style* ks = k->st;
        It it{};
        it.b = k;
        it.ml = ks ? ks->ml : 0;
        it.mr = ks ? ks->mr : 0;
        it.mt = ks ? ks->mt : 0;
        it.mb = ks ? ks->mb : 0;
        it.grow = ks ? ks->flexGrow : 0;
        it.shrink = ks ? ks->flexShrink : 1;
        if (ks && !std::isnan(ks->width))
            it.base = ks->width;
        else if (ks && !std::isnan(ks->widthPct))
            it.base = luFloor(cw * ks->widthPct / 100.0f);
        else
            it.base = k->maxC;
        it.mn = (ks && !std::isnan(ks->minWidth)) ? ks->minWidth : std::min(k->minC, it.base);
        if (ks && !std::isnan(ks->width))
            it.mn = std::min(it.mn, ks->width);
        it.mx = (ks && !std::isnan(ks->maxWidth)) ? ks->maxWidth : kInf;
        it.hyp = std::clamp(it.base, it.mn, std::max(it.mn, it.mx));
        items.push_back(it);
    }
    // lines
    QVector<QPair<int, int>> lines;
    {
        int s = 0;
        float used = 0;
        for (int i = 0; i < items.size(); ++i) {
            const float o = items[i].hyp + items[i].ml + items[i].mr;
            if (st->flexWrap && i > s && used + gap + o > cw + kEps) {
                lines.push_back({s, i});
                s = i;
                used = o;
            } else {
                used += (i > s ? gap : 0) + o;
            }
        }
        if (s < items.size())
            lines.push_back({s, int(items.size())});
    }
    float y = 0;
    for (int li = 0; li < lines.size(); ++li) {
        const int s = lines[li].first, e = lines[li].second;
        const int n = e - s;
        const float gaps = gap * float(std::max(0, n - 1));
        float sumHyp = gaps;
        for (int i = s; i < e; ++i)
            sumHyp += items[i].hyp + items[i].ml + items[i].mr;
        const bool growing = sumHyp < cw;
        // resolve flexible lengths (CSS Flexbox §9.7)
        for (int i = s; i < e; ++i) {
            It& it = items[i];
            const float f = growing ? it.grow : it.shrink;
            it.frozen = f == 0.0f || (growing && it.base > it.hyp) || (!growing && it.base < it.hyp);
            it.target = it.hyp;
        }
        float initialFree = cw - gaps;
        for (int i = s; i < e; ++i) {
            const It& it = items[i];
            initialFree -= (it.frozen ? it.target : it.base) + it.ml + it.mr;
        }
        for (int iter = 0; iter < 32; ++iter) {
            bool anyUnfrozen = false;
            float free = cw - gaps, sumF = 0, sumScaled = 0;
            for (int i = s; i < e; ++i) {
                const It& it = items[i];
                free -= (it.frozen ? it.target : it.base) + it.ml + it.mr;
                if (!it.frozen) {
                    anyUnfrozen = true;
                    sumF += growing ? it.grow : it.shrink;
                    sumScaled += it.shrink * it.base;
                }
            }
            if (!anyUnfrozen)
                break;
            if (sumF < 1.0f) {
                const float f2 = initialFree * sumF;
                if (std::abs(f2) < std::abs(free))
                    free = f2;
            }
            float totalViolation = 0;
            for (int i = s; i < e; ++i) {
                It& it = items[i];
                if (it.frozen)
                    continue;
                float t = it.base;
                if (free != 0.0f) {
                    if (growing && sumF > 0)
                        t = it.base + free * it.grow / sumF;
                    else if (!growing && sumScaled > 0)
                        t = it.base + free * (it.shrink * it.base) / sumScaled;
                }
                const float cl = std::clamp(t, it.mn, std::max(it.mn, it.mx));
                totalViolation += cl - t;
                it.target = cl;
            }
            for (int i = s; i < e; ++i) {
                It& it = items[i];
                if (it.frozen)
                    continue;
                if (totalViolation == 0.0f)
                    it.frozen = true;
                else if (totalViolation > 0 && it.target == it.mn && it.mn > 0)
                    it.frozen = true;
                else if (totalViolation < 0 && it.target == it.mx)
                    it.frozen = true;
                else if (totalViolation > 0) {
                    // min violation of an item whose min is 0? keep iterating others
                    const float t0 = it.target;
                    if (t0 <= it.mn + 1e-4f)
                        it.frozen = true;
                }
            }
            if (totalViolation == 0.0f)
                break;
        }
        // lay out items at their main sizes
        float used = gaps;
        int autos = 0;
        for (int i = s; i < e; ++i) {
            It& it = items[i];
            it.target = luFloor(it.target + 1e-4f);
            layoutBox(it.b, cw, it.target);
            used += it.target + it.ml + it.mr;
            if (it.b->st && it.b->st->mlAuto)
                ++autos;
        }
        float free = cw - used;
        float x = 0, between = 0;
        if (autos > 0 && free > 0) {
            // auto margins absorb free space
        } else {
            switch (st->justify) {
            case Justify::End: x = free; break;
            case Justify::Center: x = free / 2.0f; break;
            case Justify::SpaceBetween:
                if (n > 1 && free > 0)
                    between = free / float(n - 1);
                break;
            default: break;
            }
        }
        // cross size
        auto alignOf = [&](const It& it) {
            return (it.b->st && it.b->st->alignSelf) ? *it.b->st->alignSelf : st->alignItems;
        };
        float lineCross = 0, maxA = 0, maxD = 0;
        bool anyBaseline = false;
        for (int i = s; i < e; ++i) {
            It& it = items[i];
            const float outer = it.b->h + it.mt + it.mb;
            if (alignOf(it) == AlignItems::Baseline) {
                anyBaseline = true;
                float bl = firstOrLastBaseline(it.b, false);
                if (bl < 0)
                    bl = it.b->h;
                maxA = std::max(maxA, it.mt + bl);
                maxD = std::max(maxD, outer - it.mt - bl);
            }
            lineCross = std::max(lineCross, outer);
        }
        if (anyBaseline)
            lineCross = std::max(lineCross, maxA + maxD);
        // single-line container with a definite height: the line's cross size is the container's
        // inner height (CSS Flexbox §9.4 step 15) — #bar {height:34px;align-items:center}
        if (!st->flexWrap && !std::isnan(st->height))
            lineCross = std::max(0.0f, st->height - pt - st->pb - st->bw[2]);
        for (int i = s; i < e; ++i) {
            It& it = items[i];
            if (it.b->st && it.b->st->mlAuto && free > 0)
                x += free / float(autos);
            it.b->x = pl + x + it.ml;
            float yy = 0;
            const float outer = it.b->h + it.mt + it.mb;
            switch (alignOf(it)) {
            case AlignItems::Stretch:
                if (!it.b->st || std::isnan(it.b->st->height))
                    it.b->h = std::max(it.b->h, lineCross - it.mt - it.mb);
                break;
            case AlignItems::Center: yy = (lineCross - outer) / 2.0f; break;
            case AlignItems::End: yy = lineCross - outer; break;
            case AlignItems::Baseline: {
                float bl = firstOrLastBaseline(it.b, false);
                if (bl < 0)
                    bl = it.b->h;
                yy = maxA - (it.mt + bl);
                break;
            }
            default: break;
            }
            it.b->y = pt + y + yy + it.mt;
            x += it.target + it.ml + it.mr + gap + between;
        }
        y += lineCross + (li + 1 < lines.size() ? gap : 0);
    }
    return y;
}

// ---- grid ----
float Layout::layoutGrid(Box* b, float cw, float pl, float pt) {
    const GridSpec& g = b->st->grid;
    QVector<float> cols;
    const int nItems = int(b->kids.size());
    if (g.minWidthForCols > 0 && cw < g.minWidthForCols) {
        cols = {cw};
    } else if (g.autoFitMin > 0) {
        const int n = std::max(1, int(std::floor((cw + g.colGap) / (g.autoFitMin + g.colGap) + 1e-6f)));
        const int used = std::max(1, std::min(n, nItems));
        // minmax(min, 1fr) tracks: edges at floor(k × fr) in LayoutUnits, like the fr branch below
        const double fr = double(cw - g.colGap * float(used - 1)) / double(used);
        float edgePrev = 0.0f;
        for (int c = 1; c <= used; ++c) {
            const float edge = luFloor(float(fr * double(c)));
            cols.push_back(std::max(g.autoFitMin, edge - edgePrev));
            edgePrev = edge;
        }
    } else {
        const int nc = std::max<int>(1, int(g.cols.size()));
        float fixed = g.colGap * float(nc - 1), sumFr = 0;
        for (int c = 0; c < nc; ++c) {
            const Track t = c < g.cols.size() ? g.cols[c] : Track{-1, 1, 0};
            if (t.px >= 0)
                fixed += t.px;
            else
                sumFr += t.fr;
        }
        const float leftover = std::max(0.0f, cw - fixed);
        // fr tracks in LayoutUnits with the fraction carried along: the edge after k flex units sits at
        // floor(k × fr) (measured: .wd-split 1.05fr/1fr of 1951 → 999.2890625 + 951.7109375)
        double frAcc = 0.0;
        float edgePrev = 0.0f;
        for (int c = 0; c < nc; ++c) {
            const Track t = c < g.cols.size() ? g.cols[c] : Track{-1, 1, 0};
            if (t.px >= 0) {
                cols.push_back(t.px);
                continue;
            }
            frAcc += double(t.fr);
            const float edge = sumFr > 0 ? luFloor(float(double(leftover) * frAcc / double(sumFr))) : 0.0f;
            cols.push_back(std::max(t.minPx, edge - edgePrev));
            edgePrev = edge;
        }
    }
    const int nc = int(cols.size());
    QVector<float> colX(nc, 0.0f);
    for (int c = 1; c < nc; ++c)
        colX[c] = colX[c - 1] + cols[c - 1] + g.colGap;
    float y = 0;
    for (int r0 = 0; r0 < nItems; r0 += nc) {
        float rowH = 0;
        for (int i = r0; i < std::min(nItems, r0 + nc); ++i) {
            Box* k = b->kids[i];
            const Style* ks = k->st;
            const float m = ks ? ks->ml + ks->mr : 0;
            float w = cols[i - r0] - m;
            if (ks && !std::isnan(ks->width))
                w = ks->width;
            layoutBox(k, cols[i - r0], w);
            rowH = std::max(rowH, k->h + (ks ? ks->mt + ks->mb : 0));
        }
        for (int i = r0; i < std::min(nItems, r0 + nc); ++i) {
            Box* k = b->kids[i];
            const Style* ks = k->st;
            const float mv = ks ? ks->mt + ks->mb : 0;
            // align-self (auto → the grid's align-items, default stretch). Legacy: a sticky item
            // without align-self is start (.wd-chartcol{position:sticky;align-self:start}).
            AlignItems al = (ks && ks->alignSelf) ? *ks->alignSelf : b->st->alignItems;
            if (ks && ks->sticky && !ks->alignSelf && al == AlignItems::Stretch)
                al = AlignItems::Start;
            float dy = 0;
            if (al == AlignItems::Stretch) {
                if (!ks || std::isnan(ks->height)) {
                    const float grown = rowH - mv - k->h;
                    if (grown > 0.0f) {
                        k->h += grown;
                        // the stretched size is definite: a single-line flex item re-aligns its children
                        // in it (the sheet's <button class="card">: content centred in the taller row)
                        if (ks && ks->display == Display::Flex && !ks->flexWrap)
                            for (Box* c : k->kids) {
                                const AlignItems ca = (c->st && c->st->alignSelf) ? *c->st->alignSelf : ks->alignItems;
                                if (ca == AlignItems::Center)
                                    c->y += luFloor(grown / 2.0f);
                                else if (ca == AlignItems::End)
                                    c->y += grown;
                            }
                    }
                }
            } else if (al == AlignItems::Center) {
                dy = (rowH - k->h - mv) / 2.0f;
            } else if (al == AlignItems::End) {
                dy = rowH - k->h - mv;
            }
            k->x = pl + colX[i - r0] + (ks ? ks->ml : 0);
            k->y = pt + y + dy + (ks ? ks->mt : 0);
        }
        y += rowH + (r0 + nc < nItems ? g.rowGap : 0);
    }
    return y;
}

// ---------------------------------------------------------------------------------------
// absolute positions
// ---------------------------------------------------------------------------------------
void Layout::finalize(Box* b, float ox, float oy) {
    b->ax = ox + b->x;
    b->ay = oy + b->y;
    if (b != d_.root)
        overflowRight = std::max(overflowRight, b->ax + b->w + (b->st ? std::max(0.0f, b->st->mr) : 0.0f));
    if (b->ifc) {
        // atomics are positioned relative to the IFC container; inline boxes get line rects
        for (const IItem& it : b->ifc->items)
            if (it.box && (it.box->kind == BK::Inline || it.box->kind == BK::Text))
                it.box->inlineRects.clear();
        for (const Line& L : b->ifc->lines) {
            QHash<Box*, QRectF> rects;
            for (const Frag& fr : L.frags) {
                if (fr.box->kind == BK::Atomic) {
                    finalize(fr.box, b->ax, b->ay);
                    const QRectF ar(fr.box->ax, fr.box->ay, fr.box->w, fr.box->h);
                    for (Box* p = fr.box->parent; p && p != b; p = p->parent)
                        rects[p] = rects.value(p).united(ar);
                    continue;
                }
                const CS& cs = *fr.box->cs;
                const QRectF r(b->ax + fr.x, b->ay + L.baseline - cs.vm.ascent, fr.w,
                               cs.vm.ascent + cs.vm.descent);
                overflowRight = std::max(overflowRight, float(r.right()));
                for (Box* p = fr.box; p && p != b; p = p->parent) {
                    const CS& pc = *p->cs;
                    const QRectF pr(r.left(), b->ay + L.baseline - pc.vm.ascent, r.width(),
                                    pc.vm.ascent + pc.vm.descent);
                    rects[p] = rects.contains(p) ? rects[p].united(pr) : pr;
                }
            }
            for (auto it = rects.begin(); it != rects.end(); ++it)
                it.key()->inlineRects.push_back(it.value());
        }
        return;
    }
    for (Box* k : b->kids)
        finalize(k, b->ax, b->ay);
}

} // namespace fincept::screens::hlp::hlpdom
