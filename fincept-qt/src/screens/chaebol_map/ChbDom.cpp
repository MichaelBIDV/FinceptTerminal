// ChbDom.cpp — Document API: trees, state, resolve → style → box tree → layout orchestration.
// (Engine written from scratch for chaebol_map; not derived from hdcv_launchpad/HlpDom.)
#include "screens/chaebol_map/ChbDom_p.h"
#include "screens/chaebol_map/ChbFonts.h"

#include <QElapsedTimer>
#include <QJsonDocument>

#include <cmath>

namespace fincept::screens::chb {

// ============================================================================================== Impl

Box* Document::Impl::new_box() {
    boxes.emplace_back();
    return &boxes.back();
}

ComputedStyle* Document::Impl::new_anon_style(const ComputedStyle& parent, Display d) {
    anonStyles.push_back(std::make_unique<ComputedStyle>(anonymous_style(parent, d)));
    return anonStyles.back().get();
}

const SrcTree* Document::Impl::load_tree(const QString& kind, const QString& key) {
    if (kind == QLatin1String("inc")) {
        auto it = incs.find(key);
        if (it == incs.end()) {
            if (!incLoader) return nullptr;
            const QByteArray bytes = incLoader(key);
            if (bytes.isEmpty()) return nullptr;
            auto t = parse_tree(bytes, QStringLiteral("inc/%1").arg(key));
            if (!t->ok) warnings << t->error;
            it = incs.insert(key, t);
        }
        if (it.value() && it.value()->ok) state.add_scoped_keys(it.value()->scopedKeys);
        return it.value().get();
    }
    const QString tab = state.get(QStringLiteral("tab"));
    auto it = tabs.find(tab);
    if (it == tabs.end()) {
        if (!tabLoader || tab.isEmpty()) return nullptr;
        const QByteArray bytes = tabLoader(tab);
        if (bytes.isEmpty()) return nullptr;
        auto t = parse_tree(bytes, QStringLiteral("tab_%1").arg(tab));
        if (!t->ok) warnings << t->error;
        it = tabs.insert(tab, t);
    }
    if (it.value() && it.value()->ok) state.add_scoped_keys(it.value()->scopedKeys);
    return it.value().get();
}

void Document::Impl::do_resolve() {
    QElapsedTimer t;
    t.start();
    boxes.clear();
    body = nullptr;
    regions.clear();
    laidOut = false;
    rootNode = nullptr;
    if (!top) {
        arena.clear();
        rr = ResolveResult{};
        resolveDirty = false;
        styleDirty = true;
        return;
    }
    rr = resolve_tree(*top, state, [this](const QString& kind, const QString& key) { return load_tree(kind, key); }, arena);
    rootNode = (rr.root && !rr.root->isText) ? rr.root : nullptr;
    state.reset_unrendered_scopes(rr.renderedScopes);
    resolveDirty = false;
    styleDirty = true;
    timing.resolveMs = double(t.nsecsElapsed()) / 1e6;
    timing.nodes = rr.nodeCount;
}

void Document::Impl::do_style() {
    QElapsedTimer t;
    t.start();
    styles.clear();
    StyleEnv env;
    env.vw = vpW;
    env.vh = vpH;
    const std::vector<const DeclList*> none;
    cascade(htmlStyle, nullptr, Tag::Unknown, false, none, env);
    htmlStyle.display = Display::Block;
    cascade(bodyStyle, &htmlStyle, Tag::Body, false, none, env);
    bodyImplicit = !rr.rootIsBody;
    if (rootNode) {
        std::vector<RNode*> stack{rootNode};
        while (!stack.empty()) {
            RNode* r = stack.back();
            stack.pop_back();
            if (r->isText) continue;
            styles.emplace_back();
            ComputedStyle* st = &styles.back();
            const ComputedStyle* parent = r->parent ? r->parent->style : (rr.rootIsBody ? &htmlStyle : &bodyStyle);
            const Tag tag = (r == rootNode && rr.rootIsBody) ? Tag::Body : r->tag;
            int listDepth = 0;
            if (tag == Tag::Ul || tag == Tag::Ol)
                for (const RNode* a = r->parent; a; a = a->parent)
                    if (!a->isText && (a->tag == Tag::Ul || a->tag == Tag::Ol)) ++listDepth;
            if (tag == Tag::Tr && r->parent && !r->parent->isText && r->parent->tag == Tag::Table) listDepth = 1;
            cascade(*st, parent, r->inSvg && r->tag != Tag::Svg ? Tag::Unknown : tag, r->isLink, r->decls, env, listDepth);
            if (r == rootNode) {
                // the root element is blockified
                if (st->display == Display::Inline || st->display == Display::InlineBlock) st->display = Display::Block;
                else if (st->display == Display::InlineFlex) st->display = Display::Flex;
                else if (st->display == Display::InlineGrid) st->display = Display::Grid;
                else if (st->display == Display::InlineTable) st->display = Display::Table;
            }
            r->style = st;
            for (size_t i = r->kids.size(); i-- > 0;) stack.push_back(r->kids[i]);
        }
    }
    styleDirty = false;
    timing.styleMs = double(t.nsecsElapsed()) / 1e6;
}

// ============================================================================================== box tree

namespace {

bool chbd_ws_only(const QString& s) {
    for (const QChar c : s)
        if (c != u' ' && c != u'\n' && c != u'\t' && c != u'\r' && c != u'\f') return false;
    return true;
}

bool chbd_inline_level(const Box* k) {
    return k->kind == BoxKind::Text || k->kind == BoxKind::Br || (k->kind == BoxKind::Inline && !k->atomic) || k->atomic;
}

QString chbd_marker_text(ListStyle ls, int ordinal) {
    auto alpha = [](int n, bool upper) {
        QString s;
        while (n > 0) {
            --n;
            s.prepend(QChar((upper ? 'A' : 'a') + (n % 26)));
            n /= 26;
        }
        return s;
    };
    auto roman = [](int n, bool upper) {
        static const struct { int v; const char* s; } t[] = {{1000, "m"}, {900, "cm"}, {500, "d"}, {400, "cd"},
                                                              {100, "c"}, {90, "xc"}, {50, "l"}, {40, "xl"},
                                                              {10, "x"}, {9, "ix"}, {5, "v"}, {4, "iv"}, {1, "i"}};
        QString s;
        for (const auto& e : t)
            while (n >= e.v) { s += QString::fromLatin1(e.s); n -= e.v; }
        return upper ? s.toUpper() : s;
    };
    switch (ls) {
    case ListStyle::Disc: return QStringLiteral("• ");
    case ListStyle::Circle: return QStringLiteral("◦ ");
    case ListStyle::Square: return QStringLiteral("▪ ");
    case ListStyle::Decimal: return QString::number(ordinal) + QStringLiteral(". ");
    case ListStyle::DecimalLeadingZero: return QString::number(ordinal).rightJustified(2, u'0') + QStringLiteral(". ");
    case ListStyle::LowerAlpha: return alpha(ordinal, false) + QStringLiteral(". ");
    case ListStyle::UpperAlpha: return alpha(ordinal, true) + QStringLiteral(". ");
    case ListStyle::LowerRoman: return roman(ordinal, false) + QStringLiteral(". ");
    case ListStyle::UpperRoman: return roman(ordinal, true) + QStringLiteral(". ");
    default: return QString();
    }
}

struct ChbdBuilder {
    Document::Impl& d;

