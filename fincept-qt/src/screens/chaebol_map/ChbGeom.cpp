// ChbGeom.cpp — geometry dump (same format as the Chrome oracle's ChbOracle.dump()), plain text, hit testing.
#include "screens/chaebol_map/ChbDom_p.h"
#include "screens/chaebol_map/ChbSvg.h"

#include <cmath>

namespace fincept::screens::chb {

namespace {

double chbgm_r2(double v) { return std::round(v * 100.0) / 100.0; }

QString chbgm_num(double v) {
    v = chbgm_r2(v);
    if (v == 0) return QStringLiteral("0");
    return js_number_string(v);
}

void chbgm_json_str(QString& out, const QString& s) {
    out += QLatin1Char('"');
    for (const QChar c : s) {
        switch (c.unicode()) {
        case '"': out += QLatin1String("\\\""); break;
        case '\\': out += QLatin1String("\\\\"); break;
        case '\n': out += QLatin1String("\\n"); break;
        case '\r': out += QLatin1String("\\r"); break;
        case '\t': out += QLatin1String("\\t"); break;
        default:
            if (c.unicode() < 0x20) out += QStringLiteral("\\u%1").arg(int(c.unicode()), 4, 16, QLatin1Char('0'));
            else out += c;
        }
    }
    out += QLatin1Char('"');
}

/// Formatting root (IFC owner) of an inline-level box.
const Box* chbgm_ifc_root(const Box* b) {
    for (const Box* p = b ? b->parent : nullptr; p; p = p->parent)
        if (p->ifc && p->inlineContent) return p;
    return nullptr;
}

/// Sum of relative offsets of non-atomic inline ancestors of `b` below `root`.
QPointF chbgm_inline_rel(const Box* b, const Box* root) {
    QPointF o;
    for (const Box* p = b; p && p != root; p = p->parent)
        if (p->kind == BoxKind::Inline && !p->atomic) o += QPointF(p->relX, p->relY);
    return o;
}

/// Offset (sticky + scroll) applying to the CONTENT of `root` (its fragments).
QPointF chbgm_content_shift(const Document::Impl& d, const Box* root) {
    QPointF s = d.box_shift(root);
    if (root->regionId >= 0 && root->regionId < int(d.regions.size())) s.rx() -= d.regions[size_t(root->regionId)].scrollX;
    if (root->st && root->st->position == Position::Sticky) {} // included by box_shift
    return s;
}

const RNode* chbgm_svg_root(const RNode* r) {
    for (const RNode* p = r; p; p = p->parent)
        if (p->tag == Tag::Svg && p->box) return p;
    return nullptr;
}

QRectF chbgm_svg_content(const Box* b) {
    return QRectF(b->ax + b->bl + b->pl, b->ay + b->bt + b->pt, b->contentW(), b->contentH());
}

struct ChbgmDump {
    const Document::Impl& d;
    QString nodes, texts;
    bool firstNode = true, firstText = true;

    QRectF elementRect(const RNode* r) const {
        const Box* b = r->box;
        if (!b) {
            if (r->inSvg && r->tag != Tag::Svg) {
                const RNode* svgR = chbgm_svg_root(r);
                if (svgR && svgR->box) {
                    const QRectF c = chbgm_svg_content(svgR->box).translated(d.box_shift(svgR->box));
                    return svg::node_bbox(svgR, c, r);
                }
            }
            return QRectF();
        }
        if (b->kind == BoxKind::Inline || b->kind == BoxKind::Br) {
            const Box* root = chbgm_ifc_root(b);
            if (!root || !root->ifc) return QRectF();
            const QPointF sh = chbgm_content_shift(d, root) + chbgm_inline_rel(b->parent, root) + QPointF(b->relX, b->relY);
            QRectF u;
            bool any = false;
            for (const InlineFrag& f : root->ifc->frags) {
                if (f.box != b || f.type != InlineFrag::InlineBox) continue;
                const QRectF r2(root->ax + f.x, root->ay + f.top, f.w, f.height);
                u = any ? u.united(r2) : r2;
                any = true;
            }
            return any ? u.translated(sh) : QRectF();
        }
        QPointF sh = d.box_shift(b);
        const Box* root = b->atomic ? chbgm_ifc_root(b) : nullptr;
        if (root) sh += chbgm_inline_rel(b->parent, root) - (b->parent == root ? QPointF() : QPointF());
        return QRectF(b->ax, b->ay, b->w, b->h).translated(sh);
    }

