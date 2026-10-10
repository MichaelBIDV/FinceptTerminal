// ChbLayoutInline.cpp — inline formatting context: line breaking, inline boxes, atomic inlines, vertical alignment
// (half-leading, mixed fonts), text-align, ellipsis. The paragraph (white-space processing, items) and its line-break
// opportunities are built by lc_inline_prepare in ChbLayoutInlineBreak.cpp.
#include "screens/chaebol_map/ChbLayout_p.h"

#include <cmath>

namespace fincept::screens::chb {

const FontEntry& chbi_font(const ComputedStyle& s) {
    static const QStringList serif{QStringLiteral("serif")};
    return font_entry(s.fontFamily ? *s.fontFamily : serif, s.fontSize, s.fontWeight, s.fontStyle != FontStyle::Normal);
}

const InlineItem* chbi_item_at(const InlineLayout& L, int pos) {
    if (pos < 0 || pos >= int(L.posItem.size())) return nullptr;
    const int i = L.posItem[size_t(pos)];
    return i >= 0 ? &L.items[size_t(i)] : nullptr;
}

namespace {

constexpr float kEps = 1.0f / 128.0f;
/// Blink LineBreaker::AvailableWidthToFit(): a line fits while its (LayoutUnit) width ≤ available + one LayoutUnit
/// (AddEpsilon) — "Tiêu dùng+Banking" 92.797 stays on one line in a 92.781 px cell. + 1/512 absorbs float error.
constexpr float kFitEps = 1.0f / 64.0f + 1.0f / 512.0f;

/// Layout bounds (A above / D below the baseline) of an inline box from its own font + line-height.
void chbi_bounds(const ComputedStyle& s, const FontEntry& fe, float* A, float* D) {
    const float asc = fe.m.asc, desc = fe.m.desc;
    float lh = s.lineHeightPx();
    if (lh < 0) lh = fe.m.normalLineHeight();
    else lh = std::floor(lh * 64.0f + 1e-3f) / 64.0f; // LayoutUnit truncation (ComputedLineHeightAsFixed): 11 × 1.7 → 18.6875
    // Blink CalculateLeadingSpace: ascent side = floor((line-height − font height) / 2) in whole px
    const float top = std::floor((lh - (asc + desc)) / 2.0f);
    *A = asc + top;
    *D = lh - *A;
}

float chbi_margin(const Len& m, float cw) { return m.isAuto() ? 0.0f : lc_len(m, cw); }

/// Start of the hanging/collapsed run (spaces, forced newline) immediately before `b`.
int chbi_trail_start(const InlineLayout& L, int a, int b) {
    int s = b;
    while (s > a) {
        const QChar ch = L.para[s - 1];
        if (ch == u'\n') { --s; continue; }
        if (ch != u' ') break;
        const InlineItem* it = chbi_item_at(L, s - 1);
        if (it && it->type == InlineItem::Text && !it->collapsible && it->st->whiteSpace == WhiteSpace::Pre) break;
        --s;
    }
    return s;
}

/// Chrome keeps inline sizes in LayoutUnits: the part of a text item on a line is as wide as its shaped width
/// rounded UP to 1/64 px (ShapeResult::SnappedWidth → LayoutUnit::FromFloatCeil), for line breaking, intrinsic
/// sizes and fragment positions alike (measured: every text rect of the suite ends ≤ 1/64 px after the float width).
float chbi_lu_ceil(float w) { return w > 0 ? std::ceil(w * 64.0f - 1e-3f) / 64.0f : w; }

/// Cumulative geometry of a paragraph for the current item edges / atomic widths.
struct ChbiMetrics {
    const InlineLayout* L = nullptr;
    std::vector<float> ax;   // atomic widths, cumulative by position, size n+1
    std::vector<float> O, C; // open / close edges at positions < p, size n+2
    float width(int a, int b) const {
        return text(a, b) + (ax[size_t(b)] - ax[size_t(a)]) + (O[size_t(b)] - O[size_t(a)]) + (C[size_t(b) + 1] - C[size_t(a) + 1]);
    }
    /// Σ over the text items overlapping [a, b) of the snapped width of their part inside it.
    float text(int a, int b) const {
        float w = 0;
        for (int p = a; p < b;) {
            const int i = L->posItem[size_t(p)];
            if (i < 0) { ++p; continue; }
            const InlineItem& it = L->items[size_t(i)];
            const int e = std::min(b, it.end);
            if (it.type == InlineItem::Text) w += chbi_lu_ceil(it.shape->width_of(p - it.start, e - it.start));
            p = std::max(e, p + 1);
        }
        return w;
    }
};

void chbi_metrics(const InlineLayout& L, ChbiMetrics* m) {
    const int n = int(L.para.size());
    m->L = &L;
    m->ax.assign(size_t(n) + 1, 0.0f);
    m->O.assign(size_t(n) + 2, 0.0f);
    m->C.assign(size_t(n) + 2, 0.0f);
    std::vector<float> openAt(size_t(n) + 1, 0.0f), closeAt(size_t(n) + 1, 0.0f);
    for (const InlineItem& it : L.items) {
        if (it.type == InlineItem::Open) openAt[size_t(it.start)] += it.edge;
        else if (it.type == InlineItem::Close) closeAt[size_t(it.start)] += it.edge;
    }
    for (int p = 0; p < n; ++p) {
        const InlineItem* it = chbi_item_at(L, p);
        m->ax[size_t(p) + 1] = m->ax[size_t(p)] + (it && it->type == InlineItem::Atomic ? it->edge : 0.0f);
    }
    for (int p = 0; p <= n; ++p) {
        m->O[size_t(p) + 1] = m->O[size_t(p)] + openAt[size_t(p)];
        m->C[size_t(p) + 1] = m->C[size_t(p)] + closeAt[size_t(p)];
    }
}

void chbi_resolve_edges(InlineLayout& L, float cw) {
    for (InlineItem& it : L.items) {
        const ComputedStyle& s = *it.st;
        if (it.type == InlineItem::Open) it.edge = chbi_margin(s.margin[3], cw) + s.usedBorder(3) + lc_len(s.padding[3], cw);
        else if (it.type == InlineItem::Close) it.edge = chbi_margin(s.margin[1], cw) + s.usedBorder(1) + lc_len(s.padding[1], cw);
    }
}

} // namespace

void lc_inline_intrinsic(LayoutCtx& c, Box* b, float* minW, float* maxW) {
    lc_inline_prepare(c, b);
    InlineLayout& L = *b->ifc;
    if (L.intrinsicGen == c.gen) {
        *minW = L.minW;
        *maxW = L.maxW;
        return;
    }
    chbi_resolve_edges(L, -1);
    const int n = int(L.para.size());
    float mx = 0, mn = 0;
    for (int pass = 0; pass < 2; ++pass) {
        const bool wantMax = pass == 1;
        for (InlineItem& it : L.items)
            if (it.type == InlineItem::Atomic) it.edge = wantMax ? lc_max_contribution(c, it.box) : lc_min_contribution(c, it.box);
        ChbiMetrics m;
        chbi_metrics(L, &m);
        int start = 0;
        for (int p = 1; p <= n; ++p) {
            const int ok = L.breakOk[size_t(p)];
            if (wantMax ? (ok == 2 || p == n) : ok > 0) {
                const float w = m.width(start, chbi_trail_start(L, start, p));
                if (wantMax) mx = std::max(mx, w);
                else mn = std::max(mn, w);
                start = p;
                while (start < n && L.para[start] == u' ' && chbi_item_at(L, start) && chbi_item_at(L, start)->collapsible) ++start;
            }
        }
        if (n == 0) {
            const float w = m.O[1] + m.C[1];
            mx = std::max(mx, w);
            mn = std::max(mn, w);
        }
    }
    L.minW = mn;
    L.maxW = std::max(mx, mn);
    L.intrinsicGen = c.gen;
    *minW = L.minW;
    *maxW = L.maxW;
}

namespace {

struct ChbiVBox {
    const Box* box = nullptr; // nullptr = root inline box
    int parent = -1;
    float A = 0, D = 0;        // layout bounds around its own baseline
    float shift = 0;           // own baseline relative to the root baseline (+ down)
    VAlign va = VAlign::Baseline;
    const FontEntry* fe = nullptr;
    const ComputedStyle* st = nullptr;
};

float chbi_valign_shift(const ChbiVBox& v, const ChbiVBox& par) {
    switch (v.va) {
    case VAlign::Middle: return -par.fe->xHeight / 2.0f - (v.D - v.A) / 2.0f;
    case VAlign::Sub: return par.st->fontSize / 5.0f + 1.0f;     // Blink: font-size / 5 + 1
    case VAlign::Super: return -(par.st->fontSize / 3.0f + 1.0f); // Blink: font-size / 3 + 1
    case VAlign::TextTop: return v.A - par.fe->m.asc;
    case VAlign::TextBottom: return par.fe->m.desc - v.D;
    case VAlign::Length: {
        float lh = v.st->lineHeightPx();
        if (lh < 0) lh = v.fe ? v.fe->m.normalLineHeight() : v.A + v.D;
        return -lc_len(v.st->valignLen, lh);
    }
    default: return 0;
    }
}

struct ChbiLineBuilder {
    LayoutCtx& c;
    Box* b;
    InlineLayout& L;
    const ChbiMetrics& m;
    float cw;
    const ComputedStyle& rs;
    const FontEntry& rfe;
    int n;
    float y = 0;
    int lineNo = 0;
    size_t cursor = 0;               // next item to consume
    std::vector<size_t> openItems;   // Open items whose box continues

