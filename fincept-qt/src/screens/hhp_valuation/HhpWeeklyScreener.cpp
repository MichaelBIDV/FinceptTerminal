// src/screens/hhp_valuation/HhpWeeklyScreener.cpp
// Section 07 of the weekly issue — port of the page's screener script (render() / bar() / the sort
// handler) over the frozen snapshot rows, plus the σ LIVE column. See HhpWeeklyScreener.h; ROW schema
// and filter rules: scripts/hhp_weekly.py docstring. Every data string reaching a rich-text cell is
// escaped; tags are built as contract ihtml and converted by rich().
#include "screens/hhp_valuation/HhpWeeklyScreener.h"

#include "screens/hhp_valuation/HhpWeeklyCommon.h"

#include <QAbstractItemView>
#include <QCheckBox>
#include <QEvent>
#include <QHBoxLayout>
#include <QHeaderView>
#include <QKeyEvent>
#include <QLabel>
#include <QLineEdit>
#include <QPainter>
#include <QPushButton>
#include <QScrollBar>
#include <QSignalBlocker>
#include <QStyledItemDelegate>
#include <QTableWidget>
#include <QTextDocument>
#include <QTimer>
#include <QVBoxLayout>

#include <algorithm>
#include <array>
#include <functional>
#include <utility>
#include <vector>

namespace fincept::screens::hhp::weekly {

namespace {

enum Col {
    ColTk = 0, ColNow, ColMean, ColGauge, ColSigma, ColLive, ColPrice, ColFair, ColUp, ColFwd, ColTp, ColCat, ColCount
};

constexpr int kRoleSigma = Qt::UserRole;    // gauge σ (double)
constexpr int kRoleHtml = Qt::UserRole + 1; // rich-text cell content (RichTextDelegate)
constexpr int kRoleMine = Qt::UserRole + 2; // portfolio row → gold tint

constexpr int kRowHeight = 30;
constexpr int kCellPad = 6;
constexpr int kGaugeW = 126;     // page: 126-px track for −3…+3σ
constexpr int kMaxTableH = 620;  // like the page's max-height box: taller content scrolls inside
constexpr int kTitleChars = 60;  // catalyst title shown before "…"
constexpr double kMineTint = 0.10;
constexpr double kGaugeAlpha = 0.5;

const char* const kMono = "font-family:'Menlo','Monaco','Courier New',monospace;";

QColor selected_bg() { return QColor(0x1c, 0x20, 0x27); }

QString metric_label(const QString& metric) {
    return metric == QLatin1String("pb") ? QStringLiteral("P/B") : QStringLiteral("P/E");
}

/// Page data-k of a sortable column; "" = not sortable (gauge, catalyst — as on the page).
QString sort_key_of(int col) {
    switch (col) {
    case ColTk:
        return QStringLiteral("t");
    case ColNow:
        return QStringLiteral("now");
    case ColMean:
        return QStringLiteral("mean");
    case ColSigma:
        return QStringLiteral("sigma");
    case ColLive:
        return QStringLiteral("live");
    case ColPrice:
        return QStringLiteral("p");
    case ColFair:
        return QStringLiteral("fair");
    case ColUp:
        return QStringLiteral("up");
    case ColFwd:
        return QStringLiteral("fpe");
    case ColTp:
        return QStringLiteral("tp");
    default:
        return {};
    }
}

// ── One ROW seen through the active metric ───────────────────────────────────

struct RowView {
    QString t;
    QString uni; ///< "30" | "100" | ""
    double p = kNaN;
    double now = kNaN, mean = kNaN, sigma = kNaN, fair = kNaN, up = kNaN;
    QString zone; ///< issue zone label, e.g. "RẺ (<−1σ)"
    bool reliable = false;
    double fwd = kNaN, roe = kNaN, tp = kNaN, tp_up = kNaN;
    QString rating, fwd_src;
    QString rec, consensus, cat_src, cat_date, cat_title;
    double n_reports = kNaN;
    double live_now = kNaN, live_sigma = kNaN, live_price = kNaN;
};

RowView view_of(const QJsonObject& r, const QString& metric, const QJsonObject& live) {
    RowView v;
    v.t = r.value(QStringLiteral("t")).toString();
    v.uni = r.value(QStringLiteral("b")).toString();
    v.p = num(r.value(QStringLiteral("p")));
    const QJsonArray b = r.value(metric).toArray();
    v.now = num(b.at(0));
    v.mean = num(b.at(1));
    v.sigma = num(b.at(2));
    v.zone = b.at(3).toString();
    v.reliable = b.at(4).toBool();
    v.fair = num(b.at(5));
    v.up = num(b.at(6));
    const QJsonArray f = r.value(QStringLiteral("f")).toArray();
    v.fwd = num(f.at(metric == QLatin1String("pb") ? 1 : 0));
    v.roe = num(f.at(2));
    v.tp = num(f.at(3));
    v.rating = f.at(4).toString();
    v.fwd_src = f.at(5).toString();
    v.tp_up = num(f.at(6));
    const QJsonArray c = r.value(QStringLiteral("c")).toArray();
    v.rec = c.at(0).toString();
    v.consensus = c.at(1).toString();
    v.n_reports = num(c.at(2));
    v.cat_src = c.at(3).toString();
    v.cat_date = c.at(4).toString();
    v.cat_title = c.at(5).toString();
    const QJsonObject lv = live.value(v.t).toObject();
    const QJsonArray lm = lv.value(metric).toArray();
    v.live_now = num(lm.at(0));
    v.live_sigma = num(lm.at(1));
    v.live_price = num(lv.value(QStringLiteral("price")));
    return v;
}

/// Page's val(r, k): the number a sortable column sorts on (NaN = null → always last).
double sort_value(const RowView& v, const QString& key) {
    if (key == QLatin1String("now"))
        return v.now;
    if (key == QLatin1String("mean"))
        return v.mean;
    if (key == QLatin1String("sigma"))
        return v.sigma;
    if (key == QLatin1String("live"))
        return v.live_sigma;
    if (key == QLatin1String("p"))
        return v.p;
    if (key == QLatin1String("fair"))
        return v.fair;
    if (key == QLatin1String("up"))
        return v.up;
    if (key == QLatin1String("fpe"))
        return v.fwd;
    if (key == QLatin1String("tp"))
        return v.tp;
    return kNaN;
}

/// ≤−1 / neutral / ≥+1 — a σ live "changed zone" when this bucket differs from the issue's.
int zone_bucket(double s) {
    return s <= -1.0 ? -1 : (s >= 1.0 ? 1 : 0);
}

bool live_zone_changed(const RowView& v) {
    return has(v.sigma) && has(v.live_sigma) && zone_bucket(v.sigma) != zone_bucket(v.live_sigma);
}

// ── Display strings (table and CSV share them) ───────────────────────────────

QString sigma_txt(double s) {
    return has(s) ? fmt_dec(s, 2, true) + QStringLiteral("σ") : QStringLiteral("—");
}

QString pct_txt(double v) {
    return has(v) ? fmt_dec(v, 1, true) + QLatin1Char('%') : QStringLiteral("—");
}

QString live_txt(const RowView& v) {
    if (!has(v.live_sigma))
        return QStringLiteral("—");
    return (live_zone_changed(v) ? QStringLiteral("→ ") : QString()) + sigma_txt(v.live_sigma);
}

QString fwd_tag(const RowView& v) {
    if (v.fwd_src == QLatin1String("vietcap"))
        return QStringLiteral("V");
    if (v.fwd_src.isEmpty())
        return {};
    return QStringLiteral("S");
}

QString rating_tag(const RowView& v) {
    return v.rating.left(1);
}

QString with_tag(const QString& value, const QString& tag) {
    return tag.isEmpty() ? value : value + QLatin1Char(' ') + tag;
}

QString cat_head(const RowView& v) {
    return QStringList{v.cat_src, v.cat_date}.join(QLatin1Char(' ')).trimmed();
}

QString cat_txt(const RowView& v) {
    if (v.cat_title.isEmpty())
        return QStringLiteral("—");
    const QString head = cat_head(v);
    return head.isEmpty() ? v.cat_title : head + QLatin1Char(' ') + v.cat_title;
}

QString colored(const QString& text, const QColor& c, const QString& extra = {}) {
    return QStringLiteral("<span style=\"color:%1;%2\">%3</span>").arg(css(c), extra, esc(text));
}

/// Contract ihtml tag → Qt rich text (" " + pill).
QString tag_html(const QString& cls, const QString& text) {
    return QStringLiteral("&nbsp;") + rich(QStringLiteral("<span class=\"%1\">%2</span>").arg(cls, esc(text)), 13);
}

// ── Delegates (same approach as HhpScreenerTable) ────────────────────────────

/// Paints the selected-row colour (or the portfolio tint) itself and drops State_Selected, so per-cell
/// colours survive on the selected row.
class RowDelegate : public QStyledItemDelegate {
  public:
    using QStyledItemDelegate::QStyledItemDelegate;

