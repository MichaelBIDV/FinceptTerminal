// ChbSvg.cpp — SVG subset renderer of the chaebol_map engine (DESIGN.md §3.3): tree walk, fill/stroke with
// Chrome's defaults (nonzero fill rule, miter limit 4, dash phase), group opacity as an offscreen layer when an
// element paints more than once (fill + stroke, markers, several children), <marker> (start/mid/end, orient
// auto/auto-start-reverse/angle, refX/refY through the marker viewBox, markerUnits, overflow clip, style
// inherited from the marker's own ancestors), <pattern> (userSpaceOnUse/objectBoundingBox, patternContentUnits,
// patternTransform, viewBox; tile rasterised at device scale like Skia's picture shader), geometry for the dump.
// Parsing lives in ChbSvgParse.cpp / ChbSvgPath.cpp, text layout in ChbSvgText.cpp.
#include "screens/chaebol_map/ChbSvg.h"
#include "screens/chaebol_map/ChbSvg_p.h"

#include <QHash>
#include <QImage>

#include <cmath>
#include <unordered_map>
#include <unordered_set>

namespace fincept::screens::chb::svg {

namespace {

constexpr int kMaxDepth = 6;               // marker/pattern nesting guard
constexpr qint64 kMaxLayerPixels = 16 << 20;
constexpr int kMaxTile = 4096;

/// Target of one paint pass. W = doc → painter logical coordinates, D = doc → device pixels.
struct ChbgPainter {
    QPainter* p = nullptr;
    QTransform W, D;
    qreal baseOp = 1;
};

struct ChbgGeo {
    std::unordered_map<const RNode*, QRectF> boxes;
    std::unordered_map<const RNode*, std::vector<QRectF>> texts;
    /// Boxes a parent container leaves out of its union (Blink HasValidBoundingBoxForContainer): empty shapes
    /// (rect/circle/ellipse with a zero size, shapes without a path) and containers with no valid child.
    std::unordered_set<const RNode*> invalid;
};

struct ChbgCtx {
    const RNode* root = nullptr;
    QRectF viewport;       ///< svg content box (doc)
    QTransform base;       ///< root user space → doc
    LenCtx lc;             ///< root viewport for percentages
    bool disabled = false; ///< viewBox with a zero dimension
    int depth = 0;
    QHash<QString, const RNode*> ids;
    bool idsBuilt = false;

