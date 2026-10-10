// src/screens/langkinh/LkNumberLine.cpp
// Lăng Kính FFT — block "numline" (LK_HOSO_SPEC §6): thước vwap · sigma · ruler. Xem LkNumberLine.h.
//
// QPainter dùng thẳng QFont của LkTheme; nhãn QLabel của thẻ đi qua lk_label (phông qua QSS, vì QSS toàn cục có
// "* { font-family; font-size }"). QSS toàn cục tô nền BG_BASE cho QWidget → mọi con trong thẻ nền trong suốt.
// Vạch 1–2px vẽ bằng fillRect trên toạ độ nguyên (sắc ở 1x lẫn 2x).
#include "screens/langkinh/LkNumberLine.h"
#include "screens/langkinh/LkNumberLineDraw.h"

#include "screens/langkinh/LkChips.h"
#include "screens/langkinh/LkStory.h"

#include <QFont>
#include <QFontMetricsF>
#include <QEvent>
#include <QFrame>
#include <QHBoxLayout>
#include <QHelpEvent>
#include <QJsonArray>
#include <QLabel>
#include <QPaintEvent>
#include <QPainter>
#include <QPainterPath>
#include <QPen>
#include <QSizePolicy>
#include <QToolTip>
#include <QVBoxLayout>

#include <algorithm>
#include <cmath>
#include <limits>
#include <numeric>
#include <utility>

