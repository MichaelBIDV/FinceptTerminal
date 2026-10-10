// src/screens/hdcv_launchpad/HlpDomPaint.cpp
// Launchpad CSS engine — painting: backgrounds, borders (rounded, per-side colours, collapsed table
// borders), inset box-shadow, text runs, sticky layers, WebKit scrollbars — snapped the way Chrome
// snaps them on the page's pixel grid; plus the harness geometry dump and innerText.
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

// ---- painting ----
QColor ViewImpl::colorOf(const Box* b, const QColor& inherited) const {
    QColor c = inherited;
    if (b->st && b->st->color)
        c = *b->st->color;
    if (b->st && b->st->hoverColor && hovered(b))
        c = *b->st->hoverColor;
    return c;
}

QRectF ViewImpl::snapped(const QRectF& r) const {
    // snap on the page's pixel grid as seen from the scroller's contents layer (scroll offsets move the
    // rastered layer afterwards, unsnapped): the view's origin can be fractional (setSubpixelGeometry)
    // and the layer shifted by half a pixel (scrollerShift)
    const float l = snap(float(r.left()) + pox) - pox, t = snap(float(r.top()) + poy) - poy;
    const float rr = snap(float(r.right()) + pox) - pox, bb = snap(float(r.bottom()) + poy) - poy;
    return QRectF(l, t, rr - l, bb - t);
}

float ViewImpl::baselineY(float v) const {
    return snapBaseline(v + poy) - poy;
}

QPainterPath ViewImpl::rrect(const QRectF& r, const float rad[4]) {
    QPainterPath p;
    const float mx = float(std::min(r.width(), r.height())) / 2.0f;
    const float tl = std::min(rad[0], mx), tr = std::min(rad[1], mx), br = std::min(rad[2], mx),
                bl = std::min(rad[3], mx);
    if (tl <= 0 && tr <= 0 && br <= 0 && bl <= 0) {
        p.addRect(r);
        return p;
    }
    p.moveTo(r.left() + tl, r.top());
    p.lineTo(r.right() - tr, r.top());
    if (tr > 0)
        p.arcTo(QRectF(r.right() - 2 * tr, r.top(), 2 * tr, 2 * tr), 90, -90);
    p.lineTo(r.right(), r.bottom() - br);
    if (br > 0)
        p.arcTo(QRectF(r.right() - 2 * br, r.bottom() - 2 * br, 2 * br, 2 * br), 0, -90);
    p.lineTo(r.left() + bl, r.bottom());
    if (bl > 0)
        p.arcTo(QRectF(r.left(), r.bottom() - 2 * bl, 2 * bl, 2 * bl), 270, -90);
    p.lineTo(r.left(), r.top() + tl);
    if (tl > 0)
        p.arcTo(QRectF(r.left(), r.top(), 2 * tl, 2 * tl), 180, -90);
    p.closeSubpath();
    return p;
}

/// inner border path: radii shrink by the adjacent border widths (per axis)
QPainterPath ViewImpl::innerPath(const QRectF& o, const float rad[4], const float bw[4], float shrink, QPointF shift) {
    const QRectF in = o.adjusted(bw[3] + shrink, bw[0] + shrink, -bw[1] - shrink, -bw[2] - shrink)
                          .translated(shift);
    QPainterPath p;
    if (in.width() <= 0 || in.height() <= 0)
        return p;
    auto ell = [shrink](float r, float a) { return std::max(0.0f, r - a - shrink); };
    // elliptical corners: (rx, ry)
    const float tlx = ell(rad[0], bw[3]), tly = ell(rad[0], bw[0]);
    const float trx = ell(rad[1], bw[1]), try_ = ell(rad[1], bw[0]);
    const float brx = ell(rad[2], bw[1]), bry = ell(rad[2], bw[2]);
    const float blx = ell(rad[3], bw[3]), bly = ell(rad[3], bw[2]);
    p.moveTo(in.left() + tlx, in.top());
    p.lineTo(in.right() - trx, in.top());
    if (trx > 0 && try_ > 0)
        p.arcTo(QRectF(in.right() - 2 * trx, in.top(), 2 * trx, 2 * try_), 90, -90);
    else
        p.lineTo(in.right(), in.top());
    p.lineTo(in.right(), in.bottom() - bry);
    if (brx > 0 && bry > 0)
        p.arcTo(QRectF(in.right() - 2 * brx, in.bottom() - 2 * bry, 2 * brx, 2 * bry), 0, -90);
    else
        p.lineTo(in.right(), in.bottom());
    p.lineTo(in.left() + blx, in.bottom());
    if (blx > 0 && bly > 0)
        p.arcTo(QRectF(in.left(), in.bottom() - 2 * bly, 2 * blx, 2 * bly), 270, -90);
    else
        p.lineTo(in.left(), in.bottom());
    p.lineTo(in.left(), in.top() + tly);
    if (tlx > 0 && tly > 0)
        p.arcTo(QRectF(in.left(), in.top(), 2 * tlx, 2 * tly), 180, -90);
    else
        p.lineTo(in.left(), in.top());
    p.closeSubpath();
    return p;
}