    const RNode* find(const QString& id) {
        if (!idsBuilt) {
            idsBuilt = true;
            std::vector<const RNode*> st{root};
            while (!st.empty()) {
                const RNode* r = st.back();
                st.pop_back();
                if (r->isText) continue;
                if (const QString* a = attr(r, u"id"); a && !ids.contains(*a)) ids.insert(*a, r);
                for (auto it = r->kids.rbegin(); it != r->kids.rend(); ++it) st.push_back(*it);
            }
        }
        return ids.value(id, nullptr);
    }
};

bool chbg_finite(const QTransform& t) {
    return std::isfinite(t.m11()) && std::isfinite(t.m12()) && std::isfinite(t.m21()) && std::isfinite(t.m22()) &&
           std::isfinite(t.dx()) && std::isfinite(t.dy()) && std::isfinite(t.m13()) && std::isfinite(t.m23()) &&
           std::isfinite(t.m33());
}

bool chbg_finite(const QRectF& r) {
    return std::isfinite(r.x()) && std::isfinite(r.y()) && std::isfinite(r.width()) && std::isfinite(r.height());
}

/// Union that keeps empty rects (Blink's UnionEvenIfEmpty for container/text object bounding boxes).
QRectF chbg_union(const QRectF& a, const QRectF& b) {
    const qreal x0 = std::min(a.left(), b.left()), y0 = std::min(a.top(), b.top());
    const qreal x1 = std::max(a.right(), b.right()), y1 = std::max(a.bottom(), b.bottom());
    return QRectF(x0, y0, x1 - x0, y1 - y0);
}

bool chbg_container(Tag t) { return t == Tag::G || t == Tag::A || t == Tag::Svg; }
bool chbg_shape(Tag t) {
    return t == Tag::Line || t == Tag::Rect || t == Tag::Circle || t == Tag::Ellipse || t == Tag::Polyline ||
           t == Tag::Polygon || t == Tag::Path;
}
bool chbg_rendered(const RNode* r) {
    return r && !r->isText && (chbg_container(r->tag) || chbg_shape(r->tag) || r->tag == Tag::Text) && !is_display_none(r);
}

ChbgCtx chbg_ctx(const RNode* svg, const QRectF& viewport) {
    ChbgCtx c;
    c.root = svg;
    c.viewport = viewport;
    QRectF vb;
    const VbState vs = parse_viewbox(svg, &vb);
    c.disabled = vs == VbState::Empty;
    if (vs == VbState::Valid) {
        c.base = viewbox_to_viewport(vb, attr(svg, u"preserveAspectRatio"), viewport);
        c.lc.w = float(vb.width());
        c.lc.h = float(vb.height());
    } else {
        c.base = QTransform::fromTranslate(viewport.x(), viewport.y());
        c.lc.w = float(viewport.width());
        c.lc.h = float(viewport.height());
    }
    if (svg->style) c.lc.fontSize = svg->style->fontSize;
    return c;
}

/// Style of `node` computed along its ancestors (marker/pattern content inherits from the resource's own tree).
Style chbg_chain_style(ChbgCtx& c, const RNode* node) {
    std::vector<const RNode*> anc;
    for (const RNode* a = node; a && a != c.root; a = a->parent) anc.push_back(a);
    Style s = inherit_style(c.root, root_style(c.root), c.lc);
    for (auto it = anc.rbegin(); it != anc.rend(); ++it) s = inherit_style(*it, s, c.lc);
    return s;
}

/// Paint `body` into an offscreen layer covering `docBounds` and composite it with `op` (SVG group opacity).
template <class F>
void chbg_layer(ChbgPainter& P, const QRectF& docBounds, float op, F&& body) {
    QPainter& p = *P.p;
    QRectF dev = P.D.mapRect(docBounds).adjusted(-2, -2, 2, 2);
    if (p.hasClipping()) dev &= p.deviceTransform().mapRect(p.clipBoundingRect());
    else if (p.device()) dev &= QRectF(0, 0, p.device()->width() * p.device()->devicePixelRatio(),
                                       p.device()->height() * p.device()->devicePixelRatio());
    if (!chbg_finite(dev) || dev.width() > 1e7 || dev.height() > 1e7) { body(P, op); return; }
    const QRect r = dev.toAlignedRect();
    if (r.isEmpty()) return;
    if (qint64(r.width()) * r.height() > kMaxLayerPixels) { body(P, op); return; }
    QImage img(r.size(), QImage::Format_ARGB32_Premultiplied);
    if (img.isNull()) { body(P, op); return; }
    img.fill(Qt::transparent);
    QPainter lp(&img);
    lp.setRenderHints(p.renderHints());
    ChbgPainter L;
    L.p = &lp;
    L.D = P.D * QTransform::fromTranslate(-r.x(), -r.y());
    L.W = L.D;
    body(L, 1.0f);
    lp.end();
    // device pixels 1:1: world = T(r) · H⁻¹ where H = the device's own scaling (W⁻¹·D at the current state)
    const QTransform H = p.worldTransform().inverted() * p.deviceTransform();
    p.save();
    p.setWorldTransform(QTransform::fromTranslate(r.x(), r.y()) * H.inverted());
    p.setOpacity(P.baseOp * op);
    p.drawImage(QPointF(0, 0), img);
    p.restore();
}

class ChbgWalker {
  public:
    explicit ChbgWalker(ChbgCtx& c) : c_(c) {}

    void walk(const RNode* r, const Style& parent, const QTransform& parentXf, ChbgPainter* P, float op, ChbgGeo* geo) {
        if (!chbg_rendered(r)) return;
        const Style s = inherit_style(r, parent, c_.lc);
        QTransform xf = parentXf;
        if (const QString* t = attr(r, u"transform")) xf = parse_transform(*t) * parentXf;
        if (!chbg_finite(xf) || !xf.isInvertible()) return; // Chrome: non-invertible CTM renders nothing
        const float eop = element_opacity(r);
        if (chbg_container(r->tag)) group(r, s, xf, P, op * eop, eop, geo);
        else if (r->tag == Tag::Text) text(r, s, xf, P, op * eop, geo);
        else shape(r, s, xf, P, op * eop, geo);
    }

  private:
    ChbgCtx& c_;

