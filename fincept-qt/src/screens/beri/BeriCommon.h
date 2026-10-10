// src/screens/beri/BeriCommon.h
// Shared helpers for the BERI module (tab "beri") — Hội đồng Cố vấn AI của Viện Nghiên cứu Kinh tế BIDV.
//
// Surfaces, lines and ink come from the Lăng Kính theme roles (LkTheme.h, read-only dependency) so the
// page follows the app theme. The accents are BERI's own (teal #00726E · gold #8F6C0E · crit #9C2B2B,
// as in the "BERI · Advisory Council v2.0" artifact), pulled toward the ink colour until legible on
// the card surface.
//
// Evidence tiers here are BERI's scale — [T0] văn bản pháp lý … [T4] bên thứ ba, [EST], [CẦN DATA]
// (Hiến chương §1.1). They are NOT the securities scale (FACT-T1 … UNVERIFIED) that lk_tier() colours;
// the two systems are never mixed, so this header never calls lk_tier(). Every data string reaching a
// rich-text QLabel goes through esc() first. Header-only.
#pragma once

#include "screens/langkinh/LkTheme.h"

#include <QColor>
#include <QFrame>
#include <QHBoxLayout>
#include <QJsonArray>
#include <QJsonObject>
#include <QJsonValue>
#include <QLabel>
#include <QList>
#include <QSizePolicy>
#include <QString>
#include <QStringList>
#include <QVBoxLayout>
#include <QWidget>