namespace {

/// rrect() radii (each clamped to half the smaller side) as Radii4.
Radii4 hlpdp_radii(const QRectF& r, const float rad[4]) {
    const double mx = std::min(r.width(), r.height()) / 2.0;
    Radii4 k;
    for (int i = 0; i < 4; ++i) {
        const double v = std::min(double(rad[i]), mx);
        k.c[i] = QPointF(std::max(0.0, v), std::max(0.0, v));
    }
    return k;
}

/// innerPath() geometry as rect + Radii4: inset by the side widths, radii shrink per axis.
QRectF hlpdp_inner(const QRectF& o, const float rad[4], const float bw[4], Radii4& k) {
    const Radii4 ok = hlpdp_radii(o, rad);
    const float hx[4] = {bw[3], bw[1], bw[1], bw[3]}, vy[4] = {bw[0], bw[0], bw[2], bw[2]};
    for (int i = 0; i < 4; ++i)
        k.c[i] = QPointF(std::max(0.0, ok.c[i].x() - hx[i]), std::max(0.0, ok.c[i].y() - vy[i]));
    return o.adjusted(bw[3], bw[0], -bw[1], -bw[2]);
}


/// .tile border-left on a rounded box: fillLeftBorderRRect (HlpTheme.cpp) — false for other shapes.
bool hlpdp_leftBorder(QPainter& p, const QRectF& sr, const float rad[4], const float bw[4], const QColor& c) {
    if (!(bw[3] > 0.0f && bw[0] <= 0.0f && bw[1] <= 0.0f && bw[2] <= 0.0f))
        return false;
    Radii4 ik;
    const QRectF in = hlpdp_inner(sr, rad, bw, ik);
    return fillLeftBorderRRect(p, sr, hlpdp_radii(sr, rad), in, ik, c);
}

/// A clip rect on the half-pixel grid (content coords; the layer grid is offset by ox, oy) as whole-pixel
/// parts with their coverage: the interior at 1, a half-covered edge column / row at 0.5, corners at the
/// product. Parts are integer on the layer grid, so Qt's aliased clip keeps exactly those pixels.
QVector<QPair<QRectF, qreal>> hlpdp_clipParts(const QRectF& r, float ox, float oy) {
    const double L = r.left() + ox, T = r.top() + oy, R = r.right() + ox, B = r.bottom() + oy;
    const double il = std::ceil(L), it = std::ceil(T), ir = std::floor(R), ib = std::floor(B);
    const double xs[3][3] = {{il - 1, il, il - L}, {il, ir, 1.0}, {ir, ir + 1, R - ir}};
    const double ys[3][3] = {{it - 1, it, it - T}, {it, ib, 1.0}, {ib, ib + 1, B - ib}};
    QVector<QPair<QRectF, qreal>> out;
    for (const auto& y : ys)
        for (const auto& x : xs)
            if (x[1] > x[0] && y[1] > y[0] && x[2] * y[2] > 1e-6)
                out.push_back({QRectF(QPointF(x[0] - ox, y[0] - oy), QPointF(x[1] - ox, y[1] - oy)), x[2] * y[2]});
    return out;
}

} // namespace