    void group(const RNode* r, const Style& s, QTransform xf, ChbgPainter* P, float op, float eop, ChbgGeo* geo) {
        if (r->tag == Tag::Svg && r != c_.root) { // nested viewport
            const float x = attr_len(r, u"x", Axis::X, c_.lc), y = attr_len(r, u"y", Axis::Y, c_.lc);
            const float w = attr_len(r, u"width", Axis::X, c_.lc, c_.lc.w), h = attr_len(r, u"height", Axis::Y, c_.lc, c_.lc.h);
            QRectF vb;
            const VbState vs = parse_viewbox(r, &vb);
            if (vs == VbState::Empty || w <= 0 || h <= 0) return;
            xf = (vs == VbState::Valid ? viewbox_to_viewport(vb, attr(r, u"preserveAspectRatio"), QRectF(x, y, w, h))
                                       : QTransform::fromTranslate(x, y)) * xf;
        }
        std::vector<const RNode*> kids;
        for (const RNode* k : r->kids)
            if (chbg_rendered(k)) kids.push_back(k);
        if (geo) {
            QRectF u;
            bool any = false;
            for (const RNode* k : kids) {
                walk(k, s, xf, nullptr, 1.0f, geo);
                auto it = geo->boxes.find(k);
                if (it == geo->boxes.end() || geo->invalid.count(k)) continue;
                u = any ? chbg_union(u, it->second) : it->second;
                any = true;
            }
            geo->boxes[r] = any ? u : xf.mapRect(QRectF()); // empty container: its user-space origin (Chrome)
            if (!any) geo->invalid.insert(r);
        }
        if (!P) return;
        if (eop < 1 && kids.size() >= 2) { // several children: one transparency group
            ChbgGeo g2;
            QRectF bounds;
            for (const RNode* k : kids) {
                walk(k, s, xf, nullptr, 1.0f, &g2);
                if (auto it = g2.boxes.find(k); it != g2.boxes.end()) bounds = bounds.united(it->second);
            }
            chbg_layer(*P, bounds.adjusted(-32, -32, 32, 32), op, [&](ChbgPainter& L, float) {
                for (const RNode* k : kids) walk(k, s, xf, &L, 1.0f, nullptr);
            });
            return;
        }
        for (const RNode* k : kids) walk(k, s, xf, P, op, nullptr);
    }

    void text(const RNode* r, const Style& s, const QTransform& xf, ChbgPainter* P, float op, ChbgGeo* geo) {
        const std::vector<TextFrag> frags = layout_text(r, s, xf, c_.lc);
        if (geo) {
            QRectF all;
            bool any = false;
            for (const TextFrag& f : frags) {
                const QRectF rr = xf.mapRect(f.rect), bx = xf.mapRect(f.box);
                if (f.width > 0) geo->texts[f.textNode].push_back(rr);
                all = any ? chbg_union(all, bx) : bx;
                any = true;
                for (const RNode* e = f.textNode->parent; e && e != r; e = e->parent) {
                    auto it = geo->boxes.find(e);
                    if (it == geo->boxes.end()) geo->boxes[e] = bx;
                    else it->second = chbg_union(it->second, bx);
                }
            }
            geo->boxes[r] = any ? all : xf.mapRect(QRectF());
        }
        if (!P || op <= 0) return;
        for (const TextFrag& f : frags) textFrag(f, xf, *P, op);
    }

