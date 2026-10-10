// src/screens/langkinh/LkStory.cpp
// Lăng Kính FFT — block "story" (thẻ infographic chủ thể) và "timeline" (dòng thời gian sự kiện)
// theo CONTRACT_DELTA v4 · V4.3. Xem LkStory.h.
#include "screens/langkinh/LkStory.h"

#include "screens/langkinh/LkBlockView.h"
#include "ui/theme/Theme.h"

#include <QAbstractButton>
#include <QEvent>
#include <QFont>
#include <QFontMetricsF>
#include <QFrame>
#include <QGridLayout>
#include <QHBoxLayout>
#include <QJsonArray>
#include <QLabel>
#include <QLayout>
#include <QMouseEvent>
#include <QPainter>
#include <QPainterPath>
#include <QPen>
#include <QPushButton>
#include <QSizePolicy>
#include <QStringList>
#include <QVBoxLayout>

#include <algorithm>
#include <cmath>
#include <limits>

namespace fincept::screens::langkinh {

// Helper tự do: namespace có tên riêng (quy ước SKIP_UNITY của module, không dùng namespace ẩn danh).
namespace lkstory {

using lkview::lk_tr;

constexpr int kStackBelow = 880;          // bề rộng bố cục (≈ thẻ 900px) nhỏ hơn → 3 cột xếp dọc
constexpr int kColGap = 10;
constexpr int kWeights[3] = {26, 42, 32}; // chủ thể · động cơ · thước vùng giá
constexpr int kGaugeH = 72;
constexpr int kGaugeMinW = 200;
constexpr double kGaugePad = 12.0;

double nan_value() {
    return std::numeric_limits<double>::quiet_NaN();
}

double num_or_nan(const QJsonValue& v) {
    double d = 0.0;
    return lkview::num_of(v, &d) ? d : nan_value();
}

QString str_of(const QJsonObject& o, const char* key) {
    return lkview::text_opt(o.value(QLatin1String(key)));
}

/// Bậc bằng chứng → màu chip. Không dùng bull/bear: bậc không phải tín hiệu tăng/giảm.
QColor tier_color(const QString& bac) {
    using namespace ui::colors;
    const QString b = bac.trimmed().toUpper();
    if (b.startsWith(QLatin1String("FACT-T1")))
        return QColor(INFO());
    if (b.startsWith(QLatin1String("FACT-T2")))
        return QColor(CYAN());
    if (b.startsWith(QLatin1String("SS-T3")))
        return QColor(AMBER());
    if (b.startsWith(QLatin1String("UNVERIFIED")))
        return QColor(WARNING());
    return QColor(TEXT_SECONDARY()); // EST và nhãn lạ
}

bool is_unverified(const QString& bac) {
    return bac.trimmed().toUpper().startsWith(QLatin1String("UNVERIFIED"));
}

QString no_decision() {
    return lk_tr("UNVERIFIED — không dùng cho quyết định");
}

bool needs_no_decision(const QString& bac, const QStringList& shown) {
    if (!is_unverified(bac))
        return false;
    const QString phrase = lk_tr("không dùng cho quyết định");
    return std::none_of(shown.cbegin(), shown.cend(),
                        [&](const QString& t) { return t.contains(phrase, Qt::CaseInsensitive); });
}

/// Tooltip rich text từ các đoạn chữ thô (tự escape, " | " = xuống dòng); rỗng khi không có đoạn nào
/// (dòng đầu `head` đứng một mình không đủ thành tooltip).
QString tip_html(const QStringList& plain_parts, const QString& head) {
    QStringList out;
    for (const QString& s : plain_parts)
        if (!s.trimmed().isEmpty())
            out << s.trimmed().toHtmlEscaped().replace(QStringLiteral(" | "), QStringLiteral("<br>"));
    if (out.isEmpty())
        return {};
    if (!head.trimmed().isEmpty())
        out.prepend(QStringLiteral("<b>%1</b>").arg(head.trimmed().toHtmlEscaped()));
    return QStringLiteral("<qt>") + out.join(QStringLiteral("<br>")) + QStringLiteral("</qt>");
}

QString fmt_price(double v) {
    const double a = std::abs(v);
    return lkview::vn_num(v, a >= 1000.0 ? 0 : (a >= 10.0 ? 1 : 2));
}

QString fmt_pct(double v) {
    QString s = lkview::vn_num(v, 1);
    if (v > 0.0 && s != QStringLiteral("0,0"))
        s.prepend(QLatin1Char('+'));
    return s + QLatin1Char('%');
}

/// Nhãn chữ của thẻ: xuống dòng, KHÔNG bắt chuột (bấm xuyên xuống thẻ để mở mã).
QLabel* text_label(const QString& text, int px, const QColor& c, bool bold, QWidget* parent, Qt::TextFormat fmt) {
    auto* l = new QLabel(parent);
    l->setTextFormat(fmt);
    l->setText(text);
    l->setWordWrap(true);
    l->setTextInteractionFlags(Qt::NoTextInteraction);
    l->setStyleSheet(QStringLiteral("QLabel { color:%1; font-size:%2px; font-weight:%3; background:transparent; }")
                         .arg(c.name())
                         .arg(px)
                         .arg(bold ? 700 : 400));
    return l;
}

/// Tiêu đề cột kiểu chữ hoa nhỏ + chip bậc (nếu có).
QLayout* col_head(const QString& title, const QString& bac, const QString& tip, QWidget* parent) {
    auto* hl = new QHBoxLayout;
    hl->setSpacing(6);
    auto* t = text_label(title, 9, QColor(ui::colors::TEXT_SECONDARY()), true, parent);
    t->setWordWrap(false);
    hl->addWidget(t, 1, Qt::AlignVCenter);
    if (!bac.trimmed().isEmpty()) {
        QLabel* c = lkview::make_chip(bac.trimmed(), tier_color(bac), parent);
        QStringList tl{tip};
        if (is_unverified(bac))
            tl << no_decision();
        c->setToolTip(tip_html(tl, bac));
        hl->addWidget(c, 0, Qt::AlignTop);
    }
    return hl;
}

// ── Bố cục 3 cột ↔ xếp dọc, quyết định từ đúng hình chữ nhật được cấp (không dựa vào resizeEvent) ──

class StoryLayout : public QLayout {
  public:
    explicit StoryLayout(QWidget* parent) : QLayout(parent) { setContentsMargins(0, 0, 0, 0); }
    ~StoryLayout() override {
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
        return {w, 0};
    }
    QSize sizeHint() const override {
        const int w = kStackBelow + 240;
        return {w, heightForWidth(w)};
    }

