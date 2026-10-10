// ChbState.cpp — tree parsing, state store, resolve (see ChbState.h).
#include "screens/chaebol_map/ChbState.h"

#include <QCollator>
#include <QHash>
#include <QLocale>

#include <algorithm>
#include <cmath>

namespace fincept::screens::chb {

// ============================================================================================== parse

namespace {

/// Tags the oracle builds as real HTML elements (render.js HTML_TAGS minus body).
bool chbst_oracle_html(Tag t) {
    switch (t) {
    case Tag::Div: case Tag::Span: case Tag::Section: case Tag::Header: case Tag::Nav: case Tag::Main:
    case Tag::Footer: case Tag::H1: case Tag::H2: case Tag::H3: case Tag::H4: case Tag::P: case Tag::Ul:
    case Tag::Ol: case Tag::Li: case Tag::Table: case Tag::Thead: case Tag::Tbody: case Tag::Tfoot: case Tag::Tr:
    case Tag::Th: case Tag::Td: case Tag::Button: case Tag::Select: case Tag::Option: case Tag::Strong: case Tag::B:
    case Tag::Em: case Tag::I: case Tag::Code: case Tag::Pre: case Tag::Br: case Tag::A: case Tag::Small:
    case Tag::Sup: case Tag::Sub: case Tag::Label: case Tag::Svg:
        return true;
    default: return false;
    }
}

struct ChbstParse {
    SrcTree* tree = nullptr;
    const JVal* cls = nullptr;
    QHash<QString, DeclListPtr> clsCache;
    QSet<QString> scoped;

