// ChbPaint.cpp — overflow + scroll regions, and painting (stacking order, backgrounds, gradients, shadows,
// borders, inline content, decorations, markers, replaced elements).
#include "screens/chaebol_map/ChbDom_p.h"
#include "screens/chaebol_map/ChbSvg.h"

#include <QImage>
#include <QLinearGradient>
#include <QPainterPath>
#include <QRadialGradient>

#include <cmath>

namespace fincept::screens::chb {

// ============================================================================================== overflow

namespace {

QRectF chbp_border_rect(const Box* b) { return QRectF(b->ax, b->ay, b->w, b->h); }

/// Chrome paints box decorations on the pixel-snapped border box (PhysicalRect::PixelSnappedRect): rounded origin,
/// size = round(origin + size) − round(origin). Layout coordinates stay fractional.
QRectF chbp_snap(const QRectF& r) {
    const qreal x = std::round(r.x()), y = std::round(r.y());
    return QRectF(x, y, std::round(r.x() + r.width()) - x, std::round(r.y() + r.height()) - y);
}

QRectF chbp_shadow_extent(const Box* b, const QRectF& r) {
    QRectF u = r;
    if (b->st && b->st->shadows)
        for (const Shadow& s : *b->st->shadows) {
            if (s.inset) continue;
            const float e = s.blur + s.spread;
            u = u.united(r.translated(s.x, s.y).adjusted(-e, -e, e, e));
        }
    return u;
}

/// Returns the "scrollable overflow" right/bottom edges of b (document coords).
void chbp_overflow(Document::Impl& d, Box* b, float* loRight, float* loBottom) {
    QRectF own = chbp_border_rect(b);
    float right = float(own.right()), bottom = float(own.bottom());
    QRectF vis = chbp_shadow_extent(b, own);
    float kidRight = -kInf, kidBottom = -kInf;
    QRectF kidVis;
    if (b->ifc) {
        for (const InlineFrag& f : b->ifc->frags) {
            if (f.type == InlineFrag::Atomic) continue;
            const QRectF r(b->ax + f.x, b->ay + f.top, f.w, f.height);
            kidRight = std::max(kidRight, float(r.right()));
            kidBottom = std::max(kidBottom, float(r.bottom()));
            kidVis = kidVis.united(r);
        }
    }
    for (Box* k : b->kids) {
        if (k->kind == BoxKind::Text || k->kind == BoxKind::Br) continue;
        float r2 = 0, b2 = 0;
        chbp_overflow(d, k, &r2, &b2);
        if (k->kind == BoxKind::Inline && !k->atomic) {
            // inline boxes: fragments are in the formatting root; only their atomic descendants matter here
        }
        kidRight = std::max(kidRight, r2);
        kidBottom = std::max(kidBottom, b2);
        kidVis = kidVis.united(k->overflow);
    }
    if (b->kind == BoxKind::Inline && !b->atomic) {
        own = QRectF();
        right = kidRight;
        bottom = kidBottom;
        vis = kidVis;
    }
    if (b->clips) {
        if (b->scrollX) {
            const float padLeft = b->ax + b->bl;
            const float end = std::isfinite(kidRight) ? kidRight + b->pr : padLeft;
            // Chrome's scrollWidth is pixel-snapped (so the largest scrollLeft is whole pixels; suite 44: 2984, not 2984.39)
            b->scrollW = std::max(b->w - b->bl - b->br, std::round(end) - std::round(padLeft));
        }
        b->overflow = vis;
        *loRight = right;
        *loBottom = bottom;
        return;
    }
    // Chrome inflates by the inline-end padding only inside scroll containers (branch above), never here
    if (std::isfinite(kidRight)) right = std::max(right, kidRight);
    if (std::isfinite(kidBottom)) bottom = std::max(bottom, kidBottom);
    b->overflow = vis.united(kidVis);
    *loRight = right;
    *loBottom = bottom;
}

void chbp_regions(Document::Impl& d, Box* b) {
    if (b->scrollX) {
        b->regionId = int(d.regions.size());
        Document::Impl::Region r;
        r.box = b;
        if (b->node) r.scrollX = d.regionScrollMemo.value(QString::number(b->node->order), 0.0f);
        const float client = b->w - b->bl - b->br;
        r.scrollX = std::clamp(r.scrollX, 0.0f, std::max(0.0f, b->scrollW - client));
        d.regions.push_back(r);
    } else {
        b->regionId = -1;
    }
    for (Box* k : b->kids) chbp_regions(d, k);
}

} // namespace

void chb_compute_overflow(Document::Impl& d) {
    d.regions.clear();
    if (!d.body) return;
    float r = 0, bo = 0;
    chbp_overflow(d, d.body, &r, &bo);
    // scrollWidth/scrollHeight are pixel-snapped (rounded) like Chrome's layout overflow rect
    d.docW = std::max(d.docW, std::round(r));
    d.docH = std::max(d.docH, std::round(bo));
    chbp_regions(d, d.body);
}

// ============================================================================================== painting

namespace {

struct ChbpDeferred {
    Box* box;
    QTransform xf;
    QRegion clip;
    bool hasClip;
    int z;
    int order;
};

struct ChbpCtx {
    std::vector<ChbpDeferred> neg, zero, pos;
};

bool chbp_creates_layer(const Box* b) {
    if (!b->st || !b->node) return false;
    const ComputedStyle& s = *b->st;
    return s.isPositioned() || s.opacity < 1.0f || !s.transform.none;
}

struct ChbpRadii {
    float tl = 0, tr = 0, br = 0, bl = 0;
    bool any() const { return tl > 0 || tr > 0 || br > 0 || bl > 0; }
};

ChbpRadii chbp_radii(const Box* b, const QRectF& r) {
    ChbpRadii o;
    if (!b->st) return o;
    const float w = float(r.width()), h = float(r.height());
    auto res = [&](const Len& l) { return l.kind == Len::Val ? l.px + l.pct * std::min(w, h) / 100.0f : 0.0f; };
    o.tl = res(b->st->radius[0]);
    o.tr = res(b->st->radius[1]);
    o.br = res(b->st->radius[2]);
    o.bl = res(b->st->radius[3]);
    float f = 1.0f;
    auto fit = [&](float a, float c, float len) { if (a + c > len && a + c > 0) f = std::min(f, len / (a + c)); };
    fit(o.tl, o.tr, w);
    fit(o.bl, o.br, w);
    fit(o.tl, o.bl, h);
    fit(o.tr, o.br, h);
    o.tl *= f; o.tr *= f; o.br *= f; o.bl *= f;
    return o;
}

QPainterPath chbp_round_rect(const QRectF& r, const ChbpRadii& rd) {
    QPainterPath p;
    if (!rd.any()) {
        p.addRect(r);
        return p;
    }
    const qreal x = r.x(), y = r.y(), w = r.width(), h = r.height();
    p.moveTo(x + rd.tl, y);
    p.lineTo(x + w - rd.tr, y);
    if (rd.tr > 0) p.arcTo(x + w - 2 * rd.tr, y, 2 * rd.tr, 2 * rd.tr, 90, -90);
    p.lineTo(x + w, y + h - rd.br);
    if (rd.br > 0) p.arcTo(x + w - 2 * rd.br, y + h - 2 * rd.br, 2 * rd.br, 2 * rd.br, 0, -90);
    p.lineTo(x + rd.bl, y + h);
    if (rd.bl > 0) p.arcTo(x, y + h - 2 * rd.bl, 2 * rd.bl, 2 * rd.bl, 270, -90);
    p.lineTo(x, y + rd.tl);
    if (rd.tl > 0) p.arcTo(x, y, 2 * rd.tl, 2 * rd.tl, 180, -90);
    p.closeSubpath();
    return p;
}

ChbpRadii chbp_inner_radii(const ChbpRadii& o, float t, float r, float b, float l) {
    ChbpRadii i;
    i.tl = std::max(0.0f, o.tl - std::max(t, l));
    i.tr = std::max(0.0f, o.tr - std::max(t, r));
    i.br = std::max(0.0f, o.br - std::max(b, r));
    i.bl = std::max(0.0f, o.bl - std::max(b, l));
    return i;
}

// ---- gradients
QColor chbp_mix_transparent(const QColor& c, const QColor& neighbour) {
    if (c.alpha() > 0) return c;
    QColor n = neighbour;
    n.setAlpha(0);
    return n;
}

void chbp_stops(QGradient& g, const Gradient& gr, float lineLen) {
    const size_t n = gr.stops.size();
    std::vector<float> pos(n, -1.0f);
    for (size_t i = 0; i < n; ++i)
        if (gr.stops[i].hasPos) pos[i] = lineLen > 0 ? lc_len(gr.stops[i].pos, lineLen) / lineLen : 0.0f;
    if (pos[0] < 0) pos[0] = 0;
    if (pos[n - 1] < 0) pos[n - 1] = 1;
    for (size_t i = 1; i < n; ++i) pos[i] = pos[i] < 0 ? -1.0f : std::max(pos[i], pos[i - 1] < 0 ? 0.0f : pos[i - 1]);
    // fill runs without positions evenly
    for (size_t i = 0; i < n;) {
        if (pos[i] >= 0) { ++i; continue; }
        size_t j = i;
        while (j < n && pos[j] < 0) ++j;
        const float a = pos[i - 1], b = pos[j];
        for (size_t k = i; k < j; ++k) pos[k] = a + (b - a) * float(k - i + 1) / float(j - i + 1);
        i = j;
    }
    for (size_t i = 0; i < n; ++i) {
        QColor c = gr.stops[i].color;
        if (c.alpha() == 0) c = chbp_mix_transparent(c, i + 1 < n ? gr.stops[i + 1].color : (i > 0 ? gr.stops[i - 1].color : c));
        // Qt needs strictly increasing positions within [0,1]
        const qreal p = std::clamp(qreal(pos[i]), 0.0, 1.0);
        g.setColorAt(p, c);
        if (i > 0 && gr.stops[i - 1].color.alpha() == 0 && gr.stops[i].color.alpha() > 0) {
            // premultiplied interpolation from transparent: colour ramps from this stop's RGB
            QColor prev = gr.stops[i].color;
            prev.setAlpha(0);
            g.setColorAt(std::clamp(qreal(pos[i - 1]), 0.0, 1.0), prev);
        }
    }
}

void chbp_gradient(QPainter& p, const Gradient& gr, const QRectF& area, const QPainterPath& clipPath) {
    if (gr.stops.size() < 2) return;
    p.save();
    p.setClipPath(clipPath, Qt::IntersectClip);
    if (gr.type == Gradient::Linear) {
        const qreal w = area.width(), h = area.height();
        qreal ang = gr.angleDeg;
        if (gr.toCorner) {
            const bool top = gr.toCorner & 1, right = gr.toCorner & 2;
            const qreal a = std::atan2(w, h) * 180.0 / M_PI; // angle to the corner direction
            if (top && right) ang = a;
            else if (!top && right) ang = 180 - a;
            else if (!top && !right) ang = 180 + a;
            else ang = 360 - a;
        }
        const qreal rad = ang * M_PI / 180.0;
        const qreal sx = std::sin(rad), sy = -std::cos(rad);
        const qreal len = std::fabs(w * std::sin(rad)) + std::fabs(h * std::cos(rad));
        const QPointF c = area.center();
        QLinearGradient g(c - QPointF(sx, sy) * len / 2, c + QPointF(sx, sy) * len / 2);
        chbp_stops(g, gr, float(len));
        g.setSpread(gr.repeating ? QGradient::RepeatSpread : QGradient::PadSpread);
        p.fillRect(area, g);
    } else {
        const float w = float(area.width()), h = float(area.height());
        const float cx = lc_len(gr.posX, w), cy = lc_len(gr.posY, h);
        const float dl = cx, dr = w - cx, dt = cy, db = h - cy;
        float rx = 0, ry = 0;
        const float fx = std::max(std::fabs(dl), std::fabs(dr)), fy = std::max(std::fabs(dt), std::fabs(db));
        const float nx = std::min(std::fabs(dl), std::fabs(dr)), ny = std::min(std::fabs(dt), std::fabs(db));
        switch (gr.size) {
        case Gradient::ClosestSide: rx = nx; ry = ny; break;
        case Gradient::FarthestSide: rx = fx; ry = fy; break;
        case Gradient::ClosestCorner: rx = nx * float(M_SQRT2); ry = ny * float(M_SQRT2); break;
        case Gradient::Explicit: rx = lc_len(gr.rx, w); ry = lc_len(gr.ry, h); break;
        default: rx = fx * float(M_SQRT2); ry = fy * float(M_SQRT2); break;
        }
        if (gr.circle) {
            const float r = gr.size == Gradient::FarthestCorner ? std::hypot(fx, fy)
                            : gr.size == Gradient::ClosestCorner ? std::hypot(nx, ny)
                            : gr.size == Gradient::ClosestSide ? std::min(nx, ny)
                            : gr.size == Gradient::FarthestSide ? std::max(fx, fy) : rx;
            rx = ry = r;
        }
        if (rx <= 0 || ry <= 0) { p.restore(); return; }
        p.translate(area.x() + cx, area.y() + cy);
        p.scale(1.0, qreal(ry) / qreal(rx));
        QRadialGradient g(QPointF(0, 0), rx);
        chbp_stops(g, gr, rx);
        g.setSpread(gr.repeating ? QGradient::RepeatSpread : QGradient::PadSpread);
        const qreal sy = qreal(rx) / qreal(ry);
        p.fillRect(QRectF(-cx, -cy * sy, w, h * sy), g);
    }
    p.restore();
}

// ---- box shadow (outer), blurred via a cached alpha image
QImage chbp_blur_mask(int w, int h, float radius, const ChbpRadii& rd, int pad) {
    QImage img(w + 2 * pad, h + 2 * pad, QImage::Format_Alpha8);
    img.fill(0);
    {
        QPainter q(&img);
        q.setRenderHint(QPainter::Antialiasing, true);
        q.fillPath(chbp_round_rect(QRectF(pad, pad, w, h), rd), QColor(0, 0, 0, 255));
    }
    const float sigma = radius / 2.0f;
    if (sigma <= 0.1f) return img;
    // three box blurs ≈ gaussian
    const int bw = std::max(1, int(std::round(std::sqrt(12.0f * sigma * sigma / 3.0f + 1.0f))));
    const int r = bw / 2;
    std::vector<int> buf;
    for (int pass = 0; pass < 3; ++pass) {
        for (int y = 0; y < img.height(); ++y) { // horizontal
            uchar* row = img.scanLine(y);
            buf.assign(size_t(img.width()), 0);
            int acc = 0;
            for (int x = -r; x <= r; ++x) acc += (x >= 0 && x < img.width()) ? row[x] : 0;
            for (int x = 0; x < img.width(); ++x) {
                buf[size_t(x)] = acc / (2 * r + 1);
                const int add = x + r + 1, sub = x - r;
                acc += (add < img.width() ? row[add] : 0) - (sub >= 0 ? row[sub] : 0);
            }
            for (int x = 0; x < img.width(); ++x) row[x] = uchar(buf[size_t(x)]);
        }
        for (int x = 0; x < img.width(); ++x) { // vertical
            buf.assign(size_t(img.height()), 0);
            int acc = 0;
            for (int y = -r; y <= r; ++y) acc += (y >= 0 && y < img.height()) ? img.scanLine(y)[x] : 0;
            for (int y = 0; y < img.height(); ++y) {
                buf[size_t(y)] = acc / (2 * r + 1);
                const int add = y + r + 1, sub = y - r;
                acc += (add < img.height() ? img.scanLine(add)[x] : 0) - (sub >= 0 ? img.scanLine(sub)[x] : 0);
            }
            for (int y = 0; y < img.height(); ++y) img.scanLine(y)[x] = uchar(buf[size_t(y)]);
        }
    }
    return img;
}

void chbp_shadows(QPainter& p, const Box* b, const QRectF& r, const ChbpRadii& rd) {
    if (!b->st || !b->st->shadows) return;
    const auto& list = *b->st->shadows;
    for (auto it = list.rbegin(); it != list.rend(); ++it) {
        const Shadow& s = *it;
        if (s.inset) continue;
        const QColor col = s.currentColor ? b->st->color : s.color;
        if (col.alpha() == 0) continue;
        const QRectF sr = r.adjusted(-s.spread, -s.spread, s.spread, s.spread).translated(s.x, s.y);
        ChbpRadii srd = rd;
        srd.tl = std::max(0.0f, rd.tl + s.spread); srd.tr = std::max(0.0f, rd.tr + s.spread);
        srd.br = std::max(0.0f, rd.br + s.spread); srd.bl = std::max(0.0f, rd.bl + s.spread);
        p.save();
        // the shadow is not drawn under the box itself
        QPainterPath outside;
        outside.addRect(sr.adjusted(-s.blur * 2 - 2, -s.blur * 2 - 2, s.blur * 2 + 2, s.blur * 2 + 2));
        outside.addPath(chbp_round_rect(r, rd));
        outside.setFillRule(Qt::OddEvenFill);
        p.setClipPath(outside, Qt::IntersectClip);
        if (s.blur <= 0.1f) {
            p.setRenderHint(QPainter::Antialiasing, true);
            p.fillPath(chbp_round_rect(sr, srd), col);
        } else {
            const int pad = int(std::ceil(s.blur * 1.5f)) + 2;
            const int w = int(std::ceil(sr.width())), h = int(std::ceil(sr.height()));
            if (w > 0 && h > 0 && w < 8000 && h < 8000) {
                const QImage mask = chbp_blur_mask(w, h, s.blur, srd, pad);
                QImage colored(mask.size(), QImage::Format_ARGB32_Premultiplied);
                colored.fill(Qt::transparent);
                QPainter q(&colored);
                q.fillRect(colored.rect(), col);
                q.setCompositionMode(QPainter::CompositionMode_DestinationIn);
                q.drawImage(0, 0, mask);
                q.end();
                p.drawImage(QPointF(sr.x() - pad, sr.y() - pad), colored);
            }
        }
        p.restore();
    }
}

// ---- borders
void chbp_side_line(QPainter& p, BStyle st, const QColor& c, const QPointF& a, const QPointF& b, float width) {
    QPen pen(c, qreal(width));
    pen.setCapStyle(Qt::FlatCap);
    if (st == BStyle::Dashed) {
        const qreal len = QLineF(a, b).length();
        const qreal dash = std::max<qreal>(3.0, 3.0 * width); // Chrome: dashes 3× the width
        qreal gap = dash;
        const int n = std::max(1, int(std::round((len + gap) / (dash + gap))));
        if (n > 1) gap = (len - n * dash) / (n - 1);
        pen.setDashPattern({dash / width, std::max<qreal>(0.01, gap / width)});
    } else if (st == BStyle::Dotted) {
        if (width >= 3) pen.setCapStyle(Qt::RoundCap);
        const qreal len = QLineF(a, b).length();
        const qreal dot = width;
        const int n = std::max(1, int(std::round(len / (2 * dot))));
        const qreal gap = n > 1 ? (len - n * dot) / (n - 1) : dot;
        pen.setDashPattern({(width >= 3 ? 0.01 : 1.0), (width >= 3 ? (dot + gap) / width : gap / width)});
    }
    p.setPen(pen);
    p.drawLine(a, b);
}

void chbp_borders(QPainter& p, const QRectF& r, const ChbpRadii& rd, const float w[4], const BStyle s[4], const QColor c[4]) {
    bool any = false;
    for (int i = 0; i < 4; ++i) any = any || (w[i] > 0 && s[i] != BStyle::None && s[i] != BStyle::Hidden && c[i].alpha() > 0);
    if (!any) return;
    p.save();
    p.setRenderHint(QPainter::Antialiasing, rd.any());
    const bool uniform = s[0] == s[1] && s[1] == s[2] && s[2] == s[3] && c[0] == c[1] && c[1] == c[2] && c[2] == c[3];
    const QRectF inner = r.adjusted(w[3], w[0], -w[1], -w[2]);
    auto solidLike = [](BStyle st) { return st == BStyle::Solid || st == BStyle::Double || st == BStyle::Groove || st == BStyle::Ridge || st == BStyle::Inset || st == BStyle::Outset; };
    if (uniform && solidLike(s[0])) {
        QPainterPath path = chbp_round_rect(r, rd);
        path.addPath(chbp_round_rect(inner, chbp_inner_radii(rd, w[0], w[1], w[2], w[3])));
        path.setFillRule(Qt::OddEvenFill);
        QColor col = c[0];
        if (s[0] == BStyle::Outset || s[0] == BStyle::Inset) {
            // Chrome: outset top/left lighter, bottom/right darker — draw per side below instead
        } else {
            p.fillPath(path, col);
            p.restore();
            return;
        }
    }
    // per side: trapezoids between outer and inner edges (clip), then fill/stroke
    const QPointF o[4] = {r.topLeft(), r.topRight(), r.bottomRight(), r.bottomLeft()};
    const QPointF in[4] = {inner.topLeft(), inner.topRight(), inner.bottomRight(), inner.bottomLeft()};
    QPainterPath ring = chbp_round_rect(r, rd);
    ring.addPath(chbp_round_rect(inner, chbp_inner_radii(rd, w[0], w[1], w[2], w[3])));
    ring.setFillRule(Qt::OddEvenFill);
    for (int side = 0; side < 4; ++side) {
        if (w[side] <= 0 || s[side] == BStyle::None || s[side] == BStyle::Hidden || c[side].alpha() == 0) continue;
        QColor col = c[side];
        if (s[side] == BStyle::Outset || s[side] == BStyle::Inset) {
            const bool light = (s[side] == BStyle::Outset) == (side == 0 || side == 3);
            if (!light) col = col.darker(150);
        }
        QPolygonF poly;
        const int a = side, b = (side + 1) % 4;
        poly << o[a] << o[b] << in[b] << in[a];
        p.save();
        QPainterPath clip;
        clip.addPolygon(poly);
        p.setClipPath(clip.intersected(ring), Qt::IntersectClip);
        if (s[side] == BStyle::Dashed || s[side] == BStyle::Dotted) {
            QPointF pa, pb;
            const float hw = w[side] / 2;
            switch (side) {
            case 0: pa = QPointF(r.left(), r.top() + hw); pb = QPointF(r.right(), r.top() + hw); break;
            case 1: pa = QPointF(r.right() - hw, r.top()); pb = QPointF(r.right() - hw, r.bottom()); break;
            case 2: pa = QPointF(r.right(), r.bottom() - hw); pb = QPointF(r.left(), r.bottom() - hw); break;
            default: pa = QPointF(r.left() + hw, r.bottom()); pb = QPointF(r.left() + hw, r.top()); break;
            }
            chbp_side_line(p, s[side], col, pa, pb, w[side]);
        } else {
            p.fillRect(r, col);
        }
        p.restore();
    }
    p.restore();
}

// ---- painting of a box and its descendants
struct ChbpPainter {
    Document::Impl& d;
    QPainter& p;
    QRectF clipDoc; // document-space clip (unshifted)

