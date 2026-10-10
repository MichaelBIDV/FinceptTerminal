// src/screens/langkinh/LkRrgChart.cpp
// Lăng Kính FFT — block "rrg": RRG xấp xỉ (EST) vẽ bằng QPainter. Xem LkRrgChart.h.
#include "screens/langkinh/LkRrgChart.h"

#include "screens/langkinh/LkChips.h"
#include "screens/langkinh/LkTheme.h"

#include <QDate>
#include <QFontMetricsF>
#include <QFrame>
#include <QJsonArray>
#include <QLabel>
#include <QLineF>
#include <QMouseEvent>
#include <QPainter>
#include <QPainterPath>
#include <QPen>
#include <QPolygonF>
#include <QSizePolicy>
#include <QToolTip>
#include <QVBoxLayout>

#include <algorithm>
#include <cmath>
#include <iterator>
#include <limits>
#include <utility>

// Helper tự do: namespace có tên riêng (quy ước của module, không dùng namespace ẩn danh).
namespace fincept::screens::langkinh::lkrrg {

using lkview::dash;
using lkview::lk_col;
using lkview::lk_tr;
using lkview::num_of;
using lkview::vn_num;

constexpr double kCenter = 100.0;  // tâm RRG: RS-Ratio = RS-Momentum = 100
constexpr int kMaxTail = 8;        // SPEC §4: đuôi 8 tuần
constexpr double kMinSpan = 2.0;   // khung tự tính hẹp nhất (điểm RS) — không phóng đại nhiễu khi các điểm sát nhau
constexpr double kAutoPad = 0.10;  // đệm khung tự tính
constexpr double kMinSide = 0.30;  // khung tự tính: phía hẹp của 100 ≥ 30% phía rộng
constexpr double kGivenPad = 0.05; // đệm khi phải nới x_range/y_range cho điểm nằm ngoài
constexpr int kBaseW = 640;        // tỉ lệ khung như Artifact (640×420)
constexpr int kBaseH = 420;
constexpr int kMinW = 240;
constexpr int kMinH = 320;
constexpr int kMaxH = 640;
constexpr int kMaxW = (kMaxH * kBaseW + kBaseH / 2) / kBaseH; // 975: rộng hơn thì giữ tỉ lệ 640×420 và canh giữa
constexpr double kMarginTop = 24.0; // chỗ cho "RS-Momentum ↑"
constexpr double kMarginRight = 16.0;
constexpr double kHeadHit = 12.0;  // bán kính bấm/rê điểm mới nhất
constexpr double kPointHit = 9.0;  // bán kính rê điểm cũ
constexpr double kLabelGap = 10.0; // khoảng nhãn mã ↔ điểm mới nhất
constexpr double kDim = 0.32;      // độ mờ chuỗi khác khi đang rê một chuỗi
constexpr double kPlotMin = 40.0;  // vùng vẽ nhỏ hơn → chỉ vẽ "—"
constexpr double kInset = 8.0;     // tên góc cách mép vùng vẽ

/// Bảng màu khi chuỗi không có "mau" — thứ tự như Artifact (VCB blue, MSN violet, FPT amber).
constexpr lkview::LkRole kPalette[] = {lkview::LkRole::Blue, lkview::LkRole::Violet, lkview::LkRole::Amber,
                                       lkview::LkRole::Up,   lkview::LkRole::Down,   lkview::LkRole::Grey};

enum Quad { Improving = 0, Leading = 1, Lagging = 2, Weakening = 3 };

/// Tám hướng đặt nhãn (toạ độ màn hình, y hướng xuống): E, NE, N, NW, W, SW, S, SE.
const QPointF kDirs[8] = {QPointF(1, 0),  QPointF(1, -1), QPointF(0, -1), QPointF(-1, -1),
                          QPointF(-1, 0), QPointF(-1, 1), QPointF(0, 1),  QPointF(1, 1)};

/// Toạ độ giữa điểm ảnh: nét 1px (logic) nằm gọn trên lưới điểm ảnh ở cả dpr 1 và 2.
double crisp(double v) {
    return std::floor(v) + 0.5;
}

QColor with_alpha(QColor c, double a) {
    c.setAlphaF(static_cast<float>(std::clamp(a, 0.0, 1.0) * c.alphaF()));
    return c;
}

QColor series_color(const QString& mau, int idx) {
    const QString m = mau.trimmed();
    if (m.startsWith(QLatin1Char('#')) && QColor(m).isValid())
        return QColor(m);
    // Tên vai + tên cũ (bull/bear/info/warn/dim, good/bad/amb/neu) qua lk_role; lạ/thiếu → bảng màu theo thứ tự.
    const lkview::LkRole fallback = kPalette[static_cast<size_t>(std::max(idx, 0)) % std::size(kPalette)];
    return lk_col(lkview::lk_role(m.compare(QLatin1String("cyan"), Qt::CaseInsensitive) == 0 ? QStringLiteral("info") : m,
                                  fallback));
}

int quad_of(double x, double y) {
    if (x >= kCenter)
        return y >= kCenter ? Leading : Weakening;
    return y >= kCenter ? Improving : Lagging;
}

QString quad_vi(int q) {
    return q == Improving ? lk_tr("Cải thiện")
           : q == Leading ? lk_tr("Dẫn đầu")
           : q == Lagging ? lk_tr("Tụt hậu")
                          : lk_tr("Suy yếu");
}

QString quad_en(int q) {
    static const char* const kEn[4] = {"Improving", "Leading", "Lagging", "Weakening"};
    return QString(QLatin1String(kEn[std::clamp(q, 0, 3)]));
}

QString quad_name(int q) {
    return quad_vi(q) + QStringLiteral(" · ") + quad_en(q);
}

/// Nhãn góc script ghi ("Lagging", "tụt hậu", "LAGGING"…) → "Tụt hậu · Lagging"; chuỗi lạ giữ nguyên.
QString goc_display(const QString& goc) {
    const QString g = goc.trimmed();
    for (int q = 0; q < 4; ++q)
        if (g.compare(quad_en(q), Qt::CaseInsensitive) == 0 || g.compare(quad_vi(q), Qt::CaseInsensitive) == 0)
            return quad_name(q);
    return g;
}

QString fmt_date(const QString& s) {
    const QDate d = QDate::fromString(s.trimmed().left(10), Qt::ISODate);
    return d.isValid() ? d.toString(QStringLiteral("dd/MM/yyyy")) : s.trimmed();
}

/// Khung một trục. Có [min,max] hợp lệ → dùng làm cửa sổ tối thiểu, chỉ nới (kèm 5% đệm) phía có điểm nằm
/// ngoài — không bao giờ giấu số. Không có → [min(điểm, 100), max(điểm, 100)] rộng ít nhất kMinSpan, đệm 10%.
void axis_range(const QJsonValue& given, double dmin, double dmax, double* lo, double* hi) {
    const QJsonArray ga = given.toArray();
    double g0 = 0.0;
    double g1 = 0.0;
    if (ga.size() >= 2 && num_of(ga.at(0), &g0) && num_of(ga.at(1), &g1) && g1 > g0) {
        const double a = std::min(g0, dmin);
        const double b = std::max(g1, dmax);
        const double pad = kGivenPad * (b - a);
        *lo = dmin < g0 ? a - pad : a;
        *hi = dmax > g1 ? b + pad : b;
        return;
    }
    double a = std::min(dmin, kCenter);
    double b = std::max(dmax, kCenter);
    // Mỗi phía của 100 rộng ít nhất kMinSide phía kia — bốn góc luôn đủ chỗ cho tên góc (như Artifact: 86–104).
    const double need = kMinSide * std::max(kCenter - a, b - kCenter);
    a = std::min(a, kCenter - need);
    b = std::max(b, kCenter + need);
    if (b - a < kMinSpan) {
        const double c = (a + b) / 2.0;
        a = c - kMinSpan / 2.0;
        b = c + kMinSpan / 2.0;
    }
    const double pad = kAutoPad * (b - a);
    *lo = a - pad;
    *hi = b + pad;
}

/// Vạch "đẹp" (bước 1/2/5 × 10^k) trong [lo, hi]; dec = số chữ số thập phân cần cho bước đó.
QVector<double> make_ticks(double lo, double hi, int target, int* dec) {
    QVector<double> out;
    *dec = 0;
    const double span = hi - lo;
    if (!(span > 0.0) || !std::isfinite(span))
        return out;
    const double raw = span / std::max(target, 1);
    const double mag = std::pow(10.0, std::floor(std::log10(raw)));
    const double n = raw / mag;
    const double step = (n < 1.5 ? 1.0 : (n < 3.0 ? 2.0 : (n < 7.0 ? 5.0 : 10.0))) * mag;
    *dec = std::clamp(static_cast<int>(-std::floor(std::log10(step) + 1e-9)), 0, 4);
    const double k0 = std::ceil(lo / step - 1e-9);
    for (int i = 0; i < 64; ++i) {
        const double v = (k0 + i) * step;
        if (v > hi + step * 1e-9)
            break;
        out.append(v);
    }
    return out;
}

/// Hộp nhãn cách điểm p một khoảng gap theo hướng u (thành phần −1/0/1).
QRectF place_label(const QPointF& p, const QPointF& u, const QSizeF& sz, double gap) {
    const double g = u.x() != 0.0 && u.y() != 0.0 ? gap * 0.75 : gap; // hướng chéo: gần hơn chút
    const double left = u.x() > 0.0   ? p.x() + g
                        : u.x() < 0.0 ? p.x() - g - sz.width()
                                      : p.x() - sz.width() / 2.0;
    const double top = u.y() > 0.0   ? p.y() + g * 0.7
                       : u.y() < 0.0 ? p.y() - g * 0.7 - sz.height()
                                     : p.y() - sz.height() / 2.0;
    return QRectF(QPointF(left, top), sz);
}

QRectF clamp_into(QRectF r, const QRectF& box) {
    r.moveLeft(std::clamp(r.left(), box.left(), std::max(box.left(), box.right() - r.width())));
    r.moveTop(std::clamp(r.top(), box.top(), std::max(box.top(), box.bottom() - r.height())));
    return r;
}

/// Thứ tự hướng thử đặt nhãn: ưu tiên hướng đi tiếp của đuôi (nhãn nằm phía trước mũi tên, không đè đuôi);
/// không có hướng → phải, chéo phải, trên/dưới, trái.
QVector<int> dir_order(const QPointF& d) {
    QVector<int> ord{0, 1, 7, 2, 6, 4, 3, 5};
    if (d.isNull())
        return ord;
    const auto score = [&](int i) {
        const QPointF u = kDirs[i];
        return (u.x() * d.x() + u.y() * d.y()) / std::hypot(u.x(), u.y());
    };
    std::stable_sort(ord.begin(), ord.end(), [&](int a, int b) { return score(a) > score(b); });
    return ord;
}

/// Font của QLabel phải đi qua QSS (lk_font_css): QSS toàn cục "* { font-family; font-size }" đè setFont().
QLabel* text_label(const QString& text, const QFont& f, const QColor& c, QWidget* parent,
                   Qt::TextFormat fmt = Qt::PlainText) {
    auto* l = new QLabel(parent);
    l->setTextFormat(fmt);
    l->setText(text);
    l->setWordWrap(true);
    l->setTextInteractionFlags(Qt::TextSelectableByMouse);
    l->setStyleSheet(QStringLiteral("QLabel { color:%1; background:transparent; border:none; %2 }")
                         .arg(c.name(), lkview::lk_font_css(f)));
    return l;
}

} // namespace fincept::screens::langkinh::lkrrg