namespace fincept::screens::langkinh {

// Helper tự do: namespace có tên riêng (quy ước của module, không dùng namespace ẩn danh).
namespace lknumline {

using lkview::lk_tr;

constexpr int kVwapH = 128;
constexpr int kSigmaH = 112;
constexpr int kMinW = 280;

double nan_v() {
    return std::numeric_limits<double>::quiet_NaN();
}

double num(const QJsonObject& o, const char* key) {
    double d = 0.0;
    return lkview::num_of(o.value(QLatin1String(key)), &d) ? d : nan_v();
}

/// Nền nhạt của một màu với alpha riêng từng mức vùng σ (Artifact --zone-*: tối / sáng).
QColor zone(const QColor& c, bool light, double dark_a, double light_a) {
    QColor s = c;
    s.setAlphaF(static_cast<float>(light ? light_a : dark_a));
    return s;
}

/// Giá kiểu Việt, bỏ số 0 thừa sau dấu phẩy: 58,9 · 75,37 · 54 · 58.900.
QString fmt_px(double v) {
    const double a = std::abs(v);
    const int dec = a >= 1000.0 ? 0 : (a >= 100.0 ? 1 : 2);
    QString s = lkview::vn_num(v, dec);
    if (dec > 0 && s.contains(QLatin1Char(','))) {
        while (s.endsWith(QLatin1Char('0')))
            s.chop(1);
        if (s.endsWith(QLatin1Char(',')))
            s.chop(1);
    }
    return s;
}

/// Số kiểu Việt có dấu "+" khi dương (không gắn "+" cho số làm tròn về 0): +2,1 · −1,8 · 0,0.
QString signed_num(double v, int decimals) {
    QString s = lkview::vn_num(v, decimals);
    if (v > 0.0 && std::round(v * std::pow(10.0, decimals)) > 0.0)
        s.prepend(QLatin1Char('+'));
    return s;
}

/// Tỷ lệ → phần trăm có dấu: +2,1% · −1,8%.
QString fmt_pct(double frac) {
    return signed_num(frac * 100.0, 1) + QLatin1Char('%');
}

/// z → "+1,25σ" · "−2,31σ".
QString fmt_sigma(double z) {
    return signed_num(z, 2) + QChar(0x03C3);
}

/// Nhãn vạch nguyên của ruler: −3σ … 0σ … +3σ.
QString sigma_tick(int k) {
    return (k == 0 ? QStringLiteral("0") : signed_num(k, 0)) + QChar(0x03C3);
}

QString vwap_name(int i) {
    return i == 0 ? lk_tr("VWAP 6T") : (i == 1 ? lk_tr("VWAP 12T") : lk_tr("VWAP 24T"));
}

/// Nhãn trên thước (tiêu đề block đã ghi VWAP): "6T" · "12T" · "24T"; tên đủ ở tooltip.
QString vwap_short(int i) {
    return i == 0 ? lk_tr("6T") : (i == 1 ? lk_tr("12T") : lk_tr("24T"));
}

/// Tên mốc dải σ theo thứ tự c2 c1 f r1 r2.
QString sigma_name(int i) {
    static const QString kNames[5] = {QStringLiteral("−2σ"), QStringLiteral("−1σ"), QStringLiteral("μ"),
                                      QStringLiteral("+1σ"), QStringLiteral("+2σ")};
    return kNames[std::clamp(i, 0, 4)];
}

QFont ax_font() { // Artifact .ax: mono 10px muted
    return lkview::lk_font_mono(10, 400);
}
QFont axl_font() { // Artifact .axl: mono 10,5px đậm vừa
    return lkview::lk_font_mono(11, 600);
}
QFont px_font() { // nhãn giá
    return lkview::lk_font_mono(12, 700);
}

// ── Xếp nhãn tránh chồng ──────────────────────────────────────────────────────

/// Tổng bề ngang chồng lấn (kể cả khe kGap) của r với các nhãn đã đặt trong hàng.
double overlap(const QRectF& r, const Row& row) {
    double ov = 0.0;
    for (const QRectF& t : row.taken) {
        const double a = std::max(r.left(), t.left() - kGap);
        const double b = std::min(r.right(), t.right() + kGap);
        if (b > a)
            ov += b - a;
    }
    return ov;
}

/// Hộp chữ rộng w: canh giữa (mặc định) / trái / phải tại x, kẹp trong bề rộng widget.
QRectF text_rect(double x, double w, double top, double h, Qt::Alignment al, double width) {
    double left = x - w / 2.0;
    if (al.testFlag(Qt::AlignLeft))
        left = x;
    else if (al.testFlag(Qt::AlignRight))
        left = x - w;
    left = std::clamp(left, kEdge, std::max(kEdge, width - kEdge - w));
    return {left, top, w, h};
}

/// Hàng đầu tiên (theo thứ tự ưu tiên) mà nhãn không chồng; không có → hàng chồng ít nhất. Trả chỉ số hàng.
int best_row(const QVector<Row>& rows, const QVector<int>& prefer, double x, double w, double h, double width,
             QRectF* out) {
    int best = -1;
    double best_ov = std::numeric_limits<double>::infinity();
    for (const int ri : prefer) {
        if (ri < 0 || ri >= rows.size())
            continue;
        const QRectF r = text_rect(x, w, rows.at(ri).top, h, Qt::AlignHCenter, width);
        const double ov = overlap(r, rows.at(ri));
        if (ov < best_ov) {
            best_ov = ov;
            best = ri;
            *out = r;
            if (ov <= 0.0)
                break;
        }
    }
    return best;
}

// ── Nét vẽ ────────────────────────────────────────────────────────────────────

/// Vạch dọc w px, canh pixel nguyên (fillRect, không nhoè ở HiDPI).
void vline(QPainter& p, double x, double y0, double y1, const QColor& c, int w) {
    const double a = std::round(std::min(y0, y1));
    const double b = std::round(std::max(y0, y1));
    if (b > a)
        p.fillRect(QRectF(std::round(x - w / 2.0), a, w, b - a), c);
}

void diamond(QPainter& p, const QPointF& c, double r, const QColor& fill, const QColor& edge) {
    QPainterPath d;
    d.moveTo(c.x(), c.y() - r);
    d.lineTo(c.x() + r, c.y());
    d.lineTo(c.x(), c.y() + r);
    d.lineTo(c.x() - r, c.y());
    d.closeSubpath();
    p.setPen(QPen(edge, 1.5));
    p.setBrush(fill);
    p.drawPath(d);
}

/// Chấm ruler: tròn (dir 0) hoặc tam giác chĩa ra mép khi ngoài ±3σ (dir −1 trái, +1 phải).
void marker(QPainter& p, const QPointF& c, int dir, const QColor& fill, const QColor& edge) {
    p.setPen(QPen(edge, 1.5));
    p.setBrush(fill);
    if (dir == 0) {
        p.drawEllipse(c, 5.0, 5.0);
        return;
    }
    const double s = dir;
    QPainterPath t;
    t.moveTo(c.x() + 7.0 * s, c.y());
    t.lineTo(c.x() - 3.0 * s, c.y() - 6.0);
    t.lineTo(c.x() - 3.0 * s, c.y() + 6.0);
    t.closeSubpath();
    p.drawPath(t);
}

void text_at(QPainter& p, const QRectF& r, const QFont& f, const QFontMetricsF& fm, const QColor& c,
             const QString& s) {
    p.setFont(f);
    p.setPen(c);
    p.drawText(QPointF(r.left(), std::round(r.top() + fm.ascent())), s);
}

} // namespace lknumline

namespace lkview {

// ── LkNumberLine — đọc JSON ──────────────────────────────────────────────────

LkNumberLine::LkNumberLine(const QJsonObject& b, QWidget* parent) : QWidget(parent) {
    const QString kind = b.value(QStringLiteral("mode")).toString().trimmed().toLower();
    if (kind == QLatin1String("vwap"))
        parse_vwap(b);
    else if (kind == QLatin1String("sigma"))
        parse_sigma(b);
    else if (kind == QLatin1String("ruler"))
        parse_ruler(b);
    else
        missing_ << lk_tr("mode thước không hợp lệ");
    setSizePolicy(QSizePolicy::Expanding, QSizePolicy::Fixed);
    setFixedHeight(height_);
    setToolTip(lkstory::tip_html(tip_, tip_head_)); // helper tooltip dùng chung của module (tự escape)
    setAccessibleName(tip_head_);
    setAccessibleDescription(tip_.join(QStringLiteral("; ")));
}

QSize LkNumberLine::sizeHint() const {
    return {640, height_};
}

QSize LkNumberLine::minimumSizeHint() const {
    return {lknumline::kMinW, height_};
}

void LkNumberLine::load_palette() {
    c_.light = lk_is_light();
    c_.surface = lk_col(LkRole::Surface);
    c_.line2 = lk_col(LkRole::Line2);
    c_.ink2 = lk_col(LkRole::Ink2);
    c_.muted = lk_col(LkRole::Muted);
    c_.amber = lk_col(LkRole::Amber);
    c_.up = lk_col(LkRole::Up);
    c_.down = lk_col(LkRole::Down);
    c_.violet = lk_col(LkRole::Violet);
    c_.grey = lk_col(LkRole::Grey);
}

void LkNumberLine::set_axis(double mn, double mx, double lo_frac, double hi_frac) {
    const double span = std::max(std::abs(mx - mn), 1.0);
    a0_ = mn > 0.0 ? mn * (1.0 - lo_frac) : mn - span * lo_frac;
    a1_ = mx > 0.0 ? mx * (1.0 + hi_frac) : mx + span * hi_frac;
    if (!(a1_ > a0_)) {
        a0_ = mn - 1.0;
        a1_ = mx + 1.0;
    }
}

double LkNumberLine::gap(int i) const {
    return std::isfinite(kc_[i]) ? kc_[i] : px_ / v_[i] - 1.0;
}

double LkNumberLine::hatch_w() const {
    if (mode_ != Mode::Sigma || !neg_)
        return 0.0;
    const double w = std::max(1.0, width() - 2.0 * pad_);
    return std::clamp(w * 0.16, 116.0, 156.0); // đủ chỗ cho "không dùng được" (mono 10)
}

double LkNumberLine::x_of(double v) const {
    const double hw = hatch_w();
    const double w = std::max(1.0, width() - 2.0 * pad_ - hw);
    return pad_ + hw + (v - a0_) / (a1_ - a0_) * w;
}

void LkNumberLine::parse_vwap(const QJsonObject& b) {
    using namespace lknumline;
    mode_ = Mode::Vwap;
    height_ = kVwapH;
    pad_ = 20.0;
    px_ = num(b, "px");
    if (!std::isfinite(px_))
        missing_ << lk_tr("giá");
    const char* keys[3] = {"v6", "v12", "v24"};
    const char* kc_keys[3] = {"kc6", "kc12", "kc24"}; // hợp đồng v2: khoảng cách script tính từ số chưa làm tròn
    int n = 0;
    for (int i = 0; i < 3; ++i) {
        kc_[i] = num(b, kc_keys[i]);
        v_[i] = num(b, keys[i]);
        if (v_[i] > 0.0) { // NaN, 0, âm: không phải VWAP dùng được
            ++n;
        } else {
            v_[i] = nan_v();
            missing_ << vwap_name(i);
        }
    }
    lo_ = num(b, "lo");
    hi_ = num(b, "hi");
    if (!std::isfinite(lo_) || !std::isfinite(hi_)) {
        lo_ = hi_ = nan_v();
        missing_ << lk_tr("dải 52 tuần");
    } else if (lo_ > hi_) { // số nguồn hỏng: không tự sửa (luật §0), coi như thiếu và ghi rõ
        lo_ = hi_ = nan_v();
        missing_ << lk_tr("dải 52 tuần đảo (lo > hi)");
    }
    valid_ = std::isfinite(px_) && n > 0;
    if (!valid_)
        return;

    double mn = px_;
    double mx = px_;
    for (const double v : v_)
        if (std::isfinite(v)) {
            mn = std::min(mn, v);
            mx = std::max(mx, v);
        }
    if (std::isfinite(lo_)) {
        mn = std::min(mn, lo_);
        mx = std::max(mx, hi_);
    }
    set_axis(mn, mx, 0.015, 0.01); // Artifact: min·0,985 … max·1,01

    tip_head_ = lk_tr("Giá so với VWAP cụm");
    tip_ << lk_tr("Giá %1").arg(fmt_px(px_));
    for (int i = 0; i < 3; ++i)
        if (std::isfinite(v_[i]))
            tip_ << lk_tr("%1: %2 · giá %3 so với cụm%4")
                        .arg(vwap_name(i), fmt_px(v_[i]), fmt_pct(gap(i)),
                             std::isfinite(kc_[i]) ? QString() : lk_tr(" (tính lại từ số làm tròn)"));
    if (std::isfinite(lo_))
        tip_ << lk_tr("52 tuần %1 – %2").arg(fmt_px(lo_), fmt_px(hi_));
}

void LkNumberLine::parse_sigma(const QJsonObject& b) {
    using namespace lknumline;
    mode_ = Mode::Sigma;
    height_ = kSigmaH;
    pad_ = 16.0;
    px_ = num(b, "px");
    if (!std::isfinite(px_))
        missing_ << lk_tr("giá");
    const char* keys[5] = {"c2", "c1", "f", "r1", "r2"};
    // c2 (hoặc c2 + c1) null/vắng = mốc không có mức giá dùng được (script bỏ mức ≤ 0) → vẽ các mốc còn lại, mốc
    // trống vào ô gạch chéo "không dùng được". f, r1, r2 bắt buộc; mốc trống ở giữa thước → [CẦN DATA].
    int n_gap = 0; // số mốc trống liền từ c2
    bool all = true;
    for (int i = 0; i < 5; ++i) {
        b_[i] = num(b, keys[i]);
        if (std::isfinite(b_[i]))
            continue;
        if (i < 2 && i == n_gap) {
            ++n_gap;
            continue;
        }
        all = false;
        missing_ << QStringLiteral("%1 (%2)").arg(sigma_name(i), QLatin1String(keys[i]));
    }
    bool mono = all;
    for (int i = n_gap; all && i < 4; ++i)
        if (b_[i] > b_[i + 1])
            mono = false;
    if (all && !mono)
        missing_ << lk_tr("dải σ không đơn điệu (cần c2 ≤ c1 ≤ f ≤ r1 ≤ r2)");
    if (mono && !(b_[4] > b_[n_gap])) { // σ = 0: các mốc trùng nhau, không có thước để vẽ
        mono = false;
        missing_ << lk_tr("dải σ suy biến (%1 = r2)").arg(QLatin1String(keys[n_gap]));
    }
    s_ = text_opt(b.value(QStringLiteral("s")));
    m_ = text_opt(b.value(QStringLiteral("m")));
    valid_ = std::isfinite(px_) && mono;
    if (!valid_)
        return;

    // σ lớn hơn μ/2 (P/E của năm lãi mỏng): mốc dưới ≤ 0 không phải giá → trục kẹp ở 0, mốc âm dồn vào ô
    // "không dùng được" (không vẽ số âm lên thước; tooltip vẫn đủ số của script).
    neg_ = !(b_[0] > 0.0); // ≤ 0 hoặc trống
    if (neg_) {
        a0_ = 0.0;
        a1_ = std::max(b_[4], px_) * 1.04;
    } else {
        set_axis(std::min(b_[0], px_), std::max(b_[4], px_), 0.10, 0.04); // Artifact: min(c2,px)·0,9 … r2·1,04
    }
    tip_head_ = m_.isEmpty() ? lk_tr("Dải giá theo σ") : lk_tr("Dải giá theo σ · %1").arg(m_);
    tip_ << lk_tr("Giá %1").arg(sigma_price_label());
    for (int i = 0; i < 5; ++i)
        tip_ << (b_[i] > 0.0             ? QStringLiteral("%1  %2").arg(sigma_name(i), fmt_px(b_[i]))
                 : std::isfinite(b_[i]) ? lk_tr("%1  %2 — âm, không dùng được").arg(sigma_name(i), fmt_px(b_[i]))
                                        : lk_tr("%1 — trống (không có mức giá dương), không dùng được")
                                              .arg(sigma_name(i)));
}

/// "58.900 · P/B 1,94× · −2,31σ" (m, s bỏ qua nếu thiếu).
QString LkNumberLine::sigma_price_label() const {
    QStringList parts{lknumline::fmt_px(px_)};
    if (!m_.isEmpty())
        parts << m_;
    if (!s_.isEmpty())
        parts << s_;
    return parts.join(QStringLiteral(" · "));
}

// ── LkNumberLine — vẽ ────────────────────────────────────────────────────────

void LkNumberLine::paintEvent(QPaintEvent*) {
    if (!valid_ || width() <= 0)
        return;
    load_palette(); // quy ước LkTheme: widget tự vẽ đọc màu tại lúc vẽ
    QPainter p(this);
    p.setRenderHint(QPainter::Antialiasing, true);
    p.setRenderHint(QPainter::TextAntialiasing, true);
    switch (mode_) {
    case Mode::Vwap:
        paint_vwap(p);
        break;
    case Mode::Sigma:
        paint_sigma(p);
        break;
    case Mode::Ruler:
        paint_ruler(p);
        break;
    case Mode::None:
        break;
    }
}

/// Năm vùng rẻ₂ · rẻ₁ · giữa · đắt₁ · đắt₂ giữa 6 mốc (giá trị trục), trong thanh bo góc 4px.
/// Biên vùng làm tròn về pixel nguyên → hai vùng kề nhau không lộ đường nối.
void LkNumberLine::paint_zones(QPainter& p, const QRectF& bar, const std::array<double, 6>& edges,
                               const QRectF& outline) const {
    using lknumline::zone;
    if (!(bar.width() > 0.0))
        return;
    const bool L = c_.light;
    const QColor fills[5] = {zone(c_.up, L, 0.30, 0.26), zone(c_.up, L, 0.14, 0.12), zone(c_.grey, L, 0.10, 0.08),
                             zone(c_.down, L, 0.14, 0.12), zone(c_.down, L, 0.28, 0.24)};
    QPainterPath shape;
    shape.addRoundedRect(outline.isValid() ? outline : bar, 4.0, 4.0);
    p.setPen(Qt::NoPen);
    for (int i = 0; i < 5; ++i) {
        const double x0 = std::clamp(std::round(x_of(edges[i])), bar.left(), bar.right());
        const double x1 = std::clamp(std::round(x_of(edges[i + 1])), bar.left(), bar.right());
        if (x1 <= x0)
            continue;
        QPainterPath seg;
        seg.addRect(QRectF(x0, bar.top(), x1 - x0, bar.height()));
        p.fillPath(shape.intersected(seg), fills[i]);
    }
}

void LkNumberLine::paint_vwap(QPainter& p) const {
    using namespace lknumline;
    const double W = width();
    constexpr double yb = 60.0; // tâm thanh 52 tuần
    const QFont fa = ax_font();
    const QFont fl = axl_font();
    const QFont fp = px_font();
    const QFontMetricsF ma(fa, this);
    const QFontMetricsF ml(fl, this);
    const QFontMetricsF mp(fp, this);
    QVector<Row> rows(4);
    rows[0].top = 4.0;       // trên, xa thước
    rows[1].top = 22.0;      // trên, sát thước
    rows[2].top = yb + 28.0; // dưới: hàng nhãn giá
    rows[3].top = yb + 46.0; // dưới, xa thước

    // Dải 52 tuần + quãng giá còn phải đi để vượt cụm VWAP cao nhất.
    p.setPen(Qt::NoPen);
    const bool has_range = std::isfinite(lo_) && std::isfinite(hi_);
    const double xlo = has_range ? std::round(x_of(lo_)) : 0.0;
    const double xhi = has_range ? std::round(x_of(hi_)) : 0.0;
    if (has_range) {
        p.setBrush(lk_soft(c_.grey));
        p.drawRoundedRect(QRectF(xlo, yb - 6.0, std::max(2.0, xhi - xlo), 12.0), 6.0, 6.0);
    }
    const double P = x_of(px_);
    double vmax = -std::numeric_limits<double>::infinity();
    for (const double v : v_)
        if (std::isfinite(v))
            vmax = std::max(vmax, v);
    if (px_ < vmax) {
        const double x0 = std::round(P);
        const double x1 = std::round(x_of(vmax));
        p.fillRect(QRectF(x0, yb - 6.0, x1 - x0, 12.0), lk_soft(c_.down));
    }

    // Nhãn giá đặt trước (ưu tiên cao nhất), hàng dưới sát thước.
    const QString ps = lk_tr("Giá %1").arg(fmt_px(px_));
    const QRectF pr = text_rect(P, mp.horizontalAdvance(ps), rows[2].top, mp.height(), Qt::AlignHCenter, W);
    rows[2].taken << pr;

    // Ba cụm VWAP theo thứ tự giá: vạch violet + nhãn "VWAP 6T 59,98  −1,8%" ở hàng trống đầu tiên
    // (trên sát → trên xa → dưới xa → dưới sát), nối với vạch bằng đường dẫn mảnh.
    struct Lab {
        QRectF r;
        QString main;
        QString dist;
        double wm = 0.0;
        QColor dc;
    };
    QVector<Lab> labs;
    QVector<int> idx;
    for (int i = 0; i < 3; ++i)
        if (std::isfinite(v_[i]))
            idx << i;
    std::sort(idx.begin(), idx.end(), [this](int a, int b) { return v_[a] < v_[b]; });
    for (const int i : std::as_const(idx)) {
        const double X = x_of(v_[i]);
        Lab l;
        l.main = QStringLiteral("%1 %2").arg(vwap_short(i), fmt_px(v_[i]));
        const double d = gap(i);
        l.dist = fmt_pct(d);
        l.dc = d < 0.0 ? c_.down : (d > 0.0 ? c_.up : c_.ink2);
        l.wm = ml.horizontalAdvance(l.main);
        const double w = l.wm + 6.0 + ma.horizontalAdvance(l.dist);
        const int ri = best_row(rows, {1, 0, 3, 2}, X, w, ml.height(), W, &l.r);
        if (ri < 0)
            continue;
        rows[ri].taken << l.r;
        if (ri <= 1)
            vline(p, X, l.r.bottom() + 2.0, yb - 12.0, c_.line2);
        else
            vline(p, X, yb + 6.0, l.r.top() - 2.0, c_.line2);
        vline(p, X, yb - 12.0, yb + 6.0, c_.violet, 2);
        labs << l;
    }

    // Marker giá: vạch amber xuyên thước + thoi amber viền màu nền thẻ.
    vline(p, P, yb - 10.0, yb + 10.0, c_.amber, 2);
    diamond(p, QPointF(std::round(P), yb + 17.0), 6.0, c_.amber, c_.surface);

    // Nhãn dải 52 tuần: thử phải → trái, hàng dưới; không còn chỗ thì bỏ (tooltip vẫn có).
    if (has_range) {
        const QString rs = lk_tr("52 tuần %1 – %2").arg(fmt_px(lo_), fmt_px(hi_));
        const double w = ma.horizontalAdvance(rs);
        struct Try {
            int row;
            double x;
            Qt::Alignment al;
        };
        const Try tries[4] = {
            {2, xhi, Qt::AlignRight}, {3, xhi, Qt::AlignRight}, {2, xlo, Qt::AlignLeft}, {3, xlo, Qt::AlignLeft}};
        for (const Try& t : tries) {
            const QRectF r = text_rect(t.x, w, rows[t.row].top, ma.height(), t.al, W);
            if (overlap(r, rows[t.row]) <= 0.0) {
                rows[t.row].taken << r;
                text_at(p, r, fa, ma, c_.muted, rs);
                break;
            }
        }
    }

    for (const Lab& l : std::as_const(labs)) {
        text_at(p, l.r, fl, ml, c_.violet, l.main);
        p.setFont(fa);
        p.setPen(l.dc);
        p.drawText(QPointF(l.r.left() + l.wm + 6.0, std::round(l.r.top() + ml.ascent())), l.dist);
    }
    text_at(p, pr, fp, mp, c_.amber, ps);
}

void LkNumberLine::paint_sigma(QPainter& p) const {
    using namespace lknumline;
    const double W = width();
    constexpr double yb = 46.0; // đỉnh thanh vùng
    constexpr double bh = 22.0; // cao thanh vùng
    const QFont fa = ax_font();
    const QFont fl = axl_font();
    const QFont fp = px_font();
    const QFontMetricsF ma(fa, this);
    const QFontMetricsF ml(fl, this);
    const QFontMetricsF mp(fp, this);

    const double xh = std::round(pad_);      // mép trái thanh (kể cả ô "không dùng được")
    const double xa = std::round(x_of(a0_)); // giá trị nhỏ nhất vẽ được (= 0 khi có mốc âm)
    const double xb = std::round(x_of(a1_));
    std::array<double, 6> edges{a0_, b_[0], b_[1], b_[3], b_[4], a1_};
    if (neg_)
        for (double& e : edges)
            e = std::isfinite(e) ? std::max(e, 0.0) : 0.0; // mốc trống ~ mốc ≤ 0: dồn về mép trục (0)
    const QRectF outline(neg_ ? xh : xa, yb, xb - (neg_ ? xh : xa), bh);
    paint_zones(p, QRectF(xa, yb, xb - xa, bh), edges, outline);

    Row names;
    Row vals;
    names.top = 4.0;
    vals.top = 21.0;
    if (neg_) { // ô gạch chéo cho các mốc ≤ 0: tên mốc ở hàng trên, "< 0" ở hàng giá, chữ trong ô
        QPainterPath shape;
        shape.addRoundedRect(outline, 4.0, 4.0);
        QPainterPath cell;
        cell.addRect(QRectF(xh, yb, xa - xh, bh));
        const QPainterPath hatch = shape.intersected(cell);
        p.fillPath(hatch, zone(c_.grey, c_.light, 0.08, 0.06));
        p.save();
        p.setClipPath(hatch);
        p.setPen(QPen(c_.line2, 1.0));
        for (double x = xh - bh; x < xa; x += 6.0)
            p.drawLine(QPointF(x, yb + bh), QPointF(x + bh, yb));
        p.restore();
        vline(p, xa, yb - 4.0, yb + bh, c_.line2);
        QStringList neg;
        bool known = true; // mọi mốc gom vào ô đều có số (âm) → "< 0"; có mốc trống → "—"
        for (int i = 0; i < 5; ++i)
            if (!(b_[i] > 0.0)) {
                neg << sigma_name(i);
                known = known && std::isfinite(b_[i]);
            }
        const double xc = (xh + xa) / 2.0;
        const QString nm = neg.join(QLatin1Char(' '));
        const QRectF rn = text_rect(xc, ml.horizontalAdvance(nm), names.top, ml.height(), Qt::AlignHCenter, W);
        names.taken << rn;
        text_at(p, rn, fl, ml, c_.muted, nm);
        const QString lt = known ? lk_tr("< 0") : dash();
        const QRectF rv = text_rect(xc, ma.horizontalAdvance(lt), vals.top, ma.height(), Qt::AlignHCenter, W);
        vals.taken << rv;
        text_at(p, rv, fa, ma, c_.muted, lt);
        const QString t = lk_tr("không dùng được");
        const QRectF rt = text_rect(xc, ma.horizontalAdvance(t), yb + (bh - ma.height()) / 2.0, ma.height(),
                                    Qt::AlignHCenter, W);
        QColor halo = c_.surface;
        halo.setAlphaF(0.85f);
        p.fillRect(rt.adjusted(-3.0, 0.0, 3.0, 0.0), halo);
        text_at(p, rt, fa, ma, c_.muted, t);
    }

    // Mốc: vạch + tên σ (hàng trên) + giá (hàng dưới). Đặt μ trước rồi ±1σ, ±2σ; chồng thì bỏ nhãn đó.
    // Mốc ≤ 0 không có vị trí trên trục giá (đã gom vào ô "không dùng được").
    const int prio[5] = {2, 1, 3, 0, 4};
    for (const int i : prio) {
        if (!(b_[i] > 0.0)) // ≤ 0 hoặc trống
            continue;
        const double X = x_of(b_[i]);
        vline(p, X, yb - 4.0, yb + bh, i == 2 ? c_.ink2 : c_.line2);
        const QString nm = sigma_name(i);
        const QRectF rn = text_rect(X, ml.horizontalAdvance(nm), names.top, ml.height(), Qt::AlignHCenter, W);
        if (overlap(rn, names) <= 0.0) {
            names.taken << rn;
            text_at(p, rn, fl, ml, c_.ink2, nm);
        }
        const QString vs = fmt_px(b_[i]);
        const QRectF rv = text_rect(X, ma.horizontalAdvance(vs), vals.top, ma.height(), Qt::AlignHCenter, W);
        if (overlap(rv, vals) <= 0.0) {
            vals.taken << rv;
            text_at(p, rv, fa, ma, c_.muted, vs);
        }
    }

    // "rẻ" / "đắt" trong hai đầu thanh ("rẻ" chỉ khi vùng rẻ₁ còn chỗ sau ô "không dùng được").
    const double base = std::round(yb + (bh + ma.ascent() - ma.descent()) / 2.0);
    const QString re = lk_tr("rẻ");
    const QString dat = lk_tr("đắt");
    p.setFont(fa);
    if (!neg_ || (b_[1] > 0.0 && x_of(b_[1]) - xa > ma.horizontalAdvance(re) + 12.0)) {
        p.setPen(c_.up);
        p.drawText(QPointF(xa + 6.0, base), re);
    }
    p.setPen(c_.down);
    p.drawText(QPointF(xb - 6.0 - ma.horizontalAdvance(dat), base), dat);

    // Giá: vạch amber xuyên thanh + thoi + nhãn "58.900 · P/B 1,94× · −2,31σ".
    const double P = x_of(px_);
    vline(p, P, yb - 3.0, yb + bh + 3.0, c_.amber, 2);
    diamond(p, QPointF(std::round(P), yb + bh + 11.0), 6.0, c_.amber, c_.surface);
    const QString ps = sigma_price_label();
    text_at(p, text_rect(P, mp.horizontalAdvance(ps), yb + bh + 21.0, mp.height(), Qt::AlignHCenter, W), fp, mp,
            c_.amber, ps);
}

} // namespace lkview

} // namespace fincept::screens::langkinh
