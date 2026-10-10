// src/screens/markets/PriceHistoryDialog.cpp — xem PriceHistoryDialog.h.
#include "screens/markets/PriceHistoryDialog.h"

#include "datahub/DataHub.h"
#include "datahub/DataHubMetaTypes.h"
#include "screens/dashboard/widgets/DashboardCandleWidget.h"

#include <QDateTime>
#include <QHBoxLayout>
#include <QLabel>
#include <QMouseEvent>
#include <QPainter>
#include <QPainterPath>
#include <QPushButton>
#include <QStackedWidget>
#include <QTimer>
#include <QVBoxLayout>

#include <algorithm>
#include <cmath>

namespace fincept::screens {

namespace {

struct Ky {
    const char* nhan;
    const char* period;
    const char* interval;
};
// Chỉ những kỳ cả yfinance lẫn nhánh VN (yfinance_data._VN_PERIOD_NGAY) cùng hiểu.
const Ky kKy[] = {{"1T", "1mo", "1d"},  {"3T", "3mo", "1d"},  {"6T", "6mo", "1d"},
                  {"YTD", "ytd", "1d"}, {"1N", "1y", "1d"},   {"2N", "2y", "1wk"},
                  {"5N", "5y", "1wk"},  {"MAX", "max", "1mo"}};
constexpr int kSoKy = int(sizeof(kKy) / sizeof(kKy[0]));

constexpr const char* kBg = "#080c14";
constexpr const char* kGrid = "#1e293b";
constexpr const char* kAxis = "#64748b";
constexpr const char* kUp = "#22c55e";
constexpr const char* kDown = "#ef4444";
constexpr const char* kAccent = "#f59e0b";

QString so(double v, int nd) {
    return QLocale(QLocale::Vietnamese).toString(v, 'f', nd);
}

int so_le(double v) {
    const double a = std::abs(v);
    if (a >= 1000) return 0;
    if (a >= 10) return 2;
    return a >= 1 ? 2 : 4;
}

} // namespace

// ───────────────────────────── HistoryLineCanvas ─────────────────────────────

HistoryLineCanvas::HistoryLineCanvas(QWidget* parent) : QWidget(parent) {
    setMouseTracking(true);
    setMinimumSize(560, 300);
    setAttribute(Qt::WA_OpaquePaintEvent);
}

void HistoryLineCanvas::set_points(const QVector<services::HistoryPoint>& pts, bool is_yield) {
    pts_ = pts;
    is_yield_ = is_yield;
    hover_ = -1;
    dirty_ = true;
    update();
}

void HistoryLineCanvas::clear() {
    pts_.clear();
    hover_ = -1;
    dirty_ = true;
    update();
}

QRect HistoryLineCanvas::plot_rect() const {
    return QRect(10, 10, width() - kAxisW - 14, height() - kAxisH - 16);
}

QString HistoryLineCanvas::fmt(double v) const {
    return is_yield_ ? so(v, 3) + "%" : so(v, so_le(v));
}

void HistoryLineCanvas::resizeEvent(QResizeEvent* e) {
    dirty_ = true;
    QWidget::resizeEvent(e);
}

void HistoryLineCanvas::rebuild_cache() {
    cache_ = QPixmap(size() * devicePixelRatioF());
    cache_.setDevicePixelRatio(devicePixelRatioF());
    cache_.fill(QColor(kBg));
    dirty_ = false;

    QPainter p(&cache_);
    p.setRenderHint(QPainter::Antialiasing, true);
    const QRect r = plot_rect();

    if (pts_.size() < 2) {
        p.setPen(QColor(kAxis));
        p.drawText(rect(), Qt::AlignCenter,
                   pts_.isEmpty() ? tr("Chưa có dữ liệu") : tr("Chỉ có 1 điểm — không vẽ được đường"));
        return;
    }

    lo_ = pts_.first().close;
    hi_ = lo_;
    for (const auto& x : pts_) {
        lo_ = std::min(lo_, x.close);
        hi_ = std::max(hi_, x.close);
    }
    if (hi_ - lo_ < 1e-12) {
        hi_ += 1;
        lo_ -= 1;
    }
    const double pad = (hi_ - lo_) * 0.06;
    lo_ -= pad;
    hi_ += pad;

    auto X = [&](int i) { return r.left() + r.width() * double(i) / double(pts_.size() - 1); };
    auto Y = [&](double v) { return r.bottom() - r.height() * (v - lo_) / (hi_ - lo_); };

    // Lưới + trục giá (5 mức)
    QFont f = font();
    f.setPointSizeF(9);
    p.setFont(f);
    for (int k = 0; k <= 4; ++k) {
        const double v = lo_ + (hi_ - lo_) * k / 4.0;
        const int y = int(Y(v));
        p.setPen(QPen(QColor(kGrid), 1, Qt::DotLine));
        p.drawLine(r.left(), y, r.right(), y);
        p.setPen(QColor(kAxis));
        p.drawText(QRect(r.right() + 6, y - 8, kAxisW, 16), Qt::AlignLeft | Qt::AlignVCenter, fmt(v));
    }

    // Trục thời gian (5 mốc)
    const bool nhieu_nam = (pts_.last().timestamp - pts_.first().timestamp) > 400LL * 86400;
    for (int k = 0; k <= 4; ++k) {
        const int i = int(std::round((pts_.size() - 1) * k / 4.0));
        const QDateTime d = QDateTime::fromSecsSinceEpoch(pts_[i].timestamp);
        const QString s = d.toString(nhieu_nam ? "MM/yyyy" : "dd/MM/yy");
        const int x = int(X(i));
        p.setPen(QColor(kAxis));
        p.drawText(QRect(x - 40, r.bottom() + 4, 80, kAxisH), Qt::AlignHCenter | Qt::AlignTop, s);
    }

    // Màu theo CHIỀU cả kỳ. Với lợi suất, lên là giá trái phiếu xuống — vẫn tô theo chiều của
    // chính con số đang vẽ, vì đó là thứ mắt đọc; nghĩa kinh tế ghi ở dòng chú thích.
    const bool len = pts_.last().close >= pts_.first().close;
    const QColor c(len ? kUp : kDown);

    QPainterPath line;
    line.moveTo(X(0), Y(pts_[0].close));
    for (int i = 1; i < pts_.size(); ++i)
        line.lineTo(X(i), Y(pts_[i].close));

    QPainterPath area = line;
    area.lineTo(X(pts_.size() - 1), r.bottom());
    area.lineTo(X(0), r.bottom());
    area.closeSubpath();
    QLinearGradient g(0, r.top(), 0, r.bottom());
    QColor c1 = c;
    c1.setAlpha(70);
    QColor c2 = c;
    c2.setAlpha(0);
    g.setColorAt(0, c1);
    g.setColorAt(1, c2);
    p.fillPath(area, g);

    p.setPen(QPen(c, 1.6));
    p.drawPath(line);

    // Mức cuối kỳ: vạch ngang đứt + nhãn trên trục giá
    const double last = pts_.last().close;
    p.setPen(QPen(QColor(kAccent), 1, Qt::DashLine));
    p.drawLine(r.left(), int(Y(last)), r.right(), int(Y(last)));
    p.fillRect(QRect(r.right() + 2, int(Y(last)) - 9, kAxisW - 4, 18), QColor(kAccent));
    p.setPen(QColor("#0b0f17"));
    p.drawText(QRect(r.right() + 6, int(Y(last)) - 9, kAxisW - 8, 18), Qt::AlignLeft | Qt::AlignVCenter,
               fmt(last));
}

void HistoryLineCanvas::paintEvent(QPaintEvent*) {
    if (dirty_ || cache_.size() != size() * devicePixelRatioF())
        rebuild_cache();
    QPainter p(this);
    p.drawPixmap(0, 0, cache_);

    if (hover_ < 0 || hover_ >= pts_.size() || pts_.size() < 2)
        return;
    const QRect r = plot_rect();
    const double x = r.left() + r.width() * double(hover_) / double(pts_.size() - 1);
    const double y = r.bottom() - r.height() * (pts_[hover_].close - lo_) / (hi_ - lo_);

    p.setRenderHint(QPainter::Antialiasing, true);
    p.setPen(QPen(QColor(kAxis), 1, Qt::DashLine));
    p.drawLine(QPointF(x, r.top()), QPointF(x, r.bottom()));
    p.setBrush(QColor(kAccent));
    p.setPen(Qt::NoPen);
    p.drawEllipse(QPointF(x, y), 3.5, 3.5);

    const auto& h = pts_[hover_];
    const QString d = QDateTime::fromSecsSinceEpoch(h.timestamp).toString("dd/MM/yyyy");
    const double doi = h.close - pts_.first().close;
    const QString dong2 = is_yield_
                              ? QString("%1 điểm % so đầu kỳ").arg(so(doi, 3))
                              : QString("%1% so đầu kỳ")
                                    .arg(so(pts_.first().close ? doi / pts_.first().close * 100 : 0, 2));
    const QString txt = QString("%1\n%2\n%3").arg(d, fmt(h.close), dong2);

    QFont f = font();
    f.setPointSizeF(9.5);
    p.setFont(f);
    const QRect box = p.fontMetrics().boundingRect(QRect(0, 0, 240, 80), Qt::AlignLeft, txt).adjusted(-8, -6, 8, 6);
    QRect b = box.translated(int(x) + 12 - box.left(), r.top() + 6 - box.top());
    if (b.right() > r.right())
        b.moveRight(int(x) - 12);
    p.fillRect(b, QColor(15, 23, 42, 235));
    p.setPen(QColor(kGrid));
    p.drawRect(b);
    p.setPen(QColor("#e2e8f0"));
    p.drawText(b.adjusted(8, 6, -8, -6), Qt::AlignLeft, txt);
}

void HistoryLineCanvas::mouseMoveEvent(QMouseEvent* e) {
    if (pts_.size() < 2)
        return;
    const QRect r = plot_rect();
    const double t = std::clamp((e->position().x() - r.left()) / double(std::max(1, r.width())), 0.0, 1.0);
    const int i = int(std::round(t * (pts_.size() - 1)));
    if (i != hover_) {
        hover_ = i;
        update();
    }
}

void HistoryLineCanvas::leaveEvent(QEvent* e) {
    hover_ = -1;
    update();
    QWidget::leaveEvent(e);
}

// ───────────────────────────── PriceHistoryDialog ─────────────────────────────

bool PriceHistoryDialog::is_yield_symbol(const QString& s) {
    static const QStringList yf = {"^TNX", "^TYX", "^IRX", "^FVX"};
    return yf.contains(s.toUpper()) || s.toUpper().startsWith("VNGB");
}

PriceHistoryDialog::PriceHistoryDialog(const QString& symbol, const QString& display_name, QWidget* parent)
    : QDialog(parent), symbol_(symbol), name_(display_name.isEmpty() ? symbol : display_name) {
    is_yield_ = is_yield_symbol(symbol_);
    setAttribute(Qt::WA_DeleteOnClose);
    setWindowTitle(QString("%1 · %2").arg(name_, symbol_));
    resize(980, 560);
    build_ui();

    timeout_ = new QTimer(this);
    timeout_->setSingleShot(true);
    timeout_->setInterval(25000);
    connect(timeout_, &QTimer::timeout, this, [this]() {
        if (pts_.isEmpty())
            note_->setText(tr("Không nhận được dữ liệu sau 25 giây — nguồn có thể không có lịch sử cho "
                              "mã %1 ở kỳ này. Thử kỳ khác.")
                               .arg(symbol_));
    });
}

PriceHistoryDialog::~PriceHistoryDialog() {
    if (hub_active_)
        datahub::DataHub::instance().unsubscribe(this);
}

void PriceHistoryDialog::build_ui() {
    setStyleSheet(QString("QDialog{background:%1;} QLabel{color:#e2e8f0;}").arg(kBg));
    auto* v = new QVBoxLayout(this);
    v->setContentsMargins(14, 12, 14, 12);
    v->setSpacing(8);

    auto* top = new QHBoxLayout;
    title_ = new QLabel(QString("%1  <span style='color:#64748b'>%2</span>").arg(name_.toHtmlEscaped(),
                                                                               symbol_.toHtmlEscaped()));
    title_->setTextFormat(Qt::RichText);
    title_->setStyleSheet("font-size:15px; font-weight:800;");
    top->addWidget(title_);
    top->addStretch(1);
    last_ = new QLabel("—");
    last_->setStyleSheet("font-size:20px; font-weight:800; font-family:'JetBrains Mono','SF Mono',monospace;");
    top->addWidget(last_);
    chg_ = new QLabel;
    chg_->setStyleSheet("font-size:13px; font-weight:700; padding-left:10px;");
    top->addWidget(chg_);
    v->addLayout(top);

    auto* bar = new QHBoxLayout;
    bar->setSpacing(4);
    for (int i = 0; i < kSoKy; ++i) {
        auto* b = new QPushButton(QString::fromUtf8(kKy[i].nhan));
        b->setCheckable(true);
        b->setCursor(Qt::PointingHandCursor);
        b->setFixedHeight(24);
        b->setStyleSheet("QPushButton{background:#0d1420;color:#94a3b8;border:1px solid #1e293b;"
                         "padding:0 10px;font-weight:700;}"
                         "QPushButton:checked{background:#f59e0b;color:#0b0f17;border-color:#f59e0b;}"
                         "QPushButton:hover{border-color:#f59e0b;}");
        connect(b, &QPushButton::clicked, this, [this, i]() { select_range(i); });
        range_btns_.append(b);
        bar->addWidget(b);
    }
    bar->addSpacing(16);
    kind_btn_ = new QPushButton(tr("NẾN"));
    kind_btn_->setCheckable(true);
    kind_btn_->setCursor(Qt::PointingHandCursor);
    kind_btn_->setFixedHeight(24);
    kind_btn_->setStyleSheet(range_btns_.first()->styleSheet());
    kind_btn_->setToolTip(tr("Đổi giữa đường giá đóng cửa và nến OHLC"));
    connect(kind_btn_, &QPushButton::toggled, this, [this](bool on) { stack_->setCurrentIndex(on ? 1 : 0); });
    bar->addWidget(kind_btn_);
    bar->addStretch(1);
    hilo_ = new QLabel;
    hilo_->setStyleSheet("color:#94a3b8; font-size:11px;");
    bar->addWidget(hilo_);
    v->addLayout(bar);

    stack_ = new QStackedWidget;
    line_ = new HistoryLineCanvas;
    candle_ = new widgets::CandleCanvas;
    stack_->addWidget(line_);
    stack_->addWidget(candle_);
    v->addWidget(stack_, 1);

    note_ = new QLabel;
    note_->setWordWrap(true);
    note_->setStyleSheet("color:#64748b; font-size:10px;");
    v->addWidget(note_);

    // Lợi suất không có nến có nghĩa với nhiều nguồn (mở = đóng) — mặc định đường.
    range_btns_[range_idx_]->setChecked(true);
}

QString PriceHistoryDialog::topic() const {
    return QStringLiteral("market:history:") + symbol_ + QLatin1Char(':') + kKy[range_idx_].period +
           QLatin1Char(':') + kKy[range_idx_].interval;
}

void PriceHistoryDialog::select_range(int idx) {
    range_idx_ = idx;
    for (int i = 0; i < range_btns_.size(); ++i)
        range_btns_[i]->setChecked(i == idx);
    pts_.clear();
    line_->clear();
    candle_->clear();
    last_->setText("…");
    chg_->clear();
    hilo_->clear();
    note_->setText(tr("Đang nạp %1 · %2…").arg(symbol_, QString::fromUtf8(kKy[idx].nhan)));
    subscribe();
}

void PriceHistoryDialog::subscribe() {
    auto& hub = datahub::DataHub::instance();
    hub.unsubscribe(this);
    hub.subscribe<QVector<services::HistoryPoint>>(
        this, topic(), [this](const QVector<services::HistoryPoint>& pts) { on_points(pts); });
    hub_active_ = true;
    hub.request(topic(), /*force=*/true);
    timeout_->start();
}

void PriceHistoryDialog::on_points(const QVector<services::HistoryPoint>& in) {
    // Bỏ nến rỗng (close ≤ 0) — nguồn đôi khi trả phiên nghỉ với toàn số 0, vẽ vào là một vực
    // thẳng đứng về 0 mà người đọc sẽ tưởng là sập giá.
    QVector<services::HistoryPoint> pts;
    pts.reserve(in.size());
    for (const auto& x : in) {
        if (x.close > 0 && x.timestamp > 0)
            pts.append(x);
    }
    std::sort(pts.begin(), pts.end(), [](const auto& a, const auto& b) { return a.timestamp < b.timestamp; });
    pts_ = pts;
    timeout_->stop();
    line_->set_points(pts_, is_yield_);
    candle_->set_candles(pts_);
    update_stats();
}

void PriceHistoryDialog::update_stats() {
    if (pts_.isEmpty()) {
        note_->setText(tr("Nguồn trả về rỗng cho %1 ở kỳ này.").arg(symbol_));
        return;
    }
    const double dau = pts_.first().close;
    const double cuoi = pts_.last().close;
    double hi = cuoi, lo = cuoi;
    for (const auto& x : pts_) {
        hi = std::max(hi, x.high > 0 ? x.high : x.close);
        lo = std::min(lo, x.low > 0 ? x.low : x.close);
    }
    const int nd = is_yield_ ? 3 : so_le(cuoi);
    last_->setText(so(cuoi, nd) + (is_yield_ ? "%" : ""));

    const double doi = cuoi - dau;
    const bool len = doi >= 0;
    const QString mau = len ? kUp : kDown;
    const QString mui = len ? QStringLiteral("▲") : QStringLiteral("▼");
    // Lợi suất đo thay đổi bằng ĐIỂM %, không bằng %: 4,0% → 4,4% là +40 điểm cơ bản, không
    // phải +10%. In % ở đây sẽ phóng đại gấp chục lần.
    chg_->setText(is_yield_ ? QString("%1 %2 điểm % (%3 bp)")
                                  .arg(mui, so(doi, 3))
                                  .arg(qRound(doi * 100))
                            : QString("%1 %2  (%3%)").arg(mui, so(doi, nd), so(dau ? doi / dau * 100 : 0, 2)));
    chg_->setStyleSheet(QString("font-size:13px; font-weight:700; padding-left:10px; color:%1;").arg(mau));

    const auto d0 = QDateTime::fromSecsSinceEpoch(pts_.first().timestamp).toString("dd/MM/yyyy");
    const auto d1 = QDateTime::fromSecsSinceEpoch(pts_.last().timestamp).toString("dd/MM/yyyy");
    hilo_->setText(tr("CAO %1 · THẤP %2 · %3 → %4 · %5 điểm")
                       .arg(so(hi, nd), so(lo, nd), d0, d1)
                       .arg(pts_.size()));
    note_->setText(is_yield_
                       ? tr("Lợi suất tăng nghĩa là GIÁ trái phiếu giảm. Nguồn: MarketDataService → "
                            "yfinance_data.py.")
                       : tr("Nguồn: MarketDataService → yfinance_data.py. Mã Việt Nam dùng chuỗi đã điều "
                            "chỉnh quyền (cổ tức, thưởng) nên mức giá cũ có thể khác bảng điện."));
}

void PriceHistoryDialog::showEvent(QShowEvent* e) {
    QDialog::showEvent(e);
    if (!hub_active_)
        select_range(range_idx_);
}

void PriceHistoryDialog::hideEvent(QHideEvent* e) {
    QDialog::hideEvent(e);
    if (hub_active_) {
        datahub::DataHub::instance().unsubscribe(this);
        hub_active_ = false;
    }
}

} // namespace fincept::screens
