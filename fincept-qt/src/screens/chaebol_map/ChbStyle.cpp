// ChbStyle.cpp — tags + cascade (inheritance, UA, author longhand map with CSSOM removal, apply).
#include "screens/chaebol_map/ChbStyle.h"
#include "screens/chaebol_map/ChbStyle_p.h"

#include <QHash>

#include <algorithm>
#include <cmath>

namespace fincept::screens::chb {

// ============================================================================================== tags

Tag tag_from_name(QStringView name) {
    static const QHash<QString, Tag> m = [] {
        QHash<QString, Tag> h;
        const struct { const char* n; Tag t; } t[] = {
            {"body", Tag::Body}, {"div", Tag::Div}, {"span", Tag::Span}, {"section", Tag::Section},
            {"header", Tag::Header}, {"nav", Tag::Nav}, {"main", Tag::Main}, {"footer", Tag::Footer},
            {"article", Tag::Article}, {"aside", Tag::Aside}, {"h1", Tag::H1}, {"h2", Tag::H2}, {"h3", Tag::H3},
            {"h4", Tag::H4}, {"h5", Tag::H5}, {"h6", Tag::H6}, {"p", Tag::P}, {"ul", Tag::Ul}, {"ol", Tag::Ol},
            {"li", Tag::Li}, {"table", Tag::Table}, {"caption", Tag::Caption}, {"thead", Tag::Thead},
            {"tbody", Tag::Tbody}, {"tfoot", Tag::Tfoot}, {"tr", Tag::Tr}, {"th", Tag::Th}, {"td", Tag::Td},
            {"colgroup", Tag::Colgroup}, {"col", Tag::Col}, {"button", Tag::Button}, {"select", Tag::Select},
            {"option", Tag::Option}, {"strong", Tag::Strong}, {"b", Tag::B}, {"em", Tag::Em}, {"i", Tag::I},
            {"u", Tag::U}, {"s", Tag::S}, {"code", Tag::Code}, {"pre", Tag::Pre}, {"kbd", Tag::Kbd},
            {"br", Tag::Br}, {"hr", Tag::Hr}, {"a", Tag::A}, {"small", Tag::Small}, {"sup", Tag::Sup},
            {"sub", Tag::Sub}, {"label", Tag::Label}, {"blockquote", Tag::Blockquote}, {"mark", Tag::Mark},
            {"img", Tag::Img}, {"svg", Tag::Svg}, {"g", Tag::G}, {"line", Tag::Line}, {"rect", Tag::Rect},
            {"path", Tag::Path}, {"polyline", Tag::Polyline}, {"polygon", Tag::Polygon}, {"circle", Tag::Circle},
            {"ellipse", Tag::Ellipse}, {"text", Tag::Text}, {"tspan", Tag::Tspan}, {"defs", Tag::Defs},
            {"marker", Tag::Marker}, {"pattern", Tag::Pattern}, {"linearGradient", Tag::LinearGradient},
            {"radialGradient", Tag::RadialGradient}, {"stop", Tag::Stop}, {"clipPath", Tag::ClipPath},
            {"title", Tag::Title}, {"use", Tag::Use}, {"slot", Tag::Slot}};
        for (const auto& e : t) h.insert(QString::fromLatin1(e.n), e.t);
        return h;
    }();
    return m.value(name.toString(), Tag::Unknown);
}

bool tag_is_svg(Tag t) { return t >= Tag::Svg && t <= Tag::Use; }
bool tag_is_svg_child(Tag t) { return t > Tag::Svg && t <= Tag::Use; }

// ============================================================================================== helpers

bool ComputedStyle::isInlineLevel() const {
    return display == Display::Inline || display == Display::InlineBlock || display == Display::InlineFlex ||
           display == Display::InlineGrid || display == Display::InlineTable;
}

bool ComputedStyle::isBlockContainerDisplay() const {
    return display == Display::Block || display == Display::InlineBlock || display == Display::ListItem ||
           display == Display::FlowRoot || display == Display::TableCell || display == Display::TableCaption;
}

namespace {

const std::shared_ptr<const QStringList>& chbs_initial_family() {
    static const auto f = std::make_shared<const QStringList>(QStringList{QStringLiteral("serif")});
    return f;
}

float chbs_kw_size(int kw, bool mono) {
    static const float normal[9] = {16, 9, 10, 13, 16, 18, 24, 32, 48};
    static const float fixed[9] = {13, 9, 9, 10, 13, 16, 20, 26, 39};
    if (kw < 1 || kw > 8) return mono ? 13 : 16;
    return mono ? fixed[kw] : normal[kw];
}

bool chbs_mono_only(const ComputedStyle& cs) {
    return cs.fontFamily && cs.fontFamily->size() == 1 &&
           cs.fontFamily->first().compare(QLatin1String("monospace"), Qt::CaseInsensitive) == 0;
}

int chbs_bolder(int w) {
    if (w < 350) return 400;
    if (w < 550) return 700;
    return 900;
}
int chbs_lighter(int w) {
    if (w < 550) return 100;
    if (w < 750) return 400;
    return 700;
}

/// Copy inherited fields, reset the rest to initial.
void chbs_inherit(ComputedStyle& out, const ComputedStyle& p) {
    out = ComputedStyle{};
    out.color = p.color;
    out.fontFamily = p.fontFamily;
    out.fontSize = p.fontSize;
    out.fontSizeKw = p.fontSizeKw;
    out.fontKwScale = p.fontKwScale;
    out.fontWeight = p.fontWeight;
    out.fontStyle = p.fontStyle;
    out.letterSpacing = p.letterSpacing;
    out.wordSpacing = p.wordSpacing;
    out.lhKind = p.lhKind;
    out.lhValue = p.lhValue;
    out.textAlign = p.textAlign;
    out.textTransform = p.textTransform;
    out.whiteSpace = p.whiteSpace;
    out.wordBreak = p.wordBreak;
    out.overflowWrap = p.overflowWrap;
    out.listStyle = p.listStyle;
    out.listInside = p.listInside;
    out.visibility = p.visibility;
    out.borderCollapse = p.borderCollapse;
    out.borderSpacingH = p.borderSpacingH;
    out.borderSpacingV = p.borderSpacingV;
    out.textIndent = p.textIndent;
    out.cursorPointer = p.cursorPointer;
    out.svg = p.svg;
    out.svg.own = 0;
}

/// Copy one property from `src` (inherit keyword or UA revert).
void chbs_copy_prop(ComputedStyle& o, const ComputedStyle& s, Prop p) {
    switch (p) {
    case Prop::Display: o.display = s.display; break;
    case Prop::Position: o.position = s.position; break;
    case Prop::Top: o.top = s.top; break;
    case Prop::Right: o.right = s.right; break;
    case Prop::Bottom: o.bottom = s.bottom; break;
    case Prop::Left: o.left = s.left; break;
    case Prop::ZIndex: o.zIndex = s.zIndex; o.zAuto = s.zAuto; break;
    case Prop::BackdropFilter: o.backdropBlur = s.backdropBlur; break;
    case Prop::Float: o.isFloat = s.isFloat; break;
    case Prop::MarginTop: o.margin[0] = s.margin[0]; break;
    case Prop::MarginRight: o.margin[1] = s.margin[1]; break;
    case Prop::MarginBottom: o.margin[2] = s.margin[2]; break;
    case Prop::MarginLeft: o.margin[3] = s.margin[3]; break;
    case Prop::PaddingTop: o.padding[0] = s.padding[0]; break;
    case Prop::PaddingRight: o.padding[1] = s.padding[1]; break;
    case Prop::PaddingBottom: o.padding[2] = s.padding[2]; break;
    case Prop::PaddingLeft: o.padding[3] = s.padding[3]; break;
    case Prop::BorderTopWidth: case Prop::BorderRightWidth: case Prop::BorderBottomWidth: case Prop::BorderLeftWidth: {
        const int i = int(p) - int(Prop::BorderTopWidth);
        o.borderW[i] = s.borderW[i];
        break;
    }
    case Prop::BorderTopStyle: case Prop::BorderRightStyle: case Prop::BorderBottomStyle: case Prop::BorderLeftStyle: {
        const int i = int(p) - int(Prop::BorderTopStyle);
        o.borderS[i] = s.borderS[i];
        break;
    }
    case Prop::BorderTopColor: case Prop::BorderRightColor: case Prop::BorderBottomColor: case Prop::BorderLeftColor: {
        const int i = int(p) - int(Prop::BorderTopColor);
        o.borderC[i] = s.borderCcur[i] ? s.color : s.borderC[i];
        o.borderCcur[i] = false;
        break;
    }
    case Prop::RadiusTL: case Prop::RadiusTR: case Prop::RadiusBR: case Prop::RadiusBL: {
        const int i = int(p) - int(Prop::RadiusTL);
        o.radius[i] = s.radius[i];
        break;
    }
    case Prop::Width: o.width = s.width; break;
    case Prop::Height: o.height = s.height; break;
    case Prop::MinWidth: o.minW = s.minW; break;
    case Prop::MinHeight: o.minH = s.minH; break;
    case Prop::MaxWidth: o.maxW = s.maxW; break;
    case Prop::MaxHeight: o.maxH = s.maxH; break;
    case Prop::BoxSizing: o.boxSizing = s.boxSizing; break;
    case Prop::BackgroundColor: o.bg = s.bg; break;
    case Prop::BackgroundImage: o.bgImages = s.bgImages; break;
    case Prop::BoxShadow: o.shadows = s.shadows; break;
    case Prop::Opacity: o.opacity = s.opacity; break;
    case Prop::OverflowX: o.ovX = s.ovX; break;
    case Prop::OverflowY: o.ovY = s.ovY; break;
    case Prop::TextOverflow: o.ellipsis = s.ellipsis; break;
    case Prop::Color: o.color = s.color; break;
    case Prop::FontFamily: o.fontFamily = s.fontFamily; break;
    case Prop::FontSize: o.fontSize = s.fontSize; o.fontSizeKw = s.fontSizeKw; o.fontKwScale = s.fontKwScale; break;
    case Prop::FontWeight: o.fontWeight = s.fontWeight; break;
    case Prop::FontStyle: o.fontStyle = s.fontStyle; break;
    case Prop::LetterSpacing: o.letterSpacing = s.letterSpacing; break;
    case Prop::WordSpacing: o.wordSpacing = s.wordSpacing; break;
    case Prop::LineHeight: o.lhKind = s.lhKind; o.lhValue = s.lhValue; break;
    case Prop::TextAlign: o.textAlign = s.textAlign; break;
    case Prop::TextTransform: o.textTransform = s.textTransform; break;
    case Prop::TextDecorationLine: o.decoLine = s.decoLine; break;
    case Prop::TextDecorationColor: o.decoColor = s.decoColor; o.decoColorCur = s.decoColorCur; break;
    case Prop::TextDecorationStyle: o.decoStyle = s.decoStyle; break;
    case Prop::WhiteSpace: o.whiteSpace = s.whiteSpace; break;
    case Prop::WordBreak: o.wordBreak = s.wordBreak; break;
    case Prop::OverflowWrap: o.overflowWrap = s.overflowWrap; break;
    case Prop::VerticalAlign: o.valign = s.valign; o.valignLen = s.valignLen; break;
    case Prop::TextIndent: o.textIndent = s.textIndent; break;
    case Prop::ListStyleType: o.listStyle = s.listStyle; break;
    case Prop::ListStylePosition: o.listInside = s.listInside; break;
    case Prop::Visibility: o.visibility = s.visibility; break;
    case Prop::Cursor: o.cursorPointer = s.cursorPointer; break;
    case Prop::FlexDirection: o.flexDir = s.flexDir; break;
    case Prop::FlexWrap: o.flexWrap = s.flexWrap; break;
    case Prop::JustifyContent: o.justifyContent = s.justifyContent; break;
    case Prop::AlignItems: o.alignItems = s.alignItems; break;
    case Prop::AlignSelf: o.alignSelf = s.alignSelf; break;
    case Prop::AlignContent: o.alignContent = s.alignContent; break;
    case Prop::JustifyItems: o.justifyItems = s.justifyItems; break;
    case Prop::JustifySelf: o.justifySelf = s.justifySelf; break;
    case Prop::FlexGrow: o.flexGrow = s.flexGrow; break;
    case Prop::FlexShrink: o.flexShrink = s.flexShrink; break;
    case Prop::FlexBasis: o.flexBasis = s.flexBasis; break;
    case Prop::Order: o.order = s.order; break;
    case Prop::RowGap: o.rowGap = s.rowGap; break;
    case Prop::ColumnGap: o.colGap = s.colGap; break;
    case Prop::GridTemplateColumns: o.gridCols = s.gridCols; break;
    case Prop::GridTemplateRows: o.gridRows = s.gridRows; break;
    case Prop::GridAutoRows: o.gridAutoRows = s.gridAutoRows; break;
    case Prop::GridAutoColumns: o.gridAutoCols = s.gridAutoCols; break;
    case Prop::GridAutoFlow: o.gridFlow = s.gridFlow; break;
    case Prop::GridColumnStart: o.colStart = s.colStart; break;
    case Prop::GridColumnEnd: o.colEnd = s.colEnd; break;
    case Prop::GridRowStart: o.rowStart = s.rowStart; break;
    case Prop::GridRowEnd: o.rowEnd = s.rowEnd; break;
    case Prop::BorderCollapse: o.borderCollapse = s.borderCollapse; break;
    case Prop::BorderSpacing: o.borderSpacingH = s.borderSpacingH; o.borderSpacingV = s.borderSpacingV; break;
    case Prop::TableLayout: o.tableLayout = s.tableLayout; break;
    case Prop::Transform: o.transform = s.transform; break;
    case Prop::SvgFill: o.svg.fill = s.svg.fill; break;
    case Prop::SvgStroke: o.svg.stroke = s.svg.stroke; break;
    case Prop::SvgStrokeWidth: o.svg.strokeWidth = s.svg.strokeWidth; break;
    case Prop::SvgStrokeDasharray: o.svg.strokeDasharray = s.svg.strokeDasharray; break;
    case Prop::SvgStrokeOpacity: o.svg.strokeOpacity = s.svg.strokeOpacity; break;
    case Prop::SvgFillOpacity: o.svg.fillOpacity = s.svg.fillOpacity; break;
    case Prop::SvgStrokeLinecap: o.svg.strokeLinecap = s.svg.strokeLinecap; break;
    case Prop::SvgStrokeLinejoin: o.svg.strokeLinejoin = s.svg.strokeLinejoin; break;
    case Prop::SvgTextAnchor: o.svg.textAnchor = s.svg.textAnchor; break;
    case Prop::SvgDominantBaseline: o.svg.dominantBaseline = s.svg.dominantBaseline; break;
    case Prop::Count_: break;
    }
}

struct ChbsApply {
    ComputedStyle& o;
    const ComputedStyle& parent; ///< inherited source (initial when no parent)
    const StyleEnv& env;

