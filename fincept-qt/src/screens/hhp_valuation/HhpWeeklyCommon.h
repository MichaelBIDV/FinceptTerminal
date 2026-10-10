// src/screens/hhp_valuation/HhpWeeklyCommon.h
// Shared helpers for the BẢN TUẦN view of the HHP module (weekly issue "Ba chiếc đồng hồ…").
// The payload comes from scripts/hhp_weekly.py `weekly` (contract: that script's docstring).
//
// Rich text: every string the payload marks "ihtml" is converted by rich() below, which lets
// through ONLY the tags the contract allows (b, i, br, span with one whitelisted class) and
// escapes anything else — so a malformed or hostile issue file cannot inject markup. Plain
// strings go through esc(). Palette = the HHP module palette (HhpCommon.h) plus the page's two
// extreme-zone hues (floor = ≤−2σ, ceil = ≥+2σ). Header-only.
#pragma once

#include "screens/hhp_valuation/HhpCommon.h"

#include <QColor>
#include <QFrame>
#include <QJsonArray>
#include <QJsonObject>
#include <QJsonValue>
#include <QLabel>
#include <QRegularExpression>
#include <QString>
#include <QStringList>
#include <QVBoxLayout>
#include <QVector>
#include <QWidget>

#include <algorithm>
#include <cmath>
#include <utility>