void ViewImpl::paintBoxDecor(QPainter& p, const Box* b, const QRectF& r, const QColor& color, bool collapsedCell, DecorPart part) {
    const Style* st = b->st;
    if (!st)
        return;
    QColor bg = st->bg;
    if (st->hoverBg && hovered(b))
        bg = *st->hoverBg;
    const bool anyBorder = st->bw[0] > 0 || st->bw[1] > 0 || st->bw[2] > 0 || st->bw[3] > 0;
    const bool rounded = st->radius[0] > 0 || st->radius[1] > 0 || st->radius[2] > 0 || st->radius[3] > 0;
    const bool shadow = st->boxShadowInset && st->boxShadowInset->color.isValid() &&
                        st->boxShadowInset->color.alpha() > 0 && !collapsedCell;
    if (!bg.isValid() && !anyBorder && !shadow)
        return;
    const QRectF sr = snapped(r);
    p.setRenderHint(QPainter::Antialiasing, true);
    if (part != DecorBorder && bg.isValid() && bg.alpha() > 0) {
        if (rounded && anyBorder && !collapsedCell) {
            // Blink's background bleed avoidance for a rounded box with a border: the background stops
            // half the border width inside the border edge (measured: .pnl, .wd-it, pressed .chip —
            // the outer half-pixel of a border shows what is BELOW the box, not its background)
            const float half[4] = {st->bw[0] / 2.0f, st->bw[1] / 2.0f, st->bw[2] / 2.0f, st->bw[3] / 2.0f};
            Radii4 k;
            const QRectF in = hlpdp_inner(sr, st->radius, half, k);
            fillRRect(p, in, k, bg);
        } else if (rounded) {
            fillRRect(p, sr, hlpdp_radii(sr, st->radius), bg);
        } else {
            p.fillRect(sr, bg);
        }
    }
    if (part != DecorBorder && shadow) {
        // CSS Backgrounds §7.1.1: an inset shadow fills the padding box outside a "hole" = the
        // padding box moved by (x, y) and shrunk by spread (radii shrink with it)
        const Style::InsetShadow& sh = *st->boxShadowInset;
        const float zero[4] = {0, 0, 0, 0};
        const QPainterPath pad = innerPath(sr, rounded ? st->radius : zero, st->bw);
        // The hole ends at the BORDER edge on sides that have a border (measured: .wd-it[aria-current],
        // border-bottom 1px at 220.5–221.5 shows no shadow seam in row 220; its border-less top edge at
        // 221.5 does show the 25% seam) …
        QPainterPath hole = innerPath(sr, rounded ? st->radius : zero, st->bw, sh.spread, QPointF(sh.x, sh.y));
        if (!hole.isEmpty()) {
            // … but only along the straight part: the corner arcs keep the padding-box hole
            const QRectF hb = hole.boundingRect();
            const float rmax = rounded ? *std::max_element(st->radius, st->radius + 4) : 0.0f;
            QPainterPath ext;
            if (st->bw[0] > 0 && hb.width() > 2 * rmax)
                ext.addRect(QRectF(hb.left() + rmax, hb.top() - st->bw[0], hb.width() - 2 * rmax, st->bw[0] + 1));
            if (st->bw[2] > 0 && hb.width() > 2 * rmax)
                ext.addRect(QRectF(hb.left() + rmax, hb.bottom() - 1, hb.width() - 2 * rmax, st->bw[2] + 1));
            if (st->bw[3] > 0 && hb.height() > 2 * rmax)
                ext.addRect(QRectF(hb.left() - st->bw[3], hb.top() + rmax, st->bw[3] + 1, hb.height() - 2 * rmax));
            if (st->bw[1] > 0 && hb.height() > 2 * rmax)
                ext.addRect(QRectF(hb.right() - 1, hb.top() + rmax, st->bw[1] + 1, hb.height() - 2 * rmax));
            if (!ext.isEmpty())
                hole = hole.united(ext);
        }
        const QTransform dt = p.deviceTransform();
        if (!hole.isEmpty() && dt.type() <= QTransform::TxTranslate) {
            // Skia draws it as drawDRRect: per-pixel coverage outer × (1 − inner), so where both edges
            // share a half pixel (fractional box) a faint seam of the shadow colour shows — measured
            // on .wd-it[aria-current] at 330.5/10.3. A device-aligned layer with DestinationOut gives
            // exactly that coverage.
            const QRect dev = dt.mapRect(pad.boundingRect()).toAlignedRect().adjusted(-1, -1, 1, 1);
            QImage layer(dev.size(), QImage::Format_ARGB32_Premultiplied);
            layer.fill(Qt::transparent);
            QPainter lp(&layer);
            lp.setRenderHint(QPainter::Antialiasing, true);
            lp.translate(dt.dx() - dev.x(), dt.dy() - dev.y());
            lp.fillPath(pad, sh.color);
            lp.setCompositionMode(QPainter::CompositionMode_DestinationOut);
            lp.fillPath(hole, Qt::black);
            lp.end();
            // logical position of the device-aligned rect (translation-only transform → exact blit)
            p.drawImage(QPointF(dev.x() - dt.dx(), dev.y() - dt.dy()), layer);
        } else {
            p.fillPath(hole.isEmpty() ? pad : pad.subtracted(hole), sh.color);
        }
    }
    if (!anyBorder || part == DecorBg)
        return;
    QColor bc[4];
    for (int i = 0; i < 4; ++i) {
        bc[i] = st->bc[i].isValid() ? st->bc[i] : color;
        if (st->hoverBorderColor && hovered(b))
            bc[i] = *st->hoverBorderColor;
    }
    if (collapsedCell) {
        // collapsed borders are centred on the cell edges (half in each neighbour); each cell paints its
        // own segment on the half-pixel grid. A segment that straddles two rows (50% each) covers, across
        // the row, the WHOLE pixels its snapped extent touches: a column boundary on a .5 is painted by
        // both cells (0.5 over 0.5 = 75%), a table edge on a .5 fully; one that fills a whole row keeps
        // its .5 ends at half coverage (measured on 11 tables, 27/09: 970.7 → pixel 970 at 75%, 1485.5 →
        // 1485 full; ĐIỂM NGÀNH whole-row borders end at 1977.5 → half; on the layer grid of the scroller)
        const auto seg = [&](float y0, float h, const QColor& c) {
            QRectF s = snapped(QRectF(r.left(), y0, r.width(), h));
            if (s.top() + poy != std::floor(s.top() + poy)) {
                const double L = std::floor(s.left() + pox) - pox, R = std::ceil(s.right() + pox) - pox;
                s = QRectF(L, s.top(), R - L, s.height());
            }
            p.fillRect(s, c);
        };
        if (st->bw[2] > 0)
            seg(float(r.bottom()) - st->bw[2] / 2.0f, st->bw[2], bc[2]);
        if (st->bw[0] > 0)
            seg(float(r.top()) - st->bw[0] / 2.0f, st->bw[0], bc[0]);
        return;
    }
    float bw[4];
    for (int i = 0; i < 4; ++i)
        bw[i] = st->bw[i];
    const bool uniformColor = (bw[0] == 0 || bc[0] == bc[3] || bw[3] == 0) && [&] {
        QColor first;
        for (int i = 0; i < 4; ++i) {
            if (bw[i] <= 0)
                continue;
            if (!first.isValid())
                first = bc[i];
            else if (bc[i] != first)
                return false;
        }
        return true;
    }();
    if (!rounded) {
        // plain rectangles per side (corners belong to the top/bottom sides)
        if (bw[0] > 0)
            p.fillRect(snapped(QRectF(r.left(), r.top(), r.width(), bw[0])), bc[0]);
        if (bw[2] > 0)
            p.fillRect(snapped(QRectF(r.left(), r.bottom() - bw[2], r.width(), bw[2])), bc[2]);
        if (bw[3] > 0)
            p.fillRect(snapped(QRectF(r.left(), r.top() + bw[0], bw[3], r.height() - bw[0] - bw[2])), bc[3]);
        if (bw[1] > 0)
            p.fillRect(snapped(QRectF(r.right() - bw[1], r.top() + bw[0], bw[1], r.height() - bw[0] - bw[2])),
                       bc[1]);
        return;
    }
    p.setRenderHint(QPainter::Antialiasing, true);
    if (uniformColor) {
        QColor c;
        for (int i = 0; i < 4; ++i)
            if (bw[i] > 0) {
                c = bc[i];
                break;
            }
        if (bw[0] > 0 && bw[1] > 0 && bw[2] > 0 && bw[3] > 0) {
            // all four sides: Skia's drawDRRect (per-pixel outer × (1 − inner) coverage)
            Radii4 hk;
            const QRectF hole = hlpdp_inner(sr, st->radius, bw, hk);
            fillRRect(p, sr, hlpdp_radii(sr, st->radius), c, &hole, &hk);
        } else if (!hlpdp_leftBorder(p, sr, st->radius, bw, c)) {
            // some sides without border: Chrome clips the ring to the bordered sides, so no product seam
            // along a zero-width side — the geometric ring does that
            p.fillPath(rrect(sr, st->radius).subtracted(innerPath(sr, st->radius, bw)), c);
        }
    } else {
        const QPainterPath ring = rrect(sr, st->radius).subtracted(innerPath(sr, st->radius, bw));
        // per side: clip the ring with the trapezoid of that side
        const QPointF o[4] = {sr.topLeft(), sr.topRight(), sr.bottomRight(), sr.bottomLeft()};
        const QRectF in = sr.adjusted(bw[3], bw[0], -bw[1], -bw[2]);
        const QPointF i4[4] = {in.topLeft(), in.topRight(), in.bottomRight(), in.bottomLeft()};
        const int sideCorners[4][2] = {{0, 1}, {1, 2}, {2, 3}, {3, 0}};
        for (int s = 0; s < 4; ++s) {
            if (bw[s] <= 0)
                continue;
            QPainterPath trap;
            trap.moveTo(o[sideCorners[s][0]]);
            trap.lineTo(o[sideCorners[s][1]]);
            trap.lineTo(i4[sideCorners[s][1]]);
            trap.lineTo(i4[sideCorners[s][0]]);
            trap.closeSubpath();
            p.fillPath(ring.intersected(trap), bc[s]);
        }
    }
    p.setRenderHint(QPainter::Antialiasing, false);
}