    void build(int ls, int le) {
        const int te = chbi_trail_start(L, ls, le);
        LineBox line;
        line.fragBegin = int(L.frags.size());
        const float x0 = lineNo == 0 ? rs.textIndent : 0.0f;
        float x = x0;
        std::vector<ChbiVBox> vb(1);
        vb[0].st = &rs;
        vb[0].fe = &rfe;
        chbi_bounds(rs, rfe, &vb[0].A, &vb[0].D);
        std::vector<int> fragVb;
        std::vector<int> openVb;
        bool content = false;
        struct Hang { size_t item; int from, to; int owner; };
        std::vector<Hang> hangs;
        float tailW = 0; // preserved end-of-line spaces kept inside text fragments

        auto openFrag = [&](size_t itemIdx, bool leftEdge, float fx) {
            const InlineItem& it = L.items[itemIdx];
            InlineFrag f;
            f.type = InlineFrag::InlineBox;
            f.box = it.box;
            f.item = int(itemIdx);
            f.line = lineNo;
            f.leftEdge = leftEdge;
            f.x = fx;
            f.depth = int(openVb.size());
            ChbiVBox v;
            v.box = it.box;
            v.parent = openVb.empty() ? 0 : openVb.back();
            v.st = it.st;
            v.fe = it.fe;
            v.va = it.st->valign;
            chbi_bounds(*it.st, *it.fe, &v.A, &v.D);
            vb.push_back(v);
            L.frags.push_back(f);
            fragVb.push_back(int(vb.size()) - 1);
            openVb.push_back(int(vb.size()) - 1);
        };
        auto closeFrag = [&](const Box* box, float endX) {
            for (size_t fi = L.frags.size(); fi-- > size_t(line.fragBegin);)
                if (L.frags[fi].box == box && L.frags[fi].type == InlineFrag::InlineBox) {
                    L.frags[fi].w = std::max(0.0f, endX - L.frags[fi].x);
                    return &L.frags[fi];
                }
            return static_cast<InlineFrag*>(nullptr);
        };

        for (size_t oi : openItems) openFrag(oi, false, x); // boxes continuing from the previous line

        while (cursor < L.items.size()) {
            const InlineItem& it = L.items[cursor];
            if (it.type == InlineItem::Open) {
                if (it.start >= le && !(le == n && it.start == n)) break;
                openFrag(cursor, true, x + chbi_margin(it.st->margin[3], cw));
                openItems.push_back(cursor);
                x += it.edge;
                content = content || it.edge != 0;
                ++cursor;
                continue;
            }
            if (it.type == InlineItem::Close) {
                if (it.start > le) break;
                x += it.edge;
                if (InlineFrag* f = closeFrag(it.box, x - chbi_margin(it.st->margin[1], cw))) f->rightEdge = true;
                content = content || it.edge != 0;
                if (!openItems.empty()) openItems.pop_back();
                if (!openVb.empty()) openVb.pop_back();
                ++cursor;
                continue;
            }
            if (it.start >= le) break;
            const int owner = openVb.empty() ? 0 : openVb.back();
            if (it.type == InlineItem::Text) {
                int a = std::max(it.start, ls);
                const int e = std::min(it.end, te);
                auto pushText = [&](int from, int to) {
                    InlineFrag f;
                    f.type = InlineFrag::Text;
                    f.box = it.box;
                    f.item = int(cursor);
                    f.line = lineNo;
                    f.from = from - it.start;
                    f.to = to - it.start;
                    f.shape = it.shape;
                    f.x = x;
                    f.w = chbi_lu_ceil(it.shape->width_of(f.from, f.to));
                    x += f.w;
                    L.frags.push_back(f);
                    fragVb.push_back(owner);
                };
                // pre-wrap / break-spaces: preserved spaces opening a line are a fragment of their own (Chrome)
                const bool wrapPreserve = !it.collapsible && (it.st->whiteSpace == WhiteSpace::PreWrap ||
                                                              it.st->whiteSpace == WhiteSpace::BreakSpaces);
                if (wrapPreserve && a == ls && e > a && L.para[a] == u' ') {
                    int s2 = a;
                    while (s2 < e && L.para[s2] == u' ') ++s2;
                    if (s2 < e) {
                        pushText(a, s2);
                        content = true;
                        a = s2;
                    }
                }
                if (e > a) {
                    pushText(a, e);
                    for (int q = a; q < e; ++q)
                        if (L.para[q] != u' ' || !it.collapsible) { content = true; break; }
                    if (it.st->lhKind == LhKind::Normal && it.shape->multiFont) {
                        ChbiVBox& ov = vb[size_t(owner)];
                        it.shape->metrics_in_range(a - it.start, e - it.start, &ov.A, &ov.D);
                    }
                }
                // preserved spaces before a soft wrap hang (Chrome keeps them as their own fragment); before a
                // forced break or at the paragraph end they stay in the text fragment
                const bool softWrap = le < int(L.para.size()) && L.para[le - 1] != u'\n';
                if (!it.collapsible && te < le && !softWrap) {
                    const int to = std::min(it.end, le);
                    int he = to;
                    while (he > te && L.para[he - 1] == u'\n') --he;
                    if (he > std::max(it.start, te)) {
                        InlineFrag* lastF = L.frags.empty() ? nullptr : &L.frags.back();
                        const float x1 = x;
                        if (lastF && lastF->type == InlineFrag::Text && lastF->item == int(cursor) && lastF->line == lineNo &&
                            lastF->to == te - it.start) {
                            lastF->to = he - it.start;
                            const float w2 = chbi_lu_ceil(it.shape->width_of(lastF->from, lastF->to));
                            x += w2 - lastF->w;
                            lastF->w = w2;
                        } else {
                            pushText(std::max(it.start, te), he);
                        }
                        tailW += x - x1; // hangs: not part of the line width used for alignment
                    }
                } else if (!it.collapsible && te < le) {
                    int hs = std::max(it.start, te), he = std::min(it.end, le);
                    while (he > hs && L.para[he - 1] == u'\n') --he;
                    if (he > hs) hangs.push_back({cursor, hs - it.start, he - it.start, owner});
                }
                if (it.end > le) break; // continues on the next line
                ++cursor;
                continue;
            }
            if (it.type == InlineItem::Atomic) {
                Box* a = it.box;
                InlineFrag f;
                f.type = InlineFrag::Atomic;
                f.box = a;
                f.item = int(cursor);
                f.line = lineNo;
                f.x = x + a->ml;
                f.w = a->w;
                x += it.edge;
                L.frags.push_back(f);
                ChbiVBox v;
                v.box = a;
                v.parent = owner;
                v.st = a->st;
                v.fe = &chbi_font(*a->st);
                v.va = a->st->valign;
                const float mh = a->mt + a->h + a->mb;
                const float bl = lc_inline_block_baseline(a);
                v.A = std::isnan(bl) ? mh : a->mt + bl;
                v.D = mh - v.A;
                vb.push_back(v);
                fragVb.push_back(int(vb.size()) - 1);
                content = true;
                ++cursor;
                continue;
            }
            if (it.type == InlineItem::Break) {
                InlineFrag f;
                f.type = InlineFrag::InlineBox;
                f.box = it.box;
                f.item = int(cursor);
                f.line = lineNo;
                f.x = x;
                f.leftEdge = f.rightEdge = true;
                L.frags.push_back(f);
                ChbiVBox v;
                v.box = it.box;
                v.parent = owner;
                v.st = it.st;
                v.fe = it.fe;
                chbi_bounds(*it.st, *it.fe, &v.A, &v.D);
                vb.push_back(v);
                fragVb.push_back(int(vb.size()) - 1);
                content = true;
                ++cursor;
                continue;
            }
            ++cursor;
        }
        for (size_t oi : openItems) closeFrag(L.items[oi].box, x); // continue on the next line
        // A preserved newline (pre / pre-wrap / pre-line) is a forced break that always creates a line box, even on an
        // otherwise empty line (Blink LineBreaker::HandleControlItem: should_create_line_box) → blank lines keep
        // their line-height instead of collapsing to a phantom line.
        if (!content && le > ls && L.para[le - 1] == u'\n')
            if (const InlineItem* nl = chbi_item_at(L, le - 1); nl && nl->type == InlineItem::Text) content = true;
        const float lineW = x - x0 - tailW;
        for (const Hang& h : hangs) {
            const InlineItem& it = L.items[h.item];
            InlineFrag f;
            f.type = InlineFrag::Text;
            f.box = it.box;
            f.item = int(h.item);
            f.line = lineNo;
            f.from = h.from;
            f.to = h.to;
            f.shape = it.shape;
            f.x = x;
            f.w = chbi_lu_ceil(it.shape->width_of(f.from, f.to));
            f.hanging = true;
            x += f.w;
            L.frags.push_back(f);
            fragVb.push_back(h.owner);
        }
        line.fragEnd = int(L.frags.size());

        // ---- vertical alignment
        float topMost = 0, bottomMost = 0;
        bool first = true;
        for (size_t i = 0; i < vb.size(); ++i) {
            ChbiVBox& v = vb[i];
            if (i > 0) v.shift = vb[size_t(v.parent)].shift + chbi_valign_shift(v, vb[size_t(v.parent)]);
            if (v.va == VAlign::Top || v.va == VAlign::Bottom) continue;
            const float t = v.shift - v.A, bo = v.shift + v.D;
            if (first) { topMost = t; bottomMost = bo; first = false; }
            else { topMost = std::min(topMost, t); bottomMost = std::max(bottomMost, bo); }
        }
        for (size_t i = 1; i < vb.size(); ++i) {
            ChbiVBox& v = vb[i];
            const float hgt = v.A + v.D;
            if (v.va == VAlign::Top) {
                if (hgt > bottomMost - topMost) bottomMost = topMost + hgt;
                v.shift = topMost + v.A;
            } else if (v.va == VAlign::Bottom) {
                if (hgt > bottomMost - topMost) topMost = bottomMost - hgt;
                v.shift = bottomMost - v.D;
            }
        }
        const float lineH = content ? bottomMost - topMost : 0.0f; // phantom lines have no height
        line.top = y;
        line.height = lineH;
        line.baseline = y + (content ? -topMost : 0.0f);
        line.width = lineW;

        // ---- text-align (overflowing lines align to start)
        const float space = cw - lineW;
        float off = 0;
        switch (rs.textAlign) {
        case TextAlign::Right: case TextAlign::End: off = std::max(0.0f, space); break;
        case TextAlign::Center: case TextAlign::WebkitCenter: off = std::max(0.0f, space / 2.0f); break;
        default: off = 0; break;
        }
        const float left = b->contentX() + off;
        line.left = left + x0;

        // ---- text-overflow: ellipsis
        if (rs.ellipsis && rs.ovX != Overflow::Visible && lineW > cw + kEps) ellipsize(line, x0, fragVb);

        // ---- place fragments
        for (int fi = line.fragBegin; fi < line.fragEnd; ++fi) {
            InlineFrag& f = L.frags[size_t(fi)];
            const ChbiVBox& v = vb[size_t(fragVb[size_t(fi - line.fragBegin)])];
            f.x += left;
            const float base = line.baseline + v.shift;
            f.baseline = base;
            switch (f.type) {
            case InlineFrag::Text:
            case InlineFrag::Ellipsis: {
                const FontEntry* fe = f.type == InlineFrag::Ellipsis ? &rfe : L.items[size_t(f.item)].fe;
                f.top = base - fe->m.asc;
                f.height = fe->m.asc + fe->m.desc;
                break;
            }
            case InlineFrag::InlineBox: {
                const InlineItem& it = L.items[size_t(f.item)];
                if (it.type == InlineItem::Break) {
                    f.top = base - it.fe->m.asc;
                    f.height = it.fe->m.asc + it.fe->m.desc;
                } else {
                    const ComputedStyle& s = *it.st;
                    const float pt = lc_len(s.padding[0], cw), pb = lc_len(s.padding[2], cw);
                    f.top = base - it.fe->m.asc - pt - s.usedBorder(0);
                    f.height = it.fe->m.asc + it.fe->m.desc + pt + pb + s.usedBorder(0) + s.usedBorder(2);
                }
                break;
            }
            case InlineFrag::Atomic: {
                Box* a = f.box;
                a->ref = b;
                a->x = f.x;
                a->y = base - v.A + a->mt;
                f.top = a->y;
                f.height = a->h;
                break;
            }
            }
        }
        L.lines.push_back(line);
        y += lineH;
        ++lineNo;
    }