    DeclListPtr klass(const QString& name) {
        auto it = clsCache.find(name);
        if (it != clsCache.end()) return it.value();
        const JVal* d = cls ? cls->get(name) : nullptr;
        DeclListPtr p;
        if (d && d->isObj()) p = parse_style_dict(*d);
        else tree->warnings << QStringLiteral("class thiếu: %1").arg(name);
        clsCache.insert(name, p);
        return p;
    }
    void addClasses(const JVal* c, std::vector<DeclListPtr>& out) {
        if (!c) return;
        auto one = [&](const JVal& v) {
            if (v.isNull()) return;
            if (DeclListPtr p = klass(v.toJsString())) out.push_back(p);
        };
        if (c->isArr())
            for (const JVal& v : c->items()) one(v);
        else
            one(*c);
    }
    static SrcCond cond(const JVal& v) {
        SrcCond c;
        for (const auto& kv : v.members()) {
            QStringList wants;
            if (kv.second.isArr())
                for (const JVal& w : kv.second.items()) wants << w.toJsString();
            else
                wants << kv.second.toJsString();
            c.terms.emplace_back(kv.first, wants);
        }
        return c;
    }
    void flatten(const JVal& k, std::vector<const JVal*>& out) {
        if (k.isArr()) {
            for (const JVal& x : k.items()) {
                if (x.isArr()) flatten(x, out);
                else out.push_back(&x);
            }
        } else {
            out.push_back(&k);
        }
    }
    /// Returns false for null/bool children (skipped like React).
    bool node(const JVal& v, SrcNode* n) {
        if (v.isStr() || v.isNum()) {
            n->isText = true;
            n->text = v.toJsString();
            return true;
        }
        if (!v.isObj()) return false;
        if (const JVal* t = v.get(u"t"); t && !t->isNull()) {
            n->hasTag = true;
            n->tagName = t->toJsString();
        } else {
            n->tagName = QStringLiteral("?");
        }
        n->tag = tag_from_name(n->tagName);
        n->knownHtml = chbst_oracle_html(n->tag);
        addClasses(v.get(u"c"), n->decls);
        if (const JVal* s = v.get(u"s"); s && s->isObj()) n->decls.push_back(parse_style_dict(*s));
        if (const JVal* va = v.get(u"var"); va && va->isArr()) {
            for (const JVal& e : va->items()) {
                if (!e.isObj()) continue;
                SrcVar sv;
                if (const JVal* ci = e.get(u"if"); ci && ci->isObj()) sv.cond = cond(*ci);
                addClasses(e.get(u"c"), sv.decls);
                if (const JVal* s = e.get(u"s"); s && s->isObj()) sv.decls.push_back(parse_style_dict(*s));
                n->vars.push_back(std::move(sv));
            }
        }
        if (const JVal* ci = v.get(u"if"); ci && ci->isObj()) {
            n->hasCond = true;
            n->cond = cond(*ci);
        }
        if (const JVal* k = v.get(u"key"); k && !k->isNull()) {
            n->hasKey = true;
            n->key = k->toJsString();
        }
        if (const JVal* inc = v.get(u"inc"); inc && !inc->isNull()) {
            n->hasInc = true;
            n->inc = inc->toJsString();
        }
        if (const JVal* id = v.get(u"id"); id && !id->isNull()) n->slotId = id->toJsString();
        if (n->slotId.isEmpty()) n->slotId = QStringLiteral("main");
        if (const JVal* sc = v.get(u"scope"); sc && sc->isArr())
            for (const JVal& k : sc->items()) {
                n->scope << k.toJsString();
                scoped.insert(k.toJsString());
            }
        if (const JVal* g = v.get(u"grp"); g && !g->isNull()) {
            n->hasGrp = true;
            n->grp = g->toJsString();
        }
        if (const JVal* c = v.get(u"count"); c && c->isObj()) {
            n->hasCount = true;
            if (const JVal* g = c->get(u"grp")) n->countGrp = g->toJsString();
            const JVal* f = c->get(u"fmt");
            n->countFmt = (f && !f->isNull()) ? f->toJsString() : QStringLiteral("{n}");
        }
        if (const JVal* so = v.get(u"sort"); so && so->isObj()) {
            n->hasSort = true;
            if (const JVal* k = so->get(u"key")) n->sortKey = k->toJsString();
            if (const JVal* d = so->get(u"dir")) n->sortDir = d->toJsString();
        }
        if (const JVal* sk = v.get(u"sk"); sk && sk->isObj()) n->sk = *sk;
        if (const JVal* b = v.get(u"bind"); b && !b->isNull()) n->bind = b->toJsString();
        if (const JVal* on = v.get(u"on"); on && on->isObj()) {
            if (const JVal* set = on->get(u"set"); set && set->isObj()) {
                n->hasOnSet = true;
                for (const auto& kv : set->members())
                    n->onSet.emplace_back(kv.first, kv.second.isNull() ? QString() : kv.second.toJsString());
            }
            if (const JVal* so = on->get(u"sort"); so && so->isObj()) {
                n->hasOnSort = true;
                if (const JVal* k = so->get(u"key")) n->onSortKey = k->toJsString();
                if (const JVal* d = so->get(u"dir")) n->onSortDir = d->toJsString();
                if (const JVal* c = so->get(u"col")) n->onSortCol = c->toJsString();
            }
        }
        if (const JVal* h = v.get(u"href"); h && h->isStr()) {
            n->hasHref = true;
            n->href = h->s;
        }
        if (const JVal* a = v.get(u"a"); a && a->isObj()) {
            for (const auto& kv : a->members()) {
                const JVal& x = kv.second;
                if (x.isNull() || (x.isBool() && !x.b)) continue;
                n->attrs.emplace_back(kv.first, x.isBool() ? QString() : x.toJsString());
                if (kv.first == QLatin1String("href") && !n->hasHref) {
                    n->hasHref = true;
                    n->href = x.toJsString();
                }
            }
        }
        if (const JVal* k = v.get(u"k")) {
            std::vector<const JVal*> flat;
            flatten(*k, flat);
            n->kids.reserve(flat.size());
            for (const JVal* c : flat) {
                SrcNode child;
                if (node(*c, &child)) n->kids.push_back(std::move(child));
            }
        }
        return true;
    }
};

} // namespace

std::shared_ptr<SrcTree> parse_tree_value(const JVal& obj, const QString& name) {
    auto t = std::make_shared<SrcTree>();
    t->name = name;
    if (!obj.isObj()) {
        t->error = QStringLiteral("%1: không phải đối tượng JSON {cls, root}").arg(name);
        return t;
    }
    const JVal* root = obj.get(u"root");
    if (!root) {
        t->error = QStringLiteral("%1: thiếu khoá \"root\"").arg(name);
        return t;
    }
    ChbstParse ps;
    ps.tree = t.get();
    ps.cls = obj.get(u"cls");
    if (!ps.node(*root, &t->root)) {
        t->error = QStringLiteral("%1: \"root\" không phải nút hợp lệ").arg(name);
        return t;
    }
    t->scopedKeys = QStringList(ps.scoped.begin(), ps.scoped.end());
    t->ok = true;
    return t;
}

std::shared_ptr<SrcTree> parse_tree(const QByteArray& json, const QString& name) {
    JVal v;
    QString err;
    if (!json_parse(json, &v, &err)) {
        auto t = std::make_shared<SrcTree>();
        t->name = name;
        t->error = QStringLiteral("%1: %2").arg(name, err);
        return t;
    }
    return parse_tree_value(v, name);
}

// ============================================================================================== state

QString StateStore::value_of(const QString& compoundKey) const {
    if (!compoundKey.contains(QLatin1Char('|'))) return values_.value(compoundKey);
    QStringList parts;
    for (const QString& k : compoundKey.split(QLatin1Char('|'))) parts << values_.value(k);
    return parts.join(QLatin1Char('|'));
}

bool StateStore::matches(const SrcCond& c) const {
    for (const auto& term : c.terms) {
        const QString have = value_of(term.first);
        if (!term.second.contains(have)) return false;
    }
    return true;
}

void StateStore::add_scoped_keys(const QStringList& keys) {
    for (const QString& k : keys) scoped_.insert(k);
}

bool StateStore::reset_unrendered_scopes(const QSet<QString>& rendered) {
    bool changed = false;
    for (const QString& k : scoped_) {
        if (rendered.contains(k)) continue;
        if (defaults_.contains(k)) {
            if (values_.value(k) != defaults_.value(k) || !values_.contains(k)) changed = true;
            values_.insert(k, defaults_.value(k));
        } else if (values_.contains(k)) {
            values_.remove(k);
            changed = true;
        }
    }
    return changed;
}

void StateStore::apply_on(const SrcNode& n) {
    if (n.hasOnSet)
        for (const auto& kv : n.onSet) values_.insert(kv.first, kv.second);
    if (n.hasOnSort) {
        if (values_.value(n.onSortKey) == n.onSortCol && values_.contains(n.onSortKey)) {
            values_.insert(n.onSortDir, values_.value(n.onSortDir) == QLatin1String("desc") ? QStringLiteral("asc")
                                                                                            : QStringLiteral("desc"));
        } else {
            values_.insert(n.onSortKey, n.onSortCol);
            values_.insert(n.onSortDir, QStringLiteral("desc"));
        }
    }
}

double js_to_number(const JVal& v) {
    switch (v.type) {
    case JVal::Null: return 0;
    case JVal::Num: return v.n;
    case JVal::Bool: return v.b ? 1 : 0;
    case JVal::Str: {
        const QString s = v.s.trimmed();
        if (s.isEmpty()) return 0;
        bool ok = false;
        double d = s.toDouble(&ok);
        if (ok) return d;
        if (s.startsWith(QLatin1String("0x"), Qt::CaseInsensitive)) {
            const qlonglong h = s.mid(2).toLongLong(&ok, 16);
            if (ok) return double(h);
        }
        if (s == QLatin1String("Infinity") || s == QLatin1String("+Infinity")) return INFINITY;
        if (s == QLatin1String("-Infinity")) return -INFINITY;
        return NAN;
    }
    default: return NAN;
    }
}

// ============================================================================================== resolve

namespace {

struct ChbstResolve {
    const StateStore& state;
    const TreeLoader& loader;
    std::deque<RNode>& arena;
    ResolveResult& res;
    struct CountFix {
        RNode* node;
        QString grp, fmt;
    };
    std::vector<CountFix> counts;
    int depth = 0;
    std::shared_ptr<DeclList> unknownDecl;