void ViewImpl::paintText(QPainter& p, const Box* container, const Line& L, const Frag& fr, const QColor& color, bool underline) {
    const Box* tb = fr.box;
    const IItem& it = container->ifc->items[fr.item];
    const int a = fr.from - it.start, b = fr.to - it.start;
    if (b <= a)
        return;
    const float x = container->ax + fr.x;
    const float by = baselineY(container->ay + L.baseline);
    const float half = snap(container->ay + L.baseline + poy); // Chrome's text origin (half pixel)
    detail::drawShaped(p, tb->cs->font, *tb->shaped, a + tb->shapedOff, b + tb->shapedOff, QPointF(x, by), tb->cs->ls,
                       color, half - std::floor(half + 0.5f));
    if (underline)
        paintUnderline(p, tb, a + tb->shapedOff, b + tb->shapedOff, x, half - poy, fr.w, color);
}

void ViewImpl::paintIfc(QPainter& p, Box* b, const QColor& inherited, bool underlineInh, const QRectF& clip) {
    IFC& f = *b->ifc;
    for (const Line& L : f.lines) {
        const float top = b->ay + L.top;
        if (top > clip.bottom() || top + L.height < clip.top())
            continue;
        for (const Frag& fr : L.frags) {
            if (fr.box->kind == BK::Atomic) {
                // colour/underline inherited through the inline ancestors
                QColor c = inherited;
                bool ul = underlineInh;
                QVector<const Box*> chain;
                for (const Box* q2 = fr.box->parent; q2 && q2 != b; q2 = q2->parent)
                    chain.push_front(q2);
                for (const Box* q2 : chain) {
                    c = colorOf(q2, c);
                    ul = ul || (q2->st && (q2->st->underline || (q2->st->hoverUnderline && hovered(q2))));
                }
                paintBox(p, fr.box, c, ul, clip);
                continue;
            }
            QColor c = inherited;
            bool ul = underlineInh;
            QVector<const Box*> chain;
            for (const Box* q2 = fr.box; q2 && q2 != b; q2 = q2->parent)
                chain.push_front(q2);
            for (const Box* q2 : chain) {
                c = colorOf(q2, c);
                ul = ul || (q2->st && (q2->st->underline || (q2->st->hoverUnderline && hovered(q2))));
            }
            paintText(p, b, L, fr, c, ul);
        }
        if (L.ellX >= 0) {
            auto s = detail::shape(b->cs->font, QStringLiteral("…"));
            detail::drawShaped(p, b->cs->font, *s, 0, 1, QPointF(b->ax + L.ellX, baselineY(b->ay + L.baseline)),
                               b->cs->ls, inherited);
        }
    }
}