    Box* anon(Box* parent, Display disp, BoxKind kind) {
        Box* a = d.new_box();
        a->anonymous = true;
        a->st = d.new_anon_style(*parent->st, disp);
        a->kind = kind;
        a->parent = parent;
        a->blockLevel = true;
        return a;
    }

    Box* textBox(RNode* t, Box* parent) {
        Box* b = d.new_box();
        b->node = t;
        b->st = parent->st;
        b->kind = BoxKind::Text;
        b->parent = parent;
        b->rawText = t->text;
        t->box = b;
        return b;
    }

    void attachOutOfFlow(Box* b) {
        const bool fixed = b->st->position == Position::Fixed;
        Box* cb = nullptr;
        if (!fixed)
            for (Box* p = b->parent; p; p = p->parent)
                if (p->st && p->st->isPositioned() && !p->anonymous) { cb = p; break; }
        if (!cb) {
            cb = d.body;
            b->cbIcb = true;
        }
        cb->absKids.push_back(b);
    }

    Box* element(RNode* r, Box* parent) {
        const ComputedStyle* st = r->style;
        if (!st || st->display == Display::None) return nullptr;
        if (r->tag == Tag::Option) return nullptr; // rendered by <select>
        if (st->display == Display::TableColumn || st->display == Display::TableColumnGroup) return nullptr;
        Box* b = d.new_box();
        b->node = r;
        b->st = st;
        b->parent = parent;
        r->box = b;
        const bool parentFlexGrid = parent && (parent->kind == BoxKind::Flex || parent->kind == BoxKind::Grid);
        b->outOfFlow = st->isOutOfFlow() && parent;
        const bool blockify = parentFlexGrid || b->outOfFlow || !parent;
        Display disp = st->display;
        if (r->tag == Tag::Br) {
            b->kind = BoxKind::Br;
            return b;
        }
        if (r->tag == Tag::Svg || r->tag == Tag::Select) {
            b->kind = BoxKind::Replaced;
            b->isSvg = r->tag == Tag::Svg;
            b->isSelect = r->tag == Tag::Select;
            b->atomic = !blockify && (disp == Display::Inline || disp == Display::InlineBlock || disp == Display::InlineFlex ||
                                      disp == Display::InlineGrid || disp == Display::InlineTable);
            b->blockLevel = !b->atomic;
            b->clips = b->isSvg;
            if (b->outOfFlow) attachOutOfFlow(b);
            return b;
        }
        switch (disp) {
        case Display::Flex: case Display::InlineFlex: b->kind = BoxKind::Flex; break;
        case Display::Grid: case Display::InlineGrid: b->kind = BoxKind::Grid; break;
        case Display::Table: case Display::InlineTable: b->kind = BoxKind::Table; break;
        case Display::TableRowGroup: case Display::TableHeaderGroup: case Display::TableFooterGroup: b->kind = BoxKind::RowGroup; break;
        case Display::TableRow: b->kind = BoxKind::Row; break;
        case Display::TableCell: b->kind = BoxKind::Cell; break;
        case Display::Inline: b->kind = BoxKind::Inline; break;
        default: b->kind = BoxKind::Block; break;
        }
        const bool inlineLevel = disp == Display::InlineBlock || disp == Display::InlineFlex || disp == Display::InlineGrid ||
                                 disp == Display::InlineTable;
        if (blockify) {
            if (b->kind == BoxKind::Inline) b->kind = BoxKind::Block;
            b->atomic = false;
        } else {
            b->atomic = inlineLevel;
        }
        // table parts outside tables behave as blocks
        if ((b->kind == BoxKind::RowGroup || b->kind == BoxKind::Row) && !(parent && (parent->kind == BoxKind::Table || parent->kind == BoxKind::RowGroup)))
            b->kind = BoxKind::Block;
        if (b->kind == BoxKind::Cell && !(parent && parent->kind == BoxKind::Row)) b->kind = BoxKind::Block;
        b->blockLevel = b->kind != BoxKind::Inline && !b->atomic;
        b->isButton = r->tag == Tag::Button;
        b->isListItem = disp == Display::ListItem;
        b->clips = (st->ovX != Overflow::Visible || st->ovY != Overflow::Visible) && b->kind != BoxKind::Inline &&
                   b->kind != BoxKind::Row && b->kind != BoxKind::RowGroup;
        b->scrollX = b->clips && (st->ovX == Overflow::Auto || st->ovX == Overflow::Scroll);
        if (b->outOfFlow) attachOutOfFlow(b);

        for (RNode* k : r->kids) {
            if (k->isText) {
                b->kids.push_back(textBox(k, b));
                continue;
            }
            if (k->style && k->style->display == Display::Contents) {
                // children join this box directly
                for (RNode* kk : k->kids) {
                    if (kk->isText) b->kids.push_back(textBox(kk, b));
                    else if (Box* c = element(kk, b)) b->kids.push_back(c);
                }
                continue;
            }
            if (Box* c = element(k, b)) b->kids.push_back(c);
        }
        // inline containing block-level children → treat as a block (block-in-inline approximation)
        if (b->kind == BoxKind::Inline)
            for (Box* k : b->kids)
                if (!k->outOfFlow && k->blockLevel) {
                    b->kind = BoxKind::Block;
                    b->blockLevel = true;
                    break;
                }
        normalize(b);
        if (b->isListItem && st->listStyle != ListStyle::None) {
            int ordinal = 1;
            if (parent)
                for (Box* s : parent->kids) {
                    if (s == b) break;
                    if (s->isListItem) ++ordinal;
                }
            b->marker = chbd_marker_text(st->listStyle, ordinal);
            b->markerSymbol = st->listStyle == ListStyle::Disc ? 1 : st->listStyle == ListStyle::Circle ? 2
                              : st->listStyle == ListStyle::Square ? 3 : 0;
        }
        return b;
    }

