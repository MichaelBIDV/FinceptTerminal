#pragma once
// ChbSvg.h — SVG subset renderer interface for the chaebol_map engine (DESIGN.md §3.3).
//
// The CSS engine treats <svg> as a replaced box (ChbLayout sizes it from width/height/viewBox like Chrome); this
// module paints its subtree (resolved RNodes with their ComputedStyle, attributes in RNode::src->attrs as JS
// strings, React camelCase names) into the svg content box, and reports element boxes / text client rects for the
// geometry dump. Supported: viewBox + preserveAspectRatio, g/a/nested svg, transform, line/rect(rx, ry)/circle/
// ellipse/polyline/polygon/path (full path grammar, arcs), text/tspan (x/y/dx/dy lists, text-anchor chunks,
// dominant-baseline, letter-spacing, fonts via ChbFonts/ChbText), fill/stroke (+ opacity, width, dasharray/offset,
// linecap/linejoin/miterlimit, fill-rule), group opacity, markers, patterns. Gradients fall back to their first
// stop colour; clipPath/mask/filter/use/image/textPath are not rendered.
// Implementation: ChbSvg.cpp (walk, paint, markers, patterns), ChbSvgParse.cpp, ChbSvgPath.cpp, ChbSvgText.cpp.
#include "screens/chaebol_map/ChbNode.h"

#include <QPainter>
#include <QRectF>
#include <QTransform>

#include <vector>

namespace fincept::screens::chb::svg {

/// Map from the svg user space (viewBox) to document coordinates for a content box `viewport`.
QTransform viewbox_transform(const RNode* svg, const QRectF& viewport);
/// Paint the subtree of `svg` into `viewport` (document coordinates; painter maps document space).
void paint_svg(QPainter& p, const RNode* svg, const QRectF& viewport);
/// Bounding box (document coordinates, no stroke) of an SVG descendant — like getBoundingClientRect.
QRectF node_bbox(const RNode* svg, const QRectF& viewport, const RNode* node);
/// Client rects (document coordinates) of an SVG text node (child of <text>/<tspan>).
std::vector<QRectF> text_rects(const RNode* svg, const QRectF& viewport, const RNode* textNode);

} // namespace fincept::screens::chb::svg
