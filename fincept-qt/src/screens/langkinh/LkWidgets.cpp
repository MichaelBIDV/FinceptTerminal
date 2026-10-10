// src/screens/langkinh/LkWidgets.cpp
// Lăng Kính FFT — helper dùng chung + block banner CỔNG · note · tiles · matrix · lists · html
// (CONTRACT §3.1, §4). Xem LkWidgets.h.
#include "screens/langkinh/LkWidgets.h"

#include "screens/langkinh/LkBlockView.h"
#include "screens/langkinh/LkChips.h"
#include "ui/theme/Theme.h"

#include <QCoreApplication>
#include <QFrame>
#include <QGridLayout>
#include <QHBoxLayout>
#include <QJsonArray>
#include <QLabel>
#include <QLayout>
#include <QLocale>
#include <QPushButton>
#include <QResizeEvent>
#include <QShowEvent>
#include <QSizePolicy>
#include <QTextBrowser>
#include <QTextDocument>
#include <QVBoxLayout>
#include <QWheelEvent>

#include <algorithm>
#include <cmath>

namespace fincept::screens::langkinh::lkview {

// ── Helper chữ/số ─────────────────────────────────────────────────────────────

QString lk_tr(const char* text) {
    return QCoreApplication::translate("fincept::screens::langkinh::LkBlockView", text);
}

QString dash() {
    return QStringLiteral("—");
}

QString rgba(const QColor& c, int alpha) {
    return QStringLiteral("rgba(%1,%2,%3,%4)").arg(c.red()).arg(c.green()).arg(c.blue()).arg(alpha);
}

bool num_of(const QJsonValue& v, double* out) {
    if (!v.isDouble())
        return false;
    const double d = v.toDouble();
    if (!std::isfinite(d))
        return false;
    if (out)
        *out = d;
    return true;
}

/// Số kiểu Việt: 1.234,5 · dấu âm "−" (U+2212).
QString vn_num(double v, int decimals) {
    if (!std::isfinite(v))
        return dash();
    const double a = std::abs(v);
    const QLocale loc(QLocale::Vietnamese, QLocale::Vietnam);
    QString s = loc.toString(a, 'f', decimals);
    if (v < 0.0 && std::round(a * std::pow(10.0, decimals)) > 0.0)
        s.prepend(QChar(0x2212));
    return s;
}

QString vn_auto(double v) {
    const double a = std::abs(v);
    if (a < 1e15 && a == std::floor(a))
        return vn_num(v, 0);
    if (a >= 100.0)
        return vn_num(v, 1);
    if (a >= 1.0)
        return vn_num(v, 2);
    return vn_num(v, 3);
}

QString text_of(const QJsonValue& v) {
    if (v.isString()) {
        const QString s = v.toString();
        return s.trimmed().isEmpty() ? dash() : s;
    }
    double d = 0.0;
    if (num_of(v, &d))
        return vn_auto(d);
    if (v.isBool())
        return v.toBool() ? QStringLiteral("có") : QStringLiteral("không");
    return dash();
}

QString text_opt(const QJsonValue& v) {
    if (v.isString())
        return v.toString().trimmed();
    double d = 0.0;
    if (num_of(v, &d))
        return vn_auto(d);
    return {};
}

// ── Widget nhỏ ────────────────────────────────────────────────────────────────

QLabel* make_label(const QString& text, const char* object_name, QWidget* parent, Qt::TextFormat fmt) {
    auto* l = new QLabel(parent);
    l->setObjectName(QLatin1String(object_name));
    l->setTextFormat(fmt);
    l->setText(text);
    l->setWordWrap(true);
    l->setOpenExternalLinks(false);
    l->setTextInteractionFlags(Qt::TextSelectableByMouse);
    return l;
}

QLabel* make_chip(const QString& text, const QColor& c, QWidget* parent) {
    auto* l = new QLabel(parent);
    l->setTextFormat(Qt::PlainText);
    l->setText(text);
    l->setStyleSheet(QStringLiteral("QLabel { color:%1; border:1px solid %1; background:%2;"
                                    " font-size:9px; font-weight:700; padding:1px 5px; }")
                         .arg(c.name(), rgba(c, 24)));
    l->setSizePolicy(QSizePolicy::Fixed, QSizePolicy::Fixed);
    return l;
}

void add_head(QVBoxLayout* vl, const QJsonObject& b, QWidget* parent) {
    const QString title = b.value(QStringLiteral("title")).toString().trimmed();
    const QString sub = b.value(QStringLiteral("sub")).toString().trimmed();
    const QString tier = b.value(QStringLiteral("b")).toString().trimmed(); // hợp đồng v2: tag bậc cạnh tiêu đề
    if (!tier.isEmpty()) {
        auto* hl = new QHBoxLayout;
        hl->setContentsMargins(0, 0, 0, 0);
        hl->setSpacing(8);
        if (!title.isEmpty())
            hl->addWidget(make_label(title, "lkBlockTitle", parent), 1);
        hl->addWidget(new LkTag(tier, parent), 0, Qt::AlignTop | (title.isEmpty() ? Qt::AlignLeft : Qt::AlignRight));
        if (title.isEmpty())
            hl->addStretch(1);
        vl->addLayout(hl);
    } else if (!title.isEmpty()) {
        vl->addWidget(make_label(title, "lkBlockTitle", parent));
    }
    if (!sub.isEmpty())
        vl->addWidget(make_label(sub, "lkSub", parent, Qt::AutoText));
}

// ── Lưới co giãn cột theo bề rộng (≥1500→5, ≥1200→4, ≥880→3, ≥600→2, còn lại 1) ─
// Số cột tính trong setGeometry()/heightForWidth() của layout từ đúng hình chữ nhật được cấp — không dựa
// vào resizeEvent (trang dựng lúc đang ẩn trong QStackedWidget có thể không nhận resize nào sau khi hiện).

class LkGridLayout : public QLayout {
  public:
    LkGridLayout(QWidget* parent, int max_cols, int spacing)
        : QLayout(parent), max_cols_(std::max(1, max_cols)), sp_(spacing) {
        setContentsMargins(0, 0, 0, 0);
    }
    ~LkGridLayout() override {
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
    QSize minimumSize() const override {
        QSize s(0, 0);
        for (QLayoutItem* it : items_)
            s = s.expandedTo(it->minimumSize());
        return s;
    }
    QSize sizeHint() const override {
        int w = 0;
        for (QLayoutItem* it : items_)
            w = std::max(w, it->sizeHint().width());
        const int cols = std::max(1, std::min(max_cols_, count()));
        const int total = cols * w + (cols - 1) * sp_;
        return {total, heightForWidth(total)};
    }

    int columns_for(int w) const {
        int by_width = 1;
        if (w >= 1500)
            by_width = 5;
        else if (w >= 1200)
            by_width = 4;
        else if (w >= 880)
            by_width = 3;
        else if (w >= 600)
            by_width = 2;
        return std::max(1, std::min({max_cols_, by_width, std::max(1, count())}));
    }

  private:
    int do_layout(const QRect& rect, bool test_only) const {
        const int n = count();
        if (n == 0 || rect.width() <= 0)
            return 0;
        const int cols = columns_for(rect.width());
        const int cw = std::max(1, (rect.width() - (cols - 1) * sp_) / cols);
        int y = rect.y();
        for (int first = 0; first < n; first += cols) {
            int rh = 0;
            for (int i = first; i < std::min(n, first + cols); ++i) {
                QLayoutItem* it = items_[i];
                const int h = it->hasHeightForWidth() ? it->heightForWidth(cw) : it->sizeHint().height();
                rh = std::max({rh, h, it->minimumSize().height()});
            }
            if (!test_only)
                for (int i = first; i < std::min(n, first + cols); ++i)
                    items_[i]->setGeometry(QRect(rect.x() + (i - first) * (cw + sp_), y, cw, rh));
            y += rh + sp_;
        }
        return y - sp_ - rect.y();
    }

    QList<QLayoutItem*> items_;
    int max_cols_ = 1;
    int sp_ = 8;
};

class LkGridBox : public QWidget {
  public:
    LkGridBox(int max_cols, QWidget* parent) : QWidget(parent) { grid_ = new LkGridLayout(this, max_cols, 8); }

