// src/screens/langkinh/LkPage.cpp
// Lăng Kính FFT — khung trang hồ sơ theo hợp đồng block v2: banner CỔNG .gate, đầu trang, thẻ .fig, QSS bảng,
// chú giải chart, block "row" và đầu phần có eyebrow. Xem LkPage.h.
#include "screens/langkinh/LkPage.h"

#include "screens/langkinh/LkChartUtil.h"
#include "screens/langkinh/LkChips.h"
#include "screens/langkinh/LkLayouts.h"
#include "screens/langkinh/LkTheme.h"
#include "screens/langkinh/LkWidgets.h"

#include <QFontMetricsF>
#include <QFrame>
#include <QHBoxLayout>
#include <QLabel>
#include <QPainter>
#include <QSizePolicy>
#include <QStringList>
#include <QVBoxLayout>
#include <QVector>

#include <algorithm>
#include <cmath>
#include <utility>

namespace fincept::screens::langkinh {

// Helper tự do: namespace có tên riêng (quy ước của module, không dùng namespace ẩn danh).
namespace lkpage {

using namespace lkview;

constexpr double kSwatchW = 18.0; // Artifact .legend i{width:18px; border-top:2px}
constexpr double kSwatchGap = 5.0;
constexpr double kItemGapX = 14.0; // .legend{gap:4px 14px}
constexpr double kItemGapY = 4.0;
constexpr int kLegendPx = 12;

/// Chú giải chart tự vẽ: mỗi mục = vạch 18px (liền / đứt 3-3) màu series + chữ ink2, xếp chảy theo bề rộng.
class Legend : public QWidget {
  public:
    struct Item {
        QString text;
        QString mau;
        bool dash = false;
    };

    Legend(QVector<Item> items, bool hoso, QWidget* parent) : QWidget(parent), items_(std::move(items)), hoso_(hoso) {
        QSizePolicy sp(QSizePolicy::Preferred, QSizePolicy::Preferred);
        sp.setHeightForWidth(true);
        setSizePolicy(sp);
        lk_transparent(this); // widget lá tự vẽ: không có con để luật lan xuống
        QStringList acc;
        for (const Item& it : std::as_const(items_))
            acc << it.text;
        setAccessibleName(acc.join(QStringLiteral(" · ")));
    }

    bool hasHeightForWidth() const override { return true; }
    int heightForWidth(int w) const override { return static_cast<int>(std::ceil(place(w).h)); }
    QSize sizeHint() const override {
        const int w = static_cast<int>(std::ceil(natural_w()));
        return {w, heightForWidth(w)};
    }
    QSize minimumSizeHint() const override {
        return {std::min(160, sizeHint().width()), static_cast<int>(std::ceil(QFontMetricsF(font_of()).height()))};
    }

  protected:
    void paintEvent(QPaintEvent*) override {
        QPainter p(this);
        p.setRenderHint(QPainter::TextAntialiasing, true);
        const QFont f = font_of();
        const QFontMetricsF fm(f);
        p.setFont(f);
        const Geo g = place(width());
        for (int i = 0; i < g.rects.size(); ++i) {
            const QRectF r = g.rects.at(i);
            const Item& it = items_.at(i);
            const QColor c = lkchart::series_color(it.mau, i, hoso_);
            // Vạch 2px trên toạ độ nguyên (sắc ở 1x lẫn 2x); đứt = đoạn 3px cách 3px.
            const double yc = std::round(r.center().y());
            if (it.dash) {
                for (double k = 0.0; k < kSwatchW; k += 6.0)
                    p.fillRect(QRectF(std::round(r.left() + k), yc - 1.0, 3.0, 2.0), c);
            } else {
                p.fillRect(QRectF(std::round(r.left()), yc - 1.0, kSwatchW, 2.0), c);
            }
            const QRectF tr = r.adjusted(kSwatchW + kSwatchGap, 0.0, 0.0, 0.0);
            p.setPen(lk_col(LkRole::Ink2));
            p.drawText(tr, Qt::AlignLeft | Qt::AlignVCenter, fm.elidedText(it.text, Qt::ElideRight, tr.width() + 0.5));
        }
    }

  private:
    struct Geo {
        QVector<QRectF> rects;
        double h = 0.0;
    };

