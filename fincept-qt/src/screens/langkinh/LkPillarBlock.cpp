// src/screens/langkinh/LkPillarBlock.cpp
// Lăng Kính FFT — block "pillars" (LK_HOSO_SPEC §6). Xem LkPillarBlock.h.
//
// Chữ dựng bằng helper của LkChips (lk_label / lk_para_html / LkCapsLabel / lk_add_head): phông đi qua QSS riêng
// của từng nhãn vì QSS toàn cục của app có "* { font-family; font-size }" (setFont() bị ghi đè). QSS toàn cục cũng
// tô nền BG_BASE cho QWidget → mọi con trong thẻ đặt nền trong suốt ở QSS cấp thẻ.
#include "screens/langkinh/LkPillarBlock.h"

#include "screens/langkinh/LkChips.h"
#include "screens/langkinh/LkTheme.h"

#include <QFrame>
#include <QJsonArray>
#include <QLabel>
#include <QLayout>
#include <QList>
#include <QStringList>
#include <QVBoxLayout>

#include <algorithm>

namespace fincept::screens::langkinh {

// Helper tự do: namespace có tên riêng (quy ước của module, không dùng namespace ẩn danh).
namespace lkpillar {

constexpr int kLabW = 168;       // cột nhãn (Artifact .pl: grid 168px 1fr)
constexpr int kColGap = 20;      // khe giữa cột nhãn và đoạn văn
constexpr int kStackBelow = 760; // hàng hẹp hơn → nhãn nằm trên đoạn văn
constexpr int kMeasure = 680;    // bề rộng tối đa của đoạn văn (≈74ch như Artifact .pl p)
constexpr int kRowPadY = 14;     // đệm trên/dưới mỗi hàng
constexpr int kStackGap = 6;     // khe nhãn ↔ đoạn văn khi xếp dọc
constexpr int kParaGap = 10;     // khe giữa hai đoạn văn
constexpr double kLineEm = 1.62; // nhịp dòng đoạn văn = 1,62 × cỡ chữ (Artifact .pl p), đổi sang % Qt qua lk_line_pct

/// paras: mảng chuỗi (chuẩn) hoặc một chuỗi đơn; mục rỗng bị bỏ.
QStringList paras_of(const QJsonValue& v) {
    QStringList out;
    if (v.isString()) {
        if (const QString s = v.toString().trimmed(); !s.isEmpty())
            out << s;
        return out;
    }
    for (const auto& pv : v.toArray())
        if (const QString s = lkview::text_opt(pv); !s.isEmpty())
            out << s;
    return out;
}

// ── Hàng pillar: nhãn | đoạn văn ↔ xếp dọc, quyết định từ đúng hình chữ nhật được cấp ──────────────
// (không dựa vào resizeEvent: trang dựng lúc đang ẩn trong QStackedWidget có thể không nhận resize nào).

class RowLayout : public QLayout {
  public:
    explicit RowLayout(QWidget* parent) : QLayout(parent) { setContentsMargins(0, kRowPadY, 0, kRowPadY); }
    ~RowLayout() override {
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
        int w = 0;
        for (QLayoutItem* it : items_)
            w = std::max(w, it->minimumSize().width());
        const QMargins m = contentsMargins();
        return {w, m.top() + m.bottom()};
    }
    QSize sizeHint() const override {
        const int w = kLabW + kColGap + kMeasure;
        return {w, heightForWidth(w)};
    }

  private:
    static int item_h(QLayoutItem* it, int w) {
        const int h = it->hasHeightForWidth() ? it->heightForWidth(w) : it->sizeHint().height();
        return std::max(h, it->minimumSize().height());
    }

    /// Rộng ≥ kStackBelow: nhãn 168px bên trái, đoạn văn bên phải; hẹp hơn: nhãn trên, đoạn văn dưới.
    int do_layout(const QRect& rect, bool test_only) const {
        const QMargins m = contentsMargins();
        const QRect r = rect.adjusted(m.left(), m.top(), -m.right(), -m.bottom());
        const int pad = m.top() + m.bottom();
        if (items_.size() < 2 || r.width() <= 0)
            return pad;
        QLayoutItem* lab = items_.at(0);
        QLayoutItem* body = items_.at(1);
        int h = 0;
        if (rect.width() < kStackBelow) {
            const int bw = std::min(r.width(), kMeasure);
            const int hl = item_h(lab, r.width());
            const int hb = item_h(body, bw);
            if (!test_only) {
                lab->setGeometry(QRect(r.x(), r.y(), r.width(), hl));
                body->setGeometry(QRect(r.x(), r.y() + hl + kStackGap, bw, hb));
            }
            h = hl + kStackGap + hb;
        } else {
            const int bw = std::clamp(r.width() - kLabW - kColGap, 1, kMeasure);
            const int hl = item_h(lab, kLabW);
            const int hb = item_h(body, bw);
            if (!test_only) {
                lab->setGeometry(QRect(r.x(), r.y(), kLabW, hl));
                body->setGeometry(QRect(r.x() + kLabW + kColGap, r.y(), bw, hb));
            }
            h = std::max(hl, hb);
        }
        return h + pad;
    }

