// src/screens/hdcv_launchpad/HlpCharts.cpp
// HĐCV LAUNCHPAD — the four graphics of panels.js as custom nodes (see HlpCharts.h):
//   spark()    panels.js 20–35   SVG polyline sparkline + lo/hi row
//   sigmaBar() panels.js 37–49   .bandbar (4 zones + amber marker) + σ label row
//   ruler()    panels.js 203–236 .ruler of the "THƯỚC σ" panel (axis, ticks, labels, dots)
//   wdChart()  panels.js 906–982 wdSlice + wdChartHtml + wdHover (WiData line/area chart)
// SVG semantics reproduced: viewBox + preserveAspectRatio="none" stretches x to the real width and
// y to the real height (circles become ellipses), vector-effect:non-scaling-stroke keeps stroke
// widths / dash lengths in screen px. Pure-HTML parts (lo/hi row, σ labels, .wd-x) are nodes so the
// layout engine places the text like Chrome. Absolutely positioned CSS children that stick out of
// their box (.mk top/bottom −3px, .gl top −2px, .wd-y left of the plot) are painted outside the
// node's content box, exactly like CSS overflow:visible.
#include "screens/hdcv_launchpad/HlpCharts.h"

#include "screens/hdcv_launchpad/HlpAtoms.h"
#include "screens/hdcv_launchpad/HlpFmt.h"
#include "screens/hdcv_launchpad/HlpTheme.h"

#include <QPainter>
#include <QPainterPath>
#include <QPainterPathStroker>
#include <QPolygonF>
#include <QStringList>

#include <algorithm>
#include <cmath>
#include <memory>
#include <utility>