    RNode* make() {
        arena.emplace_back();
        ++res.nodeCount;
        return &arena.back();
    }

    RNode* textNode(const QString& t) {
        RNode* r = make();
        r->isText = true;
        r->text = t;
        return r;
    }

    RNode* resolve(const SrcNode& n, const SrcNode* sortSrc, bool inSvg) {
        if (n.isText) {
            RNode* r = textNode(n.text);
            r->src = &n;
            r->sortSrc = sortSrc;
            r->inSvg = inSvg;
            return r;
        }
        if (n.hasCond && !state.matches(n.cond)) return nullptr;
        for (const QString& k : n.scope) res.renderedScopes.insert(k);
        if (n.hasGrp) res.grpCounts[n.grp] += 1;
        if (++depth > 256) {
            --depth;
            res.warnings << QStringLiteral("cây lồng quá sâu (vòng inc?)");
            return nullptr;
        }
        RNode* out = nullptr;
        if (n.hasInc) {
            const SrcTree* t = loader ? loader(QStringLiteral("inc"), n.inc) : nullptr;
            if (!t || !t->ok) res.warnings << QStringLiteral("inc thiếu: %1").arg(n.inc);
            else out = resolve(t->root, sortSrc, inSvg);
        } else if (n.hasTag && n.tag == Tag::Slot) {
            const SrcTree* t = loader ? loader(QStringLiteral("slot"), n.slotId) : nullptr;
            if (!t || !t->ok) res.warnings << QStringLiteral("slot trống: %1 (tab %2)").arg(n.slotId, state.get(QStringLiteral("tab")));
            else out = resolve(t->root, sortSrc, inSvg);
        } else if (n.hasCount && !n.hasTag) {
            out = textNode(QString());
            out->src = nullptr;
            out->sortSrc = sortSrc;
            counts.push_back({out, n.countGrp, n.countFmt});
        } else {
            out = element(n, sortSrc, inSvg);
        }
        --depth;
        return out;
    }