    /// Fill (glyph runs, or outlines for a pattern) then stroke (outlines). A translucent solid fill is drawn
    /// opaque in a layer and composited: glyphs are drawn twice (ChbText darkening pass), which must not compound.
    void textFrag(const TextFrag& f, const QTransform& xf, ChbgPainter& P, float op) {
        if (!f.shaped || f.text.isEmpty() || !f.st.visible) return;
        const QTransform u2d = xf * P.D;
        // off-scale text (degenerate transforms): nothing sensible to draw, and Qt's glyph paths overflow
        const QRectF devBox = u2d.mapRect(f.box);
        if (!chbg_finite(devBox) || devBox.height() > 1e5 || devBox.width() > 1e7) return;
        if (P.p->hasClipping() && !devBox.intersects(P.p->deviceTransform().mapRect(P.p->clipBoundingRect()))) return;
        QBrush fb, sb;
        const bool hasFill = f.st.fillOpacity > 0 && paint(f.st.fill, f.st, f.box, u2d, &fb);
        const bool hasStroke = f.st.strokeWidth > 0 && f.st.strokeOpacity > 0 && paint(f.st.stroke, f.st, f.box, u2d, &sb);
        if (hasFill && fb.style() == Qt::SolidPattern) {
            QColor opaque = fb.color();
            const qreal a = qreal(op) * f.st.fillOpacity * opaque.alphaF();
            opaque.setAlpha(255);
            if (a >= 0.999) {
                P.p->save();
                P.p->setOpacity(P.baseOp);
                paint_text_frag(*P.p, f, xf * P.W, opaque);
                P.p->restore();
            } else if (a > 0) {
                chbg_layer(P, xf.mapRect(f.box).adjusted(-2, -2, 2, 2), float(a), [&](ChbgPainter& L, float) {
                    paint_text_frag(*L.p, f, xf * L.W, opaque);
                });
            }
        }
        if (!(hasFill && fb.style() != Qt::SolidPattern) && !hasStroke) return;
        const QPainterPath outline = text_outline(f);
        QPainter& p = *P.p;
        p.save();
        p.setTransform(xf * P.W);
        p.setRenderHint(QPainter::Antialiasing, true);
        p.setRenderHint(QPainter::SmoothPixmapTransform, true);
        if (hasFill && fb.style() != Qt::SolidPattern) {
            p.setOpacity(P.baseOp * op * f.st.fillOpacity);
            p.fillPath(outline, fb);
        }
        if (hasStroke) {
            p.setOpacity(P.baseOp * op * f.st.strokeOpacity);
            p.strokePath(outline, pen(f.st, sb));
        }
        p.restore();
    }

    // ---- paint servers
    bool paint(const PaintRef& pr, const Style& s, const QRectF& bbox, const QTransform& userToDevice, QBrush* out) {
        switch (pr.kind) {
        case PaintRef::None: return false;
        case PaintRef::Color: *out = QBrush(pr.color); return pr.color.alpha() > 0;
        case PaintRef::Current: *out = QBrush(s.color); return s.color.alpha() > 0;
        case PaintRef::Url: break;
        }
        const RNode* ref = c_.find(pr.id);
        if (ref && ref->tag == Tag::Pattern) return pattern(ref, bbox, userToDevice, out);
        if (ref && (ref->tag == Tag::LinearGradient || ref->tag == Tag::RadialGradient)) {
            // gradients are outside DESIGN §3.3: solid first stop (engine baseline behaviour)
            for (const RNode* k : ref->kids) {
                if (k->isText || k->tag != Tag::Stop) continue;
                QColor col;
                bool cur = false;
                const QString* sc = attr(k, u"stopColor");
                if (sc && parse_css_color(*sc, &col, &cur) && !cur) { *out = QBrush(col); return true; }
            }
            return false;
        }
        if (pr.fbKind == PaintRef::Color) { *out = QBrush(pr.fb); return true; }
        if (pr.fbKind == PaintRef::Current) { *out = QBrush(s.color); return true; }
        return false; // unresolved url() without fallback paints nothing (Chrome)
    }

