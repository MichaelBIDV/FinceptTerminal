// src/screens/langkinh/LkCards.cpp
// Lăng Kính FFT — block "cards" (clock · box · keynote · premortem) và "tkhead" (đầu mã) theo LK_HOSO_SPEC §6.
// Xem LkCards.h. Phần dùng chung (html-lite, nhãn, pill, bố cục) ở LkChips; màu/phông ở LkTheme.h.
#include "screens/langkinh/LkCards.h"

#include "screens/langkinh/LkChips.h"
#include "screens/langkinh/LkTheme.h"
#include "screens/langkinh/LkWidgets.h"

#include <QFontMetricsF>
#include <QFrame>
#include <QHBoxLayout>
#include <QJsonArray>
#include <QJsonValue>
#include <QLabel>
#include <QPainter>
#include <QTextDocumentFragment>
#include <QSizePolicy>
#include <QStringList>
#include <QVBoxLayout>

#include <algorithm>
#include <cmath>

namespace fincept::screens::langkinh {

// Helper tự do: namespace có tên riêng (quy ước của module, không dùng namespace ẩn danh).
namespace lkcards {

using namespace lkview;

constexpr int kCardRadius = 10;
constexpr int kClockMinW = 250; // .clocks minmax(250px, 1fr)
constexpr int kBoxMinW = 300;   // .lvl2 hai cột, gập một cột khi hẹp
constexpr int kGridGap = 12;
constexpr int kKeynoteIdW = 52; // .kn 52px | 1fr
constexpr int kPremortemNoW = 40; // .pm 40px | 1fr
constexpr int kRowMeasure = 700; // khổ chữ hàng keynote/premortem (p{max-width:74ch})
constexpr int kTkCodePx = 76; // .tk-code 84px ở desktop; 76 giữ tỉ lệ ~3× tiêu đề 26px trong khung terminal
constexpr int kTkGapX = 22;
constexpr int kTkMinRight = 300;

struct Item {
    QString pill;
    QString pill_mau;
    QString id;
    QString tieu_de;
    QString noi_dung;
    bool inv = false;
};

QString str_of(const QJsonObject& o, const char* key) {
    return text_opt(o.value(QLatin1String(key)));
}

/// html-lite → chữ trần (nhãn tự vẽ không hiểu rich text); thực thể (&amp; &#8722; …) được giải mã.
QString plain(const QString& s) {
    return QTextDocumentFragment::fromHtml(lk_inline_html(s)).toPlainText().simplified();
}

/// noi_dung: chuỗi, hoặc mảng đoạn (nối bằng dòng trống).
QString body_of(const QJsonValue& v) {
    if (!v.isArray())
        return text_opt(v);
    QStringList parts;
    for (const auto& x : v.toArray())
        if (const QString s = text_opt(x); !s.isEmpty())
            parts << s;
    return parts.join(QStringLiteral("\n\n"));
}

QList<Item> read_items(const QJsonArray& arr) {
    QList<Item> out;
    for (const auto& v : arr) {
        if (!v.isObject())
            continue;
        const QJsonObject o = v.toObject();
        Item it;
        it.pill = str_of(o, "pill");
        it.pill_mau = o.value(QStringLiteral("pill_mau")).toString().trimmed();
        it.id = str_of(o, "id");
        it.tieu_de = str_of(o, "tieu_de");
        it.noi_dung = body_of(o.value(QStringLiteral("noi_dung")));
        it.inv = o.value(QStringLiteral("inv")).toBool(false);
        if (it.tieu_de.isEmpty() && it.noi_dung.isEmpty() && it.pill.isEmpty())
            continue;
        out << it;
    }
    return out;
}

QLabel* title_label(const QString& t, const QFont& f, QWidget* parent) {
    return lk_label(lk_inline_html(t, lk_col(LkRole::Ink)), f, lk_col(LkRole::Ink), parent, Qt::RichText);
}

QLabel* body_label(const QString& t, int px, QWidget* parent) {
    const QFont f = lk_font_sans(px);
    return lk_label(lk_para_html(t, lk_col(LkRole::Ink), lk_line_pct(f)), f, lk_col(LkRole::Ink2), parent,
                    Qt::RichText);
}

QFrame* card_frame(QWidget* parent, const QColor& bg, const QColor& border) {
    auto* f = new QFrame(parent);
    f->setObjectName(QStringLiteral("lkcCard"));
    f->setStyleSheet(QStringLiteral("QFrame#lkcCard { background:%1; border:1px solid %2; border-radius:%3px; }")
                         .arg(bg.name(), border.name())
                         .arg(kCardRadius));
    return f;
}

// ── clock · box ───────────────────────────────────────────────────────────────

QWidget* clock_card(const Item& it, QWidget* parent) {
    QFrame* f = card_frame(parent, lk_col(LkRole::Surface), lk_col(LkRole::Line));
    auto* vl = new QVBoxLayout(f);
    vl->setContentsMargins(16, 15, 16, 16);
    vl->setSpacing(0);
    if (!it.pill.isEmpty()) {
        auto* row = new QHBoxLayout;
        row->setSpacing(0);
        row->addWidget(new LkPill(it.pill, lk_pill_role(it.pill_mau), f, 11, true));
        row->addStretch(1);
        vl->addLayout(row);
        vl->addSpacing(10);
    }
    if (!it.tieu_de.isEmpty())
        vl->addWidget(title_label(it.tieu_de, lk_font_sans(15, 600), f));
    if (!it.noi_dung.isEmpty()) {
        if (!it.tieu_de.isEmpty())
            vl->addSpacing(6);
        vl->addWidget(body_label(it.noi_dung, 13, f));
    }
    vl->addStretch(1);
    return f;
}

QWidget* box_card(const Item& it, QWidget* parent) {
    const QColor surface = lk_col(LkRole::Surface);
    const QColor down = lk_col(LkRole::Down);
    const QColor bg = it.inv ? lk_over(lk_soft(down), surface) : surface;
    const QColor border = it.inv ? lk_mix(lk_col(LkRole::Line), down, 0.35) : lk_col(LkRole::Line);
    QFrame* f = card_frame(parent, bg, border);
    auto* vl = new QVBoxLayout(f);
    vl->setContentsMargins(16, 14, 16, 15);
    vl->setSpacing(0);
    const QString head = plain(it.tieu_de);
    if (!head.isEmpty() || !it.pill.isEmpty()) {
        auto* hl = new QHBoxLayout;
        hl->setSpacing(8);
        if (!head.isEmpty())
            hl->addWidget(new LkCapsLabel(head, lk_font_mono(11, 600), LkRole::Muted, f, 0.08, true), 1);
        else
            hl->addStretch(1);
        if (!it.pill.isEmpty())
            hl->addWidget(new LkPill(it.pill, lk_pill_role(it.pill_mau), f), 0, Qt::AlignTop);
        vl->addLayout(hl);
        if (!it.noi_dung.isEmpty())
            vl->addSpacing(8);
    }
    if (!it.noi_dung.isEmpty())
        vl->addWidget(body_label(it.noi_dung, 13, f));
    vl->addStretch(1);
    return f;
}

QWidget* grid_box(const QList<Item>& items, bool clock, QWidget* parent) {
    auto* box = new QWidget(parent);
    auto* grid = new LkAutoGridLayout(box, clock ? kClockMinW : kBoxMinW, clock ? 0 : 2, kGridGap);
    for (const Item& it : items)
        grid->addWidget(clock ? clock_card(it, box) : box_card(it, box));
    return box;
}

// ── keynote · premortem ───────────────────────────────────────────────────────

QWidget* row_item(const Item& it, int index, bool keynote, bool last, QWidget* parent) {
    auto* row = new QFrame(parent);
    row->setObjectName(QStringLiteral("lkcRow"));
    const QString rule = last ? QString()
                              : QStringLiteral("border-bottom:1px solid %1;").arg(lk_col(LkRole::Line).name());
    row->setStyleSheet(QStringLiteral("QFrame#lkcRow { background:transparent; border:none; %1 }").arg(rule));
    auto* hl = new QHBoxLayout(row);
    hl->setContentsMargins(0, keynote ? 16 : 14, 0, keynote ? 16 : 14);
    hl->setSpacing(keynote ? 16 : 14);

    QString id = it.id;
    if (id.isEmpty())
        id = keynote ? QStringLiteral("K%1").arg(index + 1) : QString::number(index + 1);
    QLabel* idl = lk_label(id, lk_font_serif(keynote ? 28 : 24, 600), lk_col(keynote ? LkRole::Amber : LkRole::Down),
                           row);
    idl->setWordWrap(false);
    idl->setMinimumWidth(keynote ? kKeynoteIdW : kPremortemNoW); // id dài ("A-01") nới cột, không bị cắt
    idl->setSizePolicy(QSizePolicy::Minimum, QSizePolicy::Preferred);
    idl->setAlignment(Qt::AlignLeft | Qt::AlignTop);
    hl->addWidget(idl, 0, Qt::AlignTop);

    auto* col = new QWidget(row);
    auto* cl = new QVBoxLayout(col);
    cl->setContentsMargins(0, 0, 0, 0);
    cl->setSpacing(6);
    if (!it.tieu_de.isEmpty() || !it.pill.isEmpty()) {
        auto* th = new QHBoxLayout;
        th->setSpacing(10);
        if (!it.tieu_de.isEmpty())
            th->addWidget(title_label(it.tieu_de, keynote ? lk_font_serif(20, 600) : lk_font_sans(15, 600), col), 1);
        else
            th->addStretch(1);
        if (!it.pill.isEmpty())
            th->addWidget(new LkPill(it.pill, lk_pill_role(it.pill_mau), col), 0, Qt::AlignTop);
        cl->addLayout(th);
    }
    if (!it.noi_dung.isEmpty()) // keynote 14px (Artifact .kn p lớn hơn .pl p), premortem 13px
        cl->addWidget(body_label(it.noi_dung, keynote ? 14 : 13, col));
    hl->addWidget(lk_measure(col, kRowMeasure, row), 1); // cả cột (tiêu đề + pill + đoạn) theo khổ chữ
    return row;
}

/// top_rule=false khi block không có đầu riêng (nằm dưới đầu phần .sec-head — vạch của đầu phần đã ngăn cách).
QWidget* rows_box(const QList<Item>& items, bool keynote, bool top_rule, QWidget* parent) {
    auto* box = new QFrame(parent);
    box->setObjectName(QStringLiteral("lkcRows"));
    box->setStyleSheet(top_rule ? QStringLiteral("QFrame#lkcRows { background:transparent; border:none;"
                                                 " border-top:1px solid %1; }")
                                      .arg(lk_col(LkRole::Line).name())
                                : QStringLiteral("QFrame#lkcRows { background:transparent; border:none; }"));
    auto* vl = new QVBoxLayout(box);
    vl->setContentsMargins(0, 0, 0, 0);
    vl->setSpacing(0);
    const int n = static_cast<int>(items.size());
    for (int i = 0; i < n; ++i)
        vl->addWidget(row_item(items.at(i), i, keynote, i == n - 1, box));
    return box;
}

// ── tkhead ────────────────────────────────────────────────────────────────────

/// Mã chứng khoán serif lớn, hộp bó sát chữ hoa (kiểu line-height .9 của .tk-code).
class BigCode : public QWidget {
  public:
    BigCode(const QString& text, QWidget* parent) : QWidget(parent), text_(text) {
        setSizePolicy(QSizePolicy::Fixed, QSizePolicy::Fixed);
        lk_transparent(this);
    }
    QSize sizeHint() const override {
        const Geo g = geo();
        return {static_cast<int>(std::ceil(g.w)), static_cast<int>(std::ceil(g.h))};
    }
    QSize minimumSizeHint() const override { return sizeHint(); }

