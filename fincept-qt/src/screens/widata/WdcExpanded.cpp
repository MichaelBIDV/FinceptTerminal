// WdcExpanded.cpp, package F: expanded overlay of a dashboard card. Geometry: capture EX[0..54] (UI §4,
// F_plan_expanded_single §1.2); behaviour: BEH §6, DESIGN §7.1; tokens: WdcTheme_p.h, DESIGN §6.1, HOVER_CSS.md.
#include "screens/widata/WdcExpanded.h"

#include "screens/widata/WdcCard.h"
#include "screens/widata/WdcHcText.h"
#include "screens/widata/WdcIcons_p.h"
#include "screens/widata/WdcLegend.h"
#include "screens/widata/WdcTheme_p.h"
#include "screens/widata/WdcTooltip.h"
#include "screens/widata/WdcView.h"

#include <QClipboard>
#include <QDir>
#include <QFileDialog>
#include <QGuiApplication>
#include <QKeyEvent>
#include <QMetaMethod>
#include <QMetaObject>
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

// UI §4.2, §4.3, §4.5 (CSS px)
constexpr double kPad = 16, kHeaderH = 32, kTitleMargin = 8, kTitleLineH = 24, kTitlePx = 16, kTitlePadRight = 16;
constexpr int kTitleWeight = 500;
constexpr double kCalBox = 28, kCalPad = 2, kCalIcon = 20, kDivMargin = 8;
constexpr double kRangeH = 24, kRangeGap = 8;
constexpr double kActPad = 4, kActBtnH = 26, kActBtnPad = 6, kActGap = 4, kActPx = 13, kActLineH = 13.0 * 12.0 / 7.0;
constexpr int kActWeight = 500;
constexpr double kShareIcon = 16, kShareGap = 8, kShareIconDy = 5;
constexpr double kDlIconBox = 20, kDlIconML = -4, kDlIconMR = 6, kDlIcon = 18, kDlIconInset = 1;   // EX[28..30]: 34 + text
constexpr double kCloseSize = 24, kBoxRadius = 4, kBtnRadius = 4;
constexpr double kChartTop = 12, kChartToLegend = 12, kLegendH = 36, kDivTop = 12, kDivBottom = 8;
const QString kShareText = QStringLiteral("Chia sẻ");
const QString kDownloadText = QStringLiteral("Tải về");
constexpr int kTipDelayMs = 500, kCopiedTipMs = 1500;

struct WdcexLu {
    double s;
    double operator()(double css) const { return std::floor(css * s + 1e-9) / s; }   // LayoutUnit, truncated
    double text(double css) const { return std::ceil(css * s - 1e-7) / s; }          // text run, rounded up
};

WdcexLu wdcex_lu(double dpr, MetricsProfile profile) {
    return {64.0 * (profile == MetricsProfile::WidataDpr18 ? 1.8 : (dpr > 0 ? dpr : 1.0))};
}

double wdcex_textW(const QString& s, double px, int weight) { return webTextExactWidth(s, px, weight); }

QPainterPath wdcex_round(const QRectF& r, double radius) {
    QPainterPath p;
    p.addRoundedRect(r, std::min(radius, r.width() / 2), std::min(radius, r.height() / 2));
    return p;
}

// HOVER_CSS.md has no rule for these clusters (the scan covered the dashboard only): the card button cluster rule
// (.css-yp4adf: white, rgba(33,35,46,.06) 0 0 6px, #21232E) is applied to the same #F6F5F4 cluster pattern (SUY LUẬN).
const std::vector<ShadowLayer>& wdcex_hoverShadow() {
    static const std::vector<ShadowLayer> v = {{0, 0, 6, 0, QColor(33, 35, 46, 15)}};
    return v;
}

} // namespace

// ---- geometry ------------------------------------------------------------------------------------------------------