    bool pattern(const RNode* pat, const QRectF& bbox, const QTransform& userToDevice, QBrush* out) {
        if (c_.depth >= kMaxDepth || is_display_none(pat)) return false;
        const QString* pu = attr(pat, u"patternUnits");
        const QString* pcu = attr(pat, u"patternContentUnits");
        const bool obb = !(pu && pu->trimmed() == QLatin1String("userSpaceOnUse"));
        const bool obbContent = pcu && pcu->trimmed() == QLatin1String("objectBoundingBox");
        float tx, ty, tw, th;
        if (obb) {
            const LenCtx unit{1, 1, 16}; // fractions; "10%" = 0.1
            tx = float(bbox.x() + attr_len(pat, u"x", Axis::X, unit) * bbox.width());
            ty = float(bbox.y() + attr_len(pat, u"y", Axis::Y, unit) * bbox.height());
            tw = float(attr_len(pat, u"width", Axis::X, unit) * bbox.width());
            th = float(attr_len(pat, u"height", Axis::Y, unit) * bbox.height());
        } else {
            tx = attr_len(pat, u"x", Axis::X, c_.lc);
            ty = attr_len(pat, u"y", Axis::Y, c_.lc);
            tw = attr_len(pat, u"width", Axis::X, c_.lc);
            th = attr_len(pat, u"height", Axis::Y, c_.lc);
        }
        if (!(tw > 0) || !(th > 0)) return false;
        QRectF vb;
        const VbState vs = parse_viewbox(pat, &vb);
        if (vs == VbState::Empty) return false;
        QTransform content;
        if (vs == VbState::Valid) content = viewbox_to_viewport(vb, attr(pat, u"preserveAspectRatio"), QRectF(0, 0, tw, th));
        else if (obbContent) content = QTransform::fromScale(bbox.width(), bbox.height());
        QTransform ptf;
        if (const QString* t = attr(pat, u"patternTransform")) ptf = parse_transform(*t);
        const QTransform tileToUser = QTransform::fromTranslate(tx, ty) * ptf;
        const QTransform M = tileToUser * userToDevice;
        const double sx = std::hypot(M.m11(), M.m12()), sy = std::hypot(M.m21(), M.m22());
        if (!std::isfinite(tw * sx) || !std::isfinite(th * sy) || tw * sx > 1e9 || th * sy > 1e9) return false;
        int W = std::max(1, int(std::ceil(tw * sx - 1e-6))), H = std::max(1, int(std::ceil(th * sy - 1e-6)));
        if (W > kMaxTile || H > kMaxTile) {
            const double k = double(kMaxTile) / std::max(W, H);
            W = std::max(1, int(W * k));
            H = std::max(1, int(H * k));
        }
        QImage img(W, H, QImage::Format_ARGB32_Premultiplied);
        if (img.isNull()) return false;
        img.fill(Qt::transparent);
        {
            QPainter ip(&img);
            ip.setRenderHint(QPainter::Antialiasing, true);
            ChbgPainter T;
            T.p = &ip;
            const QTransform tileXf = content * QTransform::fromScale(W / double(tw), H / double(th));
            const Style st = chbg_chain_style(c_, pat);
            ++c_.depth;
            for (const RNode* k : pat->kids) walk(k, st, tileXf, &T, 1.0f, nullptr);
            --c_.depth;
        }
        QBrush br(img);
        br.setTransform(QTransform::fromScale(tw / double(W), th / double(H)) * tileToUser);
        *out = br;
        return true;
    }

    QPen pen(const Style& s, const QBrush& b) const {
        QPen pn(b, qreal(s.strokeWidth));
        pn.setCapStyle(s.cap);
        pn.setJoinStyle(s.join);
        pn.setMiterLimit(s.miterLimit);
        float sum = 0;
        for (float d : s.dash) sum += d;
        if (!s.dash.empty() && sum > 0) {
            const qreal w = std::max<qreal>(1e-6, pn.widthF());
            QList<qreal> pat;
            for (int rep = 0; rep < (s.dash.size() % 2 ? 2 : 1); ++rep)
                for (float d : s.dash) pat << std::max<qreal>(1e-4, d / w);
            pn.setDashPattern(pat);
            pn.setDashOffset(s.dashOffset / w);
        }
        return pn;
    }

    // ---- markers
    static double chbg_deg(const QPointF& d) { return std::atan2(d.y(), d.x()) * 180.0 / M_PI; }

    static double chbg_angle(const Vertex& v) {
        if (v.hasIn && v.hasOut) { // Blink BisectingAngle
            double in = chbg_deg(v.in), out = chbg_deg(v.out);
            if (std::fabs(in - out) > 180) in += 360;
            return (in + out) / 2;
        }
        if (v.hasOut) return chbg_deg(v.out);
        if (v.hasIn) return chbg_deg(v.in);
        return 0;
    }

    static bool chbg_orient(const QString* o, double autoAngle, bool isStart, double* out) {
        if (!o) { *out = 0; return true; }
        const QStringView v = QStringView(*o).trimmed();
        if (v == u"auto") { *out = autoAngle; return true; }
        if (v == u"auto-start-reverse") { *out = autoAngle + (isStart ? 180 : 0); return true; }
        int i = 0;
        float a = 0;
        if (!scan_number(v, &i, &a)) { *out = 0; return true; }
        const QStringView unit = v.mid(i).trimmed();
        double deg = a;
        if (unit == u"rad") deg = a * 180.0 / M_PI;
        else if (unit == u"grad") deg = a * 0.9;
        else if (unit == u"turn") deg = a * 360.0;
        else if (!unit.isEmpty() && unit != u"deg") deg = 0;
        *out = deg;
        return true;
    }