  protected:
    void paintEvent(QPaintEvent*) override {
        QPainter p(this);
        p.setRenderHint(QPainter::Antialiasing, true);
        p.setRenderHint(QPainter::TextAntialiasing, true);
        p.setFont(code_font());
        p.setPen(lk_col(LkRole::Ink));
        p.drawText(QPointF(1.0, geo().base), text_);
    }

  private:
    struct Geo {
        double w;
        double h;
        double base;
    };
    static QFont code_font() {
        QFont f = lk_font_serif(kTkCodePx, 700);
        f.setLetterSpacing(QFont::AbsoluteSpacing, -0.02 * kTkCodePx);
        return f;
    }
    Geo geo() const {
        const QFontMetricsF fm(code_font());
        const double base = 0.06 * kTkCodePx + fm.capHeight();
        return {fm.horizontalAdvance(text_) + 4.0, base + fm.descent() * 0.55, base};
    }

    QString text_;
};

/// Hai mục: trái theo sizeHint, phải co giãn; đủ rộng thì đứng cạnh nhau và canh ĐÁY (align-items:end),
/// hẹp hơn trái + hgap + min_right thì xếp dọc. Quyết định từ đúng hình chữ nhật được cấp.
class SplitLayout : public QLayout {
  public:
    SplitLayout(QWidget* parent, int hgap, int vgap, int min_right)
        : QLayout(parent), hgap_(hgap), vgap_(vgap), min_right_(min_right) {
        setContentsMargins(0, 0, 0, 0);
    }
    ~SplitLayout() override {
        while (QLayoutItem* it = takeAt(0))
            delete it;
    }
    void addItem(QLayoutItem* item) override { items_.append(item); }
    int count() const override { return static_cast<int>(items_.size()); }
    QLayoutItem* itemAt(int i) const override { return (i >= 0 && i < items_.size()) ? items_.at(i) : nullptr; }
    QLayoutItem* takeAt(int i) override { return (i >= 0 && i < items_.size()) ? items_.takeAt(i) : nullptr; }
    Qt::Orientations expandingDirections() const override { return Qt::Horizontal; }
    bool hasHeightForWidth() const override { return true; }
    int heightForWidth(int w) const override { return do_layout(QRect(0, 0, w, 0), true); }
    void setGeometry(const QRect& r) override {
        QLayout::setGeometry(r);
        do_layout(r, false);
    }
    QSize sizeHint() const override {
        int w = hgap_;
        for (QLayoutItem* it : items_)
            w += it->sizeHint().width();
        const QMargins m = contentsMargins();
        w = std::max(w, min_right_ + hgap_) + m.left() + m.right();
        return {w, heightForWidth(w)};
    }
    QSize minimumSize() const override {
        QSize s(0, 0);
        for (QLayoutItem* it : items_)
            s = s.expandedTo(it->minimumSize());
        const QMargins m = contentsMargins();
        return s + QSize(m.left() + m.right(), m.top() + m.bottom());
    }