ExpandedGeom layoutExpanded(QSizeF view, double dpr, int panes, MetricsProfile profile) {
    const WdcexLu lu = wdcex_lu(dpr, profile);
    const double b = profile == MetricsProfile::WidataDpr18 ? 1.0 / 1.8 : th::hairline(dpr);
    const int n = std::clamp(panes, 1, 2);
    ExpandedGeom g;
    g.backdrop = QRectF(QPointF(0, 0), view);
    const double BW = lu(0.9 * view.width()), BH = lu(0.9 * view.height());
    const double bx = (view.width() - BW) / 2, by = (view.height() - BH) / 2;   // flex centring
    g.box = QRectF(bx, by, BW, BH);
    const double hx = bx + lu(kPad), hy = by + lu(kPad), hw = BW - 2 * lu(kPad), hh = lu(kHeaderH);
    g.header = QRectF(hx, hy, hw, hh);
    const double right = hx + hw;
    // right-hand clusters, laid out from the right edge
    const double shareW = 2 * lu(kActBtnPad) + lu(kShareIcon) + lu(kShareGap) + lu.text(wdcex_textW(kShareText, kActPx, kActWeight));
    const double dlW = lu(kActBtnPad) + lu(kDlIconML + kDlIconBox) + lu(kDlIconMR) + lu.text(wdcex_textW(kDownloadText, kActPx, kActWeight)) +
                       lu(kActBtnPad);
    const double actW = 2 * lu(kActPad) + shareW + lu(kActGap) + dlW;
    g.actions = QRectF(right - actW, hy, actW, hh);
    const double by26 = hy + (hh - lu(kActBtnH)) / 2;
    g.share = QRectF(g.actions.x() + lu(kActPad), by26, shareW, lu(kActBtnH));
    g.shareIcon = QRectF(g.share.x() + lu(kActBtnPad), g.share.y() + lu(kShareIconDy), lu(kShareIcon), lu(kShareIcon));
    g.shareTextX = g.shareIcon.right() + lu(kShareGap);
    g.download = QRectF(g.share.right() + lu(kActGap), by26, dlW, lu(kActBtnH));
    g.downloadIconBox = QRectF(g.download.x() + lu(kActBtnPad + kDlIconML), g.download.y() + (lu(kActBtnH) - lu(kDlIconBox)) / 2,
                               lu(kDlIconBox), lu(kDlIconBox));
    g.downloadIcon = QRectF(g.downloadIconBox.x() + lu(kDlIconInset), g.downloadIconBox.y() + lu(kDlIconInset), lu(kDlIcon),
                            lu(kDlIcon));
    g.downloadTextX = g.downloadIconBox.right() + lu(kDlIconMR);
    g.actionBaseline = by26 + (lu(kActBtnH) - kActLineH) / 2 + th::blinkBaseline(kActPx, kActLineH, dpr);
    g.divider2 = QRectF(g.actions.x() - lu(kDivMargin) - b, hy, b, hh);
    const double rw = rangeButtonsWidth(dpr, profile, kRangeH, kRangeGap);
    const double ry = hy + (hh - lu(kRangeH)) / 2;
    g.rangeGroup = QRectF(g.divider2.x() - lu(kDivMargin) - rw, ry, rw, lu(kRangeH));
    g.buttons = layoutRangeButtons(g.rangeGroup.topLeft(), dpr, profile, kRangeH, kRangeGap);
    g.divider1 = QRectF(g.rangeGroup.x() - lu(kDivMargin) - b, hy, b, hh);
    g.calendarBox = QRectF(g.divider1.x() - lu(kDivMargin) - lu(kCalBox), hy + (hh - lu(kCalBox)) / 2, lu(kCalBox), lu(kCalBox));
    g.calendarBtn = g.calendarBox.adjusted(lu(kCalPad), lu(kCalPad), -lu(kCalPad), -lu(kCalPad));
    g.calendarIcon = QRectF(g.calendarBtn.x() + lu(kCalPad), g.calendarBtn.y() + lu(kCalPad), lu(kCalIcon), lu(kCalIcon));
    g.cluster = QRectF(g.calendarBox.x(), hy, right - g.calendarBox.x(), hh);
    g.rangeCluster = QRectF(g.calendarBox.x(), hy, g.rangeGroup.right() - g.calendarBox.x(), hh);
    const double tx = hx + lu(kTitleMargin);
    g.title = QRectF(tx, hy + (hh - lu(kTitleLineH)) / 2, std::max(0.0, g.cluster.x() - lu(kTitleMargin) - tx), lu(kTitleLineH));
    g.titleBaseline = g.title.y() + th::blinkBaseline(kTitlePx, kTitleLineH, dpr);
    g.close = QRectF(bx + BW - lu(kCloseSize / 2), by - lu(kCloseSize / 2), lu(kCloseSize), lu(kCloseSize));
    // body: chart stack under the header, padding-bottom 16 of the box
    g.body = QRectF(hx, hy + hh, hw, BH - 2 * lu(kPad) - hh);
    const double per = lu(kChartToLegend) + lu(kLegendH), div = lu(kDivTop) + b + lu(kDivBottom);
    const double chartH = std::max(0.0, (g.body.height() - lu(kChartTop) - per * n - div * (n - 1)) / n);
    double top = g.body.y() + lu(kChartTop);
    for (int k = 0; k < n; ++k) {
        QRectF d;
        if (k > 0) {
            d = QRectF(hx, top + lu(kDivTop), hw, b);
            top = d.bottom() + lu(kDivBottom);
        }
        g.paneDividers.push_back(d);
        g.paneBoxes.push_back(QRectF(hx, top, hw, chartH));
        // Highcharts getChartSize: width floor of the box (1433.99 - 32 -> 1401), height offsetHeight (823)
        g.paneCharts.push_back(QRectF(hx, top, std::floor(hw + 1e-6), std::floor(chartH + 0.5)));
        g.paneLegends.push_back(QRectF(hx, top + chartH + lu(kChartToLegend), hw, lu(kLegendH)));
        top = g.paneLegends.back().bottom();
    }
    return g;
}