    void textRects(const RNode* t, QString& out) const {
        const Box* b = t->box;
        bool first = true;
        auto add = [&](const QRectF& r) {
            if (r.width() <= 0.009) return;
            if (!first) out += QLatin1Char(',');
            first = false;
            out += QLatin1Char('[') + chbgm_num(r.x()) + QLatin1Char(',') + chbgm_num(r.y()) + QLatin1Char(',') +
                   chbgm_num(r.width()) + QLatin1Char(',') + chbgm_num(r.height()) + QLatin1Char(']');
        };
        if (!b) {
            if (t->inSvg) {
                const RNode* svgR = chbgm_svg_root(t->parent);
                if (svgR && svgR->box) {
                    const QRectF c = chbgm_svg_content(svgR->box).translated(d.box_shift(svgR->box));
                    for (const QRectF& r : svg::text_rects(svgR, c, t)) add(r);
                }
            }
            return;
        }
        const Box* root = chbgm_ifc_root(b);
        if (!root || !root->ifc) return;
        const QPointF sh = chbgm_content_shift(d, root) + chbgm_inline_rel(b->parent, root);
        for (const InlineFrag& f : root->ifc->frags)
            if (f.box == b && f.type == InlineFrag::Text) {
                if (f.fullW > 0) add(QRectF(root->ax + f.x, root->ay + f.top, f.fullW, f.height).translated(sh)); // text-overflow: untruncated first
                add(QRectF(root->ax + f.x, root->ay + f.top, f.w, f.height).translated(sh));
            }
    }

    void walk(const RNode* r, const QString& path) {
        if (r->isText) {
            if (!firstText) texts += QLatin1Char(',');
            firstText = false;
            texts += QLatin1String("{\"p\":\"") + path + QLatin1String("\",\"text\":");
            chbgm_json_str(texts, r->text);
            texts += QLatin1String(",\"rects\":[");
            textRects(r, texts);
            texts += QLatin1String("]}");
            return;
        }
        const QRectF rc = elementRect(r);
        if (!firstNode) nodes += QLatin1Char(',');
        firstNode = false;
        QString tag = r->src ? r->src->tagName : QStringLiteral("span");
        if (r->src && !r->inSvg && !r->src->knownHtml && !(r == d.rootNode && d.rr.rootIsBody)) tag = QStringLiteral("span");
        if (r == d.rootNode && d.rr.rootIsBody) tag = QStringLiteral("body");
        nodes += QLatin1String("{\"p\":\"") + path + QLatin1String("\",\"t\":");
        chbgm_json_str(nodes, tag);
        nodes += QLatin1String(",\"key\":");
        if (r->src && r->src->hasKey && (r->src->knownHtml || r->inSvg || (r == d.rootNode && d.rr.rootIsBody))) chbgm_json_str(nodes, r->src->key);
        else nodes += QLatin1String("null");
        nodes += QLatin1String(",\"x\":") + chbgm_num(rc.x()) + QLatin1String(",\"y\":") + chbgm_num(rc.y()) +
                 QLatin1String(",\"w\":") + chbgm_num(rc.width()) + QLatin1String(",\"h\":") + chbgm_num(rc.height()) +
                 QLatin1Char('}');
        for (size_t i = 0; i < r->kids.size(); ++i) walk(r->kids[i], path + QLatin1Char('.') + QString::number(i));
    }
};

// ---- hit testing
struct ChbgmHit {
    const Document::Impl& d;
    QPointF pt;

    const Box* hit(const Box* b, QPointF p) const {
        if (b->kind == BoxKind::Text || b->kind == BoxKind::Br) return nullptr;
        if (b->st && b->st->position == Position::Sticky) p -= d.sticky_offset(b);
        const QRectF r(b->ax, b->ay, b->w, b->h);
        const bool inside = b->kind == BoxKind::Inline ? inlineContains(b, p) : r.contains(p);
        if (b->clips && !inside && b->absKids.empty()) return nullptr;
        QPointF cp = p;
        if (b->regionId >= 0 && b->regionId < int(d.regions.size())) cp.rx() += d.regions[size_t(b->regionId)].scrollX;
        for (auto it = b->kids.rbegin(); it != b->kids.rend(); ++it) {
            const Box* k = *it;
            if (b->clips && !inside && !k->outOfFlow) continue;
            if (const Box* h = hit(k, k->outOfFlow ? p : cp)) return h;
        }
        if (inside && b->node && b->st && b->st->visibility == Visibility::Visible) return b;
        return nullptr;
    }