namespace fincept::screens::beri {

namespace lk = fincept::screens::langkinh::lkview;
using Role = lk::LkRole;

// ── Colours ──────────────────────────────────────────────────────────────────

inline QColor col(Role r) {
    return lk::lk_col(r);
}
inline QString css(const QColor& c) {
    return lk::lk_qss(c);
}
/// A BERI accent made legible on the card surface of the current theme.
inline QColor brand(const char* hex) {
    return lk::lk_legible(QColor(hex), col(Role::Surface), col(Role::Ink));
}
inline QColor teal() {
    return brand("#00726E");
}
inline QColor gold() {
    return brand("#8F6C0E");
}
inline QColor crit() {
    return brand("#9C2B2B");
}
/// Opaque version of `c` at `alpha` over the card surface — rich text cannot rely on rgba().
inline QColor soft(const QColor& c, double alpha = 0.16) {
    QColor t = c;
    t.setAlphaF(static_cast<float>(alpha));
    return lk::lk_over(t, col(Role::Surface));
}

/// Deadline level from the engine ("crit" ≤ 7 days · "warn" ≤ 21 · "ok" · "na" no date) → colour.
inline QColor level_color(const QString& muc) {
    if (muc == QLatin1String("crit"))
        return crit();
    if (muc == QLatin1String("warn"))
        return gold();
    if (muc == QLatin1String("ok"))
        return teal();
    return col(Role::Muted);
}

/// BERI evidence tier ("[T1]", "T1", "theo nguồn gốc", …) → colour. Unknown → muted.
inline QColor tier_color(const QString& tag) {
    const QString t = tag.trimmed().toUpper();
    if (t.contains(QStringLiteral("CẦN DATA")))
        return crit();
    if (t.contains(QStringLiteral("EST")))
        return col(Role::Amber);
    if (t.contains(QStringLiteral("T0")))
        return teal();
    if (t.contains(QStringLiteral("T1")))
        return col(Role::Blue);
    if (t.contains(QStringLiteral("T2")))
        return col(Role::Violet);
    if (t.contains(QStringLiteral("T3")))
        return col(Role::Grey);
    if (t.contains(QStringLiteral("T4")))
        return gold();
    return col(Role::Muted);
}

/// Source-registry status key (songuon_registry.json) → colour.
inline QColor source_status_color(const QString& st) {
    if (st == QLatin1String("song"))
        return teal();
    if (st == QLatin1String("thu_cong"))
        return col(Role::Blue);
    if (st == QLatin1String("chap_chon"))
        return gold();
    if (st == QLatin1String("chua_co") || st == QLatin1String("chan"))
        return crit();
    return col(Role::Muted);
}

// ── Rich-text fragments (callers escape data; these escape their own text) ───

inline QString esc(const QString& s) {
    return s.toHtmlEscaped();
}

/// `html` (already escaped) wrapped in a colour span. Single-quoted style: font CSS carries double quotes.
inline QString span(const QString& html, const QColor& c, bool bold = false) {
    return QStringLiteral("<span style='color:%1;%2'>%3</span>")
        .arg(css(c), bold ? QStringLiteral(" font-weight:600;") : QString(), html);
}

/// Pill: coloured text on a soft opaque background of the same hue. `text` is escaped here.
inline QString pill(const QString& text, const QColor& fg, int px = 11) {
    return QStringLiteral("<span style='color:%1; background-color:%2; font-size:%3px; font-weight:600;'>"
                          "&nbsp;%4&nbsp;</span>")
        .arg(css(fg), css(soft(fg)), QString::number(px), esc(text));
}

inline QString mono(const QString& html, int px, const QColor& c, int weight = 500) {
    return QStringLiteral("<span style='color:%1; %2'>%3</span>")
        .arg(css(c), lk::lk_font_css(lk::lk_font_mono(px, weight)), html);
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

/// Integer field, or `fallback` when absent / null.
inline int num(const QJsonObject& o, const char* key, int fallback = -1) {
    const QJsonValue v = o.value(QLatin1String(key));
    return v.isDouble() ? v.toInt() : fallback;
}

// ── Widgets ──────────────────────────────────────────────────────────────────

/// Plain layout container with a transparent background (a bare QWidget picks up the global QSS
/// background and paints a dark strip inside cards; the ID selector keeps the rule off the children).
inline QWidget* make_box(QWidget* parent) {
    auto* w = new QWidget(parent);
    w->setObjectName(QStringLiteral("beriBox"));
    w->setAttribute(Qt::WA_StyledBackground, true);
    w->setStyleSheet(QStringLiteral("QWidget#beriBox { background:transparent; }"));
    return w;
}

/// Word-wrapped, selectable label in the sans (or mono) body font.
inline QLabel* make_label(QWidget* parent, const QColor& color, int px, Qt::TextFormat fmt = Qt::RichText,
                          bool bold = false, bool is_mono = false) {
    auto* l = new QLabel(parent);
    l->setTextFormat(fmt);
    l->setWordWrap(true);
    l->setTextInteractionFlags(Qt::TextSelectableByMouse);
    const QFont f = is_mono ? lk::lk_font_mono(px, bold ? 600 : 400) : lk::lk_font_sans(px, bold ? 600 : 400);
    l->setStyleSheet(
        QStringLiteral("QLabel { color:%1; %2 background:transparent; }").arg(css(color), lk::lk_font_css(f)));
    return l;
}

inline QLabel* plain(QWidget* parent, const QColor& c, int px, const QString& text, bool bold = false) {
    auto* l = make_label(parent, c, px, Qt::PlainText, bold);
    l->setText(text);
    return l;
}

inline QLabel* rich(QWidget* parent, const QColor& c, int px, const QString& html) {
    auto* l = make_label(parent, c, px, Qt::RichText);
    l->setText(html);
    return l;
}

/// Muted "[CẦN DATA] what" line — gaps stay visible, never hidden.
inline QLabel* need(QWidget* parent, const QString& what) {
    return plain(parent, col(Role::Muted), 12, QStringLiteral("[CẦN DATA] ") + what);
}

/// Card frame (surface + 1px line, optional 3px coloured left edge). `lay` receives the inner layout.
inline QFrame* make_card(QWidget* parent, QVBoxLayout*& lay, const QColor& accent_left = QColor()) {
    auto* card = new QFrame(parent);
    card->setObjectName(QStringLiteral("beriCard"));
    card->setAttribute(Qt::WA_StyledBackground, true);
    const QString left = accent_left.isValid() ? QStringLiteral(" border-left:3px solid %1;").arg(css(accent_left))
                                               : QString();
    card->setStyleSheet(QStringLiteral("QFrame#beriCard { background:%1; border:1px solid %2;%3 border-radius:4px; }")
                            .arg(css(col(Role::Surface)), css(col(Role::Line)), left));
    lay = new QVBoxLayout(card);
    lay->setContentsMargins(14, 12, 14, 12);
    lay->setSpacing(6);
    return card;
}

/// Section shell: "<num>  <title>" header over a rule, optional lede, then `body` for the content.
inline QWidget* make_section(QWidget* parent, const QString& num, const QString& title, const QString& lede,
                             QVBoxLayout*& body) {
    auto* sec = make_box(parent);
    auto* vl = new QVBoxLayout(sec);
    vl->setContentsMargins(0, 16, 0, 0);
    vl->setSpacing(8);

    auto* head = new QWidget(sec);
    head->setObjectName(QStringLiteral("beriSecHead"));
    head->setAttribute(Qt::WA_StyledBackground, true);
    head->setStyleSheet(QStringLiteral("QWidget#beriSecHead { border-bottom:1px solid %1; background:transparent; }")
                            .arg(css(col(Role::Line2))));
    auto* hl = new QHBoxLayout(head);
    hl->setContentsMargins(0, 0, 0, 6);
    hl->setSpacing(10);
    if (!num.isEmpty()) {
        auto* n = make_label(head, teal(), 12, Qt::PlainText, true, true);
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

    if (!lede.trimmed().isEmpty())
        vl->addWidget(plain(sec, col(Role::Ink2), 13, lede));
    body = vl;
    return sec;
}

/// Table card: an uppercase muted header row, then one row per entry; every cell is already-escaped
/// rich text. `stretch[i]` is the column's share of the width (missing = 1). Rows are separated by a
/// hairline. Empty `rows` → a single "[CẦN DATA] empty_what" line instead of a bare header.
inline QFrame* make_table(QWidget* parent, const QStringList& headers, const QList<QStringList>& rows,
                          const QList<int>& stretch, const QString& empty_what, int px = 12) {
    QVBoxLayout* lay = nullptr;
    QFrame* card = make_card(parent, lay);
    lay->setSpacing(0);
    if (rows.isEmpty()) {
        lay->addWidget(need(card, empty_what));
        return card;
    }
    const auto add_row = [&](const QStringList& cells, bool header, bool last) {
        auto* row = new QWidget(card);
        row->setObjectName(QStringLiteral("beriRow"));
        row->setAttribute(Qt::WA_StyledBackground, true);
        row->setStyleSheet(QStringLiteral("QWidget#beriRow { background:transparent; border-bottom:%1; }")
                               .arg(last ? QStringLiteral("none")
                                         : QStringLiteral("1px solid %1").arg(css(col(header ? Role::Line2 : Role::Line)))));
        auto* hl = new QHBoxLayout(row);
        hl->setContentsMargins(0, header ? 0 : 5, 0, 5);
        hl->setSpacing(12);
        for (int i = 0; i < headers.size(); ++i) {
            QLabel* l = header ? make_label(row, col(Role::Muted), 10, Qt::PlainText, true)
                               : make_label(row, col(Role::Ink2), px, Qt::RichText);
            l->setText(i < cells.size() ? (header ? cells.at(i).toUpper() : cells.at(i)) : QString());
            l->setAlignment(Qt::AlignLeft | Qt::AlignTop);
            // Ignored horizontal policy: columns take their stretch share, text wraps inside it.
            l->setSizePolicy(QSizePolicy::Ignored, QSizePolicy::Preferred);
            hl->addWidget(l, i < stretch.size() ? stretch.at(i) : 1);
        }
        lay->addWidget(row);
    };
    add_row(headers, true, false);
    for (int r = 0; r < rows.size(); ++r)
        add_row(rows.at(r), false, r == rows.size() - 1);
    return card;
}

} // namespace fincept::screens::beri