    void ellipsize(LineBox& line, float x0, std::vector<int>& fragVb) {
        const ShapedText& ell = shape_text(rfe, QString(QChar(0x2026)), rs.letterSpacing);
        const float ellW = chbi_lu_ceil(ell.width);
        const float limit = cw - ellW;
        int keep = line.fragBegin;
        float ex = x0;
        for (int fi = line.fragBegin; fi < line.fragEnd; ++fi) {
            InlineFrag& f = L.frags[size_t(fi)];
            if (f.type == InlineFrag::InlineBox) { keep = fi + 1; continue; }
            if (f.x + f.w <= limit + kEps) { keep = fi + 1; ex = f.x + f.w; continue; }
            if (f.type == InlineFrag::Text) {
                int cut = f.from;
                for (int q = f.from + 1; q <= f.to; ++q) {
                    if (q < f.to && !f.shape->graphemeStart[size_t(q)]) continue;
                    if (f.x + chbi_lu_ceil(f.shape->width_of(f.from, q)) <= limit + kEps) cut = q;
                    else break;
                }
                if (cut > f.from) {
                    f.fullW = f.w;
                    f.to = cut;
                    f.w = chbi_lu_ceil(f.shape->width_of(f.from, f.to));
                    keep = fi + 1;
                    ex = f.x + f.w;
                }
            }
            break;
        }
        for (int fi = keep; fi < line.fragEnd; ++fi) {
            InlineFrag& f = L.frags[size_t(fi)];
            if (f.type == InlineFrag::InlineBox) { f.w = std::max(0.0f, std::min(f.w, ex - f.x)); continue; }
            if (f.type == InlineFrag::Text && f.fullW == 0) f.fullW = f.w;
            f.w = 0;
            f.to = f.from;
            if (f.type == InlineFrag::Atomic) f.x = -1.0e6f; // hidden
        }
        InlineFrag e;
        e.type = InlineFrag::Ellipsis;
        e.line = line.fragBegin >= 0 ? L.frags.empty() ? 0 : L.frags[size_t(line.fragBegin)].line : 0;
        e.x = ex;
        e.w = ellW;
        e.shape = &ell;
        e.from = 0;
        e.to = 1;
        L.frags.push_back(e);
        fragVb.push_back(0);
        line.fragEnd = int(L.frags.size());
    }
};

} // namespace

float lc_inline(LayoutCtx& c, Box* b, float cw) {
    lc_inline_prepare(c, b);
    InlineLayout& L = *b->ifc;
    L.lines.clear();
    L.frags.clear();
    const int n = int(L.para.size());
    chbi_resolve_edges(L, cw);
    // atomic inlines at shrink-to-fit width
    for (InlineItem& it : L.items) {
        if (it.type != InlineItem::Atomic) continue;
        Box* a = it.box;
        lc_edges(a, cw);
        if (a->kind == BoxKind::Table) {
            lc_table(c, a, cw - a->ml - a->mr, -1, b->definiteH);
        } else if (a->kind == BoxKind::Replaced) {
            float rw = 0, rh = 0;
            lc_replaced_size(c, a, cw, b->definiteH, &rw, &rh);
            a->w = rw;
            a->h = rh;
        } else {
            float w = lc_spec_width(c, a, cw);
            if (w < 0) w = lc_shrink_to_fit(c, a, cw - a->ml - a->mr);
            w = lc_clamp_w(c, a, w, cw);
            lc_layout_sized(c, a, w, -1, cw, b->definiteH);
        }
        it.edge = a->ml + a->w + a->mr;
    }
    ChbiMetrics m;
    chbi_metrics(L, &m);
    const ComputedStyle& rs = *b->st;
    ChbiLineBuilder lb{c, b, L, m, cw, rs, chbi_font(rs), n, 0.0f, 0, 0, {}};
    lb.y = b->contentY();

    if (n == 0) {
        bool any = false;
        for (const InlineItem& it : L.items) any = any || it.type == InlineItem::Open;
        if (any) lb.build(0, 0);
    } else {
        int pos = 0;
        while (pos < n) {
            const float avail = cw - (lb.lineNo == 0 ? rs.textIndent : 0.0f);
            int best = -1, firstOpp = -1;
            for (int p = pos + 1; p <= n; ++p) {
                const int ok = L.breakOk[size_t(p)];
                if (!ok) continue;
                if (firstOpp < 0) firstOpp = p;
                const float w = m.width(pos, chbi_trail_start(L, pos, p));
                if (w <= avail + kFitEps || best < 0) {
                    best = p;
                    if (ok == 2 || w > avail + kFitEps) break;
                } else {
                    break;
                }
            }
            if (best < 0) best = n;
            // emergency break inside an overflowing first segment (overflow-wrap: break-word/anywhere)
            if (best == firstOpp && m.width(pos, chbi_trail_start(L, pos, best)) > avail + kFitEps) {
                const InlineItem* it = chbi_item_at(L, pos);
                if (it && it->type == InlineItem::Text && it->anywhere && it->canWrap) {
                    int cut = -1;
                    for (int q = pos + 1; q < best && q < it->end; ++q) {
                        if (!it->shape->graphemeStart[size_t(q - it->start)]) continue;
                        if (m.width(pos, q) <= avail + kFitEps) cut = q;
                        else break;
                    }
                    best = cut > pos ? cut : std::min(best, pos + 1);
                }
            }
            lb.build(pos, best);
            pos = best;
            while (pos < n && L.para[pos] == u' ') { // leading collapsible spaces of the next line
                const InlineItem* it = chbi_item_at(L, pos);
                if (!it || !it->collapsible) break;
                ++pos;
            }
        }
        // closes of inline boxes ending exactly at the paragraph end were consumed by the last line;
        // a paragraph ending in collapsed spaces may leave Close items: attach them to the last line.
        if (lb.cursor < L.items.size() && !L.lines.empty()) {
            for (; lb.cursor < L.items.size(); ++lb.cursor) {
                const InlineItem& it = L.items[lb.cursor];
                if (it.type != InlineItem::Close) continue;
                for (size_t fi = L.frags.size(); fi-- > 0;)
                    if (L.frags[fi].box == it.box && L.frags[fi].type == InlineFrag::InlineBox) {
                        L.frags[fi].rightEdge = true;
                        break;
                    }
            }
        }
    }
    for (const LineBox& l : L.lines)
        if (l.height > 0) {
            if (std::isnan(b->firstBaseline)) b->firstBaseline = l.baseline;
            b->lastBaseline = l.baseline;
        }
    // static positions of absolutely positioned children
    for (const auto& e : L.absAt) {
        Box* a = e.first;
        a->staticParent = b;
        a->staticX = b->contentX();
        a->staticY = b->contentY();
        bool found = false;
        for (const LineBox& l : L.lines) {
            a->staticY = l.top;
            a->staticX = l.left;
            for (int fi = l.fragBegin; fi < l.fragEnd && !found; ++fi) {
                const InlineFrag& f = L.frags[size_t(fi)];
                if (f.item < 0) continue;
                const InlineItem& it = L.items[size_t(f.item)];
                if (it.start + (f.type == InlineFrag::Text ? f.from : 0) >= e.second) {
                    a->staticX = f.x;
                    found = true;
                }
            }
            if (found) break;
        }
    }
    L.height = lb.y - b->contentY();
    if (qEnvironmentVariableIsSet("CHB_DEBUG_IFC"))
        for (size_t li = 0; li < L.lines.size(); ++li) {
            const LineBox& l = L.lines[li];
            QString fr;
            for (int fi = l.fragBegin; fi < l.fragEnd; ++fi) {
                const InlineFrag& f = L.frags[size_t(fi)];
                fr += QStringLiteral(" [t%1 %2-%3 x%4 w%5]").arg(int(f.type)).arg(f.from).arg(f.to).arg(double(f.x)).arg(double(f.w));
            }
            qDebug("[ifc]  line %d top %.2f h %.2f base %.2f:%s", int(li), double(l.top), double(l.height), double(l.baseline), qUtf8Printable(fr));
        }
    return L.height;
}

} // namespace fincept::screens::chb
