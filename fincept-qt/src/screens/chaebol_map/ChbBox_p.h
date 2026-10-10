#pragma once
// ChbBox_p.h — internal box tree of the chaebol_map engine (layout results live here). Not an API: the View
// uses ChbDom.h. Coordinates: every box stores (x, y) of its BORDER box relative to `ref`'s border box
// (parent for block flow, the inline formatting root for atomic inlines, the containing block for
// absolutely positioned boxes); finalize_positions() turns that into document coordinates (ax, ay).
#include "screens/chaebol_map/ChbNode.h"
#include "screens/chaebol_map/ChbStyle.h"
#include "screens/chaebol_map/ChbText.h"

#include <QRectF>
#include <QString>

#include <cmath>
#include <limits>
#include <memory>
#include <vector>

namespace fincept::screens::chb {

enum class BoxKind : std::uint8_t {
    Block,         ///< block container (block flow or inline formatting context)
    Flex,
    Grid,
    Table,
    RowGroup,
    Row,
    Cell,
    Inline,        ///< non-atomic inline element
    Text,          ///< text run
    Replaced,      ///< <svg>, <select>
    Br
};

struct InlineLayout;

struct Box {
    RNode* node = nullptr;               ///< nullptr = anonymous box
    const ComputedStyle* st = nullptr;   ///< text boxes: the parent element's style
    Box* parent = nullptr;               ///< box-tree parent
    std::vector<Box*> kids;              ///< box-tree children in document order (incl. out-of-flow)
    BoxKind kind = BoxKind::Block;
    bool anonymous = false;
    bool atomic = false;                 ///< atomic inline-level (inline-block/flex/grid/table, replaced)
    bool blockLevel = false;             ///< block-level in its parent's flow
    bool outOfFlow = false;              ///< position absolute/fixed
    bool bfcRoot = false;
    bool inlineContent = false;          ///< block container holding an inline formatting context
    bool isButton = false, isSelect = false, isSvg = false, isListItem = false;
    bool clips = false;                  ///< overflow != visible (clip to padding box)
    bool scrollX = false;                ///< overflow-x auto/scroll → horizontal scroll region

    // ---- used box model (px)
    float mt = 0, mr = 0, mb = 0, ml = 0;
    float bt = 0, br = 0, bb = 0, bl = 0;
    float pt = 0, pr = 0, pb = 0, pl = 0;
    float x = 0, y = 0, w = 0, h = 0;    ///< border box, relative to `ref`
    Box* ref = nullptr;
    float ax = 0, ay = 0;                ///< document position of the border box (unscrolled)
    float relX = 0, relY = 0;            ///< position:relative + translate offsets (included in ax/ay)
    bool positioned = false;             ///< finalize_positions reached this box

    float contentW() const { return std::max(0.0f, w - bl - br - pl - pr); }
    float contentH() const { return std::max(0.0f, h - bt - bb - pt - pb); }
    float contentX() const { return bl + pl; } ///< content box origin relative to the border box
    float contentY() const { return bt + pt; }

    // ---- formatting results
    std::unique_ptr<InlineLayout> ifc;   ///< inline formatting context (inlineContent boxes)
    float firstBaseline = std::numeric_limits<float>::quiet_NaN(); ///< from border-box top
    float lastBaseline = std::numeric_limits<float>::quiet_NaN();
    float definiteH = -1;                ///< content-box height usable for children's % heights (−1 = auto)
    bool forcedW = false, forcedH = false;

    // ---- intrinsic sizes (border box), cached per layout generation
    int intrinsicGen = -1;
    float minContent = 0, maxContent = 0;

    // ---- out-of-flow
    std::vector<Box*> absKids;           ///< boxes whose containing block is this box
    bool cbIcb = false;                  ///< containing block is the initial containing block
    Box* staticParent = nullptr;         ///< box whose border box the static position is relative to
    float staticX = 0, staticY = 0;
    bool absDone = false;