    static QFont font_of() { return lk_font_sans(kLegendPx); }

    double item_w(const Item& it, const QFontMetricsF& fm) const {
        return kSwatchW + kSwatchGap + fm.horizontalAdvance(it.text) + 1.0;
    }

    double natural_w() const {
        const QFontMetricsF fm(font_of());
        double w = 0.0;
        for (const Item& it : items_)
            w += item_w(it, fm) + kItemGapX;
        return std::max(0.0, w - kItemGapX);
    }

    Geo place(double w) const {
        Geo g;
        const QFontMetricsF fm(font_of());
        const double lh = std::ceil(fm.height());
        const double avail = std::max(1.0, w);
        double x = 0.0;
        double y = 0.0;
        for (const Item& it : items_) {
            const double iw = std::min(item_w(it, fm), avail);
            if (x > 0.0 && x + iw > avail) {
                x = 0.0;
                y += lh + kItemGapY;
            }
            g.rects << QRectF(x, y, iw, lh);
            x += iw + kItemGapX;
        }
        g.h = items_.isEmpty() ? 0.0 : y + lh;
        return g;
    }

    QVector<Item> items_;
    bool hoso_;
};

QString muc_vi(const QString& muc) {
    if (muc == QLatin1String("ok"))
        return lk_tr("mở");
    if (muc == QLatin1String("canh_bao"))
        return lk_tr("cảnh báo");
    if (muc == QLatin1String("dung"))
        return lk_tr("dừng");
    return muc;
}

} // namespace lkpage

namespace lkview {

bool is_hoso(const QJsonObject& payload) {
    return payload.value(QStringLiteral("layout")).toString().trimmed().compare(QLatin1String("hoso"),
                                                                                  Qt::CaseInsensitive) == 0;
}

bool has_section_head(const QJsonObject& b) {
    return b.value(QStringLiteral("type")).toString() != QLatin1String("tkhead") &&
           !b.value(QStringLiteral("eyebrow")).toString().trimmed().isEmpty();
}

QWidget* make_gate(const QJsonValue& cong_v, QWidget* parent) {
    const QJsonObject cong = cong_v.toObject();
    QString muc = cong.value(QStringLiteral("muc")).toString().trimmed();
    QString dong = cong.value(QStringLiteral("dong")).toString().trimmed();
    if (dong.isEmpty()) { // không có dòng CỔNG thì không được coi là "ok": DỪNG, không kết luận per-mã
        muc = QStringLiteral("dung");
        dong = lk_tr("CỔNG: [CẦN DATA — trang không kèm dòng CỔNG] · không kết luận per-mã");
    }
    const QColor amber = lk_col(LkRole::Amber);
    const QColor ink = lk_col(LkRole::Ink);

    auto* f = new QFrame(parent);
    f->setObjectName(QStringLiteral("lkGate"));
    f->setStyleSheet(QStringLiteral("QFrame#lkGate { background:%1; border:1px solid %2; border-radius:12px; }"
                                    "QFrame#lkGate QWidget { background:transparent; border:none; }")
                         .arg(lk_qss(lk_col(LkRole::AmberSoft)), lk_qss(lk_col(LkRole::AmberLine))));
    auto* vl = new QVBoxLayout(f);
    vl->setContentsMargins(20, 18, 20, 18);
    vl->setSpacing(0);

    auto* top = new QHBoxLayout;
    top->setContentsMargins(0, 0, 0, 0);
    top->setSpacing(12);
    QString eb = lk_tr("Dòng cổng");
    if (const QString m = lkpage::muc_vi(muc); !m.isEmpty())
        eb += QStringLiteral(" · ") + m;
    top->addWidget(new LkCapsLabel(eb, lk_font_mono(11), LkRole::Amber, f, 0.14), 1, Qt::AlignVCenter);
    const QString bac = cong.value(QStringLiteral("bac")).toString().trimmed();
    if (!bac.isEmpty()) {
        QLabel* bl = lk_label(bac, lk_font_mono(11), lk_col(LkRole::Muted), f);
        bl->setWordWrap(false);
        bl->setAlignment(Qt::AlignRight | Qt::AlignVCenter);
        top->addWidget(bl, 0, Qt::AlignVCenter);
    }
    vl->addLayout(top);
    vl->addSpacing(8);
    const QFont fd = lk_font_mono(14);
    vl->addWidget(lk_label(lk_para_html(dong, amber, lk_line_pct(fd, 1.6)), fd, ink, f, Qt::RichText));

    const QString chi_tiet = cong.value(QStringLiteral("chi_tiet")).toString().trimmed();
    if (!chi_tiet.isEmpty()) {
        vl->addSpacing(10);
        const QFont fc = lk_font_sans(14);
        vl->addWidget(
            lk_label(lk_para_html(chi_tiet, ink, lk_line_pct(fc)), fc, lk_col(LkRole::Ink2), f, Qt::RichText));
    }
    for (const auto& c : cong.value(QStringLiteral("canh_bao")).toArray()) {
        const QString t = c.toString().trimmed();
        if (t.isEmpty())
            continue;
        vl->addSpacing(6);
        vl->addWidget(lk_label(lk_tr("Cảnh báo: %1").arg(t), lk_font_sans(12), lk_col(LkRole::Down), f));
    }
    return f;
}

QWidget* make_hoso_header(const QJsonObject& payload, bool meta_only, QWidget* parent) {
    auto* w = new QWidget(parent);
    w->setObjectName(QStringLiteral("lkHead"));
    auto* vl = new QVBoxLayout(w);
    vl->setContentsMargins(0, 0, 0, 0);
    vl->setSpacing(0);
    const QColor ink = lk_col(LkRole::Ink);
    bool any = false;
    if (!meta_only) {
        const QString title = payload.value(QStringLiteral("title")).toString().trimmed();
        const QString sub = payload.value(QStringLiteral("sub")).toString().trimmed();
        if (!title.isEmpty()) {
            vl->addWidget(lk_label(lk_inline_html(title, ink), lk_font_serif(34, 600), ink, w, Qt::RichText));
            any = true;
        }
        if (!sub.isEmpty()) {
            vl->addSpacing(8);
            vl->addWidget(lk_measure(
                lk_label(lk_inline_html(sub, ink), lk_font_sans(15), lk_col(LkRole::Ink2), w, Qt::RichText), 820, w));
            any = true;
        }
    }
    QStringList meta;
    const QString scope = payload.value(QStringLiteral("scope")).toString().trimmed();
    const QString as_of = payload.value(QStringLiteral("as_of")).toString().trimmed();
    const QString tuoi = payload.value(QStringLiteral("tuoi")).toString().trimmed();
    if (!scope.isEmpty())
        meta << scope;
    if (!as_of.isEmpty())
        meta << lk_tr("dữ liệu tới %1").arg(as_of);
    if (!tuoi.isEmpty())
        meta << tuoi;
    if (!meta.isEmpty()) {
        if (any)
            vl->addSpacing(12);
        const bool stale = tuoi.contains(QStringLiteral("CŨ"));
        vl->addWidget(lk_label(meta.join(QStringLiteral(" · ")), lk_font_mono(12, stale ? 600 : 400),
                               lk_col(stale ? LkRole::Amber : LkRole::Muted), w));
        any = true;
    }
    if (!any) {
        delete w;
        return nullptr;
    }
    return w;
}

QFrame* make_fig(QWidget* parent, QVBoxLayout** out) {
    auto* f = new QFrame(parent);
    f->setObjectName(QStringLiteral("lkFig"));
    f->setStyleSheet(QStringLiteral("QFrame#lkFig { background:%1; border:1px solid %2; border-radius:10px; }")
                         .arg(lk_qss(lk_col(LkRole::Surface)), lk_qss(lk_col(LkRole::Line))));
    auto* vl = new QVBoxLayout(f);
    vl->setContentsMargins(14, 14, 14, 10);
    vl->setSpacing(6);
    if (out)
        *out = vl;
    return f;
}

QString hoso_table_qss() {
    const QString surface = lk_qss(lk_col(LkRole::Surface));
    const QString line = lk_qss(lk_col(LkRole::Line));
    return QStringLiteral(
               "QTableWidget { background:%1; color:%2; border:none; gridline-color:%3; %4 }"
               "QTableWidget::item { padding:0px 12px; border:none; border-bottom:1px solid %3; }"
               "QTableWidget::item:selected { background:%5; color:%2; }"
               "QHeaderView::section { background:%6; color:%7; border:none; border-bottom:1px solid %3;"
               "  padding:8px 12px; %8 }"
               "QHeaderView { background:%6; border:none; }"
               "QTableCornerButton::section { background:%6; border:none; }"
               "QScrollBar:horizontal { background:%1; height:6px; }"
               "QScrollBar::handle:horizontal { background:%9; min-width:24px; }"
               "QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal { width:0; }"
               "QScrollBar:vertical { background:%1; width:6px; }"
               "QScrollBar::handle:vertical { background:%9; min-height:24px; }"
               "QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height:0; }")
        .arg(surface, lk_qss(lk_col(LkRole::Ink)), line, lk_font_css(lk_font_sans(13)),
             lk_qss(lk_col(LkRole::AmberSoft)), lk_qss(lk_col(LkRole::Surface2)), lk_qss(lk_col(LkRole::Muted)),
             lk_font_css(lk_font_mono(11, 600)), lk_qss(lk_col(LkRole::Line2)));
}

QWidget* make_legend(const QJsonArray& items, bool hoso, QWidget* parent) {
    QVector<lkpage::Legend::Item> out;
    for (const auto& iv : items) {
        if (!iv.isObject())
            continue;
        const QJsonObject o = iv.toObject();
        lkpage::Legend::Item it;
        it.text = text_opt(o.value(QStringLiteral("text")));
        if (it.text.isEmpty())
            continue;
        it.mau = o.value(QStringLiteral("mau")).toString().trimmed();
        it.dash = o.value(QStringLiteral("dash")).toBool(false);
        out << it;
    }
    if (out.isEmpty())
        return nullptr;
    return new lkpage::Legend(std::move(out), hoso, parent);
}

QWidget* make_row(const QJsonObject& b, QWidget* parent, const BlockFn& make) {
    auto* box = new QWidget(parent);
    box->setObjectName(QStringLiteral("lkRow"));
    auto* vl = new QVBoxLayout(box);
    vl->setContentsMargins(0, 0, 0, 0);
    vl->setSpacing(6);
    lk_add_head(vl, b, box); // title/sub/b của hàng (eyebrow đã thành đầu phần ở make_section)
    auto* row = new QWidget(box);
    row->setObjectName(QStringLiteral("lkRow"));
    auto* lay = new LkRowLayout(row, kHosoGap, kRowStackBelow);
    // "flex":[1,2] — trọng số bề rộng theo thứ tự items; chỉ dùng khi đủ số lượng và mọi số > 0.
    const QJsonArray items = b.value(QStringLiteral("items")).toArray();
    const QJsonArray fa = b.value(QStringLiteral("flex")).toArray();
    bool use_flex = !fa.isEmpty() && fa.size() == items.size();
    QVector<double> flex;
    for (int k = 0; k < items.size(); ++k) {
        const QJsonValue& iv = items.at(k);
        if (!iv.isObject() || !make)
            continue;
        if (QWidget* w = make(iv.toObject(), row)) {
            lay->addWidget(w);
            double f = 0.0;
            use_flex = use_flex && num_of(fa.at(k), &f) && f > 0.0;
            flex << f;
        }
    }
    if (lay->count() == 0) {
        delete box;
        return nullptr;
    }
    if (use_flex)
        lay->set_flex(flex);
    vl->addWidget(row);
    return box;
}

QWidget* make_section(const QJsonObject& b, QWidget* parent, const BlockFn& make) {
    auto* sec = new QWidget(parent);
    sec->setObjectName(QStringLiteral("lkSec"));
    auto* vl = new QVBoxLayout(sec);
    vl->setContentsMargins(0, 0, 0, 0);
    vl->setSpacing(0);
    lk_section_head(vl, b, sec);
    QJsonObject inner = b;
    for (const char* k : {"eyebrow", "title", "sub", "b"})
        inner.remove(QLatin1String(k));
    if (make)
        if (QWidget* w = make(inner, sec))
            vl->addWidget(w);
    return sec;
}

} // namespace lkview

} // namespace fincept::screens::langkinh
