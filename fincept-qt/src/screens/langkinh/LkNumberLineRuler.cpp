// src/screens/langkinh/LkNumberLineRuler.cpp
// Lăng Kính FFT — chế độ "ruler" của block numline (thước σ chung nhiều mã): đọc mục, xếp nhãn vào hàng trống,
// tooltip theo chấm. Tách khỏi LkNumberLine.cpp để mỗi tệp ≤ 800 dòng. Xem LkNumberLine.h.
#include "screens/langkinh/LkNumberLine.h"
#include "screens/langkinh/LkNumberLineDraw.h"

#include <QEvent>
#include <QFontMetricsF>
#include <QHelpEvent>
#include <QJsonArray>
#include <QPainter>
#include <QStringList>
#include <QToolTip>

#include <algorithm>
#include <cmath>
#include <numeric>
#include <utility>

namespace fincept::screens::langkinh {

namespace lknumline {

/// Ruler: hàng TRỐNG đầu tiên theo thứ tự hàng (gần trục trước); trong mỗi hàng thử canh giữa chấm, rồi lệch
/// trái/phải quanh chấm (hộp chữ luôn phủ x của chấm để đường dẫn chạm chữ). Không còn chỗ → −1 (không ép chồng).
int free_slot(const QVector<Row>& rows, double x, double w, double h, double width, QRectF* out) {
    struct Try {
        double at;
        Qt::Alignment al;
    };
    const Try tries[3] = {{x, Qt::AlignHCenter}, {x - 6.0, Qt::AlignLeft}, {x + 6.0, Qt::AlignRight}};
    for (int ri = 0; ri < rows.size(); ++ri)
        for (const Try& t : tries) {
            const QRectF r = text_rect(t.at, w, rows.at(ri).top, h, t.al, width);
            if (r.left() > x + 0.5 || r.right() < x - 0.5) // kẹp mép đẩy hộp khỏi chấm: không dùng
                continue;
            if (overlap(r, rows.at(ri)) <= 0.0) {
                *out = r;
                return ri;
            }
        }
    return -1;
}

} // namespace lknumline

namespace lkview {

void LkNumberLine::parse_ruler(const QJsonObject& b) {
    using namespace lknumline;
    mode_ = Mode::Ruler;
    height_ = kRulerH;
    pad_ = 22.0;
    a0_ = -kSpan;
    a1_ = kSpan;
    constexpr LkRole kCycle[5] = {LkRole::Blue, LkRole::Violet, LkRole::Amber, LkRole::Ink2, LkRole::Grey};
    QStringList groups; // từ đầu của nhãn (mã) → màu, cùng mã cùng màu
    int skipped = 0;
    for (const auto& v : b.value(QStringLiteral("items")).toArray()) {
        QString lab;
        QString mau;
        double z = nan_v();
        if (v.isArray()) {
            const QJsonArray a = v.toArray();
            if (!a.isEmpty())
                lab = text_opt(a.at(0));
            if (a.size() > 1)
                num_of(a.at(1), &z);
            if (a.size() > 2)
                mau = a.at(2).toString().trimmed();
        } else if (v.isObject()) {
            const QJsonObject o = v.toObject();
            lab = text_opt(o.value(QStringLiteral("lab")));
            if (lab.isEmpty())
                lab = text_opt(o.value(QStringLiteral("label")));
            num_of(o.value(QStringLiteral("z")), &z);
            mau = o.value(QStringLiteral("mau")).toString().trimmed();
        }
        if (lab.isEmpty() || !std::isfinite(z)) {
            ++skipped;
            continue;
        }
        LkRole r = lk_role(mau, LkRole::Bg); // Bg = "không có/lạ" (không bao giờ là màu chấm)
        if (r == LkRole::Bg) {
            const QString g = lab.section(QLatin1Char(' '), 0, 0);
            int gi = static_cast<int>(groups.indexOf(g));
            if (gi < 0) {
                groups << g;
                gi = static_cast<int>(groups.size()) - 1;
            }
            r = kCycle[gi % 5];
        }
        items_.append(Item{lab, z, r});
    }
    if (skipped > 0)
        missing_ << lk_tr("%1 mục thiếu nhãn hoặc z").arg(skipped);
    valid_ = !items_.isEmpty();
    if (!valid_ && skipped == 0)
        missing_ << lk_tr("chưa có mục nào trên thước σ");
    if (!valid_)
        return;

    const int n = static_cast<int>(items_.size()); // nhiều mục → thêm hàng nhãn mỗi phía, thước cao thêm
    half_rows_ = n > 14 ? 5 : (n > 8 ? 4 : 3);
    height_ = kRulerH + 36 * (half_rows_ - 3);
    tip_head_ = lk_tr("Thước σ chung");
    for (const Item& it : std::as_const(items_))
        tip_ << QStringLiteral("%1  %2").arg(it.label, fmt_sigma(it.z));
}

void LkNumberLine::paint_ruler(QPainter& p) const {
    using namespace lknumline;
    const double W = width();
    const double yb = 74.0 + 18.0 * (half_rows_ - 3); // tâm trục
    const QFont fa = ax_font();
    const QFont fl = axl_font();
    const QFontMetricsF ma(fa, this);
    const QFontMetricsF ml(fl, this);

    const double xa = std::round(x_of(-kSpan));
    const double xb = std::round(x_of(kSpan));
    paint_zones(p, QRectF(xa, yb - 8.0, xb - xa, 16.0), {-3.0, -2.0, -1.0, 1.0, 2.0, 3.0});
    for (int k = -3; k <= 3; ++k)
        vline(p, x_of(k), yb - 8.0, yb + 8.0, c_.line2);

    // Hàng nhãn xen kẽ trên/dưới, gần trục trước: A1 B1 A2 B2 … (chỉ số chẵn = trên trục).
    QVector<Row> rows(2 * half_rows_);
    for (int k = 0; k < half_rows_; ++k) {
        rows[2 * k].top = yb - 30.0 - 18.0 * k;
        rows[2 * k + 1].top = yb + 32.0 + 18.0 * k;
    }
    QVector<int> idx(items_.size());
    std::iota(idx.begin(), idx.end(), 0);
    std::stable_sort(idx.begin(), idx.end(), [this](int a, int b) { return items_.at(a).z < items_.at(b).z; });

    struct Lab {
        QRectF r;
        QString s;
        QColor c;
    };
    QVector<Lab> labs;
    hits_.clear();
    for (const int i : std::as_const(idx)) {
        const Item& it = items_.at(i);
        const double X = x_of(std::clamp(it.z, -kSpan, kSpan));
        const QString full = it.label + QLatin1Char(' ') + fmt_sigma(it.z);
        const QString shrt = it.label.section(QLatin1Char(' '), 0, 0); // chỉ mã; số σ ở tooltip của chấm
        Lab l{QRectF(), full, lk_col(it.role)};
        int ri = free_slot(rows, X, ml.horizontalAdvance(full), ml.height(), W, &l.r);
        if (ri < 0 && !shrt.isEmpty() && shrt != full) {
            l.s = shrt;
            ri = free_slot(rows, X, ml.horizontalAdvance(shrt), ml.height(), W, &l.r);
        }
        hits_.append({QPointF(std::round(X), yb), ri < 0 ? lk_tr("%1 (nhãn ẩn — chồng nhãn khác)").arg(full) : full});
        if (ri < 0) // không còn hàng trống: giữ chấm, bỏ chữ
            continue;
        rows[ri].taken << l.r;
        if (ri % 2 == 0)
            vline(p, X, l.r.bottom() + 2.0, yb - 9.0, c_.line2);
        else
            vline(p, X, yb + 9.0, l.r.top() - 2.0, c_.line2);
        labs << l;
    }
    for (int k = -3; k <= 3; ++k) { // nhãn vạch vẽ sau đường dẫn (chữ nằm trên nét mảnh)
        const QString t = sigma_tick(k);
        text_at(p, text_rect(x_of(k), ma.horizontalAdvance(t), yb + 12.0, ma.height(), Qt::AlignHCenter, W), fa, ma,
                c_.muted, t);
    }
    for (const int i : std::as_const(idx)) { // chấm vẽ sau đường dẫn, trước chữ
        const Item& it = items_.at(i);
        const int dir = it.z < -kSpan ? -1 : (it.z > kSpan ? 1 : 0);
        marker(p, QPointF(std::round(x_of(std::clamp(it.z, -kSpan, kSpan))), yb), dir, lk_col(it.role), c_.surface);
    }
    QColor halo = c_.surface; // nền chữ: đường dẫn của nhãn hàng xa không cắt ngang chữ hàng gần
    halo.setAlphaF(0.9f);
    for (const Lab& l : std::as_const(labs)) {
        p.fillRect(l.r.adjusted(-2.0, 0.0, 2.0, 0.0), halo);
        text_at(p, l.r, fl, ml, l.c, l.s);
    }
}

bool LkNumberLine::event(QEvent* e) {
    if (e->type() == QEvent::ToolTip && mode_ == Mode::Ruler && !hits_.isEmpty()) {
        const auto* he = static_cast<QHelpEvent*>(e);
        const QPointF pos = he->pos();
        QStringList near;
        for (const auto& h : std::as_const(hits_)) {
            const QPointF d = h.first - pos;
            if (d.x() * d.x() + d.y() * d.y() <= 81.0) // bán kính 9px quanh chấm
                near << h.second.toHtmlEscaped();
        }
        if (!near.isEmpty()) {
            QToolTip::showText(he->globalPos(), QStringLiteral("<qt>%1</qt>").arg(near.join(QStringLiteral("<br>"))),
                               this);
            return true;
        }
    }
    return QWidget::event(e);
}

} // namespace lkview

} // namespace fincept::screens::langkinh
