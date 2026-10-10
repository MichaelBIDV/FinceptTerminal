// src/screens/deepfa/DeepFaCommon.h
// Shared helpers for the DEEP FA module (tab "deepfa") — HĐCV Deep FA research desk: the 8-section
// PM memo (BaoCao_VN30) re-read against today's signal layers (EDI · BLĐ ⚔ street ⚔ AI-news ⚔ fund
// intent qua GATE LVF ⚔ dòng tiền Vietcap IQ), falsifiable §7 conditions as a dated checklist, and
// provenance (file · data date · evidence tier) on every number.
//
// Colours come from the Lăng Kính theme roles (LkTheme.h, read-only dependency, same as the SGI FA
// module) so the three VN modules share one evidence-tier palette:
//   FACT-T1=up · FACT-T2=blue · SS-T3=violet · EST=amber · NEWS=grey · UNVERIFIED/CẦN DATA=down.
// Nothing here recomputes a number: values arrive pre-formatted from scripts/deepfa.py ("*_txt").
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

namespace fincept::screens::deepfa {

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

inline QColor tier_color(const QString& tier) {
    return lk::lk_tier(tier);
}

/// Memo State A/B/C/D (codex 7 tầng): A=up (thesis xác nhận), B=blue (variant sống), C=amber
/// (kill/veto, không mua), D=down (tránh); anything else muted.
inline QColor state_color(const QString& state) {
    const QString u = state.trimmed().toUpper();
    if (u == QLatin1String("A"))
        return col(Role::Up);
    if (u == QLatin1String("B"))
        return col(Role::Blue);
    if (u == QLatin1String("C"))
        return col(Role::Amber);
    if (u == QLatin1String("D"))
        return col(Role::Down);
    return col(Role::Muted);
}

/// Freshness light of a data layer: "ok"=up, "warn"=amber, "stale"/"missing"=down.
inline QColor status_color(const QString& st) {
    const QString u = st.trimmed().toLower();
    if (u == QLatin1String("ok"))
        return col(Role::Up);
    if (u == QLatin1String("warn"))
        return col(Role::Amber);
    if (u == QLatin1String("stale") || u == QLatin1String("missing"))
        return col(Role::Down);
    return col(Role::Muted);
}

/// Direction of a vote stream / delta: +1 up, −1 down, 0 muted (null → muted too).
inline QColor dir_color(const QJsonValue& v) {
    if (!v.isDouble())
        return col(Role::Muted);
    const double d = v.toDouble();
    if (d > 0.0)
        return col(Role::Up);
    if (d < 0.0)
        return col(Role::Down);
    return col(Role::Muted);
}

/// Condition status (§7 checklist): "dat"=up, "gay"=down, "den_han"/"qua_han"=amber, else muted.
inline QColor cond_color(const QString& st) {
    const QString u = st.trimmed().toLower();
    if (u == QLatin1String("dat") || u == QLatin1String("dung"))
        return col(Role::Up);
    if (u == QLatin1String("gay") || u == QLatin1String("vi_pham"))
        return col(Role::Down);
    if (u == QLatin1String("den_han") || u == QLatin1String("qua_han") || u == QLatin1String("sap_den_han"))
        return col(Role::Amber);
    return col(Role::Muted);
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

/// Provenance tail "· t · n" for a number object {v,u,t,b,n,g,txt}: tier pill + data date + source.
/// Always visible on screen — a number without file·date·tier must not exist in this module.
inline QString prov_html(const QJsonObject& num, int px = 10) {
    QString out = tier_html(num.value(QLatin1String("b")).toString(), px);
    const QString t = num.value(QLatin1String("t")).toString().trimmed();
    const QString n = num.value(QLatin1String("n")).toString().trimmed();
    QString tail;
    if (!t.isEmpty())
        tail += esc(t);
    if (!n.isEmpty())
        tail += (tail.isEmpty() ? QString() : QStringLiteral(" · ")) + esc(n);
    if (!tail.isEmpty())
        out += QStringLiteral(" <span style=\"color:%1; font-size:%2px;\">%3</span>")
                   .arg(css(col(Role::Muted)), QString::number(px), tail);
    return out;
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

/// Display text of a number object: its pre-formatted "txt", else "[CẦN DATA]".
inline QString num_txt(const QJsonObject& num) {
    const QString t = num.value(QLatin1String("txt")).toString().trimmed();
    return t.isEmpty() ? QStringLiteral("[CẦN DATA]") : t;
}

inline QString or_need(const QString& s) {
    return s.trimmed().isEmpty() ? QStringLiteral("[CẦN DATA]") : s;
}

// ── Widgets ──────────────────────────────────────────────────────────────────

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

/// Muted "[CẦN DATA] what" line — gaps stay visible, never hidden.
inline QLabel* make_need(QWidget* parent, const QString& what) {
    auto* l = make_label(parent, col(Role::Muted), 12, Qt::PlainText);
    l->setText(QStringLiteral("[CẦN DATA] ") + what);
    return l;
}

/// Card frame (surface + 1px line, optional 3px coloured left edge). `lay` receives the inner layout.
inline QFrame* make_card(QWidget* parent, QVBoxLayout*& lay, const QColor& accent_left = QColor()) {
    auto* card = new QFrame(parent);
    card->setObjectName(QStringLiteral("deepfaCard"));
    card->setAttribute(Qt::WA_StyledBackground, true);
    const QString left = accent_left.isValid() ? QStringLiteral(" border-left:3px solid %1;").arg(css(accent_left))
                                               : QString();
    card->setStyleSheet(
        QStringLiteral("QFrame#deepfaCard { background:%1; border:1px solid %2;%3 border-radius:4px; }")
            .arg(css(col(Role::Surface)), css(col(Role::Line)), left));
    lay = new QVBoxLayout(card);
    lay->setContentsMargins(14, 12, 14, 12);
    lay->setSpacing(6);
    return card;
}

/// Section shell: "<num>  <title>" header over a rule, optional lede paragraph, then `body` for
/// content. Returns the section widget (transparent background).
inline QWidget* make_section(QWidget* parent, const QString& num, const QString& title, const QString& lede,
                             QVBoxLayout*& body) {
    auto* sec = new QWidget(parent);
    auto* vl = new QVBoxLayout(sec);
    vl->setContentsMargins(0, 14, 0, 0);
    vl->setSpacing(8);

    auto* head = new QWidget(sec);
    head->setObjectName(QStringLiteral("deepfaSecHead"));
    head->setAttribute(Qt::WA_StyledBackground, true);
    head->setStyleSheet(QStringLiteral("QWidget#deepfaSecHead { border-bottom:1px solid %1; background:transparent; }")
                            .arg(css(col(Role::Line2))));
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

} // namespace fincept::screens::deepfa
