// src/screens/hhp_valuation/HhpWeeklyPage.cpp
// BẢN TUẦN view — builds the whole page from one `hhp_weekly.py weekly` payload (layout map in
// HhpWeeklyPage.h, BLOCK types in the script's docstring). build_block() is the one recursive
// renderer for every contract block; the masthead, the engine card (KIỂM BẢN TUẦN) and the footer
// are page-level. Rich strings (ihtml) go through rich(), plain ones through esc(); every JSON
// lookup tolerates missing keys and wrong types, and a missing part becomes a muted note.
#include "screens/hhp_valuation/HhpWeeklyPage.h"

#include "screens/hhp_valuation/HhpWeeklyCommon.h"
#include "screens/hhp_valuation/HhpWeeklyScreener.h"
#include "screens/hhp_valuation/HhpWeeklyWidgets.h"

#include <QDate>
#include <QEvent>
#include <QFrame>
#include <QGridLayout>
#include <QHBoxLayout>
#include <QHash>
#include <QJsonArray>
#include <QLabel>
#include <QPushButton>
#include <QTextBrowser>
#include <QVBoxLayout>

#include <algorithm>
#include <cmath>
#include <optional>
#include <utility>

namespace fincept::screens::hhp::weekly {

namespace {

constexpr int kStatCols = 5;            ///< stat tiles per row
constexpr int kNavPerRow = 14;          ///< section buttons per nav row
constexpr int kTableScrollMaxPx = 520;  ///< height cap of a table the page boxed with max-height
constexpr int kTableRowMinPx = 22;      ///< lower bound of one table row (12px text + cell padding)
constexpr int kTablePx = 12;            ///< table body font px
constexpr int kVoiceWhoPx = 130;        ///< width of the "who" column of a voice row
constexpr int kMaxDepth = 6;            ///< nesting guard for cards inside cards
constexpr int kLabelHintW = 420;        ///< preferred width of a wrapped label before it has been laid out
constexpr int kLabelMinW = 60;          ///< minimum width of a wrapped label (instead of its longest word)
constexpr int kHfwCacheSize = 8;        ///< widths remembered per label

const QString kNotAdvice = QStringLiteral("Bản tuần của Hội đồng cố vấn AI — tham khảo, KHÔNG phải khuyến nghị. "
                                          "Mọi số của bản tuần giữ nguyên; số live mang ngày riêng.");

// ── JSON access (missing key / wrong type → empty) ──────────────────────────

QString jstr(const QJsonObject& o, const char* key) {
    const QJsonValue v = o.value(QLatin1String(key));
    return v.isString() ? v.toString() : QString();
}
bool jbool(const QJsonObject& o, const char* key) {
    return o.value(QLatin1String(key)).toBool(false);
}
double jnum(const QJsonObject& o, const char* key) {
    return num(o.value(QLatin1String(key)));
}
QJsonObject jobj(const QJsonObject& o, const char* key) {
    return o.value(QLatin1String(key)).toObject();
}
QJsonArray jarr(const QJsonObject& o, const char* key) {
    return o.value(QLatin1String(key)).toArray();
}

// ── Rich-text snippets ───────────────────────────────────────────────────────

QString mono() {
    return QStringLiteral("'Menlo','Monaco','Courier New',monospace");
}

/// `html` must already be safe rich text.
QString span(const QString& style, const QString& html) {
    return QStringLiteral("<span style=\"") + style + QStringLiteral("\">") + html + QStringLiteral("</span>");
}

QString color_style(const QColor& c) {
    return QStringLiteral("color:%1;").arg(css(c));
}

/// "2026-09-22" | "22/09/2026" → "22/09"; anything else unchanged.
QString short_dm(const QString& s) {
    QDate d = QDate::fromString(s.left(10), Qt::ISODate);
    if (!d.isValid())
        d = QDate::fromString(s.trimmed(), QStringLiteral("dd/MM/yyyy"));
    return d.isValid() ? d.toString(QStringLiteral("dd/MM")) : s.trimmed();
}

/// "" / "—" → fallback.
QString or_dash(const QString& s, const QString& fallback = QStringLiteral("—")) {
    const QString t = s.trimmed();
    return (t.isEmpty() || t == QStringLiteral("—")) ? fallback : t;
}

struct Cell {
    Cell() = default;
    Cell(QString h, bool r = false, QColor c = QColor(), bool b = false)
        : html(std::move(h)), right(r), color(std::move(c)), bold(b) {}

    QString html;   ///< Qt rich text
    bool right = false;
    QColor color;   ///< invalid → label colour
    bool bold = false;
    int width = 0;  ///< px, 0 = auto
};

struct Row {
    QVector<Cell> cells;
    QColor bg;      ///< invalid → none
};

/// Qt rich-text table (no per-row borders in Qt's subset — rows separate by padding only).
QString table_html(const QVector<Cell>& head, const QVector<Row>& rows, int px = kTablePx) {
    QString h = QStringLiteral("<table width=\"100%\" border=\"0\" cellspacing=\"0\" cellpadding=\"5\">");
    if (!head.isEmpty()) {
        h += QStringLiteral("<tr>");
        for (const Cell& c : head)
            h += QStringLiteral("<td bgcolor=\"%1\" align=\"%2\" valign=\"bottom\">")
                     .arg(css(c_card2()), c.right ? QStringLiteral("right") : QStringLiteral("left")) +
                 span(QStringLiteral("color:%1; font-size:11px; font-weight:bold;").arg(css(c_muted())), c.html) +
                 QStringLiteral("</td>");
        h += QStringLiteral("</tr>");
    }
    for (const Row& r : rows) {
        h += QStringLiteral("<tr>");
        for (const Cell& c : r.cells) {
            QString attrs = QStringLiteral(" valign=\"top\" align=\"%1\"").arg(c.right ? QStringLiteral("right")
                                                                                        : QStringLiteral("left"));
            if (r.bg.isValid())
                attrs += QStringLiteral(" bgcolor=\"%1\"").arg(css(r.bg));
            if (c.width > 0)
                attrs += QStringLiteral(" width=\"%1\"").arg(c.width);
            QString style = QStringLiteral("font-size:%1px;").arg(px);
            if (c.color.isValid())
                style += color_style(c.color);
            if (c.bold)
                style += QStringLiteral(" font-weight:bold;");
            h += QStringLiteral("<td") + attrs + QLatin1Char('>') + span(style, c.html) + QStringLiteral("</td>");
        }
        h += QStringLiteral("</tr>");
    }
    h += QStringLiteral("</table>");
    return h;
}

// ── Widget helpers ───────────────────────────────────────────────────────────

/// Word-wrapped rich-text QLabel with cached size hints. A stock QLabel lays its whole document out
/// again for every hint a layout asks for (minimumSizeHint alone tries three widths, and each trial
/// sets and then restores the text width); with ~400 labels and ~20 rich-text tables one layout
/// pass of the page took seconds. Here each width is laid out once, the preferred width is fixed
/// and the minimum width is a small floor instead of the longest word. Unwrapped labels are stock.
class FastLabel final : public QLabel {
  public:
    explicit FastLabel(QWidget* parent) : QLabel(parent) {}

    int heightForWidth(int w) const override {
        if (!wordWrap() || w <= 0)
            return QLabel::heightForWidth(w);
        ensurePolished(); // the style sheet sets the font; hints taken before it would be stale
        const auto it = hfw_.constFind(w);
        if (it != hfw_.cend())
            return it.value();
        if (hfw_.size() >= kHfwCacheSize)
            hfw_.clear();
        const int h = QLabel::heightForWidth(w);
        hfw_.insert(w, h);
        last_w_ = w;
        return h;
    }

