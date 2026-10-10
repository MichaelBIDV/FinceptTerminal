// src/screens/hdcv_launchpad/HlpDomStyle.cpp
// Launchpad CSS engine — computed style (inherited properties, used line-height, half-leading bounds)
// and the box tree: Node → Box with anonymous block wrappers for inline runs, flex/grid items
// blockified, BFC roots marked. See HlpDom.cpp for the file map.
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

CS rootCS() {
    CS c;
    c.font.fam = Fam::Sans;
    c.font.px = 12.0f;
    c.font.weight = 400;
    c.font.italic = false;
    c.vm = detail::vmetrics(c.font);
    c.lhSpec = {1, 1.45f};
    c.lh = luFloor(12.0f * 1.45f); // 17.3984375
    c.color = pal().ink;
    return c;
}

CS resolveCS(const Style& st, const CS& p) {
    CS c = p;
    if (st.monoFamily)
        c.font.fam = *st.monoFamily ? Fam::Mono : Fam::Sans;
    if (st.arialFamily && *st.arialFamily)
        c.font.fam = Fam::Arial;
    if (st.fontSize)
        c.font.px = *st.fontSize;
    if (st.weight)
        c.font.weight = *st.weight;
    if (st.italic)
        c.font.italic = *st.italic;
    if (st.letterSpacingEm)
        // computed to px at the element, inherited as px; Blink adds it to each glyph advance as a
        // 16.16 TextRunLayoutUnit (truncated: .07em × 10.5px = 0.735 → 48168/65536) — the pen then
        // lands on Chrome's quarter pixel where a glyph sits right at a boundary (ĐỒNG)
        c.ls = float(std::trunc(double(*st.letterSpacingEm * c.font.px) * 65536.0) / 65536.0);
    if (st.upper)
        c.upper = *st.upper;
    if (st.color)
        c.color = *st.color;
    if (st.lineHeightPx)
        c.lhSpec = {2, *st.lineHeightPx};
    else if (st.lineHeightFactor)
        c.lhSpec = {1, *st.lineHeightFactor};
    else if (st.lineHeightNormal && *st.lineHeightNormal)
        c.lhSpec = {0, 0.0f};
    if (st.whiteSpace)
        c.ws = *st.whiteSpace;
    if (st.textAlign)
        c.align = *st.textAlign;
    c.vm = detail::vmetrics(c.font);
    if (c.lhSpec.kind == 0)
        c.lh = c.vm.lineSpacing();
    else if (c.lhSpec.kind == 1)
        c.lh = luFloor(c.font.px * c.lhSpec.v);
    else
        c.lh = luFloor(c.lhSpec.v);
    return c;
}

VB inlineBounds(const CS& c) {
    const float ad = c.vm.ascent + c.vm.descent;
    const float lead = c.lh - ad;
    const float ascLead = halfFloor(lead / 2.0f); // InlineBoxState::CalculateLeadingSpace: Floor() at zoom 2
    const float descLead = lead - ascLead;
    return {c.vm.ascent + ascLead, c.vm.descent + descLead};
}

bool isInlineLevel(const Box* b) {
    return b->kind == BK::Inline || b->kind == BK::Text || b->kind == BK::Br || b->kind == BK::Atomic;
}

bool isWhitespace(const QString& s) {
    for (QChar c : s)
        if (!(c == u' ' || c == u'\n' || c == u'\t' || c == u'\r' || c == u'\f'))
            return false;
    return true;
}

bool inlineRunIsBlank(const QVector<Box*>& run) {
    for (const Box* b : run) {
        if (b->kind == BK::Atomic || b->kind == BK::Br)
            return false;
        if (b->kind == BK::Text && !isWhitespace(b->node ? b->node->text : b->text))
            return false;
        if (b->kind == BK::Inline && !inlineRunIsBlank(b->kids))
            return false;
    }
    return true;
}

