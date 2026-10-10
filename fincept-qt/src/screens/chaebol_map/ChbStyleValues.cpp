// ChbStyleValues.cpp — CSS value parsers (colour, length/calc, gradient, shadow, grid tracks, transform).
#include "screens/chaebol_map/ChbStyle.h"
#include "screens/chaebol_map/ChbStyle_p.h"

#include <QHash>

#include <algorithm>
#include <cmath>
#include <cstring>

namespace fincept::screens::chb {

namespace {

// CSS Color 4 named colours (extended keywords).
const QHash<QString, QRgb>& chbs_named() {
    static const QHash<QString, QRgb> m = [] {
        QHash<QString, QRgb> h;
        const struct { const char* n; QRgb v; } t[] = {
            {"aliceblue", 0xf0f8ff}, {"antiquewhite", 0xfaebd7}, {"aqua", 0x00ffff}, {"aquamarine", 0x7fffd4},
            {"azure", 0xf0ffff}, {"beige", 0xf5f5dc}, {"bisque", 0xffe4c4}, {"black", 0x000000},
            {"blanchedalmond", 0xffebcd}, {"blue", 0x0000ff}, {"blueviolet", 0x8a2be2}, {"brown", 0xa52a2a},
            {"burlywood", 0xdeb887}, {"cadetblue", 0x5f9ea0}, {"chartreuse", 0x7fff00}, {"chocolate", 0xd2691e},
            {"coral", 0xff7f50}, {"cornflowerblue", 0x6495ed}, {"cornsilk", 0xfff8dc}, {"crimson", 0xdc143c},
            {"cyan", 0x00ffff}, {"darkblue", 0x00008b}, {"darkcyan", 0x008b8b}, {"darkgoldenrod", 0xb8860b},
            {"darkgray", 0xa9a9a9}, {"darkgreen", 0x006400}, {"darkgrey", 0xa9a9a9}, {"darkkhaki", 0xbdb76b},
            {"darkmagenta", 0x8b008b}, {"darkolivegreen", 0x556b2f}, {"darkorange", 0xff8c00},
            {"darkorchid", 0x9932cc}, {"darkred", 0x8b0000}, {"darksalmon", 0xe9967a}, {"darkseagreen", 0x8fbc8f},
            {"darkslateblue", 0x483d8b}, {"darkslategray", 0x2f4f4f}, {"darkslategrey", 0x2f4f4f},
            {"darkturquoise", 0x00ced1}, {"darkviolet", 0x9400d3}, {"deeppink", 0xff1493},
            {"deepskyblue", 0x00bfff}, {"dimgray", 0x696969}, {"dimgrey", 0x696969}, {"dodgerblue", 0x1e90ff},
            {"firebrick", 0xb22222}, {"floralwhite", 0xfffaf0}, {"forestgreen", 0x228b22}, {"fuchsia", 0xff00ff},
            {"gainsboro", 0xdcdcdc}, {"ghostwhite", 0xf8f8ff}, {"gold", 0xffd700}, {"goldenrod", 0xdaa520},
            {"gray", 0x808080}, {"green", 0x008000}, {"greenyellow", 0xadff2f}, {"grey", 0x808080},
            {"honeydew", 0xf0fff0}, {"hotpink", 0xff69b4}, {"indianred", 0xcd5c5c}, {"indigo", 0x4b0082},
            {"ivory", 0xfffff0}, {"khaki", 0xf0e68c}, {"lavender", 0xe6e6fa}, {"lavenderblush", 0xfff0f5},
            {"lawngreen", 0x7cfc00}, {"lemonchiffon", 0xfffacd}, {"lightblue", 0xadd8e6}, {"lightcoral", 0xf08080},
            {"lightcyan", 0xe0ffff}, {"lightgoldenrodyellow", 0xfafad2}, {"lightgray", 0xd3d3d3},
            {"lightgreen", 0x90ee90}, {"lightgrey", 0xd3d3d3}, {"lightpink", 0xffb6c1}, {"lightsalmon", 0xffa07a},
            {"lightseagreen", 0x20b2aa}, {"lightskyblue", 0x87cefa}, {"lightslategray", 0x778899},
            {"lightslategrey", 0x778899}, {"lightsteelblue", 0xb0c4de}, {"lightyellow", 0xffffe0},
            {"lime", 0x00ff00}, {"limegreen", 0x32cd32}, {"linen", 0xfaf0e6}, {"magenta", 0xff00ff},
            {"maroon", 0x800000}, {"mediumaquamarine", 0x66cdaa}, {"mediumblue", 0x0000cd},
            {"mediumorchid", 0xba55d3}, {"mediumpurple", 0x9370db}, {"mediumseagreen", 0x3cb371},
            {"mediumslateblue", 0x7b68ee}, {"mediumspringgreen", 0x00fa9a}, {"mediumturquoise", 0x48d1cc},
            {"mediumvioletred", 0xc71585}, {"midnightblue", 0x191970}, {"mintcream", 0xf5fffa},
            {"mistyrose", 0xffe4e1}, {"moccasin", 0xffe4b5}, {"navajowhite", 0xffdead}, {"navy", 0x000080},
            {"oldlace", 0xfdf5e6}, {"olive", 0x808000}, {"olivedrab", 0x6b8e23}, {"orange", 0xffa500},
            {"orangered", 0xff4500}, {"orchid", 0xda70d6}, {"palegoldenrod", 0xeee8aa}, {"palegreen", 0x98fb98},
            {"paleturquoise", 0xafeeee}, {"palevioletred", 0xdb7093}, {"papayawhip", 0xffefd5},
            {"peachpuff", 0xffdab9}, {"peru", 0xcd853f}, {"pink", 0xffc0cb}, {"plum", 0xdda0dd},
            {"powderblue", 0xb0e0e6}, {"purple", 0x800080}, {"rebeccapurple", 0x663399}, {"red", 0xff0000},
            {"rosybrown", 0xbc8f8f}, {"royalblue", 0x4169e1}, {"saddlebrown", 0x8b4513}, {"salmon", 0xfa8072},
            {"sandybrown", 0xf4a460}, {"seagreen", 0x2e8b57}, {"seashell", 0xfff5ee}, {"sienna", 0xa0522d},
            {"silver", 0xc0c0c0}, {"skyblue", 0x87ceeb}, {"slateblue", 0x6a5acd}, {"slategray", 0x708090},
            {"slategrey", 0x708090}, {"snow", 0xfffafa}, {"springgreen", 0x00ff7f}, {"steelblue", 0x4682b4},
            {"tan", 0xd2b48c}, {"teal", 0x008080}, {"thistle", 0xd8bfd8}, {"tomato", 0xff6347},
            {"turquoise", 0x40e0d0}, {"violet", 0xee82ee}, {"wheat", 0xf5deb3}, {"white", 0xffffff},
            {"whitesmoke", 0xf5f5f5}, {"yellow", 0xffff00}, {"yellowgreen", 0x9acd32},
            // system colours the UA sheet uses (light scheme, Chrome 147)
            {"buttonface", 0xefefef}, {"buttontext", 0x000000}, {"buttonborder", 0x767676}, {"field", 0xffffff},
            {"fieldtext", 0x000000}, {"canvas", 0xffffff}, {"canvastext", 0x000000}, {"linktext", 0x0000ee},
            {"graytext", 0x6d6d6d},
        };
        for (const auto& e : t) h.insert(QString::fromLatin1(e.n), e.v);
        return h;
    }();
    return m;
}

int chbs_hex(QChar c) {
    const ushort u = c.unicode();
    if (u >= '0' && u <= '9') return u - '0';
    if (u >= 'a' && u <= 'f') return u - 'a' + 10;
    if (u >= 'A' && u <= 'F') return u - 'A' + 10;
    return -1;
}

bool chbs_num(QStringView s, float* out) {
    bool ok = false;
    const double d = s.toString().toDouble(&ok);
    if (!ok || !std::isfinite(d)) return false;
    *out = float(d);
    return true;
}

/// Colour channel: number 0–255 or percentage.
bool chbs_channel(QStringView s, float* out) {
    s = s.trimmed();
    if (s.endsWith(u'%')) {
        float p = 0;
        if (!chbs_num(s.chopped(1), &p)) return false;
        *out = std::clamp(p * 2.55f, 0.0f, 255.0f);
        return true;
    }
    float v = 0;
    if (!chbs_num(s, &v)) return false;
    *out = std::clamp(v, 0.0f, 255.0f);
    return true;
}
bool chbs_alpha(QStringView s, float* out) {
    s = s.trimmed();
    if (s.endsWith(u'%')) {
        float p = 0;
        if (!chbs_num(s.chopped(1), &p)) return false;
        *out = std::clamp(p / 100.0f, 0.0f, 1.0f);
        return true;
    }
    float v = 0;
    if (!chbs_num(s, &v)) return false;
    *out = std::clamp(v, 0.0f, 1.0f);
    return true;
}

/// Arguments of a colour function: comma or space syntax, optional "/ alpha".
QStringList chbs_color_args(QStringView inner) {
    QString s = inner.toString();
    if (s.contains(QLatin1Char(','))) {
        QStringList out;
        for (const QString& p : s.split(QLatin1Char(','))) out << p.trimmed();
        return out;
    }
    s.replace(QLatin1Char('/'), QStringLiteral(" / "));
    QStringList parts = s.split(QLatin1Char(' '), Qt::SkipEmptyParts);
    QStringList out;
    for (int i = 0; i < parts.size(); ++i) {
        if (parts[i] == QLatin1String("/")) continue;
        out << parts[i];
    }
    return out;
}

float chbs_hue2rgb(float p, float q, float t) {
    if (t < 0) t += 1;
    if (t > 1) t -= 1;
    if (t < 1.0f / 6) return p + (q - p) * 6 * t;
    if (t < 1.0f / 2) return q;
    if (t < 2.0f / 3) return p + (q - p) * (2.0f / 3 - t) * 6;
    return p;
}

} // namespace

// ============================================================================================== colour

bool parse_css_color(QStringView in, QColor* out, bool* current) {
    if (current) *current = false;
    const QString s = in.trimmed().toString().toLower();
    if (s.isEmpty()) return false;
    if (s == QLatin1String("transparent")) {
        *out = QColor(0, 0, 0, 0);
        return true;
    }
    if (s == QLatin1String("currentcolor")) {
        if (current) *current = true;
        *out = QColor(0, 0, 0);
        return true;
    }
    if (s.startsWith(QLatin1Char('#'))) {
        const QStringView h = QStringView(s).mid(1);
        int d[8] = {0};
        for (int i = 0; i < h.size(); ++i) {
            d[i < 8 ? i : 7] = chbs_hex(h[i]);
            if (d[i < 8 ? i : 7] < 0) return false;
        }
        switch (h.size()) {
        case 3: *out = QColor(d[0] * 17, d[1] * 17, d[2] * 17); return true;
        case 4: *out = QColor(d[0] * 17, d[1] * 17, d[2] * 17, d[3] * 17); return true;
        case 6: *out = QColor(d[0] * 16 + d[1], d[2] * 16 + d[3], d[4] * 16 + d[5]); return true;
        case 8: // CSS #RRGGBBAA — alpha LAST (never hand this string to QColor)
            *out = QColor(d[0] * 16 + d[1], d[2] * 16 + d[3], d[4] * 16 + d[5], d[6] * 16 + d[7]);
            return true;
        default: return false;
        }
    }
    const int lp = s.indexOf(QLatin1Char('('));
    if (lp > 0 && s.endsWith(QLatin1Char(')'))) {
        const QString fn = s.left(lp).trimmed();
        const QStringList a = chbs_color_args(QStringView(s).mid(lp + 1, s.size() - lp - 2));
        if (fn == QLatin1String("rgb") || fn == QLatin1String("rgba")) {
            if (a.size() != 3 && a.size() != 4) return false;
            float r, g, b, al = 1;
            if (!chbs_channel(a[0], &r) || !chbs_channel(a[1], &g) || !chbs_channel(a[2], &b)) return false;
            if (a.size() == 4 && !chbs_alpha(a[3], &al)) return false;
            *out = QColor(qRound(r), qRound(g), qRound(b), qRound(al * 255));
            return true;
        }
        if (fn == QLatin1String("hsl") || fn == QLatin1String("hsla")) {
            if (a.size() != 3 && a.size() != 4) return false;
            QString hs = a[0];
            hs.remove(QStringLiteral("deg"));
            float hh, ss, ll, al = 1;
            if (!chbs_num(hs, &hh)) return false;
            QString sp = a[1], lpv = a[2];
            sp.remove(QLatin1Char('%'));
            lpv.remove(QLatin1Char('%'));
            if (!chbs_num(sp, &ss) || !chbs_num(lpv, &ll)) return false;
            if (a.size() == 4 && !chbs_alpha(a[3], &al)) return false;
            hh = std::fmod(std::fmod(hh, 360.0f) + 360.0f, 360.0f) / 360.0f;
            ss = std::clamp(ss / 100.0f, 0.0f, 1.0f);
            ll = std::clamp(ll / 100.0f, 0.0f, 1.0f);
            float r = ll, g = ll, b = ll;
            if (ss > 0) {
                const float q = ll < 0.5f ? ll * (1 + ss) : ll + ss - ll * ss;
                const float p = 2 * ll - q;
                r = chbs_hue2rgb(p, q, hh + 1.0f / 3);
                g = chbs_hue2rgb(p, q, hh);
                b = chbs_hue2rgb(p, q, hh - 1.0f / 3);
            }
            *out = QColor(qRound(r * 255), qRound(g * 255), qRound(b * 255), qRound(al * 255));
            return true;
        }
        return false;
    }
    const auto& named = chbs_named();
    const auto it = named.find(s);
    if (it == named.end()) return false;
    *out = QColor::fromRgb(it.value());
    return true;
}

// ============================================================================================== splitting

QStringList css_split_ws(QStringView s) {
    QStringList out;
    QString cur;
    int depth = 0;
    QChar quote;
    for (const QChar c : s) {
        if (!quote.isNull()) {
            cur += c;
            if (c == quote) quote = QChar();
            continue;
        }
        if (c == u'"' || c == u'\'') {
            quote = c;
            cur += c;
            continue;
        }
        if (c == u'(') ++depth;
        if (c == u')') depth = std::max(0, depth - 1);
        if (depth == 0 && c.isSpace()) {
            if (!cur.isEmpty()) out << cur;
            cur.clear();
            continue;
        }
        cur += c;
    }
    if (!cur.isEmpty()) out << cur;
    return out;
}

QStringList css_split_commas(QStringView s) {
    QStringList out;
    QString cur;
    int depth = 0;
    QChar quote;
    for (const QChar c : s) {
        if (!quote.isNull()) {
            cur += c;
            if (c == quote) quote = QChar();
            continue;
        }
        if (c == u'"' || c == u'\'') {
            quote = c;
            cur += c;
            continue;
        }
        if (c == u'(') ++depth;
        if (c == u')') depth = std::max(0, depth - 1);
        if (depth == 0 && c == u',') {
            out << cur.trimmed();
            cur.clear();
            continue;
        }
        cur += c;
    }
    out << cur.trimmed();
    return out;
}

// ============================================================================================== length / calc

namespace {

struct ChbsCalc {
    QStringView s;
    int i = 0;
    bool ok = true;