// ---- widget --------------------------------------------------------------------------------------------------------

QWidget* WdcExpanded::create(const CardContext& ctx, QWidget* view) {
    if (!ctx.card || !view) return nullptr;
    WdcCard* src = nullptr;
    for (WdcCard* c : view->findChildren<WdcCard*>())
        if (c->spec().key == ctx.card->key && (ctx.dashId.isEmpty() || c->dashId().isEmpty() || c->dashId() == ctx.dashId)) {
            src = c;
            break;
        }
    return new WdcExpanded(*ctx.card, ctx.data, view, src);
}

WdcExpanded::WdcExpanded(const CardSpec& card, std::shared_ptr<const DashData> data, QWidget* parent, QWidget* source)
    : QWidget(parent), source_(source) {
    title_ = card.title;
    zDesc_ = card.legendOrder != QLatin1String("series");
    allExact_ = card.allExact;
    alignRight_ = card.alignPanesRight;
    for (const PaneSpec& ps : card.panes) {
        panes_.emplace_back();
        panes_.back().setPane(ps, data);
    }
    if (panes_.empty()) panes_.emplace_back();
    button_ = resolveRangeButton(source ? source->property(kRangeButtonProperty).toString() : QString(),
                                 card.defaultRange.button);
    init(std::move(data));
}

WdcExpanded::WdcExpanded(const QString& title, const PaneSpec& pane, std::shared_ptr<const DashData> data,
                         const QString& button, bool allExact, QWidget* parent)
    : QWidget(parent) {
    title_ = title;
    allExact_ = allExact;
    panes_.emplace_back();
    panes_.back().setPane(pane, data);
    button_ = resolveRangeButton(button, QString());
    init(std::move(data));
}

WdcExpanded::~WdcExpanded() {
    if (tip_) tip_->deleteLater();
}

void WdcExpanded::init(std::shared_ptr<const DashData>) {
    setMouseTracking(true);
    setFocusPolicy(Qt::StrongFocus);
    setAttribute(Qt::WA_StyledBackground, false);
    tipTimer_ = new QTimer(this);
    tipTimer_->setSingleShot(true);
    tipTimer_->setInterval(kTipDelayMs);
    connect(tipTimer_, &QTimer::timeout, this, [this] {
        if (hover_.part == Part::Calendar) showTip(QStringLiteral("Đợt 2"), geometryModel().calendarBox);
    });
    for (WdcPaneChart& pc : panes_) pc.setExpanded(true);
    auto* card = qobject_cast<WdcCard*>(source_.data());
    if (card) {   // session state of the grid card: window (pan included) and legend visibility
        const ChartInput* in = card->chartInput(0);
        for (int k = 0; k < paneCount(); ++k) {
            panes_[size_t(k)].setVisible(card->seriesVisible(k));
            if (in) panes_[size_t(k)].setWindow(in->xMin, in->xMax, in->padAuto);
        }
    } else {
        std::optional<qint64> ref;
        for (const WdcPaneChart& pc : panes_)
            if (const auto r = pc.refMax(); r && (!ref || *r > *ref)) ref = r;
        const XWindow w = windowForCard(button_, ref, allExact_);
        for (WdcPaneChart& pc : panes_) pc.setWindow(w.xMin, w.xMax, w.padAuto);
    }
    for (int k = 0; k < paneCount(); ++k) {
        auto* lg = new WdcLegend(this);
        lg->setLegendStyle(LegendStyle::Expanded);
        lg->setEntries(panes_[size_t(k)].legendEntries(zDesc_), panes_[size_t(k)].data());
        lg->setVisibility(panes_[size_t(k)].visible());
        connect(lg, &WdcLegend::toggled, this, [this, k](int refIndex, bool vis) {
            std::vector<bool> v = panes_[size_t(k)].visible();
            if (refIndex >= 0 && refIndex < int(v.size())) v[size_t(refIndex)] = vis;
            setSeriesVisible(k, v);
        });
        connect(lg, &WdcLegend::resetRequested, this, [this, k] {
            setSeriesVisible(k, std::vector<bool>(panes_[size_t(k)].pane().series.size(), true));
        });
        lg->show();
        legends_.push_back(lg);
    }
    hovers_ = attachChartHover(this);
    placeLegends();
}