    bool visible(const Box* b, const QPointF& shift) const {
        if (b->overflow.isEmpty() && b->kind != BoxKind::Inline) return b->w > 0 || b->h > 0;
        return b->overflow.translated(shift).intersects(clipDoc.adjusted(-2, -2, 2, 2));
    }

    void background(const Box* b, const QRectF& r) {
        if (!b->st) return;
        const ComputedStyle& s = *b->st;
        if (s.visibility != Visibility::Visible) return;
        const bool isBody = b == d.body;
        const ChbpRadii rd = chbp_radii(b, r);
        chbp_shadows(p, b, r, rd);
        const QPainterPath path = chbp_round_rect(r, rd);
        if (!isBody && s.backdropBlur && s.bg.alpha() < 255) {
            p.save(); // backdrop blur ≈ canvas colour (exact over a uniform canvas, hides content scrolled beneath)
            p.setRenderHint(QPainter::Antialiasing, rd.any());
            p.fillPath(path, d.canvas);
            p.restore();
        }
        if (!isBody && s.bg.alpha() > 0) {
            p.save();
            p.setRenderHint(QPainter::Antialiasing, rd.any());
            p.fillPath(path, s.bg);
            p.restore();
        }
        if (s.bgImages) {
            const QRectF pad = r.adjusted(b->bl, b->bt, -b->br, -b->bb);
            for (auto it = s.bgImages->rbegin(); it != s.bgImages->rend(); ++it) chbp_gradient(p, *it, pad, path);
        }
        if (b->kind == BoxKind::Cell && s.borderCollapse == BorderCollapse::Collapse) {
            collapsedBorders(b, chbp_border_rect(b)); // grid lines: centred on the unsnapped row/column edges
            return;
        }
        if (b->kind == BoxKind::Table && s.borderCollapse == BorderCollapse::Collapse) return;
        if (b->kind == BoxKind::Row || b->kind == BoxKind::RowGroup) return; // no borders in the separate model
        float w[4] = {b->bt, b->br, b->bb, b->bl};
        BStyle st[4] = {s.borderS[0], s.borderS[1], s.borderS[2], s.borderS[3]};
        QColor c[4] = {s.borderColor(0), s.borderColor(1), s.borderColor(2), s.borderColor(3)};
        chbp_borders(p, r, rd, w, st, c);
    }