    void add(QWidget* w) {
        if (!w)
            return;
        w->setParent(this);
        grid_->addWidget(w);
    }

    int count() const { return grid_->count(); }

  private:
    LkGridLayout* grid_ = nullptr;
};

// ── Bố cục chảy (chip mã trong ô ma trận) ─────────────────────────────────────

class LkFlowLayout : public QLayout {
  public:
    explicit LkFlowLayout(QWidget* parent, int hspace = 4, int vspace = 4)
        : QLayout(parent), h_(hspace), v_(vspace) {
        setContentsMargins(0, 0, 0, 0);
    }
    ~LkFlowLayout() override {
        while (QLayoutItem* it = takeAt(0))
            delete it;
    }

    void addItem(QLayoutItem* item) override { items_.append(item); }
    int count() const override { return static_cast<int>(items_.size()); }
    QLayoutItem* itemAt(int i) const override { return (i >= 0 && i < items_.size()) ? items_.at(i) : nullptr; }
    QLayoutItem* takeAt(int i) override { return (i >= 0 && i < items_.size()) ? items_.takeAt(i) : nullptr; }
    Qt::Orientations expandingDirections() const override { return {}; }
    bool hasHeightForWidth() const override { return true; }
    int heightForWidth(int w) const override { return do_layout(QRect(0, 0, w, 0), true); }
    void setGeometry(const QRect& r) override {
        QLayout::setGeometry(r);
        do_layout(r, false);
    }
    QSize sizeHint() const override { return minimumSize(); }
    QSize minimumSize() const override {
        QSize s;
        for (QLayoutItem* it : items_)
            s = s.expandedTo(it->minimumSize());
        const QMargins m = contentsMargins();
        return s + QSize(m.left() + m.right(), m.top() + m.bottom());
    }

