// src/screens/langkinh/LkCotMoc.cpp
// Lăng Kính FFT — block "cotmoc" (cột mốc rời kiểu holdChart của Artifact). Xem LkCotMoc.h.
// QPainter dùng thẳng QFont của LkTheme; nhãn QLabel của thẻ đi qua lk_label (phông qua QSS riêng của nhãn).
#include "screens/langkinh/LkCotMoc.h"

#include "screens/langkinh/LkChips.h"
#include "screens/langkinh/LkPage.h"
#include "screens/langkinh/LkStory.h"
#include "screens/langkinh/LkTheme.h"
#include "screens/langkinh/LkWidgets.h"

#include <QEvent>
#include <QFontMetricsF>
#include <QFrame>
#include <QHelpEvent>
#include <QJsonArray>
#include <QLabel>
#include <QPaintEvent>
#include <QPainter>
#include <QPen>
#include <QSizePolicy>
#include <QStringList>
#include <QToolTip>
#include <QVBoxLayout>
#include <QVector>

#include <algorithm>
#include <cmath>
#include <limits>
#include <utility>

namespace fincept::screens::langkinh {

// Helper tự do: namespace có tên riêng (quy ước của module, không dùng namespace ẩn danh).
namespace lkcotmoc {

using namespace lkview;

constexpr int kH = 214;          // Artifact holdChart viewBox 380×214
constexpr double kPadX = 12.0;   // m.l = m.r = 12
constexpr double kTop = 26.0;    // m.t — chỗ cho số trên cột
constexpr double kBottom = 52.0; // m.b — kỳ · nguồn · Δ dưới trục
constexpr double kBarMax = 46.0; // bw = min(46, khe·0,46)
constexpr double kBarFrac = 0.46;
constexpr double kHollowA = 0.35; // cột CF / số tròn / nội suy
constexpr double kSolidA = 0.85;  // cột quan sát (opacity .85)
constexpr double kMissingH = 0.28; // khung "CẦN DATA": 28% chiều cao vùng vẽ

struct Moc {
    QString ky;
    double v = std::numeric_limits<double>::quiet_NaN();
    QString b;
    QString kieu;
    bool cf = false;
    bool so_tron = false;
};

struct Cap {
    int tu = -1;
    int den = -1;
    QString text;
};

/// Lý do cột không phải quan sát sạch ("" = quan sát sạch).
QString why_of(const Moc& m) {
    if (m.cf)
        return lk_tr("CF");
    if (m.so_tron || m.kieu == QLatin1String("so_tron"))
        return lk_tr("số tròn");
    if (m.kieu == QLatin1String("noi_suy"))
        return lk_tr("nội suy");
    if (m.kieu == QLatin1String("chep"))
        return lk_tr("chép");
    return {};
}

bool hollow(const Moc& m) {
    return !why_of(m).isEmpty();
}

/// Hệ quả của mốc không sạch (luật §0.3): CF/chép cấm Δ; số tròn Δ chỉ ở mức hướng; nội suy chỉ để vẽ.
QString note_of(const Moc& m) {
    if (m.cf || m.kieu == QLatin1String("chep"))
        return lk_tr("Mốc chép (CF) — cấm tính Δ, không xác nhận pattern");
    if (m.so_tron || m.kieu == QLatin1String("so_tron"))
        return lk_tr("Mốc số tròn — Δ chỉ ở mức hướng, không xác nhận pattern");
    if (m.kieu == QLatin1String("noi_suy"))
        return lk_tr("Mốc nội suy — chỉ để vẽ, không phải quan sát");
    return {};
}

/// Dòng nguồn dưới cột: bậc chuẩn (hoặc nguyên văn) + lý do rỗng.
QString src_of(const Moc& m) {
    QString t = lk_tier_key(m.b);
    if (t.isEmpty())
        t = m.b.trimmed();
    const QString w = why_of(m);
    if (w.isEmpty())
        return t;
    return t.isEmpty() ? w : t + QStringLiteral(" · ") + w;
}

/// Số kiểu Việt, bỏ số 0 thừa: 73.355 · 1,5 · 12.
QString fmt_v(double v) {
    const int dec = std::abs(v) >= 100.0 ? 0 : 2;
    QString s = vn_num(v, dec);
    if (dec > 0 && s.contains(QLatin1Char(','))) {
        while (s.endsWith(QLatin1Char('0')))
            s.chop(1);
        if (s.endsWith(QLatin1Char(',')))
            s.chop(1);
    }
    return s;
}

/// Đoạn đầu của dòng Δ (trước " · " đầu tiên): "+136,6%".
QString short_of(const QString& t) {
    const int k = static_cast<int>(t.indexOf(QStringLiteral(" · ")));
    return (k > 0 ? t.left(k) : t).trimmed();
}

QFont ax_font() { // .ax: mono 10
    return lk_font_mono(10, 400);
}
QFont axl_font() { // .axl đậm: mono 10,5 → 11 / 600
    return lk_font_mono(11, 600);
}

/// Hình cột mốc tự vẽ.
class Chart : public QWidget {
  public:
    Chart(QVector<Moc> moc, QVector<Cap> cap, QWidget* parent)
        : QWidget(parent), m_(std::move(moc)), c_(std::move(cap)) {
        setSizePolicy(QSizePolicy::Expanding, QSizePolicy::Fixed);
        setFixedHeight(kH);
        lk_transparent(this);
        setMouseTracking(true);
        QStringList acc;
        for (const Moc& m : std::as_const(m_))
            acc << QStringLiteral("%1 %2").arg(m.ky, std::isfinite(m.v) ? fmt_v(m.v) : lk_tr("CẦN DATA"));
        setAccessibleName(lk_tr("Cột mốc"));
        setAccessibleDescription(acc.join(QStringLiteral("; ")));
    }