    void markers(const Style& s, const Geometry& g, const QTransform& xf, ChbgPainter& P, float op) {
        const size_t n = g.verts.size();
        for (size_t k = 0; k < n; ++k) {
            const Vertex& v = g.verts[k];
            const double a = chbg_angle(v);
            if (k == 0 && !s.markerStart.isEmpty()) marker(s.markerStart, v.p, a, true, s.strokeWidth, xf, P, op);
            if (k > 0 && k + 1 < n && !s.markerMid.isEmpty()) marker(s.markerMid, v.p, a, false, s.strokeWidth, xf, P, op);
            if (k + 1 == n && !s.markerEnd.isEmpty()) marker(s.markerEnd, v.p, a, false, s.strokeWidth, xf, P, op);
        }
    }

    void marker(const QString& id, const QPointF& at, double autoAngle, bool isStart, float strokeWidth,
                const QTransform& xf, ChbgPainter& P, float op) {
        const RNode* m = c_.find(id);
        if (!m || m->tag != Tag::Marker || c_.depth >= kMaxDepth || is_display_none(m)) return;
        const float mw = attr_len(m, u"markerWidth", Axis::X, c_.lc, 3), mh = attr_len(m, u"markerHeight", Axis::Y, c_.lc, 3);
        if (!(mw > 0) || !(mh > 0)) return;
        QRectF vb;
        const VbState vs = parse_viewbox(m, &vb);
        if (vs == VbState::Empty) return;
        const QTransform vbT = vs == VbState::Valid
                                   ? viewbox_to_viewport(vb, attr(m, u"preserveAspectRatio"), QRectF(0, 0, mw, mh))
                                   : QTransform();
        const QString* units = attr(m, u"markerUnits");
        const float scale = (units && units->trimmed() == QLatin1String("userSpaceOnUse")) ? 1.0f : strokeWidth;
        double angle = 0;
        chbg_orient(attr(m, u"orient"), autoAngle, isStart, &angle);
        const QPointF ref = vbT.map(QPointF(attr_len(m, u"refX", Axis::X, c_.lc), attr_len(m, u"refY", Axis::Y, c_.lc)));
        QTransform V = QTransform::fromTranslate(-ref.x(), -ref.y());
        V = V * QTransform::fromScale(scale, scale);
        QTransform rot;
        rot.rotate(angle);
        V = V * rot * QTransform::fromTranslate(at.x(), at.y()) * xf; // marker viewport → doc
        const Style ms = chbg_chain_style(c_, m);
        const QString* ov = attr(m, u"overflow");
        const bool clip = !(ov && (ov->trimmed() == QLatin1String("visible") || ov->trimmed() == QLatin1String("auto")));
        QPainter& p = *P.p;
        p.save();
        if (clip) {
            p.setTransform(V * P.W);
            p.setClipRect(QRectF(0, 0, mw, mh), Qt::IntersectClip);
        }
        ++c_.depth;
        for (const RNode* k : m->kids) walk(k, ms, vbT * V, &P, op, nullptr);
        --c_.depth;
        p.restore();
    }

