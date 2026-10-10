// ChbStyleProps.cpp — React style dict → longhand Decl operations (CSSOM semantics) + UA stylesheet.
#include "screens/chaebol_map/ChbStyle.h"
#include "screens/chaebol_map/ChbStyle_p.h"

#include <QHash>
#include <QRegularExpression>
#include <QSet>

#include <cmath>
#include <functional>
#include <mutex>

namespace fincept::screens::chb {

namespace {

using Out = std::vector<Decl>;
using ParseFn = std::function<bool(const QString&, Out&)>;

struct PropDef {
    std::vector<Prop> longhands;
    ParseFn parse;
    bool inherited = false; ///< for `unset`
};

// ---------------------------------------------------------------------------------------------- tiny builders
Decl chbp_kw(Prop p, int kw) {
    Decl d;
    d.prop = p;
    d.v.kind = SpecValue::Keyword;
    d.v.kw = kw;
    return d;
}
Decl chbp_len(Prop p, const SpecLen& l) {
    Decl d;
    d.prop = p;
    d.v.kind = SpecValue::Length;
    d.v.len = l;
    return d;
}
Decl chbp_num(Prop p, float n) {
    Decl d;
    d.prop = p;
    d.v.kind = SpecValue::Number;
    d.v.num = n;
    return d;
}
Decl chbp_color(Prop p, const QColor& c, bool cur) {
    Decl d;
    d.prop = p;
    d.v.kind = SpecValue::Color;
    d.v.color = c;
    d.v.currentColor = cur;
    return d;
}
Decl chbp_ext(Prop p, std::shared_ptr<const void> e) {
    Decl d;
    d.prop = p;
    d.v.kind = SpecValue::Ext;
    d.v.ext = std::move(e);
    return d;
}
Decl chbp_str(Prop p, const QString& s) {
    Decl d;
    d.prop = p;
    d.v.kind = SpecValue::Str;
    d.v.str = s;
    return d;
}

int chbp_lookup(const QString& v, std::initializer_list<std::pair<const char*, int>> table) {
    for (const auto& e : table)
        if (v == QLatin1String(e.first)) return e.second;
    return -1;
}

// ---------------------------------------------------------------------------------------------- value parsers
enum LenFlags : unsigned {
    LAuto = 1, LNone = 2, LNormal = 4, LNeg = 8, LNumber = 16, LSizing = 32, LContent = 64
};

bool chbp_parse_len(const QString& raw, unsigned flags, SpecLen* out) {
    const QString v = raw.trimmed().toLower();
    *out = SpecLen{};
    if ((flags & LAuto) && v == QLatin1String("auto")) { out->kind = SpecLen::Auto; return true; }
    if ((flags & LNone) && v == QLatin1String("none")) { out->kind = SpecLen::None; return true; }
    if ((flags & LNormal) && v == QLatin1String("normal")) { out->kind = SpecLen::Normal; return true; }
    if ((flags & LContent) && v == QLatin1String("content")) { out->kind = SpecLen::Content; return true; }
    if (flags & LSizing) {
        if (v == QLatin1String("min-content")) { out->kind = SpecLen::MinContent; return true; }
        if (v == QLatin1String("max-content")) { out->kind = SpecLen::MaxContent; return true; }
        if (v == QLatin1String("fit-content") || v == QLatin1String("-webkit-fit-content")) {
            out->kind = SpecLen::FitContent;
            return true;
        }
    }
    if (v == QLatin1String("auto")) return false;
    if (!parse_css_length(v, out, flags & LNumber)) return false;
    if (!(flags & LNeg) && (out->px < 0 || out->pct < 0 || out->em < 0 || out->rem < 0)) return false;
    return true;
}

ParseFn chbp_len_fn(Prop p, unsigned flags) {
    return [p, flags](const QString& v, Out& o) {
        SpecLen l;
        if (!chbp_parse_len(v, flags, &l)) return false;
        o.push_back(chbp_len(p, l));
        return true;
    };
}

ParseFn chbp_color_fn(Prop p) {
    return [p](const QString& v, Out& o) {
        QColor c;
        bool cur = false;
        if (!parse_css_color(v, &c, &cur)) return false;
        o.push_back(chbp_color(p, c, cur));
        return true;
    };
}

ParseFn chbp_kw_fn(Prop p, std::initializer_list<std::pair<const char*, int>> table) {
    std::vector<std::pair<QString, int>> t;
    for (const auto& e : table) t.emplace_back(QString::fromLatin1(e.first), e.second);
    return [p, t](const QString& v, Out& o) {
        const QString s = v.trimmed().toLower();
        for (const auto& e : t)
            if (e.first == s) {
                o.push_back(chbp_kw(p, e.second));
                return true;
            }
        return false;
    };
}

bool chbp_float(const QString& v, float* out) {
    bool ok = false;
    const double d = v.trimmed().toDouble(&ok);
    if (!ok || !std::isfinite(d)) return false;
    *out = float(d);
    return true;
}

// border-style keywords
const std::initializer_list<std::pair<const char*, int>> kBStyle = {
    {"none", int(BStyle::None)}, {"hidden", int(BStyle::Hidden)}, {"solid", int(BStyle::Solid)},
    {"dashed", int(BStyle::Dashed)}, {"dotted", int(BStyle::Dotted)}, {"double", int(BStyle::Double)},
    {"groove", int(BStyle::Groove)}, {"ridge", int(BStyle::Ridge)}, {"inset", int(BStyle::Inset)},
    {"outset", int(BStyle::Outset)}};

bool chbp_bwidth(const QString& t, SpecLen* out) {
    const QString s = t.trimmed().toLower();
    *out = SpecLen{};
    if (s == QLatin1String("thin")) { out->px = 1; return true; }
    if (s == QLatin1String("medium")) { out->px = 3; return true; }
    if (s == QLatin1String("thick")) { out->px = 5; return true; }
    return chbp_parse_len(s, 0, out) && out->pct == 0;
}

/// 1–4 value box expansion (top right bottom left).
bool chbp_box4(const QString& v, const std::function<bool(const QString&, Out&, Prop)>& one, const Prop props[4],
               Out& o) {
    const QStringList t = css_split_ws(v.trimmed());
    if (t.isEmpty() || t.size() > 4) return false;
    const QString vals[4] = {t[0], t.size() > 1 ? t[1] : t[0], t.size() > 2 ? t[2] : t[0],
                             t.size() > 3 ? t[3] : (t.size() > 1 ? t[1] : t[0])};
    Out tmp;
    for (int i = 0; i < 4; ++i)
        if (!one(vals[i], tmp, props[i])) return false;
    o.insert(o.end(), tmp.begin(), tmp.end());
    return true;
}

/// `border`/`borderTop`: width style color in any order; missing parts reset to initial.
bool chbp_border_parts(const QString& v, SpecLen* w, int* style, QColor* c, bool* cur) {
    *w = SpecLen{};
    w->px = 3;
    *style = int(BStyle::None);
    *c = QColor(0, 0, 0);
    *cur = true;
    bool haveW = false, haveS = false, haveC = false;
    for (const QString& t : css_split_ws(v.trimmed())) {
        const QString s = t.toLower();
        if (s == QLatin1String("none") && !haveS) {
            haveS = true;
            *style = int(BStyle::None);
            continue;
        }
        const int st = chbp_lookup(s, kBStyle);
        if (st >= 0 && !haveS) {
            haveS = true;
            *style = st;
            continue;
        }
        SpecLen l;
        if (!haveW && chbp_bwidth(s, &l)) {
            haveW = true;
            *w = l;
            continue;
        }
        QColor col;
        bool cc = false;
        if (!haveC && parse_css_color(s, &col, &cc)) {
            haveC = true;
            *c = col;
            *cur = cc;
            continue;
        }
        return false;
    }
    return haveW || haveS || haveC;
}

void chbp_border_side(Out& o, int side, const SpecLen& w, int style, const QColor& c, bool cur) {
    static const Prop W[4] = {Prop::BorderTopWidth, Prop::BorderRightWidth, Prop::BorderBottomWidth, Prop::BorderLeftWidth};
    static const Prop S[4] = {Prop::BorderTopStyle, Prop::BorderRightStyle, Prop::BorderBottomStyle, Prop::BorderLeftStyle};
    static const Prop C[4] = {Prop::BorderTopColor, Prop::BorderRightColor, Prop::BorderBottomColor, Prop::BorderLeftColor};
    o.push_back(chbp_len(W[side], w));
    o.push_back(chbp_kw(S[side], style));
    o.push_back(chbp_color(C[side], c, cur));
}

bool chbp_font_size(const QString& raw, Out& o) {
    const QString v = raw.trimmed().toLower();
    const int kw = chbp_lookup(v, {{"xx-small", KwFsXXSmall}, {"x-small", KwFsXSmall}, {"small", KwFsSmall},
                                   {"medium", KwFsMedium}, {"large", KwFsLarge}, {"x-large", KwFsXLarge},
                                   {"xx-large", KwFsXXLarge}, {"xxx-large", KwFsXXXLarge},
                                   {"smaller", KwFsSmaller}, {"larger", KwFsLarger}});
    if (kw >= 0) {
        o.push_back(chbp_kw(Prop::FontSize, kw));
        return true;
    }
    SpecLen l;
    if (!chbp_parse_len(v, 0, &l)) return false;
    o.push_back(chbp_len(Prop::FontSize, l));
    return true;
}

bool chbp_font_weight(const QString& raw, Out& o) {
    const QString v = raw.trimmed().toLower();
    if (v == QLatin1String("normal")) { o.push_back(chbp_num(Prop::FontWeight, 400)); return true; }
    if (v == QLatin1String("bold")) { o.push_back(chbp_num(Prop::FontWeight, 700)); return true; }
    if (v == QLatin1String("bolder")) { o.push_back(chbp_kw(Prop::FontWeight, KwBolder)); return true; }
    if (v == QLatin1String("lighter")) { o.push_back(chbp_kw(Prop::FontWeight, KwLighter)); return true; }
    float n = 0;
    if (!chbp_float(v, &n) || n < 1 || n > 1000) return false;
    o.push_back(chbp_num(Prop::FontWeight, n));
    return true;
}

bool chbp_line_height(const QString& raw, Out& o) {
    const QString v = raw.trimmed().toLower();
    if (v == QLatin1String("normal")) { o.push_back(chbp_kw(Prop::LineHeight, KwNormal)); return true; }
    float n = 0;
    if (chbp_float(v, &n)) {
        if (n < 0) return false;
        o.push_back(chbp_num(Prop::LineHeight, n));
        return true;
    }
    SpecLen l;
    if (!chbp_parse_len(v, 0, &l)) return false;
    o.push_back(chbp_len(Prop::LineHeight, l));
    return true;
}

bool chbp_spacing(Prop p, const QString& raw, Out& o) {
    const QString v = raw.trimmed().toLower();
    if (v == QLatin1String("normal")) { o.push_back(chbp_kw(p, KwNormal)); return true; }
    SpecLen l;
    if (!chbp_parse_len(v, LNeg, &l) || l.pct != 0) return false;
    o.push_back(chbp_len(p, l));
    return true;
}

const std::initializer_list<std::pair<const char*, int>> kAlign = {
    {"auto", int(Align::Auto)}, {"normal", int(Align::Normal)}, {"stretch", int(Align::Stretch)},
    {"flex-start", int(Align::FlexStart)}, {"flex-end", int(Align::FlexEnd)}, {"center", int(Align::Center)},
    {"baseline", int(Align::Baseline)}, {"first baseline", int(Align::Baseline)},
    {"last baseline", int(Align::LastBaseline)}, {"start", int(Align::Start)}, {"end", int(Align::End)},
    {"self-start", int(Align::SelfStart)}, {"self-end", int(Align::SelfEnd)}, {"left", int(Align::Left)},
    {"right", int(Align::Right)}, {"space-between", int(Align::SpaceBetween)},
    {"space-around", int(Align::SpaceAround)}, {"space-evenly", int(Align::SpaceEvenly)},
    {"safe center", int(Align::Center)}, {"unsafe center", int(Align::Center)}};

bool chbp_flex(const QString& raw, Out& o) {
    const QString v = raw.trimmed().toLower();
    SpecLen basis;
    float grow = 0, shrink = 1;
    if (v == QLatin1String("none")) {
        basis.kind = SpecLen::Auto;
        grow = 0;
        shrink = 0;
    } else if (v == QLatin1String("auto")) {
        basis.kind = SpecLen::Auto;
        grow = 1;
        shrink = 1;
    } else {
        const QStringList t = css_split_ws(v);
        if (t.isEmpty() || t.size() > 3) return false;
        std::vector<float> nums;
        bool haveBasis = false;
        for (const QString& w : t) {
            float n = 0;
            if (chbp_float(w, &n) && !haveBasis && nums.size() < 2) {
                if (n < 0) return false;
                nums.push_back(n);
                continue;
            }
            if (haveBasis) return false;
            if (!chbp_parse_len(w, LAuto | LContent | LSizing, &basis)) return false;
            haveBasis = true;
        }
        if (nums.empty()) { grow = 1; shrink = 1; }
        else {
            grow = nums[0];
            shrink = nums.size() > 1 ? nums[1] : 1;
        }
        if (!haveBasis) { basis = SpecLen{}; basis.pctUnit = true; } // 0%
    }
    o.push_back(chbp_num(Prop::FlexGrow, grow));
    o.push_back(chbp_num(Prop::FlexShrink, shrink));
    o.push_back(chbp_len(Prop::FlexBasis, basis));
    return true;
}

bool chbp_background(const QString& raw, Out& o) {
    const QString v = raw.trimmed();
    QColor color(0, 0, 0, 0);
    bool cur = false, haveColor = false;
    auto imgs = std::make_shared<std::vector<Gradient>>();
    const QStringList layers = css_split_commas(v);
    for (int li = 0; li < layers.size(); ++li) {
        for (const QString& tok : css_split_ws(layers[li])) {
            const QString s = tok.toLower();
            if (s.contains(QLatin1String("gradient("))) {
                auto g = parse_css_gradients(tok);
                if (!g) return false;
                imgs->insert(imgs->end(), g->begin(), g->end());
                continue;
            }
            if (s == QLatin1String("none") || s.startsWith(QLatin1String("url(")) ||
                chbp_lookup(s, {{"repeat", 1}, {"no-repeat", 1}, {"repeat-x", 1}, {"repeat-y", 1}, {"center", 1},
                                {"top", 1}, {"bottom", 1}, {"left", 1}, {"right", 1}, {"cover", 1}, {"contain", 1},
                                {"fixed", 1}, {"scroll", 1}, {"local", 1}, {"/", 1}, {"border-box", 1},
                                {"padding-box", 1}, {"content-box", 1}}) > 0)
                continue;
            QColor c;
            bool cc = false;
            if (li == layers.size() - 1 && !haveColor && parse_css_color(s, &c, &cc)) {
                color = c;
                cur = cc;
                haveColor = true;
                continue;
            }
            SpecLen l;
            if (parse_css_length(s, &l)) continue; // position/size values: ignored
            return false;
        }
    }
    o.push_back(chbp_color(Prop::BackgroundColor, color, cur));
    o.push_back(chbp_ext(Prop::BackgroundImage, imgs));
    return true;
}

bool chbp_text_deco(const QString& raw, Out& o) {
    const QString v = raw.trimmed().toLower();
    int line = 0, style = 0;
    QColor c;
    bool cur = true, haveC = false;
    for (const QString& t : css_split_ws(v)) {
        if (t == QLatin1String("none")) continue;
        if (t == QLatin1String("underline")) { line |= 1; continue; }
        if (t == QLatin1String("overline")) { line |= 2; continue; }
        if (t == QLatin1String("line-through")) { line |= 4; continue; }
        const int st = chbp_lookup(t, {{"solid", 0}, {"double", 1}, {"dotted", 2}, {"dashed", 3}, {"wavy", 4}});
        if (st >= 0) { style = st; continue; }
        bool cc = false;
        if (!haveC && parse_css_color(t, &c, &cc)) { haveC = true; cur = cc; continue; }
        SpecLen th;
        if (parse_css_length(t, &th)) continue; // thickness: ignored
        return false;
    }
    o.push_back(chbp_kw(Prop::TextDecorationLine, line));
    o.push_back(chbp_kw(Prop::TextDecorationStyle, style));
    o.push_back(chbp_color(Prop::TextDecorationColor, haveC ? c : QColor(0, 0, 0), haveC ? cur : true));
    return true;
}

bool chbp_grid_line(Prop p, const QString& v, Out& o) {
    auto gl = std::make_shared<GridLine>();
    if (!parse_css_grid_line(v, gl.get())) return false;
    o.push_back(chbp_ext(p, gl));
    return true;
}

bool chbp_grid_pair(Prop a, Prop b, const QString& raw, Out& o) {
    const QStringList parts = raw.split(QLatin1Char('/'));
    if (parts.size() > 2) return false;
    Out tmp;
    if (!chbp_grid_line(a, parts[0], tmp)) return false;
    if (parts.size() == 2) {
        if (!chbp_grid_line(b, parts[1], tmp)) return false;
    } else {
        tmp.push_back(chbp_ext(b, std::make_shared<GridLine>())); // auto
    }
    o.insert(o.end(), tmp.begin(), tmp.end());
    return true;
}

bool chbp_font_shorthand(const QString& raw, Out& o) {
    // [style] [variant] [weight] size[/line-height] family
    const QString v = raw.trimmed();
    const QStringList t = css_split_ws(v);
    int i = 0;
    Out tmp;
    tmp.push_back(chbp_kw(Prop::FontStyle, int(FontStyle::Normal)));
    tmp.push_back(chbp_num(Prop::FontWeight, 400));
    tmp.push_back(chbp_kw(Prop::LineHeight, KwNormal));
    for (; i < t.size(); ++i) {
        const QString s = t[i].toLower();
        if (s == QLatin1String("italic") || s == QLatin1String("oblique")) { tmp.push_back(chbp_kw(Prop::FontStyle, int(FontStyle::Italic))); continue; }
        if (s == QLatin1String("normal") || s == QLatin1String("small-caps")) continue;
        Out w;
        if (chbp_font_weight(s, w) && !s.endsWith(QLatin1String("px")) && !s.contains(QLatin1Char('/'))) {
            // a bare number could be a weight only when another size token follows
            if (i + 1 < t.size()) { tmp.insert(tmp.end(), w.begin(), w.end()); continue; }
        }
        break;
    }
    if (i >= t.size()) return false;
    QString sz = t[i];
    QString lh;
    const int slash = sz.indexOf(QLatin1Char('/'));
    if (slash > 0) { lh = sz.mid(slash + 1); sz = sz.left(slash); }
    if (!chbp_font_size(sz, tmp)) return false;
    if (!lh.isEmpty() && !chbp_line_height(lh, tmp)) return false;
    ++i;
    if (i >= t.size()) return false;
    const QString fam = QStringList(t.mid(i)).join(QLatin1Char(' '));
    tmp.push_back(chbp_ext(Prop::FontFamily, std::make_shared<const QStringList>(parse_font_family(fam))));
    o.insert(o.end(), tmp.begin(), tmp.end());
    return true;
}

// ---------------------------------------------------------------------------------------------- table
const QHash<QString, PropDef>& chbp_table() {
    static const QHash<QString, PropDef> table = [] {
        QHash<QString, PropDef> t;
        auto add = [&t](const char* name, std::vector<Prop> lh, ParseFn fn, bool inh = false) {
            t.insert(QString::fromLatin1(name), PropDef{std::move(lh), std::move(fn), inh});
        };
        auto addIgnored = [&t](const char* name) { t.insert(QString::fromLatin1(name), PropDef{{}, nullptr, false}); };

        add("display", {Prop::Display},
            chbp_kw_fn(Prop::Display, {{"none", int(Display::None)}, {"block", int(Display::Block)},
                                       {"inline", int(Display::Inline)}, {"inline-block", int(Display::InlineBlock)},
                                       {"flex", int(Display::Flex)}, {"inline-flex", int(Display::InlineFlex)},
                                       {"grid", int(Display::Grid)}, {"inline-grid", int(Display::InlineGrid)},
                                       {"table", int(Display::Table)}, {"inline-table", int(Display::InlineTable)},
                                       {"table-row-group", int(Display::TableRowGroup)},
                                       {"table-header-group", int(Display::TableHeaderGroup)},
                                       {"table-footer-group", int(Display::TableFooterGroup)},
                                       {"table-row", int(Display::TableRow)}, {"table-cell", int(Display::TableCell)},
                                       {"table-column", int(Display::TableColumn)},
                                       {"table-column-group", int(Display::TableColumnGroup)},
                                       {"table-caption", int(Display::TableCaption)},
                                       {"list-item", int(Display::ListItem)}, {"flow-root", int(Display::FlowRoot)},
                                       {"contents", int(Display::Contents)}, {"-webkit-box", int(Display::Block)}}));
        add("position", {Prop::Position},
            chbp_kw_fn(Prop::Position, {{"static", int(Position::Static)}, {"relative", int(Position::Relative)},
                                        {"absolute", int(Position::Absolute)}, {"fixed", int(Position::Fixed)},
                                        {"sticky", int(Position::Sticky)}, {"-webkit-sticky", int(Position::Sticky)}}));
        add("top", {Prop::Top}, chbp_len_fn(Prop::Top, LAuto | LNeg));
        add("right", {Prop::Right}, chbp_len_fn(Prop::Right, LAuto | LNeg));
        add("bottom", {Prop::Bottom}, chbp_len_fn(Prop::Bottom, LAuto | LNeg));
        add("left", {Prop::Left}, chbp_len_fn(Prop::Left, LAuto | LNeg));
        add("inset", {Prop::Top, Prop::Right, Prop::Bottom, Prop::Left}, [](const QString& v, Out& o) {
            static const Prop P[4] = {Prop::Top, Prop::Right, Prop::Bottom, Prop::Left};
            return chbp_box4(v, [](const QString& s, Out& oo, Prop p) {
                SpecLen l;
                if (!chbp_parse_len(s, LAuto | LNeg, &l)) return false;
                oo.push_back(chbp_len(p, l));
                return true;
            }, P, o);
        });
        add("zIndex", {Prop::ZIndex}, [](const QString& v, Out& o) {
            if (v.trimmed().toLower() == QLatin1String("auto")) { o.push_back(chbp_kw(Prop::ZIndex, KwAuto)); return true; }
            bool ok = false;
            const int n = v.trimmed().toInt(&ok);
            if (!ok) return false;
            o.push_back(chbp_num(Prop::ZIndex, float(n)));
            return true;
        });
        add("float", {Prop::Float}, chbp_kw_fn(Prop::Float, {{"none", 0}, {"left", 1}, {"right", 1}}));
        add("cssFloat", {Prop::Float}, chbp_kw_fn(Prop::Float, {{"none", 0}, {"left", 1}, {"right", 1}}));

        // box model
        const Prop M[4] = {Prop::MarginTop, Prop::MarginRight, Prop::MarginBottom, Prop::MarginLeft};
        const Prop Pd[4] = {Prop::PaddingTop, Prop::PaddingRight, Prop::PaddingBottom, Prop::PaddingLeft};
        const char* mn[4] = {"marginTop", "marginRight", "marginBottom", "marginLeft"};
        const char* pn[4] = {"paddingTop", "paddingRight", "paddingBottom", "paddingLeft"};
        for (int i = 0; i < 4; ++i) {
            add(mn[i], {M[i]}, chbp_len_fn(M[i], LAuto | LNeg));
            add(pn[i], {Pd[i]}, chbp_len_fn(Pd[i], 0));
        }
        add("margin", {M[0], M[1], M[2], M[3]}, [](const QString& v, Out& o) {
            static const Prop P[4] = {Prop::MarginTop, Prop::MarginRight, Prop::MarginBottom, Prop::MarginLeft};
            return chbp_box4(v, [](const QString& s, Out& oo, Prop p) {
                SpecLen l;
                if (!chbp_parse_len(s, LAuto | LNeg, &l)) return false;
                oo.push_back(chbp_len(p, l));
                return true;
            }, P, o);
        });
        add("padding", {Pd[0], Pd[1], Pd[2], Pd[3]}, [](const QString& v, Out& o) {
            static const Prop P[4] = {Prop::PaddingTop, Prop::PaddingRight, Prop::PaddingBottom, Prop::PaddingLeft};
            return chbp_box4(v, [](const QString& s, Out& oo, Prop p) {
                SpecLen l;
                if (!chbp_parse_len(s, 0, &l)) return false;
                oo.push_back(chbp_len(p, l));
                return true;
            }, P, o);
        });
        add("marginInline", {M[1], M[3]}, [](const QString& v, Out& o) {
            const QStringList t = css_split_ws(v);
            if (t.isEmpty() || t.size() > 2) return false;
            SpecLen a, b;
            if (!chbp_parse_len(t[0], LAuto | LNeg, &a) || !chbp_parse_len(t.value(1, t[0]), LAuto | LNeg, &b)) return false;
            o.push_back(chbp_len(Prop::MarginLeft, a));
            o.push_back(chbp_len(Prop::MarginRight, b));
            return true;
        });
        add("marginBlock", {M[0], M[2]}, [](const QString& v, Out& o) {
            const QStringList t = css_split_ws(v);
            if (t.isEmpty() || t.size() > 2) return false;
            SpecLen a, b;
            if (!chbp_parse_len(t[0], LAuto | LNeg, &a) || !chbp_parse_len(t.value(1, t[0]), LAuto | LNeg, &b)) return false;
            o.push_back(chbp_len(Prop::MarginTop, a));
            o.push_back(chbp_len(Prop::MarginBottom, b));
            return true;
        });
        add("paddingInline", {Pd[1], Pd[3]}, [](const QString& v, Out& o) {
            const QStringList t = css_split_ws(v);
            if (t.isEmpty() || t.size() > 2) return false;
            SpecLen a, b;
            if (!chbp_parse_len(t[0], 0, &a) || !chbp_parse_len(t.value(1, t[0]), 0, &b)) return false;
            o.push_back(chbp_len(Prop::PaddingLeft, a));
            o.push_back(chbp_len(Prop::PaddingRight, b));
            return true;
        });
        add("paddingBlock", {Pd[0], Pd[2]}, [](const QString& v, Out& o) {
            const QStringList t = css_split_ws(v);
            if (t.isEmpty() || t.size() > 2) return false;
            SpecLen a, b;
            if (!chbp_parse_len(t[0], 0, &a) || !chbp_parse_len(t.value(1, t[0]), 0, &b)) return false;
            o.push_back(chbp_len(Prop::PaddingTop, a));
            o.push_back(chbp_len(Prop::PaddingBottom, b));
            return true;
        });

        // borders
        const Prop BW[4] = {Prop::BorderTopWidth, Prop::BorderRightWidth, Prop::BorderBottomWidth, Prop::BorderLeftWidth};
        const Prop BS[4] = {Prop::BorderTopStyle, Prop::BorderRightStyle, Prop::BorderBottomStyle, Prop::BorderLeftStyle};
        const Prop BC[4] = {Prop::BorderTopColor, Prop::BorderRightColor, Prop::BorderBottomColor, Prop::BorderLeftColor};
        const char* sideName[4] = {"Top", "Right", "Bottom", "Left"};
        for (int i = 0; i < 4; ++i) {
            const Prop w = BW[i], s = BS[i], c = BC[i];
            const QByteArray base = QByteArray("border") + sideName[i];
            t.insert(QString::fromLatin1(base + "Width"), PropDef{{w}, [w](const QString& v, Out& o) {
                SpecLen l;
                if (!chbp_bwidth(v, &l)) return false;
                o.push_back(chbp_len(w, l));
                return true;
            }, false});
            t.insert(QString::fromLatin1(base + "Style"), PropDef{{s}, chbp_kw_fn(s, kBStyle), false});
            t.insert(QString::fromLatin1(base + "Color"), PropDef{{c}, chbp_color_fn(c), false});
            const int side = i;
            t.insert(QString::fromLatin1(base), PropDef{{w, s, c}, [side](const QString& v, Out& o) {
                SpecLen bw;
                int st = 0;
                QColor col;
                bool cur = false;
                if (!chbp_border_parts(v, &bw, &st, &col, &cur)) return false;
                chbp_border_side(o, side, bw, st, col, cur);
                return true;
            }, false});
        }
        add("border", {BW[0], BW[1], BW[2], BW[3], BS[0], BS[1], BS[2], BS[3], BC[0], BC[1], BC[2], BC[3]},
            [](const QString& v, Out& o) {
                SpecLen bw;
                int st = 0;
                QColor col;
                bool cur = false;
                if (!chbp_border_parts(v, &bw, &st, &col, &cur)) return false;
                for (int s = 0; s < 4; ++s) chbp_border_side(o, s, bw, st, col, cur);
                return true;
            });
        add("borderWidth", {BW[0], BW[1], BW[2], BW[3]}, [](const QString& v, Out& o) {
            static const Prop P[4] = {Prop::BorderTopWidth, Prop::BorderRightWidth, Prop::BorderBottomWidth, Prop::BorderLeftWidth};
            return chbp_box4(v, [](const QString& s, Out& oo, Prop p) {
                SpecLen l;
                if (!chbp_bwidth(s, &l)) return false;
                oo.push_back(chbp_len(p, l));
                return true;
            }, P, o);
        });
        add("borderStyle", {BS[0], BS[1], BS[2], BS[3]}, [](const QString& v, Out& o) {
            static const Prop P[4] = {Prop::BorderTopStyle, Prop::BorderRightStyle, Prop::BorderBottomStyle, Prop::BorderLeftStyle};
            return chbp_box4(v, [](const QString& s, Out& oo, Prop p) {
                const int st = chbp_lookup(s.trimmed().toLower(), kBStyle);
                if (st < 0) return false;
                oo.push_back(chbp_kw(p, st));
                return true;
            }, P, o);
        });
        add("borderColor", {BC[0], BC[1], BC[2], BC[3]}, [](const QString& v, Out& o) {
            static const Prop P[4] = {Prop::BorderTopColor, Prop::BorderRightColor, Prop::BorderBottomColor, Prop::BorderLeftColor};
            return chbp_box4(v, [](const QString& s, Out& oo, Prop p) {
                QColor c;
                bool cur = false;
                if (!parse_css_color(s, &c, &cur)) return false;
                oo.push_back(chbp_color(p, c, cur));
                return true;
            }, P, o);
        });
        const Prop R[4] = {Prop::RadiusTL, Prop::RadiusTR, Prop::RadiusBR, Prop::RadiusBL};
        const char* rn[4] = {"borderTopLeftRadius", "borderTopRightRadius", "borderBottomRightRadius", "borderBottomLeftRadius"};
        for (int i = 0; i < 4; ++i) {
            const Prop rp = R[i];
            add(rn[i], {rp}, [rp](const QString& v, Out& o) {
                const QStringList tt = css_split_ws(v); // "a b" elliptical → first value
                if (tt.isEmpty() || tt.size() > 2) return false;
                SpecLen l;
                if (!chbp_parse_len(tt[0], 0, &l)) return false;
                o.push_back(chbp_len(rp, l));
                return true;
            });
        }
        add("borderRadius", {R[0], R[1], R[2], R[3]}, [](const QString& v, Out& o) {
            static const Prop P[4] = {Prop::RadiusTL, Prop::RadiusTR, Prop::RadiusBR, Prop::RadiusBL};
            const QString first = v.split(QLatin1Char('/')).first();
            return chbp_box4(first, [](const QString& s, Out& oo, Prop p) {
                SpecLen l;
                if (!chbp_parse_len(s, 0, &l)) return false;
                oo.push_back(chbp_len(p, l));
                return true;
            }, P, o);
        });

        // sizing
        add("width", {Prop::Width}, chbp_len_fn(Prop::Width, LAuto | LSizing));
        add("height", {Prop::Height}, chbp_len_fn(Prop::Height, LAuto | LSizing));
        add("minWidth", {Prop::MinWidth}, chbp_len_fn(Prop::MinWidth, LAuto | LSizing));
        add("minHeight", {Prop::MinHeight}, chbp_len_fn(Prop::MinHeight, LAuto | LSizing));
        add("maxWidth", {Prop::MaxWidth}, chbp_len_fn(Prop::MaxWidth, LNone | LSizing));
        add("maxHeight", {Prop::MaxHeight}, chbp_len_fn(Prop::MaxHeight, LNone | LSizing));
        add("boxSizing", {Prop::BoxSizing}, chbp_kw_fn(Prop::BoxSizing, {{"content-box", int(BoxSizing::ContentBox)},
                                                                        {"border-box", int(BoxSizing::BorderBox)}}));

        // paint
        add("backgroundColor", {Prop::BackgroundColor}, chbp_color_fn(Prop::BackgroundColor));
        add("backgroundImage", {Prop::BackgroundImage}, [](const QString& v, Out& o) {
            auto g = parse_css_gradients(v);
            if (!g) {
                if (v.trimmed().startsWith(QLatin1String("url("))) { // images unsupported → none
                    o.push_back(chbp_ext(Prop::BackgroundImage, std::make_shared<std::vector<Gradient>>()));
                    return true;
                }
                return false;
            }
            o.push_back(chbp_ext(Prop::BackgroundImage, g));
            return true;
        });
        add("background", {Prop::BackgroundColor, Prop::BackgroundImage}, chbp_background);
        add("boxShadow", {Prop::BoxShadow}, [](const QString& v, Out& o) {
            auto s = parse_css_shadows(v);
            if (!s) return false;
            o.push_back(chbp_ext(Prop::BoxShadow, s));
            return true;
        });
        add("opacity", {Prop::Opacity}, [](const QString& v, Out& o) {
            QString s = v.trimmed();
            float n = 0;
            if (s.endsWith(QLatin1Char('%'))) {
                if (!chbp_float(s.chopped(1), &n)) return false;
                n /= 100;
            } else if (!chbp_float(s, &n)) return false;
            o.push_back(chbp_num(Prop::Opacity, std::clamp(n, 0.0f, 1.0f)));
            return true;
        });
        const std::initializer_list<std::pair<const char*, int>> kOv = {
            {"visible", int(Overflow::Visible)}, {"hidden", int(Overflow::Hidden)}, {"clip", int(Overflow::Clip)},
            {"auto", int(Overflow::Auto)}, {"scroll", int(Overflow::Scroll)}, {"overlay", int(Overflow::Auto)}};
        add("overflowX", {Prop::OverflowX}, chbp_kw_fn(Prop::OverflowX, kOv));
        add("overflowY", {Prop::OverflowY}, chbp_kw_fn(Prop::OverflowY, kOv));
        {
            auto one = chbp_kw_fn(Prop::OverflowX, kOv);
            add("overflow", {Prop::OverflowX, Prop::OverflowY}, [one](const QString& v, Out& o) {
                const QStringList t = css_split_ws(v);
                if (t.isEmpty() || t.size() > 2) return false;
                Out a;
                if (!one(t[0], a)) return false;
                Out b;
                if (!one(t.value(1, t[0]), b)) return false;
                a[0].prop = Prop::OverflowX;
                b[0].prop = Prop::OverflowY;
                o.push_back(a[0]);
                o.push_back(b[0]);
                return true;
            });
        }
        add("textOverflow", {Prop::TextOverflow}, chbp_kw_fn(Prop::TextOverflow, {{"clip", KwClip}, {"ellipsis", KwEllipsis}}));

        // text
        add("color", {Prop::Color}, chbp_color_fn(Prop::Color), true);
        add("fontFamily", {Prop::FontFamily}, [](const QString& v, Out& o) {
            const QStringList l = parse_font_family(v);
            if (l.isEmpty()) return false;
            o.push_back(chbp_ext(Prop::FontFamily, std::make_shared<const QStringList>(l)));
            return true;
        }, true);
        add("fontSize", {Prop::FontSize}, chbp_font_size, true);
        add("fontWeight", {Prop::FontWeight}, chbp_font_weight, true);
        add("fontStyle", {Prop::FontStyle}, chbp_kw_fn(Prop::FontStyle, {{"normal", int(FontStyle::Normal)},
                                                                        {"italic", int(FontStyle::Italic)},
                                                                        {"oblique", int(FontStyle::Oblique)}}), true);
        add("font", {Prop::FontStyle, Prop::FontWeight, Prop::LineHeight, Prop::FontSize, Prop::FontFamily},
            chbp_font_shorthand, true);
        add("letterSpacing", {Prop::LetterSpacing}, [](const QString& v, Out& o) { return chbp_spacing(Prop::LetterSpacing, v, o); }, true);
        add("wordSpacing", {Prop::WordSpacing}, [](const QString& v, Out& o) { return chbp_spacing(Prop::WordSpacing, v, o); }, true);
        add("lineHeight", {Prop::LineHeight}, chbp_line_height, true);
        add("textAlign", {Prop::TextAlign},
            chbp_kw_fn(Prop::TextAlign, {{"start", int(TextAlign::Start)}, {"left", int(TextAlign::Left)},
                                         {"right", int(TextAlign::Right)}, {"center", int(TextAlign::Center)},
                                         {"justify", int(TextAlign::Justify)}, {"end", int(TextAlign::End)},
                                         {"-webkit-center", int(TextAlign::WebkitCenter)},
                                         {"match-parent", int(TextAlign::Start)}}), true);
        add("textTransform", {Prop::TextTransform},
            chbp_kw_fn(Prop::TextTransform, {{"none", int(TextTransform::None)}, {"uppercase", int(TextTransform::Uppercase)},
                                             {"lowercase", int(TextTransform::Lowercase)},
                                             {"capitalize", int(TextTransform::Capitalize)}}), true);
        add("textDecoration", {Prop::TextDecorationLine, Prop::TextDecorationStyle, Prop::TextDecorationColor}, chbp_text_deco);
        add("textDecorationLine", {Prop::TextDecorationLine}, [](const QString& v, Out& o) {
            Out tmp;
            if (!chbp_text_deco(v, tmp)) return false;
            o.push_back(tmp[0]);
            return true;
        });
        add("textDecorationColor", {Prop::TextDecorationColor}, chbp_color_fn(Prop::TextDecorationColor));
        add("textDecorationStyle", {Prop::TextDecorationStyle},
            chbp_kw_fn(Prop::TextDecorationStyle, {{"solid", 0}, {"double", 1}, {"dotted", 2}, {"dashed", 3}, {"wavy", 4}}));
        add("whiteSpace", {Prop::WhiteSpace},
            chbp_kw_fn(Prop::WhiteSpace, {{"normal", int(WhiteSpace::Normal)}, {"nowrap", int(WhiteSpace::NoWrap)},
                                          {"pre", int(WhiteSpace::Pre)}, {"pre-wrap", int(WhiteSpace::PreWrap)},
                                          {"pre-line", int(WhiteSpace::PreLine)},
                                          {"break-spaces", int(WhiteSpace::BreakSpaces)}}), true);
        add("wordBreak", {Prop::WordBreak},
            chbp_kw_fn(Prop::WordBreak, {{"normal", int(WordBreak::Normal)}, {"break-all", int(WordBreak::BreakAll)},
                                         {"keep-all", int(WordBreak::KeepAll)}, {"break-word", int(WordBreak::BreakWord)}}), true);
        const std::initializer_list<std::pair<const char*, int>> kOw = {
            {"normal", int(OverflowWrap::Normal)}, {"break-word", int(OverflowWrap::BreakWord)},
            {"anywhere", int(OverflowWrap::Anywhere)}};
        add("overflowWrap", {Prop::OverflowWrap}, chbp_kw_fn(Prop::OverflowWrap, kOw), true);
        add("wordWrap", {Prop::OverflowWrap}, chbp_kw_fn(Prop::OverflowWrap, kOw), true);
        add("verticalAlign", {Prop::VerticalAlign}, [](const QString& v, Out& o) {
            const QString s = v.trimmed().toLower();
            const int kw = chbp_lookup(s, {{"baseline", int(VAlign::Baseline)}, {"middle", int(VAlign::Middle)},
                                           {"top", int(VAlign::Top)}, {"bottom", int(VAlign::Bottom)},
                                           {"text-top", int(VAlign::TextTop)}, {"text-bottom", int(VAlign::TextBottom)},
                                           {"sub", int(VAlign::Sub)}, {"super", int(VAlign::Super)}});
            if (kw >= 0) { o.push_back(chbp_kw(Prop::VerticalAlign, kw)); return true; }
            SpecLen l;
            if (!chbp_parse_len(s, LNeg, &l)) return false;
            o.push_back(chbp_len(Prop::VerticalAlign, l));
            return true;
        });
        add("textIndent", {Prop::TextIndent}, chbp_len_fn(Prop::TextIndent, LNeg), true);
        const std::initializer_list<std::pair<const char*, int>> kLs = {
            {"disc", int(ListStyle::Disc)}, {"circle", int(ListStyle::Circle)}, {"square", int(ListStyle::Square)},
            {"decimal", int(ListStyle::Decimal)}, {"decimal-leading-zero", int(ListStyle::DecimalLeadingZero)},
            {"lower-alpha", int(ListStyle::LowerAlpha)}, {"lower-latin", int(ListStyle::LowerAlpha)},
            {"upper-alpha", int(ListStyle::UpperAlpha)}, {"upper-latin", int(ListStyle::UpperAlpha)},
            {"lower-roman", int(ListStyle::LowerRoman)}, {"upper-roman", int(ListStyle::UpperRoman)},
            {"none", int(ListStyle::None)}};
        add("listStyleType", {Prop::ListStyleType}, chbp_kw_fn(Prop::ListStyleType, kLs), true);
        add("listStylePosition", {Prop::ListStylePosition}, chbp_kw_fn(Prop::ListStylePosition, {{"outside", 0}, {"inside", 1}}), true);
        {
            auto typeFn = chbp_kw_fn(Prop::ListStyleType, kLs);
            add("listStyle", {Prop::ListStyleType, Prop::ListStylePosition}, [typeFn](const QString& v, Out& o) {
                int type = int(ListStyle::Disc), pos = 0;
                bool sawNone = false;
                for (const QString& tk : css_split_ws(v.toLower())) {
                    if (tk == QLatin1String("inside")) { pos = 1; continue; }
                    if (tk == QLatin1String("outside")) { pos = 0; continue; }
                    if (tk == QLatin1String("none")) { sawNone = true; continue; }
                    Out tmp;
                    if (!typeFn(tk, tmp)) {
                        if (tk.startsWith(QLatin1String("url("))) continue;
                        return false;
                    }
                    type = tmp[0].v.kw;
                }
                if (sawNone) type = int(ListStyle::None);
                o.push_back(chbp_kw(Prop::ListStyleType, type));
                o.push_back(chbp_kw(Prop::ListStylePosition, pos));
                return true;
            }, true);
        }
        add("visibility", {Prop::Visibility},
            chbp_kw_fn(Prop::Visibility, {{"visible", int(Visibility::Visible)}, {"hidden", int(Visibility::Hidden)},
                                          {"collapse", int(Visibility::Collapse)}}), true);
        // backdrop-filter: only "is there a blur" matters — the painter lays the canvas colour under the box's own
        // (semi-transparent) background, so content scrolled beneath a blurred sticky bar no longer shows through.
        for (const char* n : {"backdropFilter", "WebkitBackdropFilter"}) {
            add(n, {Prop::BackdropFilter}, [](const QString& v, Out& o) {
                static const QRegularExpression re(QStringLiteral("blur\\(\\s*([0-9.]+)"));
                const auto m = re.match(v);
                o.push_back(chbp_num(Prop::BackdropFilter, m.hasMatch() && m.captured(1).toFloat() > 0 ? 1.f : 0.f));
                return true;
            });
        }
        add("cursor", {Prop::Cursor}, [](const QString& v, Out& o) {
            o.push_back(chbp_kw(Prop::Cursor, v.trimmed().toLower() == QLatin1String("pointer") ? KwPointer : KwOtherCursor));
            return true;
        }, true);

        // flex / grid / alignment
        add("flexDirection", {Prop::FlexDirection},
            chbp_kw_fn(Prop::FlexDirection, {{"row", int(FlexDir::Row)}, {"row-reverse", int(FlexDir::RowReverse)},
                                             {"column", int(FlexDir::Column)}, {"column-reverse", int(FlexDir::ColumnReverse)}}));
        add("flexWrap", {Prop::FlexWrap},
            chbp_kw_fn(Prop::FlexWrap, {{"nowrap", int(FlexWrap::NoWrap)}, {"wrap", int(FlexWrap::Wrap)},
                                        {"wrap-reverse", int(FlexWrap::WrapReverse)}}));
        {
            auto dirFn = chbp_kw_fn(Prop::FlexDirection, {{"row", int(FlexDir::Row)}, {"row-reverse", int(FlexDir::RowReverse)},
                                                          {"column", int(FlexDir::Column)}, {"column-reverse", int(FlexDir::ColumnReverse)}});
            auto wrapFn = chbp_kw_fn(Prop::FlexWrap, {{"nowrap", int(FlexWrap::NoWrap)}, {"wrap", int(FlexWrap::Wrap)},
                                                      {"wrap-reverse", int(FlexWrap::WrapReverse)}});
            add("flexFlow", {Prop::FlexDirection, Prop::FlexWrap}, [dirFn, wrapFn](const QString& v, Out& o) {
                Out d{chbp_kw(Prop::FlexDirection, int(FlexDir::Row))}, w{chbp_kw(Prop::FlexWrap, int(FlexWrap::NoWrap))};
                for (const QString& tk : css_split_ws(v)) {
                    Out tmp;
                    if (dirFn(tk, tmp)) d = tmp;
                    else if (wrapFn(tk, tmp)) w = tmp;
                    else return false;
                }
                o.push_back(d[0]);
                o.push_back(w[0]);
                return true;
            });
        }
        add("justifyContent", {Prop::JustifyContent}, chbp_kw_fn(Prop::JustifyContent, kAlign));
        add("alignItems", {Prop::AlignItems}, chbp_kw_fn(Prop::AlignItems, kAlign));
        add("alignSelf", {Prop::AlignSelf}, chbp_kw_fn(Prop::AlignSelf, kAlign));
        add("alignContent", {Prop::AlignContent}, chbp_kw_fn(Prop::AlignContent, kAlign));
        add("justifyItems", {Prop::JustifyItems}, chbp_kw_fn(Prop::JustifyItems, kAlign));
        add("justifySelf", {Prop::JustifySelf}, chbp_kw_fn(Prop::JustifySelf, kAlign));
        {
            auto aFn = chbp_kw_fn(Prop::AlignItems, kAlign);
            auto place = [aFn](Prop a, Prop j) {
                return [aFn, a, j](const QString& v, Out& o) {
                    const QStringList t = css_split_ws(v);
                    if (t.isEmpty() || t.size() > 2) return false;
                    Out x, y;
                    if (!aFn(t[0], x) || !aFn(t.value(1, t[0]), y)) return false;
                    x[0].prop = a;
                    y[0].prop = j;
                    o.push_back(x[0]);
                    o.push_back(y[0]);
                    return true;
                };
            };
            add("placeItems", {Prop::AlignItems, Prop::JustifyItems}, place(Prop::AlignItems, Prop::JustifyItems));
            add("placeContent", {Prop::AlignContent, Prop::JustifyContent}, place(Prop::AlignContent, Prop::JustifyContent));
            add("placeSelf", {Prop::AlignSelf, Prop::JustifySelf}, place(Prop::AlignSelf, Prop::JustifySelf));
        }
        add("flexGrow", {Prop::FlexGrow}, [](const QString& v, Out& o) {
            float n = 0;
            if (!chbp_float(v, &n) || n < 0) return false;
            o.push_back(chbp_num(Prop::FlexGrow, n));
            return true;
        });
        add("flexShrink", {Prop::FlexShrink}, [](const QString& v, Out& o) {
            float n = 0;
            if (!chbp_float(v, &n) || n < 0) return false;
            o.push_back(chbp_num(Prop::FlexShrink, n));
            return true;
        });
        add("flexBasis", {Prop::FlexBasis}, chbp_len_fn(Prop::FlexBasis, LAuto | LContent | LSizing));
        add("flex", {Prop::FlexGrow, Prop::FlexShrink, Prop::FlexBasis}, chbp_flex);
        add("order", {Prop::Order}, [](const QString& v, Out& o) {
            bool ok = false;
            const int n = v.trimmed().toInt(&ok);
            if (!ok) return false;
            o.push_back(chbp_num(Prop::Order, float(n)));
            return true;
        });
        add("rowGap", {Prop::RowGap}, chbp_len_fn(Prop::RowGap, LNormal));
        add("columnGap", {Prop::ColumnGap}, chbp_len_fn(Prop::ColumnGap, LNormal));
        add("gridRowGap", {Prop::RowGap}, chbp_len_fn(Prop::RowGap, LNormal));
        add("gridColumnGap", {Prop::ColumnGap}, chbp_len_fn(Prop::ColumnGap, LNormal));
        auto gapFn = [](const QString& v, Out& o) {
            const QStringList t = css_split_ws(v);
            if (t.isEmpty() || t.size() > 2) return false;
            SpecLen a, b;
            if (!chbp_parse_len(t[0], LNormal, &a) || !chbp_parse_len(t.value(1, t[0]), LNormal, &b)) return false;
            o.push_back(chbp_len(Prop::RowGap, a));
            o.push_back(chbp_len(Prop::ColumnGap, b));
            return true;
        };
        add("gap", {Prop::RowGap, Prop::ColumnGap}, gapFn);
        add("gridGap", {Prop::RowGap, Prop::ColumnGap}, gapFn);
        add("gridTemplateColumns", {Prop::GridTemplateColumns}, [](const QString& v, Out& o) {
            auto tl = parse_css_track_list(v);
            if (!tl) return false;
            o.push_back(chbp_ext(Prop::GridTemplateColumns, tl));
            return true;
        });
        add("gridTemplateRows", {Prop::GridTemplateRows}, [](const QString& v, Out& o) {
            auto tl = parse_css_track_list(v);
            if (!tl) return false;
            o.push_back(chbp_ext(Prop::GridTemplateRows, tl));
            return true;
        });
        add("gridAutoRows", {Prop::GridAutoRows}, [](const QString& v, Out& o) {
            auto ts = std::make_shared<TrackSize>();
            if (!parse_css_track_size(v, ts.get())) return false;
            o.push_back(chbp_ext(Prop::GridAutoRows, ts));
            return true;
        });
        add("gridAutoColumns", {Prop::GridAutoColumns}, [](const QString& v, Out& o) {
            auto ts = std::make_shared<TrackSize>();
            if (!parse_css_track_size(v, ts.get())) return false;
            o.push_back(chbp_ext(Prop::GridAutoColumns, ts));
            return true;
        });
        add("gridAutoFlow", {Prop::GridAutoFlow},
            chbp_kw_fn(Prop::GridAutoFlow, {{"row", int(GridFlow::Row)}, {"column", int(GridFlow::Column)},
                                            {"row dense", int(GridFlow::RowDense)}, {"dense", int(GridFlow::RowDense)},
                                            {"column dense", int(GridFlow::ColumnDense)}}));
        add("gridColumnStart", {Prop::GridColumnStart}, [](const QString& v, Out& o) { return chbp_grid_line(Prop::GridColumnStart, v, o); });
        add("gridColumnEnd", {Prop::GridColumnEnd}, [](const QString& v, Out& o) { return chbp_grid_line(Prop::GridColumnEnd, v, o); });
        add("gridRowStart", {Prop::GridRowStart}, [](const QString& v, Out& o) { return chbp_grid_line(Prop::GridRowStart, v, o); });
        add("gridRowEnd", {Prop::GridRowEnd}, [](const QString& v, Out& o) { return chbp_grid_line(Prop::GridRowEnd, v, o); });
        add("gridColumn", {Prop::GridColumnStart, Prop::GridColumnEnd},
            [](const QString& v, Out& o) { return chbp_grid_pair(Prop::GridColumnStart, Prop::GridColumnEnd, v, o); });
        add("gridRow", {Prop::GridRowStart, Prop::GridRowEnd},
            [](const QString& v, Out& o) { return chbp_grid_pair(Prop::GridRowStart, Prop::GridRowEnd, v, o); });

        // tables / transforms
        add("borderCollapse", {Prop::BorderCollapse},
            chbp_kw_fn(Prop::BorderCollapse, {{"separate", int(BorderCollapse::Separate)}, {"collapse", int(BorderCollapse::Collapse)}}), true);
        add("borderSpacing", {Prop::BorderSpacing}, [](const QString& v, Out& o) {
            const QStringList t = css_split_ws(v);
            if (t.isEmpty() || t.size() > 2) return false;
            SpecLen a, b;
            if (!chbp_parse_len(t[0], 0, &a) || !chbp_parse_len(t.value(1, t[0]), 0, &b) || a.pct != 0 || b.pct != 0) return false;
            auto pr = std::make_shared<std::pair<SpecLen, SpecLen>>(a, b);
            o.push_back(chbp_ext(Prop::BorderSpacing, pr));
            return true;
        }, true);
        add("tableLayout", {Prop::TableLayout}, chbp_kw_fn(Prop::TableLayout, {{"auto", int(TableLayout::Auto)}, {"fixed", int(TableLayout::Fixed)}}));
        add("transform", {Prop::Transform}, [](const QString& v, Out& o) {
            auto tr = std::make_shared<Transform2D>();
            if (!parse_css_transform(v, tr.get())) return false;
            o.push_back(chbp_ext(Prop::Transform, tr));
            return true;
        });

        // SVG presentation properties used via CSS (stored raw, inherited)
        const struct { const char* n; Prop p; } svgp[] = {
            {"fill", Prop::SvgFill}, {"stroke", Prop::SvgStroke}, {"strokeWidth", Prop::SvgStrokeWidth},
            {"strokeDasharray", Prop::SvgStrokeDasharray}, {"strokeOpacity", Prop::SvgStrokeOpacity},
            {"fillOpacity", Prop::SvgFillOpacity}, {"strokeLinecap", Prop::SvgStrokeLinecap},
            {"strokeLinejoin", Prop::SvgStrokeLinejoin}, {"textAnchor", Prop::SvgTextAnchor},
            {"dominantBaseline", Prop::SvgDominantBaseline}};
        for (const auto& e : svgp) {
            const Prop p = e.p;
            add(e.n, {p}, [p](const QString& v, Out& o) {
                o.push_back(chbp_str(p, v.trimmed()));
                return true;
            }, true);
        }

        // Known CSS properties with no effect in this engine (accepted silently).
        for (const char* n : {"transition", "transitionProperty", "transitionDuration", "transitionTimingFunction",
                              "userSelect", "WebkitUserSelect", "pointerEvents",
                              "outline", "outlineColor", "outlineStyle", "outlineWidth", "outlineOffset",
                              "boxDecorationBreak", "WebkitBoxDecorationBreak", "fontVariantNumeric", "fontFeatureSettings",
                              "fontVariant", "WebkitFontSmoothing", "MozOsxFontSmoothing", "textRendering", "objectFit",
                              "resize", "scrollbarWidth", "willChange", "animation", "content", "textShadow", "filter",
                              "mixBlendMode", "hyphens", "tabSize", "textWrap", "isolation", "contain", "clipPath",
                              "WebkitTextFillColor", "appearance", "WebkitAppearance", "fontStretch", "direction",
                              "unicodeBidi", "writingMode", "clear", "scrollBehavior", "overscrollBehavior",
                              "WebkitLineClamp", "WebkitBoxOrient", "lineClamp", "gridArea", "gridTemplateAreas",
                              "backgroundSize", "backgroundPosition", "backgroundRepeat", "backgroundClip",
                              "backgroundOrigin", "backgroundAttachment", "fontKerning", "textUnderlineOffset",
                              "textDecorationThickness", "caretColor", "accentColor", "colorScheme", "aspectRatio",
                              "columnCount", "columns", "breakInside", "pageBreakInside", "counterReset",
                              "counterIncrement", "quotes", "verticalAlignLast", "textAlignLast", "imageRendering",
                              "shapeRendering", "transformOrigin", "zoom"})
            addIgnored(n);
        return t;
    }();
    return table;
}

QString chbp_kebab_to_camel(const QString& k) {
    if (!k.contains(QLatin1Char('-'))) return k;
    QString out;
    bool up = false;
    for (int i = 0; i < k.size(); ++i) {
        const QChar c = k[i];
        if (c == u'-') {
            up = i > 0;
            continue;
        }
        out += up ? c.toUpper() : c;
        up = false;
    }
    if (out.startsWith(QLatin1String("webkit"))) out[0] = u'W';
    return out;
}

/// React dangerousStyleValue → CSS text; returns false for "remove" values.
bool chbp_react_value(const QString& key, const JVal& v, QString* out) {
    static const QSet<QString> unitless = [] {
        QSet<QString> s;
        for (const char* n : {"animationIterationCount", "aspectRatio", "borderImageOutset", "borderImageSlice",
                              "borderImageWidth", "boxFlex", "boxFlexGroup", "boxOrdinalGroup", "columnCount", "columns",
                              "flex", "flexGrow", "flexPositive", "flexShrink", "flexNegative", "flexOrder", "gridArea",
                              "gridRow", "gridRowEnd", "gridRowSpan", "gridRowStart", "gridColumn", "gridColumnEnd",
                              "gridColumnSpan", "gridColumnStart", "fontWeight", "lineClamp", "lineHeight", "opacity",
                              "order", "orphans", "scale", "tabSize", "widows", "zIndex", "zoom", "fillOpacity",
                              "floodOpacity", "stopOpacity", "strokeDasharray", "strokeDashoffset", "strokeMiterlimit",
                              "strokeOpacity", "strokeWidth"})
            s.insert(QString::fromLatin1(n));
        return s;
    }();
    switch (v.type) {
    case JVal::Null:
    case JVal::Bool: return false;
    case JVal::Num: {
        QString k = key;
        static const QRegularExpression prefix(QStringLiteral("^(Webkit|Moz|ms|O)([A-Z].*)$"));
        const auto m = prefix.match(key);
        if (m.hasMatch()) k = m.captured(2).left(1).toLower() + m.captured(2).mid(1);
        *out = js_number_string(v.n);
        if (v.n != 0 && !unitless.contains(k)) *out += QStringLiteral("px");
        return true;
    }
    case JVal::Str:
        *out = v.s.trimmed();
        return !out->isEmpty();
    default: return false; // arrays/objects: React would stringify; treat as removal (invalid)
    }
}

} // namespace

DeclListPtr parse_style_dict(const JVal& dict) {
    auto dl = std::make_shared<DeclList>();
    const auto& table = chbp_table();
    for (const auto& kv : dict.members()) {
        const QString key = chbp_kebab_to_camel(kv.first == QLatin1String("float") ? QStringLiteral("cssFloat") : kv.first);
        const auto it = table.find(key);
        QString css;
        const bool set = chbp_react_value(kv.first, kv.second, &css);
        dl->raw.emplace_back(kv.first, set ? css : QString());
        if (it == table.end()) {
            ++dl->unknown;
            continue;
        }
        const PropDef& def = it.value();
        if (!def.parse) continue; // known but ignored property
        if (!set) {
            for (Prop p : def.longhands) {
                Decl d;
                d.prop = p;
                d.remove = true;
                dl->decls.push_back(d);
            }
            continue;
        }
        const QString low = css.trimmed().toLower();
        if (low == QLatin1String("inherit") || low == QLatin1String("initial") || low == QLatin1String("unset") ||
            low == QLatin1String("revert")) {
            for (Prop p : def.longhands) {
                Decl d;
                d.prop = p;
                const bool inh = low == QLatin1String("inherit") || (low != QLatin1String("initial") && def.inherited);
                d.v.kind = inh ? SpecValue::Inherit : SpecValue::Initial;
                dl->decls.push_back(d);
            }
            continue;
        }
        Out tmp;
        if (def.parse(css, tmp)) dl->decls.insert(dl->decls.end(), tmp.begin(), tmp.end());
        // invalid → ignored (CSSOM keeps the previous value)
    }
    return dl;
}

// ---------------------------------------------------------------------------------------------- UA sheet

namespace {

DeclListPtr chbp_ua_from(std::initializer_list<std::pair<const char*, const char*>> kv) {
    JVal obj;
    obj.type = JVal::Obj;
    obj.obj = std::make_shared<JObj>();
    for (const auto& e : kv) {
        JVal v;
        v.type = JVal::Str;
        v.s = QString::fromUtf8(e.second);
        obj.obj->emplace_back(QString::fromLatin1(e.first), v);
    }
    return parse_style_dict(obj);
}

} // namespace

const DeclList& ua_decls(Tag tag, bool link, int listDepth) {
    static std::once_flag once;
    static QHash<int, DeclListPtr> m;
    static DeclListPtr linkList, empty, nested[2][2], trInTable; // nested: [ul/ol][depth 1 / ≥2]
    std::call_once(once, [] {
        auto set = [](Tag t, std::initializer_list<std::pair<const char*, const char*>> kv) { m.insert(int(t), chbp_ua_from(kv)); };
        const auto block = std::initializer_list<std::pair<const char*, const char*>>{{"display", "block"}};
        for (Tag t : {Tag::Div, Tag::Section, Tag::Header, Tag::Nav, Tag::Main, Tag::Footer, Tag::Article, Tag::Aside})
            set(t, block);
        // body: UA + the oracle page's <style> (author sheet, still below inline style)
        set(Tag::Body, {{"display", "block"}, {"margin", "0"}, {"background", "#0a0a0c"}, {"color", "#e8e6e0"},
                        {"fontFamily", "'Source Serif 4', Georgia, serif"}});
        set(Tag::H1, {{"display", "block"}, {"fontSize", "2em"}, {"marginTop", "0.67em"}, {"marginBottom", "0.67em"}, {"fontWeight", "bold"}});
        set(Tag::H2, {{"display", "block"}, {"fontSize", "1.5em"}, {"marginTop", "0.83em"}, {"marginBottom", "0.83em"}, {"fontWeight", "bold"}});
        set(Tag::H3, {{"display", "block"}, {"fontSize", "1.17em"}, {"marginTop", "1em"}, {"marginBottom", "1em"}, {"fontWeight", "bold"}});
        set(Tag::H4, {{"display", "block"}, {"marginTop", "1.33em"}, {"marginBottom", "1.33em"}, {"fontWeight", "bold"}});
        set(Tag::H5, {{"display", "block"}, {"fontSize", "0.83em"}, {"marginTop", "1.67em"}, {"marginBottom", "1.67em"}, {"fontWeight", "bold"}});
        set(Tag::H6, {{"display", "block"}, {"fontSize", "0.67em"}, {"marginTop", "2.33em"}, {"marginBottom", "2.33em"}, {"fontWeight", "bold"}});
        set(Tag::P, {{"display", "block"}, {"marginTop", "1em"}, {"marginBottom", "1em"}});
        set(Tag::Blockquote, {{"display", "block"}, {"margin", "1em 40px"}});
        set(Tag::Ul, {{"display", "block"}, {"listStyleType", "disc"}, {"marginTop", "1em"}, {"marginBottom", "1em"}, {"paddingLeft", "40px"}});
        set(Tag::Ol, {{"display", "block"}, {"listStyleType", "decimal"}, {"marginTop", "1em"}, {"marginBottom", "1em"}, {"paddingLeft", "40px"}});
        set(Tag::Li, {{"display", "list-item"}});
        set(Tag::Pre, {{"display", "block"}, {"fontFamily", "monospace"}, {"whiteSpace", "pre"}, {"marginTop", "1em"}, {"marginBottom", "1em"}});
        set(Tag::Code, {{"fontFamily", "monospace"}});
        set(Tag::Kbd, {{"fontFamily", "monospace"}});
        set(Tag::Strong, {{"fontWeight", "bolder"}});
        set(Tag::B, {{"fontWeight", "bolder"}});
        set(Tag::Em, {{"fontStyle", "italic"}});
        set(Tag::I, {{"fontStyle", "italic"}});
        set(Tag::U, {{"textDecoration", "underline"}});
        set(Tag::S, {{"textDecoration", "line-through"}});
        set(Tag::Small, {{"fontSize", "smaller"}});
        set(Tag::Sub, {{"verticalAlign", "sub"}, {"fontSize", "smaller"}});
        set(Tag::Sup, {{"verticalAlign", "super"}, {"fontSize", "smaller"}});
        set(Tag::Mark, {{"backgroundColor", "yellow"}, {"color", "black"}});
        set(Tag::Hr, {{"display", "block"}, {"overflow", "hidden"}, {"color", "gray"}, {"margin", "0.5em auto"},
                      {"borderStyle", "inset"}, {"borderWidth", "1px"}});
        set(Tag::Table, {{"display", "table"}, {"borderCollapse", "separate"}, {"borderSpacing", "2px"},
                         {"borderColor", "gray"}, {"boxSizing", "border-box"}, {"textIndent", "0"}});
        set(Tag::Caption, {{"display", "table-caption"}, {"textAlign", "-webkit-center"}});
        set(Tag::Thead, {{"display", "table-header-group"}, {"verticalAlign", "middle"}, {"borderColor", "inherit"}});
        set(Tag::Tbody, {{"display", "table-row-group"}, {"verticalAlign", "middle"}, {"borderColor", "inherit"}});
        set(Tag::Tfoot, {{"display", "table-footer-group"}, {"verticalAlign", "middle"}, {"borderColor", "inherit"}});
        set(Tag::Tr, {{"display", "table-row"}, {"verticalAlign", "inherit"}, {"borderColor", "inherit"}});
        set(Tag::Td, {{"display", "table-cell"}, {"verticalAlign", "inherit"}, {"padding", "1px"}});
        set(Tag::Th, {{"display", "table-cell"}, {"verticalAlign", "inherit"}, {"padding", "1px"}, {"fontWeight", "bold"},
                      {"textAlign", "-webkit-center"}});
        set(Tag::Col, {{"display", "table-column"}});
        set(Tag::Colgroup, {{"display", "table-column-group"}});
        // button/select: Chrome UA + oracle as_intended rule (font family/size/weight inherit)
        set(Tag::Button, {{"display", "inline-block"}, {"fontStyle", "normal"}, {"lineHeight", "normal"},
                          {"letterSpacing", "normal"}, {"wordSpacing", "normal"}, {"textTransform", "none"},
                          {"textIndent", "0"}, {"textAlign", "center"}, {"padding", "1px 6px"},
                          {"border", "2px outset buttonborder"}, {"backgroundColor", "buttonface"},
                          {"color", "buttontext"}, {"boxSizing", "border-box"}});
        set(Tag::Select, {{"display", "inline-block"}, {"fontStyle", "normal"}, {"lineHeight", "normal"},
                          {"letterSpacing", "normal"}, {"wordSpacing", "normal"}, {"textTransform", "none"},
                          {"textIndent", "0"}, {"textAlign", "start"}, {"border", "1px solid #767676"},
                          {"backgroundColor", "field"}, {"color", "fieldtext"}, {"boxSizing", "border-box"},
                          {"whiteSpace", "pre"}, {"borderRadius", "0"}});
        set(Tag::Option, {{"display", "block"}});
        set(Tag::Svg, {{"overflowX", "hidden"}, {"overflowY", "hidden"}});
        linkList = chbp_ua_from({{"color", "#0000ee"}, {"textDecoration", "underline"}, {"cursor", "pointer"}});
        empty = std::make_shared<DeclList>();
        // ul ul / ol ul → circle, three levels → square; any nested list: margin-block 0
        nested[0][0] = chbp_ua_from({{"display", "block"}, {"listStyleType", "circle"}, {"marginTop", "0"}, {"marginBottom", "0"}, {"paddingLeft", "40px"}});
        nested[0][1] = chbp_ua_from({{"display", "block"}, {"listStyleType", "square"}, {"marginTop", "0"}, {"marginBottom", "0"}, {"paddingLeft", "40px"}});
        nested[1][0] = chbp_ua_from({{"display", "block"}, {"listStyleType", "decimal"}, {"marginTop", "0"}, {"marginBottom", "0"}, {"paddingLeft", "40px"}});
        nested[1][1] = nested[1][0];
        // Chrome html.css `table > tr { vertical-align: middle }` (rows created without a section element)
        trInTable = chbp_ua_from({{"display", "table-row"}, {"verticalAlign", "middle"}, {"borderColor", "inherit"}});
    });
    if (tag == Tag::A && link) return *linkList;
    if (listDepth > 0 && (tag == Tag::Ul || tag == Tag::Ol)) return *nested[tag == Tag::Ol ? 1 : 0][listDepth > 1 ? 1 : 0];
    if (listDepth > 0 && tag == Tag::Tr) return *trInTable;
    const auto it = m.constFind(int(tag));
    return it == m.constEnd() ? *empty : *it.value();
}

} // namespace fincept::screens::chb