    QSize sizeHint() const override { return {420, kH}; }
    QSize minimumSizeHint() const override { return {160, kH}; }

  protected:
    void paintEvent(QPaintEvent*) override;
    bool event(QEvent* e) override;

  private:
    struct Geo {
        double base = 0.0; // y của trục (đáy cột)
        double slot = 1.0; // bề rộng một khe
        double bw = 1.0;   // bề rộng cột
        double vmax = 1.0; // giá trị ở đỉnh vùng vẽ
    };

    Geo geo() const {
        Geo g;
        const int n = std::max(1, static_cast<int>(m_.size()));
        g.base = kH - kBottom;
        g.slot = std::max(1.0, (width() - 2.0 * kPadX) / n);
        g.bw = std::min(kBarMax, g.slot * kBarFrac);
        double mx = 0.0;
        for (const Moc& m : m_)
            if (std::isfinite(m.v))
                mx = std::max(mx, m.v);
        g.vmax = mx > 0.0 ? mx * 1.12 : 1.0; // Artifact: max·1,12
        return g;
    }

    double cx(const Geo& g, int i) const { return kPadX + g.slot * (i + 0.5); }

    QRectF bar_rect(const Geo& g, int i) const {
        const Moc& m = m_.at(i);
        const double plot_h = g.base - kTop;
        double h = kMissingH * plot_h;
        if (std::isfinite(m.v))
            h = std::max(0.0, m.v) / g.vmax * plot_h;
        return {cx(g, i) - g.bw / 2.0, g.base - h, g.bw, h};
    }

    /// Chữ canh giữa tại x, đường chân chữ y; kẹp trong bề rộng widget. Trả hộp chữ.
    QRectF text_c(QPainter& p, const QFont& f, const QColor& c, double x, double y, const QString& s) const {
        const QFontMetricsF fm(f, this);
        const double w = fm.horizontalAdvance(s);
        const double left = std::clamp(x - w / 2.0, 1.0, std::max(1.0, width() - 1.0 - w));
        p.setFont(f);
        p.setPen(c);
        p.drawText(QPointF(left, std::round(y)), s);
        return {left, y - fm.ascent(), w, fm.height()};
    }