    void paint(QPainter* p, const QStyleOptionViewItem& option, const QModelIndex& index) const override {
        QStyleOptionViewItem opt(option);
        if (opt.state & QStyle::State_Selected) {
            p->fillRect(opt.rect, selected_bg());
            opt.state &= ~QStyle::State_Selected;
        } else if (index.data(kRoleMine).toBool()) {
            p->fillRect(opt.rect, soft(c_gold(), kMineTint));
        }
        opt.state &= ~QStyle::State_HasFocus;
        QStyledItemDelegate::paint(p, opt, index);
    }
};

/// Cell whose kRoleHtml holds rich text (ticker + tags, number + tag, catalyst). The document's default
/// font is the item font, so an AVOID row's struck-out ticker font strikes the whole first cell, like the
/// page's `tr.avoid td:first-child`.
class RichTextDelegate : public RowDelegate {
  public:
    using RowDelegate::RowDelegate;

    void paint(QPainter* p, const QStyleOptionViewItem& option, const QModelIndex& index) const override {
        RowDelegate::paint(p, option, index);
        const QString html = index.data(kRoleHtml).toString();
        if (html.isEmpty())
            return;
        QStyleOptionViewItem opt(option);
        initStyleOption(&opt, index);
        QTextDocument doc;
        doc.setDocumentMargin(0);
        doc.setDefaultFont(opt.font);
        doc.setHtml(html);
        const QRectF area = QRectF(option.rect).adjusted(kCellPad, 0, -kCellPad, 0);
        const qreal x = (opt.displayAlignment & Qt::AlignRight) ? area.right() - doc.idealWidth() : area.left();
        const qreal y = area.top() + (area.height() - doc.size().height()) / 2.0;
        p->save();
        p->setClipRect(area);
        p->translate(x, y);
        doc.drawContents(p);
        p->restore();
    }
};

/// Page's bar(s): −3…+3σ track, floor/up/down/ceil segments, centre line, dot in the zone colour.
class GaugeDelegate : public RowDelegate {
  public:
    using RowDelegate::RowDelegate;