void ViewImpl::paintBox(QPainter& p, Box* b, const QColor& inherited, bool underlineInh, const QRectF& clip, bool stickyPass) {
    if (!stickyPass && b->kind != BK::Cell && b->st && b->st->sticky && stickyShift(b) > 0)
        return; // painted on top later
    const float shift = stickyPass ? stickyShift(b) : 0.0f;
    const QRectF r(b->ax, b->ay + shift, b->w, b->h);
    if (b->kind != BK::Inline && b->kind != BK::Text && !stickyPass) {
        if (r.top() > clip.bottom() + 1 || r.bottom() < clip.top() - 1)
            return;
    }
    const QColor color = colorOf(b, inherited);
    const bool ul = underlineInh || (b->st && (b->st->underline || (b->st->hoverUnderline && hovered(b))));
    const float op = b->st ? b->st->opacity : 1.0f;
    if (op < 1.0f) {
        p.save();
        p.setOpacity(p.opacity() * op);
    }
    if (stickyPass) {
        p.save();
        p.translate(0, shift);
    }
    // table cells: background here, collapsed borders are painted by the table (paintTable)
    const bool isRoot = doc && b == doc->root;
    if (!(stripPass && isRoot))
        paintBoxDecor(p, b, QRectF(b->ax, b->ay, b->w, b->h), color, b->kind == BK::Cell,
                      b->kind == BK::Cell ? DecorBg : DecorAll);
    const bool rootClip = !stickyPass && isRoot && !stripPass;
    if (rootClip) {
        p.save();
        clipContent(p);
    }
    if (b->custom && b->node->customPaint) {
        const Style* st = b->st;
        const QRectF cb(b->ax + st->pl + st->bw[3], b->ay + st->pt + st->bw[0],
                        b->w - st->pl - st->pr - st->bw[1] - st->bw[3],
                        b->h - st->pt - st->pb - st->bw[0] - st->bw[2]);
        p.save();
        p.setRenderHint(QPainter::Antialiasing, true); // SVG in Chrome is antialiased
        b->node->customPaint(p, cb);
        p.restore();
    } else if (b->ifc) {
        if (b->st && (b->st->lineClamp > 0 || b->st->ellipsis)) {
            // overflow:hidden of the box itself: Chrome clips at the border box snapped to the half-pixel
            // grid, a half-pixel edge keeping its column / row at 50% coverage (the Đ of ĐIỂM NGÀNH
            // overhangs its h2 at x 1357.3 → column 1357 at half the glyph's coverage, 27/09)
            for (const auto& [part, cov] : hlpdp_clipParts(snapped(QRectF(b->ax, b->ay, b->w, b->h)), pox, poy)) {
                p.save();
                p.setClipRect(part, Qt::IntersectClip);
                p.setOpacity(p.opacity() * cov);
                paintIfc(p, b, color, ul, clip);
                p.restore();
            }
        } else {
            paintIfc(p, b, color, ul, clip);
        }
    } else if (b->kind == BK::Table) {
        paintTable(p, b, color, ul, clip);
    } else {
        for (Box* k : b->kids)
            paintBox(p, k, color, ul, clip);
    }
    if (rootClip)
        p.restore();
    if (b->node && b->node == focusNode && focusVisible && q->hasFocus() && b->node->focusRing.isValid()) {
        // :focus-visible{outline:1px solid;outline-offset:-1px} — the band just inside the border box
        const QRectF sr = snapped(QRectF(b->ax, b->ay, b->w, b->h));
        Radii4 k = hlpdp_radii(sr, b->st->radius), hk;
        const float one[4] = {1, 1, 1, 1};
        const QRectF hole = hlpdp_inner(sr, b->st->radius, one, hk);
        fillRRect(p, sr, k, b->node->focusRing, &hole, &hk);
    }
    if (stickyPass)
        p.restore();
    if (op < 1.0f)
        p.restore();
}