    void collapsedBorders(const Box* b, const QRectF& r) {
        for (int side = 0; side < 4; ++side) {
            if (!b->collapsePaint[side] || b->collapsedB[side] <= 0) continue;
            const float w = b->collapsedB[side];
            QRectF e;
            switch (side) {
            case 0: e = QRectF(r.left() - b->collapsedB[3] / 2, r.top() - w / 2, r.width() + (b->collapsedB[3] + b->collapsedB[1]) / 2, w); break;
            case 1: e = QRectF(r.right() - w / 2, r.top() - b->collapsedB[0] / 2, w, r.height() + (b->collapsedB[0] + b->collapsedB[2]) / 2); break;
            case 2: e = QRectF(r.left() - b->collapsedB[3] / 2, r.bottom() - w / 2, r.width() + (b->collapsedB[3] + b->collapsedB[1]) / 2, w); break;
            default: e = QRectF(r.left() - w / 2, r.top() - b->collapsedB[0] / 2, w, r.height() + (b->collapsedB[0] + b->collapsedB[2]) / 2); break;
            }
            const BStyle st = b->collapsedS[side];
            const QColor col = b->collapsedC[side];
            if (st == BStyle::Dashed || st == BStyle::Dotted) {
                const bool horiz = side == 0 || side == 2;
                const QPointF a = horiz ? QPointF(e.left(), e.center().y()) : QPointF(e.center().x(), e.top());
                const QPointF z = horiz ? QPointF(e.right(), e.center().y()) : QPointF(e.center().x(), e.bottom());
                p.save();
                chbp_side_line(p, st, col, a, z, w);
                p.restore();
            } else {
                p.fillRect(e, col);
            }
        }
    }

