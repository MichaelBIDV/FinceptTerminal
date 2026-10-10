// ChbSvgPath.cpp — SVG geometry for the chaebol_map engine: full path-data parser (M L H V C S Q T A Z, absolute
// and relative, implicit repeats, compact numbers/flags, error = keep what was parsed) with arcs converted to
// cubics, and the basic shapes. Every path records its marker vertices with incoming/outgoing tangents.
// Outlines start where Skia/Blink start them (dash phase): rect at the top-left corner, rounded rect at
// (x + rx, y), circle/ellipse at the rightmost point, all clockwise on screen.
#include "screens/chaebol_map/ChbSvg_p.h"

#include <cmath>

namespace fincept::screens::chb::svg {

namespace {

constexpr double kKappa = 0.55228474983079356; // 4/3·(√2 − 1): quarter circle as one cubic

bool chbg_zero(const QPointF& v) { return std::fabs(v.x()) < 1e-9 && std::fabs(v.y()) < 1e-9; }

QPointF chbg_first_nz(std::initializer_list<QPointF> l) {
    for (const QPointF& v : l)
        if (!chbg_zero(v)) return v;
    return QPointF();
}

/// Path + marker vertices. Tangents follow Blink's SVGMarkerData: cubic out = c1 − p0, in = p1 − c2 (falling
/// back along the control polygon when degenerate).
struct ChbgBuilder {
    explicit ChbgBuilder(Geometry* geo) : g(geo) {}
    Geometry* g;
    QPointF cur, start;
    int subStart = -1;

