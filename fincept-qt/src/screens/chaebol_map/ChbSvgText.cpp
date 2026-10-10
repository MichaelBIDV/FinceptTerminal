// ChbSvgText.cpp — <text>/<tspan> layout for the chaebol_map engine, measured against Chrome 147 (probe cases
// 47, 73, 74, 80 of the harness):
//  * white space: CSS `normal` over the whole <text> (runs collapse across tspans, leading/trailing removed);
//  * x/y/dx/dy lists address characters (code points) of the element's subtree; descendants override;
//    every character with an explicit position starts a new fragment, absolute x/y start a new text chunk;
//  * text-anchor per chunk (value of the chunk's first character), SVG 2 "apply anchoring";
//  * Blink's scaled font: text is shaped at font-size × s (s = √((sx² + sy²)/2) of the user → doc CTM) and mapped
//    back by 1/s, so ascent/descent are rounded at the scaled size (MiniChart 9 px at s = 0.557: height 6 px);
//  * dominant-baseline (inherited): middle = x-height/2, central = (A − D)/2, hanging = 0.8·A, mathematical = A/2,
//    ideographic / text-after-edge = −D, text-before-edge = A (A, D = rounded scaled metrics; 1/64 px units);
//  * client rects of text nodes use the primary font; element boxes add the glyph ink (diacritics, emoji).
#include "screens/chaebol_map/ChbSvg_p.h"
#include "screens/chaebol_map/ChbText.h"

#include <QRawFont>

#include <cmath>
#include <optional>