    void decorations(const Box* textBox, const InlineFrag& f, float ox, float oy, const FontEntry& fe) {
        // own + propagated text-decoration (inline ancestors up to the formatting root and block ancestors
        // up to an atomic/positioned boundary)
        struct Deco { std::uint8_t line; QColor color; };
        std::vector<Deco> decos;
        for (const Box* a = textBox->parent; a; a = a->parent) {
            if (a->st && a->st->decoLine && a->node) decos.push_back({a->st->decoLine, a->st->decoColorCur ? a->st->color : a->st->decoColor});
            if (a->atomic || a->outOfFlow || a->kind == BoxKind::Flex || a->kind == BoxKind::Grid) break;
        }
        if (decos.empty()) return;
        const float thick = fe.underlineThickness;
        for (const Deco& dc : decos) {
            if (dc.line & 1) {
                const float y = oy + f.baseline + std::max(1.0f, std::round(fe.underlinePos));
                p.fillRect(QRectF(ox + f.x, y, f.w, thick), dc.color);
            }
            if (dc.line & 4) {
                const float y = oy + f.baseline - std::round(fe.strikePos + thick / 2);
                p.fillRect(QRectF(ox + f.x, y, f.w, thick), dc.color);
            }
            if (dc.line & 2) {
                const float y = oy + f.baseline - fe.m.asc;
                p.fillRect(QRectF(ox + f.x, y, f.w, thick), dc.color);
            }
        }
    }