    void normalize(Box* b) {
        switch (b->kind) {
        case BoxKind::Block: case BoxKind::Cell: normalizeBlock(b); break;
        case BoxKind::Flex: case BoxKind::Grid: normalizeFlexGrid(b); break;
        case BoxKind::Table: normalizeTable(b); break;
        case BoxKind::RowGroup: normalizeRowGroup(b); break;
        case BoxKind::Row: normalizeRow(b); break;
        default: break;
        }
    }

    void normalizeBlock(Box* b) {
        bool hasBlock = false;
        for (Box* k : b->kids)
            if (!k->outOfFlow && !chbd_inline_level(k)) { hasBlock = true; break; }
        if (!hasBlock) {
            b->inlineContent = true;
            return;
        }
        std::vector<Box*> out, run;
        auto flush = [&]() {
            if (run.empty()) return;
            bool meaningful = false;
            for (Box* k : run) {
                if (k->outOfFlow) continue;
                if (k->kind != BoxKind::Text || !chbd_ws_only(k->rawText) || b->st->preservesSpaces()) { meaningful = true; break; }
            }
            if (meaningful) {
                Box* a = anon(b, Display::Block, BoxKind::Block);
                a->inlineContent = true;
                for (Box* k : run) {
                    k->parent = a;
                    if (k->kind == BoxKind::Text) k->st = a->st;
                    a->kids.push_back(k);
                }
                out.push_back(a);
            } else {
                for (Box* k : run)
                    if (k->outOfFlow || k->kind != BoxKind::Text) out.push_back(k);
            }
            run.clear();
        };
        for (Box* k : b->kids) {
            if (k->outOfFlow || chbd_inline_level(k)) run.push_back(k);
            else {
                flush();
                out.push_back(k);
            }
        }
        flush();
        b->kids = out;
    }