  private:
    static int item_h(QLayoutItem* it, int w) {
        const int h = it->hasHeightForWidth() ? it->heightForWidth(w) : it->sizeHint().height();
        return std::max(h, it->minimumSize().height());
    }
    int do_layout(const QRect& rect, bool test_only) const {
        const int n = count();
        if (n == 0 || rect.width() <= 0)
            return 0;
        if (n < 2 || rect.width() < kStackBelow) {
            int y = rect.y();
            for (QLayoutItem* it : items_) {
                const int h = item_h(it, rect.width());
                if (!test_only)
                    it->setGeometry(QRect(rect.x(), y, rect.width(), h));
                y += h + kColGap;
            }
            return y - kColGap - rect.y();
        }
        int wsum = 0;
        for (int i = 0; i < n; ++i)
            wsum += i < 3 ? kWeights[i] : 30;
        const int avail = rect.width() - (n - 1) * kColGap;
        QVector<int> ws;
        int used = 0;
        for (int i = 0; i < n; ++i) {
            const int wi = i == n - 1 ? avail - used : avail * (i < 3 ? kWeights[i] : 30) / wsum;
            ws.append(wi);
            used += wi;
        }
        int h = 0;
        for (int i = 0; i < n; ++i)
            h = std::max(h, item_h(items_[i], ws[i]));
        if (!test_only) {
            int x = rect.x();
            for (int i = 0; i < n; ++i) {
                items_[i]->setGeometry(QRect(x, rect.y(), ws[i], h));
                x += ws[i] + kColGap;
            }
        }
        return h;
    }

