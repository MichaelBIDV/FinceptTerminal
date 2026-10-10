// src/screens/hdcv_launchpad/HlpTheme.h
// HĐCV LAUNCHPAD (tab "hdcv_launchpad") — design tokens of the web Launchpad
// (~/SECOND BRAIN-OBSIDIAN/_System/launchpad/index.html) AS RENDERED, i.e. after
// /sys/design_system.css overrides :root. Values measured in Chrome on 2026-09-27 (see
// _System/fincept_bridge/harness/hdcv_launchpad/SPEC.md §1). Never re-derive them from index.html
// alone: design_system.css changes --bg/--bg-2/--panel/--line/--amber/--up/--down/--cyan/--cheap
// and sets --r to 14px.
#pragma once

#include <QColor>
#include <QPainterPath>
#include <QFont>
#include <QImage>
#include <QPointF>
#include <QRectF>
#include <QString>

class QPainter;

namespace fincept::screens::hlp {

struct Palette {
    QColor bg, bg2, panel, panelHd, line, line2;
    QColor ink, ink2, ink3;
    QColor amber, amberDim, up, down, flat, cyan, violet;
    QColor cheap, rich, neutral;
};

/// Current theme. Dark is the default (index.html data-theme="dark"); ◐ toggles.
bool is_dark();
void set_dark(bool dark);
const Palette& pal();

constexpr float kRadius = 14.0f; ///< --r after design_system.css (panels, tiles, inputs, tabs, warn…)
constexpr float kGap = 6.0f;     ///< --gap

/// CSS `color-mix(in oklab, c P%, transparent)` → c with alpha P/100 (what Chrome renders).
QColor mixT(const QColor& c, float pct);
/// "rgba(r,g,b,a)" for the few QSS strings the shell needs.
QString css(const QColor& c);

/// Font families actually used by Chrome on this Mac:
///  --sans "-apple-system…" → SF Pro  (Qt family ".AppleSystemUIFont")
///  --mono "ui-monospace,\"SF Mono\",Menlo…" → Menlo (Chrome has no ui-monospace; SF Mono is not a
///         public family) — measured: '0' = 7.2246px @12px in both Chrome and Qt Menlo.
///  <select> gets Arial (form controls do not inherit font).
/// px = CSS font-size; weight = CSS weight (400/600/700); ls_px = letter-spacing in px (em × size).
QFont sans(float px, int weight = 400, float ls_px = 0.0f, bool italic = false);
QFont mono(float px, int weight = 400, float ls_px = 0.0f, bool italic = false);
QFont arial(float px, int weight = 400);

// ---- text through the engine's own shaper (same advances, glyphs and fallback fonts as HlpView) ----
// Use these instead of QFontMetricsF / QPainter::drawText for anything that must line up with
// engine-laid-out text (chart labels, custom() painters). monoFamily: true = --mono (Menlo),
// false = --sans (SF Pro). lsPx = letter-spacing in px (added after every character, like CSS).

/// Advance width in px — exactly what the engine gives the same string in a line box.
float textWidth(const QString& text, bool monoFamily, float px, int weight = 400, float lsPx = 0.0f,
                bool italic = false);
/// Paint `text` with its pen origin at `baseline` (x = start of the text, y = baseline). The point is
/// used as given: no pixel snapping (HTML text in HlpView snaps y itself — round y to mimic it; keep it
/// fractional for SVG <text>).
void drawText(QPainter& p, QPointF baseline, const QString& text, bool monoFamily, float px, int weight,
              const QColor& color, float lsPx = 0.0f, bool italic = false);
/// Font ascent/descent as Blink uses them for line boxes (each rounded to 0.5px). A line box of
/// line-height L puts the baseline at top + ascent + floor_to_0.5((L − ascent − descent) / 2).
struct TextVMetrics {
    float ascent = 0.0f;
    float descent = 0.0f;
};
TextVMetrics textVMetrics(bool monoFamily, float px, int weight = 400);

// ---- rounded boxes as Chrome rasterises them ----
/// Corner radii (x, y), clockwise from top-left (tl, tr, br, bl).
struct Radii4 {
    QPointF c[4];
    static Radii4 all(double r) { return {{QPointF(r, r), QPointF(r, r), QPointF(r, r), QPointF(r, r)}}; }
};
/// Fill a rounded box the way Chrome's GPU raster (Skia analytic antialiasing) does: coverage sampled at
/// pixel centres — straight edges exact, corner arcs clamp(0.5 − distance to the arc), which a small
/// radius (tags 2px, chips, 7px dots) shows very differently from QPainter's area coverage. With
/// `hole`, coverage × (1 − hole coverage) per pixel: Skia's drawDRRect (a border ring) or clip-out.
/// Radii must already be fitted (CSS corner overlap). Uses the painter's composition mode; a painter
/// that is not translation/scale-only falls back to QPainterPath.
void fillRRect(QPainter& p, const QRectF& r, const Radii4& rad, const QColor& color, const QRectF* hole = nullptr,
               const Radii4* holeRad = nullptr);
/// A rounded box whose only border is on the left (.tile): the crescent Chrome paints — outer rrect
/// with analytic AA × clip-out of the inner rrect (`inner`/`ik`, radii shrunk per axis) sampled 4× MSAA
/// × the left side's quad (hard, pixel centres). False: the painter is not translation-only.
bool fillLeftBorderRRect(QPainter& p, const QRectF& outer, const Radii4& outerRad, const QRectF& inner,
                         const Radii4& innerRad, const QColor& color);
/// Separable [a, 1−2a, a] filter of a premultiplied layer (ax across x, then ay across y) — how Chrome
/// shows the box-shadowed ruler dots (HlpCharts.cpp).
QImage softenLayer(const QImage& layer, double ax, double ay);
/// An open polyline (moveTo/lineTo) stroked as SVG does in Chrome (SkStroke): butt caps, miter joins
/// turning into bevels past miter-limit 4; one counter-clockwise polygon per segment and join, winding fill.
QPainterPath svgMiterStroke(const QPainterPath& polyline, double width);

/// The same three for form-control text (`<select>` → Arial, which does not inherit the page font).
float textWidthArial(const QString& text, float px, int weight = 400);
void drawTextArial(QPainter& p, QPointF baseline, const QString& text, float px, int weight, const QColor& color);
TextVMetrics textVMetricsArial(float px, int weight = 400);

} // namespace fincept::screens::hlp
