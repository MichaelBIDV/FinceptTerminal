#pragma once
// ChbSvg_p.h — internals of the SVG subset renderer (DESIGN.md §3.3), shared by
//   ChbSvg.cpp       tree walk, paint (fill/stroke/opacity layers), markers, patterns, public API
//   ChbSvgParse.cpp  numbers, lengths, transforms, viewBox, path data, basic shapes, presentation style
//   ChbSvgText.cpp   <text>/<tspan> layout (white-space, x/y/dx/dy lists, chunks + anchor, dominant-baseline,
//                    Blink's "scaled font") and glyph painting
// Coordinates: "user" = the element's user space; "doc" = CSS px of the document (what ChbDom lays out);
// QTransform uses Qt's row-vector order (A * B = apply A, then B).
#include "screens/chaebol_map/ChbNode.h"
#include "screens/chaebol_map/ChbSvg.h"

#include <QColor>
#include <QPainterPath>
#include <QString>
#include <QStringList>
#include <QTransform>

#include <vector>

namespace fincept::screens::chb {
class ShapedText;
}

namespace fincept::screens::chb::svg {

// ---------------------------------------------------------------------------------------------- attributes
const QString* attr(const RNode* r, QStringView name);
/// SVG number (sign, digits, fraction, exponent) at s[*i]; advances *i. False (i unchanged) when none.
bool scan_number(QStringView s, int* i, float* out);
/// Whole string = one number (surrounding white space allowed).
bool parse_number(QStringView s, float* out);
/// Number list separated by white space and/or one comma. `ok` = false on junk (values before it are kept).
std::vector<float> number_list(QStringView s, bool* ok = nullptr);

/// Length context: nearest viewport size (for %) and the element's font size (for em).
struct LenCtx {
    float w = 300, h = 150, fontSize = 16;
    float diag() const;
};
enum class Axis : std::uint8_t { X, Y, Diag };
/// CSS length / percentage / bare number → user units. False on invalid input.
bool parse_length(QStringView s, Axis ax, const LenCtx& c, float* out);
float attr_len(const RNode* r, QStringView name, Axis ax, const LenCtx& c, float def = 0);
/// First value of a length list attribute (x="10 20 30" → 10).
float attr_len_first(const RNode* r, QStringView name, Axis ax, const LenCtx& c, float def = 0);

/// `transform` attribute grammar; invalid → identity with *ok = false (Chrome drops the whole value).
QTransform parse_transform(QStringView s, bool* ok = nullptr);
enum class VbState : std::uint8_t { Absent, Valid, Empty };
/// viewBox="x y w h": Absent (missing or invalid → ignored), Valid, Empty (w or h == 0 → disables rendering).
VbState parse_viewbox(const RNode* r, QRectF* vb);
/// viewBox → viewport per preserveAspectRatio (default xMidYMid meet).
QTransform viewbox_to_viewport(const QRectF& vb, const QString* par, const QRectF& viewport);

// ---------------------------------------------------------------------------------------------- geometry
/// Marker vertex: position + incoming/outgoing tangent (zero vector = none).
struct Vertex {
    QPointF p, in, out;
    bool hasIn = false, hasOut = false;
};
struct Geometry {
    QPainterPath path;            ///< fill rule set by the painter
    std::vector<Vertex> verts;    ///< path/line/polyline/polygon only (markers)
    bool markable = false;
};
/// Path data (M L H V C S Q T A Z, absolute + relative, implicit repeats). Stops at the first error keeping what
/// was parsed (Chrome renders up to the error). Returns false on error.
bool path_from_data(QStringView d, Geometry* g);
/// Geometry of line/rect/circle/ellipse/polyline/polygon/path. False = element renders nothing.
bool shape_geometry(const RNode* r, const LenCtx& c, Geometry* g);

// ---------------------------------------------------------------------------------------------- style
struct PaintRef {
    enum Kind : std::uint8_t { None, Color, Current, Url } kind = None;
    QColor color;
    QString id;                   ///< Url: element id
    Kind fbKind = None;           ///< Url fallback ("url(#p) red"); None = paint nothing if the url is invalid
    QColor fb;
    static PaintRef solid(const QColor& c) {
        PaintRef r;
        r.kind = Color;
        r.color = c;
        return r;
    }
};
enum class Baseline : std::uint8_t { Auto, Middle, Central, Hanging, Mathematical, Ideographic, BeforeEdge, AfterEdge };

/// Inherited presentation state (the non-inherited `opacity` / `transform` / `display` are read by the walker).
struct Style {
    PaintRef fill = PaintRef::solid(QColor(0, 0, 0)), stroke;
    float fillOpacity = 1, strokeOpacity = 1, strokeWidth = 1, dashOffset = 0, miterLimit = 4;
    std::vector<float> dash;      ///< empty = solid
    Qt::PenCapStyle cap = Qt::FlatCap;
    Qt::PenJoinStyle join = Qt::MiterJoin;
    bool evenOdd = false;
    std::uint8_t anchor = 0;      ///< 0 start, 1 middle, 2 end
    Baseline baseline = Baseline::Auto;
    QString markerStart, markerMid, markerEnd; ///< ids ("" = none)
    bool visible = true;
    QColor color;                 ///< CSS color (currentColor)
    float fontSize = 16;
    QStringList fontFamily{QStringLiteral("serif")};
    int fontWeight = 400;
    bool italic = false;
    float letterSpacing = 0;
};
/// Style of `r` from its parent's: own CSS declaration > presentation attribute > inherited. Invalid attribute
/// values are ignored (the inherited value stays), like CSS presentation hints.
Style inherit_style(const RNode* r, const Style& parent, const LenCtx& c);
/// Initial style of the <svg> root before its own attributes (color/font from its CSS box).
Style root_style(const RNode* svg);
/// display:none (CSS or attribute).
bool is_display_none(const RNode* r);
/// Group opacity of `r` (CSS declaration wins over the attribute), clamped to [0, 1].
float element_opacity(const RNode* r);

// ---------------------------------------------------------------------------------------------- text
struct TextFrag {
    const RNode* textNode = nullptr; ///< source text node
    Style st;                        ///< style of the element holding the text
    QString text;                    ///< after white-space collapsing
    const ShapedText* shaped = nullptr; ///< shaped with the scaled font (size × scale)
    float scale = 1;                 ///< Blink's screen font scaling factor
    float x = 0, baseline = 0;       ///< user space, after anchoring and dominant-baseline
    float width = 0;
    QRectF rect;                     ///< user space: text-node client rect (primary font metrics)
    QRectF box;                      ///< user space: contribution to element boxes (rect ∪ glyph ink)
};
/// Lay out one <text> element whose style is `st`; `ctm` = user → doc (gives the font scaling factor).
std::vector<TextFrag> layout_text(const RNode* text, const Style& st, const QTransform& ctm, const LenCtx& c);
/// Draw the glyphs of one fragment in `color` (as given, alpha included). `userToLogical` = painter transform
/// of the fragment's user space.
void paint_text_frag(QPainter& p, const TextFrag& f, const QTransform& userToLogical, const QColor& color);
/// Glyph outlines of a fragment in user space (for stroke / pattern fill); empty for bitmap glyphs.
QPainterPath text_outline(const TextFrag& f);

} // namespace fincept::screens::chb::svg