    void inlineContent(const Box* b, ChbpCtx& ctx) {
        const InlineLayout& L = *b->ifc;
        const float ox = b->ax, oy = b->ay;
        // culling must see the same offsets as visible(): horizontal scroll regions (-scrollX) and sticky layers.
        // Without it, text of the tab bar scrolled past its layout x (tab ≥10) or stuck below its layout y vanished.
        const QPointF shift = p.transform().map(QPointF(0, 0)) - baseOrigin;
        // inline box backgrounds (outer first by construction order)
        for (const InlineFrag& f : L.frags) {
            if (f.type != InlineFrag::InlineBox || !f.box || f.box->kind == BoxKind::Br) continue;
            const Box* ib = f.box;
            if (chbp_creates_layer(ib)) continue;
            const ComputedStyle& s = *ib->st;
            if (s.visibility != Visibility::Visible) continue;
            const QRectF r = chbp_snap(QRectF(ox + f.x, oy + f.top, f.w, f.height));
            const ChbpRadii rd = chbp_radii(ib, r);
            if (s.bg.alpha() > 0) {
                p.save();
                p.setRenderHint(QPainter::Antialiasing, rd.any());
                p.fillPath(chbp_round_rect(r, rd), s.bg);
                p.restore();
            }
            if (s.bgImages) for (auto it = s.bgImages->rbegin(); it != s.bgImages->rend(); ++it) chbp_gradient(p, *it, r, chbp_round_rect(r, rd));
            float w[4] = {s.usedBorder(0), f.rightEdge ? s.usedBorder(1) : 0.0f, s.usedBorder(2), f.leftEdge ? s.usedBorder(3) : 0.0f};
            BStyle st[4] = {s.borderS[0], s.borderS[1], s.borderS[2], s.borderS[3]};
            QColor c[4] = {s.borderColor(0), s.borderColor(1), s.borderColor(2), s.borderColor(3)};
            chbp_borders(p, r, rd, w, st, c);
        }
        for (const InlineFrag& f : L.frags) {
            switch (f.type) {
            case InlineFrag::Text: {
                if (f.to <= f.from || !f.shape) break;
                const InlineItem& it = L.items[size_t(f.item)];
                if (it.st->visibility != Visibility::Visible) break;
                if (layerAncestorBetween(it.box, b)) break; // painted with its layer
                if (!QRectF(ox + f.x - 50, oy + f.top - 20, f.w + 100, f.height + 40).translated(shift).intersects(clipDoc)) break;
                f.shape->paint(p, QPointF(ox + f.x, oy + f.baseline), f.from, f.to, it.st->color);
                decorations(it.box, f, ox, oy, *it.fe);
                break;
            }
            case InlineFrag::Ellipsis:
                if (f.shape) f.shape->paint(p, QPointF(ox + f.x, oy + f.baseline), 0, f.shape->text.size(), b->st->color);
                break;
            case InlineFrag::Atomic:
                if (f.x < -1.0e5f) break;
                if (layerAncestorBetween(f.box, b)) break;
                paintBox(f.box, ctx);
                break;
            default: break;
            }
        }
    }

