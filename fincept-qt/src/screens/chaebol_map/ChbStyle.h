#pragma once
// ChbStyle.h — React-inline-style → CSS computed style for the chaebol_map engine (DESIGN.md §3).
//
// Pipeline: a style dict (ordered JSON) is parsed ONCE into a DeclList of longhand operations, exactly as
// the Chrome oracle applies it: for each key in order, React's styleValue() (number → px unless unitless,
// null/bool/'' → remove) and then CSSOM `el.style[key] = value` (shorthands expand to all their longhands,
// invalid values are ignored, '' removes). cascade() then combines UA rules + author lists into a
// ComputedStyle (inheritance, em/%/rem/vw/vh, keywords). One colour parser (parse_css_color) handles
// #rgb #rgba #rrggbb #rrggbbaa (alpha LAST, unlike QColor), rgb()/rgba(), hsl(), named colours.
#include "screens/chaebol_map/ChbJson.h"

#include <QColor>
#include <QString>
#include <QStringList>
#include <QStringView>

#include <array>
#include <cstdint>
#include <memory>
#include <vector>

namespace fincept::screens::chb {

// ---------------------------------------------------------------------------------------------- tags
enum class Tag : std::uint8_t {
    Unknown, Body, Div, Span, Section, Header, Nav, Main, Footer, Article, Aside, H1, H2, H3, H4, H5, H6, P, Ul, Ol,
    Li, Table, Caption, Thead, Tbody, Tfoot, Tr, Th, Td, Colgroup, Col, Button, Select, Option, Strong, B, Em, I, U,
    S, Code, Pre, Kbd, Br, Hr, A, Small, Sup, Sub, Label, Blockquote, Mark, Img,
    // SVG
    Svg, G, Line, Rect, Path, Polyline, Polygon, Circle, Ellipse, Text, Tspan, Defs, Marker, Pattern,
    LinearGradient, RadialGradient, Stop, ClipPath, Title, Use,
    // engine
    Slot
};
Tag tag_from_name(QStringView name);
bool tag_is_svg(Tag t);           ///< svg and everything drawn by ChbSvg
bool tag_is_svg_child(Tag t);     ///< SVG content element (not the <svg> root)

// ---------------------------------------------------------------------------------------------- enums
enum class Display : std::uint8_t {
    None, Block, Inline, InlineBlock, Flex, InlineFlex, Grid, InlineGrid, Table, InlineTable, TableRowGroup,
    TableHeaderGroup, TableFooterGroup, TableRow, TableCell, TableColumn, TableColumnGroup, TableCaption, ListItem,
    FlowRoot, Contents
};
enum class Position : std::uint8_t { Static, Relative, Absolute, Fixed, Sticky };
enum class BStyle : std::uint8_t { None, Hidden, Solid, Dashed, Dotted, Double, Groove, Ridge, Inset, Outset };
enum class Overflow : std::uint8_t { Visible, Hidden, Clip, Auto, Scroll };
enum class TextAlign : std::uint8_t { Start, Left, Right, Center, Justify, End, WebkitCenter };
enum class WhiteSpace : std::uint8_t { Normal, NoWrap, Pre, PreWrap, PreLine, BreakSpaces };
enum class WordBreak : std::uint8_t { Normal, BreakAll, KeepAll, BreakWord };
enum class OverflowWrap : std::uint8_t { Normal, BreakWord, Anywhere };
enum class TextTransform : std::uint8_t { None, Uppercase, Lowercase, Capitalize };
enum class VAlign : std::uint8_t { Baseline, Middle, Top, Bottom, TextTop, TextBottom, Sub, Super, Length };
enum class FlexDir : std::uint8_t { Row, RowReverse, Column, ColumnReverse };
enum class FlexWrap : std::uint8_t { NoWrap, Wrap, WrapReverse };
/// Shared by justify-content/items/self and align-content/items/self.
enum class Align : std::uint8_t {
    Auto, Normal, Stretch, FlexStart, FlexEnd, Center, Baseline, LastBaseline, Start, End, SelfStart, SelfEnd,
    Left, Right, SpaceBetween, SpaceAround, SpaceEvenly
};
enum class BoxSizing : std::uint8_t { ContentBox, BorderBox };
enum class ListStyle : std::uint8_t { Disc, Circle, Square, Decimal, DecimalLeadingZero, LowerAlpha, UpperAlpha,
                                      LowerRoman, UpperRoman, None };
enum class Visibility : std::uint8_t { Visible, Hidden, Collapse };
enum class FontStyle : std::uint8_t { Normal, Italic, Oblique };
enum class BorderCollapse : std::uint8_t { Separate, Collapse };
enum class TableLayout : std::uint8_t { Auto, Fixed };
enum class GridFlow : std::uint8_t { Row, Column, RowDense, ColumnDense };
enum class LhKind : std::uint8_t { Normal, Number, Px };

// ---------------------------------------------------------------------------------------------- values
/// Specified length: px + em·fs + rem·16 + pct% + vw/vh (calc() folds into one). kind≠Val = keyword.
struct SpecLen {
    enum Kind : std::uint8_t { Val, Auto, None, Normal, MinContent, MaxContent, FitContent, Content };
    float px = 0, em = 0, rem = 0, pct = 0, vw = 0, vh = 0;
    Kind kind = Val;
    bool pctUnit = false; ///< a % term was written (distinguishes 0% from 0px, e.g. flex-basis)
};

/// Computed length: px + pct% of a context-dependent base.
struct Len {
    enum Kind : std::uint8_t { Val, Auto, None, Normal, MinContent, MaxContent, FitContent, Content };
    float px = 0, pct = 0;
    Kind kind = Val;
    bool pctUnit = false; ///< percentage written (0% ≠ 0px when the base is indefinite)
    bool isAuto() const { return kind == Auto; }
    bool isVal() const { return kind == Val; }
    bool hasPct() const { return kind == Val && (pct != 0 || pctUnit); }
    /// base < 0 = unknown/indefinite → percentages resolve to 0.
    float resolve(float base) const { return kind == Val ? px + (base >= 0 ? pct * base / 100.0f : 0.0f) : 0.0f; }
    static Len px_(float v) { Len l; l.px = v; return l; }
    static Len autoLen() { Len l; l.kind = Auto; return l; }
    static Len none() { Len l; l.kind = None; return l; }
};

struct ColorStop {
    QColor color;
    bool hasPos = false;
    Len pos; ///< % of gradient line or px
};
struct Gradient {
    enum Type : std::uint8_t { Linear, Radial } type = Linear;
    bool repeating = false;
    // linear
    float angleDeg = 180; ///< CSS angle (0 = to top, 90 = to right)
    int toCorner = 0;     ///< 0 = explicit angle; else bitmask 1 top 2 right 4 bottom 8 left ("to right bottom")
    // radial
    bool circle = false;
    enum Size : std::uint8_t { FarthestCorner, ClosestSide, ClosestCorner, FarthestSide, Explicit } size = FarthestCorner;
    Len rx, ry;           ///< explicit size
    Len posX, posY;       ///< centre (default 50% 50%)
    std::vector<ColorStop> stops;
};
struct Shadow {
    float x = 0, y = 0, blur = 0, spread = 0;
    QColor color;
    bool currentColor = false;
    bool inset = false;
};
struct TrackSize {
    enum Kind : std::uint8_t { Fixed, Fr, Auto, MinContent, MaxContent, MinMax, FitContent } kind = Auto;
    Len len;           ///< Fixed / FitContent
    float fr = 0;      ///< Fr
    // MinMax: min & max are themselves non-MinMax track sizes
    std::shared_ptr<TrackSize> mn, mx;
};
struct TrackList {
    std::vector<TrackSize> before;  ///< tracks before an auto-repeat (or all tracks when no auto-repeat)
    std::vector<TrackSize> repeat;  ///< auto-fill/auto-fit pattern
    std::vector<TrackSize> after;
    std::uint8_t autoRepeat = 0;    ///< 0 none, 1 auto-fill, 2 auto-fit
    bool none = true;
};
struct GridLine {
    bool isAuto = true;
    int line = 0; ///< 1-based, negative from end
    int span = 0; ///< >0 = span n
};
struct Transform2D {
    bool none = true;
    Len tx, ty;         ///< translate (pct of own border box)
    float rotateDeg = 0;
    float sx = 1, sy = 1;
};

/// Inherited SVG presentation properties that may come from CSS style (fill/stroke…). Strings are raw CSS.
struct SvgProps {
    QString fill, stroke, strokeWidth, strokeDasharray, strokeOpacity, fillOpacity, strokeLinecap,
        strokeLinejoin, textAnchor, dominantBaseline, fontFamilyAttr;
    std::uint32_t own = 0; ///< bit i set = property i was declared on this element (not inherited)
};

// ---------------------------------------------------------------------------------------------- computed
struct ComputedStyle {
    // ---- inherited
    QColor color = QColor(0, 0, 0);
    std::shared_ptr<const QStringList> fontFamily; ///< CSS family names as written (quotes removed)
    float fontSize = 16;
    std::uint8_t fontSizeKw = 4; ///< keyword index (1 xx-small … 4 medium … 8 xxx-large), 0 = absolute
    float fontKwScale = 1;       ///< em/% multiplier applied to the keyword size (Blink keeps keyword-ness)
    int fontWeight = 400;
    FontStyle fontStyle = FontStyle::Normal;
    float letterSpacing = 0; ///< px
    float wordSpacing = 0;
    LhKind lhKind = LhKind::Normal;
    float lhValue = 0; ///< number or px
    TextAlign textAlign = TextAlign::Start;
    TextTransform textTransform = TextTransform::None;
    WhiteSpace whiteSpace = WhiteSpace::Normal;
    WordBreak wordBreak = WordBreak::Normal;
    OverflowWrap overflowWrap = OverflowWrap::Normal;
    ListStyle listStyle = ListStyle::Disc;
    bool listInside = false;
    Visibility visibility = Visibility::Visible;
    BorderCollapse borderCollapse = BorderCollapse::Separate;
    float borderSpacingH = 0, borderSpacingV = 0;
    float textIndent = 0;
    bool cursorPointer = false;
    SvgProps svg;