    void ws() {
        while (i < s.size() && s[i].isSpace()) ++i;
    }
    // A term value: either a pure number (isNum) or a length combination.
    struct V {
        bool isNum = false;
        float n = 0;
        SpecLen l;
    };
    static void addScaled(SpecLen& a, const SpecLen& b, float k) {
        a.px += b.px * k; a.em += b.em * k; a.rem += b.rem * k; a.pct += b.pct * k; a.vw += b.vw * k; a.vh += b.vh * k;
        a.pctUnit = a.pctUnit || b.pctUnit;
    }
    V primary() {
        ws();
        V v;
        if (i >= s.size()) { ok = false; return v; }
        if (s[i] == u'(') {
            ++i;
            v = expr();
            ws();
            if (i < s.size() && s[i] == u')') ++i;
            else ok = false;
            return v;
        }
        if (s.mid(i).startsWith(u"calc(")) {
            i += 5;
            v = expr();
            ws();
            if (i < s.size() && s[i] == u')') ++i;
            else ok = false;
            return v;
        }
        int j = i;
        if (j < s.size() && (s[j] == u'+' || s[j] == u'-')) ++j;
        while (j < s.size() && (s[j].isDigit() || s[j] == u'.')) ++j;
        if (j < s.size() && (s[j] == u'e' || s[j] == u'E') && j + 1 < s.size() &&
            (s[j + 1].isDigit() || s[j + 1] == u'-' || s[j + 1] == u'+')) {
            j += 2;
            while (j < s.size() && s[j].isDigit()) ++j;
        }
        float num = 0;
        if (!chbs_num(s.mid(i, j - i), &num)) { ok = false; return v; }
        int k = j;
        while (k < s.size() && (s[k].isLetter() || s[k] == u'%')) ++k;
        const QString unit = s.mid(j, k - j).toString().toLower();
        i = k;
        if (unit.isEmpty()) { v.isNum = true; v.n = num; return v; }
        if (unit == QLatin1String("px")) v.l.px = num;
        else if (unit == QLatin1String("em")) v.l.em = num;
        else if (unit == QLatin1String("rem")) v.l.rem = num;
        else if (unit == QLatin1String("%")) { v.l.pct = num; v.l.pctUnit = true; }
        else if (unit == QLatin1String("vw")) v.l.vw = num;
        else if (unit == QLatin1String("vh")) v.l.vh = num;
        else if (unit == QLatin1String("pt")) v.l.px = num * 4.0f / 3.0f;
        else if (unit == QLatin1String("pc")) v.l.px = num * 16.0f;
        else if (unit == QLatin1String("in")) v.l.px = num * 96.0f;
        else if (unit == QLatin1String("cm")) v.l.px = num * 96.0f / 2.54f;
        else if (unit == QLatin1String("mm")) v.l.px = num * 96.0f / 25.4f;
        else if (unit == QLatin1String("ch") || unit == QLatin1String("ex")) v.l.em = num * 0.5f;
        else if (unit == QLatin1String("vmin") || unit == QLatin1String("vmax")) v.l.vw = num; // approximation
        else { ok = false; }
        return v;
    }
    V term() {
        V a = primary();
        while (ok) {
            ws();
            if (i >= s.size() || (s[i] != u'*' && s[i] != u'/')) break;
            const QChar op = s[i++];
            V b = primary();
            if (op == u'*') {
                if (a.isNum && b.isNum) a.n *= b.n;
                else if (a.isNum) { SpecLen r; addScaled(r, b.l, a.n); a.isNum = false; a.l = r; }
                else if (b.isNum) { SpecLen r; addScaled(r, a.l, b.n); a.l = r; }
                else ok = false;
            } else {
                if (!b.isNum || b.n == 0) { ok = false; break; }
                if (a.isNum) a.n /= b.n;
                else { SpecLen r; addScaled(r, a.l, 1.0f / b.n); a.l = r; }
            }
        }
        return a;
    }
    V expr() {
        V a = term();
        while (ok) {
            ws();
            if (i >= s.size() || (s[i] != u'+' && s[i] != u'-')) break;
            const QChar op = s[i++];
            V b = term();
            const float k = op == u'+' ? 1.0f : -1.0f;
            if (a.isNum && b.isNum) a.n += k * b.n;
            else if (!a.isNum && !b.isNum) addScaled(a.l, b.l, k);
            else if (a.isNum && a.n == 0) { a.isNum = false; a.l = SpecLen(); addScaled(a.l, b.l, k); }
            else if (b.isNum && b.n == 0) {}
            else ok = false;
        }
        return a;
    }
};

} // namespace

bool parse_css_length(QStringView in, SpecLen* out, bool allowNumber) {
    const QStringView s = in.trimmed();
    if (s.isEmpty()) return false;
    const QString low = s.toString().toLower();
    if (low == QLatin1String("auto")) { *out = SpecLen{}; out->kind = SpecLen::Auto; return true; }
    ChbsCalc c;
    c.s = QStringView(low);
    ChbsCalc::V v = c.expr();
    c.ws();
    if (!c.ok || c.i != c.s.size()) return false;
    if (v.isNum) {
        if (v.n != 0 && !allowNumber) return false;
        *out = SpecLen{};
        out->px = v.n;
        return true;
    }
    *out = v.l;
    out->kind = SpecLen::Val;
    return true;
}

Len resolve_len(const SpecLen& s, float fontSize, const StyleEnv& env) {
    Len l;
    l.kind = Len::Kind(s.kind);
    if (s.kind != SpecLen::Val) return l;
    l.px = s.px + s.em * fontSize + s.rem * env.rootFontSize + s.vw * env.vw / 100.0f + s.vh * env.vh / 100.0f;
    l.pct = s.pct;
    l.pctUnit = s.pctUnit;
    return l;
}

// ============================================================================================== font family

QStringList parse_font_family(QStringView s) {
    QStringList out;
    for (QString p : css_split_commas(s)) {
        p = p.trimmed();
        if (p.size() >= 2 && (p.startsWith(QLatin1Char('"')) || p.startsWith(QLatin1Char('\''))) &&
            p.endsWith(p[0]))
            p = p.mid(1, p.size() - 2);
        else
            p = p.simplified(); // unquoted identifiers: collapse inner whitespace
        if (!p.isEmpty()) out << p;
    }
    return out;
}

// ============================================================================================== gradients

namespace {

bool chbs_angle(QStringView t, float* deg) {
    const QString s = t.toString().toLower();
    struct { const char* u; float k; } units[] = {{"deg", 1.0f}, {"grad", 0.9f}, {"rad", 57.2957795f}, {"turn", 360.0f}};
    for (const auto& u : units) {
        if (s.endsWith(QLatin1String(u.u))) {
            float v = 0;
            if (!chbs_num(QStringView(s).chopped(int(std::strlen(u.u))), &v)) return false;
            *deg = v * u.k;
            return true;
        }
    }
    if (s == QLatin1String("0")) { *deg = 0; return true; }
    return false;
}

/// Position keyword/length → Len (percent of box). isX selects left/right vs top/bottom keywords.
bool chbs_pos_token(const QString& t, bool isX, Len* out) {
    if (t == QLatin1String("center")) { *out = Len{0, 50, Len::Val}; return true; }
    if (isX && t == QLatin1String("left")) { *out = Len{0, 0, Len::Val}; return true; }
    if (isX && t == QLatin1String("right")) { *out = Len{0, 100, Len::Val}; return true; }
    if (!isX && t == QLatin1String("top")) { *out = Len{0, 0, Len::Val}; return true; }
    if (!isX && t == QLatin1String("bottom")) { *out = Len{0, 100, Len::Val}; return true; }
    SpecLen sl;
    if (!parse_css_length(t, &sl)) return false;
    *out = Len{sl.px + sl.em * 16, sl.pct, Len::Val};
    return true;
}

bool chbs_position(const QStringList& toks, Len* x, Len* y) {
    *x = Len{0, 50, Len::Val};
    *y = Len{0, 50, Len::Val};
    if (toks.isEmpty()) return true;
    if (toks.size() == 1) {
        const QString& t = toks[0];
        if (t == QLatin1String("top") || t == QLatin1String("bottom")) return chbs_pos_token(t, false, y);
        return chbs_pos_token(t, true, x);
    }
    QString a = toks[0], b = toks[1];
    // "top left" → swap to x y
    if (a == QLatin1String("top") || a == QLatin1String("bottom") ||
        (b == QLatin1String("left") || b == QLatin1String("right")))
        std::swap(a, b);
    return chbs_pos_token(a, true, x) && chbs_pos_token(b, false, y);
}

bool chbs_stops(const QStringList& parts, int from, std::vector<ColorStop>* stops) {
    for (int i = from; i < parts.size(); ++i) {
        const QStringList t = css_split_ws(parts[i]);
        if (t.isEmpty()) return false;
        ColorStop cs;
        bool cur = false;
        int ci = 0;
        if (!parse_css_color(t[0], &cs.color, &cur)) {
            // "<pos> <color>" order is not valid CSS; a lone length is a transition hint → skip
            if (t.size() == 1) {
                SpecLen hint;
                if (parse_css_length(t[0], &hint)) continue;
            }
            return false;
        }
        ci = 1;
        if (t.size() > ci) {
            SpecLen sl;
            if (!parse_css_length(t[ci], &sl)) return false;
            cs.hasPos = true;
            cs.pos = Len{sl.px + sl.em * 16, sl.pct, Len::Val};
            stops->push_back(cs);
            if (t.size() > ci + 1) { // double-position stop
                SpecLen s2;
                if (!parse_css_length(t[ci + 1], &s2)) return false;
                ColorStop c2 = cs;
                c2.pos = Len{s2.px + s2.em * 16, s2.pct, Len::Val};
                stops->push_back(c2);
            }
            continue;
        }
        stops->push_back(cs);
    }
    return stops->size() >= 2;
}

bool chbs_gradient(QStringView s, Gradient* g) {
    const QString low = s.toString().trimmed();
    const int lp = low.indexOf(QLatin1Char('('));
    if (lp < 0 || !low.endsWith(QLatin1Char(')'))) return false;
    QString fn = low.left(lp).trimmed().toLower();
    if (fn.startsWith(QLatin1String("-webkit-"))) fn = fn.mid(8);
    g->repeating = fn.startsWith(QLatin1String("repeating-"));
    if (g->repeating) fn = fn.mid(10);
    const QStringList parts = css_split_commas(QStringView(low).mid(lp + 1, low.size() - lp - 2));
    if (parts.isEmpty()) return false;
    if (fn == QLatin1String("linear-gradient")) {
        g->type = Gradient::Linear;
        int from = 0;
        const QString first = parts[0].toLower();
        float deg = 0;
        if (first.startsWith(QLatin1String("to "))) {
            int mask = 0;
            for (const QString& w : css_split_ws(first.mid(3))) {
                if (w == QLatin1String("top")) mask |= 1;
                else if (w == QLatin1String("right")) mask |= 2;
                else if (w == QLatin1String("bottom")) mask |= 4;
                else if (w == QLatin1String("left")) mask |= 8;
                else return false;
            }
            if (mask == 1) g->angleDeg = 0;
            else if (mask == 2) g->angleDeg = 90;
            else if (mask == 4) g->angleDeg = 180;
            else if (mask == 8) g->angleDeg = 270;
            else g->toCorner = mask;
            from = 1;
        } else if (chbs_angle(first, &deg)) {
            g->angleDeg = deg;
            from = 1;
        }
        return chbs_stops(parts, from, &g->stops);
    }
    if (fn == QLatin1String("radial-gradient")) {
        g->type = Gradient::Radial;
        g->posX = Len{0, 50, Len::Val};
        g->posY = Len{0, 50, Len::Val};
        int from = 0;
        QColor probe;
        const QStringList t0 = css_split_ws(parts[0].toLower());
        if (!t0.isEmpty() && !parse_css_color(t0[0], &probe)) {
            // [shape] [size] [at position]
            int k = 0;
            QStringList sizeToks;
            while (k < t0.size() && t0[k] != QLatin1String("at")) {
                const QString& w = t0[k];
                if (w == QLatin1String("circle")) g->circle = true;
                else if (w == QLatin1String("ellipse")) g->circle = false;
                else if (w == QLatin1String("closest-side")) g->size = Gradient::ClosestSide;
                else if (w == QLatin1String("closest-corner")) g->size = Gradient::ClosestCorner;
                else if (w == QLatin1String("farthest-side")) g->size = Gradient::FarthestSide;
                else if (w == QLatin1String("farthest-corner")) g->size = Gradient::FarthestCorner;
                else sizeToks << w;
                ++k;
            }
            if (!sizeToks.isEmpty()) {
                SpecLen a, b;
                if (!parse_css_length(sizeToks[0], &a)) return false;
                g->size = Gradient::Explicit;
                g->rx = Len{a.px, a.pct, Len::Val};
                g->ry = g->rx;
                if (sizeToks.size() > 1) {
                    if (!parse_css_length(sizeToks[1], &b)) return false;
                    g->ry = Len{b.px, b.pct, Len::Val};
                } else {
                    g->circle = true;
                }
            }
            if (k < t0.size()) {
                if (!chbs_position(t0.mid(k + 1), &g->posX, &g->posY)) return false;
            }
            from = 1;
        }
        return chbs_stops(parts, from, &g->stops);
    }
    return false;
}

} // namespace

std::shared_ptr<const std::vector<Gradient>> parse_css_gradients(QStringView s) {
    auto v = std::make_shared<std::vector<Gradient>>();
    for (const QString& part : css_split_commas_top_functions(s)) {
        if (part.compare(QLatin1String("none"), Qt::CaseInsensitive) == 0) continue;
        Gradient g;
        if (!chbs_gradient(part, &g)) return nullptr;
        v->push_back(std::move(g));
    }
    return v;
}

// Split "a(...), b(...)" into function calls (commas inside parentheses are kept).
QStringList css_split_commas_top_functions(QStringView s) { return css_split_commas(s); }

// ============================================================================================== shadows

std::shared_ptr<const std::vector<Shadow>> parse_css_shadows(QStringView s) {
    auto v = std::make_shared<std::vector<Shadow>>();
    if (s.trimmed().compare(QLatin1String("none"), Qt::CaseInsensitive) == 0) return v;
    for (const QString& part : css_split_commas(s)) {
        Shadow sh;
        std::vector<float> lens;
        bool haveColor = false;
        for (const QString& t : css_split_ws(part)) {
            if (t.compare(QLatin1String("inset"), Qt::CaseInsensitive) == 0) { sh.inset = true; continue; }
            SpecLen sl;
            if (parse_css_length(t, &sl)) {
                if (sl.pct != 0) return nullptr;
                lens.push_back(sl.px + sl.em * 16);
                continue;
            }
            bool cur = false;
            if (!haveColor && parse_css_color(t, &sh.color, &cur)) {
                sh.currentColor = cur;
                haveColor = true;
                continue;
            }
            return nullptr;
        }
        if (lens.size() < 2 || lens.size() > 4) return nullptr;
        sh.x = lens[0];
        sh.y = lens[1];
        if (lens.size() > 2) sh.blur = std::max(0.0f, lens[2]);
        if (lens.size() > 3) sh.spread = lens[3];
        if (!haveColor) sh.currentColor = true;
        v->push_back(sh);
    }
    return v;
}

// ============================================================================================== grid

namespace {

bool chbs_track_simple(const QString& t, TrackSize* out) {
    const QString s = t.toLower();
    if (s == QLatin1String("auto")) { out->kind = TrackSize::Auto; return true; }
    if (s == QLatin1String("min-content")) { out->kind = TrackSize::MinContent; return true; }
    if (s == QLatin1String("max-content")) { out->kind = TrackSize::MaxContent; return true; }
    if (s.endsWith(QLatin1String("fr"))) {
        float f = 0;
        if (!chbs_num(QStringView(s).chopped(2), &f) || f < 0) return false;
        out->kind = TrackSize::Fr;
        out->fr = f;
        return true;
    }
    if (s.startsWith(QLatin1String("fit-content(")) && s.endsWith(QLatin1Char(')'))) {
        SpecLen sl;
        if (!parse_css_length(QStringView(s).mid(12, s.size() - 13), &sl)) return false;
        out->kind = TrackSize::FitContent;
        out->len = Len{sl.px + sl.em * 16, sl.pct, Len::Val};
        return true;
    }
    if (s.startsWith(QLatin1String("minmax(")) && s.endsWith(QLatin1Char(')'))) {
        const QStringList a = css_split_commas(QStringView(s).mid(7, s.size() - 8));
        if (a.size() != 2) return false;
        auto mn = std::make_shared<TrackSize>(), mx = std::make_shared<TrackSize>();
        if (!chbs_track_simple(a[0], mn.get()) || !chbs_track_simple(a[1], mx.get())) return false;
        if (mn->kind == TrackSize::Fr) return false; // fr not allowed as min
        out->kind = TrackSize::MinMax;
        out->mn = mn;
        out->mx = mx;
        return true;
    }
    SpecLen sl;
    if (!parse_css_length(s, &sl) || sl.kind != SpecLen::Val) return false;
    out->kind = TrackSize::Fixed;
    out->len = Len{sl.px + sl.em * 16 + sl.rem * 16, sl.pct, Len::Val};
    return true;
}

} // namespace

bool parse_css_track_size(QStringView s, TrackSize* out) { return chbs_track_simple(s.toString(), out); }

std::shared_ptr<const TrackList> parse_css_track_list(QStringView s) {
    auto tl = std::make_shared<TrackList>();
    const QString low = s.trimmed().toString().toLower();
    if (low == QLatin1String("none")) return tl;
    tl->none = false;
    bool afterRepeat = false;
    for (const QString& tok : css_split_ws(low)) {
        if (tok.startsWith(QLatin1Char('['))) continue; // line names
        if (tok.startsWith(QLatin1String("repeat(")) && tok.endsWith(QLatin1Char(')'))) {
            const QString inner = tok.mid(7, tok.size() - 8);
            const int c = inner.indexOf(QLatin1Char(','));
            if (c < 0) return nullptr;
            const QString cnt = inner.left(c).trimmed();
            std::vector<TrackSize> pat;
            for (const QString& t : css_split_ws(inner.mid(c + 1))) {
                if (t.startsWith(QLatin1Char('['))) continue;
                TrackSize ts;
                if (!chbs_track_simple(t, &ts)) return nullptr;
                pat.push_back(ts);
            }
            if (pat.empty()) return nullptr;
            if (cnt == QLatin1String("auto-fill") || cnt == QLatin1String("auto-fit")) {
                if (tl->autoRepeat) return nullptr; // only one auto repeat allowed
                tl->autoRepeat = cnt == QLatin1String("auto-fill") ? 1 : 2;
                tl->repeat = pat;
                afterRepeat = true;
                continue;
            }
            bool ok = false;
            const int n = cnt.toInt(&ok);
            if (!ok || n < 1 || n > 1000) return nullptr;
            auto& dst = afterRepeat ? tl->after : tl->before;
            for (int i = 0; i < n; ++i) dst.insert(dst.end(), pat.begin(), pat.end());
            continue;
        }
        TrackSize ts;
        if (!chbs_track_simple(tok, &ts)) return nullptr;
        (afterRepeat ? tl->after : tl->before).push_back(ts);
    }
    if (tl->before.empty() && tl->repeat.empty() && tl->after.empty()) return nullptr;
    return tl;
}

bool parse_css_grid_line(QStringView s, GridLine* out) {
    const QStringList t = css_split_ws(s.trimmed().toString().toLower());
    *out = GridLine{};
    if (t.isEmpty()) return false;
    if (t.size() == 1 && t[0] == QLatin1String("auto")) return true;
    bool span = false;
    int num = 0;
    bool haveNum = false;
    for (const QString& w : t) {
        if (w == QLatin1String("span")) { span = true; continue; }
        bool ok = false;
        const int n = w.toInt(&ok);
        if (!ok || n == 0) return false; // named lines unsupported
        num = n;
        haveNum = true;
    }
    out->isAuto = false;
    if (span) {
        out->span = haveNum ? std::max(1, num) : 1;
        return true;
    }
    if (!haveNum) return false;
    out->line = num;
    return true;
}

// ============================================================================================== transform

bool parse_css_transform(QStringView s, Transform2D* out) {
    *out = Transform2D{};
    const QString low = s.trimmed().toString().toLower();
    if (low == QLatin1String("none")) return true;
    out->none = false;
    int i = 0;
    while (i < low.size()) {
        while (i < low.size() && low[i].isSpace()) ++i;
        if (i >= low.size()) break;
        const int lp = low.indexOf(QLatin1Char('('), i);
        const int rp = low.indexOf(QLatin1Char(')'), lp);
        if (lp < 0 || rp < 0) return false;
        const QString fn = low.mid(i, lp - i).trimmed();
        const QStringList args = css_split_commas(QStringView(low).mid(lp + 1, rp - lp - 1));
        auto lenArg = [&](int k, Len* l) {
            if (k >= args.size()) { *l = Len{}; return true; }
            SpecLen sl;
            if (!parse_css_length(args[k], &sl)) return false;
            l->px += sl.px + sl.em * 16;
            l->pct += sl.pct;
            return true;
        };
        if (fn == QLatin1String("translatex")) { if (!lenArg(0, &out->tx)) return false; }
        else if (fn == QLatin1String("translatey")) { if (!lenArg(0, &out->ty)) return false; }
        else if (fn == QLatin1String("translate")) {
            if (!lenArg(0, &out->tx)) return false;
            if (args.size() > 1 && !lenArg(1, &out->ty)) return false;
        } else if (fn == QLatin1String("rotate")) {
            float d = 0;
            if (args.isEmpty() || !chbs_angle(args[0], &d)) return false;
            out->rotateDeg += d;
        } else if (fn == QLatin1String("scale") || fn == QLatin1String("scalex") || fn == QLatin1String("scaley")) {
            float a = 1, b = 1;
            if (args.isEmpty() || !chbs_num(args[0], &a)) return false;
            b = a;
            if (args.size() > 1 && !chbs_num(args[1], &b)) return false;
            if (fn == QLatin1String("scalex")) b = 1;
            if (fn == QLatin1String("scaley")) { b = a; a = 1; }
            out->sx *= a;
            out->sy *= b;
        } else {
            return false;
        }
        i = rp + 1;
    }
    return true;
}

} // namespace fincept::screens::chb