    // ---- shapes
    void shape(const RNode* r, const Style& s, const QTransform& xf, ChbgPainter* P, float op, ChbgGeo* geo) {
        LenCtx lc = c_.lc;
        lc.fontSize = s.fontSize;
        Geometry g;
        const bool ok = shape_geometry(r, lc, &g);
        if (geo) { // non-rendered shapes still report a box (Chrome): parsed points, rect x/y, centre, origin
            QRectF ub;
            if (ok || g.path.elementCount() > 0) ub = g.path.boundingRect();
            else if (r->tag == Tag::Rect)
                ub = QRectF(attr_len(r, u"x", Axis::X, lc), attr_len(r, u"y", Axis::Y, lc),
                            std::max(0.0f, attr_len(r, u"width", Axis::X, lc)),
                            std::max(0.0f, attr_len(r, u"height", Axis::Y, lc)));
            else if (r->tag == Tag::Circle || r->tag == Tag::Ellipse)
                ub = QRectF(attr_len(r, u"cx", Axis::X, lc), attr_len(r, u"cy", Axis::Y, lc), 0, 0);
            geo->boxes[r] = xf.mapRect(ub);
            // Blink LayoutSVGRect/Ellipse::IsShapeEmpty (fill box empty: "a value of zero disables rendering"),
            // LayoutSVGShape::IsShapeEmpty (no path) → not part of the parent's bounding box (a zero-width
            // overlay rect beside its label: the <g> is the label's box only)
            const bool box = r->tag == Tag::Rect || r->tag == Tag::Circle || r->tag == Tag::Ellipse;
            if (box ? (ub.width() <= 0 || ub.height() <= 0) : g.path.elementCount() == 0) geo->invalid.insert(r);
        }
        if (!P || !ok || !s.visible || op <= 0) return;
        QPainterPath path = g.path;
        path.setFillRule(s.evenOdd ? Qt::OddEvenFill : Qt::WindingFill);
        const QRectF bb = path.boundingRect();
        const QTransform u2d = xf * P->D;
        QBrush fillB, strokeB;
        const bool hasFill = paint(s.fill, s, bb, u2d, &fillB) && s.fillOpacity > 0;
        const bool hasStroke = s.strokeWidth > 0 && paint(s.stroke, s, bb, u2d, &strokeB) && s.strokeOpacity > 0;
        const bool hasMarkers =
            g.markable && (!s.markerStart.isEmpty() || !s.markerMid.isEmpty() || !s.markerEnd.isEmpty());
        if (!hasFill && !hasStroke && !hasMarkers) return;
        const QPen pn = hasStroke ? pen(s, strokeB) : QPen(Qt::NoPen);
        auto body = [&](ChbgPainter& Q, float o) {
            QPainter& p = *Q.p;
            p.save();
            p.setTransform(xf * Q.W);
            p.setRenderHint(QPainter::Antialiasing, true);
            p.setRenderHint(QPainter::SmoothPixmapTransform, true);
            if (hasFill) {
                p.setOpacity(Q.baseOp * o * s.fillOpacity);
                p.fillPath(path, fillB);
            }
            if (hasStroke) {
                p.setOpacity(Q.baseOp * o * s.strokeOpacity);
                p.strokePath(path, pn);
            }
            p.restore();
            if (hasMarkers) markers(s, g, xf, Q, o);
        };
        const int ops = int(hasFill) + int(hasStroke) + (hasMarkers ? 2 : 0);
        if (op < 1 && ops >= 2) {
            const float pad = s.strokeWidth * std::max(1.0f, s.miterLimit) + 32;
            chbg_layer(*P, xf.mapRect(bb.adjusted(-pad, -pad, pad, pad)), op, body);
        } else {
            body(*P, op);
        }
    }
};

} // namespace

QTransform viewbox_transform(const RNode* svg, const QRectF& viewport) {
    return svg ? chbg_ctx(svg, viewport).base : QTransform();
}

void paint_svg(QPainter& p, const RNode* svg, const QRectF& viewport) {
    if (!svg) return;
    ChbgCtx c = chbg_ctx(svg, viewport);
    if (c.disabled) return;
    ChbgPainter P;
    P.p = &p;
    P.W = p.worldTransform();
    P.D = p.deviceTransform();
    P.baseOp = p.opacity();
    const Style s = inherit_style(svg, root_style(svg), c.lc);
    ChbgWalker w(c);
    p.save();
    for (const RNode* k : svg->kids) w.walk(k, s, c.base, &P, 1.0f, nullptr);
    p.restore();
}

namespace {
ChbgGeo chbg_geometry(const RNode* svg, const QRectF& viewport) {
    ChbgGeo geo;
    ChbgCtx c = chbg_ctx(svg, viewport);
    if (c.disabled) return geo;
    const Style s = inherit_style(svg, root_style(svg), c.lc);
    ChbgWalker w(c);
    for (const RNode* k : svg->kids) w.walk(k, s, c.base, nullptr, 1.0f, &geo);
    return geo;
}
} // namespace

QRectF node_bbox(const RNode* svg, const QRectF& viewport, const RNode* node) {
    if (!svg || !node) return {};
    const ChbgGeo geo = chbg_geometry(svg, viewport);
    auto it = geo.boxes.find(node);
    return it == geo.boxes.end() ? QRectF() : it->second;
}

std::vector<QRectF> text_rects(const RNode* svg, const QRectF& viewport, const RNode* textNode) {
    if (!svg || !textNode) return {};
    const ChbgGeo geo = chbg_geometry(svg, viewport);
    auto it = geo.texts.find(textNode);
    return it == geo.texts.end() ? std::vector<QRectF>() : it->second;
}

} // namespace fincept::screens::chb::svg
