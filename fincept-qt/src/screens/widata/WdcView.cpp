// WdcView.cpp: page controller of the WiData clone: async loading, tab switching, grid placement,
// custom scrolling (4 px thumb, no QScrollArea so the app QSS cannot restyle it, INT R5), harness API.
// Package E. DESIGN §3 (run flow), §6, §6.1, §8.4; UI §1.3, §2; BEH §7; INT §3.4, R2.
#include "WdcView.h"

#include "WdcCard.h"
#include "WdcFonts.h"
#include "WdcRender.h"
#include "WdcTheme_p.h"
#include "WdcTooltip.h"
#if __has_include("WdcExpanded.h")
#include "WdcExpanded.h"
#define WDCVIEW_HAVE_EXPANDED 1
#endif
#if __has_include("WdcSingle.h")
#include "WdcSingle.h"
#define WDCVIEW_HAVE_SINGLE 1
#endif

#include <QBuffer>
#include <QFileDialog>
#include <QFutureWatcher>
#include <QJsonArray>
#include <QJsonDocument>
#include <QKeyEvent>
#include <QMouseEvent>
#include <QPainter>
#include <QStandardPaths>
#include <QWheelEvent>
#include <QtConcurrent/QtConcurrentRun>

#include <algorithm>
#include <cmath>