    void normalizeFlexGrid(Box* b) {
        std::vector<Box*> out, run;
        auto flush = [&]() {
            if (run.empty()) return;
            bool meaningful = false;
            for (Box* k : run)
                if (k->kind != BoxKind::Text || !chbd_ws_only(k->rawText)) { meaningful = true; break; }
            if (meaningful) {
                Box* a = anon(b, Display::Block, BoxKind::Block);
                a->inlineContent = true;
                for (Box* k : run) {
                    k->parent = a;
                    if (k->kind == BoxKind::Text) k->st = a->st;
                    a->kids.push_back(k);
                }
                out.push_back(a);
            }
            run.clear();
        };
        for (Box* k : b->kids) {
            if (k->kind == BoxKind::Text || k->kind == BoxKind::Br) run.push_back(k);
            else {
                flush();
                out.push_back(k);
            }
        }
        flush();
        b->kids = out;
    }

    /// Wrap consecutive non-matching children into one anonymous row/cell.
    void wrapInto(Box* b, BoxKind keep, BoxKind wrapKind, Display wrapDisp) {
        std::vector<Box*> out, run;
        auto flush = [&]() {
            if (run.empty()) return;
            bool meaningful = false;
            for (Box* k : run)
                if (k->outOfFlow || k->kind != BoxKind::Text || !chbd_ws_only(k->rawText)) { meaningful = true; break; }
            if (meaningful) {
                Box* a = anon(b, wrapDisp, wrapKind);
                for (Box* k : run) {
                    k->parent = a;
                    if (k->kind == BoxKind::Text) k->st = a->st;
                    a->kids.push_back(k);
                }
                normalize(a);
                out.push_back(a);
            }
            run.clear();
        };
        for (Box* k : b->kids) {
            if (k->kind == keep || (keep == BoxKind::Row && k->kind == BoxKind::RowGroup && b->kind == BoxKind::Table) || k->outOfFlow) {
                flush();
                out.push_back(k);
            } else {
                run.push_back(k);
            }
        }
        flush();
        b->kids = out;
    }

