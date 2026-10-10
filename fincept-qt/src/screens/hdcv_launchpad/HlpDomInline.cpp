// src/screens/hdcv_launchpad/HlpDomInline.cpp
// Launchpad CSS engine — inline formatting context (CSS 2.1 §10.8 as LayoutNG does it): paragraph
// items, shaping runs across element boundaries, Blink's break opportunities, line breaking,
// line-clamp / text-overflow ellipsis, line boxes with half-leading, first/last baselines.
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

QString collapseWs(const QString& s) {
    QString out;
    out.reserve(s.size());
    bool sp = false;
    for (QChar c : s) {
        if (c == u' ' || c == u'\n' || c == u'\t' || c == u'\r' || c == u'\f') {
            if (!sp)
                out += u' ';
            sp = true;
        } else {
            out += c;
            sp = false;
        }
    }
    return out;
}

void buildIfcItems(IFC& f, Box* container, Box* b, bool& lastSpace) {
    for (Box* k : b->kids) {
        switch (k->kind) {
        case BK::Text: {
            k->container = container;
            QString s = collapseWs(k->node ? k->node->text.normalized(QString::NormalizationForm_C) : QString());
            if (k->node && k->node->text.isEmpty())
                s.clear();
            if (lastSpace && s.startsWith(u' '))
                s.remove(0, 1);
            if (s.isEmpty()) {
                k->text.clear();
                // still open/close so the (empty) span keeps its place
                IItem o;
                o.t = IItem::Open;
                o.box = k;
                o.start = o.end = int(f.para.size());
                f.items.push_back(o);
                o.t = IItem::Close;
                f.items.push_back(o);
                break;
            }
            if (k->cs->upper)
                s = s.toUpper();
            k->text = s;
            k->paraStart = int(f.para.size());
            IItem it;
            it.t = IItem::Text;
            it.box = k;
            it.start = int(f.para.size());
            it.end = it.start + int(s.size());
            it.wrap = k->cs->ws == WhiteSpace::Normal;
            // the text is also an inline box (its own font / line-height)
            IItem o;
            o.t = IItem::Open;
            o.box = k;
            o.start = o.end = it.start;
            f.items.push_back(o);
            f.items.push_back(it);
            o.t = IItem::Close;
            o.start = o.end = it.end;
            f.items.push_back(o);
            f.para += s;
            lastSpace = s.endsWith(u' ');
            break;
        }
        case BK::Br: {
            k->container = container;
            IItem it;
            it.t = IItem::Br;
            it.box = k;
            it.start = int(f.para.size());
            it.end = it.start + 1;
            f.items.push_back(it);
            f.para += u'\n';
            lastSpace = true;
            break;
        }
        case BK::Inline: {
            k->container = container;
            IItem o;
            o.t = IItem::Open;
            o.box = k;
            o.start = o.end = int(f.para.size());
            f.items.push_back(o);
            buildIfcItems(f, container, k, lastSpace);
            o.t = IItem::Close;
            o.start = o.end = int(f.para.size());
            f.items.push_back(o);
            break;
        }
        case BK::Atomic: {
            k->container = container;
            IItem it;
            it.t = IItem::Atomic;
            it.box = k;
            it.start = int(f.para.size());
            it.end = it.start + 1;
            it.wrap = b->cs->ws == WhiteSpace::Normal;
            f.items.push_back(it);
            f.para += kObj;
            lastSpace = false;
            break;
        }
        default:
            break;
        }
    }
}