    /// True when an inline ancestor of `k` below `root` is painted as its own layer.
    bool layerAncestorBetween(const Box* k, const Box* root) const {
        for (const Box* a = k->parent; a && a != root; a = a->parent)
            if (chbp_creates_layer(a)) return true;
        return false;
    }

    void replaced(const Box* b) {
        const QRectF content(b->ax + b->bl + b->pl, b->ay + b->bt + b->pt, b->contentW(), b->contentH());
        if (b->isSvg) {
            p.save();
            p.setClipRect(content.adjusted(-0.5, -0.5, 0.5, 0.5), Qt::IntersectClip);
            svg::paint_svg(p, b->node, content);
            p.restore();
            return;
        }
        if (b->isSelect) {
            const ComputedStyle& s = *b->st;
            QString label, cur;
            // selected option: bound state value, else the first option
            QStringList values, labels;
            for (const RNode* o : b->node->kids) {
                if (o->isText || o->tag != Tag::Option) continue;
                QString l;
                for (const RNode* t : o->kids)
                    if (t->isText) l += t->text;
                const QString* v = o->src ? o->src->attr(u"value") : nullptr;
                values << (v ? *v : l.simplified());
                labels << l.simplified();
            }
            const QString bind = b->node->src ? b->node->src->bind : QString();
            const QString want = bind.isEmpty() ? QString() : d.state.get(bind);
            int idx = values.indexOf(want);
            if (idx < 0 && b->node->src && !bind.isEmpty()) idx = 0;
            if (idx < 0) idx = 0;
            label = idx < labels.size() ? labels[idx] : QString();
            static const QStringList serif{QStringLiteral("serif")};
            const FontEntry& fe = font_entry(s.fontFamily ? *s.fontFamily : serif, s.fontSize, s.fontWeight, s.fontStyle != FontStyle::Normal);
            const ShapedText& t = shape_text(fe, label, s.letterSpacing);
            const float base = b->ay + b->firstBaseline;
            p.save();
            p.setClipRect(content.adjusted(0, 0, -16, 0), Qt::IntersectClip);
            t.paint(p, QPointF(content.left() + 4, base), 0, int(label.size()), s.color);
            p.restore();
            // chevron (Chrome menulist-button arrow, ~7×4 px, stroke 1.5)
            const float ax = float(content.right()) - 12.5f, ay = float(content.center().y()) - 1.5f;
            QPen pen(s.color, 1.5);
            pen.setCapStyle(Qt::RoundCap);
            pen.setJoinStyle(Qt::RoundJoin);
            p.save();
            p.setRenderHint(QPainter::Antialiasing, true);
            p.setPen(pen);
            p.drawPolyline(QPolygonF({QPointF(ax, ay), QPointF(ax + 3.5, ay + 3.5), QPointF(ax + 7, ay)}));
            p.restore();
        }
    }

