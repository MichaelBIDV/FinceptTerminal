// src/screens/langkinh/LkTimeline.cpp
// Lăng Kính FFT — block "timeline" (dòng thời gian sự kiện chủ thể) theo CONTRACT_DELTA v4 · V4.3. Xem LkStory.h.
// Tách khỏi LkStory.cpp để mỗi tệp ≤ 800 dòng; helper chung (bậc, nhãn, tooltip) khai báo ở LkStory.h.
#include "screens/langkinh/LkBlockView.h"
#include "screens/langkinh/LkStory.h"
#include "ui/theme/Theme.h"

#include <QColor>
#include <QFrame>
#include <QHBoxLayout>
#include <QJsonArray>
#include <QLabel>
#include <QPainter>
#include <QPen>
#include <QSet>
#include <QVBoxLayout>

namespace fincept::screens::langkinh {

namespace lkstory {

using lkview::lk_tr;

constexpr int kDateW = 78;
constexpr int kRailW = 20;
constexpr double kDotY = 16.0; // tâm chấm = giữa dòng chữ đầu của mục (lề trên 7px + nửa dòng 12px)
constexpr double kDotR = 5.0;

// ── Timeline: đường ray (vạch dọc + chấm) ────────────────────────────────────────────────────────

class TlRail : public QWidget {
  public:
    TlRail(const QColor& dot, bool hollow, bool first, bool last, QWidget* parent)
        : QWidget(parent), dot_(dot), hollow_(hollow), first_(first), last_(last) {
        using namespace ui::colors;
        line_ = QColor(BORDER_MED());
        bg_ = QColor(BG_SURFACE());
        setFixedWidth(kRailW);
        setMinimumHeight(static_cast<int>(2.0 * kDotY));
    }

  protected:
    void paintEvent(QPaintEvent*) override {
        QPainter p(this);
        p.setRenderHint(QPainter::Antialiasing, true);
        const double cx = width() / 2.0;
        QPen lp(line_, 2.0);
        lp.setCapStyle(Qt::FlatCap);
        p.setPen(lp);
        if (!first_)
            p.drawLine(QPointF(cx, 0.0), QPointF(cx, kDotY - kDotR));
        if (!last_)
            p.drawLine(QPointF(cx, kDotY + kDotR), QPointF(cx, height()));
        p.setPen(QPen(dot_, 2.0));
        p.setBrush(hollow_ ? bg_ : dot_); // ngày ước → chấm rỗng
        p.drawEllipse(QPointF(cx, kDotY), kDotR, kDotR);
    }