    QVector<Moc> m_;
    QVector<Cap> c_;
};

void Chart::paintEvent(QPaintEvent*) {
    if (m_.isEmpty() || width() <= 0)
        return;
    QPainter p(this);
    p.setRenderHint(QPainter::Antialiasing, true);
    p.setRenderHint(QPainter::TextAntialiasing, true);
    const Geo g = geo();
    const QColor ink = lk_col(LkRole::Ink);
    const QColor ink2 = lk_col(LkRole::Ink2);
    const QColor muted = lk_col(LkRole::Muted);
    const QColor down = lk_col(LkRole::Down);

    // Trục đáy 1px (pixel nguyên).
    p.fillRect(QRectF(kPadX, std::round(g.base), width() - 2.0 * kPadX, 1.0), lk_col(LkRole::Line2));

    for (int i = 0; i < m_.size(); ++i) {
        const Moc& m = m_.at(i);
        const bool has_v = std::isfinite(m.v);
        const QColor col = has_v ? lk_tier(m.b) : down;
        const QRectF r = bar_rect(g, i);
        if (!has_v) { // thiếu số: khung rỗng đứt nét, không bao giờ vẽ thành 0
            QPen pen(down, 1.2);
            pen.setDashPattern({3.0 / 1.2, 2.0 / 1.2});
            p.setPen(pen);
            p.setBrush(Qt::NoBrush);
            p.drawRoundedRect(r.adjusted(0.6, 0.6, -0.6, 0.0), 3.0, 3.0);
        } else if (hollow(m)) {
            QColor fill = col;
            fill.setAlphaF(static_cast<float>(kHollowA));
            QPen pen(fill, 1.2);
            pen.setDashPattern({3.0 / 1.2, 2.0 / 1.2});
            p.setPen(pen);
            p.setBrush(fill);
            p.drawRoundedRect(r.adjusted(0.6, 0.6, -0.6, 0.0), 3.0, 3.0);
        } else {
            QColor fill = col;
            fill.setAlphaF(static_cast<float>(kSolidA));
            p.setPen(Qt::NoPen);
            p.setBrush(fill);
            p.drawRoundedRect(r, 3.0, 3.0);
        }
        const double x = cx(g, i);
        text_c(p, axl_font(), has_v ? ink : down, x, r.top() - 6.0, has_v ? fmt_v(m.v) : lk_tr("CẦN DATA"));
        text_c(p, ax_font(), muted, x, g.base + 14.0, m.ky.isEmpty() ? dash() : m.ky);
        const QString src = has_v ? src_of(m) : lk_tr("thiếu số");
        if (!src.isEmpty())
            text_c(p, ax_font(), col, x, g.base + 26.0, src);
    }

    // Δ giữa hai mốc: đoạn đầu của dòng cap, ở hàng dưới cùng; chồng nhãn trước → bỏ (toàn văn ở chú giải).
    QVector<QRectF> taken;
    const QFont fl = axl_font();
    const QFontMetricsF ml(fl, this);
    for (const Cap& c : std::as_const(c_)) {
        if (c.tu < 0 || c.den < 0 || c.tu >= m_.size() || c.den >= m_.size() || c.text.isEmpty())
            continue;
        const QString s = short_of(c.text);
        const double x = (cx(g, c.tu) + cx(g, c.den)) / 2.0;
        const double w = ml.horizontalAdvance(s);
        const QRectF want(x - w / 2.0 - 3.0, g.base + 44.0 - ml.ascent(), w + 6.0, ml.height());
        if (std::any_of(taken.cbegin(), taken.cend(), [&want](const QRectF& t) { return t.intersects(want); }))
            continue;
        taken << text_c(p, fl, ink2, x, g.base + 44.0, s);
    }
}

bool Chart::event(QEvent* e) {
    if (e->type() != QEvent::ToolTip)
        return QWidget::event(e);
    auto* he = static_cast<QHelpEvent*>(e);
    const Geo g = geo();
    const int i = static_cast<int>(std::floor((he->pos().x() - kPadX) / g.slot));
    if (i < 0 || i >= m_.size()) {
        QToolTip::hideText();
        e->ignore();
        return true;
    }
    const Moc& m = m_.at(i);
    QStringList lines;
    lines << (std::isfinite(m.v) ? fmt_v(m.v) : lk_tr("[CẦN DATA] — mốc chưa có số"));
    if (const QString s = src_of(m); !s.isEmpty())
        lines << lk_tr("Nguồn: %1").arg(s);
    if (const QString n = note_of(m); !n.isEmpty())
        lines << n;
    for (const Cap& c : std::as_const(c_))
        if ((c.tu == i || c.den == i) && !c.text.isEmpty())
            lines << c.text;
    QToolTip::showText(he->globalPos(), lkstory::tip_html(lines, m.ky.isEmpty() ? dash() : m.ky), this);
    return true;
}

QVector<Moc> read_moc(const QJsonArray& arr) {
    QVector<Moc> out;
    for (const auto& v : arr) {
        if (!v.isObject())
            continue;
        const QJsonObject o = v.toObject();
        Moc m;
        m.ky = text_opt(o.value(QStringLiteral("ky")));
        double d = 0.0;
        if (num_of(o.value(QStringLiteral("v")), &d))
            m.v = d;
        m.b = o.value(QStringLiteral("b")).toString().trimmed();
        m.kieu = o.value(QStringLiteral("kieu")).toString().trimmed().toLower();
        m.cf = o.value(QStringLiteral("cf")).toBool(false);
        m.so_tron = o.value(QStringLiteral("so_tron")).toBool(false);
        if (m.ky.isEmpty() && !std::isfinite(m.v))
            continue; // mục rỗng hẳn: bỏ
        out << m;
    }
    return out;
}

QVector<Cap> read_cap(const QJsonArray& arr) {
    QVector<Cap> out;
    for (const auto& v : arr) {
        if (!v.isObject())
            continue;
        const QJsonObject o = v.toObject();
        Cap c;
        double d = 0.0;
        if (num_of(o.value(QStringLiteral("i_tu")), &d))
            c.tu = static_cast<int>(std::lround(d));
        if (num_of(o.value(QStringLiteral("i_den")), &d))
            c.den = static_cast<int>(std::lround(d));
        c.text = text_opt(o.value(QStringLiteral("text")));
        if (!c.text.isEmpty())
            out << c;
    }
    return out;
}

/// Toàn văn Δ dưới hình: "12/2024 → 12/2025: +136,6% · k 27,9 nghìn · giá −5,1%".
QString legend_text(const QVector<Moc>& m, const QVector<Cap>& caps) {
    const auto ky = [&m](int i) {
        return i >= 0 && i < m.size() && !m.at(i).ky.isEmpty() ? m.at(i).ky : QStringLiteral("#%1").arg(i);
    };
    QStringList lines;
    for (const Cap& c : caps)
        lines << QStringLiteral("%1 → %2: %3").arg(ky(c.tu), ky(c.den), c.text);
    return lines.join(QLatin1Char('\n'));
}

} // namespace lkcotmoc

namespace lkview {

QWidget* make_cotmoc(const QJsonObject& b, QWidget* parent) {
    using namespace lkcotmoc;
    QVBoxLayout* vl = nullptr;
    QFrame* card = make_fig(parent, &vl);
    lk_add_head(vl, b, card, LkHead::Fig);
    const QVector<Moc> moc = read_moc(b.value(QStringLiteral("items")).toArray());
    const QVector<Cap> caps = read_cap(b.value(QStringLiteral("cap")).toArray());
    const QFont gap_font = lk_font_mono(11, 600);
    if (moc.isEmpty()) {
        vl->addWidget(lk_label(lk_tr("[CẦN DATA] — chưa có mốc nào để vẽ"), gap_font, lk_col(LkRole::Down), card));
        return card;
    }
    vl->addWidget(new Chart(moc, caps, card));
    if (!caps.isEmpty()) {
        QLabel* lg = lk_label(legend_text(moc, caps), lk_font_sans(12), lk_col(LkRole::Ink2), card);
        vl->addWidget(lg);
    }
    QStringList thieu;
    for (const Moc& m : moc)
        if (!std::isfinite(m.v))
            thieu << (m.ky.isEmpty() ? dash() : m.ky);
    if (!thieu.isEmpty())
        vl->addWidget(lk_label(lk_tr("[CẦN DATA] — mốc %1 chưa có số").arg(thieu.join(QStringLiteral(", "))), gap_font,
                               lk_col(LkRole::Down), card));
    vl->addStretch(1); // trong "row" thẻ kéo cao bằng thẻ bên cạnh: phần dư dồn xuống đáy, không giãn khe đầu
    return card;
}

} // namespace lkview

} // namespace fincept::screens::langkinh