    bool inlineContains(const Box* b, const QPointF& p) const {
        const Box* root = chbgm_ifc_root(b);
        if (!root || !root->ifc) return false;
        const QPointF sh = QPointF(root->regionId >= 0 ? -d.regions[size_t(root->regionId)].scrollX : 0.0f, 0);
        for (const InlineFrag& f : root->ifc->frags)
            if (f.box == b && f.type == InlineFrag::InlineBox && QRectF(root->ax + f.x, root->ay + f.top, f.w, f.height).translated(sh).contains(p))
                return true;
        return false;
    }
};

} // namespace

QString Document::dump_geometry_json() const {
    ChbgmDump dm{*d, {}, {}};
    if (d->rootNode) dm.walk(d->rootNode, QStringLiteral("0"));
    QString out;
    out.reserve(dm.nodes.size() + dm.texts.size() + 64);
    out += QLatin1String("{\"width\":") + QString::number(int(std::lround(d->docW))) + QLatin1String(",\"height\":") +
           QString::number(int(std::lround(d->docH))) + QLatin1String(",\"nodes\":[") + dm.nodes +
           QLatin1String("],\"texts\":[") + dm.texts + QLatin1String("]}");
    return out;
}

QString Document::plain_text() const {
    QString out;
    std::vector<const Box*> stack;
    if (d->body) stack.push_back(d->body);
    while (!stack.empty()) {
        const Box* b = stack.back();
        stack.pop_back();
        if (b->ifc && b->inlineContent) {
            const InlineLayout& L = *b->ifc;
            for (const LineBox& l : L.lines) {
                QString line;
                for (int fi = l.fragBegin; fi < l.fragEnd; ++fi) {
                    const InlineFrag& f = L.frags[size_t(fi)];
                    if (f.type == InlineFrag::Text && f.shape) line += f.shape->text.mid(f.from, f.to - f.from);
                    else if (f.type == InlineFrag::Ellipsis) line += QChar(0x2026);
                }
                if (!line.trimmed().isEmpty()) out += line + QLatin1Char('\n');
            }
        }
        for (auto it = b->kids.rbegin(); it != b->kids.rend(); ++it)
            if ((*it)->kind != BoxKind::Text) stack.push_back(*it);
    }
    return out;
}

Action Document::hit_test(QPointF docPoint) const {
    Action a;
    if (!d->body || !d->laidOut) return a;
    ChbgmHit h{*d, docPoint};
    const Box* b = h.hit(d->body, docPoint);
    if (!b) return a;
    for (const RNode* r = b->node; r; r = r->parent) {
        const SrcNode* s = r->src;
        if (!s) continue;
        const Box* tb = r->box ? r->box : b;
        auto finish = [&]() {
            a.rect = QRectF(tb->ax, tb->ay, tb->w, tb->h);
            int rid = -1;
            d->region_box_of(tb, &rid);
            a.region = rid;
            a.pointer = true;
        };
        if (s->hasOnSet || s->hasOnSort) {
            a.type = s->hasOnSet && s->hasOnSort ? Action::SetAndSort : (s->hasOnSet ? Action::Set : Action::Sort);
            a.set = s->onSet;
            a.sortKey = s->onSortKey;
            a.sortDir = s->onSortDir;
            a.sortCol = s->onSortCol;
            // bubbling: this handler, then every ancestor's
            for (const RNode* q = r; q; q = q->parent) {
                const SrcNode* qs = q->src;
                if (!qs || !(qs->hasOnSet || qs->hasOnSort)) continue;
                ActionStep st;
                st.set = qs->onSet;
                st.sort = qs->hasOnSort;
                st.sortKey = qs->onSortKey;
                st.sortDir = qs->onSortDir;
                st.sortCol = qs->onSortCol;
                a.steps.push_back(st);
            }
            finish();
            return a;
        }
        if (r->tag == Tag::Select && !s->bind.isEmpty()) {
            a.type = Action::Select;
            a.bindKey = s->bind;
            for (const RNode* o : r->kids) {
                if (o->isText || o->tag != Tag::Option) continue;
                QString l;
                for (const RNode* t : o->kids)
                    if (t->isText) l += t->text;
                const QString* v = o->src ? o->src->attr(u"value") : nullptr;
                a.optionValues << (v ? *v : l.simplified());
                a.optionLabels << l.simplified();
            }
            a.current = d->state.get(s->bind);
            finish();
            return a;
        }
        if (r->tag == Tag::A && s->hasHref) {
            const QString href = s->href.trimmed();
            if (href.startsWith(QLatin1String("http://"), Qt::CaseInsensitive) || href.startsWith(QLatin1String("https://"), Qt::CaseInsensitive)) {
                a.type = Action::Href;
                a.href = href;
                finish();
                return a;
            }
        }
    }
    a.pointer = b->st && b->st->cursorPointer;
    return a;
}

} // namespace fincept::screens::chb
