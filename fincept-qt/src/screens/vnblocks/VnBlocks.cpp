// src/screens/vnblocks/VnBlocks.cpp
// Generic "vnblocks/1" page renderer (contract in VnBlocks.h) for the tabs whose Python script shapes the
// whole page (msn_reflex, so_nguon). Look = SGI FA: serif section titles, mono tabular numbers, thin
// rules, cards with a 3px coloured left edge, pills for status and evidence tier (SgiCommon.h helpers).
//
// Layout only: values arrive pre-formatted from the script; a bare JSON number gets the Vietnamese number
// format (decimal comma, thousands dot, U+2212 minus). Nothing is computed here; an empty value renders
// as a red "[CẦN DATA]" so the gap stays visible. Every data string reaching a rich-text label goes
// through vb_html() (esc + line breaks); plain-text labels take data verbatim.
//
// Tables are QGridLayout-of-QLabel grids (word-wrapped cells, the page scrolls as one). Charts reuse
// langkinh::LkLineChart exactly as SgiSectionsBottom does (fixed height, text note when !has_data()).
// Private helpers live in an anonymous namespace with a "vb_" prefix (unity-build safety).
#include "screens/vnblocks/VnBlocks.h"
#include "screens/vnblocks/VnChartsExt.h"

#include "screens/langkinh/LkChart.h"
#include "screens/sgi_fa/SgiCommon.h"

#include <QFontMetrics>
#include <QFrame>
#include <QGridLayout>
#include <QHBoxLayout>
#include <QJsonValue>
#include <QLabel>
#include <QList>
#include <QSet>
#include <QStringList>
#include <QVBoxLayout>

#include <algorithm>
#include <cmath>