namespace fincept::screens::hlp::charts {

namespace {

// ---- constants taken from panels.js / index.html CSS ----
constexpr double hlpch_kSparkViewW = 300.0;  // spark(series, w = 300, …) viewBox width
// The spark <svg> is an inline replaced element inside `.bd` (12px/1.45 sans): its line box is the
// svg height plus the strut's descent + half-leading below the baseline. Measured in Chrome
// (ck_dump.json: svg 156.3→202.3, next block at 206.7) = 4.4px.
constexpr float hlpch_kSparkStrutBelow = 4.4f;

constexpr float hlpch_kBandH = 20.0f;       // .bandbar height
constexpr float hlpch_kMarkOut = 3.0f;      // .mk top:-3px; bottom:-3px
constexpr float hlpch_kMarkW = 2.0f;        // .mk width

constexpr float hlpch_kRulerH = 30.0f;      // .ruler height
constexpr double hlpch_kAxisTop = 15.0;     // .axis top
constexpr double hlpch_kTickTop = 8.0;      // .gp top
constexpr double hlpch_kTickH = 15.0;       // .gp height
constexpr double hlpch_kLabelTop = -2.0;    // .gl top
constexpr double hlpch_kDotTop = 11.0;      // .d top
constexpr double hlpch_kDotD = 7.0;         // .d 7×7
constexpr double hlpch_kDotOpacity = 0.72;  // .d opacity

constexpr double hlpch_kWdW = 600.0, hlpch_kWdH = 200.0; // wdChartHtml viewBox
constexpr float hlpch_kPlotH = 210.0f;                    // .wd-plot height (border-box)
constexpr double hlpch_kGutterBase = 34.0;                // .wd-chartcol padding-left

// ---- small JS-equivalent helpers ----

/// `(x).toFixed(1)` read back as a number (the SVG point strings of panels.js).
double hlpch_fx1(double v) {
    return fmt::toFixed(v, 1).toDouble();
}

/// JS `a || b` for numbers: 0 and NaN are falsy.
double hlpch_or(double a, double b) {
    return (a == 0.0 || std::isnan(a)) ? b : a;
}

/// Math.max(0, Math.min(100, (s + 2.5) / 5 * 100)) — the σ → % mapping of sigmaBar and the ruler.
double hlpch_sigPct(double s) {
    return std::max(0.0, std::min(100.0, (s + 2.5) / 5.0 * 100.0));
}

QColor hlpch_alpha(QColor c, double a) {
    c.setAlphaF(float(c.alphaF() * a));
    return c;
}

/// Height of a `line-height: normal` line box of `font: <px> var(--mono)` (ascent + descent as Blink
/// rounds them; Menlo has no line gap). 10.5px for 9px Menlo, like Chrome.
double hlpch_lineBox(float px) {
    const TextVMetrics vm = textVMetrics(true, px);
    return double(vm.ascent) + double(vm.descent);
}

/// Width of mono text through the engine's shaper (same advances as the HTML text around it).
double hlpch_textW(float px, const QString& s) {
    return double(textWidth(s, true, px));
}

/// One line of mono HTML text (line-height normal) whose line box has its top-left at `topLeft`, drawn
/// by the engine's shaper. The baseline snaps on the device pixel grid like HlpView's own text: half-pixel
/// snap, then round half up (the painter carries a translation only).
void hlpch_text(QPainter& p, float px, const QColor& c, QPointF topLeft, const QString& s) {
    const double dy = p.worldTransform().dy();
    const double dev = topLeft.y() + double(textVMetrics(true, px).ascent) + dy;
    const double base = std::floor(std::floor(dev * 2.0 + 0.5) / 2.0 + 0.5);
    drawText(p, QPointF(topLeft.x(), base - dy), s, true, px, 400, c);
}

/// A CSS box (the .wd-plot border, an <svg> root) snapped the way the engine snaps boxes: each edge on the
/// half-pixel grid of the device (measured: the WiData plot at device y 216.5 keeps its .5, the spark at
/// 156.8 lands on 157), the viewBox then stretched over the snapped box. Translation-only painter.
QRectF hlpch_svgBox(const QPainter& p, const QRectF& box) {
    const double dx = p.worldTransform().dx(), dy = p.worldTransform().dy();
    const auto r = [](double v) { return std::floor(v * 2.0 + 0.5) / 2.0; };
    const double x0 = r(box.left() + dx), y0 = r(box.top() + dy);
    return QRectF(x0 - dx, y0 - dy, r(box.right() + dx) - x0, r(box.bottom() + dy) - y0);
}

/// Fill a path the way Skia's supersampling scan converter does for SVG shapes (SkScan_AntiPath,
/// SHIFT 2): 4×4 point samples per device pixel, coverage in 1/16 steps (a flat 1.4px line comes out
/// in quarter levels, as in the Chrome capture) — Qt's analytic coverage differs by up to ±30%.
/// The painter carries a translation (+ device scale) only; anything else falls back to Qt's fill.
/// `clip` (painter coordinates, optional): an overflow clip applied the way Skia clips with AA — a
/// pixel the clip edge crosses keeps that fraction of its coverage (the <svg> box on half pixels).
void hlpch_ssFill(QPainter& p, const QPainterPath& path, const QColor& c, const QRectF& clip = QRectF()) {
    const QTransform D = p.deviceTransform();
    if (D.type() > QTransform::TxScale || path.isEmpty()) {
        p.fillPath(path, c);
        return;
    }
    QRect dev = D.mapRect(path.boundingRect()).toAlignedRect().adjusted(-1, -1, 1, 1);
    if (p.hasClipping())
        dev &= D.mapRect(p.clipBoundingRect()).toAlignedRect();
    const QRectF cd = clip.isNull() ? QRectF() : D.mapRect(clip);
    if (!cd.isNull())
        dev &= cd.toAlignedRect();
    if (dev.isEmpty())
        return;
    constexpr int kS = 4;
    QImage ss(dev.width() * kS, dev.height() * kS, QImage::Format_Alpha8);
    ss.fill(0);
    {
        QPainter sp(&ss);
        sp.setRenderHint(QPainter::Antialiasing, false);
        sp.setTransform(D * QTransform::fromTranslate(-dev.x(), -dev.y()) * QTransform::fromScale(kS, kS));
        sp.fillPath(path, QColor(0, 0, 0, 255));
    }
    QImage out(dev.size(), QImage::Format_ARGB32_Premultiplied);
    out.fill(Qt::transparent);
    const int cr = c.red(), cg = c.green(), cb = c.blue(), ca = c.alpha();
    for (int y = 0; y < out.height(); ++y) {
        QRgb* o = reinterpret_cast<QRgb*>(out.scanLine(y));
        const uchar* rows[kS];
        for (int k = 0; k < kS; ++k)
            rows[k] = ss.constScanLine(y * kS + k);
        for (int x = 0; x < out.width(); ++x) {
            // standard 4× MSAA pattern (0.375,0.125) (0.875,0.375) (0.125,0.625) (0.625,0.875)
            const int n = int(rows[0][x * kS + 1] > 127) + int(rows[1][x * kS + 3] > 127) +
                          int(rows[2][x * kS + 0] > 127) + int(rows[3][x * kS + 2] > 127);
            if (!n)
                continue;
            int cov = std::min(255, n * 64);
            if (!cd.isNull()) {
                const double px = dev.x() + x, py = dev.y() + y;
                const double fx = std::clamp(std::min(px + 1.0, cd.right()) - std::max(px, cd.left()), 0.0, 1.0);
                const double fy = std::clamp(std::min(py + 1.0, cd.bottom()) - std::max(py, cd.top()), 0.0, 1.0);
                cov = int(std::lround(cov * fx * fy));
                if (!cov)
                    continue;
            }
            const int a = (cov * ca + 127) / 255;
            o[x] = qRgba((cr * a + 127) / 255, (cg * a + 127) / 255, (cb * a + 127) / 255, a);
        }
    }
    const QTransform rest = p.worldTransform().inverted() * D; // blit 1:1 on device pixels
    p.save();
    p.setWorldTransform(QTransform::fromTranslate(dev.x(), dev.y()) * rest.inverted());
    p.drawImage(QPointF(0, 0), out);
    p.restore();
}

/// SVG stroke (non-scaling, width in device px) through hlpch_ssFill.
void hlpch_ssStroke(QPainter& p, const QPainterPath& path, const QColor& c, double width, Qt::PenJoinStyle join,
                    const QVector<qreal>& dash = {}, const QRectF& clip = QRectF()) {
    if (join == Qt::MiterJoin && dash.isEmpty()) {
        hlpch_ssFill(p, svgMiterStroke(path, width), c, clip);
        return;
    }
    QPainterPathStroker st;
    st.setWidth(width);
    st.setCapStyle(Qt::FlatCap);
    st.setJoinStyle(join);
    st.setMiterLimit(4.0);
    if (!dash.isEmpty())
        st.setDashPattern(dash); // in units of the width, like QPen
    hlpch_ssFill(p, st.createStroke(path), c, clip);
}

void hlpch_fill(QPainter& p, const QRectF& r, const QColor& c) {
    p.setPen(Qt::NoPen);
    p.setBrush(c);
    p.drawRect(r);
}

/// Rounded box with CSS radius clamping (radius ≤ half of each side).
void hlpch_fillRound(QPainter& p, const QRectF& r, double radius, const QColor& c) {
    const double rr = std::max(0.0, std::min({radius, r.width() / 2.0, r.height() / 2.0}));
    fillRRect(p, r, Radii4::all(rr), c); // Skia's analytic corner coverage, like every CSS box
}

/// A CSS box with a 1px border and radius (the .wd-tip) as Chrome paints it: background half a pixel
/// inside the border edge (bleed avoidance), then the ring (drawDRRect).
void hlpch_borderBox(QPainter& p, const QRectF& r, double radius, const QColor& bg, const QColor& border) {
    const double rr = std::max(0.0, std::min({radius, r.width() / 2.0, r.height() / 2.0}));
    fillRRect(p, r.adjusted(0.5, 0.5, -0.5, -0.5), Radii4::all(std::max(0.0, rr - 0.5)), bg);
    const QRectF hole = r.adjusted(1.0, 1.0, -1.0, -1.0);
    const Radii4 hk = Radii4::all(std::max(0.0, rr - 1.0));
    fillRRect(p, r, Radii4::all(rr), border, &hole, &hk);
}

// =============================================================================================
// WiData chart model (panels.js wdSlice / wdChartHtml / wdHover)
// =============================================================================================

struct hlpch_Pt {
    double t = 0.0; ///< ms epoch
    double v = 0.0;
};

struct hlpch_YLabel {
    QString text;
    double topPct = 0.0; ///< `(Y(v) / H * 100).toFixed(1)` — % of the plot padding-box height
    bool amber = false;  ///< the reference label (color:var(--amber))
};

struct hlpch_WdModel {
    QVector<hlpch_Pt> pts;
    double x0 = 0.0, xr = 1.0;
    QVector<QPointF> line;          ///< polyline points in viewBox units (already toFixed(1))
    std::optional<double> refY;     ///< reference line y in viewBox units (toFixed(1))
    QPointF lastDot;                ///< last point in viewBox units (toFixed(1))
    bool up = true;
    QVector<hlpch_YLabel> ylabels;  ///< in DOM order: hi, lo, ref
    QString unit;                   ///< s.don_vi (tip formatting)
};

struct hlpch_WdHover {
    QRectF box;       ///< last painted content box (= plot border box)
    bool inside = false;
    double lx = 0.0;  ///< pointer x in the box (last mousemove)
    int best = -1;    ///< index of the point nearest in time to the pointer
};

/// wdHover's nearest point: f = clamp(x / width), t = x0 + f·xr, nearest by time (first wins ties);
/// re-run at paint, so a move before the first paint of a re-rendered chart still shows the tip.
void hlpch_wdBest(const hlpch_WdModel& m, hlpch_WdHover& hv) {
    const double w = hv.box.width();
    if (!hv.inside || w <= 0.0 || m.pts.isEmpty())
        return;
    const double f = std::min(1.0, std::max(0.0, hv.lx / w));
    const double t = m.x0 + f * m.xr;
    int best = 0;
    for (int i = 0; i < m.pts.size(); ++i)
        if (std::abs(m.pts.at(i).t - t) < std::abs(m.pts.at(best).t - t))
            best = i;
    hv.best = best;
}

/// wdSlice(pts, range): cut to the last N days; a window with <2 points keeps the whole series.
QVector<hlpch_Pt> hlpch_wdSlice(const QVector<hlpch_Pt>& pts, const QString& range) {
    if (range == QLatin1String("all") || pts.isEmpty())
        return pts;
    double days = 0.0;
    if (range == QLatin1String("m3"))
        days = 92.0;
    else if (range == QLatin1String("m6"))
        days = 183.0;
    else if (range == QLatin1String("y1"))
        days = 366.0;
    else
        return pts; // JS: days undefined → cut NaN → empty filter → whole series
    const double cut = pts.last().t - days * 864e5;
    QVector<hlpch_Pt> f;
    for (const auto& p : pts)
        if (p.t >= cut)
            f.push_back(p);
    return f.size() >= 2 ? f : pts;
}

QVector<hlpch_Pt> hlpch_wdPoints(const QJsonObject& s) {
    QVector<hlpch_Pt> out;
    const QJsonArray arr = s.value(QStringLiteral("pts")).toArray();
    out.reserve(arr.size());
    for (const auto& e : arr) {
        const QJsonArray p = e.toArray();
        // JS numeric coercion: null → 0 (QJsonValue::toDouble() does the same).
        out.push_back({p.at(0).toDouble(), p.at(1).toDouble()});
    }
    return out;
}

std::shared_ptr<hlpch_WdModel> hlpch_wdModel(const QJsonObject& s, QVector<hlpch_Pt> pts) {
    auto m = std::make_shared<hlpch_WdModel>();
    m->pts = std::move(pts);
    m->unit = s.value(QStringLiteral("don_vi")).toString();

    const QJsonValue refV = s.value(QStringLiteral("tham_chieu"));
    std::optional<double> ref;
    if (refV.isDouble())
        ref = refV.toDouble();

    double lo = m->pts.first().v, hi = lo;
    for (const auto& p : m->pts) {
        lo = std::min(lo, p.v);
        hi = std::max(hi, p.v);
    }
    if (ref) {
        lo = std::min(lo, *ref);
        hi = std::max(hi, *ref);
    }
    const double pad = hlpch_or(hlpch_or((hi - lo) * 0.08, std::abs(hi) * 0.02), 1.0);
    const double y0 = lo - pad, y1 = hi + pad;
    m->x0 = m->pts.first().t;
    m->xr = hlpch_or(m->pts.last().t - m->x0, 1.0);
    const double x0 = m->x0, xr = m->xr;
    auto X = [&](double t) { return (t - x0) / xr * hlpch_kWdW; };
    auto Y = [&](double v) { return hlpch_kWdH - (v - y0) / (y1 - y0) * hlpch_kWdH; };

    m->line.reserve(m->pts.size());
    for (const auto& p : m->pts)
        m->line.push_back(QPointF(hlpch_fx1(X(p.t)), hlpch_fx1(Y(p.v))));
    m->up = m->pts.last().v >= m->pts.first().v;
    m->lastDot = QPointF(hlpch_fx1(X(m->pts.last().t)), hlpch_fx1(Y(m->pts.last().v)));
    if (ref)
        m->refY = hlpch_fx1(Y(*ref));

    // nhanY / yl(): hi (unless ref === hi), lo (unless ref === lo), ref (amber).
    auto yl = [&](double v, bool amber) {
        m->ylabels.push_back({fmt::wdFmtText(v, QString()), fmt::toFixed(Y(v) / hlpch_kWdH * 100.0, 1).toDouble(),
                              amber});
    };
    if (!(ref && *ref == hi))
        yl(hi, false);
    if (!(ref && *ref == lo))
        yl(lo, false);
    if (ref)
        yl(*ref, true);
    return m;
}

/// gut = max(len(wdFmt(label)))·5.6+8; margin-left = Math.max(0, gut − 34).toFixed(0)
float hlpch_wdMarginLeft(const hlpch_WdModel& m) {
    int maxLen = 0;
    for (const auto& l : m.ylabels)
        maxLen = std::max(maxLen, int(l.text.size()));
    const double gut = maxLen * 5.6 + 8.0;
    return float(fmt::toFixed(std::max(0.0, gut - hlpch_kGutterBase), 0).toDouble());
}

void hlpch_wdPaint(QPainter& p, const QRectF& box, const hlpch_WdModel& m, hlpch_WdHover& hv) {
    const Palette& P = pal();
    hv.box = box;
    hlpch_wdBest(m, hv);
    p.save();
    p.setRenderHint(QPainter::Antialiasing, true);
    p.setRenderHint(QPainter::TextAntialiasing, true);

    // .wd-plot border: 1px left + 1px bottom, line-2, on the snapped border box.
    const QRectF bb = hlpch_svgBox(p, box);
    hlpch_fill(p, QRectF(bb.left(), bb.top(), 1.0, bb.height()), P.line2);
    hlpch_fill(p, QRectF(bb.left() + 1.0, bb.bottom() - 1.0, bb.width() - 1.0, 1.0), P.line2);

    // Absolutely positioned children use the padding box (inside the borders).
    const double padL = box.left() + 1.0, padT = box.top();
    const double padW = std::max(0.0, box.width() - 1.0), padH = std::max(0.0, box.height() - 1.0);

    // .wd-y labels: right edge 4px left of the padding box, vertically centred on top:%.
    const double lh9 = hlpch_lineBox(9.0f);
    for (const auto& l : m.ylabels) {
        const double w = hlpch_textW(9.0f, l.text);
        const double yc = padT + l.topPct / 100.0 * padH;
        hlpch_text(p, 9.0f, l.amber ? P.amber : P.ink3, QPointF(padL - 4.0 - w, yc - lh9 / 2.0), l.text);
    }

    // <svg viewBox="0 0 600 200" preserveAspectRatio="none"> filling the padding box (inset:0): origin on
    // the half-pixel grid, the viewBox stretched over the CSS size (as the spark: a snapped size drifts
    // the right end); every shape filled like Skia (hlpch_ssFill), in document order.
    const QRectF svgCss(padL, padT, padW, padH);
    const QRectF svg(hlpch_svgBox(p, svgCss).topLeft(), svgCss.size());
    const double sx = svg.width() / hlpch_kWdW, sy = svg.height() / hlpch_kWdH;
    auto map = [&](QPointF v) { return QPointF(svg.left() + v.x() * sx, svg.top() + v.y() * sy); };
    const QColor col = m.up ? P.up : P.down;
    const auto hline = [&](double y) {
        QPainterPath l;
        l.moveTo(map(QPointF(0.0, y)));
        l.lineTo(map(QPointF(hlpch_kWdW, y)));
        return l;
    };

    // Grid: 3 dashed lines (2 3) at 25/50/75 %, var(--line), non-scaling 1px stroke.
    for (double f : {0.25, 0.5, 0.75})
        hlpch_ssStroke(p, hline(hlpch_kWdH * f), P.line, 1.0, Qt::MiterJoin, {2.0, 3.0});
    // Reference line: amber, dash 5 4, opacity .7.
    if (m.refY)
        hlpch_ssStroke(p, hline(*m.refY), hlpch_alpha(P.amber, 0.7), 1.0, Qt::MiterJoin, {5.0, 4.0});
    // Area polygon "0,H line W,H", fill = stroke colour, opacity .08 (nonzero fill rule).
    {
        QPolygonF poly;
        poly.reserve(m.line.size() + 2);
        poly << map(QPointF(0.0, hlpch_kWdH));
        for (const auto& pt : m.line)
            poly << map(pt);
        poly << map(QPointF(hlpch_kWdW, hlpch_kWdH));
        QPainterPath area;
        area.setFillRule(Qt::WindingFill);
        area.addPolygon(poly);
        area.closeSubpath();
        hlpch_ssFill(p, area, hlpch_alpha(col, 0.08));
    }
    // Polyline: 1.6px non-scaling, round joins, butt caps.
    {
        QPainterPath pl;
        for (int i = 0; i < m.line.size(); ++i) {
            if (i == 0)
                pl.moveTo(map(m.line.at(i)));
            else
                pl.lineTo(map(m.line.at(i)));
        }
        hlpch_ssStroke(p, pl, col, 1.6, Qt::RoundJoin);
    }
    // Dots r=2.2 (≤40 points) and the amber last dot r=3.4 — radii are in viewBox units, so the
    // non-uniform stretch turns them into ellipses (rx = r·sx, ry = r·sy) like Chrome does.
    const auto dot = [&](QPointF c, double r, const QColor& colour) {
        QPainterPath e;
        e.addEllipse(map(c), r * sx, r * sy);
        hlpch_ssFill(p, e, colour);
    };
    if (m.pts.size() <= 40)
        for (const auto& pt : m.line)
            dot(pt, 2.2, col);
    dot(m.lastDot, 3.4, P.amber);

    // Hover (.wd-plot:hover): crosshair + tip at the point nearest in time.
    if (hv.inside && hv.best >= 0 && hv.best < m.pts.size()) {
        const hlpch_Pt& b = m.pts.at(hv.best);
        const double px = (b.t - m.x0) / m.xr * 100.0;
        // .wd-cross: left px%, top 0 → bottom 0, 1px, ink-3.
        // (HTML boxes: each edge on the half-pixel grid — left 34.0996% → one whole column, 79.6935% →
        // half of two columns, as measured)
        hlpch_fill(p, hlpch_svgBox(p, QRectF(padL + px / 100.0 * padW, padT, 1.0, padH)), P.ink3);

        // .wd-tip: top 4px, padding 3px 6px, 1px line-2 border, radius r, panel bg, 10px mono, ink.
        const QString tipText = fmt::wdDate(qint64(b.t)) + QStringLiteral(" · ") + fmt::wdFmtText(b.v, m.unit);
        const double tw = hlpch_textW(10.0f, tipText) + 2.0 * 6.0 + 2.0;
        const double th = hlpch_lineBox(10.0f) + 2.0 * 3.0 + 2.0;
        const double left = px > 60.0 ? padL + padW - ((100.0 - px) / 100.0 * padW + 6.0) - tw
                                      : padL + px / 100.0 * padW + 6.0;
        const QRectF outer(left, padT + 4.0, tw, th);
        hlpch_borderBox(p, hlpch_svgBox(p, outer), double(kRadius), P.panel, P.line2);
        hlpch_text(p, 10.0f, P.ink, QPointF(left + 1.0 + 6.0, outer.top() + 1.0 + 3.0), tipText);
    }
    p.restore();
}

/// wdHover mousemove (the web's listener on .wd-plot).
void hlpch_wdHover(QPointF local, bool inside, const hlpch_WdModel& m, hlpch_WdHover& hv) {
    hv.inside = inside;
    hv.lx = inside ? local.x() : hv.lx;
    hlpch_wdBest(m, hv);
}

// =============================================================================================
// Ruler (THƯỚC σ)
// =============================================================================================

struct hlpch_RulerState {
    QVector<RulerDot> dots;
    QVector<double> pct; ///< left % of each dot
    int me = -1;         ///< index of the ctx dot (.d.me), −1 if absent
    int hover = -1;      ///< dot under the pointer (.d:hover)
    double width = 0.0;  ///< last painted content width
};

/// Topmost dot under a local point: z-index:2 dots (.me, :hover) first, then reverse DOM order.
/// Hit shape = the 7×7 box with border-radius 50% (Chrome hit-tests the rounded shape).
int hlpch_rulerHit(const hlpch_RulerState& st, QPointF local) {
    if (st.width <= 0.0)
        return -1;
    const double r = hlpch_kDotD / 2.0;
    auto hit = [&](int i) {
        const double cx = st.pct.at(i) / 100.0 * st.width;
        const double cy = hlpch_kDotTop + r;
        const double dx = local.x() - cx, dy = local.y() - cy;
        return dx * dx + dy * dy <= r * r;
    };
    if (st.me >= 0 && hit(st.me))
        return st.me;
    if (st.hover >= 0 && st.hover != st.me && hit(st.hover))
        return st.hover;
    for (int i = st.dots.size() - 1; i >= 0; --i)
        if (hit(i))
            return i;
    return -1;
}

/// `.gl` text: `${v > 0 ? '+' : ''}${v}σ` (JS number text: ASCII "-").
QString hlpch_rulerLabel(int v) {
    return (v > 0 ? QStringLiteral("+") : QString()) + QString::number(v) + QStringLiteral("σ");
}

QColor hlpch_dotColor(double s) {
    const Palette& P = pal();
    return s <= -1.0 ? P.cheap : s >= 1.0 ? P.rich : P.neutral;
}

void hlpch_rulerPaint(QPainter& p, const QRectF& box, hlpch_RulerState& st) {
    const Palette& P = pal();
    st.width = box.width();
    const double x = box.left(), y = box.top(), w = box.width();
    // device grid (translation-only painter): the boxes — .axis, .gp and the translateX(-50%) dots —
    // land on Chrome's half-pixel grid (measured on the ck ruler: dots at 1706.77 → 1707, 1711.30 →
    // 1711.5, y 392.89 → 393; the axis 892.8 → 893); label text keeps its fractional x.
    const double dx = p.worldTransform().dx(), dy = p.worldTransform().dy();
    const auto half = [](double v) { return std::floor(v * 2.0 + 0.5) / 2.0; };
    const auto halfRect = [&](const QRectF& r) {
        const double l = half(r.left() + dx), t = half(r.top() + dy);
        return QRectF(l - dx, t - dy, half(r.right() + dx) - l, half(r.bottom() + dy) - t);
    };
    const auto snapTo = [&half](double v, double d) { return half(v + d) - d; };
    p.save();
    p.setRenderHint(QPainter::Antialiasing, true);
    p.setRenderHint(QPainter::TextAntialiasing, true);

    // .axis: top 15px, 1px, full width, line-2.
    hlpch_fill(p, halfRect(QRectF(x, y + hlpch_kAxisTop, w, 1.0)), P.line2);

    // marks: for v in −2…+2 → .gp tick then .gl label ("-2σ" "-1σ" "0σ" "+1σ" "+2σ", JS number text).
    for (int v = -2; v <= 2; ++v) {
        const double lx = x + (v + 2.5) / 5.0 * w;
        hlpch_fill(p, halfRect(QRectF(lx, y + hlpch_kTickTop, 1.0, hlpch_kTickH)), P.line2);
        const QString s = hlpch_rulerLabel(v);
        // the label box is its LayoutUnit-snapped text width; translateX(-50%) of that
        const double tw = std::ceil(hlpch_textW(9.0f, s) * 128.0 - 1e-3) / 128.0;
        // the text inside keeps its fractional x (glyphs on quarter pixels: "-1σ" at 1177.746 → 1177.75)
        hlpch_text(p, 9.0f, P.ink3, QPointF(lx - tw / 2.0, snapTo(y + hlpch_kLabelTop, dy)), s);
    }

    // dots: 7×7 circles centred on left:p% (translateX(-50%)), top 11px, box on the half-pixel grid.
    const double r = hlpch_kDotD / 2.0;
    auto centre = [&](int i) {
        return QPointF(snapTo(x + st.pct.at(i) / 100.0 * w - r, dx) + r, snapTo(y + hlpch_kDotTop, dy) + r);
    };
    // border-radius:50% boxes → Skia's analytic round-rect coverage (fillRRect)
    const auto disc = [](QPainter& q, QPointF c, double rr, const QColor& col) {
        fillRRect(q, QRectF(c.x() - rr, c.y() - rr, 2.0 * rr, 2.0 * rr), Radii4::all(rr), col);
    };
    for (int i = 0; i < st.dots.size(); ++i) {
        if (i == st.me || i == st.hover)
            continue;
        disc(p, centre(i), r, hlpch_alpha(hlpch_dotColor(st.dots.at(i).sig), hlpch_kDotOpacity));
    }
    // z-index:2 dots in DOM order: opacity 1 + box-shadow 0 0 0 2px panel, 0 0 0 3px amber — outer
    // shadows are clipped out of the element's own box and painted last-first, then the dot itself.
    // Chrome softens such a dot along each axis centred on a pixel centre ([.2 .6 .2]), crisp on a
    // boundary — fitted 27/09 (no probe): ck (847.0, 396.5) y only, max error 24/255; vimo (1325.5, 892.5).
    const QTransform dt = p.deviceTransform(); // translation only (see above)
    for (int i = 0; i < st.dots.size(); ++i) {
        if (i != st.me && i != st.hover)
            continue;
        const QPointF c = centre(i), d = dt.map(c);
        const double R = r + 3.0;
        const QRect dev = QRectF(d.x() - R - 1, d.y() - R - 1, 2 * R + 2, 2 * R + 2).toAlignedRect();
        QImage layer(dev.size(), QImage::Format_ARGB32_Premultiplied);
        layer.fill(Qt::transparent);
        { // a device-aligned layer
            QPainter lp(&layer);
            lp.setRenderHint(QPainter::Antialiasing, true);
            lp.setTransform(QTransform::fromTranslate(dt.dx() - dev.x(), dt.dy() - dev.y()));
            // both spreads, then ONE clip-out of the border box (the panel spread hides the amber one)
            disc(lp, c, R, P.amber);
            disc(lp, c, r + 2.0, P.panel);
            lp.setCompositionMode(QPainter::CompositionMode_DestinationOut);
            disc(lp, c, r, Qt::black);
            lp.setCompositionMode(QPainter::CompositionMode_SourceOver);
            disc(lp, c, r, hlpch_dotColor(st.dots.at(i).sig));
        }
        const auto k = [](double v) { return 0.2 * (1.0 - 2.0 * std::abs(v - std::floor(v) - 0.5)); };
        p.drawImage(QPointF(dev.x() - dt.dx(), dev.y() - dt.dy()), softenLayer(layer, k(d.x()), k(d.y())));
    }
    p.restore();
}

// =============================================================================================
// sigmaBar
// =============================================================================================

void hlpch_bandPaint(QPainter& p, const QRectF& box, double pct) {
    const Palette& P = pal();
    const double x = box.left(), y = box.top(), w = box.width(), h = box.height();
    p.save();
    p.setRenderHint(QPainter::Antialiasing, true);
    // Every piece is an HTML box: offsets resolve to LayoutUnits (1/128 px, floor), edges land on the
    // half-pixel grid of the device (measured: band top/bottom rows 776/796 split like the .pnl edges).
    const auto lu = [](double v) { return std::floor(v * 128.0 + 1e-6) / 128.0; };
    // .bandbar background: bg-2, radius 2px, no overflow clipping (zones cover the corners).
    hlpch_fillRound(p, hlpch_svgBox(p, box), 2.0, P.bg2);
    // <i> zones: class opacity .2; the inline style="opacity:.1" of the two inner zones wins.
    struct Zone {
        double left;
        QColor c;
        double op;
    };
    const Zone zones[] = {{0.0, P.cheap, 0.2}, {0.2, P.cheap, 0.1}, {0.6, P.rich, 0.1}, {0.8, P.rich, 0.2}};
    for (const auto& z : zones)
        hlpch_fill(p, hlpch_svgBox(p, QRectF(x + lu(z.left * w), y, lu(0.2 * w), h)), hlpch_alpha(z.c, z.op));
    // .mk: left p%, 2px wide, top −3 → bottom −3, radius 1px, amber.
    hlpch_fillRound(p,
                    hlpch_svgBox(p, QRectF(x + lu(pct / 100.0 * w), y - hlpch_kMarkOut, hlpch_kMarkW,
                                           h + 2.0 * hlpch_kMarkOut)),
                    1.0, P.amber);
    p.restore();
}

} // namespace

// ---------------------------------------------------------------------------------------------
// spark
// ---------------------------------------------------------------------------------------------
NodeP spark(const QJsonArray& series, float h) {
    if (series.size() < 2)
        return atoms::ndD(QStringLiteral("[CẦN DATA] chuỗi giá"));

    QVector<double> ys;
    ys.reserve(series.size());
    for (const auto& e : series)
        ys.push_back(e.toArray().at(1).toDouble());
    const double lo = *std::min_element(ys.begin(), ys.end());
    const double hi = *std::max_element(ys.begin(), ys.end());
    const double rg = hlpch_or(hi - lo, 1.0);
    const double vh = double(h);

    // Points in viewBox units, rounded like the `toFixed(1)` point string.
    auto pts = std::make_shared<QVector<QPointF>>();
    pts->reserve(ys.size());
    const int n = ys.size();
    for (int i = 0; i < n; ++i)
        pts->push_back(QPointF(hlpch_fx1(double(i) / (n - 1) * hlpch_kSparkViewW),
                               hlpch_fx1(vh - (ys.at(i) - lo) / rg * vh)));
    const bool up = ys.last() >= ys.first();

    N svg = div();
    svg.key(QStringLiteral("svg"))
        .custom([h](float) { return h; },
                [pts, up, vh](QPainter& p, const QRectF& cssBox) {
                    // only the origin snaps; the viewBox is stretched over the CSS size (measured on the
                    // 797.8px P/E spark: a snapped 798px width drifts ¼px by the right end)
                    const QRectF box(hlpch_svgBox(p, cssBox).topLeft(), cssBox.size());
                    const double sx = box.width() / hlpch_kSparkViewW, sy = box.height() / vh;
                    QPainterPath pl;
                    for (int i = 0; i < pts->size(); ++i) {
                        const QPointF q(box.left() + pts->at(i).x() * sx, box.top() + pts->at(i).y() * sy);
                        if (i == 0)
                            pl.moveTo(q);
                        else
                            pl.lineTo(q);
                    }
                    // non-scaling stroke 1.4, SVG defaults: butt caps, miter join (limit 4); the <svg>
                    // clips its overflow (UA overflow:hidden) on its half-pixel box, antialiased —
                    // the miter of a peak at y=0 and a trough at y=46 are cut (measured ck + vimo)
                    hlpch_ssStroke(p, pl, up ? pal().up : pal().down, 1.4, Qt::MiterJoin, {},
                                   hlpch_svgBox(p, cssBox));
                });

    // The anonymous line box that holds the inline <svg>.
    N lineBox = div();
    lineBox.h(h + hlpch_kSparkStrutBelow) << svg;

    // <div style="display:flex;justify-content:space-between" class="mono"> lo · hi (9.5px ink-3)
    N loHi = div();
    loHi.flex(Justify::SpaceBetween).mono().tabnum()
        << span(fmt::toFixed(lo, 1)).c(pal().ink3).size(9.5f)
        << span(fmt::toFixed(hi, 1)).c(pal().ink3).size(9.5f);

    N wrap = div();
    wrap << lineBox << loHi;
    return wrap;
}

// ---------------------------------------------------------------------------------------------
// sigmaBar
// ---------------------------------------------------------------------------------------------
NodeP sigmaBar(std::optional<double> s) {
    if (!s)
        return fmt::ND();
    const double pct = hlpch_sigPct(*s);

    N band = div();
    band.key(QStringLiteral("div.bandbar"))
        .m(5.0f, 0.0f, 2.0f, 0.0f)
        .custom([](float) { return hlpch_kBandH; },
                [pct](QPainter& p, const QRectF& box) { hlpch_bandPaint(p, box, pct); });

    // <div style="display:flex;justify-content:space-between;font:9px var(--mono);color:var(--ink-3)">
    N labels = div();
    labels.flex(Justify::SpaceBetween).mono(9.0f).lhNormal().italic(false).c(pal().ink3);
    for (const char* t : {"−2σ", "−1σ", "μ", "+1σ", "+2σ"})
        labels << span(QString::fromUtf8(t));

    N wrap = div();
    wrap << band << labels;
    return wrap;
}

// ---------------------------------------------------------------------------------------------
// ruler
// ---------------------------------------------------------------------------------------------
NodeP ruler(const QVector<RulerDot>& dots, const QString& ctx, std::function<void(const QString&)> onPick) {
    auto st = std::make_shared<hlpch_RulerState>();
    st->dots = dots;
    st->pct.reserve(dots.size());
    for (int i = 0; i < dots.size(); ++i) {
        st->pct.push_back(hlpch_sigPct(dots.at(i).sig));
        if (st->me < 0 && dots.at(i).t == ctx)
            st->me = i;
    }
    // A later dot with the same ticker would also carry .me — tickers are unique in D.tickers.

    N r = div();
    r.key(QStringLiteral("div.ruler"))
        .m(14.0f, 0.0f, 6.0f, 0.0f)
        .custom([](float) { return hlpch_kRulerH; },
                [st](QPainter& p, const QRectF& box) { hlpch_rulerPaint(p, box, *st); })
        .onHover([st](QPointF local, bool inside) { st->hover = inside ? hlpch_rulerHit(*st, local) : -1; })
        .customPointer([st](QPointF local) { return hlpch_rulerHit(*st, local) >= 0; }) // .d{cursor:pointer}
        .customText([] {
            QStringList gl; // the five .gl labels, one element each
            for (int v = -2; v <= 2; ++v)
                gl << hlpch_rulerLabel(v);
            return gl.join(QLatin1Char('\n'));
        }())
        .onCustomClick([st, onPick = std::move(onPick)](QPointF local) {
            const int i = hlpch_rulerHit(*st, local);
            if (i < 0)
                return false;
            if (onPick)
                onPick(st->dots.at(i).t);
            return true;
        })
        .customTip([st](QPointF local) {
            const int i = hlpch_rulerHit(*st, local);
            if (i < 0)
                return QString();
            // title="${r.t} ${r.pe_sig.toFixed(2)}σ" — toFixed prints an ASCII "-".
            return st->dots.at(i).t + QStringLiteral(" ") + fmt::toFixed(st->dots.at(i).sig, 2) + QStringLiteral("σ");
        });
    return r;
}

// ---------------------------------------------------------------------------------------------
// wdChart
// ---------------------------------------------------------------------------------------------
NodeP wdChart(const QJsonObject& series, const QString& range) {
    const QVector<hlpch_Pt> pts = hlpch_wdSlice(hlpch_wdPoints(series), range);
    if (pts.size() < 2) {
        return atoms::ndD(QStringLiteral("[CẦN DATA] chuỗi mới có %1 điểm — chưa đủ để vẽ. "
                                         "WiData chưa phát đủ tín hiệu cho chỉ tiêu này.")
                              .arg(pts.size()))
            .m(24.0f, 0.0f, 24.0f, 0.0f);
    }

    const std::shared_ptr<const hlpch_WdModel> m = hlpch_wdModel(series, pts);
    auto hv = std::make_shared<hlpch_WdHover>();
    const float ml = hlpch_wdMarginLeft(*m);

    N plot = div();
    plot.key(QStringLiteral("div.wd-plot"))
        .m(6.0f, 0.0f, 2.0f, ml)
        .custom([](float) { return hlpch_kPlotH; },
                [m, hv](QPainter& p, const QRectF& box) { hlpch_wdPaint(p, box, *m, *hv); })
        .onHover([m, hv](QPointF local, bool inside) { hlpch_wdHover(local, inside, *m, *hv); })
        .customText([&m] {
            QStringList yl; // the .wd-y spans (hi, lo, ref) in DOM order
            for (const auto& l : m->ylabels)
                yl << l.text;
            return yl.join(QLatin1Char('\n'));
        }());

    // .wd-x: flex space-between, font 9px mono (line-height normal), ink-3; first · time-middle · last.
    const double midT = m->x0 + m->xr / 2.0;
    N xs = div();
    xs.key(QStringLiteral("div.wd-x"))
        .ml(ml)
        .flex(Justify::SpaceBetween)
        .mono(9.0f)
        .lhNormal()
        .italic(false)
        .c(pal().ink3)
        << span(fmt::wdDate(qint64(m->pts.first().t)))
        << span(fmt::wdDate(qint64(std::trunc(midT)))) // new Date(t) truncates fractional ms
        << span(fmt::wdDate(qint64(m->pts.last().t)));

    N wrap = div();
    wrap << plot << xs;
    return wrap;
}

} // namespace fincept::screens::hlp::charts