    Len len(const SpecLen& s) const { return resolve_len(s, o.fontSize, env); }

    void apply(const Decl& d) {
        const SpecValue& v = d.v;
        if (v.kind == SpecValue::Inherit) {
            chbs_copy_prop(o, parent, d.prop);
            return;
        }
        if (v.kind == SpecValue::Initial) {
            static const ComputedStyle init = [] {
                ComputedStyle c;
                c.fontFamily = chbs_initial_family();
                return c;
            }();
            chbs_copy_prop(o, init, d.prop);
            return;
        }
        switch (d.prop) {
        case Prop::Display: o.display = Display(v.kw); break;
        case Prop::Position: o.position = Position(v.kw); break;
        case Prop::Top: o.top = len(v.len); break;
        case Prop::Right: o.right = len(v.len); break;
        case Prop::Bottom: o.bottom = len(v.len); break;
        case Prop::Left: o.left = len(v.len); break;
        case Prop::ZIndex:
            if (v.kind == SpecValue::Keyword) { o.zAuto = true; o.zIndex = 0; }
            else { o.zAuto = false; o.zIndex = int(v.num); }
            break;
        case Prop::Float: o.isFloat = v.kw != 0; break;
        case Prop::MarginTop: o.margin[0] = len(v.len); break;
        case Prop::MarginRight: o.margin[1] = len(v.len); break;
        case Prop::MarginBottom: o.margin[2] = len(v.len); break;
        case Prop::MarginLeft: o.margin[3] = len(v.len); break;
        case Prop::PaddingTop: o.padding[0] = len(v.len); break;
        case Prop::PaddingRight: o.padding[1] = len(v.len); break;
        case Prop::PaddingBottom: o.padding[2] = len(v.len); break;
        case Prop::PaddingLeft: o.padding[3] = len(v.len); break;
        case Prop::BorderTopWidth: case Prop::BorderRightWidth: case Prop::BorderBottomWidth: case Prop::BorderLeftWidth: {
            const float w = len(v.len).px;
            // Chrome snaps border widths: ≥1 → floor, (0,1) → 1
            o.borderW[int(d.prop) - int(Prop::BorderTopWidth)] = w <= 0 ? 0.0f : (w < 1 ? 1.0f : std::floor(w));
            break;
        }
        case Prop::BorderTopStyle: case Prop::BorderRightStyle: case Prop::BorderBottomStyle: case Prop::BorderLeftStyle:
            o.borderS[int(d.prop) - int(Prop::BorderTopStyle)] = BStyle(v.kw);
            break;
        case Prop::BorderTopColor: case Prop::BorderRightColor: case Prop::BorderBottomColor: case Prop::BorderLeftColor: {
            const int i = int(d.prop) - int(Prop::BorderTopColor);
            o.borderC[i] = v.color;
            o.borderCcur[i] = v.currentColor;
            break;
        }
        case Prop::RadiusTL: case Prop::RadiusTR: case Prop::RadiusBR: case Prop::RadiusBL:
            o.radius[int(d.prop) - int(Prop::RadiusTL)] = len(v.len);
            break;
        case Prop::Width: o.width = len(v.len); break;
        case Prop::Height: o.height = len(v.len); break;
        case Prop::MinWidth: o.minW = len(v.len); break;
        case Prop::MinHeight: o.minH = len(v.len); break;
        case Prop::MaxWidth: o.maxW = len(v.len); break;
        case Prop::MaxHeight: o.maxH = len(v.len); break;
        case Prop::BoxSizing: o.boxSizing = BoxSizing(v.kw); break;
        case Prop::BackgroundColor: o.bg = v.currentColor ? o.color : v.color; break;
        case Prop::BackgroundImage:
            o.bgImages = std::static_pointer_cast<const std::vector<Gradient>>(v.ext);
            if (o.bgImages && o.bgImages->empty()) o.bgImages.reset();
            break;
        case Prop::BoxShadow:
            o.shadows = std::static_pointer_cast<const std::vector<Shadow>>(v.ext);
            if (o.shadows && o.shadows->empty()) o.shadows.reset();
            break;
        case Prop::Opacity: o.opacity = v.num; break;
        case Prop::OverflowX: o.ovX = Overflow(v.kw); break;
        case Prop::OverflowY: o.ovY = Overflow(v.kw); break;
        case Prop::TextOverflow: o.ellipsis = v.kw == KwEllipsis; break;
        case Prop::Color: o.color = v.currentColor ? parent.color : v.color; break;
        case Prop::FontFamily: // handled in the font pass
        case Prop::FontSize: break;
        case Prop::FontWeight:
            if (v.kind == SpecValue::Keyword) o.fontWeight = v.kw == KwBolder ? chbs_bolder(parent.fontWeight) : chbs_lighter(parent.fontWeight);
            else o.fontWeight = int(v.num);
            break;
        case Prop::FontStyle: o.fontStyle = FontStyle(v.kw); break;
        case Prop::LetterSpacing: o.letterSpacing = v.kind == SpecValue::Keyword ? 0.0f : len(v.len).px; break;
        case Prop::WordSpacing: o.wordSpacing = v.kind == SpecValue::Keyword ? 0.0f : len(v.len).px; break;
        case Prop::LineHeight:
            if (v.kind == SpecValue::Keyword) { o.lhKind = LhKind::Normal; o.lhValue = 0; }
            else if (v.kind == SpecValue::Number) { o.lhKind = LhKind::Number; o.lhValue = v.num; }
            else {
                const Len l = len(v.len);
                o.lhKind = LhKind::Px;
                o.lhValue = l.px + l.pct * o.fontSize / 100.0f;
            }
            break;
        case Prop::TextAlign: o.textAlign = TextAlign(v.kw); break;
        case Prop::TextTransform: o.textTransform = TextTransform(v.kw); break;
        case Prop::TextDecorationLine: o.decoLine = std::uint8_t(v.kw); break;
        case Prop::TextDecorationColor: o.decoColor = v.color; o.decoColorCur = v.currentColor; break;
        case Prop::TextDecorationStyle: o.decoStyle = std::uint8_t(v.kw); break;
        case Prop::WhiteSpace: o.whiteSpace = WhiteSpace(v.kw); break;
        case Prop::WordBreak: o.wordBreak = WordBreak(v.kw); break;
        case Prop::OverflowWrap: o.overflowWrap = OverflowWrap(v.kw); break;
        case Prop::VerticalAlign:
            if (v.kind == SpecValue::Keyword) o.valign = VAlign(v.kw);
            else {
                o.valign = VAlign::Length;
                o.valignLen = len(v.len);
            }
            break;
        case Prop::TextIndent: o.textIndent = len(v.len).px; break;
        case Prop::ListStyleType: o.listStyle = ListStyle(v.kw); break;
        case Prop::ListStylePosition: o.listInside = v.kw == 1; break;
        case Prop::Visibility: o.visibility = Visibility(v.kw); break;
        case Prop::Cursor: o.cursorPointer = v.kw == KwPointer; break;
        case Prop::BackdropFilter: o.backdropBlur = v.num > 0; break;
        case Prop::FlexDirection: o.flexDir = FlexDir(v.kw); break;
        case Prop::FlexWrap: o.flexWrap = FlexWrap(v.kw); break;
        case Prop::JustifyContent: o.justifyContent = Align(v.kw); break;
        case Prop::AlignItems: o.alignItems = Align(v.kw); break;
        case Prop::AlignSelf: o.alignSelf = Align(v.kw); break;
        case Prop::AlignContent: o.alignContent = Align(v.kw); break;
        case Prop::JustifyItems: o.justifyItems = Align(v.kw); break;
        case Prop::JustifySelf: o.justifySelf = Align(v.kw); break;
        case Prop::FlexGrow: o.flexGrow = v.num; break;
        case Prop::FlexShrink: o.flexShrink = v.num; break;
        case Prop::FlexBasis: o.flexBasis = len(v.len); break;
        case Prop::Order: o.order = int(v.num); break;
        case Prop::RowGap: o.rowGap = len(v.len); break;
        case Prop::ColumnGap: o.colGap = len(v.len); break;
        case Prop::GridTemplateColumns: o.gridCols = std::static_pointer_cast<const TrackList>(v.ext); break;
        case Prop::GridTemplateRows: o.gridRows = std::static_pointer_cast<const TrackList>(v.ext); break;
        case Prop::GridAutoRows: o.gridAutoRows = std::static_pointer_cast<const TrackSize>(v.ext); break;
        case Prop::GridAutoColumns: o.gridAutoCols = std::static_pointer_cast<const TrackSize>(v.ext); break;
        case Prop::GridAutoFlow: o.gridFlow = GridFlow(v.kw); break;
        case Prop::GridColumnStart: o.colStart = *std::static_pointer_cast<const GridLine>(v.ext); break;
        case Prop::GridColumnEnd: o.colEnd = *std::static_pointer_cast<const GridLine>(v.ext); break;
        case Prop::GridRowStart: o.rowStart = *std::static_pointer_cast<const GridLine>(v.ext); break;
        case Prop::GridRowEnd: o.rowEnd = *std::static_pointer_cast<const GridLine>(v.ext); break;
        case Prop::BorderCollapse: o.borderCollapse = BorderCollapse(v.kw); break;
        case Prop::BorderSpacing: {
            const auto pr = std::static_pointer_cast<const std::pair<SpecLen, SpecLen>>(v.ext);
            o.borderSpacingH = len(pr->first).px;
            o.borderSpacingV = len(pr->second).px;
            break;
        }
        case Prop::TableLayout: o.tableLayout = TableLayout(v.kw); break;
        case Prop::Transform: o.transform = *std::static_pointer_cast<const Transform2D>(v.ext); break;
        case Prop::SvgFill: o.svg.fill = v.str; o.svg.own |= 1u << 0; break;
        case Prop::SvgStroke: o.svg.stroke = v.str; o.svg.own |= 1u << 1; break;
        case Prop::SvgStrokeWidth: o.svg.strokeWidth = v.str; o.svg.own |= 1u << 2; break;
        case Prop::SvgStrokeDasharray: o.svg.strokeDasharray = v.str; o.svg.own |= 1u << 3; break;
        case Prop::SvgStrokeOpacity: o.svg.strokeOpacity = v.str; o.svg.own |= 1u << 4; break;
        case Prop::SvgFillOpacity: o.svg.fillOpacity = v.str; o.svg.own |= 1u << 5; break;
        case Prop::SvgStrokeLinecap: o.svg.strokeLinecap = v.str; o.svg.own |= 1u << 6; break;
        case Prop::SvgStrokeLinejoin: o.svg.strokeLinejoin = v.str; o.svg.own |= 1u << 7; break;
        case Prop::SvgTextAnchor: o.svg.textAnchor = v.str; o.svg.own |= 1u << 8; break;
        case Prop::SvgDominantBaseline: o.svg.dominantBaseline = v.str; o.svg.own |= 1u << 9; break;
        case Prop::Count_: break;
        }
    }
};

} // namespace

// ============================================================================================== cascade

void cascade(ComputedStyle& out, const ComputedStyle* parent, Tag tag, bool link,
             const std::vector<const DeclList*>& lists, const StyleEnv& env, int listDepth) {
    ComputedStyle initial;
    initial.fontFamily = chbs_initial_family();
    const ComputedStyle& par = parent ? *parent : initial;
    if (parent) chbs_inherit(out, *parent);
    else out = initial;

    // Author longhand map: later wins; removal drops the author value (→ UA/inherited stays).
    const Decl* fin[kPropCount] = {};
    bool any = false;
    for (const DeclList* l : lists) {
        if (!l) continue;
        for (const Decl& d : l->decls) {
            fin[int(d.prop)] = d.remove ? nullptr : &d;
            any = true;
        }
    }
    const DeclList& ua = ua_decls(tag, link, listDepth);

    // ---- font pass: family, then size (monospace quirk needs the final family), then others
    auto finalFor = [&](Prop p) -> const Decl* {
        if (fin[int(p)]) return fin[int(p)];
        const Decl* u = nullptr;
        for (const Decl& d : ua.decls)
            if (d.prop == p && !d.remove) u = &d;
        return u;
    };
    if (const Decl* f = finalFor(Prop::FontFamily)) {
        if (f->v.kind == SpecValue::Inherit) out.fontFamily = par.fontFamily;
        else if (f->v.kind == SpecValue::Initial) out.fontFamily = chbs_initial_family();
        else out.fontFamily = std::static_pointer_cast<const QStringList>(f->v.ext);
    }
    if (!out.fontFamily) out.fontFamily = chbs_initial_family();
    const bool mono = chbs_mono_only(out);
    const bool parMono = chbs_mono_only(par);
    if (const Decl* f = finalFor(Prop::FontSize)) {
        const SpecValue& v = f->v;
        if (v.kind == SpecValue::Inherit) {
            out.fontSize = par.fontSize;
            out.fontSizeKw = par.fontSizeKw;
            out.fontKwScale = par.fontKwScale;
            if (out.fontSizeKw && mono != parMono) out.fontSize = chbs_kw_size(out.fontSizeKw, mono) * out.fontKwScale;
        } else if (v.kind == SpecValue::Initial) {
            out.fontSizeKw = KwFsMedium;
            out.fontKwScale = 1;
            out.fontSize = chbs_kw_size(KwFsMedium, mono);
        } else if (v.kind == SpecValue::Keyword) {
            if (v.kw == KwFsSmaller || v.kw == KwFsLarger) {
                const float k = v.kw == KwFsSmaller ? 1.0f / 1.2f : 1.2f;
                out.fontSizeKw = par.fontSizeKw;
                out.fontKwScale = par.fontKwScale * k;
                out.fontSize = out.fontSizeKw ? chbs_kw_size(out.fontSizeKw, mono) * out.fontKwScale : par.fontSize * k;
            } else {
                out.fontSizeKw = std::uint8_t(v.kw);
                out.fontKwScale = 1;
                out.fontSize = chbs_kw_size(v.kw, mono);
            }
        } else {
            const SpecLen& l = v.len;
            const bool relativeOnly = l.px == 0 && l.rem == 0 && l.vw == 0 && l.vh == 0 && (l.em != 0 || l.pct != 0 || l.pctUnit);
            if (relativeOnly && par.fontSizeKw) {
                // Blink keeps the keyword through em/% so a later switch to `monospace` rescales (13/16)
                const float factor = l.em + l.pct / 100.0f;
                out.fontSizeKw = par.fontSizeKw;
                out.fontKwScale = par.fontKwScale * factor;
                out.fontSize = chbs_kw_size(out.fontSizeKw, mono) * out.fontKwScale;
            } else {
                const float base = par.fontSize;
                out.fontSize = std::max(0.0f, l.px + l.em * base + l.pct * base / 100.0f + l.rem * env.rootFontSize +
                                                  l.vw * env.vw / 100.0f + l.vh * env.vh / 100.0f);
                out.fontSizeKw = 0;
                out.fontKwScale = 1;
            }
        }
    } else if (out.fontSizeKw && mono != parMono) {
        out.fontSize = chbs_kw_size(out.fontSizeKw, mono) * out.fontKwScale; // inherited keyword size re-evaluated
    }

    // ---- remaining properties: UA (in order) then author finals
    ChbsApply ap{out, par, env};
    for (const Decl& d : ua.decls) {
        if (d.remove || d.prop == Prop::FontFamily || d.prop == Prop::FontSize) continue;
        ap.apply(d);
    }
    if (any) {
        // colour first: currentColor in other properties needs the element's final colour
        if (fin[int(Prop::Color)]) ap.apply(*fin[int(Prop::Color)]);
        for (int i = 0; i < kPropCount; ++i) {
            const Decl* d = fin[i];
            if (!d || i == int(Prop::FontFamily) || i == int(Prop::FontSize) || i == int(Prop::Color)) continue;
            ap.apply(*d);
        }
    }

    // th { text-align: -internal-center }: inherits a non-start parent alignment, else centre
    if (tag == Tag::Th && !fin[int(Prop::TextAlign)] && parent && par.textAlign != TextAlign::Start) out.textAlign = par.textAlign;
    // ---- computed-value fix-ups
    if (out.ovX == Overflow::Visible && out.ovY != Overflow::Visible && out.ovY != Overflow::Clip) out.ovX = Overflow::Auto;
    if (out.ovY == Overflow::Visible && out.ovX != Overflow::Visible && out.ovX != Overflow::Clip) out.ovY = Overflow::Auto;
    if (!out.decoColorCur) {} // explicit colour kept
}

ComputedStyle anonymous_style(const ComputedStyle& parent, Display d) {
    ComputedStyle s;
    chbs_inherit(s, parent);
    s.display = d;
    return s;
}

} // namespace fincept::screens::chb