    // ---- not inherited
    Display display = Display::Inline;
    Position position = Position::Static;
    Len top = Len::autoLen(), right = Len::autoLen(), bottom = Len::autoLen(), left = Len::autoLen();
    int zIndex = 0;
    bool zAuto = true;
    std::array<Len, 4> margin{};  ///< top right bottom left
    std::array<Len, 4> padding{};
    std::array<float, 4> borderW{3, 3, 3, 3}; ///< initial medium = 3px (only visible with a style)
    std::array<BStyle, 4> borderS{BStyle::None, BStyle::None, BStyle::None, BStyle::None};
    std::array<QColor, 4> borderC{};
    std::array<bool, 4> borderCcur{true, true, true, true};
    std::array<Len, 4> radius{}; ///< tl tr br bl (circular)
    Len width = Len::autoLen(), height = Len::autoLen();
    Len minW = Len::autoLen(), minH = Len::autoLen(), maxW = Len::none(), maxH = Len::none();
    BoxSizing boxSizing = BoxSizing::ContentBox;
    QColor bg = QColor(0, 0, 0, 0);
    std::shared_ptr<const std::vector<Gradient>> bgImages;
    std::shared_ptr<const std::vector<Shadow>> shadows;
    float opacity = 1;
    Overflow ovX = Overflow::Visible, ovY = Overflow::Visible;
    bool ellipsis = false;
    VAlign valign = VAlign::Baseline;
    Len valignLen;
    std::uint8_t decoLine = 0; ///< 1 underline, 2 overline, 4 line-through
    QColor decoColor;
    bool decoColorCur = true;
    std::uint8_t decoStyle = 0; ///< 0 solid 1 double 2 dotted 3 dashed 4 wavy
    FlexDir flexDir = FlexDir::Row;
    FlexWrap flexWrap = FlexWrap::NoWrap;
    Align justifyContent = Align::Normal, alignItems = Align::Normal, alignSelf = Align::Auto,
          alignContent = Align::Normal, justifyItems = Align::Normal, justifySelf = Align::Auto;
    float flexGrow = 0, flexShrink = 1;
    Len flexBasis = Len::autoLen();
    int order = 0;
    Len rowGap = Len{0, 0, Len::Normal}, colGap = Len{0, 0, Len::Normal};
    std::shared_ptr<const TrackList> gridCols, gridRows;
    std::shared_ptr<const TrackSize> gridAutoRows, gridAutoCols;
    GridFlow gridFlow = GridFlow::Row;
    GridLine colStart, colEnd, rowStart, rowEnd;
    TableLayout tableLayout = TableLayout::Auto;
    Transform2D transform;
    bool backdropBlur = false; ///< backdrop-filter: blur(>0) — painted as an opaque canvas underlay
    bool isFloat = false; ///< parsed only to warn (floats are not laid out)