namespace fincept::screens::vnblocks {

namespace {

using namespace fincept::screens::sgi;

constexpr int kVbChartH = 300;    ///< default figure height ("cao" overrides)
constexpr int kVbChartMinH = 220; ///< clamp for "cao" so a bad value cannot collapse or flood the page
constexpr int kVbChartMaxH = 900;
constexpr int kVbTileCols = 4;
constexpr int kVbCardCols = 3;
constexpr int kVbMaxCols = 6;
constexpr int kVbStretchMin = 4; ///< table column stretch = longest text, clamped to [min, max]
constexpr int kVbStretchMax = 40;
constexpr int kVbNoWrapChars = 10; ///< columns whose longest cell is this short never wrap
constexpr int kVbCellPadX = 16;    ///< horizontal padding of a table cell (vb_cell_css: 8px each side)
const QString kVbNeed = QStringLiteral("[CẦN DATA]");

// ── Text ─────────────────────────────────────────────────────────────────────

/// Vietnamese number: decimal comma, thousands dot, U+2212 minus, trailing zeros trimmed.
QString vb_fmt(double v, int dec = 2) {
    if (!std::isfinite(v))
        return {};
    QString s = QString::number(std::abs(v), 'f', dec);
    if (s.contains(QLatin1Char('.'))) {
        while (s.endsWith(QLatin1Char('0')))
            s.chop(1);
        if (s.endsWith(QLatin1Char('.')))
            s.chop(1);
    }
    QString int_part = s.section(QLatin1Char('.'), 0, 0);
    const QString frac = s.section(QLatin1Char('.'), 1);
    for (int i = int_part.size() - 3; i > 0; i -= 3)
        int_part.insert(i, QLatin1Char('.'));
    QString out = frac.isEmpty() ? int_part : int_part + QLatin1Char(',') + frac;
    if (v < 0.0 && out != QLatin1String("0"))
        out.prepend(QChar(0x2212));
    return out;
}

/// Display text of a JSON value: strings trimmed, numbers Vietnamese-formatted, anything else empty.
QString vb_text(const QJsonValue& v) {
    if (v.isString())
        return v.toString().trimmed();
    if (v.isDouble())
        return vb_fmt(v.toDouble());
    return {};
}

QString vb_key(const QJsonObject& o, const char* key) {
    return vb_text(o.value(QLatin1String(key)));
}

bool vb_is_need(const QString& s) {
    return s.trimmed().isEmpty() || s.trimmed().startsWith(QStringLiteral("[CẦN DATA"));
}

/// Break opportunities inside long unbroken tokens (file paths, launchd labels, dotted keys, CamelCase
/// class names): a zero-width space after each separator and between a lower- and an upper-case letter.
/// Without it the longest token sets the minimum width of its table column, and a 9-column table then
/// pushes the page wider than the viewport (seen at 900 px). Short tokens are left alone.
QString vb_soft(const QString& s) {
    constexpr int kLongToken = 12;
    static const QString kSeps = QStringLiteral("/_.-=,;|\\"); // not ":" — keeps hh:mm:ss whole
    QString out;
    out.reserve(s.size() + s.size() / 8);
    int i = 0;
    const int n = static_cast<int>(s.size());
    while (i < n) {
        if (s.at(i).isSpace()) {
            out += s.at(i++);
            continue;
        }
        int j = i;
        while (j < n && !s.at(j).isSpace())
            ++j;
        const bool long_token = j - i >= kLongToken;
        for (int k = i; k < j; ++k) {
            const QChar ch = s.at(k);
            if (long_token && k > i && ch.isUpper() && s.at(k - 1).isLower())
                out += QChar(0x200B);
            out += ch;
            if (long_token && k + 1 < j && kSeps.contains(ch))
                out += QChar(0x200B);
        }
        i = j;
    }
    return out;
}

/// Escaped data string with line breaks kept (long tokens made breakable).
QString vb_html(const QString& s) {
    QString h = esc(vb_soft(s));
    h.replace(QLatin1Char('\n'), QStringLiteral("<br>"));
    return h;
}

/// Escaped value, or a red "[CẦN DATA]" when empty / already marked missing.
QString vb_value_html(const QString& s) {
    if (s.trimmed().isEmpty())
        return span(esc(kVbNeed), col(Role::Down), true);
    if (vb_is_need(s))
        return span(vb_html(s), col(Role::Down), true);
    return vb_html(s);
}

/// Mono span around already-escaped html. Single-quoted style: the font CSS carries double quotes.
QString vb_mono(const QString& html, int px, const QColor& c, int weight = 500) {
    return QStringLiteral("<span style='color:%1; %2'>%3</span>").arg(css(c), mono_css(px, weight), html);
}

/// Rich-text tooltip (forces Qt's rich-text path so the escaped text shows verbatim and wraps).
QString vb_tip(const QString& tip) {
    return QStringLiteral("<p>%1</p>").arg(vb_html(tip));
}

/// Evidence tag(s): "MGMT EST" or "FACT-T1 NEWS ×3" becomes one pill per tier, each in its own tier colour
/// (a single pill would take the colour of whichever tier happens to come first). A "×n" count stays
/// with the tier before it.
QString vb_tiers(const QString& s, int px = 10) {
    QStringList parts;
    for (const QString& tok : s.split(QLatin1Char(' '), Qt::SkipEmptyParts)) {
        if (!parts.isEmpty() && (tok.startsWith(QChar(0x00D7)) ||
                                 (tok.size() > 1 && tok.at(0) == QLatin1Char('x') && tok.at(1).isDigit())))
            parts.last() += QLatin1Char(' ') + tok;
        else
            parts << tok;
    }
    QStringList html;
    for (const QString& p : parts)
        html << tier_html(p, px);
    return html.join(QStringLiteral(" "));
}

// ── Small widgets ────────────────────────────────────────────────────────────

QLabel* vb_plain(QWidget* parent, const QString& text, const QColor& c, int px, bool bold = false, bool mono = false) {
    auto* l = make_label(parent, c, px, Qt::PlainText, bold, mono);
    l->setText(vb_soft(text));
    return l;
}

QLabel* vb_rich(QWidget* parent, const QString& html, const QColor& c, int px, bool bold = false, bool mono = false) {
    auto* l = make_label(parent, c, px, Qt::RichText, bold, mono);
    l->setText(html);
    return l;
}

/// Serif card / figure title (artifact h3).
QLabel* vb_serif(QWidget* parent, const QString& text, int px = 15) {
    auto* l = vb_plain(parent, text, col(Role::Ink), px);
    l->setStyleSheet(QStringLiteral("QLabel { color:%1; %2 background:transparent; }")
                         .arg(css(col(Role::Ink)), lk::lk_font_css(lk::lk_font_serif(px, 600))));
    return l;
}

/// Muted "[CẦN DATA] <what>" note — a gap that must stay visible.
QLabel* vb_need(QWidget* parent, const QString& what) {
    return vb_rich(parent, span(esc(kVbNeed), col(Role::Down), true) + QStringLiteral(" ") + esc(what),
                   col(Role::Muted), 12);
}

/// Column count from block[key], default `def`, clamped to [1, kVbMaxCols].
int vb_cols(const QJsonObject& b, const char* key, int def) {
    const int n = b.value(QLatin1String(key)).toInt(def);
    return std::clamp(n, 1, kVbMaxCols);
}

/// Grid container with `cols` equal columns.
QGridLayout* vb_grid(QWidget* parent, QWidget*& holder, int cols, int spacing = 12) {
    holder = make_box(parent);
    auto* g = new QGridLayout(holder);
    g->setContentsMargins(0, 0, 0, 0);
    g->setHorizontalSpacing(spacing);
    g->setVerticalSpacing(spacing);
    for (int c = 0; c < cols; ++c)
        g->setColumnStretch(c, 1);
    return g;
}

// ── cong ─────────────────────────────────────────────────────────────────────

/// Gate strip: mono gate line, tier pill, muted note. Left edge = money regime read from the line.
QWidget* vb_cong(const QJsonObject& b, QWidget* parent) {
    const QString dong = vb_key(b, "dong");
    const QString low = dong.toLower();
    QColor edge = col(Role::Amber);
    if (dong.isEmpty() || dong.contains(QStringLiteral("[CẦN DATA")))
        edge = col(Role::Muted);
    else if (low.contains(QStringLiteral("tiền đắt")))
        edge = col(Role::Down);
    else if (low.contains(QStringLiteral("tiền rẻ")))
        edge = col(Role::Up);

    auto* strip = new QFrame(parent);
    strip->setObjectName(QStringLiteral("vbGate"));
    strip->setAttribute(Qt::WA_StyledBackground, true);
    strip->setStyleSheet(QStringLiteral("QFrame#vbGate { background:%1; border:1px solid %2; border-left:3px solid %3; "
                                        "border-radius:3px; }")
                             .arg(css(col(Role::Surface)), css(col(Role::AmberLine)), css(edge)));
    auto* hl = new QHBoxLayout(strip);
    hl->setContentsMargins(12, 8, 12, 8);

    QString html = dong.isEmpty() ? vb_mono(esc(QStringLiteral("CỔNG: ")), 12, col(Role::Ink), 600) +
                                        span(esc(kVbNeed), col(Role::Down), true)
                                  : vb_mono(vb_html(dong), 12, col(Role::Ink), 600);
    const QString tier = vb_tiers(str(b, "tier"));
    if (!tier.isEmpty())
        html += QStringLiteral("&nbsp; ") + tier;
    const QString phu = vb_key(b, "phu");
    if (!phu.isEmpty())
        html += QStringLiteral("&nbsp; <span style='color:%1; font-size:11px;'>%2</span>")
                    .arg(css(col(Role::Muted)), vb_html(phu));
    hl->addWidget(vb_rich(strip, html, col(Role::Ink), 12), 1);
    return strip;
}

// ── doan ─────────────────────────────────────────────────────────────────────

/// Paragraph; with "the": true a note card whose left edge carries the colour key.
QWidget* vb_doan(const QJsonObject& b, QWidget* parent) {
    const QString text = vb_key(b, "text");
    const QString mau = str(b, "mau").trimmed();
    const QString title = vb_key(b, "tieu_de");
    if (!b.value(QStringLiteral("the")).toBool()) {
        if (text.isEmpty())
            return vb_need(parent, QStringLiteral("đoạn văn trống"));
        return vb_plain(parent, text, mau.isEmpty() ? col(Role::Ink2) : colour(mau), 13, !mau.isEmpty());
    }
    QVBoxLayout* lay = nullptr;
    QFrame* card = make_card(parent, lay, mau.isEmpty() ? col(Role::Line2) : colour(mau));
    if (!title.isEmpty())
        lay->addWidget(vb_plain(card, title, col(Role::Ink), 13, true));
    if (text.isEmpty())
        lay->addWidget(vb_need(card, QStringLiteral("ghi chú trống")));
    else
        lay->addWidget(vb_plain(card, text, col(Role::Ink2), 13));
    return card;
}

// ── o_so ─────────────────────────────────────────────────────────────────────

/// One tile: uppercase label (LIVE pill when live), big mono value, sub-line, tier at the foot.
/// Live tiles get a dashed blue edge like SGI's live evidence tiles.
QFrame* vb_tile(const QJsonObject& t, QWidget* parent) {
    const bool live = t.value(QStringLiteral("live")).toBool();
    auto* card = new QFrame(parent);
    card->setObjectName(QStringLiteral("vbTile"));
    card->setAttribute(Qt::WA_StyledBackground, true);
    const QColor edge = live ? soft_on_surface(col(Role::Blue), 0.7) : col(Role::Line);
    card->setStyleSheet(QStringLiteral("QFrame#vbTile { background:%1; border:1px %2 %3; border-radius:4px; }")
                            .arg(css(col(Role::Surface)), live ? QStringLiteral("dashed") : QStringLiteral("solid"),
                                 css(edge)));
    auto* lay = new QVBoxLayout(card);
    lay->setContentsMargins(14, 12, 14, 12);
    lay->setSpacing(5);

    const QString nhan = vb_key(t, "nhan");
    QString head = esc((nhan.isEmpty() ? QStringLiteral("—") : nhan).toUpper());
    if (live)
        head = pill_html(QStringLiteral("LIVE"), col(Role::Blue), 10) + QStringLiteral("&nbsp; ") + head;
    lay->addWidget(vb_rich(card, head, col(Role::Muted), 11, true));

    const QString val = vb_key(t, "gia_tri");
    const QString mau = str(t, "mau").trimmed();
    if (vb_is_need(val)) {
        lay->addWidget(vb_rich(card, vb_value_html(val), col(Role::Down), 18, true, true));
    } else {
        // Long values step down so a narrow tile does not orphan the unit.
        const int px = val.size() <= 7 ? 26 : (val.size() <= 10 ? 22 : (val.size() <= 16 ? 18 : 15));
        lay->addWidget(vb_plain(card, val, mau.isEmpty() ? col(Role::Ink) : colour(mau), px, true, true));
    }

    const QString phu = vb_key(t, "phu");
    if (!phu.isEmpty())
        lay->addWidget(vb_plain(card, phu, col(Role::Ink2), 12));
    lay->addStretch(1);
    const QString tier = vb_tiers(str(t, "tier"));
    if (!tier.isEmpty())
        lay->addWidget(vb_rich(card, tier, col(Role::Muted), 11));
    return card;
}

QWidget* vb_o_so(const QJsonObject& b, QWidget* parent) {
    const QJsonArray tiles = b.value(QStringLiteral("o")).toArray();
    if (tiles.isEmpty())
        return vb_need(parent, QStringLiteral("khối ô số không có ô nào"));
    const int cols = vb_cols(b, "cot", kVbTileCols);
    QWidget* holder = nullptr;
    QGridLayout* g = vb_grid(parent, holder, cols);
    int i = 0;
    for (const QJsonValue& v : tiles) {
        if (!v.isObject())
            continue;
        g->addWidget(vb_tile(v.toObject(), holder), i / cols, i % cols);
        ++i;
    }
    return holder;
}

// ── bang ─────────────────────────────────────────────────────────────────────

struct VbCell {
    QString text;
    QString mau;
    QString tip;
    bool pill = false;
    bool mono = false;
    bool dam = false;
};

VbCell vb_cell(const QJsonValue& v) {
    VbCell c;
    if (!v.isObject()) {
        c.text = vb_text(v);
        return c;
    }
    const QJsonObject o = v.toObject();
    c.text = vb_key(o, "t");
    c.mau = str(o, "mau").trimmed();
    c.tip = vb_key(o, "tip");
    c.pill = o.value(QStringLiteral("pill")).toBool();
    c.mono = o.value(QStringLiteral("mono")).toBool();
    c.dam = o.value(QStringLiteral("dam")).toBool();
    return c;
}

QString vb_cell_css(const QColor& c, const QFont& f, const QColor& bg = QColor()) {
    return QStringLiteral("QLabel { color:%1; %2 background:%3; padding:7px 8px; border:none;"
                          " border-bottom:1px solid %4; }")
        .arg(css(c), lk::lk_font_css(f), bg.isValid() ? css(bg) : QStringLiteral("transparent"), css(col(Role::Line)));
}

QWidget* vb_bang(const QJsonObject& b, QWidget* parent) {
    QStringList heads;
    for (const QJsonValue& v : b.value(QStringLiteral("cot")).toArray())
        heads << vb_text(v);
    QList<QList<VbCell>> rows;
    int width = static_cast<int>(heads.size());
    for (const QJsonValue& rv : b.value(QStringLiteral("dong")).toArray()) {
        QList<VbCell> row;
        for (const QJsonValue& cv : rv.toArray())
            row << vb_cell(cv);
        if (heads.isEmpty())
            width = std::max(width, static_cast<int>(row.size()));
        rows << row;
    }
    if (width == 0)
        return vb_need(parent, QStringLiteral("bảng không có cột nào"));

    QSet<int> right;
    for (const QJsonValue& v : b.value(QStringLiteral("can_phai")).toArray())
        right.insert(v.toInt(-1));

    // Column stretch follows text length so prose columns get the room and codes stay narrow: the mean of
    // the longest and the average cell, so one long outlier row does not starve every other column.
    QList<int> longest(width, 0);
    QList<qint64> total(width, 0);
    QList<int> count(width, 0);
    for (int c = 0; c < heads.size(); ++c)
        longest[c] = static_cast<int>(heads.at(c).size());
    for (const auto& row : rows)
        for (int c = 0; c < std::min(width, static_cast<int>(row.size())); ++c) {
            const int n = static_cast<int>(row.at(c).text.size());
            longest[c] = std::max(longest[c], n);
            total[c] += n;
            ++count[c];
        }
    QList<int> stretch(width, kVbStretchMin);
    for (int c = 0; c < width; ++c) {
        const int mean = count[c] > 0 ? static_cast<int>(total[c] / count[c]) : longest[c];
        stretch[c] = std::max(kVbStretchMin, (longest[c] + mean) / 2);
    }

    auto* wrap = make_box(parent);
    auto* wl = new QVBoxLayout(wrap);
    wl->setContentsMargins(0, 0, 0, 0);
    wl->setSpacing(6);

    auto* frame = new QFrame(wrap);
    frame->setObjectName(QStringLiteral("vbTable"));
    frame->setAttribute(Qt::WA_StyledBackground, true);
    frame->setStyleSheet(QStringLiteral("QFrame#vbTable { background:%1; border:1px solid %2; border-radius:4px; }")
                             .arg(css(col(Role::Surface)), css(col(Role::Line))));
    auto* grid = new QGridLayout(frame);
    grid->setContentsMargins(1, 1, 1, 1);
    grid->setSpacing(0);
    for (int c = 0; c < width; ++c)
        grid->setColumnStretch(c, std::min(stretch.at(c), kVbStretchMax));
    // Short code-like columns (status pills, tiers, "1,26×") get a floor at their widest cell so a
    // stretched prose column cannot squeeze them into "FACT-|T2" or a one-word-per-line stack.
    for (int c = 0; c < width; ++c) {
        if (longest.at(c) > kVbNoWrapChars)
            continue;
        int px = 0;
        for (const auto& row : rows) {
            if (c >= row.size())
                continue;
            const VbCell& cell = row.at(c);
            const QFont f = cell.mono ? lk::lk_font_mono(13, 600) : lk::lk_font_sans(13, 600);
            px = std::max(px, QFontMetrics(f).horizontalAdvance(cell.text));
        }
        if (px > 0)
            grid->setColumnMinimumWidth(c, px + kVbCellPadX + 4);
    }

    int r = 0;
    if (!heads.isEmpty()) {
        for (int c = 0; c < width; ++c) {
            auto* h = new QLabel(frame);
            h->setTextFormat(Qt::PlainText);
            h->setWordWrap(true);
            h->setText(heads.at(c).toUpper());
            h->setAlignment((right.contains(c) ? Qt::AlignRight : Qt::AlignLeft) | Qt::AlignBottom);
            h->setStyleSheet(vb_cell_css(col(Role::Muted), lk::lk_font_sans(11, 600), col(Role::Surface2)));
            grid->addWidget(h, r, c);
        }
        ++r;
    }

    if (rows.isEmpty()) {
        auto* l = new QLabel(frame);
        l->setTextFormat(Qt::PlainText);
        l->setWordWrap(true);
        l->setText(QStringLiteral("— không có dòng nào —"));
        l->setStyleSheet(vb_cell_css(col(Role::Muted), lk::lk_font_sans(12, 400)));
        grid->addWidget(l, r, 0, 1, width);
    }
    for (const auto& row : rows) {
        for (int c = 0; c < width; ++c) {
            const VbCell cell = c < row.size() ? row.at(c) : VbCell{};
            const QColor fg = cell.mau.isEmpty() ? col(Role::Ink) : colour(cell.mau);
            QString html;
            if (cell.text.isEmpty())
                html = span(QStringLiteral("—"), col(Role::Muted));
            else if (cell.pill)
                html = pill_html(cell.text, cell.mau.isEmpty() ? col(Role::Muted) : fg, 11);
            else
                html = vb_value_html(cell.text);
            // Tooltip marker in the cell's own font: a fallback-font glyph such as "ⓘ" carries a taller line
            // box and left every row that had one ~1.5 lines of empty space at the bottom.
            if (!cell.tip.isEmpty())
                html += QStringLiteral(" <span style='color:%1; font-size:10px; font-weight:600;'>[i]</span>")
                            .arg(css(col(Role::Muted)));

            auto* l = new QLabel(frame);
            l->setTextFormat(Qt::RichText);
            l->setWordWrap(true);
            l->setTextInteractionFlags(Qt::TextSelectableByMouse);
            l->setAlignment((right.contains(c) ? Qt::AlignRight : Qt::AlignLeft) | Qt::AlignTop);
            const int weight = cell.dam ? 600 : (cell.mono ? 500 : 400);
            l->setStyleSheet(vb_cell_css(fg, cell.mono ? lk::lk_font_mono(13, weight) : lk::lk_font_sans(13, weight)));
            l->setText(html);
            if (!cell.tip.isEmpty())
                l->setToolTip(vb_tip(cell.tip));
            grid->addWidget(l, r, c);
        }
        ++r;
    }
    wl->addWidget(frame);

    const QString cap = vb_key(b, "chu_thich");
    if (!cap.isEmpty())
        wl->addWidget(vb_plain(wrap, cap, col(Role::Muted), 12));
    return wrap;
}

// ── the ──────────────────────────────────────────────────────────────────────

QFrame* vb_card(const QJsonObject& t, QWidget* parent) {
    const QString vien = str(t, "mau_vien").trimmed();
    QVBoxLayout* lay = nullptr;
    QFrame* card = make_card(parent, lay, vien.isEmpty() ? QColor() : colour(vien));

    const QString title = vb_key(t, "tieu_de");
    if (!title.isEmpty())
        lay->addWidget(vb_serif(card, title));

    const QJsonValue nv = t.value(QStringLiteral("nhan"));
    const QString nhan = nv.isObject() ? vb_key(nv.toObject(), "text") : vb_text(nv);
    if (!nhan.isEmpty()) {
        const QString nm = nv.isObject() ? str(nv.toObject(), "mau").trimmed() : QString();
        auto* pl = vb_rich(card, pill_html(nhan, nm.isEmpty() ? col(Role::Muted) : colour(nm), 11), col(Role::Ink), 11);
        pl->setWordWrap(false);
        lay->addWidget(pl);
    }

    const QString text = vb_key(t, "text");
    if (!text.isEmpty())
        lay->addWidget(vb_plain(card, text, col(Role::Ink2), 13));
    else if (title.isEmpty())
        lay->addWidget(vb_need(card, QStringLiteral("thẻ trống")));
    lay->addStretch(1);
    const QString tier = vb_tiers(str(t, "tier"));
    if (!tier.isEmpty())
        lay->addWidget(vb_rich(card, tier, col(Role::Muted), 11));
    return card;
}

QWidget* vb_the(const QJsonObject& b, QWidget* parent) {
    const QJsonArray cards = b.value(QStringLiteral("the")).toArray();
    if (cards.isEmpty())
        return vb_need(parent, QStringLiteral("khối thẻ không có thẻ nào"));
    const int cols = vb_cols(b, "cot", kVbCardCols);
    QWidget* holder = nullptr;
    QGridLayout* g = vb_grid(parent, holder, cols);
    int i = 0;
    for (const QJsonValue& v : cards) {
        if (!v.isObject())
            continue;
        g->addWidget(vb_card(v.toObject(), holder), i / cols, i % cols);
        ++i;
    }
    return holder;
}

// ── danh_sach ────────────────────────────────────────────────────────────────

/// One numbered item: amber circle + rail on the left (SGI keynote flow), title + tier tags + text.
QWidget* vb_list_item(QWidget* parent, const QString& so, const QJsonObject& it, bool last) {
    auto* row = make_box(parent);
    auto* hl = new QHBoxLayout(row);
    hl->setContentsMargins(0, 0, 0, 0);
    hl->setSpacing(12);

    const int rail_w = std::max(26, 10 + 8 * static_cast<int>(so.size()));
    auto* rail = make_box(row);
    rail->setFixedWidth(rail_w);
    auto* rl = new QVBoxLayout(rail);
    rl->setContentsMargins(0, 0, 0, 0);
    rl->setSpacing(0);
    auto* circle = new QLabel(rail);
    circle->setTextFormat(Qt::PlainText);
    circle->setText(so);
    circle->setFixedHeight(24);
    circle->setMinimumWidth(24);
    circle->setAlignment(Qt::AlignCenter);
    const QColor accent = col(Role::Amber);
    circle->setStyleSheet(QStringLiteral("QLabel { color:%1; background:%2; border:2px solid %1; border-radius:12px; "
                                         "padding:0 3px; %3 }")
                              .arg(css(accent), css(col(Role::Surface)), lk::lk_font_css(lk::lk_font_mono(11, 600))));
    rl->addWidget(circle, 0, Qt::AlignHCenter);
    auto* line = new QFrame(rail);
    line->setFixedWidth(2);
    line->setStyleSheet(QStringLiteral("QFrame { background:%1; border:none; }")
                            .arg(last ? QStringLiteral("transparent") : css(col(Role::Line2))));
    rl->addWidget(line, 1, Qt::AlignHCenter);
    hl->addWidget(rail, 0);

    auto* text = make_box(row);
    auto* tl = new QVBoxLayout(text);
    tl->setContentsMargins(0, 2, 0, last ? 0 : 12); // bottom gap sits beside the rail so the line stays continuous
    tl->setSpacing(2);
    const QString title = vb_key(it, "tieu_de");
    const QString body = vb_key(it, "text");
    QString head = title.isEmpty() ? QString() : vb_html(title);
    for (const QJsonValue& tv : it.value(QStringLiteral("tags")).toArray()) {
        const QString tag = vb_tiers(vb_text(tv));
        if (!tag.isEmpty())
            head += QStringLiteral("&nbsp; ") + tag;
    }
    if (!head.isEmpty())
        tl->addWidget(vb_rich(text, head, col(Role::Ink), 14, true));
    if (!body.isEmpty())
        tl->addWidget(vb_plain(text, body, col(Role::Ink2), 12));
    if (title.isEmpty() && body.isEmpty())
        tl->addWidget(vb_need(text, QStringLiteral("mục trống")));
    hl->addWidget(text, 1);
    return row;
}

QWidget* vb_danh_sach(const QJsonObject& b, QWidget* parent) {
    QList<QJsonObject> items;
    for (const QJsonValue& v : b.value(QStringLiteral("muc")).toArray())
        if (v.isObject())
            items << v.toObject();
    if (items.isEmpty())
        return vb_need(parent, QStringLiteral("danh sách trống"));
    QVBoxLayout* lay = nullptr;
    QFrame* card = make_card(parent, lay);
    lay->setSpacing(0);
    for (int i = 0; i < items.size(); ++i) {
        QString so = vb_key(items.at(i), "so");
        if (so.isEmpty())
            so = QString::number(i + 1);
        lay->addWidget(vb_list_item(card, so, items.at(i), i == items.size() - 1));
    }
    return card;
}

// ── trich ────────────────────────────────────────────────────────────────────

QWidget* vb_trich(const QJsonObject& b, QWidget* parent) {
    const QString text = vb_key(b, "text");
    if (text.isEmpty())
        return vb_need(parent, QStringLiteral("trích dẫn trống"));
    auto* q = new QFrame(parent);
    q->setObjectName(QStringLiteral("vbQuote"));
    q->setAttribute(Qt::WA_StyledBackground, true);
    q->setStyleSheet(QStringLiteral("QFrame#vbQuote { background:transparent; border:none; border-left:3px solid %1; }")
                         .arg(css(col(Role::Violet))));
    auto* lay = new QVBoxLayout(q);
    lay->setContentsMargins(16, 4, 8, 4);
    lay->setSpacing(4);
    auto* t = vb_plain(q, text, col(Role::Ink), 16);
    t->setStyleSheet(QStringLiteral("QLabel { color:%1; %2 font-style:italic; background:transparent; }")
                         .arg(css(col(Role::Ink)), lk::lk_font_css(lk::lk_font_serif(16, 400))));
    lay->addWidget(t);
    const QString nguon = vb_key(b, "nguon");
    if (!nguon.isEmpty())
        lay->addWidget(vb_plain(q, QStringLiteral("— ") + nguon, col(Role::Muted), 12));
    return q;
}

// ── bieu_do ──────────────────────────────────────────────────────────────────

/// Figure card: serif title, caption, chart (or a [CẦN DATA] note), source line + tier.
QWidget* vb_bieu_do(const QJsonObject& b, QWidget* parent) {
    QVBoxLayout* lay = nullptr;
    QFrame* card = make_card(parent, lay);
    const QString title = vb_key(b, "tieu_de");
    lay->addWidget(vb_serif(card, title.isEmpty() ? QStringLiteral("—") : title));
    const QString cap = vb_key(b, "chu_thich");
    if (!cap.isEmpty())
        lay->addWidget(vb_plain(card, cap, col(Role::Muted), 12));

    const QJsonObject block = b.value(QStringLiteral("block")).toObject();
    bool drawn = false;
    if (!block.isEmpty()) {
        const int h = std::clamp(b.value(QStringLiteral("cao")).toInt(kVbChartH), kVbChartMinH, kVbChartMaxH);
        if (is_ext_chart(block)) { // "cot" / "xy": categorical bars and numeric scatter (VnChartsExt)
            QWidget* chart = make_ext_chart(block, card);
            if (has_ext_chart_data(chart)) {
                chart->setFixedHeight(h);
                lay->addWidget(chart);
                drawn = true;
            } else {
                delete chart;
            }
        } else {
            auto* chart = new fincept::screens::langkinh::LkLineChart(block, card);
            if (chart->has_data()) {
                chart->setFixedHeight(h);
                lay->addWidget(chart);
                drawn = true;
            } else {
                delete chart;
            }
        }
    }
    if (!drawn)
        lay->addWidget(vb_need(card, QStringLiteral("không có điểm dữ liệu hợp lệ để vẽ biểu đồ này")));

    const QString nguon = vb_key(b, "nguon");
    QString src = esc(QStringLiteral("Nguồn: ")) +
                  (nguon.isEmpty() ? span(esc(kVbNeed), col(Role::Down)) : vb_html(nguon));
    const QString tier = vb_tiers(str(b, "tier"));
    if (!tier.isEmpty())
        src += QStringLiteral("&nbsp;&nbsp;") + tier;
    lay->addWidget(vb_rich(card, src, col(Role::Muted), 11));
    lay->addStretch(1);
    return card;
}

// ── canh_bao ─────────────────────────────────────────────────────────────────

QWidget* vb_canh_bao(const QJsonObject& b, QWidget* parent) {
    const QString mau = str(b, "mau").trimmed();
    const QColor accent = colour(mau.isEmpty() ? QStringLiteral("vang") : mau);
    QVBoxLayout* lay = nullptr;
    QFrame* card = make_card(parent, lay, accent);
    const QString title = vb_key(b, "tieu_de");
    if (!title.isEmpty())
        lay->addWidget(vb_rich(card, span(QStringLiteral("⚠ ") + vb_html(title), accent, true), accent, 13, true));
    int n = 0;
    for (const QJsonValue& v : b.value(QStringLiteral("muc")).toArray()) {
        const QString item = v.isObject() ? vb_key(v.toObject(), "text") : vb_text(v);
        if (item.isEmpty())
            continue;
        lay->addWidget(vb_rich(card, span(QStringLiteral("•"), accent) + QStringLiteral("&nbsp; ") + vb_html(item),
                               col(Role::Ink2), 13));
        ++n;
    }
    if (n == 0 && title.isEmpty())
        lay->addWidget(vb_need(card, QStringLiteral("khối cảnh báo trống")));
    return card;
}

// ── chips ────────────────────────────────────────────────────────────────────

QWidget* vb_chips(const QJsonObject& b, QWidget* parent) {
    QStringList parts;
    for (const QJsonValue& v : b.value(QStringLiteral("chips")).toArray()) {
        const QJsonObject c = v.toObject();
        const QString tier = vb_tiers(str(c, "tier"));
        const QString text = vb_key(c, "text");
        if (tier.isEmpty() && text.isEmpty())
            continue;
        QString p = tier;
        if (!text.isEmpty())
            p += (p.isEmpty() ? QString() : QStringLiteral("&nbsp;")) + vb_html(text);
        parts << p;
    }
    if (parts.isEmpty())
        return vb_need(parent, QStringLiteral("không có chip bằng chứng nào"));
    return vb_rich(parent, parts.join(QStringLiteral("&nbsp;&nbsp;&nbsp; ")), col(Role::Ink2), 12);
}

// ── unknown ──────────────────────────────────────────────────────────────────

QWidget* vb_unknown(const QString& kieu, QWidget* parent) {
    return vb_plain(parent, QStringLiteral("[khối lạ: %1]").arg(kieu.isEmpty() ? QStringLiteral("—") : kieu),
                    col(Role::Muted), 12);
}

QString vb_kind(const QJsonValue& v) {
    return v.isObject() ? str(v.toObject(), "kieu").trimmed() : QString();
}

} // namespace

// ── Public API ───────────────────────────────────────────────────────────────

QColor colour(const QString& mau) {
    const QString k = mau.trimmed().toLower();
    if (k == QLatin1String("xanh"))
        return col(Role::Up);
    if (k == QLatin1String("vang"))
        return col(Role::Amber);
    if (k == QLatin1String("do"))
        return col(Role::Down);
    if (k == QLatin1String("xam"))
        return col(Role::Muted);
    if (k == QLatin1String("lam"))
        return col(Role::Blue);
    if (k == QLatin1String("tim"))
        return col(Role::Violet);
    return col(Role::Ink);
}

QWidget* build_block(const QJsonObject& block, QWidget* parent) {
    const QString kieu = str(block, "kieu").trimmed();
    if (kieu == QLatin1String("cong"))
        return vb_cong(block, parent);
    if (kieu == QLatin1String("doan"))
        return vb_doan(block, parent);
    if (kieu == QLatin1String("o_so"))
        return vb_o_so(block, parent);
    if (kieu == QLatin1String("bang"))
        return vb_bang(block, parent);
    if (kieu == QLatin1String("the"))
        return vb_the(block, parent);
    if (kieu == QLatin1String("danh_sach"))
        return vb_danh_sach(block, parent);
    if (kieu == QLatin1String("trich"))
        return vb_trich(block, parent);
    if (kieu == QLatin1String("bieu_do"))
        return vb_bieu_do(block, parent);
    if (kieu == QLatin1String("canh_bao"))
        return vb_canh_bao(block, parent);
    if (kieu == QLatin1String("chips"))
        return vb_chips(block, parent);
    return vb_unknown(kieu, parent);
}

QWidget* build_section(const QJsonObject& section, QWidget* parent) {
    const QString title = vb_key(section, "tieu_de");
    QVBoxLayout* body = nullptr;
    QWidget* sec = make_section(parent, vb_key(section, "so"), title.isEmpty() ? QStringLiteral("—") : title,
                                vb_key(section, "lede"), body);
    const QString eyebrow = vb_key(section, "eyebrow");
    if (!eyebrow.isEmpty()) // above the header rule, like the artifact's section kicker
        body->insertWidget(0, vb_plain(sec, eyebrow.toUpper(), col(Role::Amber), 11, true));

    const QJsonArray khoi = section.value(QStringLiteral("khoi")).toArray();
    if (khoi.isEmpty()) {
        body->addWidget(vb_need(sec, QStringLiteral("mục này chưa có khối nội dung nào")));
        return sec;
    }
    const int n = static_cast<int>(khoi.size());
    int i = 0;
    while (i < n) {
        if (vb_kind(khoi.at(i)) != QLatin1String("bieu_do")) {
            body->addWidget(build_block(khoi.at(i).toObject(), sec));
            ++i;
            continue;
        }
        // Run of consecutive charts: two per row, an odd last one spans the row.
        int j = i;
        while (j < n && vb_kind(khoi.at(j)) == QLatin1String("bieu_do"))
            ++j;
        if (j - i == 1) {
            body->addWidget(vb_bieu_do(khoi.at(i).toObject(), sec));
        } else {
            QWidget* holder = nullptr;
            QGridLayout* g = vb_grid(sec, holder, 2);
            const int run = j - i;
            for (int k = 0; k < run; ++k) {
                QWidget* w = vb_bieu_do(khoi.at(i + k).toObject(), holder);
                if (k == run - 1 && k % 2 == 0)
                    g->addWidget(w, k / 2, 0, 1, 2);
                else
                    g->addWidget(w, k / 2, k % 2);
            }
            body->addWidget(holder);
        }
        i = j;
    }
    return sec;
}

QWidget* build_page(const QJsonObject& trang, QWidget* parent) {
    auto* page = make_box(parent);
    auto* vl = new QVBoxLayout(page);
    vl->setContentsMargins(0, 0, 0, 0);
    vl->setSpacing(6);
    const QJsonArray sections = trang.value(QStringLiteral("sections")).toArray();
    if (sections.isEmpty())
        vl->addWidget(vb_need(page, QStringLiteral("trang không có mục nào (payload thiếu \"trang.sections\")")));
    for (const QJsonValue& s : sections)
        vl->addWidget(build_section(s.toObject(), page));
    vl->addStretch(1);
    return page;
}

} // namespace fincept::screens::vnblocks