  private:
    QColor dot_;
    QColor line_;
    QColor bg_;
    bool hollow_;
    bool first_;
    bool last_;
};

QWidget* timeline_row(const QJsonObject& it, bool first, bool last, QWidget* parent, const lkview::TickerFn& on_ticker) {
    using namespace ui::colors;
    const QString mau = str_of(it, "mau");
    const QColor c = mau.isEmpty() ? QColor(TEXT_SECONDARY()) : lk_color(mau);
    const bool uoc = it.value(QStringLiteral("ngay_uoc")).toBool(false);
    QString ngay = str_of(it, "ngay");
    if (ngay.isEmpty())
        ngay = lkview::dash();
    else if (uoc && !ngay.startsWith(QLatin1Char('~')))
        ngay.prepend(QLatin1Char('~'));
    const QString who = str_of(it, "chu_the");
    const QString act = str_of(it, "hanh_dong");
    const QString mo_ta = str_of(it, "mo_ta");
    QString gia = str_of(it, "gia");
    if (gia == lkview::dash()) // sự kiện không phải giao dịch: bỏ dòng "Giá —" (chỉ thêm nhiễu dọc)
        gia.clear();
    const QString bac = str_of(it, "bac");

    auto* row = new LinkFrame(str_of(it, "link"), on_ticker, parent); // `link`: dòng thời gian gộp của rổ
    row->setObjectName(QStringLiteral("lkTlRow"));
    row->setAttribute(Qt::WA_Hover, true);
    auto* hl = new QHBoxLayout(row);
    hl->setContentsMargins(4, 0, 6, 0); // lề dọc = 0 để vạch ray nối liền giữa các mục
    hl->setSpacing(8);
    auto* date = text_label(ngay, 10, QColor(uoc ? TEXT_TERTIARY() : TEXT_SECONDARY()), !uoc, row);
    date->setWordWrap(false);
    date->setFixedWidth(kDateW);
    date->setAlignment(Qt::AlignRight | Qt::AlignTop);
    date->setContentsMargins(0, 9, 0, 0);
    if (uoc)
        date->setToolTip(lk_tr("Ngày ước tính (~)"));
    hl->addWidget(date, 0, Qt::AlignTop);
    hl->addWidget(new TlRail(c, uoc, first, last, row));

    auto* body = new QWidget(row);
    auto* bl = new QVBoxLayout(body);
    bl->setContentsMargins(0, 7, 0, 9);
    bl->setSpacing(2);
    QString head;
    if (!who.isEmpty())
        head += QStringLiteral("<span style='color:%1'>%2</span>").arg(QString(TEXT_PRIMARY()), who.toHtmlEscaped());
    if (!act.isEmpty())
        head += (head.isEmpty() ? QString() : QStringLiteral(" · ")) +
                QStringLiteral("<span style='color:%1'>%2</span>").arg(c.name(), act.toHtmlEscaped());
    bl->addWidget(text_label(head.isEmpty() ? lkview::dash() : head, 12, QColor(TEXT_PRIMARY()), true, body,
                             Qt::RichText));
    if (!mo_ta.isEmpty())
        bl->addWidget(text_label(mo_ta, 11, QColor(TEXT_SECONDARY()), false, body));
    if (!gia.isEmpty())
        bl->addWidget(text_label(QStringLiteral("<span style='color:%1'>%2</span> %3")
                                     .arg(QString(TEXT_TERTIARY()), lk_tr("Giá"), gia.toHtmlEscaped()),
                                 10, QColor(TEXT_PRIMARY()), true, body, Qt::RichText));
    if (needs_no_decision(bac, {who, act, mo_ta, gia}))
        bl->addWidget(text_label(no_decision(), 9, QColor(WARNING()), true, body));
    hl->addWidget(body, 1);
    if (!bac.isEmpty()) {
        QLabel* chip = lkview::make_chip(bac, tier_color(bac), row);
        chip->setContentsMargins(0, 0, 0, 0);
        auto* cw = new QWidget(row);
        auto* cl = new QVBoxLayout(cw);
        cl->setContentsMargins(0, 8, 0, 0);
        cl->addWidget(chip);
        cl->addStretch(1);
        hl->addWidget(cw, 0);
    }
    const QString tip = str_of(it, "tip"); // app script thường đã mở đầu bằng "nguồn: …"
    const bool has_src = tip.startsWith(lk_tr("nguồn"), Qt::CaseInsensitive);
    row->setToolTip(tip_html({mo_ta, gia.isEmpty() ? QString() : lk_tr("Giá %1").arg(gia),
                              tip.isEmpty() || has_src ? tip : lk_tr("Nguồn: %1").arg(tip),
                              needs_no_decision(bac, {mo_ta, tip}) ? no_decision() : QString()},
                             (ngay + QStringLiteral(" · ") + who + QLatin1Char(' ') + act).trimmed()));
    row->wire_clicks();
    return row;
}

/// Chú giải màu theo loại (V4.3) — chỉ các màu thật sự xuất hiện trong mục.
QWidget* timeline_legend(const QSet<QString>& used, QWidget* parent) {
    struct Entry {
        const char* mau;
        const char* text;
    };
    static const Entry kEntries[] = {{"cyan", QT_TRANSLATE_NOOP("fincept::screens::langkinh::LkBlockView", "mua · gom · thâu tóm · đấu giá")},
                                     {"amber", QT_TRANSLATE_NOOP("fincept::screens::langkinh::LkBlockView", "bán · thoái")},
                                     {"info", QT_TRANSLATE_NOOP("fincept::screens::langkinh::LkBlockView", "phát hành · tăng vốn")},
                                     {"warn", QT_TRANSLATE_NOOP("fincept::screens::langkinh::LkBlockView", "pháp lý · cầm cố")},
                                     {"dim", QT_TRANSLATE_NOOP("fincept::screens::langkinh::LkBlockView", "khác")}};
    QStringList parts;
    for (const Entry& e : kEntries)
        if (used.contains(QLatin1String(e.mau)))
            parts << QStringLiteral("<span style='color:%1'>●</span> %2")
                         .arg(lk_color(QLatin1String(e.mau)).name(), lk_tr(e.text).toHtmlEscaped());
    if (parts.isEmpty())
        return nullptr;
    parts << QStringLiteral("<span style='color:%1'>○</span> %2")
                 .arg(QString(ui::colors::TEXT_SECONDARY()), lk_tr("ngày ước (~)").toHtmlEscaped());
    return text_label(parts.join(QStringLiteral("&nbsp;&nbsp;&nbsp;")), 10, QColor(ui::colors::TEXT_SECONDARY()), false,
                      parent, Qt::RichText);
}

} // namespace lkstory

namespace lkview {

QWidget* make_timeline(const QJsonObject& b, QWidget* parent, const TickerFn& on_ticker) {
    auto* card = new QFrame(parent);
    card->setObjectName(QStringLiteral("lkTimeline"));
    card->setStyleSheet(QStringLiteral("QFrame#lkTimeline { background:%1; border:1px solid %2; }"
                                       "QFrame#lkTlRow { background:transparent; border:none; }"
                                       "QFrame#lkTlRow:hover { background:%3; }")
                            .arg(ui::colors::BG_SURFACE(), ui::colors::BORDER_DIM(), ui::colors::BG_HOVER()));
    auto* vl = new QVBoxLayout(card);
    vl->setContentsMargins(10, 8, 10, 10);
    vl->setSpacing(4);
    add_head(vl, b, card);
    QVector<QJsonObject> items;
    QSet<QString> used;
    for (const auto& v : b.value(QStringLiteral("items")).toArray()) {
        const QJsonObject o = v.toObject();
        if (o.isEmpty())
            continue;
        items.append(o);
        const QString m = lkstory::str_of(o, "mau");
        used.insert(m.isEmpty() ? QStringLiteral("dim") : m);
    }
    if (items.isEmpty()) {
        vl->addWidget(make_label(lk_tr("— chưa có sự kiện —"), "lkCap", card));
        return card;
    }
    if (QWidget* lg = lkstory::timeline_legend(used, card))
        vl->addWidget(lg);
    auto* list = new QWidget(card);
    auto* ll = new QVBoxLayout(list);
    ll->setContentsMargins(0, 2, 0, 0);
    ll->setSpacing(0);
    for (int i = 0; i < items.size(); ++i)
        ll->addWidget(lkstory::timeline_row(items[i], i == 0, i == items.size() - 1, list, on_ticker));
    vl->addWidget(list);
    return card;
}

} // namespace lkview

} // namespace fincept::screens::langkinh