  private:
    static int h_of(QLayoutItem* it, int w) {
        const int h = it->hasHeightForWidth() ? it->heightForWidth(w) : it->sizeHint().height();
        return std::max(h, it->minimumSize().height());
    }
    int do_layout(const QRect& rect, bool test_only) const {
        const QMargins m = contentsMargins();
        const QRect r = rect.adjusted(m.left(), m.top(), -m.right(), -m.bottom());
        if (items_.isEmpty() || r.width() <= 0)
            return m.top() + m.bottom();
        QLayoutItem* left = items_.at(0);
        QLayoutItem* right = items_.size() > 1 ? items_.at(1) : nullptr;
        const int lw = std::min(left->sizeHint().width(), r.width());
        const int lh = h_of(left, lw);
        int content_h = lh;
        if (right && r.width() >= lw + hgap_ + min_right_) {
            const int rw = r.width() - lw - hgap_;
            const int rh = h_of(right, rw);
            content_h = std::max(lh, rh);
            if (!test_only) {
                left->setGeometry(QRect(r.x(), r.y() + content_h - lh, lw, lh));
                right->setGeometry(QRect(r.x() + lw + hgap_, r.y() + content_h - rh, rw, rh));
            }
        } else {
            if (!test_only)
                left->setGeometry(QRect(r.x(), r.y(), lw, lh));
            if (right) {
                const int rh = h_of(right, r.width());
                if (!test_only)
                    right->setGeometry(QRect(r.x(), r.y() + lh + vgap_, r.width(), rh));
                content_h = lh + vgap_ + rh;
            }
        }
        return content_h + m.top() + m.bottom();
    }

