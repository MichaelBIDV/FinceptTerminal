// WdcIcons.cpp: icon paths and decorations of the WiData clone (package D).
//
// The path-data parser follows screens/chaebol_map/ChbSvgPath.cpp (path_from_data, endpoint arc of SVG
// implementation notes F.6), copied without marker vertices into namespace wdc so that this module never calls
// into chb. Icon path data: widata_clone_spec/analysis/assets/icons/*.svg (MUI icons, ResizeHandleDiagonal and
// CalendarExpanded20 of WiData) and the chart-page capture (Percent, InsertLinkRounded).
#include "screens/widata/WdcIcons_p.h"

#include "screens/widata/WdcTheme_p.h"

#include <QHash>
#include <QMutex>
#include <QMutexLocker>
#include <QPainter>
#include <QTransform>

#include <array>
#include <cmath>

namespace fincept::screens::wdc {

namespace {

struct WdcIconDef { const char* name; qreal viewBox; const char* d; };

// Order = enum Icon. ChevronLeft is built from ChevronRight (mirror around x = 12), d left empty.
const std::array<WdcIconDef, int(Icon::Count)> wdci_defs = {{
    {"CalendarTodayOutlined", 24,
     "M20 3h-1V1h-2v2H7V1H5v2H4c-1.1 0-2 .9-2 2v16c0 1.1.9 2 2 2h16c1.1 0 2-.9 2-2V5c0-1.1-.9-2-2-2zm0 18H4V10h16v11zm0"
     "-13H4V5h16v3z"},
    {"CropFreeRounded", 24,
     "M3 5v3c0 .55.45 1 1 1s1-.45 1-1V6c0-.55.45-1 1-1h2c.55 0 1-.45 1-1s-.45-1-1-1H5c-1.1 0-2 .9-2 2zm1 10c-.55 0-1"
     " .45-1 1v3c0 1.1.9 2 2 2h3c.55 0 1-.45 1-1s-.45-1-1-1H6c-.55 0-1-.45-1-1v-2c0-.55-.45-1-1-1zm15 3c0 .55-.45 1-1"
     " 1h-2c-.55 0-1 .45-1 1s.45 1 1 1h3c1.1 0 2-.9 2-2v-3c0-.55-.45-1-1-1s-1 .45-1 1v2zm0-15h-3c-.55 0-1 .45-1 1s.45"
     " 1 1 1h2c.55 0 1 .45 1 1v2c0 .55.45 1 1 1s1-.45 1-1V5c0-1.1-.9-2-2-2z"},
    {"Settings", 24,
     "M19.14 12.94c.04-.3.06-.61.06-.94 0-.32-.02-.64-.07-.94l2.03-1.58c.18-.14.23-.41.12-.61l-1.92-3.32c-.12-.22-.37"
     "-.29-.59-.22l-2.39.96c-.5-.38-1.03-.7-1.62-.94l-.36-2.54c-.04-.24-.24-.41-.48-.41h-3.84c-.24 0-.43.17-.47.41l-."
     "36 2.54c-.59.24-1.13.57-1.62.94l-2.39-.96c-.22-.08-.47 0-.59.22L2.74 8.87c-.12.21-.08.47.12.61l2.03 1.58c-.05.3"
     "-.09.63-.09.94s.02.64.07.94l-2.03 1.58c-.18.14-.23.41-.12.61l1.92 3.32c.12.22.37.29.59.22l2.39-.96c.5.38 1.03.7"
     " 1.62.94l.36 2.54c.05.24.24.41.48.41h3.84c.24 0 .44-.17.47-.41l.36-2.54c.59-.24 1.13-.56 1.62-.94l2.39.96c.22.0"
     "8.47 0 .59-.22l1.92-3.32c.12-.22.07-.47-.12-.61l-2.01-1.58zM12 15.6c-1.98 0-3.6-1.62-3.6-3.6s1.62-3.6 3.6-3.6 3"
     ".6 1.62 3.6 3.6-1.62 3.6-3.6 3.6z"},
    {"Cached", 24,
     "m19 8-4 4h3c0 3.31-2.69 6-6 6-1.01 0-1.97-.25-2.8-.7l-1.46 1.46C8.97 19.54 10.43 20 12 20c4.42 0 8-3.58 8-8h3l-"
     "4-4zM6 12c0-3.31 2.69-6 6-6 1.01 0 1.97.25 2.8.7l1.46-1.46C15.03 4.46 13.57 4 12 4c-4.42 0-8 3.58-8 8H1l4 4 4-4"
     "H6z"},
    {"InfoRounded", 24,
     "M12 2C6.48 2 2 6.48 2 12s4.48 10 10 10 10-4.48 10-10S17.52 2 12 2zm0 15c-.55 0-1-.45-1-1v-4c0-.55.45-1 1-1s1 .45"
     " 1 1v4c0 .55-.45 1-1 1zm1-8h-2V7h2v2z"},
    {"RestartAlt", 24,
     "M12 5V2L8 6l4 4V7c3.31 0 6 2.69 6 6 0 2.97-2.17 5.43-5 5.91v2.02c3.95-.49 7-3.85 7-7.93 0-4.42-3.58-8-8-8zm-6 8c"
     "0-1.65.67-3.15 1.76-4.24L6.34 7.34C4.9 8.79 4 10.79 4 13c0 4.08 3.05 7.44 7 7.93v-2.02c-2.83-.48-5-2.94-5-5.91z"},
    {"ResizeHandleDiagonal", 19,
     "M19.003 6.667 6.99 18.679 5.813 17.5 17.824 5.488zM18.679 1.182l-17.5 17.736L0 17.739 17.5.004zM18.677 12.5 12."
     "5 18.678 11.32 17.5 17.5 11.32z"},
    {"Add", 24, "M19 13h-6v6h-2v-6H5v-2h6V5h2v6h6v2z"},
    {"AddRounded", 24,
     "M18 13h-5v5c0 .55-.45 1-1 1s-1-.45-1-1v-5H6c-.55 0-1-.45-1-1s.45-1 1-1h5V6c0-.55.45-1 1-1s1 .45 1 1v5h5c.55 0 1 "
     ".45 1 1s-.45 1-1 1z"},
    {"ArrowDropDown", 24, "m7 10 5 5 5-5z"},
    {"ChevronRight", 24, "M10 6 8.59 7.41 13.17 12l-4.58 4.59L10 18l6-6z"},
    {"ChevronLeft", 24, ""},
    {"Cancel", 24,
     "M12 2C6.47 2 2 6.47 2 12s4.47 10 10 10 10-4.47 10-10S17.53 2 12 2zm5 13.59L15.59 17 12 13.41 8.41 17 7 15.59 10"
     ".59 12 7 8.41 8.41 7 12 10.59 15.59 7 17 8.41 13.41 12 17 15.59z"},
    {"CalendarExpanded20", 20,
     "M16.25 2.5h-1.875v-.625a.625.625 0 1 0-1.25 0V2.5h-6.25v-.625a.625.625 0 0 0-1.25 0V2.5H3.75A1.25 1.25 0 0 0 2."
     "5 3.75v12.5a1.25 1.25 0 0 0 1.25 1.25h12.5a1.25 1.25 0 0 0 1.25-1.25V3.75a1.25 1.25 0 0 0-1.25-1.25M5.625 3.75v"
     ".625a.625.625 0 0 0 1.25 0V3.75h6.25v.625a.625.625 0 1 0 1.25 0V3.75h1.875v2.5H3.75v-2.5zm10.625 12.5H3.75V7.5h"
     "12.5z"},
    {"Share", 24,
     "M18 16.08c-.76 0-1.44.3-1.96.77L8.91 12.7c.05-.23.09-.46.09-.7s-.04-.47-.09-.7l7.05-4.11c.54.5 1.25.81 2.04.81 "
     "1.66 0 3-1.34 3-3s-1.34-3-3-3-3 1.34-3 3c0 .24.04.47.09.7L8.04 9.81C7.5 9.31 6.79 9 6 9c-1.66 0-3 1.34-3 3s1.34"
     " 3 3 3c.79 0 1.5-.31 2.04-.81l7.12 4.16c-.05.21-.08.43-.08.65 0 1.61 1.31 2.92 2.92 2.92 1.61 0 2.92-1.31 2.92-"
     "2.92s-1.31-2.92-2.92-2.92z"},
    {"FileDownloadOutlined", 24,
     "M18 15v3H6v-3H4v3c0 1.1.9 2 2 2h12c1.1 0 2-.9 2-2v-3h-2zm-1-4-1.41-1.41L13 12.17V4h-2v8.17L8.41 9.59 7 11l5 5 5-"
     "5z"},
    {"Fullscreen", 24, "M7 14H5v5h5v-2H7v-3zm-2-4h2V7h3V5H5v5zm12 7h-3v2h5v-5h-2v3zM14 5v2h3v3h2V5h-5z"},
    {"Percent", 24,
     "M7.5 11C9.43 11 11 9.43 11 7.5S9.43 4 7.5 4 4 5.57 4 7.5 5.57 11 7.5 11zm0-5C8.33 6 9 6.67 9 7.5S8.33 9 7.5 9 6"
     " 8.33 6 7.5 6.67 6 7.5 6zM4.0025 18.5832 18.59 3.9955l1.4142 1.4143L5.4167 19.9974zM16.5 13c-1.93 0-3.5 1.57-3.5"
     " 3.5s1.57 3.5 3.5 3.5 3.5-1.57 3.5-3.5-1.57-3.5-3.5-3.5zm0 5c-.83 0-1.5-.67-1.5-1.5s.67-1.5 1.5-1.5 1.5.67 1.5 1"
     ".5-.67 1.5-1.5 1.5z"},
    {"InsertLinkRounded", 24,
     "M3.96 11.38C4.24 9.91 5.62 8.9 7.12 8.9h2.93c.52 0 .95-.43.95-.95S10.57 7 10.05 7H7.22c-2.61 0-4.94 1.91-5.19 4"
     ".51C1.74 14.49 4.08 17 7 17h3.05c.52 0 .95-.43.95-.95s-.43-.95-.95-.95H7c-1.91 0-3.42-1.74-3.04-3.72zM9 13h6c.5"
     "5 0 1-.45 1-1s-.45-1-1-1H9c-.55 0-1 .45-1 1s.45 1 1 1zm7.78-6h-2.83c-.52 0-.95.43-.95.95s.43.95.95.95h2.93c1.5 "
     "0 2.88 1.01 3.16 2.48.38 1.98-1.13 3.72-3.04 3.72h-3.05c-.52 0-.95.43-.95.95s.43.95.95.95H17c2.92 0 5.26-2.51 4."
     "98-5.49-.25-2.6-2.59-4.51-5.2-4.51z"},
}};

bool wdci_wsp(QChar c) { return c == u' ' || c == u'\t' || c == u'\n' || c == u'\r' || c == u'\f'; }

bool wdci_cmd(QChar c) { return QStringView(u"MmLlHhVvCcSsQqTtAaZz").contains(c); }

/// SVG number: sign, digits, optional fraction, optional exponent; ".55-.45" and "1.5.5" split as SVG does.
bool wdci_number(QStringView d, int* i, double* v) {
    const int n = int(d.size()), start = *i;
    int k = start;
    if (k < n && (d[k] == u'+' || d[k] == u'-')) ++k;
    bool digits = false;
    while (k < n && d[k].isDigit()) { ++k; digits = true; }
    if (k < n && d[k] == u'.') {
        ++k;
        while (k < n && d[k].isDigit()) { ++k; digits = true; }
    }
    if (!digits) return false;
    if (k < n && (d[k] == u'e' || d[k] == u'E')) {
        int e = k + 1;
        if (e < n && (d[e] == u'+' || d[e] == u'-')) ++e;
        if (e < n && d[e].isDigit()) {
            while (e < n && d[e].isDigit()) ++e;
            k = e;
        }
    }
    bool ok = false;
    *v = d.mid(start, k - start).toDouble(&ok);
    *i = k;
    return ok;
}

/// Endpoint arc to cubics (SVG implementation notes F.6), as ChbSvgPath.cpp ChbgBuilder::arcTo.
void wdci_arc(QPainterPath& path, QPointF p0, double rx, double ry, double phi, bool large, bool sweep, QPointF p1) {
    if (std::fabs(p1.x() - p0.x()) < 1e-12 && std::fabs(p1.y() - p0.y()) < 1e-12) return;
    rx = std::fabs(rx);
    ry = std::fabs(ry);
    if (rx == 0 || ry == 0) { path.lineTo(p1); return; }
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
    const double step = dt / segs, k = 4.0 / 3.0 * std::tan(step / 4);
    auto map = [&](double x, double y) { return QPointF(cx + cs * rx * x - sn * ry * y, cy + sn * rx * x + cs * ry * y); };
    double t = t1;
    for (int s = 0; s < segs; ++s) {
        const double c1 = std::cos(t), s1 = std::sin(t), c2 = std::cos(t + step), s2 = std::sin(t + step);
        path.cubicTo(map(c1 - k * s1, s1 + k * c1), map(c2 + k * s2, s2 - k * c2), s + 1 == segs ? p1 : map(c2, s2));
        t += step;
    }
}

QString wdcs_cacheKey(const QRectF& box, qreal radius, const std::vector<ShadowLayer>& layers, qreal dpr) {
    QString k = QStringLiteral("%1x%2r%3d%4").arg(box.width()).arg(box.height()).arg(radius).arg(dpr);
    for (const ShadowLayer& l : layers)
        k += QStringLiteral("|%1,%2,%3,%4,%5").arg(l.dx).arg(l.dy).arg(l.blur).arg(l.spread).arg(l.color.rgba());
    return k;
}

/// Separable Gaussian blur of an 8-bit alpha buffer in place.
void wdcs_blur(std::vector<float>& a, int w, int h, double sigma) {
    if (sigma < 0.05) return;
    const int r = std::max(1, int(std::ceil(sigma * 3)));
    std::vector<float> ker(size_t(2 * r + 1));
    float sum = 0;
    for (int i = -r; i <= r; ++i) sum += ker[size_t(i + r)] = float(std::exp(-0.5 * i * i / (sigma * sigma)));
    for (float& v : ker) v /= sum;
    std::vector<float> tmp(a.size());
    for (int y = 0; y < h; ++y)
        for (int x = 0; x < w; ++x) {
            float s = 0;
            for (int i = -r; i <= r; ++i) {
                const int xx = x + i;
                if (xx >= 0 && xx < w) s += a[size_t(y * w + xx)] * ker[size_t(i + r)];
            }
            tmp[size_t(y * w + x)] = s;
        }
    for (int y = 0; y < h; ++y)
        for (int x = 0; x < w; ++x) {
            float s = 0;
            for (int i = -r; i <= r; ++i) {
                const int yy = y + i;
                if (yy >= 0 && yy < h) s += tmp[size_t(yy * w + x)] * ker[size_t(i + r)];
            }
            a[size_t(y * w + x)] = s;
        }
}

QPainterPath wdcs_shape(const QRectF& r, qreal radius) {
    QPainterPath p;
    if (radius < 0) p.addEllipse(r);
    else if (radius > 0) p.addRoundedRect(r, std::min(radius, r.width() / 2), std::min(radius, r.height() / 2));
    else p.addRect(r);
    return p;
}

} // namespace

QPainterPath parseSvgPathData(QStringView d, bool* ok) {
    QPainterPath path;
    path.setFillRule(Qt::WindingFill);
    if (ok) *ok = false;
    const int n = int(d.size());
    int i = 0;
    QChar prev;
    QPointF cur, start, lastCtrl;
    auto skip = [&] { while (i < n && wdci_wsp(d[i])) ++i; };
    auto sep = [&] { skip(); if (i < n && d[i] == u',') { ++i; skip(); } };
    auto num = [&](double* v) { skip(); if (!wdci_number(d, &i, v)) return false; sep(); return true; };
    auto flag = [&](bool* f) {
        skip();
        if (i < n && (d[i] == u'0' || d[i] == u'1')) { *f = d[i] == u'1'; ++i; sep(); return true; }
        return false;
    };
    auto startsNumber = [&] { skip(); return i < n && (d[i].isDigit() || d[i] == u'.' || d[i] == u'-' || d[i] == u'+'); };
    bool any = false;
    skip();
    while (i < n) {
        const QChar cmd = d[i];
        if (!wdci_cmd(cmd)) return path;
        ++i;
        const QChar C = cmd.toUpper();
        const bool rel = cmd.isLower();
        if (!any && C != u'M') return path;
        any = true;
        if (C == u'Z') {
            path.closeSubpath();
            cur = start;
            prev = C;
            lastCtrl = cur;
            skip();
            continue;
        }
        bool first = true;
        do {
            const QPointF o = rel ? cur : QPointF();
            double a[7];
            switch (C.unicode()) {
            case 'M':
                if (!num(&a[0]) || !num(&a[1])) return path;
                cur = o + QPointF(a[0], a[1]);
                if (first) { path.moveTo(cur); start = cur; } else path.lineTo(cur);
                prev = first ? QChar(u'M') : QChar(u'L');
                break;
            case 'L':
                if (!num(&a[0]) || !num(&a[1])) return path;
                cur = o + QPointF(a[0], a[1]);
                path.lineTo(cur);
                prev = C;
                break;
            case 'H':
                if (!num(&a[0])) return path;
                cur = QPointF(rel ? cur.x() + a[0] : a[0], cur.y());
                path.lineTo(cur);
                prev = C;
                break;
            case 'V':
                if (!num(&a[0])) return path;
                cur = QPointF(cur.x(), rel ? cur.y() + a[0] : a[0]);
                path.lineTo(cur);
                prev = C;
                break;
            case 'C':
                for (int k = 0; k < 6; ++k) if (!num(&a[k])) return path;
                lastCtrl = o + QPointF(a[2], a[3]);
                cur = o + QPointF(a[4], a[5]);
                path.cubicTo(o + QPointF(a[0], a[1]), lastCtrl, cur);
                prev = C;
                break;
            case 'S': {
                for (int k = 0; k < 4; ++k) if (!num(&a[k])) return path;
                const QPointF c1 = (prev == u'C' || prev == u'S') ? cur * 2 - lastCtrl : cur;
                lastCtrl = o + QPointF(a[0], a[1]);
                cur = o + QPointF(a[2], a[3]);
                path.cubicTo(c1, lastCtrl, cur);
                prev = C;
                break;
            }
            case 'Q':
                for (int k = 0; k < 4; ++k) if (!num(&a[k])) return path;
                lastCtrl = o + QPointF(a[0], a[1]);
                cur = o + QPointF(a[2], a[3]);
                path.quadTo(lastCtrl, cur);
                prev = C;
                break;
            case 'T':
                if (!num(&a[0]) || !num(&a[1])) return path;
                lastCtrl = (prev == u'Q' || prev == u'T') ? cur * 2 - lastCtrl : cur;
                cur = o + QPointF(a[0], a[1]);
                path.quadTo(lastCtrl, cur);
                prev = C;
                break;
            case 'A': {
                bool large = false, sweep = false;
                if (!num(&a[0]) || !num(&a[1]) || !num(&a[2]) || !flag(&large) || !flag(&sweep) || !num(&a[3]) ||
                    !num(&a[4]))
                    return path;
                const QPointF to = o + QPointF(a[3], a[4]);
                wdci_arc(path, cur, a[0], a[1], a[2], large, sweep, to);
                cur = to;
                prev = C;
                break;
            }
            default:
                return path;
            }
            first = false;
        } while (startsNumber());
        skip();
    }
    if (ok) *ok = true;
    return path;
}

const QPainterPath& iconPath(Icon icon) {
    // built once for every icon (thread-safe static init: icons may be painted from the render threads)
    static const std::array<QPainterPath, int(Icon::Count)> cache = [] {
        std::array<QPainterPath, int(Icon::Count)> c;
        for (int k = 0; k < int(Icon::Count); ++k)
            if (Icon(k) != Icon::ChevronLeft) c[size_t(k)] = parseSvgPathData(QString::fromLatin1(wdci_defs[size_t(k)].d));
        QTransform mirror(-1, 0, 0, 1, 24, 0); // x -> 24 - x: MUI ChevronLeft "M15.41 7.41 14 6l-6 6 6 6..."
        c[size_t(Icon::ChevronLeft)] = mirror.map(c[size_t(Icon::ChevronRight)]);
        c[size_t(Icon::ChevronLeft)].setFillRule(Qt::WindingFill);
        return c;
    }();
    return cache[size_t(std::clamp(int(icon), 0, int(Icon::Count) - 1))];
}

qreal iconViewBox(Icon icon) { return wdci_defs[size_t(std::clamp(int(icon), 0, int(Icon::Count) - 1))].viewBox; }

QString iconName(Icon icon) {
    return QString::fromLatin1(wdci_defs[size_t(std::clamp(int(icon), 0, int(Icon::Count) - 1))].name);
}

void paintIcon(QPainter& p, Icon icon, const QRectF& target, const QColor& color) {
    const qreal s = std::min(target.width(), target.height()) / iconViewBox(icon);
    p.save();
    p.setRenderHint(QPainter::Antialiasing, true);
    p.translate(target.topLeft());
    p.scale(s, s);
    p.setPen(Qt::NoPen);
    p.setBrush(color);
    p.drawPath(iconPath(icon));
    p.restore();
}

const std::vector<ShadowLayer>& shadowCircleBtn() {
    static const std::vector<ShadowLayer> v = {{0, 3, 1, -2, QColor(166, 176, 195, 51)},
                                               {0, 2, 2, 0, QColor(166, 176, 195, 36)},
                                               {0, 1, 5, 0, QColor(166, 176, 195, 31)}};
    return v;
}

const std::vector<ShadowLayer>& shadowHeaderBtn() {   // HOVER_CSS: .css-yp4adf .MuiButtonBase-root:hover
    static const std::vector<ShadowLayer> v = {{0, 0, 6, 0, QColor(33, 35, 46, 15)}};   // rgba(33,35,46,.06)
    return v;
}

const std::vector<ShadowLayer>& shadowReset() {
    static const std::vector<ShadowLayer> v = {{0, 4, 8, 0, QColor(74, 74, 74, 20)}};
    return v;
}

qreal shadowExtent(const std::vector<ShadowLayer>& layers) {
    qreal e = 0;
    for (const ShadowLayer& l : layers)
        e = std::max(e, l.blur + std::max<qreal>(0, l.spread) + std::max(std::fabs(l.dx), std::fabs(l.dy)));
    return std::ceil(e) + 1;
}

void paintBoxShadow(QPainter& p, const QRectF& box, qreal radius, const std::vector<ShadowLayer>& layers, qreal dpr) {
    if (layers.empty() || box.isEmpty()) return;
    dpr = dpr > 0 ? dpr : 1;
    static QHash<QString, QImage> cache;
    static QMutex mutex;
    const qreal ext = shadowExtent(layers);
    const QString key = wdcs_cacheKey(box, radius, layers, dpr);
    QImage img;
    {
        QMutexLocker lock(&mutex);
        img = cache.value(key);
    }
    if (img.isNull()) {
        const int w = int(std::ceil((box.width() + 2 * ext) * dpr)), h = int(std::ceil((box.height() + 2 * ext) * dpr));
        img = QImage(w, h, QImage::Format_ARGB32_Premultiplied);
        img.fill(Qt::transparent);
        for (const ShadowLayer& l : layers) {
            QImage mask(w, h, QImage::Format_Grayscale8);
            mask.fill(0);
            {
                QPainter mp(&mask);
                mp.setRenderHint(QPainter::Antialiasing, true);
                mp.scale(dpr, dpr);
                const QRectF r = QRectF(ext + l.dx, ext + l.dy, box.width(), box.height())
                                     .adjusted(-l.spread, -l.spread, l.spread, l.spread);
                mp.fillPath(wdcs_shape(r, radius < 0 ? -1 : std::max<qreal>(0, radius + l.spread)), Qt::white);
            }
            std::vector<float> a(size_t(w) * size_t(h));
            for (int y = 0; y < h; ++y) {
                const uchar* row = mask.constScanLine(y);
                for (int x = 0; x < w; ++x) a[size_t(y * w + x)] = row[x] / 255.0f;
            }
            wdcs_blur(a, w, h, l.blur / 2.0 * dpr);
            QImage layer(w, h, QImage::Format_ARGB32_Premultiplied);
            const float ca = float(l.color.alphaF());
            for (int y = 0; y < h; ++y) {
                QRgb* row = reinterpret_cast<QRgb*>(layer.scanLine(y));
                for (int x = 0; x < w; ++x) {
                    const float al = std::clamp(a[size_t(y * w + x)] * ca, 0.0f, 1.0f);
                    row[x] = qPremultiply(qRgba(l.color.red(), l.color.green(), l.color.blue(), int(al * 255 + 0.5f)));
                }
            }
            QPainter ip(&img);
            ip.drawImage(0, 0, layer);
        }
        img.setDevicePixelRatio(dpr);
        QMutexLocker lock(&mutex);
        if (cache.size() > 64) cache.clear();
        cache.insert(key, img);
    }
    p.drawImage(QPointF(box.x() - ext, box.y() - ext), img);
}

void paintHairlineBox(QPainter& p, const QRectF& r, qreal radius, const QColor& fill, const QColor& border, qreal dpr) {
    const qreal b = theme::hairline(dpr);
    p.save();
    p.setRenderHint(QPainter::Antialiasing, true);
    if (fill.alpha() > 0) {
        p.setPen(Qt::NoPen);
        p.setBrush(fill);
        p.drawPath(wdcs_shape(r, radius));
    }
    if (border.alpha() > 0) {
        QPen pen(border, b);
        pen.setJoinStyle(Qt::MiterJoin);
        p.setPen(pen);
        p.setBrush(Qt::NoBrush);
        const QRectF in = r.adjusted(b / 2, b / 2, -b / 2, -b / 2);
        p.drawPath(wdcs_shape(in, radius > 0 ? std::max<qreal>(0, radius - b / 2) : radius));
    }
    p.restore();
}

void paintPopoverFrame(QPainter& p, const QRectF& r, qreal dpr) {
    paintBoxShadow(p, r, theme::kPopoverRadius, shadowCircleBtn(), dpr);
    paintHairlineBox(p, r, theme::kPopoverRadius, theme::color(theme::kPopoverBg), theme::color(theme::kPopoverBorder),
                     dpr);
}

} // namespace fincept::screens::wdc