namespace fincept::screens::hhp::weekly {

// ── Palette ──────────────────────────────────────────────────────────────────

inline QColor c_ink2() { return QColor(0xb8, 0xbd, 0xc6); }   // secondary text (--ink-2)
inline QColor c_card2() { return QColor(0x1b, 0x1f, 0x26); }  // inner surface (--surface-2)
inline QColor c_floor() { return QColor(0x5c, 0xc0, 0xdd); }  // ≤ −2σ (rẻ cực đoan)
inline QColor c_ceil() { return QColor(0xbd, 0x8c, 0xe0); }   // ≥ +2σ (đắt cực đoan)

/// Opaque `c` at `alpha` over the card surface (rich text cannot rely on rgba()).
inline QColor soft(const QColor& c, double alpha = 0.18) {
    const QColor b = c_card();
    const auto mix = [alpha](int fg, int bg) { return static_cast<int>(std::lround(fg * alpha + bg * (1.0 - alpha))); };
    return QColor(mix(c.red(), b.red()), mix(c.green(), b.green()), mix(c.blue(), b.blue()));
}

/// TONE (contract) → colour. Unknown / empty → `fallback`.
inline QColor tone_color(const QString& tone, const QColor& fallback = c_text()) {
    if (tone == QLatin1String("up"))
        return c_cheap();
    if (tone == QLatin1String("down"))
        return c_rich();
    if (tone == QLatin1String("ref"))
        return c_gold();
    if (tone == QLatin1String("muted"))
        return c_muted();
    if (tone == QLatin1String("ink2"))
        return c_ink2();
    if (tone == QLatin1String("floor"))
        return c_floor();
    if (tone == QLatin1String("ceil"))
        return c_ceil();
    return fallback;
}

/// σ → zone colour of the page (≤−2 floor, ≤−1 up, ≥+2 ceil, ≥+1 down, else muted). NaN → muted.
inline QColor sigma_color(double s) {
    if (!has(s))
        return c_muted();
    if (s <= -2.0)
        return c_floor();
    if (s <= -1.0)
        return c_cheap();
    if (s >= 2.0)
        return c_ceil();
    if (s >= 1.0)
        return c_rich();
    return c_muted();
}

/// Vietnamese decimal: 2 decimals, comma, minus "−", explicit "+" when `sign`. NaN → "—".
inline QString fmt_dec(double v, int decimals = 2, bool sign = false) {
    if (!has(v))
        return QStringLiteral("—");
    QString s = QString::number(std::fabs(v), 'f', decimals).replace(QLatin1Char('.'), QLatin1Char(','));
    if (v < 0 && s != QString::number(0.0, 'f', decimals).replace(QLatin1Char('.'), QLatin1Char(',')))
        return QStringLiteral("−") + s;
    return (sign && v > 0 ? QStringLiteral("+") : QString()) + s;
}

inline QString esc(const QString& s) {
    return s.toHtmlEscaped();
}

// ── ihtml → Qt rich text ─────────────────────────────────────────────────────

namespace detail {

struct SpanStyle {
    QString css;
    bool pill = false; ///< padded with &nbsp; on both sides
};

inline SpanStyle span_style(const QString& cls, int px) {
    const QString mono = QStringLiteral("font-family:'Menlo','Monaco','Courier New',monospace;");
    const auto pill = [&](const QColor& fg, const QColor& bg) {
        return SpanStyle{QStringLiteral("color:%1; background-color:%2; font-weight:bold; font-size:%3px; %4")
                             .arg(css(fg), css(bg), QString::number(std::max(9, px - 2)), mono),
                         true};
    };
    if (cls == QLatin1String("z-floor"))
        return pill(c_floor(), soft(c_floor()));
    if (cls == QLatin1String("z-up"))
        return pill(c_cheap(), soft(c_cheap()));
    if (cls == QLatin1String("z-down"))
        return pill(c_rich(), soft(c_rich()));
    if (cls == QLatin1String("z-ceil"))
        return pill(c_ceil(), soft(c_ceil()));
    if (cls == QLatin1String("z-ref"))
        return pill(c_muted(), c_card2());
    if (cls == QLatin1String("v-add"))
        return pill(c_cheap(), soft(c_cheap()));
    if (cls == QLatin1String("v-trim"))
        return pill(c_rich(), soft(c_rich()));
    if (cls == QLatin1String("v-hold"))
        return pill(c_ink2(), c_card2());
    if (cls == QLatin1String("tag"))
        return SpanStyle{QStringLiteral("color:%1; background-color:%2; font-size:%3px; %4")
                             .arg(css(c_muted()), css(c_card2()), QString::number(std::max(9, px - 3)), mono),
                         true};
    if (cls == QLatin1String("tag-f"))
        return SpanStyle{QStringLiteral("color:%1; background-color:%2; font-size:%3px; %4")
                             .arg(css(c_gold()), css(soft(c_gold(), 0.12)), QString::number(std::max(9, px - 3)), mono),
                         true};
    if (cls == QLatin1String("tag-p"))
        return SpanStyle{QStringLiteral("color:%1; background-color:%2; font-weight:bold; font-size:%3px; %4")
                             .arg(css(c_ink2()), css(c_card2()), QString::number(std::max(9, px - 3)), mono),
                         true};
    if (cls == QLatin1String("num"))
        return SpanStyle{mono, false};
    if (cls == QLatin1String("tk"))
        return SpanStyle{QStringLiteral("font-weight:bold; ") + mono, false};
    if (cls == QLatin1String("sub"))
        return SpanStyle{QStringLiteral("color:%1; font-size:%2px; font-weight:normal;")
                             .arg(css(c_muted()), QString::number(std::max(9, px - 2))),
                         false};
    if (cls == QLatin1String("hl"))
        return SpanStyle{QStringLiteral("background-color:%1;").arg(css(soft(c_gold(), 0.22))), false};
    if (cls.startsWith(QLatin1String("c-")))
        return SpanStyle{QStringLiteral("color:%1;").arg(css(tone_color(cls.mid(2), c_text()))), false};
    return SpanStyle{};
}

/// Text between tags: already escaped by the script; re-escape stray angle brackets defensively.
inline QString safe_text(const QString& t) {
    QString out = t;
    out.replace(QLatin1Char('<'), QStringLiteral("&lt;")).replace(QLatin1Char('>'), QStringLiteral("&gt;"));
    return out;
}

} // namespace detail

/// Converts contract ihtml to Qt rich text. Only b/i/br/span.K pass; anything else is escaped.
/// Unbalanced closing tags are dropped; unclosed spans are closed at the end. `px` = base font px
/// (pills and tags scale from it).
inline QString rich(const QString& ihtml, int px = 13) {
    static const QRegularExpression tag_re(QStringLiteral("<(/?)(b|i|br|span)(?: class=\"([a-z0-9-]+)\")?\\s*/?>"));
    QString out;
    out.reserve(ihtml.size() + ihtml.size() / 2);
    QVector<std::pair<QString, bool>> stack; // (tag, pill) of open elements
    qsizetype pos = 0;
    auto it = tag_re.globalMatch(ihtml);
    while (it.hasNext()) {
        const QRegularExpressionMatch m = it.next();
        out += detail::safe_text(ihtml.mid(pos, m.capturedStart() - pos));
        pos = m.capturedEnd();
        const bool closing = !m.captured(1).isEmpty();
        const QString tag = m.captured(2);
        if (tag == QLatin1String("br")) {
            out += QStringLiteral("<br>");
            continue;
        }
        if (!closing) {
            if (tag == QLatin1String("span")) {
                const detail::SpanStyle st = detail::span_style(m.captured(3), px);
                out += QStringLiteral("<span style=\"%1\">").arg(st.css);
                if (st.pill)
                    out += QStringLiteral("&nbsp;");
                stack.append({tag, st.pill});
            } else {
                out += QLatin1Char('<') + tag + QLatin1Char('>');
                stack.append({tag, false});
            }
            continue;
        }
        // closing: must match the innermost open element of that name, else dropped
        if (!stack.isEmpty() && stack.last().first == tag) {
            if (stack.last().second)
                out += QStringLiteral("&nbsp;");
            out += QStringLiteral("</") + tag + QLatin1Char('>');
            stack.removeLast();
        }
    }
    out += detail::safe_text(ihtml.mid(pos));
    while (!stack.isEmpty()) {
        if (stack.last().second)
            out += QStringLiteral("&nbsp;");
        out += QStringLiteral("</") + stack.last().first + QLatin1Char('>');
        stack.removeLast();
    }
    return out;
}

// ── Widget factories (all colours read at call time; the page is rebuilt per payload) ──

/// Word-wrapped rich-text label; `html` must already be Qt rich text (use rich()/esc()).
inline QLabel* wlabel(QWidget* parent, const QString& html, int px = 13, const QColor& color = c_text(),
                      bool bold = false) {
    auto* l = new QLabel(parent);
    l->setTextFormat(Qt::RichText);
    l->setWordWrap(true);
    l->setTextInteractionFlags(Qt::TextSelectableByMouse);
    l->setStyleSheet(QStringLiteral("QLabel { color:%1; font-size:%2px; font-weight:%3; background:transparent; }")
                         .arg(css(color), QString::number(px), bold ? QStringLiteral("bold") : QStringLiteral("normal")));
    l->setText(html);
    return l;
}

/// Card frame: HHP card surface; optional 3px left border (`left_tone`) or 2px outline
/// (`outline_tone`) in a TONE colour. `layout` receives the card's QVBoxLayout.
inline QFrame* wcard(QWidget* parent, QVBoxLayout*& layout, const QString& left_tone = {},
                     const QString& outline_tone = {}, int margin = 14) {
    static int s_seq = 0;
    auto* card = new QFrame(parent);
    const QString name = QStringLiteral("hhpwCard%1").arg(++s_seq);
    card->setObjectName(name);
    QString border = QStringLiteral("border:1px solid %1;").arg(css(c_line()));
    if (!outline_tone.isEmpty())
        border = QStringLiteral("border:2px solid %1;").arg(css(tone_color(outline_tone, c_line())));
    else if (!left_tone.isEmpty())
        border += QStringLiteral(" border-left:3px solid %1;").arg(css(tone_color(left_tone, c_line())));
    card->setStyleSheet(QStringLiteral("QFrame#%1 { background:%2; %3 border-radius:10px; }")
                            .arg(name, css(c_card()), border));
    layout = new QVBoxLayout(card);
    layout->setContentsMargins(margin, margin - 2, margin, margin - 2);
    layout->setSpacing(6);
    return card;
}

/// JSON array of strings → QStringList (non-strings skipped).
inline QStringList str_list(const QJsonValue& v) {
    QStringList out;
    for (const QJsonValue& x : v.toArray())
        if (x.isString())
            out.append(x.toString());
    return out;
}

} // namespace fincept::screens::hhp::weekly