void buildIfc(Box* b) {
    auto f = std::make_unique<IFC>();
    bool lastSpace = true;
    buildIfcItems(*f, b, b, lastSpace);
    const int n = int(f->para.size());
    f->itemAt.fill(-1, n);
    for (int i = 0; i < f->items.size(); ++i) {
        const IItem& it = f->items[i];
        if (it.t == IItem::Text || it.t == IItem::Atomic || it.t == IItem::Br)
            for (int p = it.start; p < it.end; ++p)
                f->itemAt[p] = i;
    }
    // LayoutNG shapes adjacent items that use the same font as ONE run (kerning crosses element and
    // text-node boundaries), so do the same.
    {
        int runStart = -1, runEnd = -1;
        FontKey runFont;
        QVector<Box*> runBoxes;
        auto close = [&]() {
            if (runBoxes.isEmpty())
                return;
            auto sh = detail::shape(runFont, f->para.mid(runStart, runEnd - runStart));
            for (Box* tb : runBoxes) {
                tb->shaped = sh;
                tb->shapedOff = tb->paraStart - runStart;
            }
            runBoxes.clear();
        };
        for (const IItem& it : f->items) {
            if (it.t == IItem::Open || it.t == IItem::Close)
                continue;
            if (it.t != IItem::Text) {
                close();
                continue;
            }
            const FontKey& fk = it.box->cs->font;
            if (!runBoxes.isEmpty() && fk == runFont && it.start == runEnd) {
                runBoxes.push_back(it.box);
                runEnd = it.end;
                continue;
            }
            close();
            runFont = fk;
            runStart = it.start;
            runEnd = it.end;
            runBoxes.push_back(it.box);
        }
        close();
    }
    f->brk.fill(0, n + 1);
    if (n > 0) {
        QTextBoundaryFinder bf(QTextBoundaryFinder::Line, f->para);
        bf.toStart();
        for (qsizetype p = bf.toNextBoundary(); p != -1 && p <= n; p = bf.toNextBoundary()) {
            if (p <= 0 || p >= n)
                continue;
            if (!(bf.boundaryReasons() & QTextBoundaryFinder::BreakOpportunity))
                continue;
            // Blink's ASCII line-break table never breaks after '/' before another ASCII character
            // ("TCTK/baochinhphu" stays whole — measured in the CHÍNH PHỦ table); Qt's UAX #14 does.
            if (f->para[p - 1] == u'/' && f->para[p].unicode() < 0x80 && f->para[p] != u' ')
                continue;
            const int ip = f->itemAt[int(p) - 1];
            if (ip >= 0 && !f->items[ip].wrap)
                continue;
            f->brk[int(p)] = 1;
        }
        // around atomic inlines Chrome allows a break when the surrounding text may wrap
        for (int i = 0; i < n; ++i) {
            if (f->para[i] != kObj)
                continue;
            const IItem& at = f->items[f->itemAt[i]];
            if (!at.wrap)
                continue;
            if (i > 0 && f->para[i - 1] != kObj) {
                const int ip = f->itemAt[i - 1];
                if (ip >= 0 && f->items[ip].wrap && f->para[i - 1] == u' ')
                    f->brk[i] = 1;
            }
            if (i + 1 < n && f->para[i + 1] == u' ')
                ; // the break after the following space is already an opportunity
        }
    }
    b->ifc = std::move(f);
}

// ---------------------------------------------------------------------------------------
// IFC helpers
// ---------------------------------------------------------------------------------------
float Layout::atomicOuter(Box* a, bool useMin) {
    intrinsic(a);
    const float m = a->st ? a->st->ml + a->st->mr : 0;
    return (useMin ? a->minC : a->maxC) + m;
}

/// advance of every paragraph position for a layout (atomics laid out shrink-to-fit in `avail`)
void Layout::computeAdvances(Box* c, float avail) {
    IFC& f = *c->ifc;
    const int n = int(f.para.size());
    f.adv.fill(0.0f, n);
    for (const IItem& it : f.items) {
        if (it.t == IItem::Text) {
            const Shaped& s = *it.box->shaped;
            const float ls = it.box->cs->ls;
            const int off = it.box->shapedOff;
            for (int p = it.start; p < it.end; ++p) {
                const int i = p - it.start + off;
                f.adv[p] = s.width(i, i + 1, ls);
            }
        } else if (it.t == IItem::Atomic) {
            Box* a = it.box;
            const float m = a->st ? a->st->ml + a->st->mr : 0;
            intrinsic(a);
            float w = std::min(std::max(a->minC, avail - m), a->maxC); // shrink-to-fit
            if (a->st && !std::isnan(a->st->width))
                w = a->st->width;
            else if (a->st && !std::isnan(a->st->widthPct))
                w = luFloor(avail * a->st->widthPct / 100.0f);
            layoutBox(a, avail, w);
            f.adv[it.start] = a->w + m;
        }
    }
    snapItemWidths(f, f.adv);
}

/// Adjacent sibling bare text nodes are ONE text node in the web page (the HTML parser merges them; the
/// Qt panels sometimes build `n1(x)` + text("%") as two) — so they are one LayoutNG item.
bool textContinues(const Box* prev, const Box* cur) {
    // bare text nodes only (text(), not span(t) — a span is an element: its own item in the web too)
    if (!prev || !cur || prev->parent != cur->parent || !cur->parent || !prev->node || !cur->node ||
        !prev->node->textNode || !cur->node->textNode)
        return false;
    const auto& kids = cur->parent->kids;
    const int i = int(kids.indexOf(const_cast<Box*>(cur)));
    return i > 0 && kids[i - 1] == prev;
}