    void normalizeTable(Box* b) { wrapInto(b, BoxKind::Row, BoxKind::Row, Display::TableRow); }
    void normalizeRowGroup(Box* b) { wrapInto(b, BoxKind::Row, BoxKind::Row, Display::TableRow); }
    void normalizeRow(Box* b) { wrapInto(b, BoxKind::Cell, BoxKind::Cell, Display::TableCell); }
};

} // namespace

void Document::Impl::build_boxes() {
    QElapsedTimer t;
    t.start();
    boxes.clear();
    anonStyles.clear();
    regions.clear();
    body = nullptr;
    ChbdBuilder bld{*this};
    if (rootNode && rr.rootIsBody) {
        body = bld.element(rootNode, nullptr);
    } else {
        body = new_box();
        body->st = &bodyStyle;
        body->kind = BoxKind::Block;
        body->anonymous = true;
        body->blockLevel = true;
        if (rootNode)
            if (Box* rb = bld.element(rootNode, body)) body->kids.push_back(rb);
        bld.normalize(body);
    }
    if (body) {
        body->kind = body->kind == BoxKind::Inline ? BoxKind::Block : body->kind;
        body->blockLevel = true;
        body->atomic = false;
        body->outOfFlow = false;
        body->bfcRoot = false;
    }
    for (Box& b : boxes) b.bfcRoot = lc_is_bfc_root(&b);
    if (body) body->bfcRoot = false; // html is the BFC root; body margins may collapse with children
    // canvas colour: body background propagates to the viewport (html has none)
    const ComputedStyle* bs = body ? body->st : &bodyStyle;
    canvas = bs && bs->bg.alpha() > 0 ? bs->bg : QColor(255, 255, 255);
    timing.boxMs = double(t.nsecsElapsed()) / 1e6;
    timing.boxes = int(boxes.size());
}

void Document::Impl::do_layout(float width) {
    QElapsedTimer t;
    t.start();
    laidOut = false;
    docW = width;
    docH = vpH;
    if (!body) {
        laidOut = true;
        return;
    }
    ++gen;
    LayoutCtx c;
    c.env.vw = vpW;
    c.env.vh = vpH;
    c.icbW = width;
    c.icbH = vpH;
    c.gen = gen;
    c.warnings = &warnings;
    for (Box& b : boxes) {
        b.positioned = false;
        b.absDone = false;
    }
    const BlockOut bo = lc_layout_block_level(c, body, width, -1);
    body->ref = nullptr;
    body->x = body->ml;
    body->y = bo.top.sum();
    body->ax = body->x;
    body->ay = body->y;
    body->positioned = true;
    lc_finalize(body);
    lc_absolute_pass(c, body);
    docH = std::max(vpH, std::round(body->ay + body->h + bo.bottom.sum()));
    chb_compute_overflow(*this);
    layoutWidth = width;
    laidOut = true;
    timing.layoutMs = double(t.nsecsElapsed()) / 1e6;
}

// ============================================================================================== sticky / scroll

QPointF Document::Impl::sticky_offset(const Box* b) const {
    if (!b->st || b->st->position != Position::Sticky) return {};
    const ComputedStyle& s = *b->st;
    // nearest scroll container (overflow hidden/auto/scroll; body/html propagate to the viewport)
    const Box* sc = nullptr;
    for (const Box* p = b->parent; p && p != body && p->parent; p = p->parent)
        if (p->clips && !p->isSvg && p->st &&
            ((p->st->ovX != Overflow::Visible && p->st->ovX != Overflow::Clip) ||
             (p->st->ovY != Overflow::Visible && p->st->ovY != Overflow::Clip))) {
            sc = p;
            break;
        }
    // scrollport in the scroller's unscrolled content coordinates (= layout coordinates)
    QRectF port(0, scrollY, vpW, vpH);
    if (sc) {
        port = QRectF(sc->ax + sc->bl, sc->ay + sc->bt, sc->w - sc->bl - sc->br, sc->h - sc->bt - sc->bb);
        if (sc->regionId >= 0 && sc->regionId < int(regions.size())) port.translate(regions[size_t(sc->regionId)].scrollX, 0);
    }
    // containing block: nearest non-inline ancestor's content box (the scroller's whole content when it is the CB)
    const Box* cb = b->parent;
    while (cb && cb->kind == BoxKind::Inline && !cb->atomic) cb = cb->parent;
    if (!cb) return {};
    QRectF lim(cb->ax + cb->bl + cb->pl, cb->ay + cb->bt + cb->pt, cb->contentW(), cb->contentH());
    if (cb == sc) {
        if (sc->scrollX) lim.setWidth(std::max(lim.width(), double(sc->scrollW - sc->pl - sc->pr)));
        for (const Box* k : cb->kids)
            if (!k->outOfFlow) lim = lim.united(QRectF(k->ax - k->ml, k->ay - k->mt, k->w + k->ml + k->mr, k->h + k->mt + k->mb));
    }
    const QRectF mbox(b->ax - b->ml, b->ay - b->mt, b->w + b->ml + b->mr, b->h + b->mt + b->mb);
    float dx = 0, dy = 0;
    if (s.top.kind == Len::Val) {
        const float want = float(port.top()) + lc_len(s.top, float(port.height())) - b->ay;
        if (want > 0) dy = std::max(0.0f, std::min(want, float(lim.bottom() - mbox.bottom())));
    } else if (s.bottom.kind == Len::Val) {
        const float want = float(port.bottom()) - lc_len(s.bottom, float(port.height())) - (b->ay + b->h);
        if (want < 0) dy = std::min(0.0f, std::max(want, float(lim.top() - mbox.top())));
    }
    if (s.left.kind == Len::Val) {
        const float want = float(port.left()) + lc_len(s.left, float(port.width())) - b->ax;
        if (want > 0) dx = std::max(0.0f, std::min(want, float(lim.right() - mbox.right())));
    } else if (s.right.kind == Len::Val) {
        const float want = float(port.right()) - lc_len(s.right, float(port.width())) - (b->ax + b->w);
        if (want < 0) dx = std::min(0.0f, std::max(want, float(lim.left() - mbox.left())));
    }
    return QPointF(dx, dy);
}

QPointF Document::Impl::box_shift(const Box* b) const {
    float dx = 0, dy = 0;
    for (const Box* p = b; p; p = p->parent) {
        if (p->st && p->st->position == Position::Sticky) {
            const QPointF so = sticky_offset(p);
            dx += float(so.x());
            dy += float(so.y());
        }
        if (p != b && p->regionId >= 0 && p->regionId < int(regions.size())) dx -= regions[size_t(p->regionId)].scrollX;
        if (p->outOfFlow && p->absDone) {
            // absolutely positioned boxes move with their containing block, not their DOM parent
            const Box* cb = nullptr;
            for (const Box* q = p->parent; q; q = q->parent)
                if (std::find(q->absKids.begin(), q->absKids.end(), p) != q->absKids.end()) { cb = q; break; }
            if (cb) {
                const QPointF s = box_shift(cb);
                // the containing block's own scroll offset (if it is the scroller) also applies
                if (cb->regionId >= 0 && cb->regionId < int(regions.size())) return QPointF(dx + s.x() - regions[size_t(cb->regionId)].scrollX, dy + s.y());
                return QPointF(dx + s.x(), dy + s.y());
            }
        }
    }
    return QPointF(dx, dy);
}

const Box* Document::Impl::region_box_of(const Box* b, int* regionId) const {
    for (const Box* p = b ? b->parent : nullptr; p; p = p->parent)
        if (p->regionId >= 0) {
            if (regionId) *regionId = p->regionId;
            return p;
        }
    if (regionId) *regionId = -1;
    return nullptr;
}

// ============================================================================================== Document

Document::Document() : d(std::make_unique<Impl>()) {}
Document::~Document() = default;

void Document::clear() {
    const auto tl = d->tabLoader;
    const auto il = d->incLoader;
    d = std::make_unique<Impl>();
    d->tabLoader = tl;
    d->incLoader = il;
}

bool Document::load_tree(const QByteArray& json, QString* err) {
    auto t = parse_tree(json, QStringLiteral("tree"));
    if (!t->ok) {
        if (err) *err = t->error;
        d->warnings << t->error;
        return false;
    }
    d->top = t;
    d->buildMode = false;
    d->state.add_scoped_keys(t->scopedKeys);
    for (const QString& w : t->warnings) d->warnings << w;
    d->resolveDirty = true;
    return true;
}

bool Document::load_tree(const JVal& tree, QString* err) {
    auto t = parse_tree_value(tree, QStringLiteral("tree"));
    if (!t->ok) {
        if (err) *err = t->error;
        d->warnings << t->error;
        return false;
    }
    d->top = t;
    d->buildMode = false;
    d->state.add_scoped_keys(t->scopedKeys);
    d->resolveDirty = true;
    return true;
}

bool Document::load_tree(const QJsonObject& tree, QString* err) { return load_tree(json_from_qt(tree), err); }

bool Document::set_shell(const QByteArray& json, QString* err) {
    auto t = parse_tree(json, QStringLiteral("shell"));
    if (!t->ok) {
        if (err) *err = t->error;
        d->warnings << t->error;
        return false;
    }
    d->top = t;
    d->buildMode = true;
    d->state.add_scoped_keys(t->scopedKeys);
    for (const QString& w : t->warnings) d->warnings << w;
    d->resolveDirty = true;
    return true;
}

void Document::set_tab_tree(const QString& tabId, const QByteArray& json) {
    auto t = parse_tree(json, QStringLiteral("tab_%1").arg(tabId));
    if (!t->ok) d->warnings << t->error;
    d->tabs.insert(tabId, t);
    d->resolveDirty = true;
}

void Document::set_tab_loader(std::function<QByteArray(const QString&)> loader) {
    d->tabLoader = std::move(loader);
    d->resolveDirty = true;
}

void Document::set_inc_tree(const QString& key, const QByteArray& json) {
    auto t = parse_tree(json, QStringLiteral("inc/%1").arg(key));
    if (!t->ok) d->warnings << t->error;
    d->incs.insert(key, t);
    d->resolveDirty = true;
}

void Document::set_inc_tree(const QString& key, const JVal& tree) {
    auto t = parse_tree_value(tree, QStringLiteral("inc/%1").arg(key));
    if (!t->ok) d->warnings << t->error;
    d->incs.insert(key, t);
    d->resolveDirty = true;
}

void Document::set_inc_loader(std::function<QByteArray(const QString&)> loader) {
    d->incLoader = std::move(loader);
    d->resolveDirty = true;
}

void Document::set_defaults(const QHash<QString, QString>& defaults) { d->state.set_defaults(defaults); }
QHash<QString, QString> Document::defaults() const { return d->state.defaults(); }

void Document::reset_state() {
    d->state.reset_to_defaults();
    d->resolveDirty = true;
}

void Document::set_state(const QString& key, const QString& value) {
    if (d->state.has(key) && d->state.get(key) == value) return;
    d->state.set(key, value);
    d->resolveDirty = true;
}

void Document::merge_state(const QHash<QString, QString>& kv) {
    d->state.merge(kv);
    d->resolveDirty = true;
}

void Document::remove_state(const QString& key) {
    d->state.remove(key);
    d->resolveDirty = true;
}

QString Document::get_state(const QString& key) const { return d->state.get(key); }
QHash<QString, QString> Document::state() const { return d->state.values(); }
QStringList Document::scoped_keys() const { return QStringList(d->state.scoped_keys().begin(), d->state.scoped_keys().end()); }

void Document::set_viewport(float width, float height) {
    if (width == d->vpW && height == d->vpH) return;
    d->vpW = width;
    d->vpH = height;
    d->styleDirty = true;
    d->laidOut = false;
}

void Document::resolve() { d->do_resolve(); }

void Document::layout(float width) {
    bool rebuilt = false;
    if (d->resolveDirty) {
        d->do_resolve();
        rebuilt = true;
    }
    if (d->styleDirty || rebuilt || !d->body) {
        d->do_style();
        d->build_boxes();
        rebuilt = true;
    }
    if (rebuilt || !d->laidOut || width != d->layoutWidth) d->do_layout(width);
}

bool Document::is_laid_out() const { return d->laidOut; }
float Document::content_width() const { return d->docW; }
float Document::content_height() const { return d->docH; }
QColor Document::canvas_color() const { return d->canvas; }

void Document::paint(QPainter& p, const QRectF& clipDoc) {
    if (!d->laidOut) return;
    chb_paint_document(*d, p, clipDoc);
}

void Document::set_scroll_y(float y) { d->scrollY = std::max(0.0f, y); }
float Document::scroll_y() const { return d->scrollY; }

std::vector<ScrollRegion> Document::scroll_regions() const {
    std::vector<ScrollRegion> out;
    for (size_t i = 0; i < d->regions.size(); ++i) {
        const Box* b = d->regions[i].box;
        ScrollRegion r;
        r.id = int(i);
        r.rect = QRectF(b->ax + b->bl, b->ay + b->bt, b->w - b->bl - b->br, b->h - b->bt - b->bb);
        r.clientWidth = float(r.rect.width());
        r.scrollWidth = std::max(r.clientWidth, b->scrollW);
        r.scrollX = d->regions[i].scrollX;
        for (const Box* p = b; p; p = p->parent)
            if (p->st && p->st->position == Position::Sticky) r.sticky = true;
        out.push_back(r);
    }
    return out;
}

void Document::set_scroll_x(int regionId, float x) {
    if (regionId < 0 || regionId >= int(d->regions.size())) return;
    Impl::Region& r = d->regions[size_t(regionId)];
    const Box* b = r.box;
    const float client = b->w - b->bl - b->br;
    r.scrollX = std::clamp(x, 0.0f, std::max(0.0f, b->scrollW - client));
    if (b->node) d->regionScrollMemo.insert(QString::number(b->node->order), r.scrollX);
}

float Document::scroll_x(int regionId) const {
    if (regionId < 0 || regionId >= int(d->regions.size())) return 0;
    return d->regions[size_t(regionId)].scrollX;
}

void Document::normalize_hscroll() {
    for (size_t i = 0; i < d->regions.size(); ++i) {
        const Box* c = d->regions[i].box;
        const Box* active = nullptr;
        // first descendant (document order) whose on.set matches the state
        std::vector<const Box*> stack{c};
        std::vector<const Box*> order;
        while (!stack.empty()) {
            const Box* b = stack.back();
            stack.pop_back();
            if (b != c) order.push_back(b);
            for (size_t k = b->kids.size(); k-- > 0;) stack.push_back(b->kids[k]);
        }
        std::stable_sort(order.begin(), order.end(), [](const Box* a, const Box* b) {
            const int oa = a->node ? a->node->order : 0, ob = b->node ? b->node->order : 0;
            return oa < ob;
        });
        for (const Box* b : order) {
            if (!b->node || !b->node->src || !b->node->src->hasOnSet) continue;
            bool ok = true;
            for (const auto& kv : b->node->src->onSet)
                if (d->state.value_of(kv.first) != kv.second) { ok = false; break; }
            if (ok) { active = b; break; }
        }
        float x = 0;
        if (active) {
            const float client = c->w - c->bl - c->br;
            float right = active->ax + active->w;
            if (active->kind == BoxKind::Inline && !active->atomic) right = active->ax; // inline boxes: approximate
            right -= c->ax;
            x = std::max(0.0f, std::ceil(right - client));
        }
        set_scroll_x(int(i), x);
    }
}

bool Document::activate(const Action& a) {
    const auto before = d->state.values();
    std::vector<ActionStep> steps = a.steps;
    if (steps.empty() && (a.type == Action::Set || a.type == Action::Sort || a.type == Action::SetAndSort)) {
        ActionStep st;
        st.set = a.set;
        st.sort = a.type != Action::Set;
        st.sortKey = a.sortKey;
        st.sortDir = a.sortDir;
        st.sortCol = a.sortCol;
        steps.push_back(st);
    }
    for (const ActionStep& st : steps) {
        SrcNode tmp;
        tmp.hasOnSet = !st.set.empty();
        tmp.onSet = st.set;
        tmp.hasOnSort = st.sort;
        tmp.onSortKey = st.sortKey;
        tmp.onSortDir = st.sortDir;
        tmp.onSortCol = st.sortCol;
        d->state.apply_on(tmp);
    }
    const bool changed = d->state.values() != before;
    if (changed) d->resolveDirty = true;
    return changed;
}

bool Document::click_key(const QString& key) {
    if (d->resolveDirty) d->do_resolve();
    if (!d->rootNode) return false;
    // first element in document order carrying data-key == key (the oracle sets data-key on built elements)
    const RNode* target = nullptr;
    std::vector<const RNode*> stack{d->rootNode};
    while (!stack.empty() && !target) {
        const RNode* r = stack.back();
        stack.pop_back();
        if (r->isText) continue;
        const bool built = r->src && (r->src->knownHtml || r->inSvg || (r == d->rootNode && d->rr.rootIsBody));
        if (built && r->src->hasKey && r->src->key == key) { target = r; break; }
        if (r->src && !r->src->knownHtml && !r->inSvg && !(r == d->rootNode && d->rr.rootIsBody)) continue; // "[t lạ]": children not built
        for (size_t i = r->kids.size(); i-- > 0;) stack.push_back(r->kids[i]);
    }
    if (!target) return false;
    for (const RNode* q = target; q; q = q->parent)
        if (q->src && (q->src->hasOnSet || q->src->hasOnSort)) d->state.apply_on(*q->src);
    d->resolveDirty = true;
    return true;
}

bool Document::choose_option(const Action& a, const QString& value) {
    if (a.type != Action::Select || a.bindKey.isEmpty()) return false;
    if (d->state.has(a.bindKey) && d->state.get(a.bindKey) == value) return false;
    d->state.set(a.bindKey, value);
    d->resolveDirty = true;
    return true;
}

QStringList Document::warnings() const {
    QStringList w = d->warnings;
    w += d->rr.warnings;
    w.removeDuplicates();
    return w;
}

Timing Document::last_timing() const { return d->timing; }

} // namespace fincept::screens::chb
