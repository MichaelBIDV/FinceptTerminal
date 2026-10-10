// WdcCard.cpp: dashboard card of the WiData clone (package D, đợt 3: gói UI). Geometry: UI §3.1 to §3.3 (FACT on
// the capture DOM, 108 cards); tokens: WdcTheme_p.h; behaviour: BEH §4, DESIGN §6.1, §7.1, §8.4, §16 C4, C16, C18;
// hover: A/HOVER_CSS.md (stylesheet of the reference site). Charts come from WdcRenderService (WdcRender.h) as images.
#include "screens/widata/WdcCard.h"

#include "screens/widata/WdcCache.h"
#include "screens/widata/WdcRange.h"
#include "screens/widata/WdcTheme_p.h"

#include <QEvent>
#include <QFocusEvent>
#include <QKeyEvent>
#include <QMouseEvent>
#include <QPainter>
#include <QPixmap>
#include <QTimer>

#include <algorithm>
#include <cmath>

namespace fincept::screens::wdc {

namespace th = theme;

namespace {

constexpr bool kTitleTipOnlyWhenElided = true; // DESIGN §6.1 "rê tiêu đề bị cắt …" (WiData may show it always)

QPainterPath wdcc_round(const QRectF& r, qreal radius) {
    QPainterPath p;
    p.addRoundedRect(r, std::min(radius, r.width() / 2), std::min(radius, r.height() / 2));
    return p;
}

struct WdcMenuDef { const char* id; const char* text; };
// Gear menu, read-only (BEH §4.3) + "Mở dạng biểu đồ đơn" (DESIGN §16 C4)
const WdcMenuDef wdcc_menu[] = {{"expand", "Phóng to"},
                                {"single", "Mở dạng biểu đồ đơn"},
                                {"png", "Tải ảnh PNG"},
                                {"refresh", "Làm mới dữ liệu"},
                                {"sources", "Thông tin nguồn"}};

} // namespace

Icon cardButtonIcon(const QString& id) {
    if (id == QLatin1String("sync")) return Icon::Cached;
    if (id == QLatin1String("calendar")) return Icon::CalendarTodayOutlined;
    if (id == QLatin1String("expand")) return Icon::CropFreeRounded;
    return Icon::Settings;
}

CardGeom layoutCard(const CardSpec& spec, const QRectF& rect, qreal dpr) {
    CardGeom g;
    const qreal b = th::hairline(dpr);
    g.border = b;
    g.frame = rect;
    const qreal x0 = rect.x() + b + th::kCardPadding, y0 = rect.y() + b + th::kCardPadding;
    const qreal cw = rect.width() - 2 * b - 2 * th::kCardPadding;
    g.content = QRectF(x0, y0, cw, rect.height() - 2 * b - 2 * th::kCardPadding);
    g.header = QRectF(x0, y0, cw, th::kHeaderH);
    const int nb = int(spec.buttons.size());
    const qreal gW = 2 * th::kClusterPad + th::kButtonSize * nb;
    g.cluster = QRectF(x0 + cw - gW, y0, gW, th::kHeaderH);
    g.title = QRectF(x0, y0 + th::kTitleTop, std::max<qreal>(0, cw - th::kClusterMarginLeft - gW), th::kTitleLineH);
    for (int i = 0; i < nb; ++i) {
        CardButtonGeom bg;
        bg.id = spec.buttons[i];
        bg.icon = cardButtonIcon(bg.id);
        bg.button = QRectF(g.cluster.x() + th::kClusterPad + th::kButtonSize * i, y0 + th::kClusterPad, th::kButtonSize,
                           th::kButtonSize);
        const bool sync = bg.icon == Icon::Cached;
        const qreal inset = sync ? th::kSyncIconInset : th::kIconInset, sz = sync ? th::kSyncIconSize : th::kIconSize;
        bg.iconRect = QRectF(bg.button.x() + inset, bg.button.y() + inset, sz, sz);
        g.buttons.push_back(bg);
    }
    // body: JS height = card - 60, each pane = [chart][12][legend 36], dividers margin 12 0 8 + border (UI §3.3)
    const int n = std::max(1, int(spec.panes.size()));
    const qreal per = th::kChartToLegend + th::kLegendH, div = th::kDividerTop + b + th::kDividerBottom;
    const qreal paneH = std::max<qreal>(0, (rect.height() - th::kBodyReserve - per * n - div * (n - 1)) / n);
    qreal top = y0 + th::kHeaderH + th::kBodyPadTop;
    for (int k = 0; k < n; ++k) {
        CardPaneGeom pg;
        if (k > 0) {
            pg.divider = QRectF(x0, top + th::kDividerTop, cw, b);
            top = pg.divider.bottom() + th::kDividerBottom;
        }
        pg.pane = QRectF(x0, top, cw, paneH);
        // Highcharts getChartSize: width = floor of the fractional box, height = offsetHeight (rounded)
        pg.chart = QRectF(x0, top, std::floor(cw + 1e-6), std::floor(paneH + 0.5));
        pg.legend = QRectF(x0, top + paneH + th::kChartToLegend, cw, th::kLegendH);
        top = pg.legend.bottom();
        g.panes.push_back(pg);
    }
    return g;
}

// ---- widget --------------------------------------------------------------------------------------------------

WdcCard::WdcCard(QWidget* parent) : QWidget(parent), spec_(std::make_shared<const CardSpec>()) {
    setMouseTracking(true);
    setFocusPolicy(Qt::TabFocus);
    setAttribute(Qt::WA_StyledBackground, false);
    tipTimer_ = new QTimer(this);
    tipTimer_->setSingleShot(true);
    tipTimer_->setInterval(th::kTitleTipDelayMs);
    connect(tipTimer_, &QTimer::timeout, this, &WdcCard::showTitleTip);
}

WdcCard::~WdcCard() {
    withdrawPending();
    for (const PaneState& ps : panes_) unregisterProcessedPoints(&ps.model);
    if (table_) unregisterDashTiers(*table_);
}

void WdcCard::setSpec(const CardSpec& spec, const QString& dashId) {
    auto copy = std::make_shared<CardSpec>(spec);
    if (copy->panes.empty()) copy->panes.push_back(PaneSpec{});
    spec_ = std::move(copy);
    dashId_ = dashId;
    titleShown_ = QString();
    for (WdcPopover* w : {tip_.data(), menu_.data(), info_.data()})
        if (w) w->hide();
    for (PaneState& ps : panes_) {
        delete ps.legend;
        unregisterProcessedPoints(&ps.model);
    }
    panes_.clear();
    panes_.resize(spec_->panes.size());
    for (size_t k = 0; k < panes_.size(); ++k) panes_[k].visible.assign(spec_->panes[k].series.size(), true);
    shownKey_.clear();
    rebuildLegends();
    refreshMissing();
    invalidate();
}

void WdcCard::setData(std::shared_ptr<const DashData> data) {
    if (data != table_) {   // tier_spans of the grid tooltips: " · EST" / " · UNVERIFIED" per point (DESIGN §16 C19)
        if (data) registerDashTiers(*data);
        if (table_) unregisterDashTiers(*table_);
    }
    table_ = std::move(data);
    refreshLegendEntries();
    refreshMissing();
    invalidate();
}

void WdcCard::setLoading(bool loading) {
    if (loading == loading_) return;
    loading_ = loading;
    update();
}

void WdcCard::refreshMissing() {
    for (size_t k = 0; k < panes_.size() && k < spec_->panes.size(); ++k) {
        bool missing = true;
        for (const SeriesRef& r : spec_->panes[k].series)
            if (renderHasNumbers(dataFor(r.sid))) { missing = false; break; }
        panes_[k].allMissing = missing;
        if (missing) panes_[k].image = QImage();
    }
}

void WdcCard::setXWindow(std::optional<qint64> xMin, std::optional<qint64> xMax, bool padAuto) {
    xMin_ = xMin;
    xMax_ = xMax;
    padAuto_ = padAuto;
    invalidate();
}

std::optional<qint64> WdcCard::refMax() const {
    std::optional<qint64> best;
    for (const PaneSpec& cp : spec_->panes)
        for (const SeriesRef& r : cp.series) {
            const SeriesData* d = dataFor(r.sid);
            if (!renderHasNumbers(d)) continue;
            for (auto it = d->pts.rbegin(); it != d->pts.rend(); ++it)
                if (std::isfinite(it->y())) {
                    const qint64 t = qint64(it->x());
                    if (!best || t > *best) best = t;
                    break;
                }
        }
    return best;
}

const SeriesData* WdcCard::dataFor(const QString& sid) const { return renderSeriesData(table_.get(), sid); }

void WdcCard::rebuildLegends() {
    const LegendStyle style = spec_->legendStyle == QLatin1String("macro") ? LegendStyle::Macro : LegendStyle::Aio;
    for (int k = 0; k < int(panes_.size()); ++k) {
        auto* lg = new WdcLegend(this);
        lg->setLegendStyle(style);
        connect(lg, &WdcLegend::toggled, this, [this, k](int refIndex, bool vis) {
            std::vector<bool>& v = panes_[size_t(k)].visible;
            if (refIndex >= 0 && refIndex < int(v.size())) v[size_t(refIndex)] = vis;
            invalidate();
            emit seriesVisibilityChanged(spec_->key, k);
        });
        connect(lg, &WdcLegend::resetRequested, this, [this, k] {
            std::vector<bool>& v = panes_[size_t(k)].visible;
            std::fill(v.begin(), v.end(), true);
            panes_[size_t(k)].legend->setVisibility(v);
            invalidate();
            emit seriesVisibilityChanged(spec_->key, k);
        });
        lg->show();
        panes_[size_t(k)].legend = lg;
    }
    refreshLegendEntries();
    placeChildren();
}

void WdcCard::refreshLegendEntries() {
    for (size_t k = 0; k < panes_.size(); ++k) {
        const std::vector<SeriesRef>& refs = spec_->panes[k].series;
        std::vector<LegendEntry> entries;
        for (int i : legendOrder(refs, spec_->legendOrder == QLatin1String("zIndex_desc"))) {
            LegendEntry e;
            e.ref = &refs[size_t(i)];
            e.refIndex = i;
            if (table_) {
                const auto it = table_->series.constFind(refs[size_t(i)].sid);
                if (it != table_->series.cend()) e.entry = &it.value();
            }
            entries.push_back(e);
        }
        panes_[k].legend->setEntries(std::move(entries), table_);
        panes_[k].legend->setVisibility(panes_[k].visible);
    }
}

void WdcCard::placeChildren() {
    geom_ = layoutCard(*spec_, QRectF(rect()), devicePixelRatioF());
    for (size_t k = 0; k < panes_.size() && k < geom_.panes.size(); ++k)
        if (panes_[k].legend) panes_[k].legend->setContainerRect(geom_.panes[k].legend);
}

void WdcCard::invalidate() {
    const bool was = dirty_;
    dirty_ = true;
    if (!was) emit chartModelChanged();
    scheduleRender();
    update();
}

CardRenderParams WdcCard::currentParams() const {
    CardRenderParams p;
    const qreal dpr = devicePixelRatioF();
    const CardGeom g = layoutCard(*spec_, QRectF(rect()), dpr);
    p.dpr = dpr;
    p.xMin = xMin_;
    p.xMax = xMax_;
    p.padAuto = padAuto_;
    for (size_t k = 0; k < panes_.size(); ++k) {
        p.visible.push_back(panes_[k].visible);
        const QRectF cr = k < g.panes.size() ? g.panes[k].chart : QRectF();
        p.sizes.push_back(cr.size());
        // sub-device-pixel part of the chart origin, so the blitted image lands on the same pixels as direct painting
        p.offsets.emplace_back(cr.x() - std::floor(cr.x() * dpr + 1e-6) / dpr, cr.y() - std::floor(cr.y() * dpr + 1e-6) / dpr);
    }
    return p;
}

void WdcCard::setLayouts(const std::vector<PaneLayout>& layouts, const CardRenderParams& p) {
    for (size_t k = 0; k < panes_.size() && k < layouts.size(); ++k) {
        PaneState& ps = panes_[k];
        ps.effSpec = layouts[k].effSpec;
        ps.model = layouts[k].model;
        registerProcessedPoints(&ps.model, layouts[k].processed);   // grouped isStock points for hitTest (C21)
        ps.input = renderPaneInput(spec_->panes[k], &ps.effSpec, table_.get(), p, int(k));
    }
}

void WdcCard::ensureLayout() {
    if (!dirty_) return;
    const CardRenderParams p = currentParams();
    geom_ = layoutCard(*spec_, QRectF(rect()), p.dpr);
    const QByteArray key = cardRenderKey(dashId_, *spec_, table_.get(), p);
    if (table_)
        if (auto r = WdcRenderService::instance().cached(key)) { // the worker already laid this out
            adopt(r, key, p);
            if (!dirty_) return;
        }
    setLayouts(layoutCardPanes(*spec_, table_.get(), p), p);   // synchronous path (hover, popover, harness)
    dirty_ = false;
}

// ---- off-thread rendering (DESIGN §16 C18) ----------------------------------------------------------------------

void WdcCard::scheduleRender() {
    if (renderQueued_) return;
    renderQueued_ = true;   // coalesce setSpec + setData + setXWindow + resize of one event-loop turn into one job
    QMetaObject::invokeMethod(this, [this] { renderQueued_ = false; startRender(); }, Qt::QueuedConnection);
}

void WdcCard::withdrawPending() {
    if (!pendingKey_.isEmpty())
        if (WdcRenderService* svc = WdcRenderService::existing()) svc->withdraw(pendingKey_, waiter_);
    pendingKey_.clear();
    waiter_ = 0;
}

void WdcCard::startRender() {
    if (!table_ || width() <= 0 || height() <= 0) {
        withdrawPending();
        return;
    }
    const CardRenderParams p = currentParams();
    const QByteArray key = cardRenderKey(dashId_, *spec_, table_.get(), p);
    if (key == shownKey_ || key == pendingKey_) return;
    withdrawPending();
    WdcRenderService& svc = WdcRenderService::instance();
    if (auto r = svc.cached(key)) return adopt(r, key, p);
    if (std::all_of(panes_.begin(), panes_.end(), [](const PaneState& ps) { return ps.allMissing; })) {
        shownKey_ = key;   // nothing to paint: every pane says "[CẦN DATA]"
        emit renderReady();
        return;
    }
    pendingKey_ = key;
    QPointer<WdcCard> self(this);
    const QByteArray disk =
        cacheTag_.isEmpty() ? QByteArray() : diskRenderKey(cacheTag_, cardRenderKey(dashId_, *spec_, QByteArray("build"), p));
    waiter_ = svc.submit(
        key, spec_, table_, p, renderPriority_, this,
        [self, key, p](std::shared_ptr<const CardRender> r) {
            if (!self || key != self->pendingKey_) return;
            self->pendingKey_.clear();
            self->waiter_ = 0;
            self->adopt(r, key, p);
        },
        disk);
}

void WdcCard::adopt(const std::shared_ptr<const CardRender>& r, const QByteArray& key, const CardRenderParams& p) {
    if (!r || r->panes.size() != panes_.size()) return;
    const qreal dpr = p.dpr > 0 ? p.dpr : 1.0;
    const CardGeom g = layoutCard(*spec_, QRectF(rect()), dpr);
    for (size_t k = 0; k < panes_.size(); ++k) {
        PaneState& ps = panes_[k];
        ps.image = k < r->images.size() ? r->images[k] : QImage();
        const QRectF cr = k < g.panes.size() ? g.panes[k].chart : QRectF();
        ps.imageOrigin = QPointF(std::floor(cr.x() * dpr + 1e-6) / dpr, std::floor(cr.y() * dpr + 1e-6) / dpr);
    }
    shownKey_ = key;
    lastPaintMs_ = r->paintMs;
    const bool current = dirty_ && key == cardRenderKey(dashId_, *spec_, table_.get(), currentParams());
    if (current) {   // the models of the current parameters: no synchronous layout needed any more
        setLayouts(r->panes, p);
        dirty_ = false;
    }
    QRect area;   // only the chart areas changed: header and legends are not repainted
    for (const CardPaneGeom& pg : g.panes) area |= pg.chart.toAlignedRect().adjusted(-1, -1, 1, 1);
    update(area);
    emit renderReady();
}

void WdcCard::renderNow() {
    if (!table_ || width() <= 0 || height() <= 0) return;
    const CardRenderParams p = currentParams();
    const QByteArray key = cardRenderKey(dashId_, *spec_, table_.get(), p);
    if (key == shownKey_) return;
    withdrawPending();
    adopt(WdcRenderService::instance().renderNow(key, *spec_, table_, p), key, p);
}

bool WdcCard::rendered() const {
    if (!table_) return !loading_;
    if (std::all_of(panes_.begin(), panes_.end(), [](const PaneState& ps) { return ps.allMissing; })) return true;
    return !shownKey_.isEmpty() && shownKey_ == cardRenderKey(dashId_, *spec_, table_.get(), currentParams());
}

QRectF WdcCard::chartRect(int pane) const {
    const CardGeom g = layoutCard(*spec_, QRectF(rect()), devicePixelRatioF());
    return pane >= 0 && pane < int(g.panes.size()) ? g.panes[size_t(pane)].chart : QRectF();
}

bool WdcCard::paneAllMissing(int pane) const {
    if (pane < 0 || pane >= paneCount()) return true;
    for (const SeriesRef& r : spec_->panes[size_t(pane)].series)
        if (renderHasNumbers(dataFor(r.sid))) return false;
    return true;
}

const ChartModel* WdcCard::chartModel(int pane) {
    ensureLayout();
    return pane >= 0 && pane < int(panes_.size()) ? &panes_[size_t(pane)].model : nullptr;
}

const ChartInput* WdcCard::chartInput(int pane) {
    ensureLayout();
    return pane >= 0 && pane < int(panes_.size()) ? &panes_[size_t(pane)].input : nullptr;
}

std::vector<bool> WdcCard::seriesVisible(int pane) const {
    return pane >= 0 && pane < int(panes_.size()) ? panes_[size_t(pane)].visible : std::vector<bool>();
}

void WdcCard::setSeriesVisible(int pane, const std::vector<bool>& visible) {
    if (pane < 0 || pane >= int(panes_.size())) return;
    std::vector<bool>& v = panes_[size_t(pane)].visible;
    for (size_t i = 0; i < v.size(); ++i) v[i] = i < visible.size() ? bool(visible[i]) : true;
    panes_[size_t(pane)].legend->setVisibility(v);
    invalidate();
}

void WdcCard::setOverlayPainter(OverlayPainter fn) {
    overlay_ = std::move(fn);
    update();
}

CardGeom WdcCard::geometryModel() const { return layoutCard(*spec_, QRectF(rect()), devicePixelRatioF()); }

WdcLegend* WdcCard::legend(int pane) const {
    return pane >= 0 && pane < int(panes_.size()) ? panes_[size_t(pane)].legend : nullptr;
}

QImage WdcCard::renderImage(qreal dpr) {
    QImage img((QSizeF(size()) * dpr).toSize(), QImage::Format_ARGB32_Premultiplied);
    img.setDevicePixelRatio(dpr);
    img.fill(Qt::transparent);
    directPaint_ = true;   // charts painted straight into the export at its own DPR (no cached image rescaled)
    render(&img);
    directPaint_ = false;
    return img;
}

// ---- painting ------------------------------------------------------------------------------------------------

void WdcCard::refreshGeom() { geom_ = layoutCard(*spec_, QRectF(rect()), devicePixelRatioF()); }

void WdcCard::paintEvent(QPaintEvent*) {
    refreshGeom();   // cheap; the charts are laid out by the render service
    if (directPaint_) ensureLayout();
    QPainter p(this);
    p.setRenderHint(QPainter::Antialiasing, true);
    p.setRenderHint(QPainter::TextAntialiasing, true);
    const qreal dpr = p.device()->devicePixelRatioF();
    paintHairlineBox(p, geom_.frame.adjusted(0, 0, 0, 0), th::kCardRadius, th::color(th::kBgSurface),
                     th::color(th::kBorder), dpr);
    paintHeader(p);
    for (int k = 0; k < int(panes_.size()); ++k) {
        const QRectF d = k < int(geom_.panes.size()) ? geom_.panes[size_t(k)].divider : QRectF();
        if (!d.isEmpty()) { // snapped to the device grid like Chromium's border
            const qreal y = std::round(d.y() * dpr) / dpr;
            p.fillRect(QRectF(d.x(), y, d.width(), th::hairline(dpr)), th::color(th::kBorder));
        }
        paintPane(p, k);
    }
}

void WdcCard::paintHeader(QPainter& p) {
    const qreal dpr = p.device()->devicePixelRatioF();
    if (!geom_.buttons.empty()) p.fillPath(wdcc_round(geom_.cluster, th::kClusterRadius), th::color(th::kBgSubtle));
    for (int i = 0; i < int(geom_.buttons.size()); ++i) {
        const CardButtonGeom& bg = geom_.buttons[size_t(i)];
        // HOVER_CSS.md: `.css-yp4adf .MuiButtonBase-root:hover` (wins over the button's own rule): white background,
        // box-shadow rgba(33,35,46,.06) 0 0 6px 0, icon #21232E. No :active rule, so pressed looks like hover.
        const bool hot = i == hoverBtn_ || (i == pressBtn_ && i == hoverBtn_);
        if (hot) {
            paintBoxShadow(p, bg.button, th::kButtonRadius, shadowHeaderBtn(), dpr);
            p.fillPath(wdcc_round(bg.button, th::kButtonRadius), th::color(th::kWhite));
        }
        paintIcon(p, bg.icon, bg.iconRect, th::color(hot ? th::kTextPrimary : th::kTextSecondary));
        if (i == focusBtn_ && hasFocus()) {
            p.save();
            p.setPen(QPen(th::color(th::kFocusRing), 1));
            p.setBrush(Qt::NoBrush);
            p.drawRoundedRect(bg.button.adjusted(0.5, 0.5, -0.5, -0.5), th::kButtonRadius, th::kButtonRadius);
            p.restore();
        }
    }
    const QFont f = th::font(th::kTitlePx, th::kTitleWeight);
    p.setFont(f);
    p.setPen(th::color(th::kTextPrimary));
    if (titleShownW_ != geom_.title.width() || titleShown_.isNull()) {   // the ellipsis search is not free: cache it
        titleShown_ = th::exactElide(QFontMetricsF(th::exactFont(th::kTitlePx, th::kTitleWeight)),
                                     th::cardTitleText(spec_->title), th::kTitlePx, geom_.title.width(), nullptr,
                                     th::kTitleWeight);
        titleShownW_ = geom_.title.width();
    }
    const QString& shown = titleShown_;
    p.drawText(QPointF(geom_.title.x(), geom_.title.y() + th::blinkBaseline(th::kTitlePx, th::kTitleLineH, dpr)), shown);
}

void WdcCard::paintPane(QPainter& p, int k) {
    if (k >= int(geom_.panes.size())) return;
    const PaneState& ps = panes_[size_t(k)];
    const QRectF cr = geom_.panes[size_t(k)].chart;
    const qreal dpr = p.device()->devicePixelRatioF();
    if (!table_ && loading_) {
        // "đang nạp" (DESIGN §16 C18): blank pane, no "[CẦN DATA]" flash before the data arrives
    } else if (ps.allMissing) { // DESIGN §8.4: no axis, no grid, label in the middle of the chart area
        const QFont f = th::font(th::kNeedDataPx, th::kNeedDataWeight);
        const QString s = QStringLiteral("[CẦN DATA]");
        p.setFont(f);
        p.setPen(th::color(th::kNeedDataText));
        const qreal w = th::textWidth(QFontMetricsF(f), s, th::kNeedDataWeight);
        const qreal lh = th::blinkNormalLineH(th::kNeedDataPx, dpr);
        th::drawWebText(p, QPointF(cr.center().x() - w / 2, cr.center().y() - lh / 2 + th::blinkAscent(th::kNeedDataPx, dpr)),
                        s, th::kNeedDataWeight);
    } else if (directPaint_) {
        p.save();
        p.translate(cr.topLeft());
        p.setClipRect(QRectF(QPointF(0, 0), cr.size()));
        paintChart(p, ps.model, ps.input);
        p.restore();
    } else if (!ps.image.isNull()) {
        // image of the render service, aligned on the device grid (WdcRender.h); a stale one stays until the new
        // window/size is rendered, so the pane never flashes empty
        p.save();
        p.setClipRect(cr);
        if (qFuzzyCompare(ps.image.devicePixelRatio(), dpr)) p.drawImage(ps.imageOrigin, ps.image);
        else p.drawImage(QRectF(ps.imageOrigin, QSizeF(ps.image.size()) / ps.image.devicePixelRatio()), ps.image);
        p.restore();
    }
    if (overlay_) {
        p.save();
        overlay_(p, k, cr);
        p.restore();
    }
}

// ---- interaction ---------------------------------------------------------------------------------------------

int WdcCard::buttonAt(const QPointF& pos) const {
    for (int i = 0; i < int(geom_.buttons.size()); ++i)
        if (geom_.buttons[size_t(i)].button.contains(pos)) return i;
    return -1;
}

int WdcCard::chartAt(const QPointF& pos) const {
    for (int k = 0; k < int(geom_.panes.size()); ++k)
        if (geom_.panes[size_t(k)].chart.contains(pos)) return k;
    return -1;
}

void WdcCard::mouseMoveEvent(QMouseEvent* e) {
    refreshGeom();
    const QPointF pos = e->position();
    const int b = buttonAt(pos);
    if (b != hoverBtn_) { hoverBtn_ = b; update(); }
    const bool onTitle = geom_.title.contains(pos);
    if (onTitle != titleHover_) {
        titleHover_ = onTitle;
        if (onTitle) tipTimer_->start();
        else hideTitleTip();
    }
    const int c = chartAt(pos);
    if (c != hoverChart_ && hoverChart_ >= 0) emit chartLeft(hoverChart_);
    hoverChart_ = c;
    if (c >= 0) emit chartMouse(c, int(QEvent::MouseMove), pos - geom_.panes[size_t(c)].chart.topLeft(), e->buttons());
    setCursor(b >= 0 ? Qt::PointingHandCursor : Qt::ArrowCursor);
}

void WdcCard::mousePressEvent(QMouseEvent* e) {
    refreshGeom();
    const QPointF pos = e->position();
    hideTitleTip();
    pressBtn_ = e->button() == Qt::LeftButton ? buttonAt(pos) : -1;
    if (pressBtn_ >= 0) { update(); return; }
    const int c = chartAt(pos);
    if (c >= 0) emit chartMouse(c, int(QEvent::MouseButtonPress), pos - geom_.panes[size_t(c)].chart.topLeft(), e->buttons());
}

void WdcCard::mouseReleaseEvent(QMouseEvent* e) {
    const QPointF pos = e->position();
    const int pressed = pressBtn_;
    pressBtn_ = -1;
    if (pressed >= 0) {
        update();
        if (buttonAt(pos) == pressed) activateButton(pressed);
        return;
    }
    const int c = chartAt(pos);
    if (c >= 0) emit chartMouse(c, int(QEvent::MouseButtonRelease), pos - geom_.panes[size_t(c)].chart.topLeft(), e->buttons());
}

void WdcCard::leaveEvent(QEvent*) {
    hoverBtn_ = -1;
    titleHover_ = false;
    hideTitleTip();
    if (hoverChart_ >= 0) emit chartLeft(hoverChart_);
    hoverChart_ = -1;
    unsetCursor();
    update();
}

void WdcCard::keyPressEvent(QKeyEvent* e) {
    const int n = int(geom_.buttons.size());
    switch (e->key()) {
    case Qt::Key_Left: if (n) { focusBtn_ = focusBtn_ < 0 ? 0 : std::max(0, focusBtn_ - 1); update(); } return;
    case Qt::Key_Right: if (n) { focusBtn_ = focusBtn_ < 0 ? 0 : std::min(n - 1, focusBtn_ + 1); update(); } return;
    case Qt::Key_Return: case Qt::Key_Enter: case Qt::Key_Space:
        if (focusBtn_ >= 0 && focusBtn_ < n) activateButton(focusBtn_);
        return;
    default: QWidget::keyPressEvent(e);
    }
}

void WdcCard::focusInEvent(QFocusEvent* e) {
    refreshGeom();
    const int n = int(geom_.buttons.size());
    // ring only for keyboard focus (:focus-visible); a click or window activation does not show it
    focusBtn_ = n == 0 ? -1
                : e->reason() == Qt::TabFocusReason     ? 0
                : e->reason() == Qt::BacktabFocusReason ? n - 1
                                                        : -1;
    update();
    QWidget::focusInEvent(e);
}

void WdcCard::focusOutEvent(QFocusEvent* e) {
    focusBtn_ = -1;
    update();
    QWidget::focusOutEvent(e);
}

bool WdcCard::focusNextPrevChild(bool next) {
    const int n = int(geom_.buttons.size()), to = focusBtn_ + (next ? 1 : -1);
    if (hasFocus() && focusBtn_ >= 0 && to >= 0 && to < n) {
        focusBtn_ = to;
        update();
        return true;
    }
    return QWidget::focusNextPrevChild(next);
}

void WdcCard::changeEvent(QEvent* e) {
    if (e->type() == QEvent::DevicePixelRatioChange) {
        placeChildren();
        invalidate();
    }
    QWidget::changeEvent(e);
}

void WdcCard::resizeEvent(QResizeEvent* e) {
    QWidget::resizeEvent(e);
    placeChildren();
    invalidate();
}

void WdcCard::activateButton(int i) {
    if (i < 0 || i >= int(geom_.buttons.size())) return;
    const CardButtonGeom& bg = geom_.buttons[size_t(i)];
    if (bg.id == QLatin1String("calendar")) {
        const QRect anchor(mapToGlobal(bg.button.topLeft()).toPoint(), bg.button.size().toSize());
        emit calendarRequested(spec_->key, anchor);
    } else if (bg.id == QLatin1String("expand")) {
        emit expandRequested(spec_->key);
    } else if (bg.id == QLatin1String("sync")) {
        emit syncRequested(spec_->key);
    } else {
        openMenu();
    }
}

void WdcCard::openMenu() {
    refreshGeom();
    hideTitleTip();
    if (!menu_) {
        menu_ = new WdcPopover(this, WdcPopover::Mode::Menu);
        std::vector<WdcPopover::Item> items;
        for (const WdcMenuDef& d : wdcc_menu) items.push_back({QString::fromLatin1(d.id), QString::fromUtf8(d.text), true});
        menu_->setItems(items);
        connect(menu_, &WdcPopover::triggered, this, &WdcCard::triggerMenu);
    }
    QRectF anchor = geom_.cluster;
    for (const CardButtonGeom& bg : geom_.buttons)
        if (bg.id == QLatin1String("settings")) anchor = bg.button;
    menu_->showAt(mapToGlobal(QPointF(anchor.left(), anchor.bottom() + 4)).toPoint());
}

void WdcCard::triggerMenu(const QString& id) {
    if (menu_ && menu_->isVisible()) menu_->hide();
    if (id == QLatin1String("expand")) emit expandRequested(spec_->key);
    else if (id == QLatin1String("single")) emit openSingleRequested(spec_->key);
    else if (id == QLatin1String("png")) emit exportPngRequested(spec_->key);
    else if (id == QLatin1String("refresh")) emit refreshRequested(spec_->key);
    else if (id == QLatin1String("sources")) showSourceInfo();
}

void WdcCard::showSourceInfo() {
    QStringList lines;
    lines << QStringLiteral("Thông tin nguồn");
    for (const PaneSpec& cp : spec_->panes)
        for (int i : legendOrder(cp.series, spec_->legendOrder == QLatin1String("zIndex_desc"))) {
            const SeriesRef& r = cp.series[size_t(i)];
            const SeriesEntry* e = nullptr;
            if (table_) {
                const auto it = table_->series.constFind(r.sid);
                if (it != table_->series.cend()) e = &it.value();
            }
            QString s = th::displayName(r.nameRaw) + QStringLiteral(": ");
            if (!e || e->data.status == Status::Missing) s += QStringLiteral("[CẦN DATA]");
            else {
                s += e->meta.sourceName.isEmpty() ? QStringLiteral("[CẦN DATA]") : e->meta.sourceName;
                const QString when = !e->meta.lastUpdated.isEmpty() ? e->meta.lastUpdated : e->asOf;
                if (!when.isEmpty()) s += QStringLiteral(" (") + when + QLatin1Char(')');
            }
            lines << s;
        }
    if (!info_) info_ = new WdcPopover(this, WdcPopover::Mode::Panel);
    info_->setLines(lines);
    QRectF anchor = geom_.cluster;
    for (const CardButtonGeom& bg : geom_.buttons)
        if (bg.id == QLatin1String("settings")) anchor = bg.button;
    info_->showAt(mapToGlobal(QPointF(anchor.left(), anchor.bottom() + 4)).toPoint());
}

void WdcCard::showTitleTip() {
    if (!titleHover_) return;
    if (kTitleTipOnlyWhenElided && !titleElided()) return;
    if (!tip_) tip_ = new WdcPopover(this, WdcPopover::Mode::TitleTip);
    tip_->setLines({th::displayName(spec_->title)});
    const QSizeF fs = tip_->frameSize();
    const QPointF tl(geom_.title.center().x() - fs.width() / 2, geom_.title.bottom() + th::kTitleTipGap);
    tip_->showAt(mapToGlobal(tl).toPoint());
}

void WdcCard::hideTitleTip() {
    tipTimer_->stop();
    if (tip_) tip_->hide();
}

bool WdcCard::titleElided() const {
    const CardGeom g = layoutCard(*spec_, QRectF(rect()), devicePixelRatioF());
    bool elided = false;
    th::exactElide(QFontMetricsF(th::exactFont(th::kTitlePx, th::kTitleWeight)), th::cardTitleText(spec_->title),
                   th::kTitlePx, g.title.width(), &elided, th::kTitleWeight);
    return elided;
}

bool WdcCard::titleTipVisible() const { return tip_ && tip_->isVisible(); }
bool WdcCard::menuVisible() const { return menu_ && menu_->isVisible(); }
bool WdcCard::sourceInfoVisible() const { return info_ && info_->isVisible(); }

QStringList WdcCard::menuItemIds() const {
    QStringList ids;
    for (const WdcMenuDef& d : wdcc_menu) ids << QString::fromLatin1(d.id);
    return ids;
}

} // namespace fincept::screens::wdc