void ViewImpl::clipContent(QPainter& p) const {
    const QRectF& c = contentClip;
    if (c.isEmpty() || stripPass)
        return;
    const QRectF in(QPointF(std::ceil(c.left()), std::ceil(c.top())), QPointF(std::floor(c.right()), std::floor(c.bottom())));
    p.setClipRect(in.translated(-paintOrigin()), Qt::IntersectClip);
}

void ViewImpl::paintEdgeStrips(QPainter& p, const QRect& dirty) {
    const QRectF& c = contentClip;
    if (c.isEmpty() || !doc || !doc->root)
        return;
    const int l = int(std::floor(c.left())), t = int(std::floor(c.top()));
    const int r = int(std::ceil(c.right())), b = int(std::ceil(c.bottom()));
    const int il = int(std::ceil(c.left())), it = int(std::ceil(c.top()));
    const int ir = int(std::floor(c.right())), ib = int(std::floor(c.bottom()));
    QVector<QRect> strips;
    if (it != t)
        strips.push_back(QRect(l, t, r - l, 1));
    if (ib != b)
        strips.push_back(QRect(l, ib, r - l, 1));
    // left/right columns only matter when content reaches the side edge (horizontal overflow)
    if (hbar && il != l)
        strips.push_back(QRect(l, it, 1, ib - it));
    if (hbar && ir != r)
        strips.push_back(QRect(ir, it, 1, ib - it));
    const QPointF o = paintOrigin();
    for (const QRect& sr : strips) {
        const QRect d = sr.intersected(dirty);
        if (d.isEmpty())
            continue;
        QImage img(d.size(), QImage::Format_ARGB32_Premultiplied);
        img.fill(Qt::transparent);
        {
            QPainter ip(&img);
            ip.setRenderHint(QPainter::TextAntialiasing, true);
            ip.translate(QPointF(o.x() - d.x(), o.y() - d.y()));
            const QRectF lc = QRectF(d).translated(-o);
            ip.setClipRect(lc);
            stripPass = true;
            paintBox(ip, doc->root, rootCS().color, false, lc);
            paintStickies(ip, lc);
            stripPass = false;
        }
        p.save();
        p.setClipRect(d);
        p.setOpacity(0.5);
        p.drawImage(d.topLeft(), img);
        p.restore();
    }
}

void ViewImpl::paintStickies(QPainter& p, const QRectF& clip) {
    p.save();
    clipContent(p);
    for (Box* sb : doc->stickies) {
        if (sb->kind == BK::Cell || stickyShift(sb) <= 0)
            continue; // table cells are painted by paintTable
        // inherited colour along the ancestor chain
        QVector<Box*> chain;
        for (Box* a = sb->parent; a; a = a->parent)
            chain.push_front(a);
        QColor c = rootCS().color;
        bool ul = false;
        for (Box* a : chain) {
            c = colorOf(a, c);
            ul = ul || (a->st && a->st->underline);
        }
        paintBox(p, sb, c, ul, clip, true);
    }
    p.restore();
}