namespace fincept::screens::langkinh::lkview {

// ── LkRrgChart: dữ liệu + kích thước ──────────────────────────────────────────

LkRrgChart::LkRrgChart(const QJsonObject& block, const TickerFn& on_ticker, QWidget* parent)
    : QWidget(parent), on_ticker_(on_ticker) {
    using namespace lkrrg;
    setMouseTracking(true);
    QSizePolicy sp(QSizePolicy::Expanding, QSizePolicy::Preferred);
    sp.setHeightForWidth(true);
    setSizePolicy(sp);
    setMinimumSize(kMinW, kMinH);

    surface_ = lk_col("surface");
    line_ = lk_col("line");
    line2_ = lk_col("line2");
    ink2_ = lk_col("ink2");
    muted_ = lk_col("muted");
    quad_[Improving] = lk_col("blue");
    quad_[Leading] = lk_col("up");
    quad_[Lagging] = lk_col("down");
    quad_[Weakening] = lk_col("amber");
    soft_ = lk_is_light() ? 0.09 : 0.12; // ≈ *-soft của Artifact (.10 sáng / .13 tối), nhạt hơn chút vì phủ cả góc
    f_tick_ = lk_font_mono(10, 500);
    f_quad_ = lk_font_sans(10, 600);
    f_quad_.setLetterSpacing(QFont::AbsoluteSpacing, 0.6);
    f_quad_en_ = lk_font_mono(9, 500);
    f_label_ = lk_font_sans(11, 700);
    t_cuoi_ = fmt_date(text_opt(block.value(QStringLiteral("t_cuoi"))));

    double xmin = std::numeric_limits<double>::infinity();
    double xmax = -xmin;
    double ymin = xmin;
    double ymax = -xmin;
    const QJsonArray arr = block.value(QStringLiteral("series")).toArray();
    int idx = 0; // chỉ số trong JSON → màu mặc định ổn định kể cả khi có chuỗi bị bỏ
    for (const auto& sv : arr) {
        if (!sv.isObject())
            continue;
        const QJsonObject so = sv.toObject();
        Series s;
        s.ma = text_opt(so.value(QStringLiteral("ma")));
        s.color = series_color(so.value(QStringLiteral("mau")).toString(), idx++);
        s.goc = so.value(QStringLiteral("goc")).toString().trimmed();
        s.ghi = so.value(QStringLiteral("ghi")).toString().trimmed();
        const QJsonArray duoi = so.value(QStringLiteral("duoi")).toArray();
        for (const auto& pv : duoi) {
            const QJsonArray pa = pv.toArray();
            double x = 0.0;
            double y = 0.0;
            if (pa.size() >= 2 && num_of(pa.at(0), &x) && num_of(pa.at(1), &y))
                s.tail.append(QPointF(x, y));
        }
        if (s.tail.size() > kMaxTail)
            s.tail = s.tail.mid(s.tail.size() - kMaxTail); // giữ các tuần MỚI nhất
        if (s.tail.isEmpty()) {
            missing_.append(s.ma.isEmpty() ? dash() : s.ma);
            continue;
        }
        for (const QPointF& p : std::as_const(s.tail)) {
            xmin = std::min(xmin, p.x());
            xmax = std::max(xmax, p.x());
            ymin = std::min(ymin, p.y());
            ymax = std::max(ymax, p.y());
        }
        series_.append(s);
    }
    if (series_.isEmpty())
        return;
    axis_range(block.value(QStringLiteral("x_range")), xmin, xmax, &x0_, &x1_);
    axis_range(block.value(QStringLiteral("y_range")), ymin, ymax, &y0_, &y1_);
}

int LkRrgChart::max_tail() const {
    int n = 0;
    for (const Series& s : series_)
        n = std::max(n, static_cast<int>(s.tail.size()));
    return n;
}

int LkRrgChart::heightForWidth(int w) const {
    w = std::min(w, maximumWidth()); // QWidgetItem::heightForWidth không tự chặn theo maximumWidth
    return std::clamp(static_cast<int>(std::lround(w * static_cast<double>(lkrrg::kBaseH) / lkrrg::kBaseW)),
                      lkrrg::kMinH, lkrrg::kMaxH);
}

QSize LkRrgChart::sizeHint() const { // rộng = kMaxW: đặt canh giữa thì layout cấp min(khung, kMaxW)
    return {lkrrg::kMaxW, heightForWidth(lkrrg::kMaxW)};
}

QSize LkRrgChart::minimumSizeHint() const {
    return {lkrrg::kMinW, lkrrg::kMinH};
}

double LkRrgChart::px(double x) const {
    return plot_.left() + (x - x0_) / (x1_ - x0_) * plot_.width();
}

double LkRrgChart::py(double y) const {
    return plot_.bottom() - (y - y0_) / (y1_ - y0_) * plot_.height();
}

void LkRrgChart::ensure_layout() const {
    using namespace lkrrg;
    if (geo_size_ == size())
        return;
    geo_size_ = size();
    heads_.clear();

    // Vùng vẽ: lề trái vừa nhãn vạch dọc dài nhất; mép làm tròn nguyên để khung/lưới 1px sắc nét.
    const QFontMetricsF fm(f_tick_);
    const double bottom = 2.0 * fm.height() + 14.0; // hàng nhãn vạch ngang + hàng "RS-Ratio →"
    const double ph_est = height() - kMarginTop - bottom;
    yt_ = make_ticks(y0_, y1_, std::clamp(static_cast<int>(ph_est / 56.0), 3, 8), &ydec_);
    double lw = 0.0;
    for (const double v : std::as_const(yt_))
        lw = std::max(lw, fm.horizontalAdvance(vn_num(v, ydec_)));
    const double left = std::max(34.0, std::ceil(lw) + 12.0);
    plot_ = QRectF(QPointF(std::round(left), std::round(kMarginTop)),
                   QPointF(std::round(width() - kMarginRight), std::round(height() - bottom)));
    xt_ = make_ticks(x0_, x1_, std::clamp(static_cast<int>(plot_.width() / 84.0), 3, 10), &xdec_);
    if (plot_.width() < kPlotMin || plot_.height() < kPlotMin || series_.isEmpty())
        return;

    // Đuôi → toạ độ widget; hướng đoạn cuối = từ điểm KHÁC gần nhất phía trước tới điểm mới nhất.
    heads_.resize(series_.size());
    QVector<QRectF> occupied; // ô quanh mũi tên của mọi chuỗi — nhãn chuỗi khác không đè lên
    for (int s = 0; s < series_.size(); ++s) {
        Head& h = heads_[s];
        for (const QPointF& v : std::as_const(series_[s].tail))
            h.pts.append(QPointF(px(v.x()), py(v.y())));
        const QPointF last = h.pts.last();
        for (int k = static_cast<int>(h.pts.size()) - 2; k >= 0; --k) {
            const QPointF d = last - h.pts[k];
            const double len = std::hypot(d.x(), d.y());
            if (len >= 0.5) {
                h.dir = d / len;
                break;
            }
        }
        occupied.append(QRectF(last.x() - 9.0, last.y() - 9.0, 18.0, 18.0));
    }

    // Nhãn mã: hướng đầu tiên nằm trọn trong vùng vẽ và không đè mũi tên/nhãn chuỗi khác; hết chỗ → kẹp vào khung.
    const QFontMetricsF lm(f_label_);
    QVector<QRectF> placed;
    for (int s = 0; s < series_.size(); ++s) {
        Head& h = heads_[s];
        const QSizeF sz(lm.horizontalAdvance(series_[s].ma.isEmpty() ? dash() : series_[s].ma) + 4.0, lm.height());
        const QVector<int> ord = dir_order(h.dir);
        const QPointF at = h.pts.last();
        h.label = clamp_into(place_label(at, kDirs[ord.first()], sz, kLabelGap), plot_);
        for (const int i : ord) {
            const QRectF r = place_label(at, kDirs[i], sz, kLabelGap);
            bool clash = !plot_.contains(r) ||
                         std::any_of(placed.cbegin(), placed.cend(), [&](const QRectF& o) { return o.intersects(r); });
            for (int o = 0; o < occupied.size() && !clash; ++o)
                clash = o != s && occupied[o].intersects(r);
            if (!clash) {
                h.label = r;
                break;
            }
        }
        placed.append(h.label.adjusted(-2.0, -2.0, 2.0, 2.0));
    }
}

// ── Vẽ ────────────────────────────────────────────────────────────────────────

void LkRrgChart::paintEvent(QPaintEvent*) {
    ensure_layout();
    QPainter p(this);
    p.setRenderHint(QPainter::Antialiasing, true);
    p.setRenderHint(QPainter::TextAntialiasing, true);
    p.fillRect(rect(), surface_);
    if (series_.isEmpty() || heads_.size() != series_.size()) { // không có điểm hoặc quá hẹp
        p.setFont(f_tick_);
        p.setPen(muted_);
        p.drawText(rect(), Qt::AlignCenter, lkrrg::dash());
        return;
    }
    paint_frame(p);
    paint_axes(p);
    paint_series(p);
}

void LkRrgChart::paint_frame(QPainter& p) const {
    using namespace lkrrg;
    // Bốn góc tách tại 100/100 (kẹp vào vùng vẽ khi 100 nằm ngoài khung trục). Làm tròn về pixel nguyên: mép vùng tô
    // trùng mép nét tâm crisp(s) = s + 0,5 → không còn khe nửa tô dọc đường 100.
    const double sx = std::round(std::clamp(px(kCenter), plot_.left(), plot_.right()));
    const double sy = std::round(std::clamp(py(kCenter), plot_.top(), plot_.bottom()));
    const QRectF& pa = plot_;
    QRectF q[4];
    q[Improving] = QRectF(QPointF(pa.left(), pa.top()), QPointF(sx, sy));
    q[Leading] = QRectF(QPointF(sx, pa.top()), QPointF(pa.right(), sy));
    q[Lagging] = QRectF(QPointF(pa.left(), sy), QPointF(sx, pa.bottom()));
    q[Weakening] = QRectF(QPointF(sx, sy), QPointF(pa.right(), pa.bottom()));
    for (int i = 0; i < 4; ++i)
        if (q[i].width() > 0.5 && q[i].height() > 0.5)
            p.fillRect(q[i], with_alpha(quad_[i], soft_));

    // Lưới mảnh tại vạch (bỏ vạch 100 — nét tâm vẽ đậm hơn bên dưới).
    QPen grid(with_alpha(line_, 0.6), 1.0);
    grid.setCapStyle(Qt::FlatCap);
    p.setPen(grid);
    for (const double v : std::as_const(xt_)) {
        const double x = px(v);
        if (std::abs(v - kCenter) > 1e-9 && x > pa.left() + 1.0 && x < pa.right() - 1.0)
            p.drawLine(QPointF(crisp(x), pa.top()), QPointF(crisp(x), pa.bottom()));
    }
    for (const double v : std::as_const(yt_)) {
        const double y = py(v);
        if (std::abs(v - kCenter) > 1e-9 && y > pa.top() + 1.0 && y < pa.bottom() - 1.0)
            p.drawLine(QPointF(pa.left(), crisp(y)), QPointF(pa.right(), crisp(y)));
    }
    p.setPen(QPen(line_, 1.0, Qt::SolidLine, Qt::FlatCap, Qt::MiterJoin));
    p.setBrush(Qt::NoBrush);
    p.drawRect(pa.adjusted(0.5, 0.5, -0.5, -0.5));
    p.setPen(QPen(line2_, 1.0, Qt::SolidLine, Qt::FlatCap));
    if (kCenter > x0_ && kCenter < x1_)
        p.drawLine(QPointF(crisp(sx), pa.top()), QPointF(crisp(sx), pa.bottom()));
    if (kCenter > y0_ && kCenter < y1_)
        p.drawLine(QPointF(pa.left(), crisp(sy)), QPointF(pa.right(), crisp(sy)));

    // Tên góc ở góc ngoài: một dòng "DẪN ĐẦU · Leading"; góc hẹp → hai dòng; hẹp nữa → chỉ tên tiếng Việt.
    const QFontMetricsF mv(f_quad_);
    const QFontMetricsF me(f_quad_en_);
    const QString sep = QStringLiteral(" · ");
    for (int i = 0; i < 4; ++i) {
        const QRectF& r = q[i];
        if (r.width() < 28.0 || r.height() < 18.0)
            continue;
        const QString vi = quad_vi(i).toUpper();
        const QString en = quad_en(i);
        const double wv = mv.horizontalAdvance(vi);
        const double wen = me.horizontalAdvance(sep + en);
        const double avail = r.width() - 2.0 * kInset;
        const bool right = i == Leading || i == Weakening;
        const bool bottom = i == Lagging || i == Weakening;
        const auto x_for = [&](double w) { return right ? r.right() - kInset - w : r.left() + kInset; };
        const auto draw = [&](const QFont& f, const QColor& c, double x, double base, const QString& s) {
            p.setFont(f);
            p.setPen(c);
            p.drawText(QPointF(x, base), s);
        };
        const QColor cv = with_alpha(quad_[i], 0.95);
        if (wv + wen <= avail) {
            const double base = bottom ? r.bottom() - 7.0 - std::max(mv.descent(), me.descent())
                                       : r.top() + 6.0 + std::max(mv.ascent(), me.ascent());
            const double x = x_for(wv + wen);
            draw(f_quad_, cv, x, base, vi);
            draw(f_quad_en_, muted_, x + wv, base, sep + en);
        } else if (std::max(wv, me.horizontalAdvance(en)) <= avail && r.height() >= mv.height() + me.height() + 14.0) {
            const double y1 = bottom ? r.bottom() - 7.0 - me.descent() - me.ascent() - 2.0 - mv.descent()
                                     : r.top() + 6.0 + mv.ascent();
            draw(f_quad_, cv, x_for(wv), y1, vi);
            draw(f_quad_en_, muted_, x_for(me.horizontalAdvance(en)), y1 + mv.descent() + 2.0 + me.ascent(), en);
        } else if (wv <= avail) {
            draw(f_quad_, cv, x_for(wv), bottom ? r.bottom() - 7.0 - mv.descent() : r.top() + 6.0 + mv.ascent(), vi);
        }
    }
}

void LkRrgChart::paint_axes(QPainter& p) const {
    using namespace lkrrg;
    const QFontMetricsF fm(f_tick_);
    p.setFont(f_tick_);
    for (const double v : std::as_const(xt_)) {
        const double x = px(v);
        if (x < plot_.left() - 0.5 || x > plot_.right() + 0.5)
            continue;
        const QString s = vn_num(v, xdec_);
        const double w = fm.horizontalAdvance(s);
        p.setPen(std::abs(v - kCenter) < 1e-9 ? ink2_ : muted_);
        p.drawText(QPointF(std::clamp(x - w / 2.0, 0.0, std::max(0.0, width() - w)), plot_.bottom() + 5.0 + fm.ascent()),
                   s);
    }
    for (const double v : std::as_const(yt_)) {
        const double y = py(v);
        if (y < plot_.top() - 0.5 || y > plot_.bottom() + 0.5)
            continue;
        const QString s = vn_num(v, ydec_);
        p.setPen(std::abs(v - kCenter) < 1e-9 ? ink2_ : muted_);
        p.drawText(QPointF(plot_.left() - 7.0 - fm.horizontalAdvance(s), y + (fm.ascent() - fm.descent()) / 2.0), s);
    }
    p.setPen(muted_);
    const QString tx = QStringLiteral("RS-Ratio →");
    p.drawText(QPointF(plot_.right() - fm.horizontalAdvance(tx), plot_.bottom() + 9.0 + fm.height() + fm.ascent()), tx);
    p.drawText(QPointF(plot_.left(), plot_.top() - 8.0 - fm.descent()), QStringLiteral("RS-Momentum ↑"));
}

void LkRrgChart::paint_series(QPainter& p) const {
    using namespace lkrrg;
    QVector<int> order; // chuỗi đang rê vẽ sau cùng (nằm trên)
    for (int s = 0; s < series_.size(); ++s)
        if (s != hover_s_)
            order.append(s);
    if (hover_s_ >= 0 && hover_s_ < series_.size())
        order.append(hover_s_);
    const auto dim_of = [&](int s) { return hover_s_ >= 0 && hover_s_ != s ? kDim : 1.0; };

    // 1) Đuôi: đoạn cũ mảnh + nhạt, đoạn mới dày + đậm; chấm nhỏ ở các tuần cũ.
    p.save();
    p.setClipRect(plot_.adjusted(-1.0, -1.0, 1.0, 1.0));
    for (const int s : std::as_const(order)) {
        const QVector<QPointF>& pts = heads_[s].pts;
        const int n = static_cast<int>(pts.size());
        const QColor& c = series_[s].color;
        for (int i = 1; i < n; ++i) {
            const double t = static_cast<double>(i) / (n - 1);
            p.setPen(QPen(with_alpha(c, (0.22 + 0.78 * t) * dim_of(s)), 1.2 + 1.0 * t, Qt::SolidLine, Qt::RoundCap,
                          Qt::RoundJoin));
            p.drawLine(pts[i - 1], pts[i]);
        }
        p.setPen(Qt::NoPen);
        for (int i = 0; i + 1 < n; ++i) {
            const double t = static_cast<double>(i) / (n - 1);
            p.setBrush(with_alpha(c, (0.30 + 0.70 * t) * dim_of(s)));
            p.drawEllipse(pts[i], 1.8 + 0.9 * t, 1.8 + 0.9 * t);
        }
    }
    // Điểm cũ đang rê: vòng mảnh để biết tooltip thuộc điểm nào.
    if (hover_s_ >= 0 && hover_s_ < heads_.size() && hover_p_ >= 0 && hover_p_ + 1 < heads_[hover_s_].pts.size()) {
        p.setBrush(Qt::NoBrush);
        p.setPen(QPen(series_[hover_s_].color, 1.2));
        p.drawEllipse(heads_[hover_s_].pts[hover_p_], 5.0, 5.0);
    }
    p.restore();

    // 2) Mũi tên (hoặc chấm tròn khi chỉ có một điểm/đứng yên) + nhãn mã có viền màu nền (halo).
    const QFontMetricsF lm(f_label_);
    for (const int s : std::as_const(order)) {
        const Head& h = heads_[s];
        const QColor c = with_alpha(series_[s].color, dim_of(s));
        const QPointF at = h.pts.last();
        p.setPen(QPen(with_alpha(surface_, 0.95), 1.5, Qt::SolidLine, Qt::RoundCap, Qt::RoundJoin));
        p.setBrush(c);
        if (h.dir.isNull()) {
            p.drawEllipse(at, 5.5, 5.5);
        } else { // mũi vượt điểm 4px theo hướng tuần cuối
            const QPointF nrm(-h.dir.y(), h.dir.x());
            const QPointF base = at - h.dir * 8.0;
            QPolygonF tri;
            tri << at + h.dir * 4.0 << base + nrm * 5.5 << base - nrm * 5.5;
            p.drawPolygon(tri);
        }
        if (s == hover_s_ && hover_p_ == static_cast<int>(h.pts.size()) - 1 && on_ticker_ &&
            !series_[s].ma.isEmpty()) { // vòng báo "bấm được"
            p.setBrush(Qt::NoBrush);
            p.setPen(QPen(with_alpha(series_[s].color, 0.55), 1.0));
            p.drawEllipse(at, 10.5, 10.5);
        }
        QPainterPath tp;
        tp.addText(QPointF(h.label.left() + 2.0, h.label.top() + lm.ascent()), f_label_,
                   series_[s].ma.isEmpty() ? dash() : series_[s].ma);
        p.setBrush(Qt::NoBrush);
        p.strokePath(tp, QPen(with_alpha(surface_, 0.9), 3.0, Qt::SolidLine, Qt::RoundCap, Qt::RoundJoin));
        p.fillPath(tp, c);
    }
}

// ── Chuột ─────────────────────────────────────────────────────────────────────

int LkRrgChart::hit(const QPointF& pos, int* pi, bool heads_only) const {
    ensure_layout();
    if (series_.isEmpty() || heads_.size() != series_.size())
        return -1;
    int best = -1;
    double bd = lkrrg::kHeadHit;
    for (int s = 0; s < heads_.size(); ++s) { // mũi tên gần nhất
        const double d = QLineF(pos, heads_[s].pts.last()).length();
        if (d <= bd) {
            bd = d;
            best = s;
        }
    }
    for (int s = 0; s < heads_.size() && best < 0; ++s) // rồi nhãn mã
        if (heads_[s].label.adjusted(-2.0, -2.0, 2.0, 2.0).contains(pos))
            best = s;
    if (best >= 0) {
        *pi = static_cast<int>(heads_[best].pts.size()) - 1;
        return best;
    }
    if (heads_only)
        return -1;
    bd = lkrrg::kPointHit;
    for (int s = 0; s < heads_.size(); ++s)
        for (int i = 0; i < heads_[s].pts.size(); ++i) {
            const double d = QLineF(pos, heads_[s].pts[i]).length();
            if (d <= bd) {
                bd = d;
                best = s;
                *pi = i;
            }
        }
    return best;
}

QString LkRrgChart::tooltip_for(int si, int pi) const {
    using namespace lkrrg;
    const Series& s = series_[si];
    const QPointF v = s.tail[pi];
    const int n = static_cast<int>(s.tail.size());
    const bool head = pi == n - 1;
    QString t = QStringLiteral("<b><span style='color:%1'>■</span> %2</b> · ")
                    .arg(s.color.name(), s.ma.isEmpty() ? dash() : s.ma.toHtmlEscaped());
    if (head)
        t += t_cuoi_.isEmpty() ? lk_tr("tuần mới nhất") : lk_tr("tuần mới nhất (%1)").arg(t_cuoi_.toHtmlEscaped());
    else
        t += lk_tr("%1 tuần trước điểm mới nhất").arg(n - 1 - pi);
    t += QStringLiteral("<br>RS-Ratio: %1<br>RS-Momentum: %2").arg(vn_num(v.x(), 2), vn_num(v.y(), 2));
    t += QStringLiteral("<br>") + lk_tr("Góc: %1").arg(quad_name(quad_of(v.x(), v.y())).toHtmlEscaped());
    if (head && on_ticker_ && !s.ma.isEmpty())
        t += QStringLiteral("<br><i>") + lk_tr("Bấm để mở mã %1").arg(s.ma.toHtmlEscaped()) + QStringLiteral("</i>");
    return t;
}

void LkRrgChart::mouseMoveEvent(QMouseEvent* event) {
    QWidget::mouseMoveEvent(event);
    int pi = -1;
    const int si = hit(event->position(), &pi, false);
    if (si < 0) {
        if (hover_s_ >= 0) {
            hover_s_ = -1;
            hover_p_ = -1;
            QToolTip::hideText();
            unsetCursor();
            update();
        }
        return;
    }
    if (si == hover_s_ && pi == hover_p_)
        return;
    hover_s_ = si;
    hover_p_ = pi;
    const bool head = pi == static_cast<int>(series_[si].tail.size()) - 1;
    setCursor(head && on_ticker_ && !series_[si].ma.isEmpty() ? Qt::PointingHandCursor : Qt::ArrowCursor);
    QToolTip::showText(event->globalPosition().toPoint(), tooltip_for(si, pi), this);
    update();
}

void LkRrgChart::mousePressEvent(QMouseEvent* event) {
    int pi = -1;
    press_s_ = event->button() == Qt::LeftButton ? hit(event->position(), &pi, true) : -1;
    if (press_s_ >= 0)
        event->accept();
    else
        QWidget::mousePressEvent(event);
}

void LkRrgChart::mouseReleaseEvent(QMouseEvent* event) {
    const int pressed = press_s_;
    press_s_ = -1;
    int pi = -1;
    if (event->button() != Qt::LeftButton || pressed < 0 || hit(event->position(), &pi, true) != pressed) {
        QWidget::mouseReleaseEvent(event);
        return;
    }
    event->accept();
    const QString ma = series_[pressed].ma;
    if (ma.isEmpty() || !on_ticker_)
        return;
    QToolTip::hideText();
    const TickerFn fn = on_ticker_; // bản sao: callback có thể dựng lại trang (widget này bị deleteLater)
    fn(ma);
}

void LkRrgChart::leaveEvent(QEvent* event) {
    QToolTip::hideText();
    press_s_ = -1;
    hover_s_ = -1;
    hover_p_ = -1;
    unsetCursor();
    update();
    QWidget::leaveEvent(event);
}

// ── make_rrg: thẻ = đầu (tiêu đề + chip bậc) · phụ đề · biểu đồ · chú giải · chú thích ──

QWidget* make_rrg(const QJsonObject& b, QWidget* parent, const TickerFn& on_ticker) {
    using namespace lkrrg;
    auto* card = new QFrame(parent);
    card->setObjectName(QStringLiteral("lkRrgCard"));
    card->setStyleSheet(QStringLiteral("QFrame#lkRrgCard { background:%1; border:1px solid %2; border-radius:10px; }")
                            .arg(lk_col("surface").name(), lk_col("line").name()));
    auto* vl = new QVBoxLayout(card);
    vl->setContentsMargins(14, 12, 14, 10);
    vl->setSpacing(6);

    lk_add_head(vl, b, card); // title + tag bậc `b` (LkTag, cùng hình với tag các block khác) + sub html-lite

    auto* chart = new LkRrgChart(b, on_ticker, card);
    const QStringList missing = chart->missing();
    const QString miss_line = missing.isEmpty()
                                  ? QString()
                                  : QStringLiteral("<span style='color:%1'>[CẦN DATA]</span> %2 — %3")
                                        .arg(lk_col("down").name(), missing.join(QStringLiteral(", ")).toHtmlEscaped(),
                                             lk_tr("không có điểm đuôi hợp lệ").toHtmlEscaped());
    if (!chart->has_data()) {
        delete chart;
        const QString msg = miss_line.isEmpty() ? lk_tr("— không có điểm RRG hợp lệ để vẽ —").toHtmlEscaped() : miss_line;
        vl->addWidget(text_label(msg, lk_font_sans(12, 400), lk_col("muted"), card, Qt::RichText));
        return card;
    }
    // Khung giữ tỉ lệ 640×420 của Artifact: trang rộng thì biểu đồ ≤ 975×640, canh giữa (không bẹt đuôi).
    chart->setMaximumWidth(kMaxW);
    vl->addWidget(chart, 0, Qt::AlignHCenter);

    // Chú giải: nét màu · mã · góc (script ghi sẵn thì dùng, không thì tính từ điểm mới nhất) · ghi chú.
    const QString ink = lk_col("ink").name();
    QStringList items;
    for (const LkRrgChart::Series& s : chart->series()) {
        const QPointF last = s.tail.last();
        const QString goc = s.goc.isEmpty() ? quad_name(quad_of(last.x(), last.y())) : goc_display(s.goc);
        QString it = QStringLiteral("<span style='color:%1'>━━</span>&nbsp;<span style='color:%2; font-weight:600'>%3"
                                    "</span> · %4")
                         .arg(s.color.name(), ink, (s.ma.isEmpty() ? dash() : s.ma).toHtmlEscaped(), goc.toHtmlEscaped());
        if (!s.ghi.isEmpty())
            it += QStringLiteral(" · ") + s.ghi.toHtmlEscaped();
        items << it;
    }
    if (!miss_line.isEmpty())
        items << miss_line;
    vl->addWidget(text_label(items.join(QStringLiteral("&nbsp;&nbsp;&nbsp; ")), lk_font_sans(12, 400), lk_col("ink2"),
                             card, Qt::RichText));

    QString cap = lk_tr("Tâm 100/100 · đuôi %1 tuần, nhạt = cũ, mũi tên = tuần mới nhất").arg(chart->max_tail());
    if (!chart->t_cuoi().isEmpty())
        cap += QStringLiteral(" (") + chart->t_cuoi() + QStringLiteral(")");
    cap += QStringLiteral(" · ") + (on_ticker ? lk_tr("rê chuột xem số, bấm mũi tên để mở mã") : lk_tr("rê chuột xem số"));
    vl->addWidget(text_label(cap, lk_font_sans(11, 400), lk_col("muted"), card));
    return card;
}

} // namespace fincept::screens::langkinh::lkview