void WdcExpanded::placeLegends() {
    const ExpandedGeom g = geometryModel();
    for (int k = 0; k < paneCount(); ++k) {
        if (size_t(k) < g.paneCharts.size()) panes_[size_t(k)].setSize(g.paneCharts[size_t(k)].size());
        if (size_t(k) < legends_.size() && size_t(k) < g.paneLegends.size())
            legends_[size_t(k)]->setContainerRect(g.paneLegends[size_t(k)]);
    }
    alignPanes();
    resetHovers();
}

void WdcExpanded::alignPanes() {
    // DESIGN §4.6 "Lề canh hàng", as WdcCard: first pass without marginRight, then every pane gets the largest need
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

void WdcExpanded::resetHovers() {
    for (WdcChartHover* h : hovers_) h->reset();
}

ExpandedGeom WdcExpanded::geometryModel() const {
    return layoutExpanded(QSizeF(size()), devicePixelRatioF() > 0 ? devicePixelRatioF() : 1.0, paneCount());
}

const ChartModel* WdcExpanded::chartModel(int pane) {
    return pane >= 0 && pane < paneCount() ? panes_[size_t(pane)].model() : nullptr;
}

const ChartInput* WdcExpanded::chartInput(int pane) {
    return pane >= 0 && pane < paneCount() ? panes_[size_t(pane)].input() : nullptr;
}

QRectF WdcExpanded::chartRect(int pane) const {
    const ExpandedGeom g = geometryModel();
    return pane >= 0 && size_t(pane) < g.paneCharts.size() ? g.paneCharts[size_t(pane)] : QRectF();
}

WdcLegend* WdcExpanded::legend(int pane) const {
    return pane >= 0 && size_t(pane) < legends_.size() ? legends_[size_t(pane)] : nullptr;
}

std::vector<bool> WdcExpanded::seriesVisible(int pane) const {
    return pane >= 0 && pane < paneCount() ? panes_[size_t(pane)].visible() : std::vector<bool>();
}

void WdcExpanded::setSeriesVisible(int pane, const std::vector<bool>& visible) {
    if (pane < 0 || pane >= paneCount()) return;
    panes_[size_t(pane)].setVisible(visible);
    alignPanes();
    legends_[size_t(pane)]->setVisibility(panes_[size_t(pane)].visible());
    syncSourceVisible(pane);
    resetHovers();
    update();
    emit seriesVisibilityChanged(pane);
}

void WdcExpanded::syncSourceVisible(int pane) {
    if (auto* card = qobject_cast<WdcCard*>(source_.data())) card->setSeriesVisible(pane, panes_[size_t(pane)].visible());
}

void WdcExpanded::setXWindow(std::optional<qint64> xMin, std::optional<qint64> xMax, bool padAuto) {
    for (WdcPaneChart& pc : panes_) pc.setWindow(xMin, xMax, padAuto);
    alignPanes();
    if (auto* card = qobject_cast<WdcCard*>(source_.data())) card->setXWindow(xMin, xMax, padAuto);
    resetHovers();
    update();
}

QStringList WdcExpanded::dimmedButtons() {
    std::vector<const ChartInput*> ins;
    std::optional<qint64> ref;
    for (WdcPaneChart& pc : panes_) {
        ins.push_back(pc.input());
        if (const auto r = pc.refMax(); r && (!ref || *r > *ref)) ref = r;
    }
    return dimmedRangeButtons(ins, ref);
}

bool WdcExpanded::pickRange(const QString& button) {
    if (!isRangeButton(button) || dimmedButtons().contains(button)) return false;   // BEH §6.3: dimmed = no-op
    std::optional<qint64> ref;
    for (const WdcPaneChart& pc : panes_)
        if (const auto r = pc.refMax(); r && (!ref || *r > *ref)) ref = r;
    button_ = button;
    const XWindow w = windowForCard(button, ref, allExact_);
    setXWindow(w.xMin, w.xMax, w.padAuto);
    if (source_) source_->setProperty(kRangeButtonProperty, button);
    emit rangePicked(button);
    return true;
}

void WdcExpanded::closeOverlay() {
    emit closed();
    QWidget* view = parentWidget();
    if (view && view->metaObject()->indexOfSlot("close_expanded()") >= 0)
        QMetaObject::invokeMethod(view, "close_expanded", Qt::DirectConnection);
    hide();
    deleteLater();
}

QString WdcExpanded::exportFileName() const {
    QString t = th::displayName(title_);
    t.replace(QRegularExpression(QStringLiteral("[/\\\\:*?\"<>|]")), QStringLiteral("_"));
    return (t.isEmpty() ? QStringLiteral("widata_chart") : t) + QStringLiteral(".png");
}

QImage WdcExpanded::exportImage(qreal dpr) {
    const ExpandedGeom g = geometryModel();
    const QRectF area(g.body.x(), g.paneBoxes.front().y(), g.body.width(),
                      g.paneLegends.back().bottom() - g.paneBoxes.front().y());
    QImage img((area.size() * dpr).toSize(), QImage::Format_ARGB32_Premultiplied);
    img.setDevicePixelRatio(dpr);
    img.fill(Qt::white);
    QPainter p(&img);
    p.setRenderHint(QPainter::Antialiasing, true);
    p.setRenderHint(QPainter::TextAntialiasing, true);
    p.translate(-area.topLeft());
    for (int k = 0; k < paneCount(); ++k) {
        const QRectF d = g.paneDividers[size_t(k)];
        if (!d.isEmpty()) p.fillRect(QRectF(d.x(), std::round(d.y() * dpr) / dpr, d.width(), th::hairline(dpr)), th::color(th::kBorder));
        panes_[size_t(k)].paint(p, g.paneCharts[size_t(k)]);
        panes_[size_t(k)].paintExportLegend(p, g.paneLegends[size_t(k)], LegendStyle::Expanded, zDesc_, dpr);
    }
    return img;
}

void WdcExpanded::copyImageToClipboard() {
    QGuiApplication::clipboard()->setImage(exportImage(devicePixelRatioF() > 0 ? devicePixelRatioF() : 2.0));
    emit imageCopied();
    showTip(QStringLiteral("Đã chép ảnh biểu đồ vào clipboard"), geometryModel().share);
    QTimer::singleShot(kCopiedTipMs, this, [this] { if (tip_) tip_->hide(); });
}

bool WdcExpanded::saveImage(const QString& path) { return exportImage(2.0).save(path, "PNG"); }

bool WdcExpanded::trigger(const QString& part) {
    if (part == QLatin1String("share")) activate({Part::Share, -1});
    else if (part == QLatin1String("download")) activate({Part::Download, -1});
    else if (part == QLatin1String("close")) activate({Part::Close, -1});
    else if (part == QLatin1String("calendar")) activate({Part::Calendar, -1});
    else if (isRangeButton(part)) return pickRange(part);
    else return false;
    return true;
}

void WdcExpanded::activate(const HitRes& h) {
    switch (h.part) {
    case Part::Close:
    case Part::Backdrop: closeOverlay(); break;
    case Part::Range:
        if (h.index >= 0 && h.index < int(rangeButtons().size())) pickRange(rangeButtons()[h.index]);
        break;
    case Part::Share: copyImageToClipboard(); break;
    case Part::Download: {
        const QImage img = exportImage(2.0);
        const QString name = exportFileName();
        if (isSignalConnected(QMetaMethod::fromSignal(&WdcExpanded::exportPngRequested))) {
            emit exportPngRequested(img, name);
            break;
        }
        const QString path = QFileDialog::getSaveFileName(this, kDownloadText, QDir::home().filePath(name),
                                                          QStringLiteral("PNG (*.png)"));
        if (!path.isEmpty()) (void)QtConcurrent::run([img, path] { img.save(path, "PNG"); });
        break;
    }
    case Part::Calendar: break;   // date picker: Đợt 2 (BEH §6.4)
    default: break;
    }
}

// ---- events --------------------------------------------------------------------------------------------------------

WdcExpanded::HitRes WdcExpanded::hitAt(const QPointF& pos) const {
    const ExpandedGeom g = geometryModel();
    const QPointF c = g.close.center();
    if (QLineF(c, pos).length() <= g.close.width() / 2) return {Part::Close, -1};
    if (!g.box.contains(pos)) return {Part::Backdrop, -1};
    if (g.calendarBtn.contains(pos)) return {Part::Calendar, -1};
    for (int i = 0; i < int(g.buttons.size()); ++i)
        if (g.buttons[size_t(i)].rect.contains(pos)) return {Part::Range, i};
    if (g.share.contains(pos)) return {Part::Share, -1};
    if (g.download.contains(pos)) return {Part::Download, -1};
    for (int k = 0; k < int(g.paneCharts.size()); ++k)
        if (g.paneCharts[size_t(k)].contains(pos)) return {Part::Chart, k};
    return {Part::Box, -1};
}

void WdcExpanded::mouseMoveEvent(QMouseEvent* e) {
    const QPointF pos = e->position();
    const HitRes h = hitAt(pos);
    if (!(h == hover_)) {
        hover_ = h;
        if (h.part == Part::Calendar) tipTimer_->start();
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
    if (chart >= 0)
        emit chartMouse(chart, int(QEvent::MouseMove), pos - chartRect(chart).topLeft(), e->buttons());
    const bool hand = h.part == Part::Close || h.part == Part::Calendar || h.part == Part::Range ||
                      h.part == Part::Share || h.part == Part::Download;   // dimmed range buttons keep the pointer
    if (press_.part != Part::Chart) setCursor(hand ? Qt::PointingHandCursor : Qt::ArrowCursor);
}

void WdcExpanded::mousePressEvent(QMouseEvent* e) {
    const QPointF pos = e->position();
    press_ = e->button() == Qt::LeftButton ? hitAt(pos) : HitRes{};
    if (press_.part == Part::Chart)
        emit chartMouse(press_.index, int(QEvent::MouseButtonPress), pos - chartRect(press_.index).topLeft(), e->buttons());
    update();
}

void WdcExpanded::mouseReleaseEvent(QMouseEvent* e) {
    const QPointF pos = e->position();
    const HitRes pressed = press_;
    press_ = {};
    if (pressed.part == Part::Chart) {
        emit chartMouse(pressed.index, int(QEvent::MouseButtonRelease), pos - chartRect(pressed.index).topLeft(), e->buttons());
        return;
    }
    update();
    if (pressed.part != Part::None && hitAt(pos) == pressed) activate(pressed);
}

void WdcExpanded::leaveEvent(QEvent*) {
    hover_ = {};
    tipTimer_->stop();
    if (hoverChart_ >= 0) emit chartLeft(hoverChart_);
    hoverChart_ = -1;
    unsetCursor();
    update();
}

void WdcExpanded::keyPressEvent(QKeyEvent* e) {
    if (e->key() == Qt::Key_Escape) {
        e->accept();
        closeOverlay();
        return;
    }
    QWidget::keyPressEvent(e);
}

void WdcExpanded::resizeEvent(QResizeEvent* e) {
    QWidget::resizeEvent(e);
    placeLegends();
}

void WdcExpanded::showTip(const QString& text, const QRectF& anchor) {
    if (!tip_) tip_ = new WdcPopover(this, WdcPopover::Mode::TitleTip);
    tip_->setLines({text});
    tip_->showAt(mapToGlobal(QPointF(anchor.x(), anchor.bottom() + th::kTitleTipGap)).toPoint());
}

// ---- painting ------------------------------------------------------------------------------------------------------

void WdcExpanded::paintHeader(QPainter& p, const ExpandedGeom& g, qreal dpr) {
    // title: 16/500 uppercase #21232E, ellipsis inside padding-right 16 (UI §4.3 #1). WiData serves Inter 400/500 as
    // static opsz 14 subsets, also at 16 px: outlines and widths of webFont / webTextExactWidth (FACT 230.41, chart page)
    p.setFont(webFont(kTitlePx, kTitleWeight));
    p.setPen(th::color(th::kTextPrimary));
    const QString title = upper_ ? th::cardTitleText(title_) : th::displayName(title_);
    th::drawWebText(p, QPointF(g.title.x(), g.titleBaseline),
                    webElide(title, kTitlePx, kTitleWeight, g.title.width() - kTitlePadRight), kTitleWeight);
    // calendar box (inert in wave 1)
    p.fillPath(wdcex_round(g.calendarBox, kBtnRadius), th::color(th::kBgSubtle));
    paintIcon(p, Icon::CalendarExpanded20, g.calendarIcon, th::color(th::kTextSecondary));
    for (const QRectF& d : {g.divider1, g.divider2})   // 1 device px, #DEDEDE (MẶC ĐỊNH, UI §4.3 #3)
        p.fillRect(QRectF(std::round(d.x() * dpr) / dpr, d.y(), th::hairline(dpr), d.height()), th::color(th::kBorder));
    // range buttons
    QStringList dim;
    for (WdcPaneChart& pc : panes_) (void)pc.input();
    dim = dimmedButtons();
    for (int i = 0; i < int(g.buttons.size()); ++i) {
        const RangeButtonGeom& b = g.buttons[size_t(i)];
        paintRangeButton(p, b, b.label == button_, dim.contains(b.label), hover_ == HitRes{Part::Range, i},
                         press_ == HitRes{Part::Range, i});
    }
    // action cluster
    p.fillPath(wdcex_round(g.actions, kBtnRadius), th::color(th::kBgSubtle));
    p.setFont(th::font(kActPx, kActWeight));
    for (const Part part : {Part::Share, Part::Download}) {
        const bool share = part == Part::Share;
        const QRectF r = share ? g.share : g.download;
        const bool hot = hover_.part == part;
        if (hot) {
            paintBoxShadow(p, r, kBtnRadius, wdcex_hoverShadow(), dpr);
            p.fillPath(wdcex_round(r, kBtnRadius), th::color(th::kWhite));
        }
        const QColor fg = th::color(hot ? th::kTextPrimary : th::kTextSecondary);
        paintIcon(p, share ? Icon::Share : Icon::FileDownloadOutlined, share ? g.shareIcon : g.downloadIcon, fg);
        p.setPen(fg);
        th::drawWebText(p, QPointF(share ? g.shareTextX : g.downloadTextX, g.actionBaseline), share ? kShareText : kDownloadText,
                        kActWeight);
    }
}

void WdcExpanded::paintEvent(QPaintEvent*) {
    QPainter p(this);
    p.setRenderHint(QPainter::Antialiasing, true);
    p.setRenderHint(QPainter::TextAntialiasing, true);
    const qreal dpr = devicePixelRatioF() > 0 ? devicePixelRatioF() : 1.0;
    const ExpandedGeom g = geometryModel();
    p.fillRect(g.backdrop, QColor::fromRgba(th::kOverlay));
    p.fillPath(wdcex_round(g.box, kBoxRadius), th::color(th::kBgSurface));
    paintHeader(p, g, dpr);
    for (int k = 0; k < paneCount(); ++k) {
        const QRectF d = g.paneDividers[size_t(k)];
        if (!d.isEmpty()) p.fillRect(QRectF(d.x(), std::round(d.y() * dpr) / dpr, d.width(), th::hairline(dpr)), th::color(th::kBorder));
        panes_[size_t(k)].paint(p, g.paneCharts[size_t(k)]);
        if (overlay_) {
            p.save();
            overlay_(p, k, g.paneCharts[size_t(k)]);
            p.restore();
        }
    }
    // close: white circle 24 centred on the top-right corner, Cancel 24 #21232E (UI §4.3 #7)
    QPainterPath circle;
    circle.addEllipse(g.close);
    p.fillPath(circle, th::color(th::kWhite));
    paintIcon(p, Icon::Cancel, g.close, th::color(th::kTextPrimary));
}

} // namespace fincept::screens::wdc