void ViewImpl::paintScrollbars(QPainter& p) {
    constexpr double kThumbHalfW = 6.75;
    // border-radius:4px on a 7px-wide thumb: CSS scales BOTH radii by 7/8 → circular 3.5px ends (Qt's
    // addRoundedRect clamps only the short axis → 3.5×4 ellipses, a 10–20/255 seam on the head and tail)
    const auto thumbRad = [](const QRectF& r) { return 4.0 * std::min({1.0, r.width() / 8.0, r.height() / 8.0}); };
    const QRectF s = sub();
    p.setRenderHint(QPainter::Antialiasing, true);
    const QColor thumb = pal().line2;
    // A thumb whose leading end sits on a whole pixel comes out of Chrome with Skia's analytic coverage
    // (fillRRect, exact to 1/255 on SỔ NGUỒN / RÀ SOÁT / THƯ VIỆN); one that starts on a .5 has softer
    // ends that Qt's path coverage follows more closely (2 labs of 71 real thumbs, 27/09 — fixer2r2/).
    const auto fillThumb = [&](const QRectF& r, double lead) {
        if (lead == std::floor(lead)) {
            fillRRect(p, r, Radii4::all(thumbRad(r)), thumb);
            return;
        }
        QPainterPath path;
        path.addRoundedRect(r, thumbRad(r), thumbRad(r));
        p.fillPath(path, thumb);
    };
    if (vbar) {
        const QRectF t = vThumb();
        // right edge on the half-pixel grid; the thumb is 7px on a whole-pixel edge and 6.75px on a half
        // one (measured: MÔ TẢ .bd right 1993 → 1986–1993; CỔNG 497.5 → 490.75–497.5; VN-INDEX 1328.33 →
        // 1321.75–1328.5)
        const double right = snap(float(s.x() + viewW()));
        const double tw = right == std::floor(right) ? double(kScrollbar) : kThumbHalfW;
        const QRectF r(right - tw, t.top(), tw, t.height());
        fillThumb(r, r.top());
    }
    if (hbar) {
        const QRectF r = hThumb();
        fillThumb(r, r.left());
    }
    if (vbar && hbar) {
        // index.html styles only the bars and the thumb: Chrome paints the default ::-webkit-scrollbar-
        // corner, WHITE in both themes (measured: CHÍNH PHỦ .bd, 255 on the half-pixel grid)
        const QRectF c(s.x() + viewW() - kScrollbar, s.y() + viewH() - kScrollbar, kScrollbar, kScrollbar);
        p.fillRect(QRectF(QPointF(snap(float(c.left())), snap(float(c.top()))),
                          QPointF(snap(float(c.right())), snap(float(c.bottom())))),
                   Qt::white);
    }
    p.setRenderHint(QPainter::Antialiasing, false);
}

namespace {

/// Blink's ScrollbarTheme::ThumbLength / ThumbPosition, in the scrollbar's device units (zoom 2 = half
/// CSS pixels): the frame on the half-pixel grid, length = round(visible / total × track), at least
/// 26px, position truncated with (0, 1) → 1. Returns {start, length} in CSS px. Measured on the thumb
/// ends (beri CHUYỂN ĐỘNG NGÀNH .bd 64.695 + 300, content 429: 64.5 → 274.5, not 64.695 → 274.49;
/// a 300px .bd over 320 / 700 / 2758 / 4431+ px: 281.5 / 128.5 / 32.5 / 26 — 27/09).
QPair<double, double> hlpdp_thumb(double frameStart, double frameLen, double visible, double total, double scroll) {
    const double a = std::floor(frameStart * 2.0 + 0.5) / 2.0, b = std::floor((frameStart + frameLen) * 2.0 + 0.5) / 2.0;
    const int track = int(std::lround((b - a) * 2.0));
    const int vis = int(std::lround(visible * 2.0)), tot = int(std::lround(total * 2.0));
    int len = tot > 0 ? int(std::lround(double(vis) / double(tot) * track)) : track;
    len = std::min(std::max(len, 52), track);
    int pos = 0;
    if (tot > vis) {
        const double f = std::max(0.0, scroll) * 2.0 * double(track - len) / double(tot - vis);
        pos = (f > 0.0 && f < 1.0) ? 1 : int(f);
    }
    return {a + pos / 2.0, len / 2.0};
}

} // namespace

QRectF ViewImpl::vThumb() const {
    const QRectF s = sub();
    const auto t = hlpdp_thumb(s.y(), portH(), portH(), contentH, scrollY);
    return QRectF(s.x() + viewW() - kScrollbar, t.first, kScrollbar, t.second);
}