/// LayoutNG advances the line by each text item's SnappedWidth() (ceil to a LayoutUnit), so the next
/// item starts on the LayoutUnit grid (measured: "●" 9.3647 → 9.375 before " Chưa có quyền"): the
/// rounding goes on the item's last character.
void snapItemWidths(const IFC& f, QVector<float>& adv) {
    int groupEnd = -1;
    float sum = 0.0f;
    const Box* prev = nullptr;
    const auto flush = [&]() {
        if (groupEnd >= 0)
            adv[groupEnd] += luCeil(sum) - sum;
        groupEnd = -1;
        sum = 0.0f;
    };
    for (const IItem& it : f.items) {
        if (it.t == IItem::Open || it.t == IItem::Close)
            continue;
        if (it.t != IItem::Text || it.end <= it.start) {
            flush();
            prev = nullptr;
            continue;
        }
        if (!textContinues(prev, it.box))
            flush();
        for (int p = it.start; p < it.end; ++p)
            sum += adv[p];
        groupEnd = it.end - 1;
        prev = it.box;
    }
    flush();
}

void Layout::ifcIntrinsic(Box* c, float& mn, float& mx) {
    IFC& f = *c->ifc;
    const int n = int(f.para.size());
    // text advances (atomics as min / max contributions)
    QVector<float> aMin(n, 0.0f), aMax(n, 0.0f);
    for (const IItem& it : f.items) {
        if (it.t == IItem::Text) {
            const Shaped& s = *it.box->shaped;
            const float ls = it.box->cs->ls;
            const int off = it.box->shapedOff;
            for (int p = it.start; p < it.end; ++p) {
                const int i = p - it.start + off;
                aMin[p] = aMax[p] = s.width(i, i + 1, ls);
            }
        } else if (it.t == IItem::Atomic) {
            aMin[it.start] = atomicOuter(it.box, true);
            aMax[it.start] = atomicOuter(it.box, false);
        }
    }
    snapItemWidths(f, aMin); // SnappedWidth() per item, as in computeAdvances()
    snapItemWidths(f, aMax);
    auto trailingSpaces = [&](int a, int b, const QVector<float>& adv) {
        float w = 0;
        for (int i = b - 1; i >= a && f.para[i] == u' '; --i)
            w += adv[i];
        return w;
    };
    // max-content: lines split only at forced breaks
    mx = 0;
    {
        int s = 0;
        float w = 0;
        for (int i = 0; i <= n; ++i) {
            if (i == n || f.para[i] == u'\n') {
                mx = std::max(mx, w - trailingSpaces(s, i, aMax));
                w = 0;
                s = i + 1;
                continue;
            }
            w += aMax[i];
        }
    }
    // min-content: longest unbreakable segment
    mn = 0;
    {
        int s = 0;
        float w = 0;
        for (int i = 0; i <= n; ++i) {
            const bool end = i == n || f.para[i] == u'\n' || f.brk[i];
            if (end && i > s) {
                mn = std::max(mn, w - trailingSpaces(s, i, aMin));
                w = 0;
                s = i;
            }
            if (i < n && f.para[i] == u'\n') {
                s = i + 1;
                continue;
            }
            if (i < n)
                w += aMin[i];
        }
    }
}