    // helpers
    bool isInlineLevel() const;
    bool isBlockContainerDisplay() const;
    bool preservesSpaces() const {
        return whiteSpace == WhiteSpace::Pre || whiteSpace == WhiteSpace::PreWrap || whiteSpace == WhiteSpace::BreakSpaces;
    }
    bool preservesNewlines() const { return preservesSpaces() || whiteSpace == WhiteSpace::PreLine; }
    bool canWrap() const { return whiteSpace != WhiteSpace::NoWrap && whiteSpace != WhiteSpace::Pre; }
    /// Used line-height in px, or <0 for `normal` (caller uses font metrics).
    float lineHeightPx() const {
        return lhKind == LhKind::Normal ? -1.0f : (lhKind == LhKind::Number ? lhValue * fontSize : lhValue);
    }
    QColor borderColor(int side) const { return borderCcur[side] ? color : borderC[side]; }
    float usedBorder(int side) const {
        return (borderS[side] == BStyle::None || borderS[side] == BStyle::Hidden) ? 0.0f : borderW[side];
    }
    bool isPositioned() const { return position != Position::Static; }
    bool isOutOfFlow() const { return position == Position::Absolute || position == Position::Fixed; }
    bool clipsX() const { return ovX != Overflow::Visible; }
    bool clipsY() const { return ovY != Overflow::Visible; }
};

// ---------------------------------------------------------------------------------------------- decls
enum class Prop : std::uint16_t {
    Display, Position, Top, Right, Bottom, Left, ZIndex, Float,
    MarginTop, MarginRight, MarginBottom, MarginLeft,
    PaddingTop, PaddingRight, PaddingBottom, PaddingLeft,
    BorderTopWidth, BorderRightWidth, BorderBottomWidth, BorderLeftWidth,
    BorderTopStyle, BorderRightStyle, BorderBottomStyle, BorderLeftStyle,
    BorderTopColor, BorderRightColor, BorderBottomColor, BorderLeftColor,
    RadiusTL, RadiusTR, RadiusBR, RadiusBL,
    Width, Height, MinWidth, MinHeight, MaxWidth, MaxHeight, BoxSizing,
    BackgroundColor, BackgroundImage, BoxShadow, Opacity, OverflowX, OverflowY, TextOverflow,
    Color, FontFamily, FontSize, FontWeight, FontStyle, LetterSpacing, WordSpacing, LineHeight,
    TextAlign, TextTransform, TextDecorationLine, TextDecorationColor, TextDecorationStyle, WhiteSpace, WordBreak,
    OverflowWrap, VerticalAlign, TextIndent, ListStyleType, ListStylePosition, Visibility, Cursor,
    FlexDirection, FlexWrap, JustifyContent, AlignItems, AlignSelf, AlignContent, JustifyItems, JustifySelf,
    FlexGrow, FlexShrink, FlexBasis, Order, RowGap, ColumnGap,
    GridTemplateColumns, GridTemplateRows, GridAutoRows, GridAutoColumns, GridAutoFlow,
    GridColumnStart, GridColumnEnd, GridRowStart, GridRowEnd,
    BorderCollapse, BorderSpacing, TableLayout, Transform,
    SvgFill, SvgStroke, SvgStrokeWidth, SvgStrokeDasharray, SvgStrokeOpacity, SvgFillOpacity, SvgStrokeLinecap,
    SvgStrokeLinejoin, SvgTextAnchor, SvgDominantBaseline,
    BackdropFilter,
    Count_
};
constexpr int kPropCount = int(Prop::Count_);

struct SpecValue {
    enum Kind : std::uint8_t { Keyword, Length, Number, Color, Ext, Str, Inherit, Initial } kind = Keyword;
    int kw = 0;
    float num = 0;
    SpecLen len;
    QColor color;
    bool currentColor = false;
    QString str;
    std::shared_ptr<const void> ext;
};

struct Decl {
    Prop prop = Prop::Display;
    bool remove = false; ///< CSSOM removal ('' / null / boolean in the React dict)
    SpecValue v;
};

struct DeclList {
    std::vector<Decl> decls;
    std::vector<std::pair<QString, QString>> raw; ///< every (key, CSS string) in order — for SVG/debug
    int unknown = 0;                               ///< keys ignored (not a supported CSS property)
};
using DeclListPtr = std::shared_ptr<const DeclList>;

/// Parse one React style dict (ordered). Never fails; invalid entries are dropped like CSSOM does.
DeclListPtr parse_style_dict(const JVal& dict);
/// UA declarations for a tag (static, parsed once). `link` = <a> with href. `listDepth` = number of ul/ol
/// ancestors (Chrome UA: nested lists lose their block margins; ul → circle at depth 1, square at depth ≥ 2);
/// for <tr>: 1 = direct child of <table> (Chrome UA `table > tr { vertical-align: middle }`).
const DeclList& ua_decls(Tag tag, bool link, int listDepth = 0);

struct StyleEnv {
    float vw = 1600, vh = 1000; ///< viewport for vw/vh units
    float rootFontSize = 16;    ///< rem base
};
/// Compute `out` for an element: inherited from `parent` (nullptr = initial), then UA(tag), then `lists`
/// in order (later wins, removal reverts to UA/inherited).
void cascade(ComputedStyle& out, const ComputedStyle* parent, Tag tag, bool link,
             const std::vector<const DeclList*>& lists, const StyleEnv& env, int listDepth = 0);
/// Anonymous box style: inherited properties only, display as given.
ComputedStyle anonymous_style(const ComputedStyle& parent, Display d);

// ---------------------------------------------------------------------------------------------- parsing helpers
/// THE colour parser. Returns false for invalid input. `current` receives true for currentColor.
bool parse_css_color(QStringView s, QColor* out, bool* current = nullptr);
/// Length/percentage/calc() → SpecLen. `allowNumber` accepts a bare number as px (SVG/unitless contexts).
bool parse_css_length(QStringView s, SpecLen* out, bool allowNumber = false);
/// Resolve a SpecLen at an element (font size known).
Len resolve_len(const SpecLen& s, float fontSize, const StyleEnv& env);
/// Split a CSS value on top-level whitespace / commas (parentheses aware).
QStringList css_split_ws(QStringView s);
QStringList css_split_commas(QStringView s);
/// Parse gradients list ("linear-gradient(...), radial-gradient(...)") — nullptr on invalid.
std::shared_ptr<const std::vector<Gradient>> parse_css_gradients(QStringView s);
/// Parse `font-family` into a clean list (quotes removed, order kept).
QStringList parse_font_family(QStringView s);

} // namespace fincept::screens::chb