namespace fincept::screens::chb::svg {

namespace {

// Blink clamps font sizes at 10 000 px; ChbText shapes at ×32 and CoreText/Qt crash beyond ~65 536 px, so the
// scaled font stops at 1 024 px (larger magnifications are drawn by the painter transform instead).
constexpr float kMaxFontPx = 1024.0f;
constexpr float kMinFontPx = 1e-3f;    // below: nothing is shaped (zero advance)

struct ChbgTNode {
    const RNode* node = nullptr;
    Style st;
    QString text;              ///< collapsed
    int charBase = 0;          ///< global index of its first addressable character
    std::vector<int> cpStart;  ///< UTF-16 index of each character (code point)
};

struct ChbgElem {
    const RNode* el = nullptr;
    int nodeFrom = 0, nodeTo = 0;
    LenCtx lc;
};

struct ChbgPos {
    std::optional<float> x, y, dx, dy;
    bool any() const { return x || y || dx || dy; }
};

void chbg_gather(const RNode* el, const Style& st, const LenCtx& c, std::vector<ChbgTNode>& nodes,
                 std::vector<ChbgElem>& elems) {
    const size_t me = elems.size();
    LenCtx lc = c;
    lc.fontSize = st.fontSize;
    elems.push_back({el, int(nodes.size()), 0, lc});
    for (const RNode* k : el->kids) {
        if (k->isText) {
            ChbgTNode t;
            t.node = k;
            t.st = st;
            t.text = k->text;
            nodes.push_back(std::move(t));
            continue;
        }
        if ((k->tag != Tag::Tspan && k->tag != Tag::A) || is_display_none(k)) continue;
        chbg_gather(k, inherit_style(k, st, c), c, nodes, elems);
    }
    elems[me].nodeTo = int(nodes.size());
}

bool chbg_space(QChar ch) { return ch == u' ' || ch == u'\t' || ch == u'\n' || ch == u'\r'; }

void chbg_collapse(std::vector<ChbgTNode>& nodes) {
    bool prevSpace = true; // drops leading white space of the whole <text>
    for (ChbgTNode& n : nodes) {
        QString out;
        out.reserve(n.text.size());
        for (QChar ch : n.text) {
            if (chbg_space(ch)) {
                if (!prevSpace) out += QLatin1Char(' ');
                prevSpace = true;
            } else {
                out += ch;
                prevSpace = false;
            }
        }
        n.text = out;
    }
    for (auto it = nodes.rbegin(); it != nodes.rend(); ++it) {
        if (it->text.isEmpty()) continue;
        if (it->text.endsWith(QLatin1Char(' '))) it->text.chop(1);
        break;
    }
}

/// Length list attribute (x="10 20 30", dx="5px 2") → values; empty when absent or invalid.
std::vector<float> chbg_len_list(const RNode* r, QStringView name, Axis ax, const LenCtx& c) {
    std::vector<float> out;
    const QString* v = attr(r, name);
    if (!v) return out;
    QString norm = *v;
    norm.replace(QLatin1Char(','), QLatin1Char(' '));
    for (const QString& t : norm.split(QLatin1Char(' '), Qt::SkipEmptyParts)) {
        float f = 0;
        if (!parse_length(t, ax, c, &f)) return {};
        out.push_back(f);
    }
    return out;
}

float chbg_snap64(float v) { return std::round(v * 64.0f) / 64.0f; }

/// x-height used by dominant-baseline: middle. Variable faces with an opsz instance (Source Serif 4 @ opsz 14)
/// report the default master's OS/2 value through Qt; Chrome/CoreText applies the instance — measure the 'x' glyph.
float chbg_x_height(const FontEntry& fe) {
    if (fe.spec.opsz > 0 && fe.raw.isValid()) {
        const QList<quint32> ids = fe.raw.glyphIndexesForString(QStringLiteral("x"));
        if (!ids.isEmpty() && ids[0] != 0) {
            const QRectF br = fe.raw.boundingRect(ids[0]);
            if (br.height() > 0) return float(-br.top());
        }
    }
    return fe.xHeight;
}

/// Ink bounds of the shaped glyphs (scaled font space, origin = text start on the baseline).
QRectF chbg_ink(const ShapedText& sh) {
    QRectF u;
    const float x0 = sh.x(0);
    for (const ShapedText::Glyph& g : sh.glyphs) {
        const ShapedText::Run& run = sh.runs[size_t(g.run)];
        QRectF b = run.raw.boundingRect(g.id);
        if (b.width() <= 0 || b.height() <= 0) continue;
        if (run.bitmap) // colour bitmap glyphs: Skia mask bounds, rounded out + 1 px (measured: ⛔ at 8.3–8.7 px)
            b = QRectF(QPointF(std::floor(b.left()) - 1, std::floor(b.top()) - 1),
                       QPointF(std::ceil(b.right()) + 1, std::ceil(b.bottom()) + 1));
        b.translate(qreal(g.x - x0), qreal(g.y));
        u = u.isNull() ? b : u.united(b);
    }
    if (!u.isNull() && sh.font && sh.font->spec.fakeItalic) u = QTransform(1, 0, -0.25, 1, 0, 0).mapRect(u);
    if (!u.isNull() && sh.font && sh.font->spec.fakeBold) u.adjust(-0.5, -0.5, 0.5, 0.5);
    return u;
}

float chbg_baseline_shift(const Style& st, const FontEntry& fe) {
    const float A = fe.m.asc, D = fe.m.desc;
    switch (st.baseline) {
    case Baseline::Middle: return chbg_snap64(chbg_x_height(fe) / 2.0f);
    case Baseline::Central: return chbg_snap64((A - D) / 2.0f);
    case Baseline::Hanging: return chbg_snap64(A * 0.8f);
    case Baseline::Mathematical: return chbg_snap64(A / 2.0f);
    case Baseline::Ideographic: case Baseline::AfterEdge: return -D;
    case Baseline::BeforeEdge: return A;
    case Baseline::Auto: break;
    }
    return 0;
}

} // namespace

std::vector<TextFrag> layout_text(const RNode* text, const Style& st, const QTransform& ctm, const LenCtx& c) {
    std::vector<TextFrag> out;
    std::vector<ChbgTNode> nodes;
    std::vector<ChbgElem> elems;
    chbg_gather(text, st, c, nodes, elems);
    chbg_collapse(nodes);

    // addressable characters (code points)
    int total = 0;
    for (ChbgTNode& n : nodes) {
        n.charBase = total;
        for (int i = 0; i < n.text.size(); ++i) {
            n.cpStart.push_back(i);
            if (n.text[i].isHighSurrogate() && i + 1 < n.text.size() && n.text[i + 1].isLowSurrogate()) ++i;
        }
        total += int(n.cpStart.size());
    }
    if (total == 0) return out;

    // position lists, pre-order (descendants override ancestors)
    std::vector<ChbgPos> pos(static_cast<size_t>(total));
    for (const ChbgElem& e : elems) {
        if (e.nodeFrom >= e.nodeTo) continue;
        const int from = nodes[size_t(e.nodeFrom)].charBase;
        const ChbgTNode& lastN = nodes[size_t(e.nodeTo - 1)];
        const int to = lastN.charBase + int(lastN.cpStart.size());
        auto apply = [&](QStringView name, Axis ax, std::optional<float> ChbgPos::*field) {
            const std::vector<float> v = chbg_len_list(e.el, name, ax, e.lc);
            for (int i = 0; i < int(v.size()) && from + i < to; ++i) pos[size_t(from + i)].*field = v[size_t(i)];
        };
        apply(u"x", Axis::X, &ChbgPos::x);
        apply(u"y", Axis::Y, &ChbgPos::y);
        apply(u"dx", Axis::X, &ChbgPos::dx);
        apply(u"dy", Axis::Y, &ChbgPos::dy);
    }

    // Blink's screen font scaling factor
    const double sx = std::hypot(ctm.m11(), ctm.m12()), sy = std::hypot(ctm.m21(), ctm.m22());
    float s = float(std::sqrt((sx * sx + sy * sy) / 2.0));
    if (!(s > 0) || !std::isfinite(s)) s = 1;

    // fragments: split at every explicitly positioned character
    struct Pending {
        int node, from, to; // UTF-16 range in node text
        ChbgPos p;
        bool chunkStart;
    };
    std::vector<Pending> segs;
    bool firstChar = true;
    for (int ni = 0; ni < int(nodes.size()); ++ni) {
        const ChbgTNode& n = nodes[size_t(ni)];
        for (int k = 0; k < int(n.cpStart.size()); ++k) {
            const ChbgPos& p = pos[size_t(n.charBase + k)];
            if (k == 0 || p.any()) {
                if (!segs.empty() && segs.back().node == ni) segs.back().to = n.cpStart[size_t(k)];
                segs.push_back({ni, n.cpStart[size_t(k)], int(n.text.size()), p, firstChar || p.x || p.y});
            }
            firstChar = false;
        }
    }

    // pen + shaping
    float penX = 0, penY = 0;
    for (const Pending& sg : segs) {
        const ChbgTNode& n = nodes[size_t(sg.node)];
        TextFrag f;
        f.textNode = n.node;
        f.st = n.st;
        f.text = n.text.mid(sg.from, sg.to - sg.from);
        // keep the scaled font in range (kMaxFontPx), map back with the clamped factor
        f.scale = n.st.fontSize > 0 ? std::min(s, kMaxFontPx / n.st.fontSize) : s;
        if (sg.p.x) penX = *sg.p.x;
        if (sg.p.y) penY = *sg.p.y;
        if (sg.p.dx) penX += *sg.p.dx;
        if (sg.p.dy) penY += *sg.p.dy;
        f.x = penX;
        f.baseline = penY;
        const float px = n.st.fontSize * f.scale;
        if (px >= kMinFontPx && std::isfinite(px)) {
            const FontEntry& fe = font_entry(n.st.fontFamily, px, n.st.fontWeight, n.st.italic);
            const ShapedText& sh = shape_text(fe, f.text, n.st.letterSpacing * f.scale);
            f.shaped = &sh;
            f.width = sh.width / f.scale;
        }
        penX += f.width;
        out.push_back(std::move(f));
    }

    // text-anchor per chunk: shift = x(first) − (a + b)/2 (middle) or − b (end), a/b = extent of the chunk
    for (size_t a = 0; a < out.size();) {
        size_t b = a + 1;
        while (b < segs.size() && !segs[b].chunkStart) ++b;
        const std::uint8_t anchor = out[a].st.anchor;
        if (anchor != 0) {
            float lo = out[a].x, hi = out[a].x + out[a].width;
            for (size_t k = a; k < b; ++k) {
                lo = std::min(lo, out[k].x);
                hi = std::max(hi, out[k].x + out[k].width);
            }
            const float shift = anchor == 1 ? out[a].x - (lo + hi) / 2.0f : out[a].x - hi;
            for (size_t k = a; k < b; ++k) out[k].x += shift;
        }
        a = b;
    }

    // dominant-baseline + rects
    for (TextFrag& f : out) {
        if (!f.shaped) {
            f.rect = f.box = QRectF(f.x, f.baseline, 0, 0);
            continue;
        }
        const FontEntry& fe = *f.shaped->font;
        const float s = f.scale;
        f.baseline += chbg_baseline_shift(f.st, fe) / s;
        const float A = fe.m.asc, D = fe.m.desc;
        f.rect = QRectF(f.x, f.baseline - A / s, f.width, (A + D) / s);
        // element boxes: layout rect ∪ glyph ink (Blink: SVG text object bounding box includes ink overflow —
        // stacked Vietnamese diacritics, emoji, italic overhang)
        f.box = f.rect;
        const QRectF ink = chbg_ink(*f.shaped);
        if (!ink.isNull()) {
            const QRectF iu(f.x + ink.x() / s, f.baseline + ink.y() / s, ink.width() / s, ink.height() / s);
            f.box = f.box.united(iu);
        }
    }
    return out;
}

void paint_text_frag(QPainter& p, const TextFrag& f, const QTransform& userToLogical, const QColor& color) {
    if (!f.shaped || f.text.isEmpty() || color.alpha() == 0) return;
    const qreal s = f.scale;
    p.save();
    p.setTransform(QTransform::fromScale(1.0 / s, 1.0 / s) * userToLogical);
    f.shaped->paint(p, QPointF(f.x * s, f.baseline * s), 0, int(f.text.size()), color);
    p.restore();
}

QPainterPath text_outline(const TextFrag& f) {
    QPainterPath path;
    if (!f.shaped || f.text.isEmpty()) return path;
    const ShapedText& sh = *f.shaped;
    const float x0 = sh.x(0);
    for (const ShapedText::Glyph& g : sh.glyphs) {
        const ShapedText::Run& run = sh.runs[size_t(g.run)];
        if (run.bitmap) continue;
        path.addPath(run.raw.pathForGlyph(g.id).translated(qreal(g.x - x0), qreal(g.y)));
    }
    QTransform t;
    if (sh.font && sh.font->spec.fakeItalic) t = QTransform(1, 0, -0.25, 1, 0, 0); // Skia fake italic
    const qreal s = f.scale;
    t = t * QTransform::fromScale(1.0 / s, 1.0 / s) * QTransform::fromTranslate(f.x, f.baseline);
    path = t.map(path);
    path.setFillRule(Qt::WindingFill);
    return path;
}

} // namespace fincept::screens::chb::svg