/// line layout of an IFC container; returns content height
float Layout::layoutLines(Box* c, float cw, float contentX, float contentY) {
    IFC& f = *c->ifc;
    f.lines.clear();
    computeAdvances(c, cw);
    const int n = int(f.para.size());
    QVector<float> pre(n + 1, 0.0f);
    for (int i = 0; i < n; ++i)
        pre[i + 1] = pre[i] + f.adv[i];
    auto width = [&](int a, int b) { return pre[b] - pre[a]; };
    auto trailing = [&](int a, int b) {
        int e = b;
        while (e > a && f.para[e - 1] == u' ')
            --e;
        return e;
    };
    const int clamp = c->st ? c->st->lineClamp : 0;
    const bool ellipsisOverflow = c->st && c->st->ellipsis;
    int pos = 0;
    float y = 0;
    bool truncated = false;
    while (pos < n) {
        if (clamp > 0 && int(f.lines.size()) >= clamp) {
            truncated = true;
            break;
        }
        const int ls = pos;
        int i = pos;
        float lw = 0;
        while (i < n) {
            if (f.para[i] == u'\n') {
                i += 1; // a <br> ends the line
                break;
            }
            int j = i + 1;
            while (j < n && !f.brk[j] && f.para[j] != u'\n')
                ++j;
            const float w = width(i, j);
            const int te = trailing(i, j);
            const float wNoTrail = width(i, te);
            if (i == ls || lw + wNoTrail <= cw + kEps) {
                lw += w;
                i = j;
            } else {
                break;
            }
        }
        Line L;
        L.from = ls;
        L.to = i;
        f.lines.push_back(L);
        pos = i;
    }
    if (clamp > 0 && pos < n)
        truncated = true;

    // horizontal placement + fragments + vertical metrics
    const VB strut = inlineBounds(*c->cs);
    const float ellW = c->cs ? detail::shape(c->cs->font, QStringLiteral("…"))->width(0, 1, c->cs->ls) : 0;
    for (int li = 0; li < f.lines.size(); ++li) {
        Line& L = f.lines[li];
        int end = L.to;
        if (end > L.from && f.para[end - 1] == u'\n')
            --end;
        int visEnd = trailing(L.from, end);
        float used = width(L.from, visEnd);
        const bool lastVisible = li == f.lines.size() - 1;
        if ((truncated && lastVisible) || (ellipsisOverflow && used > cw + kEps)) {
            // -webkit-line-clamp / text-overflow: shorten to fit "…"
            // Chrome (NGLineTruncator) cuts at the last grapheme that fits and keeps a space
            // that precedes the cut ("RẤT …"); when nothing has to go, "…" follows the text.
            const float target = cw - ellW;
            int k = visEnd;
            bool cut = false;
            while (k > L.from && width(L.from, k) > target + kEps) {
                --k;
                if (k > L.from && f.para[k].isLowSurrogate())
                    --k;
                cut = true;
            }
            if (truncated || used > cw + kEps) {
                visEnd = cut ? k : trailing(L.from, k);
                used = width(L.from, visEnd);
                L.ellX = used;
            }
        }
        float off = 0;
        const float free = cw - used;
        if (free > 0 && c->cs->align == TextAlign::Right)
            off = free;
        else if (free > 0 && c->cs->align == TextAlign::Center)
            off = free / 2.0f; // an overflowing line starts at the start edge
        L.left = contentX + off;
        L.width = used;
        if (L.ellX >= 0)
            L.ellX += L.left;
        // vertical: strut + every inline box with content on the line
        float above = strut.above, below = strut.below;
        QHash<Box*, bool> seen;
        for (int ii = 0; ii < f.items.size(); ++ii) {
            const IItem& it = f.items[ii];
            if (it.t == IItem::Open || it.t == IItem::Close)
                continue;
            const int a = std::max(it.start, L.from), b = std::min(it.end, visEnd);
            const bool onLine = it.end > L.from && it.start < L.to;
            if (!onLine)
                continue;
            // contributing inline ancestors (Text boxes are inline boxes too)
            for (Box* p = it.t == IItem::Atomic ? it.box->parent : it.box; p && p != c; p = p->parent) {
                if (p->kind != BK::Inline && p->kind != BK::Text && p->kind != BK::Br)
                    continue;
                if (seen.contains(p))
                    continue;
                seen.insert(p, true);
                const VB vb = inlineBounds(*p->cs);
                above = std::max(above, vb.above);
                below = std::max(below, vb.below);
            }
            if (it.t == IItem::Atomic) {
                Box* at = it.box;
                const float mT = at->st ? at->st->mt : 0, mB = at->st ? at->st->mb : 0;
                float bl = firstOrLastBaseline(at, true);
                const float outerH = at->h + mT + mB;
                const float base = bl < 0 ? outerH : mT + bl; // no line box → bottom margin edge
                above = std::max(above, base);
                below = std::max(below, outerH - base);
            }
            if (b <= a && it.t != IItem::Br)
                continue;
            if (it.t == IItem::Br)
                continue;
            Frag fr;
            fr.box = it.box;
            fr.item = ii;
            fr.from = a;
            fr.to = std::max(a, b);
            fr.x = L.left + width(L.from, a);
            fr.w = width(a, fr.to);
            L.frags.push_back(fr);
        }
        L.top = contentY + y;
        L.height = above + below;
        L.baseline = L.top + above;
        y += L.height;
    }
    // position atomics
    for (Line& L : f.lines) {
        for (Frag& fr : L.frags) {
            if (fr.box->kind != BK::Atomic)
                continue;
            Box* at = fr.box;
            const float mT = at->st ? at->st->mt : 0, mB = at->st ? at->st->mb : 0;
            const float bl = firstOrLastBaseline(at, true);
            const float outerH = at->h + mT + mB;
            const float base = bl < 0 ? outerH : mT + bl;
            at->x = fr.x + (at->st ? at->st->ml : 0);
            at->y = L.baseline - base + mT;
        }
    }
    return y;
}

