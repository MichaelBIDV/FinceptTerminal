// src/screens/langkinh/LkSodo.cpp
// Lăng Kính FFT — block "sodo" (lưới sơ đồ hình lý tưởng của mẫu hình). Xem LkSodo.h.
// QPainter dùng thẳng QFont của LkTheme; nhãn QLabel đi qua lk_label (phông qua QSS riêng của nhãn).
#include "screens/langkinh/LkSodo.h"

#include "screens/langkinh/LkChips.h"
#include "screens/langkinh/LkStory.h"
#include "screens/langkinh/LkTheme.h"
#include "screens/langkinh/LkWidgets.h"

#include <QFontMetricsF>
#include <QFrame>
#include <QHBoxLayout>
#include <QJsonArray>
#include <QLabel>
#include <QPaintEvent>
#include <QPainter>
#include <QPainterPath>
#include <QPen>
#include <QPointF>
#include <QRectF>
#include <QSizePolicy>
#include <QStringList>
#include <QTextDocumentFragment>
#include <QVBoxLayout>
#include <QVector>

#include <algorithm>
#include <cmath>
#include <utility>

namespace fincept::screens::langkinh {

// Helper tự do: namespace có tên riêng (quy ước của module, không dùng namespace ẩn danh).
namespace lksodo {

using namespace lkview;

constexpr int kCellMinW = 240;  // cột lưới ≥ 240px (khung vẽ ≈220 + đệm thẻ)
constexpr int kGridGap = 12;
constexpr double kAspect = 130.0 / 220.0; // khung vẽ ≈220×130
constexpr int kCanvasMinH = 120;
constexpr int kCanvasMaxH = 170;
constexpr double kPadX = 10.0;  // lề khung vẽ trong canvas (chỗ cho nhãn sát mép)
constexpr double kPadY = 18.0;
constexpr double kDotR = 3.5;
constexpr double kLineKeepOut = 6.0; // dải cấm chữ quanh đường hình lý tưởng (nét 2px + 2px mỗi bên)
constexpr int kCellCapW = 280;       // trong "row": một sơ đồ chỉ cần ≈ bề rộng này, phần còn lại nhường mục bên cạnh

struct Box {
    double x0 = 0.0, x1 = 0.0, y0 = 0.0, y1 = 0.0;
    QString text;
};

struct Label {
    int i = -1;
    QString text;
};

struct Item {
    QString id;
    QString ten;
    QString trang_thai;
    QVector<QPointF> diem; // chuẩn hoá 0..1, y dưới → trên
    QVector<Label> nhan;
    QVector<Box> hop;
    QString ghi_chu;
    int n_bad = 0; // số điểm hỏng bị bỏ
};

/// Trạng thái → chữ pill + vai màu (hợp đồng lk_mauhinh/1).
std::pair<QString, LkRole> status_of(const QString& tt) {
    const QString s = tt.trimmed().toLower();
    if (s == QLatin1String("dang_hinh_thanh"))
        return {lk_tr("đang hình thành"), LkRole::Amber};
    if (s == QLatin1String("xac_nhan"))
        return {lk_tr("xác nhận"), LkRole::Up};
    if (s == QLatin1String("gay"))
        return {lk_tr("gãy"), LkRole::Down};
    if (s == QLatin1String("het_hieu_luc"))
        return {lk_tr("hết hiệu lực"), LkRole::Grey};
    return {tt.trimmed(), LkRole::Grey};
}

/// html-lite → chữ trần (tooltip, nhãn tự vẽ).
QString plain(const QString& s) {
    return QTextDocumentFragment::fromHtml(lk_inline_html(s)).toPlainText().simplified();
}

double clamp01(double v) {
    return std::clamp(v, 0.0, 1.0);
}

/// Tách chữ làm hai dòng tại dấu cách cho dòng dài nhất ngắn nhất; không có dấu cách → rỗng.
QString two_lines(const QString& s, const QFontMetricsF& fm) {
    int best = -1;
    double best_w = 0.0;
    for (int i = s.indexOf(QLatin1Char(' ')); i > 0; i = s.indexOf(QLatin1Char(' '), i + 1)) {
        const double w = std::max(fm.horizontalAdvance(s.left(i)), fm.horizontalAdvance(s.mid(i + 1)));
        if (best < 0 || w < best_w) {
            best = i;
            best_w = w;
        }
    }
    return best < 0 ? QString() : s.left(best) + QLatin1Char('\n') + s.mid(best + 1);
}

/// Bề rộng dòng dài nhất của chữ nhiều dòng ("\n").
double lines_w(const QString& s, const QFontMetricsF& fm) {
    double w = 0.0;
    for (const QString& ln : s.split(QLatin1Char('\n')))
        w = std::max(w, fm.horizontalAdvance(ln));
    return w;
}

Item read_item(const QJsonObject& o) {
    Item it;
    it.id = text_opt(o.value(QStringLiteral("id")));
    it.ten = text_opt(o.value(QStringLiteral("ten")));
    it.trang_thai = o.value(QStringLiteral("trang_thai")).toString().trimmed();
    it.ghi_chu = text_opt(o.value(QStringLiteral("ghi_chu")));
    for (const auto& pv : o.value(QStringLiteral("diem")).toArray()) {
        const QJsonArray a = pv.toArray();
        double x = 0.0;
        double y = 0.0;
        if (a.size() >= 2 && num_of(a.at(0), &x) && num_of(a.at(1), &y))
            it.diem << QPointF(clamp01(x), clamp01(y));
        else
            ++it.n_bad;
    }
    for (const auto& lv : o.value(QStringLiteral("nhan")).toArray()) {
        const QJsonObject lo = lv.toObject();
        double i = 0.0;
        Label l;
        l.text = text_opt(lo.value(QStringLiteral("text")));
        if (num_of(lo.value(QStringLiteral("i")), &i))
            l.i = static_cast<int>(std::lround(i));
        if (l.i >= 0 && l.i < it.diem.size())
            it.nhan << l;
    }
    for (const auto& hv : o.value(QStringLiteral("hop")).toArray()) {
        const QJsonObject ho = hv.toObject();
        Box b;
        if (!num_of(ho.value(QStringLiteral("x0")), &b.x0) || !num_of(ho.value(QStringLiteral("x1")), &b.x1) ||
            !num_of(ho.value(QStringLiteral("y0")), &b.y0) || !num_of(ho.value(QStringLiteral("y1")), &b.y1))
            continue;
        b.text = text_opt(ho.value(QStringLiteral("text")));
        it.hop << b;
    }
    return it;
}

/// Khung vẽ hình lý tưởng.
class Canvas : public QWidget {
  public:
    Canvas(Item it, QWidget* parent) : QWidget(parent), it_(std::move(it)) {
        QSizePolicy sp(QSizePolicy::Expanding, QSizePolicy::Preferred);
        sp.setHeightForWidth(true);
        setSizePolicy(sp);
        lk_transparent(this);
        QStringList lines;
        for (const Label& l : std::as_const(it_.nhan))
            if (!l.text.isEmpty())
                lines << plain(l.text);
        for (const Box& b : std::as_const(it_.hop))
            if (!b.text.isEmpty())
                lines << lk_tr("Hộp: %1").arg(plain(b.text));
        lines << lk_tr("Hình lý tưởng để đối chiếu — không phải chuỗi giá thật");
        setToolTip(lkstory::tip_html(lines, plain(it_.ten)));
        setAccessibleName(plain(it_.ten));
        setAccessibleDescription(lines.join(QStringLiteral("; ")));
    }