    QList<QLayoutItem*> items_;
    int hgap_;
    int vgap_;
    int min_right_;
};

/// Màu biến động giá: khoá chg_mau có mặt → theo khoá ("" = trung tính); vắng → theo dấu đầu chuỗi.
LkRole chg_role(const QJsonObject& b, const QString& chg) {
    const QJsonValue v = b.value(QStringLiteral("chg_mau"));
    if (v.isString())
        return lk_role(v.toString(), LkRole::Ink2);
    const QString c = chg.trimmed();
    if (c.startsWith(QLatin1Char('+')))
        return LkRole::Up;
    if (c.startsWith(QChar(0x2212)) || c.startsWith(QLatin1Char('-')))
        return LkRole::Down;
    return LkRole::Ink2;
}

/// Dòng giá (mono 15px) + pills, xếp chảy. Không có gì → nullptr.
QWidget* meta_row(const QJsonObject& b, QWidget* parent) {
    const QString px = str_of(b, "px");
    const QString chg = str_of(b, "chg");
    auto* box = new QWidget(parent);
    auto* flow = new LkWrapLayout(box, 10, 6, true);
    if (!px.isEmpty() || !chg.isEmpty()) {
        QString html = (px.isEmpty() ? dash() : px).toHtmlEscaped();
        if (!chg.isEmpty())
            html += QStringLiteral("&nbsp;&nbsp;<span style=\"color:%1;\">").arg(lk_col(chg_role(b, chg)).name()) +
                    chg.toHtmlEscaped() + QStringLiteral("</span>");
        QLabel* l = lk_label(html, lk_font_mono(15), lk_col(LkRole::Ink), box, Qt::RichText);
        l->setWordWrap(false);
        flow->addWidget(l);
        if (const QString bac = str_of(b, "b"); !bac.isEmpty()) // bậc của giá (hợp đồng v2: khoá `b` của tkhead)
            flow->addWidget(new LkTag(bac, box));
    }
    for (const auto& pv : b.value(QStringLiteral("pills")).toArray()) {
        if (!pv.isObject())
            continue;
        const QJsonObject o = pv.toObject();
        const QString text = str_of(o, "text");
        if (!text.isEmpty())
            flow->addWidget(new LkPill(text, lk_pill_role(o.value(QStringLiteral("mau")).toString()), box));
    }
    if (flow->count() == 0) {
        delete box;
        return nullptr;
    }
    return box;
}

/// Dòng CỔNG của mã: mono, chữ ink2, vạch amber 2px bên trái (.gate-tk); thiếu → [CẦN DATA] vạch đỏ.
QLabel* gate_label(const QJsonValue& v, QWidget* parent) {
    QString t = text_opt(v);
    const bool missing = t.isEmpty();
    if (missing)
        t = lk_tr("CỔNG: [CẦN DATA] — hồ sơ chưa kèm dòng CỔNG của mã; không kết luận theo mã");
    const QFont f = lk_font_mono(12);
    QLabel* l = lk_label(lk_inline_html(t, lk_col(LkRole::Ink)), f, lk_col(LkRole::Ink2), parent, Qt::RichText);
    l->setStyleSheet(QStringLiteral("QLabel { %1 color:%2; background:transparent; border:none;"
                                    " border-left:2px solid %3; padding:4px 0px 4px 12px; }")
                         .arg(lk_font_css(f), lk_col(LkRole::Ink2).name(),
                              lk_col(missing ? LkRole::Down : LkRole::Amber).name()));
    return l;
}

} // namespace lkcards

namespace lkview {

QWidget* make_cards(const QJsonObject& b, QWidget* parent) {
    const QList<lkcards::Item> items = lkcards::read_items(b.value(QStringLiteral("items")).toArray());
    if (items.isEmpty())
        return nullptr;
    const QString variant = b.value(QStringLiteral("variant")).toString().trimmed().toLower();
    auto* w = new QWidget(parent);
    lk_transparent(w); // hộp lưới/cột chữ bên trong là QWidget trần
    auto* vl = new QVBoxLayout(w);
    vl->setContentsMargins(0, 0, 0, 0);
    vl->setSpacing(10);
    lk_add_head(vl, b, w);
    const bool has_head = vl->count() > 0;
    if (variant == QLatin1String("clock"))
        vl->addWidget(lkcards::grid_box(items, true, w));
    else if (variant == QLatin1String("keynote"))
        vl->addWidget(lkcards::rows_box(items, true, has_head, w));
    else if (variant == QLatin1String("premortem"))
        vl->addWidget(lkcards::rows_box(items, false, has_head, w));
    else // "box" và biến thể lạ
        vl->addWidget(lkcards::grid_box(items, false, w));
    return w;
}

QWidget* make_tkhead(const QJsonObject& b, QWidget* parent) {
    const QString ma = lkcards::str_of(b, "ma");
    const QString eyebrow = lkcards::str_of(b, "eyebrow");
    const QString tieu_de = lkcards::str_of(b, "tieu_de");
    if (ma.isEmpty() && eyebrow.isEmpty() && tieu_de.isEmpty())
        return nullptr;
    auto* w = new QWidget(parent);
    lk_transparent(w);
    auto* vl = new QVBoxLayout(w);
    vl->setContentsMargins(0, 0, 0, 0);
    vl->setSpacing(14);

    auto* head = new QFrame(w);
    head->setObjectName(QStringLiteral("lkcTkHead"));
    head->setStyleSheet(QStringLiteral("QFrame#lkcTkHead { background:transparent; border:none;"
                                       " border-bottom:1px solid %1; }")
                            .arg(lk_col(LkRole::Line).name()));
    auto* split = new lkcards::SplitLayout(head, lkcards::kTkGapX, 6, lkcards::kTkMinRight);
    split->setContentsMargins(0, 0, 0, 14);
    split->addWidget(new lkcards::BigCode(ma.isEmpty() ? dash() : ma, head));

    auto* right = new QWidget(head);
    auto* rl = new QVBoxLayout(right);
    rl->setContentsMargins(0, 0, 0, 0);
    rl->setSpacing(4);
    if (!eyebrow.isEmpty())
        rl->addWidget(new LkCapsLabel(eyebrow, lk_font_mono(11, 500), LkRole::Amber, right, 0.14, true));
    if (!tieu_de.isEmpty())
        rl->addWidget(lkcards::title_label(tieu_de, lk_font_serif(26, 600), right));
    if (QWidget* meta = lkcards::meta_row(b, right)) {
        rl->addSpacing(4);
        rl->addWidget(meta);
    }
    split->addWidget(right);
    vl->addWidget(head);
    vl->addWidget(lkcards::gate_label(b.value(QStringLiteral("cong_ma")), w));
    return w;
}

} // namespace lkview

} // namespace fincept::screens::langkinh