    void marker(const Box* b) {
        if (b->markerSymbol && !b->markerRect.isEmpty()) {
            const QRectF r = b->markerRect.translated(b->ax, b->ay);
            p.save();
            p.setRenderHint(QPainter::Antialiasing, true);
            if (b->markerSymbol == 1) {
                p.setPen(Qt::NoPen);
                p.setBrush(b->st->color);
                p.drawEllipse(r);
            } else if (b->markerSymbol == 2) {
                p.setPen(QPen(b->st->color, 1.0));
                p.setBrush(Qt::NoBrush);
                p.drawEllipse(r.adjusted(0.5, 0.5, -0.5, -0.5));
            } else {
                p.fillRect(r, b->st->color);
            }
            p.restore();
            return;
        }
        if (!b->markerShape) return;
        b->markerShape->paint(p, QPointF(b->ax + b->markerX, b->ay + b->markerBaseline), 0, b->markerShape->text.size(), b->st->color);
    }

    /// Paint `b` (not a layer root here) and its in-flow descendants; layers are deferred into ctx.
    void paintBox(const Box* b, ChbpCtx& ctx) {
        if (b->kind == BoxKind::Text || b->kind == BoxKind::Br || b->kind == BoxKind::Inline) {
            if (b->kind == BoxKind::Inline) // inline boxes are painted through their formatting root; recurse for layers
                for (const Box* k : b->kids) collectLayers(k, ctx);
            return;
        }
        const QPointF shift = p.transform().map(QPointF(0, 0)) - baseOrigin;
        if (!visible(b, shift) && !b->clips) {
            // still collect layers inside (they may be visible elsewhere)
            for (const Box* k : b->kids) collectLayers(k, ctx);
            return;
        }
        const QRectF r = chbp_snap(chbp_border_rect(b));
        if (b != d.body || !d.bodyImplicit) background(b, r);
        if (b->kind == BoxKind::Replaced) {
            replaced(b);
            return;
        }
        if (b->isListItem) marker(b);
        p.save();
        if (b->clips) {
            const QRectF pad = r.adjusted(b->bl, b->bt, -b->br, -b->bb);
            const ChbpRadii rd = chbp_inner_radii(chbp_radii(b, r), b->bt, b->br, b->bb, b->bl);
            if (rd.any()) p.setClipPath(chbp_round_rect(pad, rd), Qt::IntersectClip);
            else p.setClipRect(pad, Qt::IntersectClip);
        }
        if (b->regionId >= 0 && b->regionId < int(d.regions.size())) p.translate(-d.regions[size_t(b->regionId)].scrollX, 0);
        if (b->ifc) inlineContent(b, ctx);
        for (const Box* k : b->kids) {
            if (k->kind == BoxKind::Text || k->kind == BoxKind::Br) continue;
            if (chbp_creates_layer(k)) { defer(k, ctx); continue; }
            if (b->ifc && (k->atomic || k->kind == BoxKind::Inline)) {
                if (k->kind == BoxKind::Inline) for (const Box* kk : k->kids) collectLayers(kk, ctx);
                continue; // painted by inlineContent
            }
            paintBox(k, ctx);
        }
        p.restore();
    }

    /// Descend without painting to find deferred layers (inside inline boxes).
    void collectLayers(const Box* k, ChbpCtx& ctx) {
        if (k->kind == BoxKind::Text || k->kind == BoxKind::Br) return;
        if (chbp_creates_layer(k)) { defer(k, ctx); return; }
        if (k->kind == BoxKind::Inline) for (const Box* kk : k->kids) collectLayers(kk, ctx);
    }

    void defer(const Box* k, ChbpCtx& ctx) {
        ChbpDeferred df;
        df.box = const_cast<Box*>(k);
        df.xf = p.transform();
        df.hasClip = p.hasClipping();
        if (df.hasClip) df.clip = p.clipRegion();
        df.z = k->st->zAuto ? 0 : k->st->zIndex;
        df.order = k->node ? k->node->order : 0;
        if (df.z < 0) ctx.neg.push_back(df);
        else if (df.z == 0) ctx.zero.push_back(df);
        else ctx.pos.push_back(df);
    }