    // ---- table
    int colSpan = 1, rowSpan = 1, col = 0, row = 0;
    float collapsedB[4] = {0, 0, 0, 0}; ///< collapse mode: full edge widths owned/painted (t r b l)
    QColor collapsedC[4];
    BStyle collapsedS[4] = {BStyle::None, BStyle::None, BStyle::None, BStyle::None};
    bool collapsePaint[4] = {false, false, false, false};

    // ---- list marker (outside)
    QString marker;
    float markerX = 0, markerBaseline = 0; ///< relative to border box
    const ShapedText* markerShape = nullptr;
    int markerSymbol = 0;                  ///< 1 disc, 2 circle, 3 square (painted shape, Blink symbol marker)
    QRectF markerRect;                     ///< symbol rect relative to the border box

    // ---- paint / scroll
    QRectF overflow;                     ///< visual overflow in document coords (for culling)
    float scrollW = 0;                   ///< scroll container: scrollable width (from padding-box left)
    int regionId = -1;                   ///< index into Document scroll regions
    int stackOrder = 0;

    // text boxes
    QString rawText;                     ///< text node content (before white-space processing)
};

/// One entry of the inline paragraph.
struct InlineItem {
    enum Type : std::uint8_t { Text, Open, Close, Atomic, Break };
    Type type = Text;
    Box* box = nullptr;                  ///< text box / inline box / atomic box / br box
    Box* parentInline = nullptr;         ///< enclosing inline box (nullptr = root inline box)
    int start = 0, end = 0;              ///< range in the paragraph string
    const ComputedStyle* st = nullptr;
    const FontEntry* fe = nullptr;
    const ShapedText* shape = nullptr;   ///< text: shaped [start, end)
    float edge = 0;                      ///< Open: margin+border+padding start; Close: end; Atomic: outer width
    bool collapsible = true;             ///< text: spaces collapse/hang (white-space normal/nowrap/pre-line)
    bool canWrap = true;                 ///< soft wrap allowed inside/after this item
    bool breakAll = false;
    bool anywhere = false;               ///< overflow-wrap anywhere/break-word
};

/// A piece of an item on one line.
struct InlineFrag {
    enum Type : std::uint8_t { Text, InlineBox, Atomic, Ellipsis };
    Type type = Text;
    Box* box = nullptr;
    int item = -1;
    int line = 0;
    int from = 0, to = 0;                ///< text: range within the item (0-based)
    float x = 0, w = 0;                  ///< relative to the IFC root border box
    float top = 0, height = 0;           ///< text: content area; inline box: border box; atomic: border box
    float baseline = 0;                  ///< relative to the IFC root border box
    bool leftEdge = false, rightEdge = false;
    const ShapedText* shape = nullptr;   ///< text / ellipsis
    int depth = 0;                       ///< inline nesting depth (paint order of inline backgrounds)
    float fullW = 0;                     ///< text cut by text-overflow: width before truncation (Chrome reports both)
    bool hanging = false;                ///< preserved trailing spaces hanging past the line end (pre-wrap)
};

struct LineBox {
    float top = 0, height = 0, baseline = 0; ///< relative to the IFC root border box
    float left = 0, width = 0;               ///< content extent
    int fragBegin = 0, fragEnd = 0;
};

struct InlineLayout {
    QString para;
    std::vector<InlineItem> items;
    std::vector<int> breakOk;            ///< per position 0..n: 0 none, 1 soft, 2 mandatory
    std::vector<int> posItem;            ///< per char: index of the item covering it
    std::vector<std::pair<Box*, int>> absAt; ///< out-of-flow children and their paragraph position
    bool prepared = false;
    bool hasContent = false;             ///< any non-collapsed text / atomic / br / decorated inline box
    std::vector<LineBox> lines;
    std::vector<InlineFrag> frags;
    float height = 0;
    // intrinsic (content box widths)
    int intrinsicGen = -1;
    float minW = 0, maxW = 0;
};

} // namespace fincept::screens::chb