namespace fincept::screens::wdc {
namespace {

const QColor kWvThumb(0xC6, 0xCB, 0xD3);   // scrollbar.thumb (UI §5.1)
// Hover of package F repaints the whole chart in its hover state on the UI thread (2 to 3 paints per new point). For
// the dense charts whose paint costs more than this the hover draws the crosshair, its label and the tooltip over the
// chart image instead (no hover marker, no fading of the other series). Since the faster paint of ENG2 (đợt 4) 107 of
// the 110 panes of the current build paint under it (bench_engine 04/10 under load 34: heaviest 51 ms, was 10 s), so
// nearly every card gets the faithful hover again; the budget stays as the safety net (TASKS đợt 4, gói UI2 (8)).
constexpr double kHoverRepaintBudgetMs = 25;

QString wdcview_prefs_path(const QString& p) {   // worker only: QStandardPaths may touch the disk
    if (!p.isEmpty()) return p;
    const QByteArray env = qgetenv("WDC_VIEW_PREFS");
    if (!env.isEmpty()) return QString::fromLocal8Bit(env);
    return QStandardPaths::writableLocation(QStandardPaths::AppConfigLocation) + QStringLiteral("/widata_clone_view.json");
}

QJsonArray wdcview_rect(const QRectF& r) { return {r.x(), r.y(), r.width(), r.height()}; }

class WdcviewScrollBar : public QWidget {   // DESIGN §6.1: width 4, thumb #C6CBD3, radius 2, no track
  public:
    std::function<void(double)> onScroll;
    double pos = 0, content = 0, viewport = 0;
    explicit WdcviewScrollBar(QWidget* parent) : QWidget(parent) { setAttribute(Qt::WA_NoSystemBackground); }
    QRectF thumb() const {
        if (content <= viewport || viewport <= 0) return {};
        const double len = std::max(20.0, viewport * viewport / content);
        const double y = (viewport - len) * pos / (content - viewport);
        return {0, y, double(width()), len};
    }
  protected:
    void paintEvent(QPaintEvent*) override {
        const QRectF t = thumb();
        if (t.isEmpty()) return;
        QPainter g(this);
        g.setRenderHint(QPainter::Antialiasing);
        g.setPen(Qt::NoPen);
        g.setBrush(kWvThumb);
        g.drawRoundedRect(t, 2, 2);
    }
    void mousePressEvent(QMouseEvent* e) override {
        const QRectF t = thumb();
        if (t.isEmpty()) return;
        grab_ = t.contains(e->position()) ? e->position().y() - t.y() : t.height() / 2;
        mouseMoveEvent(e);
    }
    void mouseMoveEvent(QMouseEvent* e) override {
        const QRectF t = thumb();
        if (t.isEmpty() || !(e->buttons() & Qt::LeftButton) || !onScroll) return;
        const double span = viewport - t.height();
        if (span > 0) onScroll((e->position().y() - grab_) / span * (content - viewport));
    }
  private:
    double grab_ = 0;
};

} // namespace

struct WdcView::InitResult {
    BuildState build;
    Loaded<LayoutsDoc> layouts;
    QString dashId;
    Loaded<DashData> dash;
    bool dashTried = false;
    QJsonObject ranges;   // "range" of the prefs (WdcRangeStore::toJson)
};

WdcView::WdcView(QWidget* parent) : QWidget(parent) {
    WdcRenderService::retain();   // the render pool is stopped and awaited when the last view goes (WdcRender.h)
    setAttribute(Qt::WA_OpaquePaintEvent);
    setAutoFillBackground(false);
    setFocusPolicy(Qt::ClickFocus);
    shell_ = new WdcShell(this);
    frame_ = new QWidget(this);
    content_ = new WdcContent(frame_);
    auto* sb = new WdcviewScrollBar(frame_);
    sb->onScroll = [this](double y) { set_scroll_y(y); };
    scrollbar_ = sb;
    menu_ = new WdcPopup(this);
    tip_ = new WdcPopup(this);
    connect(shell_, &WdcShell::tabActivated, this, &WdcView::select_dashboard);
    connect(shell_, &WdcShell::menuRequested, this, [this](const QRectF&) { open_tab_menu(); });
    connect(shell_, &WdcShell::tipRequested, this, [this](const QString& t, const QRectF& a) { showTip(t, a); });
    connect(shell_, &WdcShell::tipHidden, tip_, &WdcPopup::dismiss);
    connect(content_, &WdcContent::tipRequested, this, [this](const QString& t, const QRectF& a) {
        showTip(t, a.translated(content_->mapTo(this, QPoint(0, 0))));
    });
    connect(content_, &WdcContent::tipHidden, tip_, &WdcPopup::dismiss);
    connect(menu_, &WdcPopup::triggered, this, [this](const QString& a) {
        if (a == QLatin1String("legacy")) emit legacySourcesRequested();
        else if (a.startsWith(QLatin1String("single:"))) emit singleChartRequested(a.mid(7));
    });
    cardFactory_ = [this](const CardContext& c, QWidget* p) { return makeDefaultCard(c, p); };
#ifdef WDCVIEW_HAVE_EXPANDED
    expandFactory_ = &WdcExpanded::create;   // package F (F2_api.md §1)
#endif
#ifdef WDCVIEW_HAVE_SINGLE
    connect(this, &WdcView::singleChartRequested, this, [this](const QString& id) { openSingleChart(this, id); });
    connect(this, &WdcView::cardSingleRequested, this,
            [this](const QString& d, const QString& k) { openCardSingle(this, d, k); });
#endif
}

WdcView::~WdcView() {
    // Loads of this view run on the global pool (fonts, JSON): short, but ensureFonts() touches QFontDatabase, which
    // must not happen once QGuiApplication is gone (the global pool is only awaited at the end of ~QCoreApplication).
    for (QFutureWatcherBase* w : findChildren<QFutureWatcherBase*>()) w->waitForFinished();
    // before the cards (children) go: no worker may still paint for this page once the view is gone
    WdcRenderService::release();
}

void WdcView::set_state_dir(const QString& dir) {
    stateDir_ = dir;
    if (started_) reload();
}

void WdcView::set_card_factory(CardFactory f) {
    customFactory_ = bool(f);
    cardFactory_ = f ? std::move(f) : CardFactory([this](const CardContext& c, QWidget* p) { return makeDefaultCard(c, p); });
    if (started_) rebuildCards();
}

void WdcView::set_card_hook(CardHook h) {
    cardHook_ = std::move(h);
    if (started_) rebuildCards();
}

QWidget* WdcView::makeDefaultCard(const CardContext& ctx, QWidget* parent) {
    auto* card = new WdcCard(parent);
    card->setSpec(*ctx.card, ctx.dashId);
    card->setLoading(ctx.loading);
    card->setData(ctx.data);
    wireCard(card, ctx);
    const QString dash = ctx.dashId;
    connect(card, &WdcCard::expandRequested, this, [this](const QString& k) { expand_card(k); });
    connect(card, &WdcCard::syncRequested, this, [this, dash](const QString&) { reload_dashboard(dash); });
    connect(card, &WdcCard::refreshRequested, this, [this, dash](const QString&) { reload_dashboard(dash); });
    connect(card, &WdcCard::exportPngRequested, this, [this](const QString& k) { export_card_png(k); });
    connect(card, &WdcCard::openSingleRequested, this, [this, dash](const QString& k) { emit cardSingleRequested(dash, k); });
    connect(card, &WdcCard::calendarRequested, this,
            [this, dash](const QString& k, const QRect& a) { emit calendarRequested(dash, k, a); });
    if (cardHook_) cardHook_(card, ctx);
    return card;
}

void WdcView::applyRange(WdcCard* card) {   // DESIGN §7.2, §7.3: stored button, else the card default (3Y, ...)
    const CardSpec& c = card->spec();
    const QString b = applyCardRange(card, card->dashId(), c.key, c.defaultRange.button, c.allExact, rangeStore_);
    card->setProperty("wdcRangeButton", b);   // read by WdcExpanded (F2_api.md §1)
}

void WdcView::wireCard(WdcCard* card, const CardContext& ctx) {
    card->setCacheTag(cacheTag());
    applyRange(card);
    // tooltip, crosshair and the isStock pan of package F; a new model (window, data, legend, size) drops the hover
    const std::vector<WdcChartHover*> hovers = attachChartHover(card);
    connect(card, &WdcCard::chartModelChanged, card, [hovers] {
        for (WdcChartHover* h : hovers) h->reset();
    });
    card->setOverlayPainter([card, hovers](QPainter& p, int pane, const QRectF& cr) {
        if (pane < 0 || pane >= int(hovers.size()) || !hovers[size_t(pane)]->active()) return;
        WdcChartHover* h = hovers[size_t(pane)];
        // faithful (whole chart in its hover state) when the measured paint fits the budget; before the first image
        // the cost is unknown (0): overlay
        const double cost = card->lastPaintMs();
        if (cost > 0 && cost <= kHoverRepaintBudgetMs) return h->paint(p, cr);
        const ChartModel* m = card->chartModel(pane);
        const ChartInput* in = card->chartInput(pane);
        if (!m || !in || m->allMissing) return;
        const HoverFrame& f = h->frame();
        const double dpr = card->devicePixelRatioF();
        p.save();
        p.setClipRect(cr, Qt::IntersectClip);
        p.translate(cr.topLeft());
        if (f.hit) {
            const CrosshairGeom g = crosshairGeometry(*m, *in, *f.hit, dpr);
            paintCrosshairLines(p, g);
            paintCrosshairLabel(p, g);
        }
        const std::optional<TooltipFrame> tip = f.hit ? tooltipFrame(*m, *in, *f.hit, dpr) : f.tooltip;
        if (tip) paintTooltip(p, *tip, dpr);
        p.restore();
    });
    connect(card, &WdcCard::renderReady, this, &WdcView::checkRendered);
    const QString dash = ctx.dashId;
    connect(card, &WdcCard::calendarRequested, this, [this, card, dash](const QString& k, const QRect& anchor) {
        const CardSpec& c = card->spec();
        openCardRangePopover(card, anchor, dash, k, c.defaultRange.button, c.allExact, &rangeStore_, [this, card, dash, k] {
            card->setProperty("wdcRangeButton", resolveRangeButton(rangeStore_.get(dash, k), card->spec().defaultRange.button));
            savePrefs();
        });
    });
}

QByteArray WdcView::cacheTag() const {   // a build directory is never rewritten: it identifies the data on disk
    if (!build_.ok() || !layouts_ || layouts_->fromLayoutConst) return QByteArray();
    return (build_.buildDir + QLatin1Char('|') + build_.generated).toUtf8();
}

bool WdcView::cards_rendered() const {
    for (const auto& [key, w] : cards_) {
        const auto* card = qobject_cast<const WdcCard*>(w.data());
        if (card && !card->rendered()) return false;
    }
    return true;
}

void WdcView::checkRendered() {
    if (renderedEmitted_ || loading_.value(current_) || !cards_rendered()) return;
    renderedEmitted_ = true;
    emit dashboardRendered(current_);
}

bool WdcView::export_card_png(const QString& cardKey, const QString& pathIn) {
    WdcCard* card = nullptr;
    for (const auto& [key, w] : cards_)
        if (key == cardKey) card = qobject_cast<WdcCard*>(w.data());
    if (!card) return false;
    QString path = pathIn;
    if (path.isEmpty()) {
        QString name = card->spec().title.simplified();
        name.replace(QLatin1Char('/'), QLatin1Char('-'));
        path = QFileDialog::getSaveFileName(this, QStringLiteral("Tải ảnh PNG"), name + QStringLiteral(".png"),
                                            QStringLiteral("PNG (*.png)"));
        if (path.isEmpty()) return false;
    }
    const QImage img = card->renderImage(2.0);
    (void)QtConcurrent::run([img, path] {   // encode + write off the UI thread
        QByteArray bytes;
        QBuffer buf(&bytes);
        buf.open(QIODevice::WriteOnly);
        img.save(&buf, "PNG");
        writeFileCounted(path, bytes, nullptr);
    });
    return true;
}

void WdcView::set_grid_basis_override(std::optional<double> colW, std::optional<double> rowW) {
    colOverride_ = colW;
    rowOverride_ = rowW;
    relayout();
}

void WdcView::start() {
    if (!started_) reload();
}

void WdcView::showEvent(QShowEvent* e) {
    QWidget::showEvent(e);
    start();
}

void WdcView::reload() {
    started_ = true;
    const quint64 gen = ++gen_;
    const QString stateDir = stateDir_.isEmpty() ? defaultStateDir() : stateDir_;
    const QString layoutConst = layoutConstPath_.isEmpty() ? defaultLayoutConstPath() : layoutConstPath_;
    const QString prefs = prefsPath_, want = current_;
    ++pending_;
    auto* w = new QFutureWatcher<InitResult>(this);
    connect(w, &QFutureWatcherBase::finished, this, [this, w, gen] {
        --pending_;
        applyInit(w->result(), gen);
        w->deleteLater();
    });
    w->setFuture(QtConcurrent::run([stateDir, layoutConst, prefs, want]() -> InitResult {
        ensureFonts();
        InitResult r;
        r.build = readCurrent(stateDir);
        r.layouts = loadLayouts(r.build, layoutConst);
        if (!r.layouts.ok()) return r;
        QString last;
        {
            const QByteArray pb = readFileCounted(wdcview_prefs_path(prefs), nullptr);
            const QJsonObject po = QJsonDocument::fromJson(pb).object();
            if (want.isEmpty()) last = po.value(QStringLiteral("last_dash")).toString();
            r.ranges = po.value(QStringLiteral("range")).toObject();
        }
        const LayoutsDoc& doc = *r.layouts.value;
        r.dashId = doc.dash(want) ? want : doc.dash(last) ? last : doc.defaultDash;
        if (!doc.fromLayoutConst && !r.dashId.isEmpty()) {
            r.dash = loadDash(r.build.buildDir, r.dashId);
            r.dashTried = true;
        }
        return r;
    }));
}

void WdcView::applyInit(const InitResult& r, quint64 gen) {
    if (gen != gen_) return;   // a newer reload() superseded this one
    if (!rangeLoaded_) {          // the stored buttons are read once; later picks live in memory and are saved
        rangeStore_.fromJson(r.ranges);
        rangeLoaded_ = true;
    }
    build_ = r.build;
    layouts_ = r.layouts.value;
    loadError_ = !build_.ok() ? build_.error : (!r.layouts.ok() || layouts_->fromLayoutConst) ? r.layouts.error : QString();
    if (!loadError_.isEmpty()) qWarning("[widata] %s", qUtf8Printable(loadError_));
    cache_.clear();
    dashErrors_.clear();
    loading_.clear();
    shell_->refreshMetrics();
    QStringList ids, names;
    if (layouts_)
        for (const DashSpec& d : layouts_->dashboards) { ids << d.id; names << d.name; }
    shell_->setTabs(ids, names);
    const QString prev = current_;
    current_ = r.dashId;
    if (r.dashTried) {
        if (r.dash.ok()) cache_.insert(current_, r.dash.value);
        else dashErrors_.insert(current_, r.dash.error);
    } else if (!current_.isEmpty()) {
        dashErrors_.insert(current_, loadError_);
    }
    shell_->setActive(current_);
    content_->setNotice(layouts_ ? QString() : QStringLiteral("[CẦN DATA]"));
    rebuildCards();
    emit layoutsReady();
    emit loadStatusChanged(loadError_);
    if (prev != current_) emit dashboardChanged(current_);
    emit dashboardReady(current_);
}

void WdcView::select_dashboard(const QString& id) {
    if (!layouts_) { current_ = id; return; }   // before the first load: remembered, used by reload()
    if (id == current_ || !layouts_->dash(id)) return;
    current_ = id;
    scrollY_ = 0;
    tip_->dismiss();
    menu_->dismiss();
    close_expanded();
    shell_->setActive(id);
    savePrefs();
    emit dashboardChanged(id);
    const bool known = cache_.contains(id) || dashErrors_.contains(id);
    if (!known && build_.ok() && !layouts_->fromLayoutConst) requestDash(id);
    else if (!known) dashErrors_.insert(id, loadError_);
    rebuildCards();
    if (!loading_.value(id)) emit dashboardReady(id);
}

void WdcView::requestDash(const QString& id) {
    if (loading_.value(id)) return;
    loading_.insert(id, true);
    ++pending_;
    const quint64 gen = gen_;
    const QString dir = build_.buildDir;
    auto* w = new QFutureWatcher<Loaded<DashData>>(this);
    connect(w, &QFutureWatcherBase::finished, this, [this, w, gen, id] {
        --pending_;
        const Loaded<DashData> r = w->result();
        w->deleteLater();
        if (gen != gen_) return;
        loading_.remove(id);
        if (r.ok()) cache_.insert(id, r.value);
        else dashErrors_.insert(id, r.error);
        if (!r.ok()) qWarning("[widata] %s", qUtf8Printable(r.error));
        if (id != current_) return;
        refreshCardData();
        emit dashboardReady(id);
    });
    w->setFuture(QtConcurrent::run([dir, id] { return loadDash(dir, id); }));
}

void WdcView::reload_dashboard(const QString& id) {
    if (!layouts_ || !layouts_->dash(id)) return;
    // the cards keep the data they hold until the new file is read, then are updated in place
    cache_.remove(id);
    dashErrors_.remove(id);
    if (build_.ok() && !layouts_->fromLayoutConst) return requestDash(id);
    dashErrors_.insert(id, loadError_);
    if (id == current_) refreshCardData();
}

void WdcView::savePrefs() {
    const QString path = prefsPath_;
    const QJsonObject o{{QStringLiteral("last_dash"), current_}, {QStringLiteral("range"), rangeStore_.toJson()}};
    (void)QtConcurrent::run([path, o] {
        writeFileCounted(wdcview_prefs_path(path), QJsonDocument(o).toJson(QJsonDocument::Compact), nullptr);
    });
}

CardContext WdcView::contextFor(const CardSpec& c) const {
    CardContext x;
    x.dashId = current_;
    x.layouts = layouts_;
    x.card = &c;
    x.data = cache_.value(current_);
    x.loading = loading_.value(current_);
    x.dataError = dashErrors_.value(current_);
    return x;
}

void WdcView::refreshCardData() {
    // Cards of the default factory built for this dashboard while it was loading: give them the data in place
    // (a WdcCard costs about 7 ms to build, measured 04/10); any other card set is rebuilt.
    const DashSpec* ds = layouts_ ? layouts_->dash(current_) : nullptr;
    bool inPlace = ds && cardsDefault_ && cardsDash_ == current_ && cards_.size() == ds->cards.size();
    for (const auto& [key, w] : cards_) inPlace = inPlace && qobject_cast<WdcCard*>(w.data());
    if (!inPlace) return rebuildCards();
    renderedEmitted_ = false;
    for (const auto& [key, w] : cards_) {
        auto* card = static_cast<WdcCard*>(w.data());
        const CardSpec* c = ds->card(key);
        if (!c) continue;
        const CardContext ctx = contextFor(*c);
        card->setLoading(ctx.loading);
        card->setCacheTag(cacheTag());
        card->setData(ctx.data);
        applyRange(card);   // refMax comes with the data
        if (cardHook_) cardHook_(card, ctx);
    }
    checkRendered();
}

void WdcView::rebuildCards() {
    for (auto& [key, w] : cards_)
        if (w) { w->hide(); w->deleteLater(); }
    cards_.clear();
    cardsDash_ = current_;
    cardsDefault_ = !customFactory_;
    renderedEmitted_ = false;
    const DashSpec* ds = layouts_ ? layouts_->dash(current_) : nullptr;
    if (ds)
        for (const CardSpec& c : ds->cards) {
            QWidget* w = cardFactory_(contextFor(c), content_);
            if (!w) continue;
            if (w->parentWidget() != content_) w->setParent(content_);
            w->show();
            cards_.emplace_back(c.key, w);
        }
    relayout();
    QMetaObject::invokeMethod(this, &WdcView::checkRendered, Qt::QueuedConnection);   // all-missing dashboards
}

GridGeom WdcView::currentGrid() const {
    const double gw = gridWidthForPanel(width());
    return gridGeom(colOverride_.value_or(gw), rowOverride_.value_or(gw));
}

void WdcView::relayout() {
    const int W = width(), H = height();
    shell_->setGeometry(0, 0, W, int(kShellH));
    frame_->setGeometry(0, int(kShellH), W, std::max(0, H - int(kShellH)));
    const GridGeom gg = currentGrid();
    const DashSpec* ds = layouts_ ? layouts_->dash(current_) : nullptr;
    const PageGeom pg = pageGeom(gg.colBasis, ds ? gridHeight(gg, ds->maxRow()) : 0);
    content_->setPage(pg);
    const int ch = int(std::ceil(pg.contentH));
    const double maxScroll = std::max(0, ch - frame_->height());
    scrollY_ = std::clamp(scrollY_, 0.0, maxScroll);
    content_->setGeometry(0, -int(std::lround(scrollY_)), W, ch);
    if (ds)
        for (auto& [key, w] : cards_) {
            const CardSpec* c = ds->card(key);
            if (!w || !c) continue;
            const QRectF r = gridCellRect(gg, c->grid.x, c->grid.y, c->grid.w, c->grid.h);
            w->setGeometry(int(kPadX + r.x()), int(r.y()), int(r.width()), int(r.height()));
            if (auto* card = qobject_cast<WdcCard*>(w.data()))   // top of the page first, then left to right
                card->setRenderPriority(-(c->grid.y * 100 + c->grid.x));
        }
    auto* sb = static_cast<WdcviewScrollBar*>(scrollbar_);
    sb->setGeometry(W - int(kScrollbarW), 0, int(kScrollbarW), frame_->height());
    sb->pos = scrollY_;
    sb->content = ch;
    sb->viewport = frame_->height();
    sb->raise();
    sb->update();
    if (expanded_) expanded_->setGeometry(rect());
}

void WdcView::set_scroll_y(double y) {
    scrollY_ = y;
    tip_->dismiss();
    relayout();
}

void WdcView::resizeEvent(QResizeEvent* e) {
    QWidget::resizeEvent(e);
    shell_->setScrollX(shell_->scrollX());
    relayout();
}

void WdcView::wheelEvent(QWheelEvent* e) {
    if (e->position().y() < kShellH) return QWidget::wheelEvent(e);
    const QPoint px = e->pixelDelta();
    const double d = !px.isNull() ? px.y() : e->angleDelta().y() / 120.0 * 100;
    set_scroll_y(scrollY_ - d);
    e->accept();
}

void WdcView::keyPressEvent(QKeyEvent* e) {
    if (e->key() == Qt::Key_Escape && expanded_) close_expanded();
    else QWidget::keyPressEvent(e);
}

void WdcView::showTip(const QString& text, const QRectF& anchorInView) {
    if (menu_->isVisible()) return;
    tip_->showTip(text, anchorInView);
}

void WdcView::open_tab_menu() {
    if (!layouts_ || current_.isEmpty()) return;
    tip_->dismiss();
    std::vector<WdcPopup::Item> items;
    for (const SingleChartSpec& s : layouts_->singleCharts)
        items.push_back({QStringLiteral("Biểu đồ: ") + s.title, QStringLiteral("single:") + s.id, true});
    items.push_back({QStringLiteral("Nguồn quốc tế & bảng SGI (màn cũ)"), QStringLiteral("legacy"), true});
    items.push_back({QStringLiteral("Đổi tên bố cục (Đợt 2)"), {}, false});
    items.push_back({QStringLiteral("Nhân bản bố cục (Đợt 2)"), {}, false});
    items.push_back({QStringLiteral("Xoá bố cục (Đợt 2)"), {}, false});
    const QRectF drop = shell_->geom().dropBtn;
    menu_->showMenu(QPointF(drop.x(), shell_->geom().row.bottom() + 4), items);
}

bool WdcView::expand_card(const QString& cardKey) {
    const DashSpec* ds = layouts_ ? layouts_->dash(current_) : nullptr;
    const CardSpec* c = ds ? ds->card(cardKey) : nullptr;
    if (!c) return false;
    emit expandRequested(current_, cardKey);
    if (!expandFactory_) return false;
    close_expanded();
    QWidget* w = expandFactory_(contextFor(*c), this);
    if (!w) return false;
    w->setParent(this);
    w->setGeometry(rect());
    w->show();
    w->raise();
    w->setFocus();
    expanded_ = w;
    return true;
}

void WdcView::close_expanded() {
    if (expanded_) expanded_->deleteLater();
    expanded_.clear();
    setFocus();
}

QStringList WdcView::dashboards() const { return layouts_ ? layouts_->tabOrder : QStringList(); }

QList<QWidget*> WdcView::card_widgets() const {
    QList<QWidget*> out;
    for (const auto& [key, w] : cards_) if (w) out << w;
    return out;
}

QJsonObject WdcView::dump_geometry_json() const {
    const ShellGeom s = shell_->geom();
    QJsonArray tabs;
    const QStringList ids = dashboards();
    for (size_t i = 0; i < s.tabs.size(); ++i) {
        const ShellTabGeom& t = s.tabs[i];
        const DashSpec* d = layouts_ ? layouts_->dash(ids.value(int(i))) : nullptr;
        tabs.append(QJsonObject{{"id", ids.value(int(i))}, {"name", d ? d->name : QString()}, {"shown", t.shown},
                                {"elided", t.elided}, {"active", t.active}, {"box", wdcview_rect(t.box)}, {"text", wdcview_rect(t.text)}});
    }
    const QJsonObject shell{{"row", wdcview_rect(s.row)}, {"label", wdcview_rect(s.label)}, {"cluster", wdcview_rect(s.cluster)},
                            {"frame", wdcview_rect(s.frame)}, {"add_btn", wdcview_rect(s.addBtn)}, {"add_icon", wdcview_rect(s.addIcon)},
                            {"add_text_x", s.addTextX}, {"next_btn", wdcview_rect(s.nextBtn)}, {"show_next", s.showNext},
                            {"prev_btn", wdcview_rect(s.prevBtn)}, {"show_prev", s.showPrev}, {"drop_btn", wdcview_rect(s.dropBtn)},
                            {"scroll_x", s.scrollX}, {"content_w", s.contentW}, {"tabs", tabs},
                            {"baselines", QJsonArray{s.labelBaseline, s.tabBaseline, s.addBaseline}}};
    const GridGeom gg = currentGrid();
    const PageGeom& pg = content_->page();
    QJsonArray cards;
    const DashSpec* ds = layouts_ ? layouts_->dash(current_) : nullptr;
    for (const auto& [key, w] : cards_) {
        const CardSpec* c = ds ? ds->card(key) : nullptr;
        if (!c || !w) continue;
        const QRectF r = gridCellRect(gg, c->grid.x, c->grid.y, c->grid.w, c->grid.h).translated(kPadX, kShellH);
        const QRect wr = w->geometry().translated(0, int(kShellH));   // content coords (unrolled) -> panel
        cards.append(QJsonObject{{"key", key}, {"title", c->title},
                                 {"grid", QJsonArray{c->grid.x, c->grid.y, c->grid.w, c->grid.h}},
                                 {"rect", wdcview_rect(r)}, {"widget", wdcview_rect(QRectF(wr))},
                                 {"class", QString::fromLatin1(w->metaObject()->className())}});
    }
    const FontStatus* fs = fontsLoaded() ? &ensureFonts() : nullptr;
    return QJsonObject{
        {"panel", QJsonArray{width(), height()}}, {"dpr", devicePixelRatioF()}, {"border", theme::hairline(devicePixelRatioF())},
        {"dashboard", current_}, {"shell", shell},
        {"grid", QJsonObject{{"x", kPadX}, {"y", kShellH}, {"col_basis", gg.colBasis}, {"row_basis", gg.rowBasis},
                             {"cw", gg.cw}, {"rh", gg.rh}, {"height", pg.gridH}}},
        {"cards", cards},
        {"add_block", wdcview_rect(pg.addBlock.translated(0, kShellH))}, {"add_btn", wdcview_rect(pg.addBtn.translated(0, kShellH))},
        {"add_icon", wdcview_rect(addChartIconRect(pg.addBtn, theme::hairline(devicePixelRatioF())).translated(0, kShellH))},
        {"scroll", QJsonObject{{"y", scrollY_}, {"content_h", content_->height()}, {"frame_h", frame_->height()}}},
        {"build", QJsonObject{{"state_dir", build_.stateDir}, {"build_dir", build_.buildDir}, {"error_code", build_.errorCode},
                              {"from_layout_const", layouts_ ? layouts_->fromLayoutConst : false}}},
        {"load_error", loadError_},
        {"fonts", QJsonObject{{"dir", fs ? fs->dir : QString()}, {"families", fs ? QJsonArray::fromStringList(fs->families) : QJsonArray()}}}};
}

QImage WdcView::grab_unrolled(qreal dpr) const {
    const qreal d = dpr > 0 ? dpr : devicePixelRatioF();
    for (const auto& [key, w] : cards_)   // charts of every card, rendered now if still in flight (harness)
        if (auto* card = qobject_cast<WdcCard*>(w.data())) card->renderNow();
    const int W = width(), ch = content_->height();
    QImage img(QSize(int(std::ceil(W * d)), int(std::ceil((kShellH + ch) * d))), QImage::Format_ARGB32_Premultiplied);
    img.setDevicePixelRatio(d);
    img.fill(Qt::white);
    QPainter p(&img);
    shell_->render(&p, QPoint(0, 0), QRegion(), QWidget::DrawChildren);
    content_->render(&p, QPoint(0, int(kShellH)), QRegion(), QWidget::DrawWindowBackground | QWidget::DrawChildren);
    return img;
}

} // namespace fincept::screens::wdc