/// Normalise the children of a block container / flex / grid: anonymous wrappers for inline runs.
void normalizeKids(Doc& d, Box* b) {
    const bool itemsCtx = b->kind == BK::Flex || b->kind == BK::Grid;
    bool anyBlock = false, anyInline = false;
    for (Box* k : b->kids)
        (isInlineLevel(k) ? anyInline : anyBlock) = true;
    if (!itemsCtx && !anyBlock)
        return; // pure inline content → IFC
    if (itemsCtx) {
        // each atomic inline becomes a block item; text runs get an anonymous item
        QVector<Box*> out, run;
        auto flush = [&]() {
            if (run.isEmpty())
                return;
            if (!inlineRunIsBlank(run)) {
                Box* a = d.make();
                a->kind = BK::Block;
                a->cs = b->cs;
                a->st = nullptr;
                a->parent = b;
                a->kids = run;
                for (Box* k : run)
                    k->parent = a;
                out.push_back(a);
            }
            run.clear();
        };
        for (Box* k : b->kids) {
            // text nodes (and <br>) gather into anonymous items; every element is its own item
            // (lineClamp < 0 = the pre-textNode marker, still honoured)
            const bool textNode = k->kind == BK::Br ||
                                  (k->kind == BK::Text && (!k->st || (k->node && k->node->textNode) ||
                                                           k->st->lineClamp < 0 || k->node == b->node));
            if (textNode) {
                run.push_back(k);
                continue;
            }
            flush();
            if (isInlineLevel(k)) {
                // blockify: an inline element becomes a block container around its own content
                if (k->kind == BK::Text) {
                    Box* t = d.make();
                    t->kind = BK::Text;
                    t->node = k->node;
                    t->st = k->st;
                    t->cs = k->cs;
                    t->parent = k;
                    k->kids = {t};
                } else {
                    for (Box* kk : k->kids)
                        kk->parent = k;
                }
                k->kind = BK::Block;
                normalizeKids(d, k);
            }
            out.push_back(k);
        }
        flush();
        b->kids = out;
        return;
    }
    if (!anyInline)
        return;
    QVector<Box*> out, run;
    auto flush = [&]() {
        if (run.isEmpty())
            return;
        if (!inlineRunIsBlank(run)) {
            Box* a = d.make();
            a->kind = BK::Block;
            a->cs = b->cs;
            a->parent = b;
            a->kids = run;
            for (Box* k : run)
                k->parent = a;
            out.push_back(a);
        }
        run.clear();
    };
    for (Box* k : b->kids) {
        if (isInlineLevel(k))
            run.push_back(k);
        else {
            flush();
            out.push_back(k);
        }
    }
    flush();
    b->kids = out;
}

Box* build(Doc& d, Node* n, const CS& pcs, Box* parent) {
    if (!n || n->st.display == Display::None)
        return nullptr;
    Box* b = d.make();
    b->node = n;
    b->parent = parent;
    b->st = &n->st;
    b->cs = d.cs(resolveCS(n->st, pcs));
    switch (n->st.display) {
    case Display::Inline:
        b->kind = n->br ? BK::Br : (!n->text.isEmpty() && n->kids.isEmpty()) ? BK::Text : BK::Inline;
        break;
    case Display::InlineBlock: b->kind = BK::Atomic; break;
    case Display::Flex: b->kind = BK::Flex; break;
    case Display::Grid: b->kind = BK::Grid; break;
    case Display::Table: b->kind = BK::Table; break;
    case Display::TableRow: b->kind = BK::Row; break;
    case Display::TableCell: b->kind = BK::Cell; break;
    default: b->kind = BK::Block; break;
    }
    if (n->customPaint || n->customHeight)
        b->custom = true;
    if (n->widget) {
        b->widget = true;
        d.widgets.push_back(b);
    }
    if (n->st.sticky)
        d.stickies.push_back(b);
    if (b->kind == BK::Text || b->kind == BK::Br || b->custom || b->widget)
        return b;
    // a text on a container node = leading anonymous text child
    if (!n->text.isEmpty()) {
        Box* t = d.make();
        t->kind = BK::Text;
        t->node = n;
        t->st = &n->st;
        t->cs = b->cs;
        t->parent = b;
        b->kids.push_back(t);
    }
    for (const NodeP& k : n->kids)
        if (Box* kb = build(d, k.get(), *b->cs, b))
            b->kids.push_back(kb);
    if (b->kind == BK::Inline) {
        bool hasBlock = false;
        for (Box* k : b->kids)
            if (!isInlineLevel(k))
                hasBlock = true;
        if (hasBlock)
            b->kind = BK::Block; // block-in-inline: treat the span as a block (not used by the Launchpad)
        else
            return b;
    }
    if (b->kind == BK::Table || b->kind == BK::Row)
        return b;
    normalizeKids(d, b);
    return b;
}

void markBfc(Box* b, bool isRoot) {
    b->bfcRoot = isRoot || b->kind == BK::Flex || b->kind == BK::Grid || b->kind == BK::Table ||
                 b->kind == BK::Cell || b->kind == BK::Atomic || b->custom || b->widget ||
                 (b->st && b->st->lineClamp > 0);
    const bool itemsCtx = b->kind == BK::Flex || b->kind == BK::Grid;
    for (Box* k : b->kids) {
        markBfc(k, itemsCtx);
        if (itemsCtx)
            k->bfcRoot = true;
    }
}

bool hasInlineContent(const Box* b) {
    if (b->kids.isEmpty())
        return false;
    for (const Box* k : b->kids)
        if (!isInlineLevel(k))
            return false;
    return true;
}

void prepare(Box* b) {
    if (b->kind == BK::Text || b->kind == BK::Br || b->custom || b->widget)
        return;
    if (b->kind != BK::Inline && b->kind != BK::Row && b->kind != BK::Table && b->kind != BK::Flex &&
        b->kind != BK::Grid && hasInlineContent(b)) {
        buildIfc(b);
    }
    for (Box* k : b->kids)
        prepare(k);
}

} // namespace fincept::screens::hlp::hlpdom