    /// Height = the last width actually laid out (box and grid layouts place wrapped labels by
    /// heightForWidth, so this only feeds their aggregate hints); one line before any layout.
    QSize sizeHint() const override {
        if (!wordWrap())
            return QLabel::sizeHint();
        const auto it = hfw_.constFind(last_w_);
        return QSize(kLabelHintW, it != hfw_.cend() ? it.value() : fontMetrics().lineSpacing());
    }

    QSize minimumSizeHint() const override {
        return wordWrap() ? QSize(kLabelMinW, 0) : QLabel::minimumSizeHint();
    }

  protected:
    void changeEvent(QEvent* e) override {
        const QEvent::Type t = e->type();
        if (t == QEvent::FontChange || t == QEvent::StyleChange || t == QEvent::ContentsRectChange)
            hfw_.clear();
        QLabel::changeEvent(e);
    }

  private:
    mutable QHash<int, int> hfw_;
    mutable int last_w_ = 0;
};

/// wlabel() (HhpWeeklyCommon.h) on a FastLabel: same look, cheap to lay out.
QLabel* flabel(QWidget* parent, const QString& html, int px = 13, const QColor& color = c_text(), bool bold = false) {
    auto* l = new FastLabel(parent);
    l->setTextFormat(Qt::RichText);
    l->setWordWrap(true);
    l->setTextInteractionFlags(Qt::TextSelectableByMouse);
    l->setStyleSheet(QStringLiteral("QLabel { color:%1; font-size:%2px; font-weight:%3; background:transparent; }")
                         .arg(css(color), QString::number(px),
                              bold ? QStringLiteral("bold") : QStringLiteral("normal")));
    l->setText(html);
    return l;
}

QString unique_name() {
    static int s_seq = 0;
    return QStringLiteral("hhpwPg%1").arg(++s_seq);
}

/// QFrame styled by an object-name selector, so the rule does not cascade into child QLabels.
QFrame* styled_frame(QWidget* parent, const QString& rule) {
    auto* f = new QFrame(parent);
    const QString name = unique_name();
    f->setObjectName(name);
    f->setStyleSheet(QStringLiteral("QFrame#") + name + QStringLiteral(" { ") + rule + QStringLiteral(" }"));
    return f;
}

QFrame* hline(QWidget* parent) {
    auto* f = new QFrame(parent);
    f->setFixedHeight(1);
    f->setStyleSheet(QStringLiteral("QFrame { background:%1; border:none; }").arg(css(c_line())));
    return f;
}

/// Bold, letter-spaced label; `html` is rich text already.
QLabel* eyebrow_label(QWidget* parent, const QString& html, int px, const QColor& color) {
    QLabel* l = flabel(parent, html, px, color, true);
    l->setStyleSheet(QStringLiteral("QLabel { color:%1; font-size:%2px; font-weight:bold; letter-spacing:1px;"
                                    " background:transparent; }")
                         .arg(css(color), QString::number(px)));
    return l;
}

/// Upper-case like the page's CSS text-transform, but keep the Greek of the method (μ, σ) lower-case:
/// "Μ" / "Σ" in a column header read as the Latin letters M / E.
QString caps(const QString& plain) {
    QString out = plain.toUpper();
    for (qsizetype i = 0; i < plain.size() && i < out.size(); ++i) {
        const QChar c = plain.at(i);
        if (c == QChar(0x03BC) || c == QChar(0x03C3) || c == QChar(0x00B5))
            out[i] = c;
    }
    return out;
}

QLabel* caps_label(QWidget* parent, const QString& plain, int px, const QColor& color) {
    return eyebrow_label(parent, esc(caps(plain)), px, color);
}

QLabel* muted_note(QWidget* parent, const QString& plain, int px = 12) {
    return flabel(parent, esc(plain), px, c_muted());
}

// ── Block renderer ───────────────────────────────────────────────────────────

struct BuildCtx {
    HhpWeeklyPage* page = nullptr;
    QJsonObject snapshot;             ///< payload.snapshot (screener data)
    QStringList mine;                 ///< core.mine
    QStringList avoid;                ///< core.avoid
    QString issue_dm;                 ///< valuation vintage "11/09" ("" when the issue does not state it)
    QColor surface = c_bg();          ///< background the current block sits on
    HhpWeeklyScreener* screener = nullptr;
    int depth = 0;
};

QWidget* build_block(const QJsonObject& b, QWidget* parent, BuildCtx& ctx);

/// Appends every block of `blocks` to `lay`, children of `parent`.
void add_blocks(const QJsonValue& blocks, QWidget* parent, QVBoxLayout* lay, BuildCtx& ctx) {
    if (ctx.depth >= kMaxDepth)
        return;
    ++ctx.depth;
    for (const QJsonValue& v : blocks.toArray()) {
        if (!v.isObject())
            continue;
        if (QWidget* w = build_block(v.toObject(), parent, ctx))
            lay->addWidget(w);
    }
    --ctx.depth;
}

QWidget* build_p(const QJsonObject& b, QWidget* parent) {
    const QString html = jstr(b, "html");
    if (html.trimmed().isEmpty())
        return nullptr;
    const int px = jbool(b, "small") ? 12 : 13;
    const QColor color = tone_color(jstr(b, "tone"), c_text());
    const bool bold = jbool(b, "bold");
    const QString box = jstr(b, "box");
    if (box.isEmpty())
        return flabel(parent, rich(html, px), px, color, bold);
    const QColor bg = box == QLatin1String("down") ? soft(c_rich(), 0.12) : c_card2();
    QFrame* f = styled_frame(parent, QStringLiteral("background:%1; border:none; border-radius:6px;").arg(css(bg)));
    auto* l = new QVBoxLayout(f);
    l->setContentsMargins(12, 8, 12, 8);
    l->addWidget(flabel(f, rich(html, px), px, color, bold));
    return f;
}

QWidget* build_note(const QJsonObject& b, QWidget* parent) {
    const QString html = jstr(b, "html");
    if (html.trimmed().isEmpty())
        return nullptr;
    const QColor tone = tone_color(or_dash(jstr(b, "tone"), QStringLiteral("ref")), c_gold());
    QFrame* f = styled_frame(parent, QStringLiteral("background:%1; border:none; border-left:3px solid %2;"
                                                    " border-radius:4px;")
                                         .arg(css(c_card()), css(tone)));
    auto* l = new QVBoxLayout(f);
    l->setContentsMargins(12, 8, 12, 8);
    l->addWidget(flabel(f, rich(html, 13), 13, c_ink2()));
    return f;
}

/// Fixed-height, read-only, selectable view of a long rich-text table; it scrolls itself and lays
/// the document out once per width (a QLabel in a scroll area did it several times per pass).
QWidget* scroll_table(const QString& html, const QColor& surface, QWidget* parent) {
    auto* tb = new QTextBrowser(parent);
    const QString name = unique_name();
    tb->setObjectName(name);
    tb->setFrameShape(QFrame::NoFrame);
    tb->setOpenLinks(false);
    tb->setHorizontalScrollBarPolicy(Qt::ScrollBarAlwaysOff);
    tb->setFixedHeight(kTableScrollMaxPx);
    tb->setStyleSheet(QStringLiteral("QTextBrowser#%1 { background:%2; color:%3; border:none; font-size:%4px; }")
                          .arg(name, css(surface), css(c_text()), QString::number(kTablePx)));
    tb->document()->setDocumentMargin(0);
    tb->setHtml(html);
    return tb;
}

QWidget* build_table(const QJsonObject& b, QWidget* parent, const BuildCtx& ctx) {
    QVector<Cell> head;
    for (const QJsonValue& hv : jarr(b, "head")) {
        const QJsonObject h = hv.toObject();
        const QString text = hv.isString() ? hv.toString() : jstr(h, "text");
        Cell c;
        c.html = esc(caps(text));
        c.right = jstr(h, "align") == QLatin1String("r");
        head.append(c);
    }
    QVector<Row> rows;
    for (const QJsonValue& rv : jarr(b, "rows")) {
        const QJsonObject r = rv.toObject();
        Row row;
        if (jbool(r, "mine"))
            row.bg = soft(c_gold(), 0.10);
        for (const QJsonValue& cv : jarr(r, "cells")) {
            const QJsonObject co = cv.toObject();
            Cell c;
            c.html = rich(cv.isString() ? cv.toString() : jstr(co, "html"), kTablePx);
            c.right = jstr(co, "align") == QLatin1String("r");
            const QString tone = jstr(co, "tone");
            if (!tone.isEmpty())
                c.color = tone_color(tone, c_text());
            c.bold = jbool(co, "bold");
            row.cells.append(c);
        }
        if (!row.cells.isEmpty())
            rows.append(row);
    }
    if (rows.isEmpty() && head.isEmpty())
        return nullptr;

    auto* box = new QWidget(parent);
    auto* vl = new QVBoxLayout(box);
    vl->setContentsMargins(0, 0, 0, 0);
    vl->setSpacing(4);
    const QString html = table_html(head, rows);
    // The page boxed this table with max-height. Only a table that cannot fit under the cap gets
    // the scroll box; the row count gives a safe lower bound of its height without laying it out.
    const bool tall = (static_cast<int>(rows.size()) + 1) * kTableRowMinPx > kTableScrollMaxPx;
    if (jbool(b, "scroll") && tall)
        vl->addWidget(scroll_table(html, ctx.surface, box));
    else
        vl->addWidget(flabel(box, html, kTablePx, c_text()));
    const QString caption = jstr(b, "caption");
    if (!caption.trimmed().isEmpty())
        vl->addWidget(flabel(box, rich(caption, 11), 11, c_muted()));
    return box;
}

/// Stat tiles (masthead and section-level "stats"): label · value · sub · optional live line.
QFrame* build_stat_tile(const QJsonObject& st, QWidget* parent) {
    QVBoxLayout* lay = nullptr;
    QFrame* card = wcard(parent, lay, {}, {}, 12);
    lay->setSpacing(3);
    const QString label = jstr(st, "label");
    if (!label.trimmed().isEmpty())
        lay->addWidget(caps_label(card, label, 11, c_muted()));
    const QColor value_color = tone_color(jstr(st, "value_tone"), c_text());
    lay->addWidget(flabel(card, esc(or_dash(jstr(st, "value"))), 22, value_color, true));
    const QString sub = jstr(st, "sub");
    if (!sub.trimmed().isEmpty())
        lay->addWidget(flabel(card, rich(sub, 12), 12, c_muted()));
    const QJsonObject live = jobj(st, "live");
    const QString live_text = jstr(live, "text");
    if (!live_text.trimmed().isEmpty())
        lay->addWidget(
            flabel(card, esc(QStringLiteral("↳ ") + live_text), 11, tone_color(jstr(live, "tone"), c_muted())));
    lay->addStretch(1);
    return card;
}

QWidget* build_stats(const QJsonArray& items, QWidget* parent) {
    QVector<QJsonObject> tiles;
    for (const QJsonValue& v : items)
        if (v.isObject() && !v.toObject().isEmpty())
            tiles.append(v.toObject());
    if (tiles.isEmpty())
        return nullptr;
    auto* box = new QWidget(parent);
    auto* grid = new QGridLayout(box);
    grid->setContentsMargins(0, 0, 0, 0);
    grid->setHorizontalSpacing(10);
    grid->setVerticalSpacing(10);
    const int cols = std::min(kStatCols, static_cast<int>(tiles.size()));
    for (int i = 0; i < tiles.size(); ++i)
        grid->addWidget(build_stat_tile(tiles.at(i), box), i / cols, i % cols);
    for (int c = 0; c < cols; ++c)
        grid->setColumnStretch(c, 1);
    return box;
}

/// CARD fields (contract) — used by "cards", "card".
QFrame* build_card(const QJsonObject& c, QWidget* parent, BuildCtx& ctx) {
    QVBoxLayout* lay = nullptr;
    QFrame* card = wcard(parent, lay, jstr(c, "tone"), jstr(c, "outline"));
    const QString title = jstr(c, "title");
    const QString chip = jstr(c, "chip");
    if (!title.trimmed().isEmpty() || !chip.trimmed().isEmpty()) {
        auto* hd = new QHBoxLayout;
        hd->setSpacing(8);
        hd->addWidget(flabel(card, esc(title), 14, tone_color(jstr(c, "title_tone"), c_text()), true), 1);
        if (!chip.trimmed().isEmpty()) {
            QLabel* cl = flabel(card, rich(chip, 11), 11, c_ink2(), true);
            cl->setWordWrap(false);
            cl->setAlignment(Qt::AlignRight | Qt::AlignTop);
            hd->addWidget(cl, 0, Qt::AlignTop);
        }
        lay->addLayout(hd);
    }
    const QColor prev = ctx.surface;
    ctx.surface = c_card();
    add_blocks(c.value(QLatin1String("blocks")), card, lay, ctx);
    ctx.surface = prev;
    lay->addStretch(1);
    return card;
}

QWidget* build_cards(const QJsonObject& b, QWidget* parent, BuildCtx& ctx) {
    QVector<QJsonObject> cards;
    for (const QJsonValue& v : jarr(b, "cards"))
        if (v.isObject() && !v.toObject().isEmpty())
            cards.append(v.toObject());
    if (cards.isEmpty())
        return nullptr;
    const int n = static_cast<int>(cards.size());
    const double want = jnum(b, "cols"); // contract: 2 for "grid2 g2", else min(3, n)
    const int cols = std::min(has(want) ? static_cast<int>(std::clamp(want, 1.0, 3.0)) : 3, n);
    auto* box = new QWidget(parent);
    auto* grid = new QGridLayout(box);
    grid->setContentsMargins(0, 0, 0, 0);
    grid->setHorizontalSpacing(10);
    grid->setVerticalSpacing(10);
    for (int i = 0; i < n; ++i)
        grid->addWidget(build_card(cards.at(i), box, ctx), i / cols, i % cols);
    for (int c = 0; c < cols; ++c)
        grid->setColumnStretch(c, 1);
    return box;
}

QWidget* build_kv(const QJsonObject& b, QWidget* parent) {
    auto* box = new QWidget(parent);
    auto* grid = new QGridLayout(box);
    grid->setContentsMargins(0, 0, 0, 0);
    grid->setHorizontalSpacing(14);
    grid->setVerticalSpacing(6);
    int r = 0;
    for (const QJsonValue& v : jarr(b, "items")) {
        const QJsonObject it = v.toObject();
        const QString k = jstr(it, "k");
        const QString val = jstr(it, "v");
        if (k.trimmed().isEmpty() && val.trimmed().isEmpty())
            continue;
        QLabel* kl = caps_label(box, k, 11, c_muted());
        kl->setMaximumWidth(240);
        grid->addWidget(kl, r, 0, Qt::AlignTop);
        grid->addWidget(flabel(box, span(QStringLiteral("font-family:") + mono() + QLatin1Char(';'), rich(val, 13)), 13,
                               c_text()),
                        r, 1);
        ++r;
    }
    if (r == 0) {
        delete box;
        return nullptr;
    }
    grid->setColumnStretch(1, 1);
    return box;
}

QWidget* build_list(const QJsonObject& b, QWidget* parent) {
    QString items;
    for (const QJsonValue& v : jarr(b, "items"))
        if (v.isString() && !v.toString().trimmed().isEmpty())
            items += QStringLiteral("<li>") + rich(v.toString(), 13) + QStringLiteral("</li>");
    if (items.isEmpty())
        return nullptr;
    const QString tag = jbool(b, "ordered") ? QStringLiteral("ol") : QStringLiteral("ul");
    const QString html = QLatin1Char('<') + tag + QStringLiteral(" style=\"margin-top:0px; margin-bottom:0px;\">") +
                         items + QStringLiteral("</") + tag + QLatin1Char('>');
    return flabel(parent, html, 13, tone_color(jstr(b, "tone"), c_text()));
}

BandLevels band_levels(const QJsonObject& o) {
    BandLevels l;
    l.cheap2 = jnum(o, "cheap2");
    l.cheap1 = jnum(o, "cheap1");
    l.fair = jnum(o, "fair");
    l.rich1 = jnum(o, "rich1");
    l.rich2 = jnum(o, "rich2");
    l.price = jnum(o, "price");
    return l;
}

/// Row caption of HhpBandStrip / HhpSigmaDist: the widgets keep a narrow gutter sized for "dd/MM".
QString row_tag(const QString& date, const QString& fallback) {
    const QString d = short_dm(or_dash(date, QString()));
    return d.isEmpty() ? fallback : d;
}

/// Says which chart row is which, since the rows themselves carry only a date.
QString rows_legend(const QString& issue_tag, const QString& live_tag) {
    return esc(QStringLiteral("trên: bản tuần ") + issue_tag + QStringLiteral(" · dưới: live ") + live_tag);
}

QWidget* build_band(const QJsonObject& b, QWidget* parent, const BuildCtx& ctx) {
    const QString tk = jstr(b, "ticker");
    const QString aria = jstr(b, "label");
    const BandLevels issue = band_levels(b);
    const QJsonObject live_o = jobj(b, "live");
    const BandLevels live = band_levels(live_o);
    const bool live_ok = !live_o.isEmpty() && live.valid();
    if (!issue.valid() && !live_ok)
        return muted_note(parent, QStringLiteral("[CẦN DATA] dải định giá ") + tk + QStringLiteral(" không đọc được") +
                                      (aria.isEmpty() ? QString() : QStringLiteral(" — ") + aria));

    auto* box = new QWidget(parent);
    auto* vl = new QVBoxLayout(box);
    vl->setContentsMargins(0, 2, 0, 2);
    vl->setSpacing(4);
    QString head = span(QStringLiteral("font-family:") + mono() + QStringLiteral("; font-weight:bold;"), esc(tk));
    const QString metric = jstr(b, "metric");
    if (!metric.isEmpty())
        head += QStringLiteral(" · ") + esc(metric);
    const QString issue_tag = ctx.issue_dm.isEmpty() ? QStringLiteral("tuần") : ctx.issue_dm;
    const QString live_tag = row_tag(jstr(live_o, "as_of"), QStringLiteral("live"));
    if (live_ok) {
        head += QStringLiteral("&nbsp;&nbsp; ") + span(color_style(c_muted()), rows_legend(issue_tag, live_tag));
        const double s = jnum(live_o, "sigma");
        const QString s_txt = jstr(live_o, "sigma_txt");
        if (!s_txt.isEmpty())
            head += QStringLiteral(" · σ live ") +
                    span(color_style(has(s) ? sigma_color(s) : zone_color(jstr(live_o, "zone_key"))), esc(s_txt));
    }
    vl->addWidget(flabel(box, head, 12, c_ink2()));
    auto* strip = new HhpBandStrip(box);
    strip->set_bands(issue, issue_tag, live_ok ? &live : nullptr, live_tag);
    vl->addWidget(strip);
    if (!aria.trimmed().isEmpty())
        vl->addWidget(muted_note(box, aria, 11));
    return box;
}

QVector<DistPoint> dist_points(const QJsonObject& o) {
    QVector<DistPoint> out;
    for (const QJsonValue& v : jarr(o, "points")) {
        const QJsonObject p = v.toObject();
        const QString tk = jstr(p, "tk");
        const double s = jnum(p, "s");
        if (tk.isEmpty() || !has(s))
            continue;
        DistPoint d;
        d.tk = tk;
        d.s = s;
        d.mine = jbool(p, "mine");
        out.append(d);
    }
    return out;
}

QWidget* build_dist(const QJsonObject& b, QWidget* parent, const BuildCtx& ctx) {
    const QJsonObject io = jobj(b, "issue");
    const QJsonObject lo = jobj(b, "live");
    const QVector<DistPoint> issue = dist_points(io);
    const QVector<DistPoint> live = dist_points(lo);
    const QString caption = jstr(b, "caption");
    if (issue.isEmpty() && live.isEmpty())
        return muted_note(parent, QStringLiteral("[CẦN DATA] thước σ không có điểm nào"));

    auto* box = new QWidget(parent);
    auto* vl = new QVBoxLayout(box);
    vl->setContentsMargins(0, 2, 0, 2);
    vl->setSpacing(4);
    const QString issue_tag =
        row_tag(jstr(io, "as_of"), ctx.issue_dm.isEmpty() ? QStringLiteral("tuần") : ctx.issue_dm);
    const QString live_tag = row_tag(jstr(lo, "as_of"), QStringLiteral("live"));
    auto* chart = new HhpSigmaDist(box);
    chart->set_data(issue, issue_tag, live, live_tag, str_list(b.value(QLatin1String("labels"))));
    vl->addWidget(chart);
    if (!live.isEmpty())
        vl->addWidget(flabel(box, rows_legend(issue_tag, live_tag), 11, c_muted()));
    if (!caption.trimmed().isEmpty())
        vl->addWidget(flabel(box, rich(caption, 12), 12, c_muted()));
    return box;
}

QWidget* build_screener(QWidget* parent, BuildCtx& ctx) {
    if (ctx.screener)
        return nullptr; // one interactive screener per page
    const QJsonArray rows = jarr(ctx.snapshot, "rows");
    if (rows.isEmpty())
        return muted_note(parent, QStringLiteral("[CẦN DATA] bản tuần không kèm dữ liệu bộ lọc (snapshot)"));
    auto* scr = new HhpWeeklyScreener(parent);
    scr->set_data(rows, jobj(ctx.snapshot, "live"), ctx.mine, ctx.avoid, jstr(ctx.snapshot, "as_of_txt"),
                  jstr(ctx.snapshot, "live_as_of_txt"));
    if (ctx.page)
        QObject::connect(scr, &HhpWeeklyScreener::ticker_activated, ctx.page, &HhpWeeklyPage::ticker_activated);
    ctx.screener = scr;
    return scr;
}

QWidget* build_voice(const QJsonObject& b, QWidget* parent) {
    const QString who = jstr(b, "who");
    const QString html = jstr(b, "html");
    if (who.trimmed().isEmpty() && html.trimmed().isEmpty())
        return nullptr;
    const QString side = jstr(b, "side");
    const QColor sc = side == QLatin1String("kill")    ? c_rich()
                      : side == QLatin1String("alpha") ? c_cheap()
                                                       : c_muted();
    QFrame* row = styled_frame(parent, QStringLiteral("background:transparent; border:none; border-left:2px solid %1;")
                                           .arg(css(sc)));
    auto* hl = new QHBoxLayout(row);
    hl->setContentsMargins(10, 2, 0, 2);
    hl->setSpacing(12);
    QLabel* wl = caps_label(row, who, 11, sc);
    wl->setFixedWidth(kVoiceWhoPx);
    hl->addWidget(wl, 0, Qt::AlignTop);
    hl->addWidget(flabel(row, rich(html, 13), 13, c_text()), 1);
    return row;
}

QWidget* build_advisor(const QJsonObject& b, QWidget* parent, BuildCtx& ctx) {
    if (jstr(b, "ticker").trimmed().isEmpty() && jstr(b, "subtitle").trimmed().isEmpty() &&
        jstr(b, "verdict").trimmed().isEmpty() && jarr(b, "blocks").isEmpty())
        return nullptr;
    QVBoxLayout* lay = nullptr;
    QFrame* card = wcard(parent, lay, QStringLiteral("ref"));
    auto* hd = new QHBoxLayout;
    hd->setSpacing(12);
    const QString tk = jstr(b, "ticker").trimmed();
    if (!tk.isEmpty()) {
        auto* btn = new QPushButton(card);
        btn->setText(QString(tk).replace(QLatin1Char('&'), QStringLiteral("&&")));
        btn->setFlat(true);
        btn->setCursor(Qt::PointingHandCursor);
        btn->setToolTip(QStringLiteral("Mở chi tiết định giá ") + tk);
        btn->setStyleSheet(QStringLiteral("QPushButton { background:transparent; border:none; padding:0; color:%1;"
                                          " font-size:20px; font-weight:bold; font-family:%2; text-align:left; }"
                                          "QPushButton:hover { color:%3; }")
                               .arg(css(c_text()), mono(), css(c_gold())));
        if (HhpWeeklyPage* page = ctx.page)
            QObject::connect(btn, &QPushButton::clicked, page, [page, tk]() { emit page->ticker_activated(tk); });
        hd->addWidget(btn, 0, Qt::AlignVCenter);
    }
    hd->addWidget(flabel(card, esc(jstr(b, "subtitle")), 12, c_muted()), 1, Qt::AlignVCenter);
    const QString verdict = jstr(b, "verdict");
    if (!verdict.trimmed().isEmpty()) {
        const QString vc = jstr(b, "verdict_class");
        QColor fg = c_ink2();
        QColor bg = c_card2();
        if (vc == QLatin1String("add")) {
            fg = c_cheap();
            bg = soft(c_cheap());
        } else if (vc == QLatin1String("trim")) {
            fg = c_rich();
            bg = soft(c_rich());
        }
        auto* pill = new QLabel(card);
        pill->setTextFormat(Qt::PlainText);
        pill->setText(verdict);
        pill->setStyleSheet(QStringLiteral("QLabel { color:%1; background:%2; border-radius:4px; padding:3px 9px;"
                                           " font-size:12px; font-weight:bold; font-family:%3; }")
                                .arg(css(fg), css(bg), mono()));
        hd->addWidget(pill, 0, Qt::AlignVCenter | Qt::AlignRight);
    }
    lay->addLayout(hd);
    const QColor prev = ctx.surface;
    ctx.surface = c_card();
    add_blocks(b.value(QLatin1String("blocks")), card, lay, ctx);
    ctx.surface = prev;
    return card;
}

QWidget* build_block(const QJsonObject& b, QWidget* parent, BuildCtx& ctx) {
    const QString t = jstr(b, "t");
    if (t == QLatin1String("p"))
        return build_p(b, parent);
    if (t == QLatin1String("h3")) {
        const QString text = jstr(b, "text");
        if (text.trimmed().isEmpty())
            return nullptr;
        QLabel* l = flabel(parent, esc(text), 15, tone_color(jstr(b, "tone"), c_text()), true);
        l->setContentsMargins(0, 8, 0, 0);
        return l;
    }
    if (t == QLatin1String("eyebrow")) {
        const QString text = jstr(b, "text");
        if (text.trimmed().isEmpty())
            return nullptr;
        return caps_label(parent, text, 11, tone_color(jstr(b, "tone"), c_muted()));
    }
    if (t == QLatin1String("note"))
        return build_note(b, parent);
    if (t == QLatin1String("table"))
        return build_table(b, parent, ctx);
    if (t == QLatin1String("cards"))
        return build_cards(b, parent, ctx);
    if (t == QLatin1String("card"))
        return build_card(b, parent, ctx);
    if (t == QLatin1String("stats"))
        return build_stats(jarr(b, "items"), parent);
    if (t == QLatin1String("kv"))
        return build_kv(b, parent);
    if (t == QLatin1String("list"))
        return build_list(b, parent);
    if (t == QLatin1String("rule"))
        return hline(parent);
    if (t == QLatin1String("band"))
        return build_band(b, parent, ctx);
    if (t == QLatin1String("dist"))
        return build_dist(b, parent, ctx);
    if (t == QLatin1String("screener"))
        return build_screener(parent, ctx);
    if (t == QLatin1String("advisor"))
        return build_advisor(b, parent, ctx);
    if (t == QLatin1String("voice"))
        return build_voice(b, parent);
    // Unknown type: keep its text, like the script does for unknown elements.
    const QString html = jstr(b, "html");
    if (!html.trimmed().isEmpty())
        return flabel(parent, rich(html, 13), 13, c_text());
    const QString text = jstr(b, "text");
    return text.trimmed().isEmpty() ? nullptr : flabel(parent, esc(text), 13, c_text());
}

// ── Page-level parts ─────────────────────────────────────────────────────────

QWidget* build_meta(const QJsonObject& meta, QWidget* parent) {
    auto* box = new QWidget(parent);
    auto* vl = new QVBoxLayout(box);
    vl->setContentsMargins(0, 0, 0, 0);
    vl->setSpacing(3);
    QStringList parts;
    parts << span(QStringLiteral("color:%1; font-weight:bold;").arg(css(c_gold())), QStringLiteral("BẢN TUẦN")) +
                 QStringLiteral(" kỳ <b>") + esc(or_dash(jstr(meta, "ky_txt"))) + QStringLiteral("</b>");
    const QString rev = jstr(meta, "rev");
    if (!rev.trimmed().isEmpty())
        parts << esc(rev);
    parts << QStringLiteral("định giá chốt <b>") + esc(or_dash(jstr(meta, "data_as_of_txt"))) + QStringLiteral("</b>");
    const QString engine_run = jstr(meta, "engine_run");
    if (!engine_run.trimmed().isEmpty())
        parts << QStringLiteral("engine ") + esc(engine_run);
    const double age = jnum(meta, "age_days");
    if (has(age) && age >= 0) {
        const long days = std::lround(age);
        parts << (days == 0 ? QStringLiteral("hôm nay") : QString::number(days) + QStringLiteral(" ngày trước"));
    }
    vl->addWidget(flabel(box, parts.join(QStringLiteral(" · ")), 12, c_muted()));
    if (jbool(meta, "stale"))
        vl->addWidget(flabel(box, esc(or_dash(jstr(meta, "stale_text"), QStringLiteral("BẢN TUẦN CŨ"))), 12, c_rich(),
                             true));
    QStringList warns;
    for (const QString& w : str_list(meta.value(QLatin1String("warnings"))))
        if (!w.trimmed().isEmpty())
            warns << QStringLiteral("⚠ ") + esc(w);
    if (!warns.isEmpty())
        vl->addWidget(flabel(box, warns.join(QStringLiteral("<br>")), 11, c_muted()));
    return box;
}

/// Evidence chips as one wrapping rich line of pills (tier tag kept, in bold).
QString chips_html(const QJsonArray& chips) {
    QStringList pills;
    for (const QJsonValue& v : chips) {
        const QJsonObject c = v.toObject();
        const QString text = v.isString() ? v.toString() : jstr(c, "text");
        if (text.trimmed().isEmpty())
            continue;
        const QString tone = jstr(c, "tone");
        const QColor fg = tone_color(tone, c_ink2());
        const QColor bg = tone.isEmpty() ? c_card2() : soft(fg, 0.14);
        const QString tier = jstr(c, "tier");
        const bool lead_tier = !tier.isEmpty() && text.startsWith(tier);
        const QString inner = lead_tier ? QStringLiteral("<b>%1</b>").arg(esc(tier)) + esc(text.mid(tier.size()))
                                        : esc(text);
        pills << span(QStringLiteral("color:%1; background-color:%2; font-size:11px; font-family:%3;")
                          .arg(css(fg), css(bg), mono()),
                      QStringLiteral("&nbsp;") + inner + QStringLiteral("&nbsp;"));
    }
    return pills.join(QStringLiteral("&nbsp;&nbsp; "));
}

QWidget* build_masthead(const QJsonObject& issue, QWidget* parent) {
    QStringList kicker;
    for (const QString& s : str_list(issue.value(QLatin1String("kicker"))))
        if (!s.trimmed().isEmpty())
            kicker << esc(caps(s));
    const QString title = jstr(issue, "title");
    const QString lede = jstr(issue, "lede");
    const QString chips = chips_html(jarr(issue, "chips"));
    const QString status = jstr(issue, "status");
    if (kicker.isEmpty() && title.trimmed().isEmpty() && lede.trimmed().isEmpty() && chips.isEmpty() &&
        status.trimmed().isEmpty())
        return nullptr;

    QVBoxLayout* lay = nullptr;
    QFrame* card = wcard(parent, lay, {}, {}, 18);
    lay->setSpacing(8);
    if (!kicker.isEmpty())
        lay->addWidget(eyebrow_label(card, kicker.join(QStringLiteral("&nbsp;&nbsp;·&nbsp;&nbsp;")), 11, c_gold()));
    if (!title.trimmed().isEmpty())
        lay->addWidget(flabel(card, esc(title).replace(QLatin1Char('\n'), QStringLiteral("<br>")), 22, c_text(), true));
    if (!lede.trimmed().isEmpty())
        lay->addWidget(flabel(card, rich(lede, 14), 14, c_ink2()));
    if (!chips.isEmpty())
        lay->addWidget(flabel(card, chips, 11, c_ink2()));
    if (!status.trimmed().isEmpty())
        lay->addWidget(flabel(card, rich(status, 12), 12, c_muted()));
    return card;
}

QLabel* kiem_subhead(QWidget* parent, const QString& plain) {
    QLabel* l = caps_label(parent, plain, 10, c_muted());
    l->setContentsMargins(0, 8, 0, 0);
    return l;
}

QString zone_html(const QString& zone_issue, const QString& zone_live, bool changed) {
    const auto one = [](const QString& z) { return span(color_style(zone_color(z)), esc(zone_short(z))); };
    if (changed)
        return QStringLiteral("<b>%1 → %2</b>").arg(one(zone_issue), one(zone_live));
    return one(zone_live.isEmpty() ? zone_issue : zone_live);
}

void add_kiem_lines(const QJsonArray& kiem, QWidget* card, QVBoxLayout* lay) {
    QVector<Row> rows;
    for (const QJsonValue& v : kiem) {
        const QJsonObject k = v.toObject();
        const QString muc = jstr(k, "muc");
        const QString text = jstr(k, "text");
        if (muc.trimmed().isEmpty() && text.trimmed().isEmpty())
            continue;
        const QJsonValue ok = k.value(QLatin1String("ok"));
        Cell mark;
        mark.width = 16;
        mark.bold = true;
        if (ok.isBool() && ok.toBool()) {
            mark.html = QStringLiteral("✓");
            mark.color = c_cheap();
        } else if (ok.isBool()) {
            mark.html = QStringLiteral("✗");
            mark.color = c_rich();
        } else {
            mark.html = QStringLiteral("•");
            mark.color = c_muted();
        }
        Cell body;
        body.html = QStringLiteral("<b>") + esc(muc) + QStringLiteral("</b>") +
                    (text.trimmed().isEmpty() ? QString() : QStringLiteral(" — ") + esc(text));
        rows.append(Row{{mark, body}, QColor()});
    }
    if (!rows.isEmpty())
        lay->addWidget(flabel(card, table_html({}, rows, 13), 13, c_text()));
}

void add_drift(const QJsonArray& drift, QWidget* card, QVBoxLayout* lay) {
    QVector<Row> rows;
    for (const QJsonValue& v : drift) {
        const QJsonObject d = v.toObject();
        if (d.isEmpty())
            continue;
        const bool changed = jbool(d, "changed");
        Cell muc{esc(jstr(d, "muc")), false, QColor(), changed};
        Cell iss{esc(or_dash(jstr(d, "issue_txt"))), true};
        Cell liv{esc(or_dash(jstr(d, "live_txt"))), true};
        Cell dlt{esc(or_dash(jstr(d, "delta_txt"))), true, changed ? c_gold() : c_muted(), changed};
        rows.append(Row{{muc, iss, liv, dlt}, QColor()});
    }
    if (rows.isEmpty())
        return;
    const QVector<Cell> head = {{esc(QStringLiteral("CHỈ TIÊU"))},
                                {esc(QStringLiteral("BẢN TUẦN")), true},
                                {esc(QStringLiteral("LIVE")), true},
                                {esc(QStringLiteral("Δ")), true}};
    lay->addWidget(kiem_subhead(card, QStringLiteral("Drift chỉ tiêu")));
    lay->addWidget(flabel(card, table_html(head, rows), kTablePx, c_text()));
}

void add_tickers(const QJsonArray& tickers, QWidget* card, QVBoxLayout* lay) {
    QVector<Row> rows;
    for (const QJsonValue& v : tickers) {
        const QJsonObject t = v.toObject();
        const QString tk = jstr(t, "tk");
        if (tk.trimmed().isEmpty())
            continue;
        const bool mine = jbool(t, "mine");
        QString tk_html = span(QStringLiteral("font-family:%1; font-weight:bold;").arg(mono()), esc(tk));
        if (mine)
            tk_html += QLatin1Char(' ') + span(color_style(c_gold()), QStringLiteral("◆"));
        if (jbool(t, "avoid"))
            tk_html += QLatin1Char(' ') + span(color_style(c_rich()), QStringLiteral("⊘"));
        const QString adv = jstr(t, "advisor");
        if (!adv.trimmed().isEmpty())
            tk_html += QLatin1Char(' ') + span(color_style(c_muted()) + QStringLiteral(" font-size:10px;"), esc(adv));
        const bool changed = jbool(t, "changed");
        Row row;
        if (mine)
            row.bg = soft(c_gold(), 0.10);
        row.cells = {Cell{tk_html},
                     Cell{esc(or_dash(jstr(t, "pe_issue_txt"))), true},
                     Cell{esc(or_dash(jstr(t, "pe_live_txt"))), true},
                     Cell{esc(or_dash(jstr(t, "pb_issue_txt"))), true},
                     Cell{esc(or_dash(jstr(t, "pb_live_txt"))), true},
                     Cell{zone_html(jstr(t, "zone_issue"), jstr(t, "zone_live"), changed)}};
        rows.append(row);
    }
    if (rows.isEmpty())
        return;
    const QVector<Cell> head = {{esc(QStringLiteral("MÃ"))},
                                {esc(QStringLiteral("P/E BẢN TUẦN")), true},
                                {esc(QStringLiteral("P/E LIVE")), true},
                                {esc(QStringLiteral("P/B BẢN TUẦN")), true},
                                {esc(QStringLiteral("P/B LIVE")), true},
                                {esc(QStringLiteral("VÙNG"))}};
    lay->addWidget(kiem_subhead(card, QStringLiteral("Mã danh mục · tránh · cố vấn")));
    lay->addWidget(flabel(card, table_html(head, rows), kTablePx, c_text()));
}

void add_baskets(const QJsonArray& baskets, QWidget* card, QVBoxLayout* lay) {
    int total = 0;
    QVector<Row> rows;
    for (const QJsonValue& v : baskets) {
        const QJsonObject bk = v.toObject();
        if (bk.isEmpty())
            continue;
        ++total;
        if (!jbool(bk, "changed"))
            continue;
        QString name = QStringLiteral("<b>") + esc(jstr(bk, "code")) + QStringLiteral("</b>");
        const QString label = jstr(bk, "label");
        if (!label.trimmed().isEmpty())
            name += QStringLiteral("<br>") +
                    span(color_style(c_muted()) + QStringLiteral(" font-size:10px;"), esc(label));
        rows.append(Row{{Cell{name},
                         Cell{esc(or_dash(jstr(bk, "pe_issue_txt"))), true},
                         Cell{esc(or_dash(jstr(bk, "pe_live_txt"))), true, c_gold(), true},
                         Cell{esc(or_dash(jstr(bk, "pb_issue_txt"))), true},
                         Cell{esc(or_dash(jstr(bk, "pb_live_txt"))), true, c_gold(), true}},
                        QColor()});
    }
    if (total == 0)
        return;
    lay->addWidget(kiem_subhead(card, QStringLiteral("Rổ ngành")));
    lay->addWidget(muted_note(card, QString::number(total) + QStringLiteral(" rổ, ") + QString::number(rows.size()) +
                                        QStringLiteral(" đổi vùng")));
    if (rows.isEmpty())
        return;
    const QVector<Cell> head = {{esc(QStringLiteral("RỔ"))},
                                {esc(QStringLiteral("σ P/E BẢN TUẦN")), true},
                                {esc(QStringLiteral("σ P/E LIVE")), true},
                                {esc(QStringLiteral("σ P/B BẢN TUẦN")), true},
                                {esc(QStringLiteral("σ P/B LIVE")), true}};
    lay->addWidget(flabel(card, table_html(head, rows), kTablePx, c_text()));
}

void add_levels(const QJsonArray& levels, QWidget* card, QVBoxLayout* lay) {
    QStringList lines;
    for (const QJsonValue& v : levels) {
        const QJsonObject lv = v.toObject();
        QString level = jstr(lv, "level_txt");
        if (level.trimmed().isEmpty())
            level = fmt_vi(jnum(lv, "level"));
        if (level == QStringLiteral("—"))
            continue;
        QString html = QStringLiteral("Mốc <b>") + esc(level) + QStringLiteral("</b>");
        const QString live = jstr(lv, "live_txt");
        if (!live.trimmed().isEmpty())
            html += QStringLiteral(" — live ") + esc(live);
        const QString gap = (jstr(lv, "side") + QLatin1Char(' ') + jstr(lv, "gap_txt")).trimmed();
        if (!gap.isEmpty())
            html += QStringLiteral(" · ") + esc(gap);
        const QString context = jstr(lv, "context");
        if (!context.trimmed().isEmpty())
            html += QStringLiteral(" · ") + span(color_style(c_muted()), esc(context));
        lines << html;
    }
    if (lines.isEmpty())
        return;
    lay->addWidget(kiem_subhead(card, QStringLiteral("Mốc VN-Index trong bảng hành động")));
    lay->addWidget(flabel(card, lines.join(QStringLiteral("<br>")), 12, c_ink2()));
}

void add_past(const QJsonArray& past, QWidget* card, QVBoxLayout* lay) {
    QStringList lines;
    for (const QJsonValue& v : past) {
        const QJsonObject p = v.toObject();
        const QString date = jstr(p, "date");
        const QString text = jstr(p, "text");
        if (date.trimmed().isEmpty() && text.trimmed().isEmpty())
            continue;
        lines << QStringLiteral("› đã qua mốc ") + esc(or_dash(date)) +
                     (text.trimmed().isEmpty() ? QString() : QStringLiteral(" — ") + esc(text));
    }
    if (lines.isEmpty())
        return;
    lay->addWidget(kiem_subhead(card, QStringLiteral("Mốc đã qua")));
    lay->addWidget(flabel(card, lines.join(QStringLiteral("<br>")), 12, c_ink2()));
}

QWidget* build_kiem(const QJsonValue& engine_v, QWidget* parent) {
    QVBoxLayout* lay = nullptr;
    QFrame* card = wcard(parent, lay, QStringLiteral("ref"));
    lay->addWidget(eyebrow_label(card, esc(QStringLiteral("⚙︎ KIỂM BẢN TUẦN · so với dữ liệu live")), 12, c_gold()));
    if (!engine_v.isObject()) {
        lay->addWidget(muted_note(card, QStringLiteral("[CẦN DATA] engine không chạy")));
        return card;
    }
    const QJsonObject eng = engine_v.toObject();
    add_kiem_lines(jarr(eng, "kiem"), card, lay);
    add_drift(jarr(eng, "drift"), card, lay);
    add_tickers(jarr(eng, "tickers"), card, lay);
    add_baskets(jarr(eng, "baskets"), card, lay);
    add_levels(jarr(eng, "levels"), card, lay);
    add_past(jarr(eng, "past"), card, lay);
    return card;
}

/// Section container: "00A  title  EYEBROW" header, 1 px rule, blocks.
QWidget* build_section(const QJsonObject& sec, QWidget* parent, BuildCtx& ctx) {
    auto* w = new QWidget(parent);
    auto* vl = new QVBoxLayout(w);
    vl->setContentsMargins(0, 14, 0, 0);
    vl->setSpacing(10);
    const QString id = jstr(sec, "id");
    const QString title = jstr(sec, "title");
    const QString eyebrow = jstr(sec, "eyebrow");
    QString head;
    if (!id.trimmed().isEmpty())
        head += span(QStringLiteral("color:%1; font-family:%2; font-size:13px; font-weight:bold;")
                         .arg(css(c_gold()), mono()),
                     esc(id)) +
                QStringLiteral("&nbsp;&nbsp; ");
    head += span(QStringLiteral("font-size:18px; font-weight:bold;"), esc(title));
    if (!eyebrow.trimmed().isEmpty())
        head += QStringLiteral("&nbsp;&nbsp; ") +
                span(QStringLiteral("color:%1; font-size:11px; font-weight:bold;").arg(css(c_muted())),
                     esc(caps(eyebrow)));
    auto* hv = new QVBoxLayout;
    hv->setSpacing(6);
    hv->addWidget(flabel(w, head, 18, c_text()));
    hv->addWidget(hline(w));
    vl->addLayout(hv);
    ctx.surface = c_bg();
    add_blocks(sec.value(QLatin1String("blocks")), w, vl, ctx);
    return w;
}

QString nav_style() {
    return QStringLiteral("QPushButton { background:%1; color:%2; border:1px solid %3; border-radius:4px;"
                          " padding:2px 8px; font-family:%4; font-size:11px; font-weight:bold; }"
                          "QPushButton:hover { border-color:%2; background:%5; }")
        .arg(css(c_card()), css(c_gold()), css(c_line()), mono(), css(soft(c_gold(), 0.12)));
}

} // namespace

// ── HhpWeeklyPage ────────────────────────────────────────────────────────────

HhpWeeklyPage::HhpWeeklyPage(QWidget* parent) : QWidget(parent) {
    setObjectName(QStringLiteral("hhpWeeklyPage"));
    setAttribute(Qt::WA_StyledBackground, true);
    setStyleSheet(QStringLiteral("QWidget#hhpWeeklyPage { background:%1; }").arg(css(c_bg())));
    root_ = new QVBoxLayout(this);
    root_->setContentsMargins(0, 0, 0, 0);
    root_->setSpacing(0);
}

void HhpWeeklyPage::set_payload(const QJsonObject& payload) {
    // Same kỳ (the panel's timed re-read): the rebuilt screener keeps what the user set.
    const QString ky = jstr(jobj(payload, "meta"), "ky");
    std::optional<HhpWeeklyScreener::State> keep;
    if (screener_ && !ky.isEmpty() && ky == ky_)
        keep = screener_->state();
    ky_ = ky;

    screener_.clear(); // the old one dies with the old body
    if (body_) {
        root_->removeWidget(body_);
        body_->hide();
        body_->deleteLater();
        body_ = nullptr;
    }

    body_ = new QWidget(this);
    body_->setObjectName(QStringLiteral("hhpWeeklyBody"));
    body_->setAttribute(Qt::WA_StyledBackground, true);
    body_->setStyleSheet(QStringLiteral("QWidget#hhpWeeklyBody { background:%1; }").arg(css(c_bg())));
    auto* vl = new QVBoxLayout(body_);
    vl->setContentsMargins(18, 14, 18, 24);
    vl->setSpacing(10);
    root_->addWidget(body_);

    const QString error = jstr(payload, "error");
    if (!error.trimmed().isEmpty()) {
        QVBoxLayout* lay = nullptr;
        QFrame* card = wcard(body_, lay, QStringLiteral("down"));
        lay->addWidget(flabel(card, esc(QStringLiteral("Không đọc được bản tuần")), 14, c_rich(), true));
        lay->addWidget(flabel(card, esc(error), 13, c_text()));
        const QString code = jstr(payload, "error_code");
        if (!code.isEmpty())
            lay->addWidget(muted_note(card, code, 11));
        vl->addWidget(card);
        vl->addStretch(1);
        return;
    }

    const QJsonObject meta = jobj(payload, "meta");
    const QJsonObject issue = jobj(payload, "issue");
    const QJsonObject core = jobj(payload, "core");

    BuildCtx ctx;
    ctx.page = this;
    ctx.snapshot = jobj(payload, "snapshot");
    ctx.mine = str_list(core.value(QLatin1String("mine")));
    ctx.avoid = str_list(core.value(QLatin1String("avoid")));
    ctx.issue_dm = short_dm(or_dash(jstr(meta, "data_as_of_txt"), QString()));

    vl->addWidget(build_meta(meta, body_));
    if (issue.isEmpty())
        vl->addWidget(
            muted_note(body_, QStringLiteral("[CẦN DATA] payload không có phần issue — bản tuần không đọc được")));
    if (QWidget* mast = build_masthead(issue, body_))
        vl->addWidget(mast);
    if (QWidget* stats = build_stats(jarr(issue, "stats"), body_))
        vl->addWidget(stats);
    vl->addWidget(build_kiem(payload.value(QLatin1String("engine")), body_));

    struct SectionRef {
        QWidget* widget;
        QString id;
        QString title;
    };
    QVector<SectionRef> sections;
    for (const QJsonValue& v : jarr(issue, "sections")) {
        const QJsonObject sec = v.toObject();
        const bool blank = jstr(sec, "id").trimmed().isEmpty() && jstr(sec, "title").trimmed().isEmpty();
        if (blank && jarr(sec, "blocks").isEmpty())
            continue;
        sections.append({build_section(sec, body_, ctx), jstr(sec, "id"), jstr(sec, "title")});
    }

    if (!sections.isEmpty()) {
        auto* nav = new QWidget(body_);
        auto* nv = new QVBoxLayout(nav);
        nv->setContentsMargins(0, 4, 0, 0);
        nv->setSpacing(4);
        const QString style = nav_style();
        for (int start = 0; start < sections.size(); start += kNavPerRow) {
            auto* row = new QHBoxLayout;
            row->setSpacing(4);
            const int end = std::min(static_cast<int>(sections.size()), start + kNavPerRow);
            for (int i = start; i < end; ++i) {
                const SectionRef& s = sections.at(i);
                const QString id = s.id.trimmed().isEmpty() ? QStringLiteral("§%1").arg(i + 1) : s.id.trimmed();
                auto* btn = new QPushButton(nav);
                btn->setText(QString(id).replace(QLatin1Char('&'), QStringLiteral("&&")));
                btn->setCursor(Qt::PointingHandCursor);
                btn->setStyleSheet(style);
                if (!s.title.trimmed().isEmpty())
                    btn->setToolTip(QStringLiteral("<span>") + esc(s.title) + QStringLiteral("</span>"));
                connect(btn, &QPushButton::clicked, this, [this, target = QPointer<QWidget>(s.widget)]() {
                    if (target)
                        emit section_requested(target);
                });
                row->addWidget(btn);
            }
            row->addStretch(1);
            nv->addLayout(row);
        }
        vl->addWidget(nav);
        for (const SectionRef& s : sections)
            vl->addWidget(s.widget);
    }

    // Footer: the issue's own blocks, the fixed not-advice line, the page's links as plain text.
    vl->addSpacing(8);
    vl->addWidget(hline(body_));
    ctx.surface = c_bg();
    add_blocks(issue.value(QLatin1String("footer")), body_, vl, ctx);
    vl->addWidget(muted_note(body_, kNotAdvice, 11));
    QStringList links;
    for (const QJsonValue& v : jarr(meta, "links")) {
        const QJsonObject l = v.toObject();
        const QString title = or_dash(jstr(l, "title"), jstr(l, "kind"));
        const QString url = jstr(l, "url");
        if (title.trimmed().isEmpty() && url.trimmed().isEmpty())
            continue;
        links << esc(QStringLiteral("↗ ") + title + (url.isEmpty() ? QString() : QStringLiteral(" — ") + url));
    }
    if (!links.isEmpty())
        vl->addWidget(flabel(body_, links.join(QStringLiteral("<br>")), 11, c_muted()));
    vl->addStretch(1);

    screener_ = ctx.screener;
    if (screener_ && keep)
        screener_->restore_state(*keep);
}

QStringList HhpWeeklyPage::csv_header() const {
    return screener_ ? screener_->csv_header() : QStringList{};
}

QVector<QStringList> HhpWeeklyPage::csv_rows() const {
    return screener_ ? screener_->csv_rows() : QVector<QStringList>{};
}

} // namespace fincept::screens::hhp::weekly