/// first (or last, for inline-block) baseline from the border-box top; −1 if none
float Layout::firstOrLastBaseline(Box* b, bool last) {
    if (b->ifc) {
        if (b->ifc->lines.isEmpty())
            return -1;
        const Line& L = last ? b->ifc->lines.last() : b->ifc->lines.first();
        return L.baseline;
    }
    if (b->custom || b->widget)
        return -1;
    if (b->kind == BK::Table || b->kind == BK::Row) {
        for (Box* r : b->kids)
            for (Box* cell : r->kids) {
                const float v = firstOrLastBaseline(cell, false);
                if (v >= 0)
                    return v + cell->y + (b->kind == BK::Table ? r->y : 0);
            }
        return -1;
    }
    if (last) {
        for (int i = int(b->kids.size()) - 1; i >= 0; --i) {
            const float v = firstOrLastBaseline(b->kids[i], true);
            if (v >= 0)
                return v + b->kids[i]->y;
        }
        return -1;
    }
    for (Box* k : b->kids) {
        const float v = firstOrLastBaseline(k, false);
        if (v >= 0)
            return v + k->y;
    }
    return -1;
}

/// a:hover underline as Blink paints it: thickness max(1, font-size/10) (the rect keeps its integer
/// part: GraphicsContext::GetRectForTextLine), top at the text origin + max(1, ⌈thickness/2⌉)
/// (ComputeUnderlineOffsetAuto) — so it straddles two rows when the origin is on a half pixel — and
/// text-decoration-skip-ink: every glyph crossing the stripe clips out its x-range ± thickness (hard
/// clip on pixel centres). `baseY` = Chrome's (half-pixel) text origin in painter coordinates.
void paintUnderline(QPainter& p, const Box* tb, int from, int to, float x, float baseY, float w, const QColor& c) {
    const float thF = std::max(1.0f, tb->cs->font.px / 10.0f);
    const float gap = std::max(1.0f, std::ceil(thF / 2.0f));
    const float th = std::floor(thF);
    const float top = baseY + gap;
    const QVector<QPointF> iv = detail::textIntercepts(tb->cs->font, *tb->shaped, from, to, tb->cs->ls, gap, gap + thF);
    const QTransform D = p.deviceTransform();
    const double dx = D.dx(), dil = std::min(thF, 13.0f);
    // device columns whose centre falls in a dilated intercept
    const double l = x + dx, r = x + w + dx;
    QVector<QPair<double, double>> keep;
    double segStart = l;
    for (int col = int(std::floor(l)); col < int(std::ceil(r)); ++col) {
        bool cut = false;
        for (const QPointF& g : iv)
            cut = cut || (col + 0.5 >= x + g.x() - dil + dx && col + 0.5 <= x + g.y() + dil + dx);
        if (cut) {
            if (col > segStart)
                keep.push_back({segStart, double(col)});
            segStart = col + 1;
        }
    }
    if (r > segStart)
        keep.push_back({segStart, r});
    // Below 10px the auto thickness (font-size/10) is under a pixel and Chrome draws a hairline: a
    // 1px band at half the colour's alpha, centred a quarter pixel above the band a 1px line would
    // start at (measured 27/09 on 9 and 9.5px links: rows .376/.124 at every top offset; the WiData
    // "mở trên WiData ↗" link: rows 211/212 = 38%/12% where the 1px rule gave row 212 = 100%)
    QColor col = c;
    float y0 = top;
    if (tb->cs->font.px < 10.0f) {
        col.setAlphaF(c.alphaF() * 0.5f);
        y0 = top - 0.75f;
    }
    p.save();
    p.setRenderHint(QPainter::Antialiasing, true);
    for (const auto& k : keep)
        p.fillRect(QRectF(k.first - dx, y0, k.second - k.first, th), col);
    p.restore();
}

} // namespace fincept::screens::hlp::hlpdom