QRectF ViewImpl::hThumb() const {
    const QRectF s = sub();
    const auto t = hlpdp_thumb(s.x(), layoutW(), layoutW(), overflowW, scrollX);
    return QRectF(t.first, s.y() + viewH() - kScrollbar, t.second, kScrollbar);
}

// ---- dump / text ----
void ViewImpl::dumpBox(const Box* b, QJsonArray& out, const QPointF& off) const {
    if (b->node && !b->node->key.isEmpty() && b->kind != BK::Text && b->kind != BK::Inline) {
        QJsonObject o;
        o["key"] = b->node->key;
        o["x"] = double(b->ax + off.x());
        o["y"] = double(b->ay + off.y());
        o["w"] = double(b->w);
        o["h"] = double(b->h);
        out.append(o);
    }
    const bool ownText = b->kind == BK::Text && b->parent && b->parent->node == b->node;
    if ((b->kind == BK::Inline || b->kind == BK::Text) && b->node && !b->node->key.isEmpty() && !ownText) {
        for (const QRectF& r : b->inlineRects) {
            QJsonObject o;
            o["key"] = b->node->key;
            o["x"] = r.x() + off.x();
            o["y"] = r.y() + off.y();
            o["w"] = r.width();
            o["h"] = r.height();
            out.append(o);
        }
    }
    if (b->ifc) {
        // keyed inline boxes (spans): the union of their line rects, like getBoundingClientRect()
        for (const IItem& it : b->ifc->items) {
            if (it.t != IItem::Open || !it.box->node || it.box->node->key.isEmpty())
                continue;
            if (it.box->kind == BK::Text && it.box->parent && it.box->parent->node == it.box->node)
                continue;
            QRectF u;
            for (const QRectF& r : it.box->inlineRects)
                u = u.isNull() ? r : u.united(r);
            if (!u.isNull()) {
                const QRectF& r = u;
                QJsonObject o;
                o["key"] = it.box->node->key;
                o["x"] = r.x() + off.x();
                o["y"] = r.y() + off.y();
                o["w"] = r.width();
                o["h"] = r.height();
                o["inline"] = true;
                out.append(o);
            }
        }
        for (const Line& L : b->ifc->lines) {
            for (const Frag& fr : L.frags) {
                if (fr.box->kind == BK::Atomic) {
                    dumpBox(fr.box, out, off);
                    continue;
                }
                const IItem& it = b->ifc->items[fr.item];
                const CS& cs = *fr.box->cs;
                QJsonObject o;
                o["text"] = fr.box->text.mid(fr.from - it.start, fr.to - fr.from);
                if (fr.box->node && !fr.box->node->key.isEmpty())
                    o["key"] = fr.box->node->key;
                o["x"] = double(b->ax + fr.x + off.x());
                o["y"] = double(b->ay + L.baseline - cs.vm.ascent + off.y());
                o["w"] = double(fr.w);
                o["h"] = double(cs.vm.ascent + cs.vm.descent);
                o["baseline"] = double(b->ay + L.baseline + off.y());
                out.append(o);
            }
        }
        return;
    }
    for (const Box* k : b->kids)
        dumpBox(k, out, off);
}

void ViewImpl::textOf(const Box* b, QString& out) const {
    auto nl = [&]() {
        if (!out.isEmpty() && !out.endsWith(u'\n'))
            out += u'\n';
    };
    if (b->custom && b->node && !b->node->customText.isEmpty()) {
        nl();
        out += b->node->customText; // text the web draws as HTML where we paint (chart labels)
        return;
    }
    if (b->ifc) {
        nl();
        // innerText: collapsed paragraph text, inline-blocks contribute their own text, <br> → newline
        QString s;
        for (const IItem& it : b->ifc->items) {
            if (it.t == IItem::Text)
                s += it.box->text;
            else if (it.t == IItem::Br)
                s += u'\n';
            else if (it.t == IItem::Atomic) {
                QString inner;
                textOf(it.box, inner);
                s += inner.trimmed();
            }
        }
        out += s.trimmed();
        return;
    }
    if (b->kind == BK::Table) {
        for (const Box* r : b->kids) {
            nl();
            bool firstCell = true;
            for (const Box* c : r->kids) {
                if (!firstCell)
                    out += u'\t';
                QString cs;
                textOf(c, cs);
                out += cs.trimmed(); // a block inside a cell keeps its line break (innerText)
                if (!c->ifc && !c->kids.isEmpty() && !isInlineLevel(c->kids.last()))
                    out += u'\n'; // …and after a trailing block
                firstCell = false;
            }
        }
        return;
    }
    for (const Box* k : b->kids) {
        if (!isInlineLevel(k))
            nl();
        textOf(k, out);
    }
}

} // namespace fincept::screens::hlp::hlpdom