    bool hasHeightForWidth() const override { return true; }
    int heightForWidth(int w) const override {
        return std::clamp(static_cast<int>(std::lround(w * kAspect)), kCanvasMinH, kCanvasMaxH);
    }
    QSize sizeHint() const override { return {220, heightForWidth(220)}; }
    QSize minimumSizeHint() const override { return {160, kCanvasMinH}; }

  protected:
    void paintEvent(QPaintEvent*) override;

  private:
    QRectF plot() const {
        return QRectF(kPadX, kPadY, std::max(1.0, width() - 2.0 * kPadX), std::max(1.0, height() - 2.0 * kPadY));
    }
    QPointF map(const QRectF& pr, const QPointF& n) const {
        return {pr.left() + n.x() * pr.width(), pr.bottom() - n.y() * pr.height()};
    }
    /// Nhãn điểm i đặt phía trên (true) khi là đỉnh cục bộ, phía dưới khi là đáy cục bộ.
    bool above(int i) const {
        const double y = it_.diem.at(i).y();
        double lo = y;
        double hi = y;
        if (i > 0) {
            lo = std::min(lo, it_.diem.at(i - 1).y());
            hi = std::max(hi, it_.diem.at(i - 1).y());
        }
        if (i + 1 < it_.diem.size()) {
            lo = std::min(lo, it_.diem.at(i + 1).y());
            hi = std::max(hi, it_.diem.at(i + 1).y());
        }
        if (y >= hi)
            return true;
        if (y <= lo)
            return false;
        return y >= 0.5;
    }