    void paint(QPainter* p, const QStyleOptionViewItem& option, const QModelIndex& index) const override {
        RowDelegate::paint(p, option, index);
        const QVariant v = index.data(kRoleSigma);
        if (!v.isValid())
            return;
        const double s = v.toDouble();
        if (!has(s))
            return;
        const qreal w = std::min<qreal>(kGaugeW, option.rect.width() - 2 * kCellPad);
        if (w <= 12)
            return;
        const qreal left = option.rect.left() + kCellPad;
        const qreal cy = option.rect.top() + option.rect.height() / 2.0;
        const auto x_of = [left, w](double sig) { return left + (std::clamp(sig, -3.0, 3.0) + 3.0) / 6.0 * w; };

        p->save();
        p->setRenderHint(QPainter::Antialiasing, true);
        const QRectF track(left, cy - 2, w, 4);
        p->fillRect(track, c_card2());
        const auto seg = [&](double a, double b, const QColor& c) {
            p->fillRect(QRectF(QPointF(x_of(a), track.top()), QPointF(x_of(b), track.bottom())), c);
        };
        seg(-3, -2, soft(c_floor(), kGaugeAlpha));
        seg(-2, -1, soft(c_cheap(), kGaugeAlpha));
        seg(1, 2, soft(c_rich(), kGaugeAlpha));
        seg(2, 3, soft(c_ceil(), kGaugeAlpha));
        QColor mid = c_muted();
        mid.setAlphaF(0.6f);
        p->setPen(QPen(mid, 1.0));
        p->drawLine(QPointF(x_of(0), cy - 4.5), QPointF(x_of(0), cy + 4.5));
        p->setPen(Qt::NoPen);
        p->setBrush(sigma_color(s));
        p->drawEllipse(QPointF(x_of(s), cy), 3.6, 3.6);
        p->restore();
    }
};

QTableWidgetItem* make_item(const QString& text, const QColor& color, bool mine, Qt::Alignment align = Qt::AlignLeft) {
    auto* it = new QTableWidgetItem(text);
    it->setFlags(Qt::ItemIsSelectable | Qt::ItemIsEnabled);
    it->setForeground(color);
    it->setTextAlignment(align | Qt::AlignVCenter);
    it->setData(kRoleMine, mine);
    return it;
}

QTableWidgetItem* make_rich_item(const QString& html, bool mine, Qt::Alignment align = Qt::AlignLeft) {
    auto* it = make_item(QString(), c_text(), mine, align);
    it->setData(kRoleHtml, html);
    return it;
}

void fill_row(QTableWidget* t, int row, const RowView& v, bool mine, bool avoid, const QString& metric,
              const QString& live_as_of) {
    const QFont base = t->font();
    QFont bold = base;
    bold.setBold(true);
    const QString m = metric_label(metric);

    // Mã (+VN30/V100, "band lỏng"): mine = gold ticker; avoid = red, struck through.
    const QColor tk_col = mine ? c_gold() : (avoid ? c_rich() : c_text());
    QString tk_html = colored(v.t, tk_col, QStringLiteral(" font-weight:bold; ") + QLatin1String(kMono));
    if (v.uni == QLatin1String("30"))
        tk_html += tag_html(QStringLiteral("tag-p"), QStringLiteral("VN30"));
    else if (v.uni == QLatin1String("100"))
        tk_html += tag_html(QStringLiteral("tag-p"), QStringLiteral("V100"));
    if (!v.reliable)
        tk_html += tag_html(QStringLiteral("tag"), QStringLiteral("band lỏng"));
    auto* tk = make_rich_item(tk_html, mine);
    QFont tk_font = base;
    tk_font.setStrikeOut(avoid && !mine);
    tk->setFont(tk_font);
    QStringList tk_tip{QStringLiteral("Bấm để mở chart định giá P/E · P/B")};
    if (mine)
        tk_tip << QStringLiteral("Danh mục tham chiếu của bản tuần");
    else if (avoid)
        tk_tip << QStringLiteral("Nhóm AVOID của bản tuần");
    if (!v.reliable)
        tk_tip << QStringLiteral("Band lỏng: hệ số biến thiên sd/μ ≥ 0,6 — dải giá %1 vô nghĩa").arg(m);
    tk->setToolTip(tk_tip.join(QLatin1Char('\n')));
    t->setItem(row, ColTk, tk);

    t->setItem(row, ColNow, make_item(fmt_dec(v.now), c_text(), mine, Qt::AlignRight));
    t->setItem(row, ColMean, make_item(fmt_dec(v.mean), c_muted(), mine, Qt::AlignRight));

    auto* gauge = make_item(QString(), c_text(), mine);
    gauge->setData(kRoleSigma, v.sigma);
    gauge->setToolTip(
        QStringLiteral("%1 %2 · %3").arg(m, sigma_txt(v.sigma), v.zone.isEmpty() ? QStringLiteral("—") : v.zone));
    t->setItem(row, ColGauge, gauge);

    auto* sig = make_item(sigma_txt(v.sigma), sigma_color(v.sigma), mine, Qt::AlignRight);
    sig->setFont(bold);
    sig->setToolTip(v.reliable ? v.zone : v.zone + QStringLiteral("\nBand lỏng — σ kém tin, đọc thước còn lại"));
    t->setItem(row, ColSigma, sig);

    const bool changed = live_zone_changed(v);
    auto* live =
        make_item(live_txt(v), has(v.live_sigma) ? sigma_color(v.live_sigma) : c_muted(), mine, Qt::AlignRight);
    if (changed)
        live->setFont(bold);
    if (has(v.live_sigma)) {
        QString tip = QStringLiteral("σ live %1: %2 %3 · %4")
                          .arg(live_as_of, m, fmt_dec(v.live_now), sigma_txt(v.live_sigma));
        if (changed)
            tip += QStringLiteral("\nĐổi vùng so với bản tuần: %1 → %2")
                       .arg(sigma_txt(v.sigma), sigma_txt(v.live_sigma));
        live->setToolTip(tip);
    } else {
        live->setToolTip(QStringLiteral("Chưa có σ live cho mã này"));
    }
    t->setItem(row, ColLive, live);

    auto* price = make_item(fmt_vi(v.p), c_text(), mine, Qt::AlignRight);
    if (has(v.live_price))
        price->setToolTip(QStringLiteral("Giá bản tuần · live %1: %2").arg(live_as_of, fmt_vi(v.live_price)));
    t->setItem(row, ColPrice, price);
    t->setItem(row, ColFair, make_item(fmt_vi(v.fair), c_text(), mine, Qt::AlignRight));
    t->setItem(row, ColUp,
               make_item(pct_txt(v.up), has(v.up) && v.up > 0 ? c_cheap() : c_muted(), mine, Qt::AlignRight));

    QString fwd_html = colored(fmt_dec(v.fwd), c_text());
    if (!fwd_tag(v).isEmpty())
        fwd_html += tag_html(QStringLiteral("tag"), fwd_tag(v));
    auto* fwd = make_rich_item(fwd_html, mine, Qt::AlignRight);
    QString fwd_tip = QStringLiteral("%1 dự phóng 2026F — V = Vietcap IQ, S = S&P CapIQ snapshot").arg(m);
    if (has(v.roe))
        fwd_tip += QStringLiteral(" · ROE ") + fmt_dec(v.roe, 1) + QLatin1Char('%');
    fwd->setToolTip(fwd_tip);
    t->setItem(row, ColFwd, fwd);

    QString tp_html = colored(fmt_vi(v.tp), c_text());
    if (!v.rating.isEmpty())
        tp_html += tag_html(QStringLiteral("tag-f"), rating_tag(v));
    auto* tp = make_rich_item(tp_html, mine, Qt::AlignRight);
    QStringList tp_tip{QStringLiteral("TP ") + fmt_vi(v.tp)};
    if (!v.rating.isEmpty())
        tp_tip << v.rating;
    if (has(v.tp_up))
        tp_tip << QStringLiteral("upside ") + pct_txt(v.tp_up);
    tp_tip << QStringLiteral("quan điểm bên bán");
    tp->setToolTip(tp_tip.join(QStringLiteral(" · ")));
    t->setItem(row, ColTp, tp);

    if (v.cat_title.isEmpty()) {
        t->setItem(row, ColCat, make_item(QStringLiteral("—"), c_muted(), mine));
    } else {
        QString title = v.cat_title.left(kTitleChars);
        if (v.cat_title.size() > kTitleChars)
            title += QStringLiteral("…");
        const QString head = cat_head(v);
        QString html = head.isEmpty() ? QString() : colored(head, c_muted(), QStringLiteral(" font-size:11px;")) +
                                                        QStringLiteral("&nbsp;");
        html += colored(title, c_text(), QStringLiteral(" font-size:12px;"));
        auto* cat = make_rich_item(html, mine);
        QStringList tip{v.cat_title};
        QStringList meta;
        for (const QString& s : {v.cat_src, v.cat_date, rec_display(v.rec), v.consensus})
            if (!s.isEmpty())
                meta << s;
        if (has(v.n_reports))
            meta << QStringLiteral("%1 báo cáo").arg(static_cast<int>(v.n_reports));
        if (!meta.isEmpty())
            tip << meta.join(QStringLiteral(" · "));
        cat->setToolTip(tip.join(QLatin1Char('\n')));
        t->setItem(row, ColCat, cat);
    }
}

// ── Controls look (copied from HhpValuationPanel's pill_style / screener bar) ─

QString seg_style(bool on) {
    if (on)
        return QStringLiteral("QPushButton { background:%1; color:#1a1208; font-weight:bold; border-radius:3px;"
                              " padding:2px 8px; border:1px solid %1; }")
            .arg(css(c_gold()));
    return QStringLiteral("QPushButton { background: rgba(255,255,255,0.06); color: #cbd5e1; border-radius: 3px;"
                          " padding: 2px 8px; border: 1px solid rgba(255,255,255,0.12); }"
                          "QPushButton:hover { background: rgba(255,255,255,0.12); color: #ffffff; }");
}

/// Calls `fn` for key presses on `target`; `fn` returns true when it handled the key.
class KeyHook : public QObject {
  public:
    KeyHook(QObject* target, std::function<bool(QKeyEvent*)> fn) : QObject(target), fn_(std::move(fn)) {
        target->installEventFilter(this);
    }