    QList<QLayoutItem*> items_;
};

// ── Thước vùng giá: dải [lo, hi] · vạch VWAP · tam giác "giá nay" ──────────────────────────────────

class PriceGauge : public QWidget {
  public:
    PriceGauge(double lo, double hi, double vwap, double nay, QWidget* parent)
        : QWidget(parent), lo_(std::min(lo, hi)), hi_(std::max(lo, hi)), vwap_(vwap), nay_(nay) {
        using namespace ui::colors;
        setObjectName(QStringLiteral("lkGauge"));
        setSizePolicy(QSizePolicy::Expanding, QSizePolicy::Fixed);
        setFixedHeight(kGaugeH);
        if (!std::isfinite(lo) || !std::isfinite(hi)) { // chỉ có một đầu → không vẽ dải
            lo_ = nan_value();
            hi_ = nan_value();
        }
        double mn = std::numeric_limits<double>::infinity();
        double mx = -mn;
        for (const double v : {lo, hi, vwap, nay})
            if (std::isfinite(v)) {
                mn = std::min(mn, v);
                mx = std::max(mx, v);
            }
        a0_ = mn * 0.9; // V4.3: min(lo, nay)·0,9 … max(hi, nay)·1,1
        a1_ = mx * 1.1;
        if (!(a1_ > a0_)) {
            a0_ = mn - 1.0;
            a1_ = mx + 1.0;
        }
        track_ = QColor(BORDER_MED());
        zone_ = QColor(AMBER());
        now_ = QColor(TEXT_PRIMARY());
        dim_ = QColor(TEXT_SECONDARY());
        edge_ = QColor(BG_BASE());
    }
    QSize sizeHint() const override { return {320, kGaugeH}; }
    QSize minimumSizeHint() const override { return {kGaugeMinW, kGaugeH}; }

  protected:
    void paintEvent(QPaintEvent*) override {
        QPainter p(this);
        p.setRenderHint(QPainter::Antialiasing, true);
        constexpr double ty = 32.0; // tâm thanh thước
        p.setPen(Qt::NoPen);
        p.setBrush(track_);
        p.drawRoundedRect(QRectF(kGaugePad, ty - 2.0, width() - 2.0 * kGaugePad, 4.0), 2.0, 2.0);
        QFont f9;
        f9.setPixelSize(9);
        QFont f9b = f9;
        f9b.setBold(true);
        QFont f10b;
        f10b.setPixelSize(10);
        f10b.setBold(true);
        if (std::isfinite(lo_) && std::isfinite(hi_)) {
            double x0 = x_of(lo_);
            double x1 = x_of(hi_);
            if (x1 - x0 < 3.0) {
                const double c = (x0 + x1) / 2.0;
                x0 = c - 1.5;
                x1 = c + 1.5;
            }
            QColor fill = zone_;
            fill.setAlpha(72);
            p.setBrush(fill);
            p.setPen(QPen(zone_, 1.0));
            p.drawRect(QRectF(x0, ty - 8.0, x1 - x0, 16.0));
            // Nhãn hai đầu dải ở hàng dưới cùng; chạm nhau → gộp "lo–hi" ở giữa dải. Một mức giá trùng VWAP
            // (nguồn nêu một giá) → nhãn VWAP đã đủ, không lặp số.
            p.setFont(f9);
            p.setPen(dim_);
            const QString sl = fmt_price(lo_);
            const QString sh = fmt_price(hi_);
            const QFontMetricsF fm(f9);
            const QRectF rl = text_box(sl, fm, x0, 58.0);
            const QRectF rh = text_box(sh, fm, x1, 58.0);
            const bool one_price = lo_ == hi_ && vwap_ == lo_;
            if (!one_price && (rl.right() + 4.0 > rh.left() || lo_ == hi_)) {
                const QString both = lo_ == hi_ ? sl : sl + QStringLiteral("–") + sh;
                p.drawText(text_box(both, fm, (x0 + x1) / 2.0, 58.0), Qt::AlignCenter, both);
            } else if (!one_price) {
                p.drawText(rl, Qt::AlignCenter, sl);
                p.drawText(rh, Qt::AlignCenter, sh);
            }
        }
        if (std::isfinite(vwap_)) {
            const double xv = x_of(vwap_);
            p.setPen(QPen(zone_, 2.2));
            p.drawLine(QPointF(xv, ty - 11.0), QPointF(xv, ty + 11.0));
            p.setFont(f9b);
            const QString sv = lk_tr("VWAP %1").arg(fmt_price(vwap_));
            p.drawText(text_box(sv, QFontMetricsF(f9b), xv, 44.0), Qt::AlignCenter, sv);
        }
        if (std::isfinite(nay_)) {
            const double xn = x_of(nay_);
            QPainterPath tri;
            tri.moveTo(xn, ty - 9.0);
            tri.lineTo(xn + 6.0, ty - 19.0);
            tri.lineTo(xn - 6.0, ty - 19.0);
            tri.closeSubpath();
            p.setPen(QPen(edge_, 1.2));
            p.setBrush(now_);
            p.drawPath(tri);
            p.setFont(f10b);
            p.setPen(now_);
            const QString sn = lk_tr("nay %1").arg(fmt_price(nay_));
            p.drawText(text_box(sn, QFontMetricsF(f10b), xn, 0.0), Qt::AlignCenter, sn);
        }
    }

