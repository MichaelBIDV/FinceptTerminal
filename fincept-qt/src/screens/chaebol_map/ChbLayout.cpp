// ChbLayout.cpp — sizing helpers, intrinsic dispatch, block-level layout + margin collapsing, block flow,
// absolute positioning, replaced elements, position finalization.
#include "screens/chaebol_map/ChbLayout_p.h"

#include <QStringList>

#include <cmath>

namespace fincept::screens::chb {

namespace {

float chbl_edge_px(const Len& l, float cbW) { return l.kind == Len::Val ? l.px + (cbW >= 0 ? l.pct * cbW / 100.0f : 0.0f) : 0.0f; }

/// Horizontal border+padding of `b` computed without touching its fields (for intrinsic sizing).
float chbl_hbp_pure(const Box* b, float cbW) {
    if (!b->st || b->kind == BoxKind::Text) return 0;
    const ComputedStyle& s = *b->st;
    return chbl_edge_px(s.padding[1], cbW) + chbl_edge_px(s.padding[3], cbW) + s.usedBorder(1) + s.usedBorder(3);
}

float chbl_margins_pure(const Box* b) {
    if (!b->st || b->kind == BoxKind::Text) return 0;
    const ComputedStyle& s = *b->st;
    return (s.margin[1].isAuto() ? 0.0f : chbl_edge_px(s.margin[1], -1)) +
           (s.margin[3].isAuto() ? 0.0f : chbl_edge_px(s.margin[3], -1));
}

/// Box-sizing conversion of a specified width value to a border-box width.
float chbl_to_border_w(const Box* b, float v, float cbW) {
    const float hbp = chbl_hbp_pure(b, cbW);
    return b->st->boxSizing == BoxSizing::BorderBox ? std::max(v, hbp) : v + hbp;
}

float chbl_to_border_h(const Box* b, float v) {
    const float vbp = b->pt + b->pb + b->bt + b->bb;
    return b->st->boxSizing == BoxSizing::BorderBox ? std::max(v, vbp) : v + vbp;
}

void chbl_center_button(Box* b, float contentH) {
    const float inner = b->contentH();
    if (!b->isButton || inner <= contentH + 0.01f) return;
    const float off = (inner - contentH) / 2.0f;
    for (Box* k : b->kids)
        if (!k->outOfFlow && k->kind != BoxKind::Text && k->kind != BoxKind::Inline) k->y += off;
    if (b->ifc) {
        for (auto& l : b->ifc->lines) { l.top += off; l.baseline += off; }
        for (auto& f : b->ifc->frags) { f.top += off; f.baseline += off; }
        for (const auto& f : b->ifc->frags)
            if (f.type == InlineFrag::Atomic && f.box) f.box->y = f.top;
    }
    if (!std::isnan(b->firstBaseline)) b->firstBaseline += off;
    if (!std::isnan(b->lastBaseline)) b->lastBaseline += off;
}

void chbl_list_marker(LayoutCtx& c, Box* b) {
    Q_UNUSED(c);
    if (!b->isListItem || b->marker.isEmpty() || b->st->listInside) return;
    const ComputedStyle& s = *b->st;
    const FontEntry& fe = font_entry(s.fontFamily ? *s.fontFamily : QStringList{QStringLiteral("serif")}, s.fontSize,
                                     s.fontWeight, s.fontStyle != FontStyle::Normal);
    b->markerShape = &shape_text(fe, b->marker, 0.0f);
    b->markerX = b->contentX() - b->markerShape->width;
    float base = lc_first_baseline(b);
    if (std::isnan(base)) base = b->contentY() + fe.m.asc;
    b->markerBaseline = base;
    if (b->markerSymbol) {
        // Blink ListMarker: symbol markers are shapes. margin-start = −(asc·2/3) − kCMarkerPaddingPx(7) − 1,
        // bullet = (asc·2/3 + 1)/2 square at (1, 3·(asc − asc·2/3)/2) inside the marker box (integer maths).
        const int asc = int(fe.m.asc);
        const int offset = asc * 2 / 3;
        const int bullet = (asc * 2 / 3 + 1) / 2;
        const float boxLeft = b->contentX() - float(offset + 7 + 1);
        const float boxTop = base - float(asc);
        b->markerRect = QRectF(boxLeft + 1, boxTop + float(3 * (asc - offset) / 2), bullet, bullet);
    }
}

} // namespace

// ============================================================================================== sizing

float lc_len(const Len& l, float base) { return chbl_edge_px(l, base); }

void lc_edges(Box* b, float cbW) {
    if (!b->st || b->kind == BoxKind::Text) {
        b->mt = b->mr = b->mb = b->ml = b->bt = b->br = b->bb = b->bl = b->pt = b->pr = b->pb = b->pl = 0;
        return;
    }
    const ComputedStyle& s = *b->st;
    b->pt = chbl_edge_px(s.padding[0], cbW);
    b->pr = chbl_edge_px(s.padding[1], cbW);
    b->pb = chbl_edge_px(s.padding[2], cbW);
    b->pl = chbl_edge_px(s.padding[3], cbW);
    if (b->kind != BoxKind::Cell || s.borderCollapse != BorderCollapse::Collapse) {
        b->bt = s.usedBorder(0);
        b->br = s.usedBorder(1);
        b->bb = s.usedBorder(2);
        b->bl = s.usedBorder(3);
    }
    b->mt = s.margin[0].isAuto() ? 0.0f : chbl_edge_px(s.margin[0], cbW);
    b->mr = s.margin[1].isAuto() ? 0.0f : chbl_edge_px(s.margin[1], cbW);
    b->mb = s.margin[2].isAuto() ? 0.0f : chbl_edge_px(s.margin[2], cbW);
    b->ml = s.margin[3].isAuto() ? 0.0f : chbl_edge_px(s.margin[3], cbW);
}

float lc_hbp(const Box* b) { return b->pl + b->pr + b->bl + b->br; }
float lc_vbp(const Box* b) { return b->pt + b->pb + b->bt + b->bb; }

float lc_spec_width(LayoutCtx& c, Box* b, float cbW) {
    const Len& w = b->st->width;
    switch (w.kind) {
    case Len::Val:
        if (w.hasPct() && cbW < 0) return -1;
        return chbl_to_border_w(b, chbl_edge_px(w, cbW), cbW);
    case Len::MinContent: { float mn, mx; lc_intrinsic(c, b, &mn, &mx); return mn; }
    case Len::MaxContent: { float mn, mx; lc_intrinsic(c, b, &mn, &mx); return mx; }
    case Len::FitContent: {
        if (cbW < 0) { float mn, mx; lc_intrinsic(c, b, &mn, &mx); return mx; }
        return lc_shrink_to_fit(c, b, cbW - chbl_margins_pure(b));
    }
    default: return -1;
    }
}

float lc_spec_height(Box* b, float cbH) {
    const Len& h = b->st->height;
    if (h.kind != Len::Val) return -1;
    if (h.hasPct() && cbH < 0) return -1;
    return chbl_to_border_h(b, chbl_edge_px(h, cbH));
}

float lc_min_width(LayoutCtx& c, Box* b, float cbW) {
    const Len& m = b->st->minW;
    if (m.kind == Len::Val) {
        if (m.hasPct() && cbW < 0) return 0;
        return chbl_to_border_w(b, chbl_edge_px(m, cbW), cbW);
    }
    if (m.kind == Len::MinContent || m.kind == Len::MaxContent || m.kind == Len::FitContent) {
        float mn, mx;
        lc_intrinsic(c, b, &mn, &mx);
        return m.kind == Len::MinContent ? mn : mx;
    }
    return 0;
}

float lc_max_width(LayoutCtx& c, Box* b, float cbW) {
    const Len& m = b->st->maxW;
    if (m.kind == Len::Val) {
        if (m.hasPct() && cbW < 0) return kInf;
        return chbl_to_border_w(b, chbl_edge_px(m, cbW), cbW);
    }
    if (m.kind == Len::MinContent || m.kind == Len::MaxContent || m.kind == Len::FitContent) {
        float mn, mx;
        lc_intrinsic(c, b, &mn, &mx);
        return m.kind == Len::MinContent ? mn : mx;
    }
    return kInf;
}

float lc_min_height(Box* b, float cbH) {
    const Len& m = b->st->minH;
    if (m.kind != Len::Val || (m.hasPct() && cbH < 0)) return 0;
    return chbl_to_border_h(b, chbl_edge_px(m, cbH));
}

float lc_max_height(Box* b, float cbH) {
    const Len& m = b->st->maxH;
    if (m.kind != Len::Val || (m.hasPct() && cbH < 0)) return kInf;
    return chbl_to_border_h(b, chbl_edge_px(m, cbH));
}

float lc_clamp_w(LayoutCtx& c, Box* b, float w, float cbW) {
    return std::max(lc_min_width(c, b, cbW), std::min(w, lc_max_width(c, b, cbW)));
}

float lc_clamp_h(Box* b, float h, float cbH) { return std::max(lc_min_height(b, cbH), std::min(h, lc_max_height(b, cbH))); }

// ============================================================================================== intrinsic

void lc_intrinsic(LayoutCtx& c, Box* b, float* minW, float* maxW) {
    if (b->intrinsicGen == c.gen) {
        *minW = b->minContent;
        *maxW = b->maxContent;
        return;
    }
    float mn = 0, mx = 0;
    const float hbp = chbl_hbp_pure(b, -1);
    switch (b->kind) {
    case BoxKind::Flex: lc_flex_intrinsic(c, b, &mn, &mx); mn += hbp; mx += hbp; break;
    case BoxKind::Grid: lc_grid_intrinsic(c, b, &mn, &mx); mn += hbp; mx += hbp; break;
    case BoxKind::Table: lc_table_intrinsic(c, b, &mn, &mx); break;
    case BoxKind::Replaced: lc_replaced_intrinsic(c, b, &mn, &mx); break;
    case BoxKind::Text: case BoxKind::Br: break;
    default:
        if (b->inlineContent) {
            lc_inline_intrinsic(c, b, &mn, &mx);
        } else {
            for (Box* k : b->kids) {
                if (k->outOfFlow || k->kind == BoxKind::Text) continue;
                mn = std::max(mn, lc_min_contribution(c, k));
                mx = std::max(mx, lc_max_contribution(c, k));
            }
        }
        mn += hbp;
        mx += hbp;
        break;
    }
    if (mx < mn) mx = mn;
    b->minContent = mn;
    b->maxContent = mx;
    b->intrinsicGen = c.gen;
    *minW = mn;
    *maxW = mx;
}

namespace {

float chbl_contribution(LayoutCtx& c, Box* b, bool wantMax) {
    if (b->outOfFlow) return 0;
    float mn = 0, mx = 0;
    const Len& w = b->st->width;
    float v;
    if (w.kind == Len::Val && !w.hasPct()) {
        v = chbl_to_border_w(b, w.px, -1);
    } else if (w.kind == Len::Val && w.hasPct() && b->kind == BoxKind::Replaced) {
        v = wantMax ? (lc_intrinsic(c, b, &mn, &mx), mx) : 0.0f; // % replaced: min-content contribution 0
    } else {
        lc_intrinsic(c, b, &mn, &mx);
        v = (w.kind == Len::MinContent) ? mn : (w.kind == Len::MaxContent ? mx : (wantMax ? mx : mn));
    }
    // min/max-width (only definite px values apply to contributions)
    const Len& mw = b->st->minW;
    if (mw.kind == Len::Val && !mw.hasPct()) v = std::max(v, chbl_to_border_w(b, mw.px, -1));
    const Len& xw = b->st->maxW;
    if (xw.kind == Len::Val && !xw.hasPct()) v = std::min(v, chbl_to_border_w(b, xw.px, -1));
    return std::max(0.0f, v + chbl_margins_pure(b));
}

} // namespace

float lc_min_contribution(LayoutCtx& c, Box* b) { return chbl_contribution(c, b, false); }
float lc_max_contribution(LayoutCtx& c, Box* b) { return chbl_contribution(c, b, true); }

float lc_shrink_to_fit(LayoutCtx& c, Box* b, float availBorderW) {
    float mn = 0, mx = 0;
    lc_intrinsic(c, b, &mn, &mx);
    // Chrome rounds the preferred width up to the next LayoutUnit so its own content fits.
    mx = std::ceil(mx * 64.0f - 0.001f) / 64.0f;
    return std::min(std::max(mn, availBorderW), mx);
}

// ============================================================================================== BFC

bool lc_is_bfc_root(const Box* b) {
    if (!b->st) return false;
    if (!b->parent) return true;
    if (b->atomic || b->outOfFlow || b->clips) return true;
    if (b->kind != BoxKind::Block) return true; // flex/grid/table/cell/replaced establish their own context
    const Box* p = b->parent;
    if (p->kind == BoxKind::Flex || p->kind == BoxKind::Grid) return true;
    if (b->st->display == Display::FlowRoot || b->isButton || b->isSelect) return true;
    return false;
}

// ============================================================================================== block-level

BlockOut lc_layout_block_level(LayoutCtx& c, Box* b, float cbW, float cbH) {
    lc_edges(b, cbW);
    const ComputedStyle& s = *b->st;
    const bool mlAuto = s.margin[3].isAuto(), mrAuto = s.margin[1].isAuto();
    float w = 0;
    bool haveWidth = false;
    if (b->kind == BoxKind::Table) {
        const float avail = cbW - b->ml - b->mr;
        lc_table(c, b, avail, -1, cbH);
        w = b->w;
        haveWidth = true;
    } else if (b->kind == BoxKind::Replaced) {
        float rw = 0, rh = 0;
        lc_replaced_size(c, b, cbW, cbH, &rw, &rh);
        w = rw;
        b->w = rw;
        b->h = rh;
        haveWidth = true;
    } else {
        const float spec = lc_spec_width(c, b, cbW);
        if (spec >= 0) {
            w = spec;
            haveWidth = true;
        } else {
            w = cbW - b->ml - b->mr;
        }
        const float clamped = lc_clamp_w(c, b, w, cbW);
        if (clamped != w) haveWidth = true;
        w = std::max(0.0f, clamped);
    }
    // horizontal margins (CSS 2.1 §10.3.3)
    if (haveWidth) {
        float rest = cbW - w - (mlAuto ? 0 : b->ml) - (mrAuto ? 0 : b->mr);
        if (mlAuto && mrAuto) {
            if (rest < 0) { b->ml = 0; b->mr = rest; }
            else { b->ml = rest / 2.0f; b->mr = rest / 2.0f; }
        } else if (mlAuto) {
            b->ml = std::max(rest, 0.0f) > 0 ? rest : 0.0f;
            if (rest < 0) b->ml = 0;
        } else if (mrAuto) {
            b->mr = rest;
        } else {
            b->mr = cbW - w - b->ml; // over-constrained: margin-right ignored (LTR)
        }
    }
    if (b->kind == BoxKind::Table || b->kind == BoxKind::Replaced) {
        BlockOut out;
        out.top.add(b->mt);
        out.bottom.add(b->mb);
        return out;
    }
    b->w = w;
    const float specH = lc_spec_height(b, cbH);
    b->definiteH = specH >= 0 ? std::max(0.0f, specH - lc_vbp(b)) : -1;
    BlockOut through;
    const float ch = lc_layout_inside(c, b, &through);
    float h = specH >= 0 ? specH : ch + lc_vbp(b);
    h = lc_clamp_h(b, h, cbH);
    b->h = h;
    chbl_center_button(b, ch);
    chbl_list_marker(c, b);

    BlockOut out;
    out.top.add(b->mt);
    out.bottom.add(b->mb);
    const bool isFlowBlock = b->kind == BoxKind::Block && !b->bfcRoot;
    const bool canTop = isFlowBlock && b->bt == 0 && b->pt == 0;
    const bool autoH = s.height.kind == Len::Auto || specH < 0;
    const bool canBottom = isFlowBlock && b->bb == 0 && b->pb == 0 && autoH && lc_min_height(b, cbH) <= 0;
    if (canTop) out.top.merge(through.top);
    if (canBottom) out.bottom.merge(through.bottom);
    if (through.selfCollapsing && canTop && canBottom && h <= 0.0001f) {
        out.selfCollapsing = true;
        out.ownTop = out.top;
        MarginStrut all = out.top;
        all.merge(out.bottom);
        out.top = all;
        out.bottom = all;
    }
    return out;
}

void lc_layout_sized(LayoutCtx& c, Box* b, float borderW, float borderH, float cbW, float cbH) {
    lc_edges(b, cbW);
    if (b->kind == BoxKind::Table) {
        lc_table(c, b, borderW, borderW, cbH);
        if (borderH > b->h) b->h = borderH;
        return;
    }
    if (b->kind == BoxKind::Replaced) {
        float rw = 0, rh = 0;
        lc_replaced_size(c, b, cbW, cbH, &rw, &rh);
        b->w = borderW;
        b->h = borderH >= 0 ? borderH : rh;
        return;
    }
    b->w = std::max(0.0f, borderW);
    b->forcedW = true;
    const float specH = borderH >= 0 ? borderH : lc_spec_height(b, cbH);
    b->forcedH = borderH >= 0;
    b->definiteH = specH >= 0 ? std::max(0.0f, specH - lc_vbp(b)) : -1;
    const float ch = lc_layout_inside(c, b, nullptr);
    float h = specH >= 0 ? specH : ch + lc_vbp(b);
    if (borderH < 0) h = lc_clamp_h(b, h, cbH);
    b->h = h;
    chbl_center_button(b, ch);
    chbl_list_marker(c, b);
}

float lc_layout_inside(LayoutCtx& c, Box* b, BlockOut* through) {
    b->firstBaseline = b->lastBaseline = std::numeric_limits<float>::quiet_NaN();
    const float cw = b->contentW();
    switch (b->kind) {
    case BoxKind::Flex: return lc_flex(c, b, cw, b->definiteH);
    case BoxKind::Grid: return lc_grid(c, b, cw, b->definiteH);
    case BoxKind::Replaced: return 0;
    case BoxKind::Table: return 0;
    default: break;
    }
    if (b->inlineContent) {
        const float h = lc_inline(c, b, cw);
        if (through) {
            through->selfCollapsing = !(b->ifc && b->ifc->hasContent);
        }
        return h;
    }
    return lc_block_flow(c, b, cw, through);
}

float lc_block_flow(LayoutCtx& c, Box* b, float cw, BlockOut* through) {
    const float top = b->contentY();
    float y = top;
    const bool canTop = !b->bfcRoot && b->bt == 0 && b->pt == 0;
    MarginStrut pending, topThrough;
    bool placed = false;
    bool anyInFlow = false;
    for (Box* k : b->kids) {
        if (k->outOfFlow) {
            k->staticParent = b;
            k->staticX = b->contentX();
            k->staticY = y + ((placed || !canTop) ? pending.sum() : 0.0f);
            continue;
        }
        if (k->kind == BoxKind::Text) continue;
        anyInFlow = true;
        const BlockOut co = lc_layout_block_level(c, k, cw, b->definiteH);
        k->ref = b;
        k->x = b->contentX() + k->ml;
        if (!placed && canTop) {
            topThrough.merge(co.top);
            if (co.selfCollapsing) {
                topThrough.merge(co.bottom);
                k->y = y;
                continue;
            }
            k->y = y;
            y += k->h;
            pending = co.bottom;
            placed = true;
        } else {
            if (co.selfCollapsing) {
                // CSS 2.1 §8.3.1: top border edge placed as if it had a bottom border (own top margin only)
                MarginStrut pos = pending;
                pos.merge(co.ownTop);
                pending.merge(co.top);
                k->y = y + pos.sum();
                continue;
            }
            pending.merge(co.top);
            y += pending.sum();
            k->y = y;
            y += k->h;
            pending = co.bottom;
            placed = true;
        }
        // baselines
        const float fb = lc_first_baseline(k);
        if (std::isnan(b->firstBaseline) && !std::isnan(fb)) b->firstBaseline = k->y + fb;
        const float lb = !std::isnan(k->lastBaseline) ? k->lastBaseline : fb;
        if (!std::isnan(lb) && !k->clips) b->lastBaseline = k->y + lb;
    }
    Q_UNUSED(anyInFlow);
    Q_UNUSED(c);
    Q_UNUSED(cw);
    const bool autoH = b->st->height.kind == Len::Auto;
    const bool canBottom = !b->bfcRoot && b->bb == 0 && b->pb == 0 && autoH;
    if (through) {
        through->top = topThrough;
        if (canBottom) {
            MarginStrut bt = pending;
            if (!placed) bt.merge(topThrough);
            through->bottom = bt;
        }
        through->selfCollapsing = !placed;
    }
    if (!canBottom || !through) y += placed ? pending.sum() : 0.0f;
    if (!placed && !canTop) y += 0; // nothing placed: content height 0
    return std::max(0.0f, y - top);
}

// ============================================================================================== baselines

float lc_first_baseline(const Box* b) {
    if (!std::isnan(b->firstBaseline)) return b->firstBaseline;
    return std::numeric_limits<float>::quiet_NaN();
}

float lc_inline_block_baseline(const Box* b) {
    // inline-flex/grid/table and buttons/selects: first baseline; inline-block: last line box baseline;
    // scroll containers / no line boxes: bottom margin edge (caller adds margins).
    if (b->kind == BoxKind::Replaced && !b->isSelect) return std::numeric_limits<float>::quiet_NaN();
    if (b->kind == BoxKind::Flex || b->kind == BoxKind::Grid || b->kind == BoxKind::Table || b->isButton || b->isSelect)
        return b->firstBaseline;
    if (b->clips) return std::numeric_limits<float>::quiet_NaN();
    return b->lastBaseline;
}

// ============================================================================================== finalize

namespace {

void chbl_rel_offsets(Box* k) {
    k->relX = k->relY = 0;
    if (!k->st) return;
    const ComputedStyle& s = *k->st;
    const Box* p = k->parent;
    const float cbW = p ? p->contentW() : 0.0f;
    const float cbH = p ? p->definiteH : -1.0f;
    if (s.position == Position::Relative) {
        if (s.left.kind == Len::Val) k->relX = lc_len(s.left, cbW);
        else if (s.right.kind == Len::Val) k->relX = -lc_len(s.right, cbW);
        if (s.top.kind == Len::Val && !(s.top.hasPct() && cbH < 0)) k->relY = lc_len(s.top, cbH);
        else if (s.bottom.kind == Len::Val && !(s.bottom.hasPct() && cbH < 0)) k->relY = -lc_len(s.bottom, cbH);
    }
    if (!s.transform.none && k->kind != BoxKind::Inline) {
        k->relX += lc_len(s.transform.tx, k->w);
        k->relY += lc_len(s.transform.ty, k->h);
    }
}

void chbl_fin(Box* b, float addX, float addY) {
    for (Box* k : b->kids) {
        if (k->outOfFlow || k->kind == BoxKind::Text || k->kind == BoxKind::Br) continue;
        chbl_rel_offsets(k);
        if (k->kind == BoxKind::Inline && !k->atomic) {
            k->ax = b->ax;
            k->ay = b->ay;
            k->positioned = true;
            chbl_fin(k, addX + k->relX, addY + k->relY);
            continue;
        }
        const Box* ref = k->ref ? k->ref : b;
        k->ax = ref->ax + k->x + k->relX + addX;
        k->ay = ref->ay + k->y + k->relY + addY;
        k->positioned = true;
        chbl_fin(k, 0, 0);
    }
}

} // namespace

void lc_finalize(Box* b) { chbl_fin(b, 0, 0); }

// ============================================================================================== absolute

namespace {

QRectF chbl_cb_rect(const Box* cb, float icbW, float icbH) {
    if (!cb) return QRectF(0, 0, icbW, icbH);
    if (cb->kind == BoxKind::Inline && !cb->atomic) {
        // bounding box of the inline box's fragments in its formatting root
        const Box* root = cb->parent;
        while (root && !root->inlineContent) root = root->parent;
        QRectF u;
        if (root && root->ifc)
            for (const auto& f : root->ifc->frags)
                if (f.box == cb) u = u.united(QRectF(root->ax + f.x, root->ay + f.top, f.w, f.height));
        if (!u.isEmpty()) return u;
    }
    return QRectF(cb->ax + cb->bl, cb->ay + cb->bt, cb->w - cb->bl - cb->br, cb->h - cb->bt - cb->bb);
}

void chbl_layout_abs(LayoutCtx& c, Box* a, const QRectF& cbr) {
    const ComputedStyle& s = *a->st;
    const float cbW = float(cbr.width()), cbH = float(cbr.height());
    lc_edges(a, cbW);
    const bool lAuto = s.left.kind != Len::Val, rAuto = s.right.kind != Len::Val;
    const bool tAuto = s.top.kind != Len::Val, bAuto = s.bottom.kind != Len::Val;
    const float L = lAuto ? 0 : lc_len(s.left, cbW), R = rAuto ? 0 : lc_len(s.right, cbW);
    const float T = tAuto ? 0 : lc_len(s.top, cbH), B = bAuto ? 0 : lc_len(s.bottom, cbH);
    float sx = 0, sy = 0;
    if (a->staticParent && a->staticParent->positioned) {
        sx = a->staticParent->ax + a->staticX - float(cbr.x());
        sy = a->staticParent->ay + a->staticY - float(cbr.y());
    }
    const bool mlAuto = s.margin[3].isAuto(), mrAuto = s.margin[1].isAuto();
    float w = lc_spec_width(c, a, cbW);
    const bool autoW = w < 0;
    if (autoW) {
        if (a->kind == BoxKind::Replaced) {
            float rw = 0, rh = 0;
            lc_replaced_size(c, a, cbW, cbH, &rw, &rh);
            w = rw;
        } else if (!lAuto && !rAuto) {
            w = cbW - L - R - a->ml - a->mr;
        } else {
            const float left = lAuto ? sx : L;
            w = lc_shrink_to_fit(c, a, cbW - left - (rAuto ? 0 : R) - a->ml - a->mr);
        }
    }
    w = std::max(0.0f, lc_clamp_w(c, a, w, cbW));
    if (!lAuto && !rAuto && !autoW && (mlAuto || mrAuto)) {
        const float rest = cbW - L - R - w - (mlAuto ? 0 : a->ml) - (mrAuto ? 0 : a->mr);
        if (mlAuto && mrAuto) { a->ml = a->mr = std::max(0.0f, rest / 2.0f); }
        else if (mlAuto) a->ml = rest;
        else a->mr = rest;
    }
    float x = !lAuto ? L + a->ml : (!rAuto ? cbW - R - a->mr - w : sx + a->ml);
    // height
    float forcedH = -1;
    const float specH = lc_spec_height(a, cbH);
    if (specH >= 0) forcedH = specH;
    else if (!tAuto && !bAuto && s.height.kind == Len::Auto) forcedH = std::max(0.0f, cbH - T - B - a->mt - a->mb);
    lc_layout_sized(c, a, w, forcedH, cbW, cbH);
    if (forcedH >= 0) a->h = lc_clamp_h(a, forcedH, cbH);
    const float y = !tAuto ? T + a->mt : (!bAuto ? cbH - B - a->mb - a->h : sy + a->mt);
    a->relX = a->relY = 0;
    if (!s.transform.none) {
        a->relX = lc_len(s.transform.tx, a->w);
        a->relY = lc_len(s.transform.ty, a->h);
    }
    a->ax = float(cbr.x()) + x + a->relX;
    a->ay = float(cbr.y()) + y + a->relY;
    a->x = a->ax;
    a->y = a->ay;
    a->ref = nullptr;
    a->positioned = true;
    a->absDone = true;
}

void chbl_abs_walk(LayoutCtx& c, Box* b) {
    for (Box* a : b->absKids) {
        if (a->absDone) continue;
        const Box* cb = b->node || b->parent ? b : nullptr;
        const QRectF r = (b->parent == nullptr && !b->st->isPositioned()) ? QRectF(0, 0, c.icbW, c.icbH)
                                                                           : chbl_cb_rect(cb, c.icbW, c.icbH);
        chbl_layout_abs(c, a, r);
        lc_finalize(a);
    }
    for (Box* k : b->kids)
        if (!k->outOfFlow || k->absDone) chbl_abs_walk(c, k);
}

} // namespace

void lc_absolute_pass(LayoutCtx& c, Box* root) { chbl_abs_walk(c, root); }

// ============================================================================================== replaced

namespace {

bool chbl_attr_len(const RNode* n, QStringView name, float base, float* out) {
    if (!n || !n->src) return false;
    const QString* v = n->src->attr(name);
    if (!v) return false;
    SpecLen sl;
    if (!parse_css_length(*v, &sl, true) || sl.kind != SpecLen::Val) return false;
    if (sl.pct != 0 || sl.pctUnit) {
        if (base < 0) return false;
        *out = sl.px + sl.pct * base / 100.0f;
        return true;
    }
    *out = sl.px + sl.em * 16;
    return true;
}

/// True when the author style (classes, s, active var) sets property `p` to any value (auto included).
bool chbl_author_sets(const RNode* n, Prop p) {
    if (!n) return false;
    bool set = false;
    for (const DeclList* dl : n->decls)
        for (const Decl& d : dl->decls)
            if (d.prop == p) set = !d.remove;
    return set;
}

bool chbl_viewbox(const RNode* n, float* vw, float* vh) {
    if (!n || !n->src) return false;
    const QString* v = n->src->attr(u"viewBox");
    if (!v) return false;
    QString s = *v;
    s.replace(QLatin1Char(','), QLatin1Char(' '));
    const QStringList p = s.split(QLatin1Char(' '), Qt::SkipEmptyParts);
    if (p.size() != 4) return false;
    *vw = p[2].toFloat();
    *vh = p[3].toFloat();
    return *vw > 0 && *vh > 0;
}

void chbl_select_content(const Box* b, float* w, float* h) {
    const ComputedStyle& s = *b->st;
    const FontEntry& fe = font_entry(s.fontFamily ? *s.fontFamily : QStringList{QStringLiteral("serif")}, s.fontSize,
                                     s.fontWeight, s.fontStyle != FontStyle::Normal);
    float maxW = 0;
    if (b->node)
        for (const RNode* o : b->node->kids) {
            if (o->isText || o->tag != Tag::Option) continue;
            QString label;
            for (const RNode* t : o->kids)
                if (t->isText) label += t->text;
            label = label.simplified();
            maxW = std::max(maxW, shape_text(fe, label, s.letterSpacing).width);
        }
    // Chrome menulist (author-styled, measured): 4 px inner start padding + text + 16 px arrow area; the inner
    // line box gets 1 px above and below. The option width is whole pixels (MenuListSelectType::UpdateOptionsWidth:
    // ceil of the widest option; suite 54/57: 81.2 → 82, 205.4 → 206).
    *w = std::ceil(maxW - 1e-3f) + 4.0f + 16.0f;
    const float lh = s.lineHeightPx();
    *h = (lh >= 0 ? lh : fe.m.normalLineHeight()) + 2.0f;
}

} // namespace

void lc_replaced_size(LayoutCtx& c, Box* b, float cbW, float cbH, float* ow, float* oh) {
    Q_UNUSED(c);
    const ComputedStyle& s = *b->st;
    const float hbp = lc_hbp(b), vbp = lc_vbp(b);
    if (b->isSelect) {
        float cw = 0, chh = 0;
        chbl_select_content(b, &cw, &chh);
        float w = lc_spec_width(c, b, cbW);
        if (w < 0) w = cw + hbp;
        float h = lc_spec_height(b, cbH);
        if (h < 0) h = chh + vbp;
        *ow = lc_clamp_w(c, b, w, cbW);
        *oh = lc_clamp_h(b, h, cbH);
        // baseline: text line centred in the content box
        const ComputedStyle& ss = *b->st;
        static const QStringList serif{QStringLiteral("serif")};
        const FontEntry& fe = font_entry(ss.fontFamily ? *ss.fontFamily : serif, ss.fontSize, ss.fontWeight, ss.fontStyle != FontStyle::Normal);
        const float lhp = ss.lineHeightPx() >= 0 ? ss.lineHeightPx() : fe.m.normalLineHeight();
        const float bt = ss.usedBorder(0), pt = lc_len(ss.padding[0], cbW), pb = lc_len(ss.padding[2], cbW), bb = ss.usedBorder(2);
        const float inner = *oh - bt - pt - pb - bb;
        const float top = bt + pt + std::floor((inner - lhp) / 2.0f);
        b->firstBaseline = b->lastBaseline = top + std::floor((lhp - fe.m.height()) / 2.0f) + fe.m.asc;
        return;
    }
    // <svg>: CSS width/height (any author value, `auto` included, overrides the attribute) > attributes >
    // viewBox ratio > 300×150. The auto dimension follows the ratio AFTER the other one is clamped.
    float vbW = 0, vbH = 0;
    const bool hasVb = chbl_viewbox(b->node, &vbW, &vbH);
    float attrW = -1, attrH = -1;
    {
        float a = 0;
        if (chbl_attr_len(b->node, u"width", cbW, &a)) attrW = a;
        if (chbl_attr_len(b->node, u"height", cbH, &a)) attrH = a;
    }
    const float ratio = hasVb ? vbW / vbH : (attrW > 0 && attrH > 0 ? attrW / attrH : 0.0f);
    float w = -1, h = -1;
    if (s.width.kind == Len::Val && !(s.width.hasPct() && cbW < 0)) w = lc_len(s.width, cbW);
    else if (!chbl_author_sets(b->node, Prop::Width)) w = attrW;
    if (s.height.kind == Len::Val && !(s.height.hasPct() && cbH < 0)) h = lc_len(s.height, cbH);
    else if (!chbl_author_sets(b->node, Prop::Height)) h = attrH;
    if (s.boxSizing == BoxSizing::BorderBox && s.width.kind == Len::Val && w >= 0) w = std::max(0.0f, w - hbp);
    if (s.boxSizing == BoxSizing::BorderBox && s.height.kind == Len::Val && h >= 0) h = std::max(0.0f, h - vbp);
    if (w < 0 && h < 0) {
        if (ratio > 0 && cbW >= 0) {
            w = lc_clamp_w(c, b, cbW - b->ml - b->mr, cbW) - hbp;
            h = w / ratio;
        } else {
            w = 300;
            h = 150;
        }
    } else if (w < 0) {
        h = lc_clamp_h(b, h + vbp, cbH) - vbp;
        w = ratio > 0 ? h * ratio : 300;
    } else if (h < 0) {
        w = lc_clamp_w(c, b, w + hbp, cbW) - hbp;
        h = ratio > 0 ? w / ratio : 150;
    }
    *ow = lc_clamp_w(c, b, w + hbp, cbW);
    *oh = lc_clamp_h(b, h + vbp, cbH);
}

void lc_replaced_intrinsic(LayoutCtx& c, Box* b, float* minW, float* maxW) {
    float w = 0, h = 0;
    lc_replaced_size(c, b, -1, -1, &w, &h);
    *minW = w;
    *maxW = w;
}

} // namespace fincept::screens::chb
