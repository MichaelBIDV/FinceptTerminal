// ChbLayoutInlineBreak.cpp — paragraph of an inline formatting context (white-space processing, text-transform,
// inline items, shaping) and its line-break opportunities: UAX #14, Chrome's ASCII pair table, the end of every
// space run, break-all. Line building is in ChbLayoutInline.cpp.
#include "screens/chaebol_map/ChbAsciiBreak_p.h"
#include "screens/chaebol_map/ChbLayout_p.h"

#include <QTextBoundaryFinder>

namespace fincept::screens::chb {

namespace {

constexpr QChar kObj = QChar(0xFFFC);

QString chbi_transform(const QString& t, TextTransform tt, bool* atWordStart) {
    switch (tt) {
    case TextTransform::Uppercase: return t.toUpper();
    case TextTransform::Lowercase: return t.toLower();
    case TextTransform::Capitalize: {
        QString o = t;
        for (int i = 0; i < o.size(); ++i) {
            if (o[i].isSpace()) { *atWordStart = true; continue; }
            if (*atWordStart && o[i].isLetterOrNumber()) o[i] = o[i].toUpper();
            *atWordStart = false;
        }
        return o;
    }
    default: return t;
    }
}

bool chbi_collapsible(const ComputedStyle& s) {
    return s.whiteSpace == WhiteSpace::Normal || s.whiteSpace == WhiteSpace::NoWrap || s.whiteSpace == WhiteSpace::PreLine;
}

struct ChbiBuilder {
    InlineLayout* L;
    bool lastSpace = true;  // paragraph start behaves like after a collapsible space
    bool capWordStart = true;
    int column = 0;

    void addText(Box* t, Box* inl) {
        const ComputedStyle& s = *t->st;
        const bool coll = chbi_collapsible(s);
        const bool keepNl = s.preservesNewlines();
        QString out;
        out.reserve(t->rawText.size());
        for (int i = 0; i < t->rawText.size(); ++i) {
            QChar ch = t->rawText[i];
            if (ch == u'\r') continue;
            if (ch == u'\n') {
                if (keepNl) {
                    if (coll)
                        while (!out.isEmpty() && out.back() == u' ') out.chop(1);
                    out += QLatin1Char('\n');
                    lastSpace = coll;
                    column = 0;
                    continue;
                }
                ch = u' ';
            }
            if (ch == u'\t') {
                if (coll) ch = u' ';
                else {
                    const int n = 8 - (column % 8);
                    out += QString(n, u' ');
                    column += n;
                    lastSpace = false;
                    continue;
                }
            }
            if (ch == u' ' || ch == u'\f') {
                if (coll) {
                    if (lastSpace) continue;
                    lastSpace = true;
                } else {
                    lastSpace = false;
                }
                out += u' ';
                ++column;
                continue;
            }
            out += ch;
            ++column;
            lastSpace = false;
        }
        out = chbi_transform(out, s.textTransform, &capWordStart);
        InlineItem it;
        it.type = InlineItem::Text;
        it.box = t;
        it.parentInline = inl;
        it.st = &s;
        it.start = int(L->para.size());
        L->para += out;
        it.end = int(L->para.size());
        it.fe = &chbi_font(s);
        it.collapsible = coll;
        it.canWrap = s.canWrap();
        it.breakAll = s.wordBreak == WordBreak::BreakAll;
        it.anywhere = s.overflowWrap != OverflowWrap::Normal || s.wordBreak == WordBreak::BreakWord;
        QString shaped = out;
        shaped.replace(QLatin1Char('\n'), QLatin1Char(' '));
        it.shape = &shape_text(*it.fe, shaped, s.letterSpacing);
        L->items.push_back(it);
    }