  private:
    int do_layout(const QRect& rect, bool test_only) const {
        const QMargins m = contentsMargins();
        const QRect r = rect.adjusted(m.left(), m.top(), -m.right(), -m.bottom());
        int x = r.x();
        int y = r.y();
        int line_h = 0;
        for (QLayoutItem* it : items_) {
            const QSize sz = it->sizeHint();
            if (x > r.x() && x + sz.width() > r.right() + 1) {
                x = r.x();
                y += line_h + v_;
                line_h = 0;
            }
            if (!test_only)
                it->setGeometry(QRect(QPoint(x, y), sz));
            x += sz.width() + h_;
            line_h = std::max(line_h, sz.height());
        }
        return y + line_h - rect.y() + m.bottom();
    }

    QList<QLayoutItem*> items_;
    int h_ = 4;
    int v_ = 4;
};

// ── HTML tĩnh (§1 phương pháp luận) — cao theo nội dung, cuộn bằng trang ngoài ─

class LkHtmlView : public QTextBrowser {
  public:
    LkHtmlView(const QString& html, QWidget* parent) : QTextBrowser(parent) {
        using namespace ui::colors;
        setOpenExternalLinks(false);
        setOpenLinks(false);
        setFrameShape(QFrame::NoFrame);
        setVerticalScrollBarPolicy(Qt::ScrollBarAlwaysOff);
        setHorizontalScrollBarPolicy(Qt::ScrollBarAlwaysOff);
        setSizePolicy(QSizePolicy::Expanding, QSizePolicy::Fixed);
        setStyleSheet(QStringLiteral("QTextBrowser { background:%1; color:%2; border:none; font-size:12px; }")
                          .arg(BG_SURFACE(), TEXT_PRIMARY()));
        document()->setDefaultStyleSheet(
            QStringLiteral("h3 { color:%1; font-size:13px; font-weight:700; margin-top:10px; margin-bottom:4px; }"
                           "h4 { color:%2; font-size:12px; font-weight:700; margin-top:8px; margin-bottom:3px; }"
                           "p { margin-top:2px; margin-bottom:6px; }"
                           "li { margin-bottom:3px; }"
                           "th { color:%3; font-weight:700; padding:3px 6px; }"
                           "td { padding:3px 6px; }"
                           "code { color:%4; }")
                .arg(AMBER(), TEXT_PRIMARY(), TEXT_SECONDARY(), CYAN()));
        document()->setDocumentMargin(4);
        setHtml(html);
        fit();
    }

  protected:
    void resizeEvent(QResizeEvent* e) override {
        QTextBrowser::resizeEvent(e);
        fit();
    }
    void showEvent(QShowEvent* e) override {
        QTextBrowser::showEvent(e);
        fit();
    }
    void wheelEvent(QWheelEvent* e) override { e->ignore(); }

