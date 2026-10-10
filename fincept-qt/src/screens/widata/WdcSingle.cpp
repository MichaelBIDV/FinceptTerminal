// WdcSingle.cpp, package F: chart page (DESIGN §16 C4). Geometry: capture vimo mainDom (layout_const
// single_charts[0].page, F_plan_expanded_single §2.2); behaviour: F_plan §2.3; tokens: WdcTheme_p.h, HOVER_CSS.md.
#include "screens/widata/WdcSingle.h"

#include "screens/widata/WdcExpanded.h"
#include "screens/widata/WdcIcons_p.h"
#include "screens/widata/WdcLegend.h"
#include "screens/widata/WdcTheme_p.h"
#include "screens/widata/WdcTooltip.h"
#include "screens/widata/WdcView.h"

#include <QClipboard>
#include <QDir>
#include <QFileDialog>
#include <QFutureWatcher>
#include <QGuiApplication>
#include <QKeyEvent>
#include <QMetaMethod>
#include <QMouseEvent>
#include <QPainter>
#include <QPainterPath>
#include <QRegularExpression>
#include <QTimer>
#include <QtConcurrent/QtConcurrentRun>

#include <algorithm>
#include <cmath>

namespace fincept::screens::wdc {

namespace th = theme;

namespace {

// capture vimo mainDom (CSS px)
constexpr double kHeaderH = 32, kTitlePx = 16, kTitleLineH = 24, kTitleGap = 8;
constexpr int kTitleWeight = 500;
constexpr double kActPad = 4, kActGap = 4, kBtnH = 24, kBtnPadX = 8, kIconGap = 4, kBtnPx = 13;
constexpr double kBtnLineH = 13.0 * 12.0 / 7.0;   // 22.2857
constexpr int kBtnWeight = 500;
constexpr double kCalBox = 28, kCalPad = 2, kCalIcon = 20, kDivMargin = 8, kRangeH = 28, kRangeGap = 4, kRowGap = 12;
constexpr double kLegendH = 36, kLegendMargin = 0.05, kBottomPad = 10, kRadius = 4;
constexpr double kPaneDivTop = 12, kPaneDivBottom = 8;    // between the panes of a 2-pane card, as WdcExpanded (MẶC ĐỊNH)
constexpr double kCapW = 812.47, kCapChartH = 391.34;     // chart column and chart box of the capture
constexpr double kMinChartH = 120;                        // floor when the frame is very short (MẶC ĐỊNH)
constexpr int kTipDelayMs = 500, kCopiedTipMs = 1500;
const QColor kDisabledFg(166, 176, 195, 204);   // HOVER_CSS.md: .Mui-disabled rgba(166,176,195,.8)

struct WdcsgAction { const char* id; const char* text; Icon icon; double iconPx; };
const WdcsgAction kActions[] = {{"compare", "So sánh biến động", Icon::Percent, 18},
                                {"copy_link", "Sao chép liên kết", Icon::InsertLinkRounded, 18},
                                {"customize", "Tuỳ chỉnh", Icon::Settings, 18},
                                {"download", "Tải về", Icon::FileDownloadOutlined, 20},
                                {"fullscreen", "", Icon::Fullscreen, 18}};

double wdcsg_lu(double css, double s) { return std::floor(css * s + 1e-9) / s; }
double wdcsg_luText(double css, double s) { return std::ceil(css * s - 1e-7) / s; }

QPainterPath wdcsg_round(const QRectF& r, double radius) {
    QPainterPath p;
    p.addRoundedRect(r, std::min(radius, r.width() / 2), std::min(radius, r.height() / 2));
    return p;
}

const std::vector<ShadowLayer>& wdcsg_hoverShadow() {   // card cluster rule of HOVER_CSS.md, applied by analogy
    static const std::vector<ShadowLayer> v = {{0, 0, 6, 0, QColor(33, 35, 46, 15)}};
    return v;
}

QString wdcsg_fileName(const QString& title) {
    QString t = th::displayName(title);
    t.replace(QRegularExpression(QStringLiteral("[/\\\\:*?\"<>|]")), QStringLiteral("_"));
    return (t.isEmpty() ? QStringLiteral("widata_chart") : t) + QStringLiteral(".png");
}

} // namespace

// ---- geometry ------------------------------------------------------------------------------------------------------

SingleGeom layoutSingle(double W, double dpr, const QString& title, MetricsProfile profile, double chartH, int panes) {
    const double s = 64.0 * (profile == MetricsProfile::WidataDpr18 ? 1.8 : (dpr > 0 ? dpr : 1.0));
    auto lu = [s](double v) { return wdcsg_lu(v, s); };
    const double b = profile == MetricsProfile::WidataDpr18 ? 1.0 / 1.8 : th::hairline(dpr);
    SingleGeom g;
    g.header = QRectF(0, 0, W, lu(kHeaderH));
    const double by = (lu(kHeaderH) - lu(kBtnH)) / 2;
    double total = 2 * lu(kActPad);
    for (const WdcsgAction& a : kActions) {
        SingleGeom::Btn btn;
        btn.id = QString::fromLatin1(a.id);
        btn.text = QString::fromUtf8(a.text);
        const double tw = btn.text.isEmpty() ? 0 : lu(kIconGap) + wdcsg_luText(webTextExactWidth(btn.text, kBtnPx, kBtnWeight), s);
        btn.rect = QRectF(0, by, 2 * lu(kBtnPadX) + lu(a.iconPx) + tw, lu(kBtnH));
        g.actionButtons.push_back(btn);
        total += btn.rect.width();
    }
    total += lu(kActGap) * (g.actionButtons.size() - 1);
    g.actions = QRectF(W - total, 0, total, lu(kHeaderH));
    double x = g.actions.x() + lu(kActPad);
    for (size_t i = 0; i < g.actionButtons.size(); ++i) {
        SingleGeom::Btn& btn = g.actionButtons[i];
        btn.rect.moveLeft(x);
        const double ip = lu(kActions[i].iconPx);
        btn.icon = QRectF(x + lu(kBtnPadX), by + (lu(kBtnH) - ip) / 2, ip, ip);
        btn.textX = btn.icon.right() + lu(kIconGap);
        x = btn.rect.right() + lu(kActGap);
    }
    g.actionBaseline = by + (lu(kBtnH) - kBtnLineH) / 2 + th::blinkBaseline(kBtnPx, kBtnLineH, dpr);
    // title: 16/500 on the opsz 14 outlines (webTextExactWidth: 230.40 for the capture's 230.41)
    const double tw = wdcsg_luText(webTextExactWidth(th::displayName(title), kTitlePx, kTitleWeight), s);
    g.title = QRectF(0, 0, std::min(tw, std::max(0.0, g.actions.x() - lu(kTitleGap))), lu(kHeaderH));
    g.titleBaseline = th::blinkBaseline(kTitlePx, kTitleLineH, dpr);   // line box at the top of the stretched h6
    // range row: calendar box, divider, 9 buttons (28 high, gap 4), margin-bottom 12
    g.row = QRectF(0, g.header.bottom(), W, lu(kRangeH) + lu(kRowGap));
    g.calendarBox = QRectF(0, g.row.y(), lu(kCalBox), lu(kCalBox));
    g.calendarBtn = g.calendarBox.adjusted(lu(kCalPad), lu(kCalPad), -lu(kCalPad), -lu(kCalPad));
    g.calendarIcon = QRectF(g.calendarBtn.x() + lu(kCalPad), g.calendarBtn.y() + lu(kCalPad), lu(kCalIcon), lu(kCalIcon));
    g.divider = QRectF(g.calendarBox.right() + lu(kDivMargin), g.row.y(), b, lu(kCalBox));
    g.buttons = layoutRangeButtons(QPointF(g.divider.right() + lu(kDivMargin), g.row.y()), dpr, profile, kRangeH, kRangeGap);
    g.rangeGroup = QRectF(g.buttons.front().rect.topLeft(), QPointF(g.buttons.back().rect.right(), g.buttons.back().rect.bottom()));
    // panes: chart box, legend right under it; a 2-pane card adds a divider between the two (MẶC ĐỊNH)
    double top = g.row.bottom();
    for (int k = 0; k < std::clamp(panes, 1, 2); ++k) {
        QRectF d;
        if (k > 0) {
            d = QRectF(0, top + lu(kPaneDivTop), W, b);
            top = d.bottom() + lu(kPaneDivBottom);
        }
        g.paneDividers.push_back(d);
        g.paneBoxes.push_back(QRectF(0, top, W, chartH));
        g.paneCharts.push_back(QRectF(0, top, std::floor(W + 1e-6), std::floor(chartH + 0.5)));   // Highcharts size
        g.paneLegends.push_back(QRectF(kLegendMargin * W, top + chartH, (1 - 2 * kLegendMargin) * W, lu(kLegendH)));
        top = g.paneLegends.back().bottom();
    }
    g.chartBox = g.paneBoxes.front();
    g.chart = g.paneCharts.front();
    g.legend = g.paneLegends.front();
    g.frame = QRectF(0, 0, W, top + lu(kBottomPad));
    return g;
}

double singleChartHeight(QSizeF content, int panes, double dpr) {
    const int n = std::clamp(panes, 1, 2);
    const double fixed = layoutSingle(content.width(), dpr, QString(), MetricsProfile::Native, 0, n).frame.height();
    const double room = (content.height() - fixed) / n;
    return std::max(kMinChartH, std::min(content.width() * kCapChartH / kCapW, room));
}

// ---- widget --------------------------------------------------------------------------------------------------------

WdcSingle::WdcSingle(QWidget* parent) : QWidget(parent) {
    setMouseTracking(true);
    setFocusPolicy(Qt::StrongFocus);
    setAutoFillBackground(false);
    tipTimer_ = new QTimer(this);
    tipTimer_->setSingleShot(true);
    tipTimer_->setInterval(kTipDelayMs);
    connect(tipTimer_, &QTimer::timeout, this, [this] {
        const SingleGeom g = geometryModel();
        if (hover_.part == Part::Calendar) showTip(QStringLiteral("Đợt 2"), g.calendarBox.translated(contentOrigin()));
        else if (hover_ == HitRes{Part::Action, 2})
            showTip(QStringLiteral("Đợt 2"), g.actionButtons[2].rect.translated(contentOrigin()));
    });
}

WdcSingle::~WdcSingle() {
    if (tip_) tip_->deleteLater();
}

void WdcSingle::reset(const QString& title, const std::vector<PaneSpec>& panes, std::shared_ptr<const DashData> data,
                      const QString& button, bool zIndexDesc, bool allExact, bool alignRight) {
    title_ = title;
    zDesc_ = zIndexDesc;
    allExact_ = allExact;
    alignRight_ = alignRight;
    button_ = resolveRangeButton(button, QString());
    const size_t n = std::clamp<size_t>(panes.size(), 1, 2);
    panes_.clear();
    panes_.resize(n);   // never resized again until the next reset: pointers into it stay valid
    for (size_t k = 0; k < n; ++k) {
        panes_[k].setPane(k < panes.size() ? panes[k] : PaneSpec{}, data);
        panes_[k].setExpanded(card_.has_value());   // card spec: Y labels 11 px like the overlay (MẶC ĐỊNH)
    }
    while (legends_.size() > n) {
        delete legends_.back();
        legends_.pop_back();
    }
    while (legends_.size() < n) {
        const int k = int(legends_.size());
        auto* lg = new WdcLegend(this);
        lg->setLegendStyle(LegendStyle::Single);
        connect(lg, &WdcLegend::toggled, this, [this, k](int refIndex, bool vis) {
            std::vector<bool> v = panes_[size_t(k)].visible();
            if (refIndex >= 0 && refIndex < int(v.size())) v[size_t(refIndex)] = vis;
            setPaneVisible(k, v);
        });
        connect(lg, &WdcLegend::resetRequested, this, [this, k] {
            setPaneVisible(k, std::vector<bool>(panes_[size_t(k)].pane().series.size(), true));
        });
        lg->show();
        legends_.push_back(lg);
    }
    for (size_t k = 0; k < n; ++k) {
        legends_[k]->setEntries(panes_[k].legendEntries(zDesc_), panes_[k].data());
        legends_[k]->setVisibility(panes_[k].visible());
    }
    rebuildHovers();
    applyWindow();
    place();
}

void WdcSingle::rebuildHovers() {
    // attachChartHover connects chartMouse/chartLeft with this page as context: drop those, then one hover per pane
    disconnect(this, &WdcSingle::chartMouse, this, nullptr);
    disconnect(this, &WdcSingle::chartLeft, this, nullptr);
    for (WdcChartHover* h : hovers_) delete h;
    hovers_ = attachChartHover(this);
    hoverChart_ = -1;
}

void WdcSingle::setChart(const SingleChartSpec& spec, std::shared_ptr<const DashData> data) {
    link_ = QStringLiteral("wdc://chart/") + spec.id;
    card_.reset();   // the chart-page spec carries its own 12 px labels
    reset(spec.title, {spec.pane}, std::move(data), spec.defaultRange, false, false, false);   // series order
}

void WdcSingle::setCard(const QString& dashId, const CardSpec& card, std::shared_ptr<const DashData> data) {
    link_ = QStringLiteral("wdc://card/%1/%2").arg(dashId, card.key);
    card_ = card;
    reset(card.title, card.panes, std::move(data), card.defaultRange.button, card.legendOrder != QLatin1String("series"),
          card.allExact, card.alignPanesRight);
}

void WdcSingle::setData(std::shared_ptr<const DashData> data) {
    for (size_t k = 0; k < panes_.size(); ++k) {
        panes_[k].setData(data);
        legends_[k]->setEntries(panes_[k].legendEntries(zDesc_), panes_[k].data());
        legends_[k]->setVisibility(panes_[k].visible());
    }
    applyWindow();
}

void WdcSingle::setFollowParent(int top) {
    followTop_ = top;
    if (QWidget* p = parentWidget()) {
        p->installEventFilter(this);
        setGeometry(0, top, p->width(), std::max(0, p->height() - top));
    }
}

bool WdcSingle::eventFilter(QObject* o, QEvent* e) {
    if (followTop_ >= 0 && o == parentWidget() && e->type() == QEvent::Resize)
        setGeometry(0, followTop_, parentWidget()->width(), std::max(0, parentWidget()->height() - followTop_));
    return QWidget::eventFilter(o, e);
}

std::optional<qint64> WdcSingle::refMax() const {   // every pane (BEH §3.1)
    std::optional<qint64> ref;
    for (const WdcPaneChart& pc : panes_)
        if (const auto r = pc.refMax(); r && (!ref || *r > *ref)) ref = r;
    return ref;
}

void WdcSingle::applyWindow() {
    const XWindow w = windowForPage(button_, refMax(), allExact_);
    setXWindow(w.xMin, w.xMax, w.padAuto);
}

void WdcSingle::setXWindow(std::optional<qint64> xMin, std::optional<qint64> xMax, bool padAuto) {
    for (WdcPaneChart& pc : panes_) pc.setWindow(xMin, xMax, padAuto);   // compare base follows the window (pan too)
    alignPanes();
    resetHovers();
    update();
}

void WdcSingle::alignPanes() {
    // DESIGN §4.6 "Lề canh hàng", as WdcCard / WdcExpanded: first pass without marginRight, then the largest need
    if (!alignRight_ || paneCount() < 2) return;
    double need = 0;
    bool any = false;
    for (WdcPaneChart& pc : panes_) {
        pc.setMarginRight(std::nullopt);
        const ChartModel* m = pc.model();
        if (m->allMissing) continue;
        need = std::max(need, pc.size().width() - m->plotBox.right());
        any = true;
    }
    if (any)
        for (WdcPaneChart& pc : panes_) pc.setMarginRight(need);
}

void WdcSingle::resetHovers() {
    for (WdcChartHover* h : hovers_) h->reset();
}

void WdcSingle::setPaneVisible(int pane, const std::vector<bool>& visible) {
    if (pane < 0 || pane >= paneCount()) return;
    panes_[size_t(pane)].setVisible(visible);
    legends_[size_t(pane)]->setVisibility(panes_[size_t(pane)].visible());
    alignPanes();
    resetHovers();
    update();
}

QStringList WdcSingle::dimmedButtons() {
    std::vector<const ChartInput*> ins;
    for (WdcPaneChart& pc : panes_) ins.push_back(pc.input());
    return dimmedRangeButtons(ins, refMax());
}

bool WdcSingle::pickRange(const QString& button) {
    if (!isRangeButton(button) || dimmedButtons().contains(button)) return false;
    button_ = button;
    applyWindow();
    emit rangePicked(button);
    return true;
}

bool WdcSingle::compare() const { return !panes_.empty() && panes_.front().compare(); }

void WdcSingle::setCompare(bool on) {
    if (on == compare()) return;
    for (WdcPaneChart& pc : panes_) pc.setCompare(on);
    alignPanes();
    resetHovers();
    update();
    emit compareChanged(on);
}

SingleGeom WdcSingle::geometryModel() const {
    const double dpr = devicePixelRatioF() > 0 ? devicePixelRatioF() : 1.0;
    const QSizeF content(std::max(0.0, width() - 2 * kInset), std::max(0.0, height() - 2 * kInset));
    const int n = std::max(1, paneCount());
    return layoutSingle(content.width(), dpr, title_, MetricsProfile::Native, singleChartHeight(content, n, dpr), n);
}

const ChartModel* WdcSingle::chartModel(int pane) {
    return pane >= 0 && pane < paneCount() ? panes_[size_t(pane)].model() : nullptr;
}

const ChartInput* WdcSingle::chartInput(int pane) {
    return pane >= 0 && pane < paneCount() ? panes_[size_t(pane)].input() : nullptr;
}

QRectF WdcSingle::chartRect(int pane) const {
    const SingleGeom g = geometryModel();
    return pane >= 0 && size_t(pane) < g.paneCharts.size() ? g.paneCharts[size_t(pane)].translated(contentOrigin()) : QRectF();
}

WdcLegend* WdcSingle::legend(int pane) const {
    return pane >= 0 && size_t(pane) < legends_.size() ? legends_[size_t(pane)] : nullptr;
}

void WdcSingle::place() {
    const SingleGeom g = geometryModel();
    for (size_t k = 0; k < panes_.size() && k < g.paneCharts.size(); ++k) {
        panes_[k].setSize(g.paneCharts[k].size());
        legends_[k]->setContainerRect(g.paneLegends[k].translated(contentOrigin()));
    }
    alignPanes();
    resetHovers();
    update();
}

void WdcSingle::resizeEvent(QResizeEvent* e) {
    QWidget::resizeEvent(e);
    place();
}

QImage WdcSingle::exportImage(qreal dpr) {
    const SingleGeom g = geometryModel();
    const QRectF area(0, g.chartBox.y(), g.frame.width(), g.frame.bottom() - g.chartBox.y());
    QImage img((area.size() * dpr).toSize(), QImage::Format_ARGB32_Premultiplied);
    img.setDevicePixelRatio(dpr);
    img.fill(Qt::white);
    QPainter p(&img);
    p.setRenderHint(QPainter::Antialiasing, true);
    p.setRenderHint(QPainter::TextAntialiasing, true);
    p.translate(-area.topLeft());
    for (size_t k = 0; k < panes_.size() && k < g.paneCharts.size(); ++k) {
        const QRectF d = g.paneDividers[k];
        if (!d.isEmpty()) p.fillRect(QRectF(d.x(), std::round(d.y() * dpr) / dpr, d.width(), th::hairline(dpr)), th::color(th::kBorder));
        panes_[k].paint(p, g.paneCharts[k]);
        panes_[k].paintExportLegend(p, g.paneLegends[k], LegendStyle::Single, zDesc_, dpr);
    }
    return img;
}

bool WdcSingle::trigger(const QString& actionId) {
    if (isRangeButton(actionId)) return pickRange(actionId);
    for (int i = 0; i < int(std::size(kActions)); ++i)
        if (actionId == QLatin1String(kActions[i].id)) {
            if (i == 2) return false;   // "Tuỳ chỉnh": Đợt 2
            activate({Part::Action, i});
            return true;
        }
    return false;
}

void WdcSingle::activate(const HitRes& h) {
    if (h.part == Part::Range) {
        if (h.index >= 0 && h.index < int(rangeButtons().size())) pickRange(rangeButtons()[h.index]);
        return;
    }
    if (h.part != Part::Action) return;
    const SingleGeom g = geometryModel();
    switch (h.index) {
    case 0: setCompare(!compare()); break;
    case 1:
        QGuiApplication::clipboard()->setText(link_);
        emit linkCopied(link_);
        showTip(QStringLiteral("Đã chép liên kết"), g.actionButtons[1].rect.translated(contentOrigin()), kCopiedTipMs);
        break;
    case 3: {
        const QImage img = exportImage(2.0);
        const QString name = wdcsg_fileName(title_);
        if (isSignalConnected(QMetaMethod::fromSignal(&WdcSingle::exportPngRequested))) {
            emit exportPngRequested(img, name);
            break;
        }
        const QString path = QFileDialog::getSaveFileName(this, QStringLiteral("Tải về"), QDir::home().filePath(name),
                                                          QStringLiteral("PNG (*.png)"));
        if (!path.isEmpty()) (void)QtConcurrent::run([img, path] { img.save(path, "PNG"); });
        break;
    }
    case 4: openExpanded(); break;
    default: break;
    }
}

void WdcSingle::openExpanded() {
    // full screen: the expanded overlay over the page's parent, every pane, the page's window and legend (MẶC ĐỊNH)
    if (panes_.empty()) return;
    emit expandRequested();
    QWidget* host = parentWidget() ? parentWidget() : this;
    const WdcPaneChart& p0 = panes_.front();
    auto* ex = card_ ? new WdcExpanded(*card_, p0.data(), host)
                     : new WdcExpanded(title_, p0.pane(), p0.data(), button_, allExact_, host);
    if (card_) ex->pickRange(button_);
    for (int k = 0; k < paneCount() && k < ex->paneCount(); ++k) ex->setSeriesVisible(k, panes_[size_t(k)].visible());
    ex->setXWindow(p0.xMin(), p0.xMax(), p0.padAuto());
    ex->setGeometry(host->rect());
    ex->show();
    ex->raise();
    ex->setFocus();
    QPointer<WdcSingle> self(this);
    connect(ex, &WdcExpanded::closed, this, [self] {
        if (self) QTimer::singleShot(0, self, [self] { if (self) self->setFocus(); });
    });
    expanded_ = ex;
}

// ---- events --------------------------------------------------------------------------------------------------------

WdcSingle::HitRes WdcSingle::hitAt(const QPointF& pos) const {
    const SingleGeom g = geometryModel();
    const QPointF c = pos - contentOrigin();
    for (int i = 0; i < int(g.actionButtons.size()); ++i)
        if (g.actionButtons[size_t(i)].rect.contains(c)) return {Part::Action, i};
    if (g.calendarBtn.contains(c)) return {Part::Calendar, -1};
    for (int i = 0; i < int(g.buttons.size()); ++i)
        if (g.buttons[size_t(i)].rect.contains(c)) return {Part::Range, i};
    for (int k = 0; k < int(g.paneCharts.size()) && k < paneCount(); ++k)
        if (g.paneCharts[size_t(k)].contains(c)) return {Part::Chart, k};
    return {};
}

void WdcSingle::mouseMoveEvent(QMouseEvent* e) {
    const QPointF pos = e->position();
    const HitRes h = hitAt(pos);
    if (!(h == hover_)) {
        hover_ = h;
        if (h.part == Part::Calendar || h == HitRes{Part::Action, 2}) tipTimer_->start();
        else {
            tipTimer_->stop();
            if (tip_ && tip_->isVisible()) tip_->hide();
        }
        update();
    }
    // a drag that started in a chart keeps going outside it (Highcharts listens on the document while panning)
    const int chart = press_.part == Part::Chart ? press_.index : (h.part == Part::Chart ? h.index : -1);
    if (chart != hoverChart_ && hoverChart_ >= 0) emit chartLeft(hoverChart_);
    hoverChart_ = chart;
    if (chart >= 0) emit chartMouse(chart, int(QEvent::MouseMove), pos - chartRect(chart).topLeft(), e->buttons());
    const bool hand = (h.part == Part::Action && h.index != 2) || h.part == Part::Range;
    if (press_.part != Part::Chart) setCursor(hand ? Qt::PointingHandCursor : Qt::ArrowCursor);
}

void WdcSingle::mousePressEvent(QMouseEvent* e) {
    press_ = e->button() == Qt::LeftButton ? hitAt(e->position()) : HitRes{};
    if (press_.part == Part::Chart)
        emit chartMouse(press_.index, int(QEvent::MouseButtonPress), e->position() - chartRect(press_.index).topLeft(),
                        e->buttons());
    setFocus(Qt::MouseFocusReason);
    update();
}

void WdcSingle::mouseReleaseEvent(QMouseEvent* e) {
    const HitRes pressed = press_;
    press_ = {};
    if (pressed.part == Part::Chart) {
        emit chartMouse(pressed.index, int(QEvent::MouseButtonRelease), e->position() - chartRect(pressed.index).topLeft(),
                        e->buttons());
        return;
    }
    update();
    if (pressed.part != Part::None && hitAt(e->position()) == pressed && !(pressed == HitRes{Part::Action, 2}))
        activate(pressed);
}

void WdcSingle::leaveEvent(QEvent*) {
    hover_ = {};
    tipTimer_->stop();
    if (hoverChart_ >= 0) emit chartLeft(hoverChart_);
    hoverChart_ = -1;
    unsetCursor();
    update();
}

void WdcSingle::keyPressEvent(QKeyEvent* e) {
    if (e->key() == Qt::Key_Escape) {   // back to the dashboard (MẶC ĐỊNH đợt 4)
        e->accept();
        emit backRequested();
        return;
    }
    QWidget::keyPressEvent(e);
}

void WdcSingle::showTip(const QString& text, const QRectF& anchor, int hideAfterMs) {
    if (!tip_) tip_ = new WdcPopover(this, WdcPopover::Mode::TitleTip);
    tip_->setLines({text});
    tip_->showAt(mapToGlobal(QPointF(anchor.x(), anchor.bottom() + th::kTitleTipGap)).toPoint());
    if (hideAfterMs > 0) {
        QPointer<WdcPopover> t = tip_;
        QTimer::singleShot(hideAfterMs, this, [t] { if (t) t->hide(); });
    }
}

void WdcSingle::paintEvent(QPaintEvent*) {
    QPainter p(this);
    p.setRenderHint(QPainter::Antialiasing, true);
    p.setRenderHint(QPainter::TextAntialiasing, true);
    const qreal dpr = devicePixelRatioF() > 0 ? devicePixelRatioF() : 1.0;
    p.fillRect(rect(), th::color(th::kBgSurface));
    const SingleGeom g = geometryModel();
    p.translate(contentOrigin());
    // title: 16/500 on the opsz 14 outlines, sentence case, no margin
    p.setFont(webFont(kTitlePx, kTitleWeight));
    p.setPen(th::color(th::kTextPrimary));
    th::drawWebText(p, QPointF(g.title.x(), g.titleBaseline),
                    webElide(th::displayName(title_), kTitlePx, kTitleWeight, g.title.width() + 0.01), kTitleWeight);
    // action cluster
    p.fillPath(wdcsg_round(g.actions, kRadius), th::color(th::kBgSubtle));
    p.setFont(th::font(kBtnPx, kBtnWeight));
    for (int i = 0; i < int(g.actionButtons.size()); ++i) {
        const SingleGeom::Btn& btn = g.actionButtons[size_t(i)];
        const bool disabled = i == 2;
        const bool on = i == 0 && compare();
        const bool hot = !disabled && hover_ == HitRes{Part::Action, i};
        if (hot || on) {   // hover: card cluster rule (SUY LUẬN); compare on: same token, MẶC ĐỊNH
            paintBoxShadow(p, btn.rect, kRadius, wdcsg_hoverShadow(), dpr);
            p.fillPath(wdcsg_round(btn.rect, kRadius), th::color(th::kWhite));
        }
        const QColor fg = disabled ? kDisabledFg : th::color(hot || on ? th::kTextPrimary : th::kTextSecondary);
        paintIcon(p, kActions[i].icon, btn.icon, fg);
        if (!btn.text.isEmpty()) {
            p.setPen(fg);
            th::drawWebText(p, QPointF(btn.textX, g.actionBaseline), btn.text, kBtnWeight);
        }
    }
    // range row
    p.fillPath(wdcsg_round(g.calendarBox, kRadius), th::color(th::kBgSubtle));
    paintIcon(p, Icon::CalendarExpanded20, g.calendarIcon, th::color(th::kTextSecondary));
    const double ox = contentOrigin().x();
    p.fillRect(QRectF(std::round((g.divider.x() + ox) * dpr) / dpr - ox, g.divider.y(), th::hairline(dpr), g.divider.height()),
               th::color(th::kBorder));
    const QStringList dim = dimmedButtons();
    for (int i = 0; i < int(g.buttons.size()); ++i) {
        const RangeButtonGeom& b = g.buttons[size_t(i)];
        paintRangeButton(p, b, b.label == button_, dim.contains(b.label), hover_ == HitRes{Part::Range, i},
                         press_ == HitRes{Part::Range, i});
    }
    // charts (no watermark, DESIGN §16 C7) + hover layer; 1 device px divider between two panes
    for (size_t k = 0; k < panes_.size() && k < g.paneCharts.size(); ++k) {
        const QRectF d = g.paneDividers[k];
        if (!d.isEmpty()) p.fillRect(QRectF(d.x(), std::round(d.y() * dpr) / dpr, d.width(), th::hairline(dpr)), th::color(th::kBorder));
        panes_[k].paint(p, g.paneCharts[k]);
        if (overlay_) {
            p.save();
            overlay_(p, int(k), g.paneCharts[k]);
            p.restore();
        }
    }
}

// ---- host glue -----------------------------------------------------------------------------------------------------

namespace {

WdcSingle* wdcsg_host(WdcView* view) {
    for (WdcSingle* old : view->findChildren<WdcSingle*>(Qt::FindDirectChildrenOnly)) {
        old->hide();
        old->deleteLater();
    }
    auto* page = new WdcSingle(view);
    WdcShell* shell = view->shell();
    const int top = shell ? shell->geometry().bottom() + 1 : 0;
    page->setFollowParent(top);
    QPointer<WdcView> v(view);
    QPointer<WdcSingle> pg(page);
    auto close = [v, pg] {
        if (!pg) return;
        pg->hide();
        pg->deleteLater();
        if (v && v->shell()) v->shell()->setActive(v->current_dashboard());
        if (v) v->setFocus();
    };
    QObject::connect(page, &WdcSingle::backRequested, page, close);
    if (shell) {
        shell->setActive(QString());   // no tab highlighted while the page is open
        QObject::connect(shell, &WdcShell::tabActivated, page, [close](const QString&) { close(); });
    }
    page->show();
    page->raise();
    page->setFocus();
    return page;
}

} // namespace

WdcSingle* openSingleChart(WdcView* view, const QString& singleId) {
    if (!view || !view->layouts()) return nullptr;
    const SingleChartSpec* spec = view->layouts()->single(singleId);
    if (!spec) return nullptr;
    WdcSingle* page = wdcsg_host(view);
    page->setChart(*spec, nullptr);
    const QString buildDir = view->build_state().buildDir;
    if (buildDir.isEmpty()) return page;   // no build: every series [CẦN DATA]
    auto* watcher = new QFutureWatcher<Loaded<DashData>>(page);
    QObject::connect(watcher, &QFutureWatcher<Loaded<DashData>>::finished, page, [page, watcher] {
        page->setData(watcher->result().value);
        watcher->deleteLater();
    });
    watcher->setFuture(QtConcurrent::run([buildDir, singleId] {
        Loaded<DashData> r = loadDash(buildDir, QStringLiteral("single"));   // layouts.json single_charts_data
        return r.ok() ? r : loadSingle(buildDir, singleId);
    }));
    return page;
}

WdcSingle* openCardSingle(WdcView* view, const QString& dashId, const QString& cardKey) {
    if (!view || !view->layouts()) return nullptr;
    const DashSpec* ds = view->layouts()->dash(dashId);
    const CardSpec* card = ds ? ds->card(cardKey) : nullptr;
    if (!card) return nullptr;
    WdcSingle* page = wdcsg_host(view);
    page->setCard(dashId, *card, view->dash_data(dashId));
    return page;
}

} // namespace fincept::screens::wdc