    bool eventFilter(QObject* obj, QEvent* ev) override {
        if (ev->type() == QEvent::KeyPress && fn_(static_cast<QKeyEvent*>(ev)))
            return true;
        return QObject::eventFilter(obj, ev);
    }

  private:
    std::function<bool(QKeyEvent*)> fn_;
};

} // namespace

// ── Construction ─────────────────────────────────────────────────────────────

HhpWeeklyScreener::HhpWeeklyScreener(QWidget* parent) : QWidget(parent) {
    auto* root = new QVBoxLayout(this);
    root->setContentsMargins(0, 0, 0, 0);
    root->setSpacing(8);

    // Controls: search · [P/E|P/B] · [Tất cả|VN30|VN100|Danh mục|Chỉ RẺ] · band đáng tin · count.
    auto* bar = new QWidget(this);
    auto* bl = new QHBoxLayout(bar);
    bl->setContentsMargins(0, 2, 0, 2);
    bl->setSpacing(12);

    search_ = new QLineEdit(bar);
    search_->setPlaceholderText(tr("Tìm mã…"));
    search_->setMinimumWidth(140);
    search_->setMaximumWidth(220);
    search_->setClearButtonEnabled(true);
    search_->setStyleSheet(QStringLiteral("QLineEdit { background:%1; color:%2; border:1px solid %3;"
                                          " border-radius:8px; padding:4px 10px; font-size:12px; }"
                                          "QLineEdit:focus { border-color:%4; }")
                               .arg(css(c_card()), css(c_text()), css(c_line()), css(c_gold())));
    connect(search_, &QLineEdit::textChanged, this, [this]() { rebuild(); });
    bl->addWidget(search_);

    const auto add_group = [this, bar, bl](const std::vector<std::pair<QString, QString>>& items,
                                           QVector<QPushButton*>& out, bool is_metric) {
        auto* group = new QWidget(bar);
        auto* gl = new QHBoxLayout(group);
        gl->setContentsMargins(0, 0, 0, 0);
        gl->setSpacing(3);
        for (const auto& [key, label] : items) {
            auto* btn = new QPushButton(label, group);
            btn->setFixedHeight(26);
            btn->setCursor(Qt::PointingHandCursor);
            btn->setProperty("seg_key", key);
            connect(btn, &QPushButton::clicked, this, [this, key, is_metric]() {
                if (is_metric)
                    metric_ = key;
                else
                    filter_ = key;
                restyle_segments();
                rebuild();
            });
            gl->addWidget(btn);
            out.append(btn);
        }
        bl->addWidget(group);
    };
    add_group({{QStringLiteral("pe"), QStringLiteral("P/E")}, {QStringLiteral("pb"), QStringLiteral("P/B")}},
              metric_btns_, true);
    add_group({{QStringLiteral("all"), tr("Tất cả")},
               {QStringLiteral("30"), QStringLiteral("VN30")},
               {QStringLiteral("100"), QStringLiteral("VN100")},
               {QStringLiteral("mine"), tr("Danh mục")},
               {QStringLiteral("cheap"), tr("Chỉ RẺ")}},
              filter_btns_, false);

    reliable_ = new QCheckBox(tr("chỉ band đáng tin"), bar);
    reliable_->setChecked(reliable_only_);
    reliable_->setCursor(Qt::PointingHandCursor);
    reliable_->setStyleSheet(
        QStringLiteral("QCheckBox { color:%1; font-size:12px; background:transparent; spacing:6px; }"
                       "QCheckBox::indicator { width:13px; height:13px; border:1px solid %2; border-radius:3px;"
                       " background:%3; }"
                       "QCheckBox::indicator:checked { background:%4; border-color:%4; }")
            .arg(css(c_muted()), css(c_neutral()), css(c_card()), css(c_gold())));
    connect(reliable_, &QCheckBox::toggled, this, [this](bool on) {
        reliable_only_ = on;
        rebuild();
    });
    bl->addWidget(reliable_);

    bl->addStretch(1);
    count_ = new QLabel(bar);
    count_->setTextFormat(Qt::PlainText);
    count_->setStyleSheet(QStringLiteral("QLabel { color:%1; font-size:11px; font-weight:bold; letter-spacing:1px;"
                                         " background:transparent; }")
                              .arg(css(c_muted())));
    bl->addWidget(count_);
    root->addWidget(bar);

    // Table.
    table_ = new QTableWidget(this);
    table_->setColumnCount(ColCount);
    for (int c = 0; c < ColCount; ++c)
        table_->setHorizontalHeaderItem(c, new QTableWidgetItem);
    for (int c : {ColNow, ColMean, ColSigma, ColLive, ColPrice, ColFair, ColUp, ColFwd, ColTp})
        table_->horizontalHeaderItem(c)->setTextAlignment(Qt::AlignRight | Qt::AlignVCenter);
    table_->horizontalHeaderItem(ColSigma)->setToolTip(
        tr("Số độ lệch chuẩn so với trung bình lịch sử của CHÍNH mã — ảnh chụp bản tuần"));
    table_->horizontalHeaderItem(ColFwd)->setToolTip(
        tr("Dự phóng 2026F — V = Vietcap IQ coverage, S = S&P CapIQ snapshot (quan điểm bên bán)"));
    table_->horizontalHeaderItem(ColTp)->setToolTip(tr("Giá mục tiêu bên bán + khuyến nghị (chữ đầu)"));

    table_->setSortingEnabled(false);
    table_->setEditTriggers(QAbstractItemView::NoEditTriggers);
    table_->setSelectionBehavior(QAbstractItemView::SelectRows);
    table_->setSelectionMode(QAbstractItemView::SingleSelection);
    table_->setShowGrid(false);
    table_->setWordWrap(false);
    table_->setCornerButtonEnabled(false);
    table_->setTextElideMode(Qt::ElideRight);
    table_->setHorizontalScrollBarPolicy(Qt::ScrollBarAsNeeded);
    table_->setVerticalScrollBarPolicy(Qt::ScrollBarAsNeeded);
    table_->setHorizontalScrollMode(QAbstractItemView::ScrollPerPixel);
    table_->setVerticalScrollMode(QAbstractItemView::ScrollPerPixel);
    table_->setMouseTracking(true);
    table_->viewport()->setMouseTracking(true);

    QFont f = table_->font();
    f.setPixelSize(13);
    table_->setFont(f);

    table_->verticalHeader()->setVisible(false);
    table_->verticalHeader()->setSectionResizeMode(QHeaderView::Fixed);
    table_->verticalHeader()->setDefaultSectionSize(kRowHeight);

    QHeaderView* hh = table_->horizontalHeader();
    hh->setDefaultAlignment(Qt::AlignLeft | Qt::AlignVCenter);
    hh->setSectionsClickable(true);
    hh->setHighlightSections(false);
    hh->setSortIndicatorShown(false); // direction is drawn as ▲/▼ in the label
    hh->setStretchLastSection(true);
    hh->setMinimumSectionSize(40);
    const std::array<int, ColCount> widths = {168, 66, 64, 146, 82, 92, 78, 84, 86, 88, 100, 320};
    for (int c = 0; c < ColCount; ++c)
        hh->resizeSection(c, widths[static_cast<size_t>(c)]);

    table_->setItemDelegate(new RowDelegate(table_));
    table_->setItemDelegateForColumn(ColGauge, new GaugeDelegate(table_));
    for (int c : {ColTk, ColFwd, ColTp, ColCat})
        table_->setItemDelegateForColumn(c, new RichTextDelegate(table_));

    table_->setStyleSheet(
        QStringLiteral("QTableWidget { background:%1; color:%2; border:1px solid %3; outline:0; font-size:13px; }"
                       "QTableWidget::item { border-bottom: 1px solid %3; padding: 0 6px; }"
                       "QHeaderView { background:%1; border:none; }"
                       "QHeaderView::section { background:%1; color:%4; font-size:10px; font-weight:700;"
                       " border:none; border-bottom:1px solid %3; padding:6px 6px; }"
                       "QHeaderView::section:hover { color:%5; }"
                       "QScrollBar:horizontal { background:%1; height:10px; margin:0; }"
                       "QScrollBar::handle:horizontal { background:%3; border-radius:4px; min-width:40px; }"
                       "QScrollBar:vertical { background:%1; width:10px; margin:0; }"
                       "QScrollBar::handle:vertical { background:%3; border-radius:4px; min-height:40px; }"
                       "QScrollBar::add-line, QScrollBar::sub-line { width:0; height:0; }"
                       "QScrollBar::add-page, QScrollBar::sub-page { background:none; }")
            .arg(css(c_bg()), css(c_text()), css(c_line()), css(c_muted()), css(c_gold())));

    connect(hh, &QHeaderView::sectionClicked, this, [this](int column) {
        const QString key = sort_key_of(column);
        if (key.isEmpty())
            return;
        if (key == sort_key_) {
            sort_dir_ = -sort_dir_;
        } else {
            sort_key_ = key;
            sort_dir_ = 1; // page: a new column always starts ascending
        }
        rebuild();
    });

    const auto activate = [this](int row) {
        if (row < 0 || row >= shown_.size())
            return; // also covers the "no match" placeholder row
        const QString tk = shown_.at(row).value(QStringLiteral("t")).toString();
        if (!tk.isEmpty())
            emit ticker_activated(tk);
    };
    connect(table_, &QTableWidget::cellClicked, this, [activate](int row, int column) {
        if (column == ColTk)
            activate(row);
    });
    // A double-click on the ticker cell already fired on the first click.
    connect(table_, &QTableWidget::cellDoubleClicked, this, [activate](int row, int column) {
        if (column != ColTk)
            activate(row);
    });
    // Enter/Return: QAbstractItemView does not emit activated() for them on macOS.
    new KeyHook(table_, [this, activate](QKeyEvent* e) {
        if (e->key() != Qt::Key_Return && e->key() != Qt::Key_Enter)
            return false;
        const int row = table_->currentRow();
        if (row < 0 || row >= shown_.size())
            return false;
        activate(row);
        return true;
    });
    connect(table_, &QAbstractItemView::entered, this, [this](const QModelIndex& idx) {
        const bool link = idx.column() == ColTk && idx.row() < shown_.size();
        table_->viewport()->setCursor(link ? Qt::PointingHandCursor : Qt::ArrowCursor);
    });
    connect(table_, &QAbstractItemView::viewportEntered, this, [this]() { table_->viewport()->unsetCursor(); });
    root->addWidget(table_);

    foot_ = new QLabel(this);
    foot_->setTextFormat(Qt::PlainText);
    foot_->setWordWrap(true);
    foot_->setStyleSheet(
        QStringLiteral("QLabel { color:%1; font-size:11px; background:transparent; }").arg(css(c_muted())));
    root->addWidget(foot_);
    root->addStretch(1); // extra height stays below the footer, never between controls and table

    restyle_segments();
    rebuild();
}

void HhpWeeklyScreener::set_data(const QJsonArray& rows, const QJsonObject& live, const QStringList& mine,
                                 const QStringList& avoid, const QString& as_of_txt, const QString& live_as_of_txt) {
    rows_ = rows;
    live_ = live;
    mine_ = QSet<QString>(mine.begin(), mine.end());
    avoid_ = QSet<QString>(avoid.begin(), avoid.end());
    as_of_txt_ = as_of_txt;
    live_as_of_txt_ = live_as_of_txt;
    rebuild();
}

HhpWeeklyScreener::State HhpWeeklyScreener::state() const {
    State s;
    s.metric = metric_;
    s.filter = filter_;
    s.reliable_only = reliable_only_;
    s.sort_key = sort_key_;
    s.sort_dir = sort_dir_;
    s.search = search_->text();
    s.search_focused = search_->window()->focusWidget() == search_;
    return s;
}

void HhpWeeklyScreener::restore_state(const State& s) {
    const auto has_key = [](const QVector<QPushButton*>& btns, const QString& key) {
        return std::any_of(btns.begin(), btns.end(),
                           [&key](const QPushButton* b) { return b->property("seg_key").toString() == key; });
    };
    if (has_key(metric_btns_, s.metric))
        metric_ = s.metric;
    if (has_key(filter_btns_, s.filter))
        filter_ = s.filter;
    reliable_only_ = s.reliable_only;
    for (int c = 0; c < ColCount; ++c) {
        if (!s.sort_key.isEmpty() && sort_key_of(c) == s.sort_key) {
            sort_key_ = s.sort_key;
            sort_dir_ = s.sort_dir < 0 ? -1 : 1;
            break;
        }
    }
    {
        const QSignalBlocker block_reliable(reliable_);
        const QSignalBlocker block_search(search_);
        reliable_->setChecked(reliable_only_);
        search_->setText(s.search);
    }
    restyle_segments();
    rebuild();
    // A freshly built screener is not shown yet; take the focus once it is.
    if (s.search_focused)
        QTimer::singleShot(0, search_, [box = search_]() { box->setFocus(Qt::OtherFocusReason); });
}

void HhpWeeklyScreener::restyle_segments() {
    for (QPushButton* b : metric_btns_)
        b->setStyleSheet(seg_style(b->property("seg_key").toString() == metric_));
    for (QPushButton* b : filter_btns_)
        b->setStyleSheet(seg_style(b->property("seg_key").toString() == filter_));
}

// ── Filter + sort + fill (page: render()) ────────────────────────────────────

void HhpWeeklyScreener::rebuild() {
    if (!table_)
        return;
    const int cur = table_->currentRow();
    const QString keep_tk =
        (cur >= 0 && cur < shown_.size()) ? shown_.at(cur).value(QStringLiteral("t")).toString() : QString();
    const QString q = search_ ? search_->text().trimmed() : QString();

    QVector<std::pair<QJsonObject, RowView>> out;
    out.reserve(rows_.size());
    for (const QJsonValue& rv : rows_) {
        const QJsonObject r = rv.toObject();
        const RowView v = view_of(r, metric_, live_);
        if (!has(v.sigma))
            continue;
        if (reliable_only_ && !v.reliable)
            continue;
        if (!q.isEmpty() && !v.t.contains(q, Qt::CaseInsensitive))
            continue;
        if (filter_ == QLatin1String("30") && v.uni != QLatin1String("30"))
            continue;
        if (filter_ == QLatin1String("100") && v.uni != QLatin1String("30") && v.uni != QLatin1String("100"))
            continue;
        if (filter_ == QLatin1String("mine") && !mine_.contains(v.t))
            continue;
        if (filter_ == QLatin1String("cheap") && !(v.sigma <= -1.0))
            continue;
        out.append({r, v});
    }

    // Nulls last whichever way the column is sorted; ties keep the issue's row order.
    const bool asc = sort_dir_ > 0;
    if (sort_key_ == QLatin1String("t")) {
        std::stable_sort(out.begin(), out.end(), [asc](const auto& a, const auto& b) {
            const QString& x = a.second.t;
            const QString& y = b.second.t;
            if (x.isEmpty() || y.isEmpty())
                return !x.isEmpty() && y.isEmpty();
            const int c = QString::compare(x, y, Qt::CaseInsensitive);
            return asc ? c < 0 : c > 0;
        });
    } else {
        const QString key = sort_key_;
        std::stable_sort(out.begin(), out.end(), [asc, &key](const auto& a, const auto& b) {
            const double x = sort_value(a.second, key), y = sort_value(b.second, key);
            if (!has(x) || !has(y))
                return has(x) && !has(y);
            return asc ? x < y : x > y;
        });
    }

    shown_.clear();
    shown_.reserve(out.size());
    for (const auto& pr : out)
        shown_.append(pr.first);

    // Headers: page labels, ▲/▼ on the sorted column.
    const QString m = metric_label(metric_);
    const std::array<QString, ColCount> heads = {
        QStringLiteral("MÃ"),     QStringLiteral("RATIO"),  QStringLiteral("μ"),
        QStringLiteral("VỊ THẾ  RẺ ◄ ► ĐẮT"), QStringLiteral("σ"), QStringLiteral("σ LIVE"),
        QStringLiteral("GIÁ"),    QStringLiteral("GIÁ TB"), QStringLiteral("→TB"),
        QStringLiteral("FWD 26F"), QStringLiteral("TP"),    QStringLiteral("CATALYST MỚI NHẤT")};
    for (int c = 0; c < ColCount; ++c) {
        QString text = heads[static_cast<size_t>(c)];
        if (!sort_key_of(c).isEmpty() && sort_key_of(c) == sort_key_)
            text += sort_dir_ > 0 ? QStringLiteral(" ▲") : QStringLiteral(" ▼");
        table_->horizontalHeaderItem(c)->setText(text);
    }
    table_->horizontalHeaderItem(ColNow)->setToolTip(tr("%1 hiện tại (chốt bản tuần)").arg(m));
    table_->horizontalHeaderItem(ColMean)->setToolTip(tr("Trung bình lịch sử %1 của chính mã").arg(m));
    table_->horizontalHeaderItem(ColLive)->setToolTip(
        tr("σ %1 đọc từ pipeline HHP hôm nay (%2) — \"→\" = đã đổi vùng so với bản tuần")
            .arg(m, live_as_of_txt_.isEmpty() ? QStringLiteral("—") : live_as_of_txt_));

    table_->setUpdatesEnabled(false);
    table_->selectionModel()->clear(); // also drops the current row: Enter must not open a ticker nobody picked
    table_->clearContents();
    table_->clearSpans();
    if (out.isEmpty()) {
        table_->setRowCount(1);
        table_->setSpan(0, 0, 1, ColCount);
        const QString msg = rows_.isEmpty() ? tr("[CẦN DATA] — bản tuần không có bảng lọc (snapshot trống).")
                                            : tr("Không có mã nào khớp bộ lọc.");
        auto* it = make_item(msg, c_muted(), false);
        it->setFlags(Qt::ItemIsEnabled);
        table_->setItem(0, 0, it);
    } else {
        table_->setRowCount(static_cast<int>(out.size()));
        const QString live_as_of = live_as_of_txt_.isEmpty() ? QStringLiteral("—") : live_as_of_txt_;
        for (int i = 0; i < out.size(); ++i) {
            const RowView& v = out.at(i).second;
            fill_row(table_, i, v, mine_.contains(v.t), avoid_.contains(v.t), metric_, live_as_of);
        }
    }
    table_->setUpdatesEnabled(true);

    const QString n_txt = tr("%1 / %2 mã").arg(shown_.size()).arg(rows_.size());
    count_->setText(n_txt);
    foot_->setText(tr("Ảnh chụp bản tuần — định giá chốt %1 · σ live %2 · %3")
                       .arg(as_of_txt_.isEmpty() ? QStringLiteral("—") : as_of_txt_,
                            live_as_of_txt_.isEmpty() ? QStringLiteral("—") : live_as_of_txt_, n_txt));

    // Height follows the rows up to the cap; past it the table scrolls inside (page: max-height box).
    const QHeaderView* header = table_->horizontalHeader();
    const int header_h = header->isHidden() ? 0 : header->sizeHint().height();
    const int body = table_->rowCount() * kRowHeight;
    const int hbar = table_->horizontalScrollBar()->sizeHint().height();
    table_->setFixedHeight(std::min(kMaxTableH, header_h + body + 2 * table_->frameWidth() + hbar + 4));

    if (!keep_tk.isEmpty()) {
        for (int i = 0; i < shown_.size(); ++i) {
            if (shown_.at(i).value(QStringLiteral("t")).toString() == keep_tk) {
                table_->selectRow(i);
                break;
            }
        }
    }
}

// ── CSV (what is shown; the painted gauge column is left out — σ carries it) ──

QStringList HhpWeeklyScreener::csv_header() const {
    const QString m = metric_label(metric_);
    return {QStringLiteral("Mã"),
            QStringLiteral("Danh mục"),
            m,
            QStringLiteral("μ ") + m,
            QStringLiteral("σ ") + m,
            QStringLiteral("σ live ") + m,
            QStringLiteral("Giá"),
            QStringLiteral("Giá TB"),
            QStringLiteral("→TB"),
            QStringLiteral("Fwd 26F"),
            QStringLiteral("TP"),
            QStringLiteral("Catalyst mới nhất")};
}

QVector<QStringList> HhpWeeklyScreener::csv_rows() const {
    QVector<QStringList> out;
    out.reserve(shown_.size());
    for (const QJsonObject& r : shown_) {
        const RowView v = view_of(r, metric_, live_);
        // Same membership words and precedence as the contract csv (mine before avoid).
        const QString member = mine_.contains(v.t)    ? QStringLiteral("danh mục")
                               : avoid_.contains(v.t) ? QStringLiteral("tránh")
                                                      : QString();
        out.append({v.t, member, fmt_dec(v.now), fmt_dec(v.mean), sigma_txt(v.sigma), live_txt(v), fmt_vi(v.p),
                    fmt_vi(v.fair), pct_txt(v.up), with_tag(fmt_dec(v.fwd), fwd_tag(v)),
                    with_tag(fmt_vi(v.tp), v.rating), cat_txt(v)});
    }
    return out;
}

} // namespace fincept::screens::hhp::weekly