    /// A stacking context (or a positioned / translucent box painted as one).
    void paintLayer(const Box* b) {
        ChbpCtx ctx;
        const ComputedStyle& s = *b->st;
        const QPointF sticky = s.position == Position::Sticky ? d.sticky_offset(b) : QPointF();
        p.save();
        if (!sticky.isNull()) p.translate(sticky);
        const bool opacityLayer = s.opacity < 1.0f;
        QImage layer;
        QPainter* saved = nullptr;
        QRectF layerRect;
        QTransform savedXf;
        if (opacityLayer) {
            // render into an offscreen image, then composite with the opacity
            savedXf = p.transform();
            layerRect = savedXf.mapRect(b->overflow.isEmpty() ? chbp_border_rect(b) : b->overflow);
            const QRectF devClip = savedXf.mapRect(clipDoc);
            layerRect = layerRect.intersected(devClip.adjusted(-4, -4, 4, 4));
            if (layerRect.isEmpty()) {
                p.restore();
                return;
            }
            layerRect = layerRect.toAlignedRect();
        }
        if (opacityLayer) {
            layer = QImage(layerRect.size().toSize(), QImage::Format_ARGB32_Premultiplied);
            layer.fill(Qt::transparent);
            saved = &p;
            QPainter lp(&layer);
            lp.setRenderHints(p.renderHints());
            lp.setTransform(savedXf * QTransform::fromTranslate(-layerRect.x(), -layerRect.y()));
            ChbpPainter sub{d, lp, clipDoc, baseOrigin - layerRect.topLeft()};
            sub.paintLayerBody(b);
            lp.end();
            p.save();
            p.resetTransform();
            p.setOpacity(p.opacity() * qreal(s.opacity));
            p.drawImage(layerRect.topLeft(), layer);
            p.restore();
            Q_UNUSED(saved);
        } else {
            paintLayerBody(b);
        }
        p.restore();
    }

    void paintLayerBody(const Box* b) {
        ChbpCtx ctx;
        if (b->kind == BoxKind::Inline && !b->atomic) {
            // positioned inline box: paint its fragments + contents from the formatting root
            paintInlineLayer(b, ctx);
        } else {
            paintBox(b, ctx);
        }
        flush(ctx);
    }

    void paintInlineLayer(const Box* ib, ChbpCtx& ctx) {
        const Box* root = ib->parent;
        while (root && !root->ifc) root = root->parent;
        if (!root) return;
        const InlineLayout& L = *root->ifc;
        const ComputedStyle& s = *ib->st;
        auto inside = [&](const Box* k) {
            for (const Box* a = k; a; a = a->parent) {
                if (a == ib) return true;
                if (a == root) return false;
            }
            return false;
        };
        for (const InlineFrag& f : L.frags) {
            if (!f.box) continue;
            if (f.type == InlineFrag::InlineBox && f.box == ib) {
                const QRectF r(root->ax + f.x + ib->relX, root->ay + f.top + ib->relY, f.w, f.height);
                if (s.bg.alpha() > 0) p.fillRect(r, s.bg);
                float w[4] = {s.usedBorder(0), f.rightEdge ? s.usedBorder(1) : 0.0f, s.usedBorder(2), f.leftEdge ? s.usedBorder(3) : 0.0f};
                BStyle st[4] = {s.borderS[0], s.borderS[1], s.borderS[2], s.borderS[3]};
                QColor c[4] = {s.borderColor(0), s.borderColor(1), s.borderColor(2), s.borderColor(3)};
                chbp_borders(p, r, chbp_radii(ib, r), w, st, c);
            } else if (f.type == InlineFrag::Text && inside(f.box)) {
                const InlineItem& it = L.items[size_t(f.item)];
                f.shape->paint(p, QPointF(root->ax + f.x + ib->relX, root->ay + f.baseline + ib->relY), f.from, f.to, it.st->color);
            } else if (f.type == InlineFrag::Atomic && inside(f.box)) {
                paintBox(f.box, ctx);
            }
        }
    }

    void flush(ChbpCtx& ctx) {
        auto run = [&](std::vector<ChbpDeferred>& v) {
            std::stable_sort(v.begin(), v.end(), [](const ChbpDeferred& a, const ChbpDeferred& b) { return a.z < b.z; });
            for (const ChbpDeferred& df : v) {
                p.save();
                p.setTransform(df.xf);
                if (df.hasClip) p.setClipRegion(df.clip);
                else p.setClipping(false);
                paintLayer(df.box);
                p.restore();
            }
        };
        run(ctx.neg);
        run(ctx.zero);
        run(ctx.pos);
    }

    QPointF baseOrigin;
};

} // namespace

void chb_paint_document(Document::Impl& d, QPainter& p, const QRectF& clip) {
    p.save();
    p.fillRect(clip, d.canvas);
    p.setClipRect(clip, Qt::IntersectClip);
    p.setRenderHint(QPainter::Antialiasing, false);
    p.setRenderHint(QPainter::TextAntialiasing, true);
    if (d.body) {
        ChbpPainter pt{d, p, clip, p.transform().map(QPointF(0, 0))};
        ChbpCtx ctx;
        if (chbp_creates_layer(d.body)) pt.paintLayer(d.body);
        else {
            pt.paintBox(d.body, ctx);
            pt.flush(ctx);
        }
    }
    p.restore();
}

} // namespace fincept::screens::chb