    void segment_start(const QPointF& dir) {
        if (g->verts.empty()) return;
        Vertex& v = g->verts.back();
        v.out = dir;
        v.hasOut = true;
    }
    void push(const QPointF& p, const QPointF& in) {
        Vertex v;
        v.p = p;
        v.in = in;
        v.hasIn = true;
        g->verts.push_back(v);
        cur = p;
    }
    void moveTo(const QPointF& p) {
        g->path.moveTo(p);
        Vertex v;
        v.p = p;
        g->verts.push_back(v);
        cur = start = p;
        subStart = int(g->verts.size()) - 1;
    }
    void lineTo(const QPointF& p) {
        const QPointF d = p - cur;
        segment_start(d);
        g->path.lineTo(p);
        push(p, d);
    }
    void cubicTo(const QPointF& c1, const QPointF& c2, const QPointF& p) {
        segment_start(chbg_first_nz({c1 - cur, c2 - cur, p - cur}));
        g->path.cubicTo(c1, c2, p);
        push(p, chbg_first_nz({p - c2, p - c1, p - cur}));
    }
    void quadTo(const QPointF& c, const QPointF& p) {
        segment_start(chbg_first_nz({c - cur, p - cur}));
        g->path.quadTo(c, p);
        push(p, chbg_first_nz({p - c, p - cur}));
    }
    /// Endpoint arc (SVG implementation notes F.6); identical endpoints = no segment, zero radius = line.
    void arcTo(double rx, double ry, double phi, bool large, bool sweep, const QPointF& p1) {
        const QPointF p0 = cur;
        if (chbg_zero(p1 - p0)) return;
        rx = std::fabs(rx);
        ry = std::fabs(ry);
        if (rx == 0 || ry == 0) { lineTo(p1); return; }
        const double rad = phi * M_PI / 180.0, cs = std::cos(rad), sn = std::sin(rad);
        const double dx = (p0.x() - p1.x()) / 2, dy = (p0.y() - p1.y()) / 2;
        const double x1 = cs * dx + sn * dy, y1 = -sn * dx + cs * dy;
        const double lam = (x1 * x1) / (rx * rx) + (y1 * y1) / (ry * ry);
        if (lam > 1) { rx *= std::sqrt(lam); ry *= std::sqrt(lam); }
        const double num = rx * rx * ry * ry - rx * rx * y1 * y1 - ry * ry * x1 * x1;
        const double den = rx * rx * y1 * y1 + ry * ry * x1 * x1;
        double co = den == 0 ? 0 : std::sqrt(std::max(0.0, num / den));
        if (large == sweep) co = -co;
        const double cx1 = co * rx * y1 / ry, cy1 = -co * ry * x1 / rx;
        const double cx = cs * cx1 - sn * cy1 + (p0.x() + p1.x()) / 2;
        const double cy = sn * cx1 + cs * cy1 + (p0.y() + p1.y()) / 2;
        auto ang = [](double ux, double uy, double vx, double vy) { return std::atan2(ux * vy - uy * vx, ux * vx + uy * vy); };
        const double t1 = ang(1, 0, (x1 - cx1) / rx, (y1 - cy1) / ry);
        double dt = ang((x1 - cx1) / rx, (y1 - cy1) / ry, (-x1 - cx1) / rx, (-y1 - cy1) / ry);
        if (!sweep && dt > 0) dt -= 2 * M_PI;
        if (sweep && dt < 0) dt += 2 * M_PI;
        const int segs = std::max(1, int(std::ceil(std::fabs(dt) / (M_PI / 2) - 1e-9)));
        const double d = dt / segs, k = 4.0 / 3.0 * std::tan(d / 4);
        auto map = [&](double x, double y) { return QPointF(cx + cs * rx * x - sn * ry * y, cy + sn * rx * x + cs * ry * y); };
        double t = t1;
        QPointF firstC1, lastC2;
        for (int i = 0; i < segs; ++i) {
            const double c1 = std::cos(t), s1 = std::sin(t), c2 = std::cos(t + d), s2 = std::sin(t + d);
            const QPointF a = map(c1 - k * s1, s1 + k * c1), b = map(c2 + k * s2, s2 - k * c2);
            const QPointF e = i + 1 == segs ? p1 : map(c2, s2);
            if (i == 0) {
                firstC1 = a;
                segment_start(chbg_first_nz({a - p0, p1 - p0}));
            }
            lastC2 = b;
            g->path.cubicTo(a, b, e);
            t += d;
        }
        push(p1, chbg_first_nz({p1 - lastC2, p1 - p0}));
    }
    /// closepath: vertex back at the subpath start; a closed subpath's first and closing vertices take the
    /// bisector of the closing segment and the first segment (SVG 2 marker orientation).
    void close() {
        if (subStart < 0) return;
        const QPointF d = start - cur;
        const QPointF closing = chbg_zero(d) ? g->verts.back().in : d;
        if (!chbg_zero(d)) {
            segment_start(d);
            Vertex v;
            v.p = start;
            v.in = d;
            v.hasIn = true;
            g->verts.push_back(v);
        }
        g->path.closeSubpath();
        Vertex& first = g->verts[size_t(subStart)];
        Vertex& last = g->verts.back();
        if (&first != &last) {
            first.in = closing;
            first.hasIn = true;
            if (first.hasOut) {
                last.out = first.out;
                last.hasOut = true;
            }
        }
        cur = start;
    }
};

bool chbg_cmd(QChar c) {
    switch (c.unicode()) {
    case 'M': case 'm': case 'L': case 'l': case 'H': case 'h': case 'V': case 'v': case 'C': case 'c':
    case 'S': case 's': case 'Q': case 'q': case 'T': case 't': case 'A': case 'a': case 'Z': case 'z':
        return true;
    default:
        return false;
    }
}

bool chbg_wsp(QChar c) { return c == u' ' || c == u'\t' || c == u'\n' || c == u'\r' || c == u'\f'; }

} // namespace

bool path_from_data(QStringView d, Geometry* g) {
    g->path = QPainterPath();
    g->verts.clear();
    g->markable = true;
    ChbgBuilder b(g);
    const int n = int(d.size());
    int i = 0;
    QChar cmd;
    QChar prev;         // upper-case command of the previous segment (S/T control reflection)
    QPointF lastCtrl;
    auto skipWsp = [&] { while (i < n && chbg_wsp(d[i])) ++i; };
    auto sep = [&] {
        skipWsp();
        if (i < n && d[i] == u',') { ++i; skipWsp(); }
    };
    auto num = [&](double* v) {
        skipWsp();
        float f = 0;
        if (!scan_number(d, &i, &f)) return false;
        *v = f;
        sep();
        return true;
    };
    auto flag = [&](bool* f) {
        skipWsp();
        if (i < n && (d[i] == u'0' || d[i] == u'1')) {
            *f = d[i] == u'1';
            ++i;
            sep();
            return true;
        }
        return false;
    };
    auto startsNumber = [&] {
        skipWsp();
        return i < n && (d[i].isDigit() || d[i] == u'.' || d[i] == u'-' || d[i] == u'+');
    };
    bool any = false;
    skipWsp();
    while (i < n) {
        const QChar c = d[i];
        if (!chbg_cmd(c)) return false;
        cmd = c;
        ++i;
        const QChar C = cmd.toUpper();
        const bool rel = cmd.isLower();
        if (!any && C != u'M') return false; // a path must begin with a moveto
        any = true;
        if (C == u'Z') {
            b.close();
            prev = C;
            lastCtrl = b.cur;
            skipWsp();
            continue; // numbers right after Z → the next round sees a non-command → error
        }
        bool first = true;
        do {
            const QPointF o = rel ? b.cur : QPointF();
            double a[7];
            switch (C.unicode()) {
            case 'M':
                if (!num(&a[0]) || !num(&a[1])) return false;
                if (first) b.moveTo(o + QPointF(a[0], a[1]));
                else b.lineTo(o + QPointF(a[0], a[1]));
                prev = first ? QChar(u'M') : QChar(u'L');
                break;
            case 'L':
                if (!num(&a[0]) || !num(&a[1])) return false;
                b.lineTo(o + QPointF(a[0], a[1]));
                prev = C;
                break;
            case 'H':
                if (!num(&a[0])) return false;
                b.lineTo(QPointF(rel ? b.cur.x() + a[0] : a[0], b.cur.y()));
                prev = C;
                break;
            case 'V':
                if (!num(&a[0])) return false;
                b.lineTo(QPointF(b.cur.x(), rel ? b.cur.y() + a[0] : a[0]));
                prev = C;
                break;
            case 'C':
                for (int k = 0; k < 6; ++k)
                    if (!num(&a[k])) return false;
                lastCtrl = o + QPointF(a[2], a[3]);
                b.cubicTo(o + QPointF(a[0], a[1]), lastCtrl, o + QPointF(a[4], a[5]));
                prev = C;
                break;
            case 'S': {
                for (int k = 0; k < 4; ++k)
                    if (!num(&a[k])) return false;
                const QPointF c1 = (prev == u'C' || prev == u'S') ? b.cur * 2 - lastCtrl : b.cur;
                lastCtrl = o + QPointF(a[0], a[1]);
                b.cubicTo(c1, lastCtrl, o + QPointF(a[2], a[3]));
                prev = C;
                break;
            }
            case 'Q':
                for (int k = 0; k < 4; ++k)
                    if (!num(&a[k])) return false;
                lastCtrl = o + QPointF(a[0], a[1]);
                b.quadTo(lastCtrl, o + QPointF(a[2], a[3]));
                prev = C;
                break;
            case 'T': {
                if (!num(&a[0]) || !num(&a[1])) return false;
                lastCtrl = (prev == u'Q' || prev == u'T') ? b.cur * 2 - lastCtrl : b.cur;
                b.quadTo(lastCtrl, o + QPointF(a[0], a[1]));
                prev = C;
                break;
            }
            case 'A': {
                bool large = false, sweep = false;
                if (!num(&a[0]) || !num(&a[1]) || !num(&a[2]) || !flag(&large) || !flag(&sweep) || !num(&a[3]) ||
                    !num(&a[4]))
                    return false;
                b.arcTo(a[0], a[1], a[2], large, sweep, o + QPointF(a[3], a[4]));
                prev = C;
                break;
            }
            default:
                return false;
            }
            first = false;
        } while (startsNumber());
        skipWsp();
    }
    return true;
}

bool shape_geometry(const RNode* r, const LenCtx& c, Geometry* g) {
    g->path = QPainterPath();
    g->verts.clear();
    g->markable = false;
    ChbgBuilder b(g);
    switch (r->tag) {
    case Tag::Path: {
        const QString* d = attr(r, u"d");
        if (!d) return false;
        path_from_data(*d, g);
        return !g->path.isEmpty();
    }
    case Tag::Line: {
        g->markable = true;
        b.moveTo(QPointF(attr_len(r, u"x1", Axis::X, c), attr_len(r, u"y1", Axis::Y, c)));
        b.lineTo(QPointF(attr_len(r, u"x2", Axis::X, c), attr_len(r, u"y2", Axis::Y, c)));
        return true;
    }
    case Tag::Polyline: case Tag::Polygon: {
        const QString* pts = attr(r, u"points");
        if (!pts) return false;
        const std::vector<float> v = number_list(*pts); // error: keep the points before it (Chrome)
        if (v.size() < 2) return false;
        g->markable = true;
        b.moveTo(QPointF(v[0], v[1]));
        for (size_t k = 2; k + 1 < v.size(); k += 2) b.lineTo(QPointF(v[k], v[k + 1]));
        if (r->tag == Tag::Polygon) b.close();
        return true;
    }
    case Tag::Rect: {
        const float x = attr_len(r, u"x", Axis::X, c), y = attr_len(r, u"y", Axis::Y, c);
        const float w = attr_len(r, u"width", Axis::X, c, -1), h = attr_len(r, u"height", Axis::Y, c, -1);
        if (w <= 0 || h <= 0) return false;
        float rx = attr_len(r, u"rx", Axis::X, c, -1), ry = attr_len(r, u"ry", Axis::Y, c, -1);
        if (rx < 0) rx = ry;
        if (ry < 0) ry = rx;
        rx = std::min(std::max(rx, 0.0f), w / 2);
        ry = std::min(std::max(ry, 0.0f), h / 2);
        QPainterPath& p = g->path;
        if (rx > 0 && ry > 0) {
            const double kx = kKappa * rx, ky = kKappa * ry, r0 = x + w, b0 = y + h;
            p.moveTo(x + rx, y);
            p.lineTo(r0 - rx, y);
            p.cubicTo(r0 - rx + kx, y, r0, y + ry - ky, r0, y + ry);
            p.lineTo(r0, b0 - ry);
            p.cubicTo(r0, b0 - ry + ky, r0 - rx + kx, b0, r0 - rx, b0);
            p.lineTo(x + rx, b0);
            p.cubicTo(x + rx - kx, b0, x, b0 - ry + ky, x, b0 - ry);
            p.lineTo(x, y + ry);
            p.cubicTo(x, y + ry - ky, x + rx - kx, y, x + rx, y);
            p.closeSubpath();
        } else {
            p.moveTo(x, y);
            p.lineTo(x + w, y);
            p.lineTo(x + w, y + h);
            p.lineTo(x, y + h);
            p.closeSubpath();
        }
        return true;
    }
    case Tag::Circle: case Tag::Ellipse: {
        const float cx = attr_len(r, u"cx", Axis::X, c), cy = attr_len(r, u"cy", Axis::Y, c);
        float rx, ry;
        if (r->tag == Tag::Circle) {
            rx = ry = attr_len(r, u"r", Axis::Diag, c);
        } else {
            rx = attr_len(r, u"rx", Axis::X, c, -1);
            ry = attr_len(r, u"ry", Axis::Y, c, -1);
            if (rx < 0) rx = ry;
            if (ry < 0) ry = rx;
        }
        if (rx <= 0 || ry <= 0) return false;
        const double kx = kKappa * rx, ky = kKappa * ry;
        QPainterPath& p = g->path;
        p.moveTo(cx + rx, cy);
        p.cubicTo(cx + rx, cy + ky, cx + kx, cy + ry, cx, cy + ry);
        p.cubicTo(cx - kx, cy + ry, cx - rx, cy + ky, cx - rx, cy);
        p.cubicTo(cx - rx, cy - ky, cx - kx, cy - ry, cx, cy - ry);
        p.cubicTo(cx + kx, cy - ry, cx + rx, cy - ky, cx + rx, cy);
        p.closeSubpath();
        return true;
    }
    default:
        return false;
    }
}

} // namespace fincept::screens::chb::svg