    void walk(Box* parent, Box* inl) {
        for (Box* k : parent->kids) {
            if (k->outOfFlow) {
                L->absAt.emplace_back(k, int(L->para.size()));
                continue;
            }
            if (k->kind == BoxKind::Text) {
                addText(k, inl);
                continue;
            }
            if (k->kind == BoxKind::Br) {
                InlineItem it;
                it.type = InlineItem::Break;
                it.box = k;
                it.parentInline = inl;
                it.st = k->st;
                it.fe = &chbi_font(*k->st);
                it.start = int(L->para.size());
                L->para += QLatin1Char('\n');
                it.end = it.start + 1;
                L->items.push_back(it);
                lastSpace = true;
                column = 0;
                continue;
            }
            if (k->kind == BoxKind::Inline && !k->atomic) {
                InlineItem o;
                o.type = InlineItem::Open;
                o.box = k;
                o.parentInline = inl;
                o.st = k->st;
                o.fe = &chbi_font(*k->st);
                o.start = o.end = int(L->para.size());
                L->items.push_back(o);
                walk(k, k);
                InlineItem cl = o;
                cl.type = InlineItem::Close;
                cl.start = cl.end = int(L->para.size());
                L->items.push_back(cl);
                continue;
            }
            InlineItem it;
            it.type = InlineItem::Atomic;
            it.box = k;
            it.parentInline = inl;
            it.st = k->st;
            it.start = int(L->para.size());
            L->para += kObj;
            it.end = it.start + 1;
            L->items.push_back(it);
            lastSpace = false;
            ++column;
        }
    }
};

} // namespace

void lc_inline_prepare(LayoutCtx& c, Box* b) {
    Q_UNUSED(c);
    if (b->ifc && b->ifc->prepared) return;
    b->ifc = std::make_unique<InlineLayout>();
    InlineLayout* L = b->ifc.get();
    ChbiBuilder bl{L};
    bl.walk(b, nullptr);
    const int n = int(L->para.size());
    L->posItem.assign(size_t(n), -1);
    for (size_t i = 0; i < L->items.size(); ++i)
        for (int p = L->items[i].start; p < L->items[i].end; ++p) L->posItem[size_t(p)] = int(i);
    for (const InlineItem& it : L->items) {
        if (it.type == InlineItem::Atomic || it.type == InlineItem::Break) L->hasContent = true;
        else if (it.type == InlineItem::Text) {
            for (int i = it.start; i < it.end; ++i)
                if (L->para[i] != u' ' || !it.collapsible) { L->hasContent = true; break; }
        } else if (it.type == InlineItem::Open) {
            const ComputedStyle& s = *it.st;
            if (s.usedBorder(1) + s.usedBorder(3) > 0 || s.padding[1].px + s.padding[3].px + s.padding[1].pct + s.padding[3].pct > 0 ||
                s.margin[1].px + s.margin[3].px != 0)
                L->hasContent = true;
        }
    }
    L->breakOk.assign(size_t(n) + 1, 0);
    if (n > 0) {
        std::vector<char> cand(size_t(n) + 1, 0); // UAX #14 opportunities: 1 soft, 2 mandatory
        QTextBoundaryFinder f(QTextBoundaryFinder::Line, L->para);
        for (qsizetype p = f.toNextBoundary(); p >= 0 && p <= n; p = f.toNextBoundary()) {
            if (p == 0) continue;
            const bool mandatory = (f.boundaryReasons() & QTextBoundaryFinder::MandatoryBreak) || L->para[p - 1] == u'\n';
            cand[size_t(p)] = mandatory ? 2 : 1;
        }
        // Chrome: between two printable ASCII characters Blink's own pair table replaces UAX #14
        for (int p = 1; p < n; ++p) {
            const char16_t a = L->para[p - 1].unicode(), c = L->para[p].unicode();
            if (cand[size_t(p)] != 2 && chb_is_ascii_graphic(a) && chb_is_ascii_graphic(c))
                cand[size_t(p)] = chb_ascii_break(p >= 2 ? L->para[p - 2].unicode() : u'\0', a, c) ? 1 : 0;
        }
        // Blink (LazyLineBreakIterator, BreakSpaceType::kAfterSpaceRun): the end of every space run is a break
        // opportunity, even before characters UAX #14 LB13 keeps attached ("claims20 / claims54" breaks before "/").
        for (int p = 1; p < n; ++p) {
            const QChar a = L->para[p - 1], c = L->para[p];
            if (!cand[size_t(p)] && (a == u' ' || a == u'\t') && c != u' ' && c != u'\t' && c != u'\n') cand[size_t(p)] = 1;
        }
        for (int p = 1; p <= n; ++p) {
            if (!cand[size_t(p)]) continue;
            if (cand[size_t(p)] == 2) {
                L->breakOk[size_t(p)] = 2;
                continue;
            }
            bool wrap = true;
            if (const InlineItem* it = chbi_item_at(*L, int(p) - 1)) {
                if (it->type == InlineItem::Atomic) wrap = (it->parentInline ? it->parentInline : b)->st->canWrap();
                else wrap = it->canWrap;
            }
            if (wrap && p < n)
                if (const InlineItem* nx = chbi_item_at(*L, int(p)); nx && nx->type == InlineItem::Atomic)
                    wrap = (nx->parentInline ? nx->parentInline : b)->st->canWrap();
            if (wrap) L->breakOk[size_t(p)] = 1;
        }
        L->breakOk[size_t(n)] = std::max(L->breakOk[size_t(n)], 1);
        for (const InlineItem& it : L->items) {
            if (it.type != InlineItem::Text || !it.breakAll || !it.canWrap) continue;
            const auto& gs = it.shape->graphemeStart;
            for (int i = it.start + 1; i < it.end; ++i)
                if (gs[size_t(i - it.start)] && L->para[i - 1] != u' ' && L->breakOk[size_t(i)] == 0) L->breakOk[size_t(i)] = 1;
        }
    }
    L->prepared = true;
    if (qEnvironmentVariableIsSet("CHB_DEBUG_IFC")) {
        QString ops;
        for (int p = 0; p <= n; ++p)
            if (L->breakOk[size_t(p)]) ops += QStringLiteral(" %1%2").arg(p).arg(L->breakOk[size_t(p)] == 2 ? QStringLiteral("!") : QString());
        qDebug("[ifc] para=%s | breaks:%s", qUtf8Printable(QString(L->para).replace(QLatin1Char('\n'), QStringLiteral("⏎"))), qUtf8Printable(ops));
    }
}

} // namespace fincept::screens::chb