    QList<QLayoutItem*> items_;
};

/// Vạch mảnh 1px giữa các hàng (màu line đặt ở QSS thẻ, objectName lkPlRule).
QFrame* rule(QWidget* parent) {
    auto* f = new QFrame(parent);
    f->setObjectName(QStringLiteral("lkPlRule"));
    f->setAttribute(Qt::WA_StyledBackground, true);
    f->setFrameShape(QFrame::NoFrame);
    f->setFixedHeight(1);
    return f;
}

/// Một hàng pillar; thiếu cả lab lẫn paras → nullptr (bỏ mục).
QWidget* make_row(const QJsonObject& it, QWidget* parent) {
    using namespace lkview;
    const QString lab = text_opt(it.value(QStringLiteral("lab")));
    const QString sub = text_opt(it.value(QStringLiteral("sub")));
    const QStringList paras = paras_of(it.value(QStringLiteral("paras")));
    if (lab.isEmpty() && paras.isEmpty())
        return nullptr;

    auto* row = new QWidget(parent);
    row->setObjectName(QStringLiteral("lkPlRow"));
    auto* rl = new RowLayout(row);

    // Cột nhãn: mono chữ hoa giãn chữ 0,06em màu amber; sub bên dưới, mono muted, giữ hoa/thường.
    auto* labw = new QWidget(row);
    auto* ll = new QVBoxLayout(labw);
    ll->setContentsMargins(0, 2, 0, 0);
    ll->setSpacing(3);
    ll->addWidget(new LkCapsLabel(lab.isEmpty() ? dash() : lab, lk_font_mono(11, 500), LkRole::Amber, labw, 0.06, true));
    if (!sub.isEmpty())
        ll->addWidget(lk_label(sub, lk_font_mono(11), lk_col(LkRole::Muted), labw));

    // Đoạn văn: sans 14px ink-2, <b> đậm màu ink, <tag b="…"> thành chip bậc (lk_para_html).
    auto* body = new QWidget(row);
    auto* bl = new QVBoxLayout(body);
    bl->setContentsMargins(0, 0, 0, 0);
    bl->setSpacing(kParaGap);
    const QColor ink = lk_col(LkRole::Ink);
    const QColor ink2 = lk_col(LkRole::Ink2);
    const QFont pf = lk_font_sans(14);
    if (paras.isEmpty())
        bl->addWidget(lk_label(dash(), lk_font_sans(14), lk_col(LkRole::Muted), body));
    for (const QString& p : paras)
        bl->addWidget(lk_label(lk_para_html(p, ink, lk_line_pct(pf, kLineEm)), pf, ink2, body, Qt::RichText));

    rl->addWidget(labw);
    rl->addWidget(body);
    return row;
}

/// QSS của thẻ: nền surface, viền line, bo 10px; mọi con nền trong suốt; vạch lkPlRule màu line.
QString card_qss() {
    using namespace lkview;
    return QStringLiteral("QFrame#lkPlCard { background:%1; border:1px solid %2; border-radius:10px; }"
                          "QFrame#lkPlCard QWidget { background:transparent; border:none; }"
                          "QFrame#lkPlCard QFrame#lkPlRule { background:%2; }")
        .arg(lk_qss(lk_col(LkRole::Surface)), lk_qss(lk_col(LkRole::Line)));
}

} // namespace lkpillar

namespace lkview {

QWidget* make_pillars(const QJsonObject& b, QWidget* parent) {
    using namespace lkpillar;
    auto* card = new QFrame(parent);
    card->setObjectName(QStringLiteral("lkPlCard"));
    card->setAttribute(Qt::WA_StyledBackground, true);

    QList<QWidget*> rows;
    for (const auto& iv : b.value(QStringLiteral("items")).toArray())
        if (QWidget* r = make_row(iv.toObject(), card))
            rows << r;
    if (rows.isEmpty()) {
        delete card;
        return nullptr;
    }
    card->setStyleSheet(card_qss());

    const bool has_head = !b.value(QStringLiteral("title")).toString().trimmed().isEmpty() ||
                          !b.value(QStringLiteral("sub")).toString().trimmed().isEmpty() ||
                          !b.value(QStringLiteral("b")).toString().trimmed().isEmpty();
    auto* vl = new QVBoxLayout(card);
    vl->setContentsMargins(18, has_head ? 14 : 2, 18, 2);
    vl->setSpacing(0);
    if (has_head) {
        auto* hl = new QVBoxLayout;
        hl->setContentsMargins(0, 0, 0, 10);
        hl->setSpacing(3);
        lk_add_head(hl, b, card);
        vl->addLayout(hl);
        vl->addWidget(rule(card));
    }
    for (int i = 0; i < rows.size(); ++i) {
        if (i > 0)
            vl->addWidget(rule(card));
        vl->addWidget(rows.at(i));
    }
    return card;
}

} // namespace lkview

} // namespace fincept::screens::langkinh