  private:
    void fit() {
        const int w = viewport()->width();
        if (w > 0)
            document()->setTextWidth(w);
        const int h = std::max(24, static_cast<int>(std::ceil(document()->size().height())) + 2 * frameWidth() + 2);
        if (h != height() || minimumHeight() != h)
            setFixedHeight(h);
    }
};

// ── Thẻ số (tiles) ────────────────────────────────────────────────────────────

QWidget* make_tile(const QJsonObject& it, QWidget* parent) {
    using namespace ui::colors;
    const QString mau = it.value(QStringLiteral("mau")).toString().trimmed();
    const QColor c = mau.isEmpty() ? QColor(TEXT_PRIMARY()) : lk_color(mau);
    auto* f = new QFrame(parent);
    f->setObjectName(QStringLiteral("lkTile"));
    f->setStyleSheet(QStringLiteral("QFrame#lkTile { background:%1; border:1px solid %2; border-left:3px solid %3; }")
                         .arg(BG_SURFACE(), BORDER_DIM(), mau.isEmpty() ? QString(BORDER_MED()) : c.name()));
    f->setMinimumHeight(72);
    auto* vl = new QVBoxLayout(f);
    vl->setContentsMargins(10, 7, 10, 8);
    vl->setSpacing(2);
    auto* top = new QHBoxLayout;
    top->setSpacing(6);
    top->addWidget(make_label(text_of(it.value(QStringLiteral("k"))), "lkTileK", f), 1);
    const QString bac = it.value(QStringLiteral("bac")).toString().trimmed();
    if (!bac.isEmpty())
        top->addWidget(make_chip(bac, QColor(TEXT_TERTIARY()), f), 0, Qt::AlignTop);
    vl->addLayout(top);
    auto* v = make_label(text_of(it.value(QStringLiteral("v"))), "lkTileV", f);
    v->setStyleSheet(
        QStringLiteral("QLabel { color:%1; font-size:18px; font-weight:700; background:transparent; }").arg(c.name()));
    vl->addWidget(v);
    const QString s = it.value(QStringLiteral("s")).toString();
    if (!s.trimmed().isEmpty())
        vl->addWidget(make_label(s, "lkTileS", f, Qt::AutoText));
    vl->addStretch(1);
    return f;
}

// ── Ô ma trận: tiêu đề + chip mã + ghi chú ────────────────────────────────────

QPushButton* make_ticker_chip(const QJsonObject& chip, QWidget* parent, const TickerFn& on_ticker) {
    using namespace ui::colors;
    const QString ma = chip.value(QStringLiteral("ma")).toString().trimmed();
    if (ma.isEmpty())
        return nullptr;
    const QString v = text_opt(chip.value(QStringLiteral("v")));
    const QString mau = chip.value(QStringLiteral("mau")).toString().trimmed();
    const QColor fg = mau.isEmpty() ? QColor(TEXT_PRIMARY()) : lk_color(mau);
    const QColor edge = mau.isEmpty() ? QColor(BORDER_BRIGHT()) : lk_color(mau);
    auto* b = new QPushButton(v.isEmpty() ? ma : ma + QLatin1Char(' ') + v, parent);
    b->setFlat(true);
    b->setCursor(Qt::PointingHandCursor);
    b->setFocusPolicy(Qt::NoFocus);
    b->setToolTip(lk_tr("Mở chuỗi FFT × Giá của %1").arg(ma));
    b->setStyleSheet(QStringLiteral("QPushButton { color:%1; background:%2; border:1px solid %3;"
                                    " font-size:10px; font-weight:600; padding:1px 6px; }"
                                    "QPushButton:hover { background:%4; }")
                         .arg(fg.name(), rgba(edge, 22), edge.name(), rgba(edge, 64)));
    QObject::connect(b, &QPushButton::clicked, b, [on_ticker, ma]() {
        if (on_ticker)
            on_ticker(ma);
    });
    return b;
}

QWidget* make_matrix_cell(const QJsonObject& cell, QWidget* parent, const TickerFn& on_ticker) {
    auto* f = new QFrame(parent);
    f->setObjectName(QStringLiteral("lkCell"));
    auto* vl = new QVBoxLayout(f);
    vl->setContentsMargins(8, 6, 8, 7);
    vl->setSpacing(4);
    const QString title = cell.value(QStringLiteral("title")).toString().trimmed();
    if (!title.isEmpty())
        vl->addWidget(make_label(title, "lkCellTitle", f));
    auto* holder = new QWidget(f);
    auto* flow = new LkFlowLayout(holder, 4, 4);
    const QJsonArray chips = cell.value(QStringLiteral("chips")).toArray();
    for (const auto& cv : chips)
        if (QPushButton* b = make_ticker_chip(cv.toObject(), holder, on_ticker))
            flow->addWidget(b);
    if (flow->count() > 0)
        vl->addWidget(holder);
    else {
        delete holder;
        vl->addWidget(make_label(dash(), "lkCap", f));
    }
    const QString note = cell.value(QStringLiteral("note")).toString().trimmed();
    if (!note.isEmpty())
        vl->addWidget(make_label(note, "lkCap", f, Qt::AutoText));
    vl->addStretch(1);
    return f;
}

// ═════════════════════════════════════════════════════════════════════════════
// Block
// ═════════════════════════════════════════════════════════════════════════════

QWidget* make_banner(const QJsonValue& cong_v, QWidget* parent) {
    using namespace ui::colors;
    const QJsonObject cong = cong_v.toObject();
    QString muc = cong.value(QStringLiteral("muc")).toString().trimmed();
    QString dong = cong.value(QStringLiteral("dong")).toString().trimmed();
    if (dong.isEmpty()) {
        // Không có dòng CỔNG thì không được coi là "ok": DỪNG, không kết luận per-mã.
        muc = QStringLiteral("dung");
        dong = lk_tr("CỔNG: [CẦN DATA — trang không kèm dòng CỔNG] · không kết luận per-mã");
    }
    QColor edge;
    QString bg;
    if (muc == QLatin1String("ok")) {
        edge = QColor(POSITIVE());
        bg = QString(POSITIVE_BG());
    } else if (muc == QLatin1String("dung")) {
        edge = QColor(NEGATIVE());
        bg = QString(NEGATIVE_BG());
    } else {
        edge = QColor(WARNING());
        bg = rgba(edge, 28);
    }

    auto* f = new QFrame(parent);
    f->setObjectName(QStringLiteral("lkBanner"));
    f->setStyleSheet(QStringLiteral("QFrame#lkBanner { background:%1; border:1px solid %2; border-left:4px solid %2; }")
                         .arg(bg, edge.name()));
    auto* vl = new QVBoxLayout(f);
    vl->setContentsMargins(12, 8, 12, 9);
    vl->setSpacing(3);

    auto* top = new QHBoxLayout;
    top->setSpacing(8);
    auto* dong_lbl = make_label(dong, "lkBannerDong", f);
    dong_lbl->setStyleSheet(
        QStringLiteral("QLabel { color:%1; font-size:13px; font-weight:700; background:transparent; }").arg(TEXT_PRIMARY()));
    top->addWidget(dong_lbl, 1);
    const QString bac = cong.value(QStringLiteral("bac")).toString().trimmed();
    if (!bac.isEmpty())
        top->addWidget(make_chip(bac, edge, f), 0, Qt::AlignTop);
    vl->addLayout(top);

    const QString chi_tiet = cong.value(QStringLiteral("chi_tiet")).toString().trimmed();
    if (!chi_tiet.isEmpty())
        vl->addWidget(make_label(chi_tiet, "lkSub", f));
    const QJsonArray cb = cong.value(QStringLiteral("canh_bao")).toArray();
    for (const auto& c : cb) {
        const QString t = c.toString().trimmed();
        if (t.isEmpty())
            continue;
        auto* l = make_label(lk_tr("Cảnh báo: %1").arg(t), "lkBannerWarn", f);
        l->setStyleSheet(QStringLiteral("QLabel { color:%1; font-size:10px; background:transparent; }").arg(WARNING()));
        vl->addWidget(l);
    }
    return f;
}

/// Ghi chú trong trang hồ sơ (khoá nội bộ _hoso): thẻ cùng kiểu .fig (surface, viền line, bo 10) + vạch màu 2px bên
/// trái, pill + tiêu đề sans 14/600, chữ sans 13 ink2; phần cao dư (khi đứng trong "row") dồn xuống đáy thẻ.
QWidget* make_note_hoso(const QJsonObject& b, QWidget* parent) {
    const QString mau = b.value(QStringLiteral("mau")).toString().trimmed();
    const QColor c = mau.isEmpty() ? lk_col(LkRole::Line2) : lk_col(lk_role(mau, LkRole::Grey));
    auto* f = new QFrame(parent);
    f->setObjectName(QStringLiteral("lkNoteH"));
    f->setStyleSheet(QStringLiteral("QFrame#lkNoteH { background:%1; border:1px solid %2; border-left:2px solid %3;"
                                    " border-radius:10px; }")
                         .arg(lk_qss(lk_col(LkRole::Surface)), lk_qss(lk_col(LkRole::Line)), c.name()));
    auto* vl = new QVBoxLayout(f);
    vl->setContentsMargins(14, 12, 14, 12);
    vl->setSpacing(6);
    const QString pill = b.value(QStringLiteral("pill")).toString().trimmed();
    const QString title = b.value(QStringLiteral("title")).toString().trimmed();
    if (!pill.isEmpty() || !title.isEmpty()) {
        auto* hl = new QHBoxLayout;
        hl->setSpacing(8);
        if (!pill.isEmpty())
            hl->addWidget(new LkPill(pill, lk_pill_role(mau), f), 0, Qt::AlignTop);
        if (!title.isEmpty())
            hl->addWidget(lk_label(title, lk_font_sans(14, 600), lk_col(LkRole::Ink), f), 1);
        else
            hl->addStretch(1);
        vl->addLayout(hl);
    }
    QString text = b.value(QStringLiteral("text")).toString();
    if (!text.trimmed().isEmpty()) {
        text.replace(QLatin1Char('\n'), QStringLiteral("<br>"));
        vl->addWidget(lk_label(text, lk_font_sans(13), lk_col(LkRole::Ink2), f, Qt::RichText));
    }
    vl->addStretch(1);
    return f;
}

QWidget* make_note(const QJsonObject& b, QWidget* parent) {
    using namespace ui::colors;
    if (b.value(QStringLiteral("_hoso")).toBool(false))
        return make_note_hoso(b, parent);
    const QString mau = b.value(QStringLiteral("mau")).toString().trimmed();
    const QColor c = mau.isEmpty() ? QColor(BORDER_BRIGHT()) : lk_color(mau);
    auto* f = new QFrame(parent);
    f->setObjectName(QStringLiteral("lkNote"));
    f->setStyleSheet(QStringLiteral("QFrame#lkNote { background:%1; border:1px solid %2; border-left:3px solid %3; }")
                         .arg(BG_SURFACE(), BORDER_DIM(), c.name()));
    auto* vl = new QVBoxLayout(f);
    vl->setContentsMargins(12, 8, 12, 9);
    vl->setSpacing(5);
    const QString pill = b.value(QStringLiteral("pill")).toString().trimmed();
    const QString title = b.value(QStringLiteral("title")).toString().trimmed();
    if (!pill.isEmpty() || !title.isEmpty()) {
        auto* hl = new QHBoxLayout;
        hl->setSpacing(8);
        if (!pill.isEmpty())
            hl->addWidget(make_chip(pill, mau.isEmpty() ? QColor(TEXT_SECONDARY()) : c, f), 0, Qt::AlignVCenter);
        if (!title.isEmpty())
            hl->addWidget(make_label(title, "lkBlockTitle", f), 1);
        else
            hl->addStretch(1);
        vl->addLayout(hl);
    }
    QString text = b.value(QStringLiteral("text")).toString();
    if (!text.trimmed().isEmpty()) {
        text.replace(QLatin1Char('\n'), QStringLiteral("<br>"));
        vl->addWidget(make_label(text, "lkText", f, Qt::RichText));
    }
    return f;
}

QWidget* make_tiles(const QJsonObject& b, QWidget* parent) {
    const QJsonArray items = b.value(QStringLiteral("items")).toArray();
    auto* box = new LkGridBox(5, parent);
    for (const auto& iv : items) {
        const QJsonObject it = iv.toObject();
        if (it.isEmpty())
            continue;
        box->add(make_tile(it, box));
    }
    if (box->count() == 0) {
        delete box;
        return nullptr;
    }
    return box;
}

QWidget* make_matrix(const QJsonObject& b, QWidget* parent, const TickerFn& on_ticker) {
    auto* card = new QFrame(parent);
    card->setObjectName(QStringLiteral("lkCard"));
    auto* outer = new QVBoxLayout(card);
    outer->setContentsMargins(10, 8, 10, 10);
    outer->setSpacing(6);
    add_head(outer, b, card);

    const QJsonArray cols = b.value(QStringLiteral("cols")).toArray();
    const QJsonArray rows = b.value(QStringLiteral("rows")).toArray();
    int ncols = static_cast<int>(cols.size());
    for (const auto& rv : rows)
        ncols = std::max(ncols, static_cast<int>(rv.toObject().value(QStringLiteral("cells")).toArray().size()));
    if (ncols == 0 || rows.isEmpty()) {
        outer->addWidget(make_label(lk_tr("— ma trận trống —"), "lkCap", card));
        return card;
    }

    auto* grid = new QGridLayout;
    grid->setHorizontalSpacing(6);
    grid->setVerticalSpacing(6);
    for (int j = 0; j < ncols; ++j) {
        auto* h = make_label(j < cols.size() ? text_of(cols.at(j)) : QString(), "lkColHead", card);
        h->setAlignment(Qt::AlignCenter);
        grid->addWidget(h, 0, j + 1);
        grid->setColumnStretch(j + 1, 1);
    }
    int r = 1;
    for (const auto& rv : rows) {
        const QJsonObject ro = rv.toObject();
        if (ro.isEmpty())
            continue;
        auto* rl = make_label(text_of(ro.value(QStringLiteral("label"))), "lkRowHead", card);
        rl->setWordWrap(false);
        rl->setAlignment(Qt::AlignCenter);
        rl->setMinimumWidth(64);
        grid->addWidget(rl, r, 0);
        const QJsonArray cells = ro.value(QStringLiteral("cells")).toArray();
        for (int j = 0; j < ncols; ++j) {
            const QJsonObject cell = j < cells.size() ? cells.at(j).toObject() : QJsonObject();
            grid->addWidget(make_matrix_cell(cell, card, on_ticker), r, j + 1);
        }
        ++r;
    }
    outer->addLayout(grid);
    return card;
}

QWidget* make_lists(const QJsonObject& b, QWidget* parent) {
    const QJsonArray items = b.value(QStringLiteral("items")).toArray();
    int n_valid = 0;
    for (const auto& iv : items)
        if (iv.isObject())
            ++n_valid;
    if (n_valid == 0)
        return nullptr;

    auto* box = new LkGridBox(std::min(4, n_valid), nullptr);
    for (const auto& iv : items) {
        if (!iv.isObject())
            continue;
        const QJsonObject it = iv.toObject();
        auto* card = new QFrame(box);
        card->setObjectName(QStringLiteral("lkCard"));
        auto* vl = new QVBoxLayout(card);
        vl->setContentsMargins(10, 8, 10, 9);
        vl->setSpacing(3);
        const QString mau = it.value(QStringLiteral("mau")).toString().trimmed();
        auto* t = make_label(text_of(it.value(QStringLiteral("title"))), "lkListTitle", card);
        t->setStyleSheet(QStringLiteral("QLabel { color:%1; font-size:11px; font-weight:700; background:transparent; }")
                             .arg(lk_color(mau).name()));
        vl->addWidget(t);
        const QJsonArray rows = it.value(QStringLiteral("rows")).toArray();
        int k = 0;
        for (const auto& rv : rows) {
            const QString s = text_opt(rv);
            if (s.isEmpty())
                continue;
            ++k;
            vl->addWidget(make_label(QStringLiteral("%1. %2").arg(k).arg(s), "lkListRow", card));
        }
        if (k == 0)
            vl->addWidget(make_label(dash(), "lkCap", card));
        vl->addStretch(1);
        box->add(card);
    }

    const QString title = b.value(QStringLiteral("title")).toString().trimmed();
    const QString sub = b.value(QStringLiteral("sub")).toString().trimmed();
    if (title.isEmpty() && sub.isEmpty()) {
        box->setParent(parent);
        return box;
    }
    auto* wrap = new QWidget(parent);
    auto* wl = new QVBoxLayout(wrap);
    wl->setContentsMargins(0, 0, 0, 0);
    wl->setSpacing(5);
    add_head(wl, b, wrap);
    wl->addWidget(box);
    return wrap;
}

QWidget* make_html(const QJsonObject& b, QWidget* parent) {
    const QString html = b.value(QStringLiteral("html")).toString();
    if (html.trimmed().isEmpty())
        return nullptr;
    auto* card = new QFrame(parent);
    card->setObjectName(QStringLiteral("lkCard"));
    auto* vl = new QVBoxLayout(card);
    vl->setContentsMargins(12, 8, 12, 8);
    vl->setSpacing(4);
    add_head(vl, b, card);
    vl->addWidget(new LkHtmlView(html, card));
    return card;
}

} // namespace fincept::screens::langkinh::lkview