    Item it_;
};

void Canvas::paintEvent(QPaintEvent*) {
    if (it_.diem.size() < 2 || width() <= 0)
        return;
    QPainter p(this);
    p.setRenderHint(QPainter::Antialiasing, true);
    p.setRenderHint(QPainter::TextAntialiasing, true);
    const QRectF pr = plot();
    const QColor surface = lk_col(LkRole::Surface);
    const bool faded = it_.trang_thai.trimmed().toLower() == QLatin1String("het_hieu_luc");
    QColor line = lk_col(LkRole::Amber);
    if (faded)
        line.setAlphaF(0.45f);

    // Nhãn chờ đặt: mỗi nhãn có danh sách vị trí thử (hộp chữ + chữ, "\n" = hai dòng) theo thứ tự. Chữ KHÔNG bao
    // giờ bị cắt "…": vị trí chồng chấm, nhãn đã đặt hoặc đường hình lý tưởng (hay lòi khỏi canvas) → thử vị trí
    // sau; hết → bỏ chữ, tooltip của sơ đồ vẫn đủ.
    struct Try {
        QRectF r;
        QString text;
    };
    struct Pending {
        QFont font;
        QColor color;
        QVector<Try> tries;
    };
    QVector<Pending> pend;
    const QFont fb = lk_font_mono(9, 500);
    const QFontMetricsF mb(fb, this);
    const QFont fl = lk_font_mono(10, 500);
    const QFontMetricsF ml(fl, this);
    const auto fit = [this](QRectF r) { // kẹp hộp chữ trong canvas
        r.moveLeft(std::clamp(r.left(), 1.0, std::max(1.0, width() - 1.0 - r.width())));
        r.moveTop(std::clamp(r.top(), 0.0, std::max(0.0, height() - r.height())));
        return r;
    };

    // 1) Hộp / vạch đứt (hình), nhãn đưa vào hàng chờ.
    QPen dpen(lk_col(LkRole::Line2), 1.0);
    dpen.setDashPattern({3.0, 3.0});
    QColor box_fill = lk_col(LkRole::Grey);
    box_fill.setAlphaF(0.07f);
    QVector<Pending> box_labels;
    for (const Box& b : std::as_const(it_.hop)) {
        const QPointF a = map(pr, QPointF(clamp01(std::min(b.x0, b.x1)), clamp01(std::max(b.y0, b.y1))));
        const QPointF c = map(pr, QPointF(clamp01(std::max(b.x0, b.x1)), clamp01(std::min(b.y0, b.y1))));
        const QRectF r = QRectF(a, c).normalized();
        const QString s = plain(b.text);
        const double tw = mb.horizontalAdvance(s);
        const double th = mb.height();
        p.setPen(dpen);
        Pending lab{fb, lk_col(LkRole::Muted), {}};
        const auto add = [&lab, &fit, &s](const QRectF& rr) { lab.tries << Try{fit(rr), s}; };
        if (r.height() < 2.0 && r.width() >= 2.0) { // y0 = y1 → vạch ngang đứt (mức gãy, viền hồ …); nhãn trên/dưới
            const double y = std::round(r.center().y()) + 0.5;
            p.drawLine(QPointF(r.left(), y), QPointF(r.right(), y));
            add(QRectF(r.left() + 2.0, y - 2.0 - th, tw, th));
            add(QRectF(r.left() + 2.0, y + 2.0, tw, th));
            add(QRectF(r.right() - 2.0 - tw, y - 2.0 - th, tw, th));
            add(QRectF(r.right() - 2.0 - tw, y + 2.0, tw, th));
        } else if (r.width() < 2.0 && r.height() >= 2.0) { // x0 = x1 → vạch dọc đứt (phiên mốc)
            const double x = std::round(r.center().x()) + 0.5;
            p.drawLine(QPointF(x, r.top()), QPointF(x, r.bottom()));
            add(QRectF(x + 3.0, r.top(), tw, th));
            add(QRectF(x - 3.0 - tw, r.top(), tw, th));
            add(QRectF(x + 3.0, r.bottom() - th, tw, th));
            add(QRectF(x - 3.0 - tw, r.bottom() - th, tw, th));
        } else if (r.width() >= 2.0 && r.height() >= 2.0) {
            p.setBrush(box_fill);
            p.drawRect(r.adjusted(0.5, 0.5, -0.5, -0.5));
            p.setBrush(Qt::NoBrush);
            // Trong hộp chỉ khi chữ vừa trọn (một dòng, rồi hai dòng); không thì ra ngoài hộp: trên, dưới, phải, trái.
            const double in_w = r.width() - 6.0;
            if (tw <= in_w && th + 4.0 <= r.height()) {
                lab.tries << Try{QRectF(r.left() + 3.0, r.top() + 2.0, tw, th), s}
                          << Try{QRectF(r.left() + 3.0, r.bottom() - 2.0 - th, tw, th), s};
            }
            const QString s2 = two_lines(s, mb);
            const double w2 = s2.isEmpty() ? 0.0 : lines_w(s2, mb);
            if (!s2.isEmpty() && w2 <= in_w && 2.0 * th + 4.0 <= r.height())
                lab.tries << Try{QRectF(r.left() + 3.0, r.top() + 2.0, w2, 2.0 * th), s2};
            add(QRectF(r.left(), r.top() - 2.0 - th, tw, th));
            add(QRectF(r.right() - tw, r.top() - 2.0 - th, tw, th));
            add(QRectF(r.left(), r.bottom() + 2.0, tw, th));
            add(QRectF(r.right() - tw, r.bottom() + 2.0, tw, th));
            add(QRectF(r.right() + 3.0, r.center().y() - th / 2.0, tw, th));
            add(QRectF(r.left() - 3.0 - tw, r.center().y() - th / 2.0, tw, th));
        }
        if (!s.isEmpty() && !lab.tries.isEmpty())
            box_labels << lab;
    }

    // 2) Đường hình lý tưởng + vùng cấm chữ quanh nó (nét 2px nới thành dải 6px).
    QPainterPath path;
    path.moveTo(map(pr, it_.diem.first()));
    for (int i = 1; i < it_.diem.size(); ++i)
        path.lineTo(map(pr, it_.diem.at(i)));
    QPen pen(line, 2.0);
    pen.setCapStyle(Qt::RoundCap);
    pen.setJoinStyle(Qt::RoundJoin);
    p.setPen(pen);
    p.setBrush(Qt::NoBrush);
    p.drawPath(path);
    QPainterPathStroker stroker;
    stroker.setWidth(kLineKeepOut);
    stroker.setCapStyle(Qt::RoundCap);
    stroker.setJoinStyle(Qt::RoundJoin);
    const QPainterPath line_zone = stroker.createStroke(path);

    // 3) Chấm neo; nhãn neo đặt TRƯỚC nhãn hộp: trên đỉnh / dưới đáy (canh giữa, rồi lệch phải/trái), phía kia,
    // ngang chấm (phải, trái), rồi xa thêm một nấc.
    QVector<QRectF> dots;
    for (const Label& l : std::as_const(it_.nhan)) {
        const QPointF c = map(pr, it_.diem.at(l.i));
        p.setPen(QPen(surface, 1.5));
        p.setBrush(line);
        p.drawEllipse(c, kDotR, kDotR);
        dots << QRectF(c.x() - kDotR, c.y() - kDotR, 2.0 * kDotR, 2.0 * kDotR);
        const QString s = plain(l.text);
        if (s.isEmpty())
            continue;
        const double w = ml.horizontalAdvance(s);
        const double h = ml.height();
        const double g = kDotR + 3.0;
        const double sh = std::max(0.0, w / 2.0 - 4.0); // lệch: mép chữ cách tâm chấm 4px
        const QRectF up(c.x() - w / 2.0, c.y() - g - h, w, h);
        const QRectF dn(c.x() - w / 2.0, c.y() + g, w, h);
        const QRectF first = above(l.i) ? up : dn;
        const QRectF second = above(l.i) ? dn : up;
        const QRectF cand[] = {first,
                               first.translated(sh, 0.0),
                               first.translated(-sh, 0.0),
                               second,
                               second.translated(sh, 0.0),
                               second.translated(-sh, 0.0),
                               QRectF(c.x() + g + 1.0, c.y() - h / 2.0, w, h),
                               QRectF(c.x() - g - 1.0 - w, c.y() - h / 2.0, w, h),
                               up.translated(0.0, -(h + 2.0)),
                               dn.translated(0.0, h + 2.0)};
        Pending lab{fl, lk_col(LkRole::Ink2), {}};
        for (const QRectF& rr : cand)
            lab.tries << Try{fit(rr), s};
        pend << lab;
    }
    pend << box_labels;

    // 4) Đặt chữ. Nền surface mờ chỉ để chữ nổi trên vạch đứt của hộp — chữ không còn đè lên đường hình.
    QVector<QRectF> taken = dots;
    QColor halo = surface;
    halo.setAlphaF(0.82f);
    const QRectF canvas = QRectF(rect()).adjusted(0.5, 0.0, -0.5, 0.0);
    for (const Pending& lab : std::as_const(pend)) {
        const QFontMetricsF fm(lab.font, this);
        for (const Try& t : lab.tries) {
            const QRectF& r = t.r;
            if (!canvas.contains(r) || line_zone.intersects(r) ||
                std::any_of(taken.cbegin(), taken.cend(), [&r](const QRectF& q) { return q.intersects(r); }))
                continue;
            taken << r;
            p.fillRect(r.adjusted(-1.5, 0.0, 1.5, 0.0), halo);
            p.setFont(lab.font);
            p.setPen(lab.color);
            const QStringList rows = t.text.split(QLatin1Char('\n'));
            for (int k = 0; k < rows.size(); ++k)
                p.drawText(QPointF(r.left(), std::round(r.top() + k * fm.height() + fm.ascent())), rows.at(k));
            break;
        }
    }
}

QFrame* cell_frame(QWidget* parent) {
    auto* f = new QFrame(parent);
    f->setObjectName(QStringLiteral("lksdCell"));
    f->setStyleSheet(QStringLiteral("QFrame#lksdCell { background:%1; border:1px solid %2; border-radius:10px; }"
                                    "QFrame#lksdCell QWidget { background:transparent; border:none; }")
                         .arg(lk_qss(lk_col(LkRole::Surface)), lk_qss(lk_col(LkRole::Line))));
    return f;
}

QWidget* make_cell(const Item& it, QWidget* parent) {
    QFrame* f = cell_frame(parent);
    auto* vl = new QVBoxLayout(f);
    vl->setContentsMargins(12, 11, 12, 12);
    vl->setSpacing(6);
    const QColor ink = lk_col(LkRole::Ink);

    auto* head = new QHBoxLayout;
    head->setContentsMargins(0, 0, 0, 0);
    head->setSpacing(8);
    const QString ten = it.ten.isEmpty() ? (it.id.isEmpty() ? dash() : it.id) : it.ten;
    head->addWidget(lk_label(lk_inline_html(ten, ink), lk_font_sans(13, 600), ink, f, Qt::RichText), 1);
    if (!it.trang_thai.isEmpty()) {
        const auto [txt, role] = status_of(it.trang_thai);
        head->addWidget(new LkPill(txt, role, f, 10), 0, Qt::AlignTop);
    }
    vl->addLayout(head);

    const QFont gap_font = lk_font_mono(11, 600);
    if (it.diem.size() >= 2) {
        vl->addWidget(new Canvas(it, f));
        if (it.n_bad > 0)
            vl->addWidget(lk_label(lk_tr("[CẦN DATA] — %1 điểm sơ đồ hỏng bị bỏ").arg(it.n_bad), gap_font,
                                   lk_col(LkRole::Down), f));
    } else {
        vl->addWidget(lk_label(lk_tr("[CẦN DATA] — sơ đồ cần ít nhất 2 điểm hợp lệ"), gap_font, lk_col(LkRole::Down),
                               f));
    }
    if (!it.ghi_chu.isEmpty())
        vl->addWidget(lk_label(lk_inline_html(it.ghi_chu, lk_col(LkRole::Ink2)), lk_font_sans(12),
                               lk_col(LkRole::Muted), f, Qt::RichText));
    vl->addStretch(1);
    return f;
}

} // namespace lksodo

namespace lkview {

QWidget* make_sodo(const QJsonObject& b, QWidget* parent) {
    QList<lksodo::Item> items;
    for (const auto& v : b.value(QStringLiteral("items")).toArray()) {
        if (!v.isObject())
            continue;
        lksodo::Item it = lksodo::read_item(v.toObject());
        if (it.ten.isEmpty() && it.diem.isEmpty())
            continue;
        items << it;
    }
    if (items.isEmpty())
        return nullptr;
    auto* w = new QWidget(parent);
    lk_transparent(w); // hộp lưới bên trong là QWidget trần
    auto* vl = new QVBoxLayout(w);
    vl->setContentsMargins(0, 0, 0, 0);
    vl->setSpacing(10);
    lk_add_head(vl, b, w);
    // Trong "row": bề rộng hữu ích tối đa = số sơ đồ × ≈280px — một sơ đồ lẻ không giữ nửa hàng trống.
    const int n = static_cast<int>(items.size());
    w->setProperty(kRowMaxWProp, n * lksodo::kCellCapW + (n - 1) * lksodo::kGridGap);
    auto* box = new QWidget(w);
    auto* grid = new LkAutoGridLayout(box, lksodo::kCellMinW, 0, lksodo::kGridGap);
    grid->set_keep_tracks(true); // ít sơ đồ: giữ cỡ ≈220×130, không giãn một sơ đồ hết bề rộng trang
    for (const lksodo::Item& it : std::as_const(items))
        grid->addWidget(lksodo::make_cell(it, box));
    vl->addWidget(box);
    return w;
}

} // namespace lkview

} // namespace fincept::screens::langkinh