  private:
    double x_of(double v) const {
        const double w = std::max(1.0, width() - 2.0 * kGaugePad);
        return kGaugePad + (v - a0_) / (a1_ - a0_) * w;
    }
    /// Hộp chữ canh giữa tại x, kẹp trong bề rộng widget.
    QRectF text_box(const QString& s, const QFontMetricsF& fm, double x, double top) const {
        const double w = fm.horizontalAdvance(s) + 4.0;
        const double left = std::clamp(x - w / 2.0, 0.0, std::max(0.0, width() - w));
        return QRectF(left, top, w, fm.height() + 1.0);
    }

    double lo_;
    double hi_;
    double vwap_;
    double nay_;
    double a0_ = 0.0;
    double a1_ = 1.0;
    QColor track_;
    QColor zone_;
    QColor now_;
    QColor dim_;
    QColor edge_;
};

// ── LinkFrame: bấm bất kỳ đâu (trừ nút) → mở mã ────────────────────────────────────────────────────

LinkFrame::LinkFrame(const QString& link, const lkview::TickerFn& fn, QWidget* parent)
    : QFrame(parent), link_(link), fn_(fn) {}

void LinkFrame::wire_clicks() {
    if (link_.isEmpty())
        return;
    setCursor(Qt::PointingHandCursor);
    const QString hint = lk_tr("Bấm để mở chuỗi FFT × Giá của %1").arg(link_);
    if (toolTip().isEmpty())
        setToolTip(hint);
    else if (toolTip().endsWith(QLatin1String("</qt>")))
        setToolTip(toolTip().chopped(5) + QStringLiteral("<br><i>") + hint.toHtmlEscaped() + QStringLiteral("</i></qt>"));
    const QList<QWidget*> kids = findChildren<QWidget*>();
    for (QWidget* w : kids)
        if (!qobject_cast<QAbstractButton*>(w))
            w->installEventFilter(this);
}

bool LinkFrame::eventFilter(QObject* o, QEvent* e) {
    if (e->type() == QEvent::MouseButtonRelease) {
        auto* me = static_cast<QMouseEvent*>(e);
        auto* w = qobject_cast<QWidget*>(o);
        if (me->button() == Qt::LeftButton && w && rect().contains(mapFrom(w, me->position().toPoint())) && fire())
            return true;
    }
    return QFrame::eventFilter(o, e);
}

void LinkFrame::mousePressEvent(QMouseEvent* e) {
    if (!link_.isEmpty() && e->button() == Qt::LeftButton)
        e->accept();
    else
        QFrame::mousePressEvent(e);
}

void LinkFrame::mouseReleaseEvent(QMouseEvent* e) {
    if (e->button() == Qt::LeftButton && rect().contains(e->position().toPoint()) && fire())
        return;
    QFrame::mouseReleaseEvent(e);
}

bool LinkFrame::fire() {
    if (link_.isEmpty() || !fn_)
        return false;
    fn_(link_);
    return true;
}

QFrame* make_col(QWidget* parent) {
    auto* f = new QFrame(parent);
    f->setObjectName(QStringLiteral("lkStoryCol"));
    auto* vl = new QVBoxLayout(f);
    vl->setContentsMargins(10, 8, 10, 9);
    vl->setSpacing(6);
    return f;
}

QWidget* actor_chip(const QJsonObject& a, QWidget* parent) {
    using namespace ui::colors;
    const QString ten = str_of(a, "ten");
    const QString vai = str_of(a, "vai_tro");
    const QString so_huu = str_of(a, "so_huu");
    const QString bac = str_of(a, "bac");
    const QString tip = str_of(a, "tip");
    if (ten.isEmpty() && vai.isEmpty())
        return nullptr;
    auto* f = new QFrame(parent);
    f->setObjectName(QStringLiteral("lkStoryActor"));
    f->setStyleSheet(QStringLiteral("QFrame#lkStoryActor { background:%1; border:1px solid %2; border-left:3px solid %3; }")
                         .arg(BG_SURFACE(), BORDER_DIM(), tier_color(bac).name()));
    auto* vl = new QVBoxLayout(f);
    vl->setContentsMargins(8, 5, 8, 6);
    vl->setSpacing(2);
    auto* top = new QHBoxLayout;
    top->setSpacing(6);
    top->addWidget(text_label(ten.isEmpty() ? lkview::dash() : ten, 12, QColor(TEXT_PRIMARY()), true, f), 1);
    if (!bac.isEmpty()) {
        QLabel* c = lkview::make_chip(bac, tier_color(bac), f);
        c->setToolTip(tip_html({tip, is_unverified(bac) ? no_decision() : QString()}, bac));
        top->addWidget(c, 0, Qt::AlignTop);
    }
    vl->addLayout(top);
    if (!vai.isEmpty())
        vl->addWidget(text_label(vai, 10, QColor(TEXT_SECONDARY()), false, f));
    if (!so_huu.isEmpty() && so_huu != lkview::dash())
        vl->addWidget(text_label(lk_tr("Sở hữu %1").arg(so_huu), 10, QColor(AMBER()), false, f));
    if (needs_no_decision(bac, {ten, vai, so_huu}))
        vl->addWidget(text_label(no_decision(), 9, QColor(WARNING()), true, f));
    f->setToolTip(tip_html({vai, so_huu.isEmpty() ? QString() : lk_tr("Sở hữu %1").arg(so_huu), tip}, ten));
    return f;
}

QWidget* actors_col(const QJsonArray& actors, QWidget* parent) {
    QFrame* col = make_col(parent);
    auto* vl = static_cast<QVBoxLayout*>(col->layout());
    vl->addLayout(col_head(lk_tr("CHỦ THỂ"), {}, {}, col));
    int n = 0;
    for (const auto& v : actors)
        if (QWidget* w = actor_chip(v.toObject(), col)) {
            vl->addWidget(w);
            ++n;
        }
    if (n == 0)
        vl->addWidget(text_label(lk_tr("[CẦN DATA] chưa định danh chủ thể trong nguồn"), 10,
                                 QColor(ui::colors::TEXT_SECONDARY()), false, col));
    vl->addStretch(1);
    return col;
}

QWidget* break_box(const QJsonValue& dg, QWidget* parent) {
    using namespace ui::colors;
    const QJsonObject o = dg.toObject();
    const QString text = str_of(o, "text");
    if (text.isEmpty())
        return text_label(lk_tr("Điểm gãy: [CẦN DATA]"), 10, QColor(TEXT_SECONDARY()), false, parent);
    const QColor w(WARNING());
    auto* f = new QFrame(parent);
    f->setObjectName(QStringLiteral("lkStoryBreak"));
    f->setStyleSheet(QStringLiteral("QFrame#lkStoryBreak { background:%1; border:1px solid %2; border-left:3px solid %3; }")
                         .arg(lkview::rgba(w, 22), lkview::rgba(w, 120), w.name()));
    auto* vl = new QVBoxLayout(f);
    vl->setContentsMargins(9, 6, 9, 7);
    vl->setSpacing(3);
    auto* hl = new QHBoxLayout;
    hl->setSpacing(6);
    auto* t = text_label(lk_tr("ĐIỂM GÃY"), 9, w, true, f);
    t->setWordWrap(false);
    hl->addWidget(t, 1, Qt::AlignVCenter);
    const QString bac = str_of(o, "bac");
    if (!bac.isEmpty()) {
        QLabel* c = lkview::make_chip(bac, tier_color(bac), f);
        c->setToolTip(tip_html({str_of(o, "tip"), is_unverified(bac) ? no_decision() : QString()}, bac));
        hl->addWidget(c, 0, Qt::AlignTop);
    }
    vl->addLayout(hl);
    vl->addWidget(text_label(text, 11, QColor(TEXT_PRIMARY()), false, f));
    if (needs_no_decision(bac, {text}))
        vl->addWidget(text_label(no_decision(), 9, w, true, f));
    return f;
}

QWidget* motive_col(const QJsonObject& b, QWidget* parent) {
    using namespace ui::colors;
    QFrame* col = make_col(parent);
    auto* vl = static_cast<QVBoxLayout*>(col->layout());
    const QJsonObject dc = b.value(QStringLiteral("dong_co")).toObject();
    const QString dc_bac = str_of(dc, "bac");
    vl->addLayout(col_head(lk_tr("ĐỘNG CƠ"), dc_bac, str_of(dc, "tip"), col));
    const QString text = str_of(dc, "text");
    auto* tl = text_label(text.isEmpty() ? lk_tr("[CẦN DATA] động cơ chưa có nguồn") : text, 11,
                          QColor(text.isEmpty() ? TEXT_SECONDARY() : TEXT_PRIMARY()), false, col);
    tl->setToolTip(tip_html({str_of(dc, "tip")}, lk_tr("Nguồn")));
    vl->addWidget(tl);
    if (needs_no_decision(dc_bac, {text}))
        vl->addWidget(text_label(no_decision(), 9, QColor(WARNING()), true, col));
    vl->addWidget(break_box(b.value(QStringLiteral("diem_gay")), col));
    QStringList qs;
    for (const auto& v : b.value(QStringLiteral("cau_hoi_mo")).toArray())
        if (const QString s = lkview::text_opt(v); !s.isEmpty())
            qs << s;
    if (!qs.isEmpty()) {
        vl->addWidget(text_label(lk_tr("CÂU HỎI MỞ"), 9, QColor(TEXT_SECONDARY()), true, col));
        for (const QString& q : std::as_const(qs))
            vl->addWidget(text_label(QStringLiteral("? ") + q, 10, QColor(TEXT_SECONDARY()), false, col));
    }
    vl->addStretch(1);
    return col;
}

QWidget* zone_col(const QJsonValue& zv, QWidget* parent) {
    using namespace ui::colors;
    QFrame* col = make_col(parent);
    auto* vl = static_cast<QVBoxLayout*>(col->layout());
    const QJsonObject z = zv.toObject();
    const double lo = num_or_nan(z.value(QStringLiteral("lo")));
    const double hi = num_or_nan(z.value(QStringLiteral("hi")));
    const double vwap = num_or_nan(z.value(QStringLiteral("vwap")));
    const double nay = num_or_nan(z.value(QStringLiteral("nay")));
    const QString bac = str_of(z, "bac");
    const QString logic = str_of(z, "logic");
    vl->addLayout(col_head(lk_tr("THƯỚC VÙNG GIÁ"), bac, logic, col));
    const bool has_zone = std::isfinite(vwap) || (std::isfinite(lo) && std::isfinite(hi));
    if (!has_zone) { // V4.3: null → ô [CẦN DATA]
        auto* f = new QFrame(col);
        f->setObjectName(QStringLiteral("lkStoryNoZone"));
        auto* fl = new QVBoxLayout(f);
        fl->setContentsMargins(10, 10, 10, 10);
        fl->addWidget(text_label(lk_tr("[CẦN DATA] vùng giá — chưa có cửa sổ/giá trong nguồn"), 11, QColor(WARNING()),
                                 true, f));
        vl->addWidget(f);
        vl->addStretch(1);
        return col;
    }
    const QString nhan = str_of(z, "nhan");
    vl->addWidget(text_label(nhan.isEmpty() ? lk_tr("Vùng giá") : nhan, 11, QColor(AMBER()), true, col));
    auto* g = new PriceGauge(lo, hi, vwap, nay, col);
    QStringList parts;
    if (std::isfinite(lo) && std::isfinite(hi))
        parts << lk_tr("Vùng %1 – %2").arg(fmt_price(std::min(lo, hi)), fmt_price(std::max(lo, hi)));
    if (std::isfinite(vwap))
        parts << lk_tr("VWAP %1").arg(fmt_price(vwap));
    if (std::isfinite(nay))
        parts << lk_tr("Giá nay %1").arg(fmt_price(nay));
    g->setToolTip(tip_html({parts.join(QStringLiteral(" · ")), logic}, nhan));
    vl->addWidget(g);
    QString line = std::isfinite(nay) ? lk_tr("nay %1").arg(fmt_price(nay)) : lk_tr("giá nay —");
    const double lech = num_or_nan(z.value(QStringLiteral("lech_pct")));
    if (std::isfinite(lech))
        line += lk_tr(" · %1 so vùng gom").arg(fmt_pct(lech));
    if (!bac.isEmpty())
        line += QStringLiteral(" (%1)").arg(bac);
    vl->addWidget(text_label(line, 11, QColor(TEXT_PRIMARY()), true, col));
    if (!logic.isEmpty())
        vl->addWidget(text_label(logic, 10, QColor(TEXT_TERTIARY()), false, col));
    if (needs_no_decision(bac, {logic, nhan}))
        vl->addWidget(text_label(no_decision(), 9, QColor(WARNING()), true, col));
    vl->addStretch(1);
    return col;
}

QWidget* story_header(const QJsonObject& b, const QString& link, QWidget* parent, const lkview::TickerFn& on_ticker) {
    using namespace ui::colors;
    auto* w = new QWidget(parent);
    auto* vl = new QVBoxLayout(w);
    vl->setContentsMargins(0, 0, 0, 0);
    vl->setSpacing(3);
    auto* hl = new QHBoxLayout;
    hl->setSpacing(8);
    const QString ma = str_of(b, "ma");
    if (!ma.isEmpty()) {
        const QColor a(AMBER());
        auto* badge = text_label(ma, 12, a, true, w);
        badge->setWordWrap(false);
        badge->setStyleSheet(QStringLiteral("QLabel { color:%1; background:%2; border:1px solid %1; font-size:12px;"
                                            " font-weight:700; padding:1px 7px; }")
                                 .arg(a.name(), lkview::rgba(a, 30)));
        hl->addWidget(badge, 0, Qt::AlignTop);
    }
    const QString tieu_de = str_of(b, "tieu_de");
    hl->addWidget(text_label(tieu_de.isEmpty() ? lkview::dash() : tieu_de, 13, QColor(TEXT_PRIMARY()), true, w), 1);
    if (!link.isEmpty()) {
        auto* btn = new QPushButton(lk_tr("Mở FFT × Giá ›"), w);
        btn->setFlat(true);
        btn->setCursor(Qt::PointingHandCursor);
        btn->setFocusPolicy(Qt::NoFocus);
        btn->setToolTip(lk_tr("Mở chuỗi FFT × Giá của %1").arg(link));
        const QColor c(CYAN());
        btn->setStyleSheet(QStringLiteral("QPushButton { color:%1; background:transparent; border:1px solid %2;"
                                          " font-size:10px; font-weight:600; padding:2px 8px; }"
                                          "QPushButton:hover { background:%3; }")
                               .arg(c.name(), lkview::rgba(c, 110), lkview::rgba(c, 40)));
        QObject::connect(btn, &QPushButton::clicked, btn, [on_ticker, link]() {
            if (on_ticker)
                on_ticker(link);
        });
        hl->addWidget(btn, 0, Qt::AlignTop);
    }
    vl->addLayout(hl);
    const QString sub = str_of(b, "sub");
    if (!sub.isEmpty())
        vl->addWidget(text_label(sub, 11, QColor(TEXT_SECONDARY()), false, w));
    for (const auto& v : b.value(QStringLiteral("canh_bao")).toArray())
        if (const QString s = lkview::text_opt(v); !s.isEmpty())
            vl->addWidget(text_label(QStringLiteral("⚠ ") + s, 10, QColor(WARNING()), false, w));
    return w;
}

/// DELTA V5.1 — "sections": mục đầu ("Bức tranh tổng thể") trải hết bề ngang, chữ lớn hơn một bậc; các mục sau
/// xếp lưới 2 cột. Mỗi mục: tiêu đề nhỏ + chip bậc (tooltip = nguồn) + đoạn chữ. Không có mục hợp lệ → nullptr.
QWidget* sections_box(const QJsonArray& secs, QWidget* parent) {
    using namespace ui::colors;
    QList<QJsonObject> ok;
    for (const auto& v : secs)
        if (const QJsonObject o = v.toObject(); !str_of(o, "title").isEmpty() && !str_of(o, "text").isEmpty())
            ok << o;
    if (ok.isEmpty())
        return nullptr;
    auto* w = new QWidget(parent);
    auto* gl = new QGridLayout(w);
    gl->setContentsMargins(0, 0, 0, 0);
    gl->setHorizontalSpacing(kColGap);
    gl->setVerticalSpacing(6);
    for (int i = 0; i < ok.size(); ++i) {
        const QJsonObject& o = ok.at(i);
        const bool dau = i == 0;
        auto* f = new QFrame(w);
        f->setObjectName(QStringLiteral("lkStorySec"));
        auto* fl = new QVBoxLayout(f);
        fl->setContentsMargins(9, 6, 9, 7);
        fl->setSpacing(3);
        const QString bac = str_of(o, "bac"), text = str_of(o, "text");
        auto* head = static_cast<QHBoxLayout*>(col_head(str_of(o, "title").toUpper(), bac, str_of(o, "tip"), f));
        if (dau) // tiêu đề mục đầu: amber, lớn hơn một bậc
            if (auto* t = qobject_cast<QLabel*>(head->itemAt(0)->widget()))
                t->setStyleSheet(QStringLiteral("QLabel { color:%1; font-size:10px; font-weight:700; background:transparent; }")
                                     .arg(QColor(AMBER()).name()));
        fl->addLayout(head);
        fl->addWidget(text_label(text, dau ? 12 : 11, QColor(TEXT_PRIMARY()), false, f));
        if (needs_no_decision(bac, {text}))
            fl->addWidget(text_label(no_decision(), 9, QColor(WARNING()), true, f));
        if (dau)
            gl->addWidget(f, 0, 0, 1, 2);
        else
            gl->addWidget(f, 1 + (i - 1) / 2, (i - 1) % 2);
    }
    gl->setColumnStretch(0, 1);
    gl->setColumnStretch(1, 1);
    return w;
}

} // namespace lkstory

namespace lkview {

QWidget* make_story(const QJsonObject& b, QWidget* parent, const TickerFn& on_ticker) {
    using namespace ui::colors;
    const QString link = lkstory::str_of(b, "link");
    const QJsonArray actors = b.value(QStringLiteral("chu_the")).toArray();
    if (lkstory::str_of(b, "tieu_de").isEmpty() && lkstory::str_of(b, "ma").isEmpty() && actors.isEmpty() &&
        !b.value(QStringLiteral("dong_co")).isObject())
        return nullptr;
    auto* card = new lkstory::LinkFrame(link, on_ticker, parent);
    card->setObjectName(QStringLiteral("lkStory"));
    card->setAttribute(Qt::WA_Hover, true);
    card->setStyleSheet(
        QStringLiteral("QFrame#lkStory { background:%1; border:1px solid %2; border-left:3px solid %3; }"
                       "QFrame#lkStory:hover { border:1px solid %4; border-left:3px solid %3; }"
                       "QFrame#lkStoryCol { background:%5; border:1px solid %2; }"
                       "QFrame#lkStorySec { background:%5; border:1px solid %2; }"
                       "QFrame#lkStoryNoZone { background:transparent; border:1px dashed %6; }")
            .arg(BG_SURFACE(), BORDER_DIM(), AMBER(), link.isEmpty() ? BORDER_DIM() : BORDER_BRIGHT(), BG_RAISED(),
                 BORDER_MED()));
    auto* vl = new QVBoxLayout(card);
    vl->setContentsMargins(12, 9, 12, 11);
    vl->setSpacing(8);
    vl->addWidget(lkstory::story_header(b, link, card, on_ticker));
    if (QWidget* secs = lkstory::sections_box(b.value(QStringLiteral("sections")).toArray(), card))
        vl->addWidget(secs);
    auto* cols = new QWidget(card);
    cols->setObjectName(QStringLiteral("lkStoryCols"));
    auto* sl = new lkstory::StoryLayout(cols);
    sl->addWidget(lkstory::actors_col(actors, cols));
    sl->addWidget(lkstory::motive_col(b, cols));
    sl->addWidget(lkstory::zone_col(b.value(QStringLiteral("vung_gia")), cols));
    vl->addWidget(cols);
    card->wire_clicks();
    return card;
}

} // namespace lkview

} // namespace fincept::screens::langkinh