    RNode* element(const SrcNode& n, const SrcNode* sortSrc, bool inSvg) {
        RNode* r = make();
        r->src = &n;
        r->sortSrc = sortSrc;
        r->tag = n.tag;
        const bool svg = inSvg || n.tag == Tag::Svg;
        r->inSvg = svg;
        r->isLink = n.tag == Tag::A && n.hasHref;
        for (const auto& d : n.decls) r->decls.push_back(d.get());
        for (const SrcVar& v : n.vars) {
            if (!v.cond.empty() && !state.matches(v.cond)) continue;
            for (const auto& d : v.decls) r->decls.push_back(d.get());
        }
        if (n.hasCount) {
            RNode* t = textNode(QString());
            t->parent = r;
            r->kids.push_back(t);
            counts.push_back({t, n.countGrp, n.countFmt});
        } else {
            std::vector<std::pair<const SrcNode*, RNode*>> pairs;
            pairs.reserve(n.kids.size());
            for (const SrcNode& c : n.kids) {
                RNode* rr = resolve(c, &c, svg);
                if (rr) pairs.emplace_back(&c, rr);
            }
            if (n.hasSort) sortPairs(pairs, n);
            for (auto& p : pairs) {
                p.second->parent = r;
                r->kids.push_back(p.second);
            }
        }
        // Unknown HTML tag outside SVG → the oracle's "[t lạ: x]" label (children resolved for grp/scope only)
        if (!svg && !n.knownHtml && !(n.tag == Tag::Body && depth == 1)) {
            r->tag = Tag::Span;
            r->decls.clear();
            if (!unknownDecl) {
                unknownDecl = std::make_shared<DeclList>();
                JVal o;
                o.type = JVal::Obj;
                o.obj = std::make_shared<JObj>();
                JVal half;
                half.type = JVal::Str;
                half.s = QStringLiteral("0.5");
                o.obj->emplace_back(QStringLiteral("opacity"), half);
                *unknownDecl = *parse_style_dict(o);
            }
            r->decls.push_back(unknownDecl.get());
            r->kids.clear();
            RNode* t = textNode(QStringLiteral("[t lạ: %1]").arg(n.tagName));
            t->parent = r;
            r->kids.push_back(t);
            r->src = &n;
        }
        return r;
    }

    void sortPairs(std::vector<std::pair<const SrcNode*, RNode*>>& pairs, const SrcNode& n) {
        const QString col = state.get(n.sortKey);
        const double dir = state.get(n.sortDir) == QLatin1String("desc") ? -1.0 : 1.0;
        static QCollator coll = [] {
            QCollator c(QLocale(QStringLiteral("vi_VN")));
            c.setNumericMode(false);
            c.setCaseSensitivity(Qt::CaseSensitive);
            return c;
        }();
        auto keyOf = [&](const SrcNode* s) -> const JVal* { return s ? s->sk.get(col) : nullptr; };
        std::stable_sort(pairs.begin(), pairs.end(), [&](const auto& A, const auto& B) {
            const JVal* a = keyOf(A.first);
            const JVal* b = keyOf(B.first);
            double d = 0;
            if (a && b && a->isStr() && b->isStr()) {
                d = coll.compare(a->s, b->s);
            } else {
                static const JVal undef;
                d = js_to_number(a ? *a : undef) - js_to_number(b ? *b : undef);
            }
            if (std::isnan(d)) d = 0;
            return d * dir < 0;
        });
    }
};

} // namespace

ResolveResult resolve_tree(const SrcTree& top, const StateStore& state, const TreeLoader& loader,
                           std::deque<RNode>& arena) {
    ResolveResult res;
    arena.clear();
    if (!top.ok) {
        res.warnings << top.error;
        return res;
    }
    ChbstResolve rs{state, loader, arena, res, {}, 0, nullptr};
    res.root = rs.resolve(top.root, nullptr, false);
    res.rootIsBody = res.root && !res.root->isText && top.root.tag == Tag::Body && res.root->tag == Tag::Body;
    for (auto& c : rs.counts) {
        const int n = res.grpCounts.value(c.grp, 0);
        c.node->text = c.fmt.split(QStringLiteral("{n}")).join(QString::number(n));
    }
    // indices + document order
    int order = 0;
    std::vector<RNode*> stack;
    if (res.root) stack.push_back(res.root);
    while (!stack.empty()) {
        RNode* r = stack.back();
        stack.pop_back();
        r->order = order++;
        for (size_t i = r->kids.size(); i-- > 0;) {
            r->kids[i]->index = int(i);
            r->kids[i]->parent = r;
            stack.push_back(r->kids[i]);
        }
    }
    res.warnings.removeDuplicates();
    return res;
}

} // namespace fincept::screens::chb
