// ChbSvgParse.cpp — SVG attribute grammar for the chaebol_map engine: numbers, lengths, `transform`, viewBox +
// preserveAspectRatio, and the inherited presentation style (fill/stroke/… + font) with Chrome's precedence
// (own CSS declaration > presentation attribute > inherited; invalid attribute values are ignored).
#include "screens/chaebol_map/ChbSvg_p.h"

#include <algorithm>
#include <cmath>

namespace fincept::screens::chb::svg {

namespace {

bool chbg_wsp(QChar c) { return c == u' ' || c == u'\t' || c == u'\n' || c == u'\r' || c == u'\f'; }

void chbg_skip_wsp(QStringView s, int* i) {
    while (*i < s.size() && chbg_wsp(s[*i])) ++*i;
}

/// White space and at most one comma.
void chbg_skip_comma_wsp(QStringView s, int* i) {
    chbg_skip_wsp(s, i);
    if (*i < s.size() && s[*i] == u',') {
        ++*i;
        chbg_skip_wsp(s, i);
    }
}

bool chbg_is(QStringView v, const char* kw) { return v.compare(QLatin1String(kw), Qt::CaseInsensitive) == 0; }

/// Property present among the element's own author declarations (last one wins, CSSOM removal unsets).
bool chbg_own_decl(const RNode* r, Prop p) {
    bool set = false;
    for (const DeclList* l : r->decls)
        for (const Decl& d : l->decls)
            if (d.prop == p) set = !d.remove;
    return set;
}

/// Number or percentage in [0, 1] (opacity-like values).
bool chbg_alpha(QStringView v, float* out) {
    v = v.trimmed();
    float f = 0;
    if (v.endsWith(u'%')) {
        if (!parse_number(v.chopped(1), &f)) return false;
        f /= 100.0f;
    } else if (!parse_number(v, &f)) {
        return false;
    }
    *out = std::clamp(f, 0.0f, 1.0f);
    return true;
}

bool chbg_paint(QStringView v, PaintRef* out) {
    v = v.trimmed();
    if (v.isEmpty()) return false;
    PaintRef r;
    if (chbg_is(v, "none")) {
        r.kind = PaintRef::None;
    } else if (v.startsWith(QLatin1String("url("), Qt::CaseInsensitive)) {
        const int close = int(v.indexOf(u')'));
        if (close < 0) return false;
        QStringView in = v.mid(4, close - 4).trimmed();
        if (in.size() >= 2 && (in.front() == u'"' || in.front() == u'\'') && in.back() == in.front())
            in = in.mid(1, in.size() - 2).trimmed();
        if (!in.startsWith(u'#')) return false;
        r.kind = PaintRef::Url;
        r.id = in.mid(1).toString();
        const QStringView fb = v.mid(close + 1).trimmed();
        if (!fb.isEmpty()) {
            PaintRef f;
            if (!chbg_paint(fb, &f) || f.kind == PaintRef::Url) return false;
            r.fbKind = f.kind;
            r.fb = f.color;
        }
    } else {
        bool cur = false;
        QColor c;
        if (!parse_css_color(v, &c, &cur)) return false;
        r.kind = cur ? PaintRef::Current : PaintRef::Color;
        r.color = c;
    }
    *out = r;
    return true;
}

bool chbg_dash(QStringView v, const LenCtx& c, std::vector<float>* out) {
    v = v.trimmed();
    if (v.isEmpty()) return false;
    if (chbg_is(v, "none")) {
        out->clear();
        return true;
    }
    std::vector<float> d;
    QString norm = v.toString();
    norm.replace(QLatin1Char(','), QLatin1Char(' '));
    for (const QString& t : norm.split(QLatin1Char(' '), Qt::SkipEmptyParts)) {
        float f = 0;
        if (!parse_length(t, Axis::Diag, c, &f) || f < 0) return false;
        d.push_back(f);
    }
    if (d.empty()) return false;
    *out = std::move(d);
    return true;
}

int chbg_weight(QStringView v, int parent) {
    v = v.trimmed();
    if (chbg_is(v, "normal")) return 400;
    if (chbg_is(v, "bold")) return 700;
    if (chbg_is(v, "bolder")) return parent < 350 ? 400 : parent < 550 ? 700 : 900;
    if (chbg_is(v, "lighter")) return parent < 550 ? 100 : parent < 750 ? 400 : 700;
    float f = 0;
    if (parse_number(v, &f) && f >= 1 && f <= 1000) return int(std::lround(f));
    return -1;
}

/// font-size: length/percentage relative to the parent's font size (keywords: the CSS absolute table).
bool chbg_font_size(QStringView v, float parent, float* out) {
    v = v.trimmed();
    static const struct { const char* k; float px; } kw[] = {{"xx-small", 9}, {"x-small", 10}, {"small", 13},
        {"medium", 16}, {"large", 18}, {"x-large", 24}, {"xx-large", 32}, {"xxx-large", 48}};
    for (const auto& e : kw)
        if (chbg_is(v, e.k)) { *out = e.px; return true; }
    if (chbg_is(v, "smaller")) { *out = parent / 1.2f; return true; }
    if (chbg_is(v, "larger")) { *out = parent * 1.2f; return true; }
    SpecLen sl;
    if (!parse_css_length(v, &sl, true) || sl.kind != SpecLen::Val) return false;
    const float f = sl.px + sl.em * parent + sl.rem * 16.0f + sl.pct * parent / 100.0f;
    if (f < 0) return false;
    *out = f;
    return true;
}

} // namespace

// ---------------------------------------------------------------------------------------------- numbers

const QString* attr(const RNode* r, QStringView name) { return (r && r->src) ? r->src->attr(name) : nullptr; }

bool scan_number(QStringView s, int* pi, float* out) {
    int i = *pi;
    const int n = int(s.size());
    const int start = i;
    if (i < n && (s[i] == u'+' || s[i] == u'-')) ++i;
    int digits = 0;
    while (i < n && s[i].isDigit()) { ++i; ++digits; }
    if (i < n && s[i] == u'.') {
        int j = i + 1, frac = 0;
        while (j < n && s[j].isDigit()) { ++j; ++frac; }
        if (frac > 0 || digits > 0) { i = j; digits += frac; }
    }
    if (digits == 0) return false;
    if (i < n && (s[i] == u'e' || s[i] == u'E')) {
        int j = i + 1;
        if (j < n && (s[j] == u'+' || s[j] == u'-')) ++j;
        int ed = 0;
        while (j < n && s[j].isDigit()) { ++j; ++ed; }
        if (ed > 0) i = j; // "1e" / "1em": the exponent is not part of the number
    }
    bool ok = false;
    const double v = s.mid(start, i - start).toDouble(&ok);
    if (!ok || !std::isfinite(v)) return false;
    *out = float(v);
    *pi = i;
    return true;
}

bool parse_number(QStringView s, float* out) {
    s = s.trimmed();
    int i = 0;
    float v = 0;
    if (!scan_number(s, &i, &v) || i != s.size()) return false;
    *out = v;
    return true;
}

std::vector<float> number_list(QStringView s, bool* ok) {
    std::vector<float> out;
    int i = 0;
    chbg_skip_wsp(s, &i);
    bool good = true;
    while (i < s.size()) {
        float v = 0;
        if (!scan_number(s, &i, &v)) { good = false; break; }
        out.push_back(v);
        chbg_skip_comma_wsp(s, &i);
    }
    if (ok) *ok = good;
    return out;
}

// ---------------------------------------------------------------------------------------------- lengths

float LenCtx::diag() const { return std::sqrt((w * w + h * h) / 2.0f); }

bool parse_length(QStringView s, Axis ax, const LenCtx& c, float* out) {
    s = s.trimmed();
    if (s.isEmpty()) return false;
    float f = 0;
    if (parse_number(s, &f)) { *out = f; return true; } // fast path (numbers from React props)
    SpecLen sl;
    if (!parse_css_length(s, &sl, true) || sl.kind != SpecLen::Val) return false;
    const float ref = ax == Axis::X ? c.w : ax == Axis::Y ? c.h : c.diag();
    *out = sl.px + sl.em * c.fontSize + sl.rem * 16.0f + sl.pct * ref / 100.0f;
    return std::isfinite(*out);
}

float attr_len(const RNode* r, QStringView name, Axis ax, const LenCtx& c, float def) {
    const QString* v = attr(r, name);
    float f = 0;
    return (v && parse_length(*v, ax, c, &f)) ? f : def;
}

float attr_len_first(const RNode* r, QStringView name, Axis ax, const LenCtx& c, float def) {
    const QString* v = attr(r, name);
    if (!v) return def;
    const QStringView t = QStringView(*v).trimmed();
    int cut = 0;
    while (cut < t.size() && !chbg_wsp(t[cut]) && t[cut] != u',') ++cut;
    float f = 0;
    return parse_length(t.left(cut), ax, c, &f) ? f : def;
}

// ---------------------------------------------------------------------------------------------- transform

QTransform parse_transform(QStringView s, bool* okOut) {
    QTransform t;
    int i = 0;
    const int n = int(s.size());
    bool ok = true;
    chbg_skip_wsp(s, &i);
    while (i < n) {
        const int nameStart = i;
        while (i < n && s[i].isLetter()) ++i;
        const QStringView name = s.mid(nameStart, i - nameStart);
        chbg_skip_wsp(s, &i);
        if (name.isEmpty() || i >= n || s[i] != u'(') { ok = false; break; }
        ++i;
        std::vector<float> a;
        chbg_skip_wsp(s, &i);
        while (i < n && s[i] != u')') {
            float v = 0;
            if (!scan_number(s, &i, &v)) { ok = false; break; }
            a.push_back(v);
            chbg_skip_comma_wsp(s, &i);
        }
        if (!ok || i >= n) { ok = false; break; }
        ++i; // ')'
        QTransform x;
        const size_t k = a.size();
        if (name == u"matrix" && k == 6) x = QTransform(a[0], a[1], a[2], a[3], a[4], a[5]);
        else if (name == u"translate" && (k == 1 || k == 2)) x.translate(a[0], k == 2 ? a[1] : 0);
        else if (name == u"scale" && (k == 1 || k == 2)) x.scale(a[0], k == 2 ? a[1] : a[0]);
        else if (name == u"rotate" && (k == 1 || k == 3)) {
            if (k == 3) { x.translate(a[1], a[2]); x.rotate(a[0]); x.translate(-a[1], -a[2]); }
            else x.rotate(a[0]);
        } else if (name == u"skewX" && k == 1) x.shear(std::tan(a[0] * M_PI / 180.0), 0);
        else if (name == u"skewY" && k == 1) x.shear(0, std::tan(a[0] * M_PI / 180.0));
        else { ok = false; break; }
        t = x * t; // "A B": B applies first
        chbg_skip_comma_wsp(s, &i);
    }
    if (okOut) *okOut = ok;
    return ok ? t : QTransform();
}

VbState parse_viewbox(const RNode* r, QRectF* vb) {
    const QString* v = attr(r, u"viewBox");
    if (!v) return VbState::Absent;
    bool ok = false;
    const std::vector<float> n = number_list(*v, &ok);
    if (!ok || n.size() != 4 || n[2] < 0 || n[3] < 0) return VbState::Absent;
    *vb = QRectF(n[0], n[1], n[2], n[3]);
    return (n[2] == 0 || n[3] == 0) ? VbState::Empty : VbState::Valid;
}

QTransform viewbox_to_viewport(const QRectF& vb, const QString* par, const QRectF& vp) {
    QTransform t;
    if (vb.width() <= 0 || vb.height() <= 0) return t;
    int ax = 1, ay = 1; // 0 min, 1 mid, 2 max
    bool none = false, slice = false;
    if (par) {
        QStringList tok = par->simplified().split(QLatin1Char(' '), Qt::SkipEmptyParts);
        if (!tok.isEmpty() && tok.front() == QLatin1String("defer")) tok.pop_front();
        bool valid = !tok.isEmpty() && tok.size() <= 2;
        int px = 1, py = 1;
        bool pn = false, ps = false;
        if (valid) {
            const QString& al = tok[0];
            if (al == QLatin1String("none")) pn = true;
            else if (al.size() == 8 && al[0] == u'x' && al[4] == u'Y') {
                auto lvl = [](QStringView v) { return v == u"Min" ? 0 : v == u"Mid" ? 1 : v == u"Max" ? 2 : -1; };
                px = lvl(QStringView(al).mid(1, 3));
                py = lvl(QStringView(al).mid(5, 3));
                valid = px >= 0 && py >= 0;
            } else valid = false;
            if (valid && tok.size() == 2) {
                if (tok[1] == QLatin1String("slice")) ps = true;
                else if (tok[1] != QLatin1String("meet")) valid = false;
            }
        }
        if (valid) { ax = px; ay = py; none = pn; slice = ps; }
    }
    const qreal sx = vp.width() / vb.width(), sy = vp.height() / vb.height();
    if (none) {
        t.translate(vp.x(), vp.y());
        t.scale(sx, sy);
        t.translate(-vb.x(), -vb.y());
        return t;
    }
    const qreal s = slice ? std::max(sx, sy) : std::min(sx, sy);
    const qreal w = vb.width() * s, h = vb.height() * s;
    const qreal ox = vp.x() + (vp.width() - w) * ax / 2.0, oy = vp.y() + (vp.height() - h) * ay / 2.0;
    t.translate(ox, oy);
    t.scale(s, s);
    t.translate(-vb.x(), -vb.y());
    return t;
}

// ---------------------------------------------------------------------------------------------- style

bool is_display_none(const RNode* r) {
    if (!r) return true;
    if (chbg_own_decl(r, Prop::Display)) return r->style && r->style->display == Display::None;
    const QString* d = attr(r, u"display");
    return d && d->trimmed() == QLatin1String("none");
}

float element_opacity(const RNode* r) {
    if (r->style && chbg_own_decl(r, Prop::Opacity)) return std::clamp(r->style->opacity, 0.0f, 1.0f);
    float f = 1;
    if (const QString* o = attr(r, u"opacity"); o && chbg_alpha(*o, &f)) return f;
    return 1;
}

Style root_style(const RNode* svg) {
    Style s;
    if (svg && svg->style) {
        const ComputedStyle& cs = *svg->style;
        s.color = cs.color;
        s.fontSize = cs.fontSize;
        if (cs.fontFamily) s.fontFamily = *cs.fontFamily;
        s.fontWeight = cs.fontWeight;
        s.italic = cs.fontStyle != FontStyle::Normal;
        s.letterSpacing = cs.letterSpacing;
        s.visible = cs.visibility == Visibility::Visible;
    }
    return s;
}

Style inherit_style(const RNode* r, const Style& parent, const LenCtx& ctx) {
    Style s = parent;
    const ComputedStyle* cs = r->style;
    // value from own CSS (bit set in svg.own) if it parses, else from the attribute; `apply` returns validity
    auto pick = [&](std::uint32_t bit, const QString* css, QStringView name, auto&& apply) {
        if (cs && css && (cs->svg.own & (1u << bit)) && apply(QStringView(*css))) return;
        if (const QString* a = attr(r, name)) apply(QStringView(*a));
    };
    auto inheritKw = [](QStringView v) { return v.trimmed() == u"inherit"; };

    // ---- color + font first (em lengths below use the element's own font size)
    if (cs && chbg_own_decl(r, Prop::Color)) s.color = cs->color;
    else if (const QString* a = attr(r, u"color")) {
        QColor c;
        bool cur = false;
        if (parse_css_color(*a, &c, &cur) && !cur) s.color = c;
    }
    if (cs && chbg_own_decl(r, Prop::FontSize)) s.fontSize = cs->fontSize;
    else if (const QString* a = attr(r, u"fontSize")) chbg_font_size(*a, parent.fontSize, &s.fontSize);
    if (cs && chbg_own_decl(r, Prop::FontFamily)) { if (cs->fontFamily) s.fontFamily = *cs->fontFamily; }
    else if (const QString* a = attr(r, u"fontFamily")) {
        const QStringList f = parse_font_family(*a);
        if (!f.isEmpty() && !inheritKw(*a)) s.fontFamily = f;
    }
    if (cs && chbg_own_decl(r, Prop::FontWeight)) s.fontWeight = cs->fontWeight;
    else if (const QString* a = attr(r, u"fontWeight")) {
        const int w = chbg_weight(*a, parent.fontWeight);
        if (w > 0) s.fontWeight = w;
    }
    if (cs && chbg_own_decl(r, Prop::FontStyle)) s.italic = cs->fontStyle != FontStyle::Normal;
    else if (const QString* a = attr(r, u"fontStyle")) {
        const QStringView v = QStringView(*a).trimmed();
        if (v == u"normal") s.italic = false;
        else if (v == u"italic" || v.startsWith(u"oblique")) s.italic = true;
    }
    LenCtx c = ctx;
    c.fontSize = s.fontSize;
    if (cs && chbg_own_decl(r, Prop::LetterSpacing)) s.letterSpacing = cs->letterSpacing;
    else if (const QString* a = attr(r, u"letterSpacing")) {
        const QStringView v = QStringView(*a).trimmed();
        float f = 0;
        if (v == u"normal") s.letterSpacing = 0;
        else if (parse_length(v, Axis::X, LenCtx{c.fontSize, c.fontSize, c.fontSize}, &f)) s.letterSpacing = f;
    }
    if (cs && chbg_own_decl(r, Prop::Visibility)) s.visible = cs->visibility == Visibility::Visible;
    else if (const QString* a = attr(r, u"visibility")) {
        const QStringView v = QStringView(*a).trimmed();
        if (v == u"visible") s.visible = true;
        else if (v == u"hidden" || v == u"collapse") s.visible = false;
    }

    // ---- paint
    const SvgProps* sp = cs ? &cs->svg : nullptr;
    pick(0, sp ? &sp->fill : nullptr, u"fill", [&](QStringView v) { return inheritKw(v) || chbg_paint(v, &s.fill); });
    pick(1, sp ? &sp->stroke : nullptr, u"stroke", [&](QStringView v) { return inheritKw(v) || chbg_paint(v, &s.stroke); });
    pick(2, sp ? &sp->strokeWidth : nullptr, u"strokeWidth", [&](QStringView v) {
        float f = 0;
        if (inheritKw(v)) return true;
        if (!parse_length(v, Axis::Diag, c, &f) || f < 0) return false;
        s.strokeWidth = f;
        return true;
    });
    pick(3, sp ? &sp->strokeDasharray : nullptr, u"strokeDasharray", [&](QStringView v) { return inheritKw(v) || chbg_dash(v, c, &s.dash); });
    pick(4, sp ? &sp->strokeOpacity : nullptr, u"strokeOpacity", [&](QStringView v) { return inheritKw(v) || chbg_alpha(v, &s.strokeOpacity); });
    pick(5, sp ? &sp->fillOpacity : nullptr, u"fillOpacity", [&](QStringView v) { return inheritKw(v) || chbg_alpha(v, &s.fillOpacity); });
    pick(6, sp ? &sp->strokeLinecap : nullptr, u"strokeLinecap", [&](QStringView v) {
        v = v.trimmed();
        if (v == u"butt") s.cap = Qt::FlatCap;
        else if (v == u"round") s.cap = Qt::RoundCap;
        else if (v == u"square") s.cap = Qt::SquareCap;
        else return inheritKw(v);
        return true;
    });
    pick(7, sp ? &sp->strokeLinejoin : nullptr, u"strokeLinejoin", [&](QStringView v) {
        v = v.trimmed();
        if (v == u"miter" || v == u"miter-clip" || v == u"arcs") s.join = Qt::MiterJoin;
        else if (v == u"round") s.join = Qt::RoundJoin;
        else if (v == u"bevel") s.join = Qt::BevelJoin;
        else return inheritKw(v);
        return true;
    });
    pick(8, sp ? &sp->textAnchor : nullptr, u"textAnchor", [&](QStringView v) {
        v = v.trimmed();
        if (v == u"start") s.anchor = 0;
        else if (v == u"middle") s.anchor = 1;
        else if (v == u"end") s.anchor = 2;
        else return inheritKw(v);
        return true;
    });
    pick(9, sp ? &sp->dominantBaseline : nullptr, u"dominantBaseline", [&](QStringView v) {
        v = v.trimmed();
        static const struct { const char* k; Baseline b; } tab[] = {{"auto", Baseline::Auto},
            {"use-script", Baseline::Auto}, {"reset-size", Baseline::Auto}, {"alphabetic", Baseline::Auto},
            {"middle", Baseline::Middle}, {"central", Baseline::Central}, {"hanging", Baseline::Hanging},
            {"mathematical", Baseline::Mathematical}, {"ideographic", Baseline::Ideographic},
            {"text-before-edge", Baseline::BeforeEdge}, {"text-after-edge", Baseline::AfterEdge}};
        if (v == u"no-change" || inheritKw(v)) return true;
        for (const auto& e : tab)
            if (v == QLatin1String(e.k)) { s.baseline = e.b; return true; }
        return false; // text-top / text-bottom are not dominant-baseline values in Chrome (measured: ignored)
    });
    // attribute-only properties
    if (const QString* a = attr(r, u"fillRule")) {
        const QStringView v = QStringView(*a).trimmed();
        if (v == u"evenodd") s.evenOdd = true;
        else if (v == u"nonzero") s.evenOdd = false;
    }
    if (const QString* a = attr(r, u"strokeDashoffset")) {
        float f = 0;
        if (parse_length(*a, Axis::Diag, c, &f)) s.dashOffset = f;
    }
    if (const QString* a = attr(r, u"strokeMiterlimit")) {
        float f = 0;
        if (parse_number(*a, &f) && f >= 1) s.miterLimit = f;
    }
    auto marker = [&](QStringView name, QString* out) {
        const QString* a = attr(r, name);
        if (!a) return;
        const QStringView v = QStringView(*a).trimmed();
        if (v == u"none") { out->clear(); return; }
        PaintRef pr;
        if (chbg_paint(v, &pr) && pr.kind == PaintRef::Url && pr.fbKind == PaintRef::None) *out = pr.id;
    };
    marker(u"markerStart", &s.markerStart);
    marker(u"markerMid", &s.markerMid);
    marker(u"markerEnd", &s.markerEnd);
    return s;
}

} // namespace fincept::screens::chb::svg
