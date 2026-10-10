// src/screens/sgi_fa/SgiCommon.h
// Shared helpers for the SGI FA module (tab "sgi_fa") — khung vĩ mô Lê Chí Phúc / SGI Capital
// (skill deep-macro-sgi, module M13): chẩn đoán chu kỳ thanh khoản → chế độ → tỷ trọng tiền mặt.
//
// Colours come from the Lăng Kính theme roles (LkTheme.h, read-only dependency) so the module follows
// the app theme and shares one evidence-tier palette with Lăng Kính:
//   FACT-T1=up · FACT-T2=blue · SS-T3=violet · EST=amber · NEWS=grey · UNVERIFIED/CẦN DATA=down.
// Every data string reaching a rich-text QLabel goes through esc() first. Header-only.
#pragma once

#include "screens/langkinh/LkTheme.h"

#include <QColor>
#include <QFrame>
#include <QHBoxLayout>
#include <QJsonArray>
#include <QJsonObject>
#include <QJsonValue>
#include <QLabel>
#include <QString>
#include <QVBoxLayout>
#include <QWidget>

namespace fincept::screens::sgi {

namespace lk = fincept::screens::langkinh::lkview;
using Role = lk::LkRole;

// ── Colours ──────────────────────────────────────────────────────────────────

inline QColor col(Role r) {
    return lk::lk_col(r);
}
inline QString css(const QColor& c) {
    return lk::lk_qss(c);
}
/// Opaque version of `c` at `alpha` over the card surface — rich text cannot rely on rgba().
inline QColor soft_on_surface(const QColor& c, double alpha = 0.16) {
    QColor t = c;
    t.setAlphaF(static_cast<float>(alpha));
    return lk::lk_over(t, col(Role::Surface));
}

/// Light key from the data ("xanh" | "vang" | "do" | "xam" | anything else) → colour.
inline QColor light_color(const QString& mau) {
    if (mau == QLatin1String("xanh"))
        return col(Role::Up);
    if (mau == QLatin1String("vang"))
        return col(Role::Amber);
    if (mau == QLatin1String("do"))
        return col(Role::Down);
    return col(Role::Muted);
}

/// Condition / threshold status → colour. ĐẠT (condition met) = up; MỘT PHẦN / GẦN ĐỦ = amber;
/// CHƯA = down; CHẠM (a reversal threshold was hit) = blue (an event to act on, neither good nor bad);
/// anything else ([CẦN DATA], "—") = muted.
inline QColor status_color(const QString& st) {
    const QString u = st.trimmed().toUpper();
    if (u == QStringLiteral("ĐẠT"))
        return col(Role::Up);
    if (u == QStringLiteral("MỘT PHẦN") || u == QStringLiteral("GẦN ĐỦ"))
        return col(Role::Amber);
    if (u == QStringLiteral("CHƯA"))
        return col(Role::Down);
    if (u == QStringLiteral("CHẠM"))
        return col(Role::Blue);
    return col(Role::Muted);
}

/// Regime (chế độ §7) → colour.
inline QColor regime_color(const QString& che_do) {
    const QString u = che_do.trimmed().toUpper();
    if (u == QStringLiteral("MỞ RỘNG"))
        return col(Role::Up);
    if (u == QStringLiteral("TÍCH LŨY"))
        return col(Role::Blue);
    if (u == QStringLiteral("HƯNG PHẤN") || u == QStringLiteral("CHUYỂN TIẾP"))
        return col(Role::Amber);
    if (u == QStringLiteral("SIẾT"))
        return col(Role::Down);
    return col(Role::Muted);
}

/// Signed score colour: > 0 up, < 0 down, 0 muted.
inline QColor sign_color(double v) {
    if (v > 0.0)
        return col(Role::Up);
    if (v < 0.0)
        return col(Role::Down);
    return col(Role::Muted);
}

inline QColor tier_color(const QString& tier) {
    return lk::lk_tier(tier);
}

// ── Rich-text fragments (callers escape data; these escape their own text) ───

inline QString esc(const QString& s) {
    return s.toHtmlEscaped();
}

/// `html` (already escaped) wrapped in a colour span.
inline QString span(const QString& html, const QColor& c, bool bold = false) {
    return QStringLiteral("<span style=\"color:%1;%2\">%3</span>")
        .arg(css(c), bold ? QStringLiteral(" font-weight:bold;") : QString(), html);
}

/// Pill: coloured text on a soft opaque background of the same hue. `text` is escaped here.
inline QString pill_html(const QString& text, const QColor& fg, int px = 11) {
    return QStringLiteral("<span style=\"color:%1; background-color:%2; font-size:%3px; font-weight:bold;\">"
                          "&nbsp;%4&nbsp;</span>")
        .arg(css(fg), css(soft_on_surface(fg)), QString::number(px), esc(text));
}

/// Small evidence-tier tag, e.g. "FACT-T1". Empty tier → empty string.
inline QString tier_html(const QString& tier, int px = 10) {
    if (tier.trimmed().isEmpty())
        return {};
    return pill_html(tier.trimmed(), tier_color(tier), px);
}

/// Mono font CSS for numbers (tabular digits).
inline QString mono_css(int px, int weight = 500) {
    return lk::lk_font_css(lk::lk_font_mono(px, weight));
}

// ── JSON helpers ─────────────────────────────────────────────────────────────

inline QString str(const QJsonObject& o, const char* key) {
    const QJsonValue v = o.value(QLatin1String(key));
    if (v.isString())
        return v.toString();
    if (v.isDouble())
        return QString::number(v.toDouble());
    return {};
}

// ── Widgets ──────────────────────────────────────────────────────────────────

/// Plain layout container with a transparent background. A bare QWidget picks up the global QSS
/// `QWidget { background-color: BG_BASE }` and paints a dark strip inside cards; the ID selector keeps
/// the rule off the children (charts, cards).
inline QWidget* make_box(QWidget* parent) {
    auto* w = new QWidget(parent);
    w->setObjectName(QStringLiteral("sgiBox"));
    w->setAttribute(Qt::WA_StyledBackground, true);
    w->setStyleSheet(QStringLiteral("QWidget#sgiBox { background:transparent; }"));
    return w;
}

/// Word-wrapped label. `mono` = tabular digits (numbers); otherwise the sans body font.
inline QLabel* make_label(QWidget* parent, const QColor& color, int px, Qt::TextFormat fmt = Qt::RichText,
                          bool bold = false, bool mono = false) {
    auto* l = new QLabel(parent);
    l->setTextFormat(fmt);
    l->setWordWrap(true);
    l->setTextInteractionFlags(Qt::TextSelectableByMouse);
    const QFont f = mono ? lk::lk_font_mono(px, bold ? 600 : 400) : lk::lk_font_sans(px, bold ? 600 : 400);
    l->setStyleSheet(
        QStringLiteral("QLabel { color:%1; %2 background:transparent; }").arg(css(color), lk::lk_font_css(f)));
    return l;
}

/// Card frame (surface + 1px line, optional 3px coloured left edge). `lay` receives the inner layout.
inline QFrame* make_card(QWidget* parent, QVBoxLayout*& lay, const QColor& accent_left = QColor()) {
    auto* card = new QFrame(parent);
    card->setObjectName(QStringLiteral("sgiCard"));
    card->setAttribute(Qt::WA_StyledBackground, true);
    const QString left = accent_left.isValid() ? QStringLiteral(" border-left:3px solid %1;").arg(css(accent_left))
                                               : QString();
    card->setStyleSheet(QStringLiteral("QFrame#sgiCard { background:%1; border:1px solid %2;%3 border-radius:4px; }")
                            .arg(css(col(Role::Surface)), css(col(Role::Line)), left));
    lay = new QVBoxLayout(card);
    lay->setContentsMargins(14, 12, 14, 12);
    lay->setSpacing(6);
    return card;
}

/// Section shell: "<num>  <title>" header over a rule, optional lede paragraph, then `body` for content.
/// Returns the section widget (transparent background).
inline QWidget* make_section(QWidget* parent, const QString& num, const QString& title, const QString& lede,
                             QVBoxLayout*& body) {
    auto* sec = make_box(parent);
    auto* vl = new QVBoxLayout(sec);
    vl->setContentsMargins(0, 14, 0, 0);
    vl->setSpacing(8);

    auto* head = new QWidget(sec);
    head->setObjectName(QStringLiteral("sgiSecHead"));
    head->setAttribute(Qt::WA_StyledBackground, true);
    head->setStyleSheet(
        QStringLiteral("QWidget#sgiSecHead { border-bottom:1px solid %1; background:transparent; }").arg(css(col(Role::Line2))));
    auto* hl = new QHBoxLayout(head);
    hl->setContentsMargins(0, 0, 0, 6);
    hl->setSpacing(10);
    if (!num.isEmpty()) {
        auto* n = make_label(head, col(Role::Amber), 12, Qt::PlainText, true, true);
        n->setWordWrap(false);
        n->setText(num);
        hl->addWidget(n, 0, Qt::AlignBottom);
    }
    auto* t = new QLabel(head);
    t->setTextFormat(Qt::PlainText);
    t->setText(title);
    t->setWordWrap(true);
    t->setStyleSheet(QStringLiteral("QLabel { color:%1; %2 background:transparent; }")
                         .arg(css(col(Role::Ink)), lk::lk_font_css(lk::lk_font_serif(19, 600))));
    hl->addWidget(t, 1, Qt::AlignBottom);
    vl->addWidget(head);

    if (!lede.trimmed().isEmpty()) {
        auto* l = make_label(sec, col(Role::Ink2), 13, Qt::PlainText);
        l->setText(lede);
        vl->addWidget(l);
    }
    body = vl;
    return sec;
}

} // namespace fincept::screens::sgi
