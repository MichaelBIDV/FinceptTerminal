// WdcRender.cpp: off-UI-thread layout + chart painting of dashboard cards (DESIGN §16 C18), gói UI (đợt 3).
#include "screens/widata/WdcRender.h"

#include "screens/widata/WdcCache.h"
#include "screens/widata/WdcHcApi.h"

#include <QCoreApplication>
#include <QElapsedTimer>
#include <QPainter>
#include <QThread>
#include <QThreadPool>
#include <QTimer>

#include <algorithm>
#include <cmath>

namespace fincept::screens::wdc {

namespace {

const SeriesData& wdcr_missing() {
    static const SeriesData d{Status::Missing, QString(), QString(), {}, {}};
    return d;
}

qint64 wdcr_q64(double v) { return qint64(std::llround(v * 64.0)); }   // 1/64 CSS px, LayoutUnit-like

// Plain pointers and counters (no static object with a destructor that would run after QApplication): UI thread only.
WdcRenderService* wdcr_inst = nullptr;
WdcRenderService* wdcr_parked = nullptr;   // released while still painting, deleted when their pool is idle
int wdcr_users = 0;
bool wdcr_routine = false;                 // WdcRenderService::shutdown is a registered post routine

void wdcr_routineOn() {
    if (wdcr_routine) return;
    qAddPostRoutine(&WdcRenderService::shutdown);
    wdcr_routine = true;
}

void wdcr_routineOff() {   // nothing left to stop; harmless while the post routines are being called
    if (!wdcr_routine || wdcr_inst || wdcr_parked) return;
    qRemovePostRoutine(&WdcRenderService::shutdown);
    wdcr_routine = false;
}

} // namespace

const SeriesData* renderSeriesData(const DashData* d, const QString& sid) {
    if (!d) return &wdcr_missing();
    const auto it = d->series.constFind(sid);
    return it == d->series.cend() ? &wdcr_missing() : &it.value().data;
}

bool renderHasNumbers(const SeriesData* d) {
    if (!d || d->status == Status::Missing) return false;
    return std::any_of(d->pts.begin(), d->pts.end(), [](const QPointF& p) { return std::isfinite(p.y()); });
}

ChartInput renderPaneInput(const PaneSpec& pane, const ChartSpec* effSpec, const DashData* data,
                           const CardRenderParams& p, int k) {
    ChartInput in{};
    in.spec = effSpec;
    for (const SeriesRef& r : pane.series) {
        in.refs.push_back(&r);
        in.data.push_back(renderSeriesData(data, r.sid));
    }
    in.visible = k < int(p.visible.size()) ? p.visible[size_t(k)] : std::vector<bool>(pane.series.size(), true);
    in.visible.resize(pane.series.size(), true);
    in.xMin = p.xMin;
    in.xMax = p.xMax;
    in.padAuto = p.padAuto;
    in.size = k < int(p.sizes.size()) ? p.sizes[size_t(k)] : QSizeF();
    in.profile = MetricsProfile::Native;
    in.expanded = false;
    return in;
}

std::vector<PaneLayout> layoutCardPanes(const CardSpec& card, const DashData* data, const CardRenderParams& p,
                                        const std::atomic<bool>* cancel) {
    std::vector<PaneLayout> out(card.panes.size());
    for (size_t k = 0; k < card.panes.size(); ++k) {
        out[k].effSpec = card.panes[k].chart;
        out[k].allMissing = true;
        for (const SeriesRef& r : card.panes[k].series)
            if (renderHasNumbers(renderSeriesData(data, r.sid))) { out[k].allMissing = false; break; }
    }
    // DESIGN §4.6 "Lề canh hàng": first pass without marginRight, then every pane gets the largest need
    if (card.alignPanesRight && out.size() > 1) {
        qreal need = 0;
        bool any = false;
        for (size_t k = 0; k < out.size(); ++k) {
            if (out[k].allMissing) continue;
            out[k].effSpec.margin[1] = std::nullopt;
            if (cancel && cancel->load()) return out;
            const ChartInput in = renderPaneInput(card.panes[k], &out[k].effSpec, data, p, int(k));
            const ChartModel m = layoutChartAtDpr(in, p.dpr);
            need = std::max(need, in.size.width() - m.plotBox.right());
            any = true;
        }
        if (any)
            for (PaneLayout& pl : out) pl.effSpec.margin[1] = need;
    }
    for (size_t k = 0; k < out.size(); ++k) {
        if (out[k].allMissing) {
            out[k].model = ChartModel{};
            out[k].model.allMissing = true;
        } else {
            if (cancel && cancel->load()) return out;
            // the DPR of the target surface (Native label boxes, C13); isStock: keep the grouped points for hitTest (C21)
            auto proc = out[k].effSpec.isStock ? std::make_shared<std::vector<std::vector<QPointF>>>() : nullptr;
            const ChartInput in = renderPaneInput(card.panes[k], &out[k].effSpec, data, p, int(k));
            out[k].model = layoutChartAtDpr(in, p.dpr, proc.get());
            out[k].processed = std::move(proc);
        }
    }
    return out;
}

CardRender renderCard(const CardSpec& card, const DashData* data, const CardRenderParams& p,
                      const std::atomic<bool>* cancel) {
    CardRender r;
    QElapsedTimer t;
    t.start();
    r.panes = layoutCardPanes(card, data, p, cancel);
    r.layoutMs = double(t.nsecsElapsed()) / 1e6;
    t.restart();
    r.images.resize(r.panes.size());
    const qreal dpr = p.dpr > 0 ? p.dpr : 1.0;
    for (size_t k = 0; k < r.panes.size(); ++k) {
        if (cancel && cancel->load()) { r.complete = false; break; }
        const PaneLayout& pl = r.panes[k];
        if (pl.allMissing) continue;
        const QSizeF size = k < p.sizes.size() ? p.sizes[k] : QSizeF();
        if (size.isEmpty()) continue;
        const QPointF off = k < p.offsets.size() ? p.offsets[k] : QPointF();
        // one extra device pixel each way for the sub-pixel offset of the chart origin
        QImage img(int(std::ceil((size.width() + off.x()) * dpr)) + 1, int(std::ceil((size.height() + off.y()) * dpr)) + 1,
                   QImage::Format_ARGB32_Premultiplied);
        img.setDevicePixelRatio(dpr);
        img.fill(Qt::transparent);
        {
            QPainter g(&img);
            g.setRenderHint(QPainter::Antialiasing, true);
            g.setRenderHint(QPainter::TextAntialiasing, true);
            g.translate(off);
            g.setClipRect(QRectF(QPointF(0, 0), size));
            const ChartInput in = renderPaneInput(card.panes[k], &pl.effSpec, data, p, int(k));
            paintChart(g, pl.model, in);
        }
        r.images[k] = std::move(img);
    }
    r.paintMs = double(t.nsecsElapsed()) / 1e6;
    return r;
}

QByteArray cardRenderKey(const QString& dashId, const CardSpec& card, const DashData* data, const CardRenderParams& p) {
    return cardRenderKey(dashId, card, QByteArray::number(quintptr(data), 16), p);
}

QByteArray cardRenderKey(const QString& dashId, const CardSpec& card, const QByteArray& dataId, const CardRenderParams& p) {
    QByteArray k;
    k.reserve(160);
    k += dashId.toUtf8();
    k += '|';
    k += card.key.toUtf8();
    k += '|';
    k += dataId;
    k += '|';
    k += QByteArray::number(qint64(card.panes.size()));
    for (const PaneSpec& ps : card.panes) {
        k += ':';
        k += QByteArray::number(qint64(ps.series.size()));
    }
    k += "|w";
    k += p.xMin ? QByteArray::number(*p.xMin) : QByteArray("-");
    k += ',';
    k += p.xMax ? QByteArray::number(*p.xMax) : QByteArray("-");
    k += p.padAuto ? ",a" : ",x";
    k += "|v";
    for (const auto& v : p.visible) {
        k += ':';
        for (bool b : v) k += b ? '1' : '0';
    }
    k += "|s";
    for (const QSizeF& s : p.sizes) {
        k += ':';
        k += QByteArray::number(wdcr_q64(s.width()));
        k += 'x';
        k += QByteArray::number(wdcr_q64(s.height()));
    }
    k += "|o";
    for (const QPointF& o : p.offsets) {
        k += ':';
        k += QByteArray::number(wdcr_q64(o.x()));
        k += ',';
        k += QByteArray::number(wdcr_q64(o.y()));
    }
    k += "|d";
    k += QByteArray::number(wdcr_q64(p.dpr));
    return k;
}

// ---- service --------------------------------------------------------------------------------------------------

WdcRenderService::WdcRenderService(QObject* parent) : QObject(parent) {
    pool_ = new QThreadPool(this);
    pool_->setObjectName(QStringLiteral("wdc-render"));
    pool_->setMaxThreadCount(std::max(2, QThread::idealThreadCount() - 1));
    pool_->setExpiryTimeout(30000);
    // app shutdown: jobs must not outlive QGuiApplication (fonts); queued ones are dropped, running ones awaited
    pool_->start([] { trimDiskCache(256ll * 1024 * 1024); }, -1000);   // once per session, after the urgent jobs
    if (QCoreApplication* app = QCoreApplication::instance())
        connect(app, &QCoreApplication::aboutToQuit, this, [this] { stopPool(); });
}

WdcRenderService::~WdcRenderService() { stopPool(); }

bool WdcRenderService::stopPool(int waitMs) {
    for (Job& j : jobs_) j.cancel->store(true);
    pool_->clear();
    return pool_->waitForDone(waitMs);   // a running paint cannot be interrupted: it stops before its next pane
}

WdcRenderService& WdcRenderService::instance() {
    if (!wdcr_inst) {
        wdcr_inst = new WdcRenderService(nullptr);
        wdcr_routineOn();
    }
    return *wdcr_inst;
}

WdcRenderService* WdcRenderService::existing() { return wdcr_inst; }

void WdcRenderService::retain() { ++wdcr_users; }

void WdcRenderService::release() {
    if (wdcr_users > 0 && --wdcr_users == 0) retire(kReleaseWaitMs);
}

void WdcRenderService::retire(int waitMs) {
    WdcRenderService* s = wdcr_inst;
    if (!s) return;
    wdcr_inst = nullptr;
    if (!s->stopPool(waitMs)) return s->park();
    delete s;
    wdcr_routineOff();
}

void WdcRenderService::park() {
    parkedNext_ = wdcr_parked;
    wdcr_parked = this;
    auto* poll = new QTimer(this);
    poll->setInterval(50);
    connect(poll, &QTimer::timeout, this, [this, poll] {
        if (!pool_->waitForDone(0)) return;
        poll->stop();
        for (WdcRenderService** link = &wdcr_parked; *link; link = &(*link)->parkedNext_)
            if (*link == this) { *link = parkedNext_; break; }
        deleteLater();   // idle pool: ~WdcRenderService does not block
        wdcr_routineOff();
    });
    poll->start();
}

void WdcRenderService::shutdown() {
    if (WdcRenderService* s = wdcr_inst) {
        wdcr_inst = nullptr;
        delete s;   // ~WdcRenderService: stopPool(), no time limit (the application is going away)
    }
    while (WdcRenderService* s = wdcr_parked) {
        wdcr_parked = s->parkedNext_;
        delete s;
    }
    wdcr_routineOff();
}

std::shared_ptr<const CardRender> WdcRenderService::cached(const QByteArray& key) {
    auto it = cache_.find(key);
    if (it == cache_.end()) return nullptr;
    it->used = useClock_++;
    ++stats_.hits;
    return it->render;
}

void WdcRenderService::setCacheLimitBytes(qint64 bytes) {
    cacheLimit_ = std::max<qint64>(0, bytes);
    insertCache(QByteArray(), nullptr, nullptr);   // evict down to the new limit
}

void WdcRenderService::clearCache() {
    cache_.clear();
    cacheBytes_ = 0;
}

void WdcRenderService::insertCache(const QByteArray& key, std::shared_ptr<const CardRender> r,
                                   std::shared_ptr<const DashData> pin) {
    if (r && r->complete && !key.isEmpty()) {
        qint64 bytes = 0;
        for (const QImage& img : r->images) bytes += img.sizeInBytes();
        Entry& e = cache_[key];
        cacheBytes_ -= e.bytes;
        e = Entry{std::move(r), std::move(pin), bytes, useClock_++};
        cacheBytes_ += bytes;
    }
    while (cacheBytes_ > cacheLimit_ && !cache_.isEmpty()) {   // least recently used first
        auto victim = cache_.begin();
        for (auto it = cache_.begin(); it != cache_.end(); ++it)
            if (it->used < victim->used) victim = it;
        cacheBytes_ -= victim->bytes;
        cache_.erase(victim);
    }
}

quint64 WdcRenderService::submit(const QByteArray& key, std::shared_ptr<const CardSpec> card,
                                 std::shared_ptr<const DashData> data, const CardRenderParams& p, int priority,
                                 QObject* receiver, Done done, const QByteArray& diskKey) {
    const quint64 id = nextWaiter_++;
    auto it = jobs_.find(key);
    if (it != jobs_.end() && !it->cancel->load()) {
        it->waiters.push_back(Waiter{id, receiver, std::move(done)});
        ++stats_.merged;
        return id;
    }
    Job job;
    job.cancel = std::make_shared<std::atomic<bool>>(false);
    job.waiters.push_back(Waiter{id, receiver, std::move(done)});
    jobs_.insert(key, job);
    ++stats_.submitted;
    const auto cancel = job.cancel;
    QPointer<WdcRenderService> self(this);
    pool_->start(
        [self, key, card = std::move(card), data = std::move(data), p, cancel, diskKey]() {
            std::shared_ptr<const CardRender> out;
            if (!cancel->load() && QCoreApplication::instance()) {
                DiskRender disk;
                if (!diskKey.isEmpty() && loadDiskRender(diskKey, int(card->panes.size()), &disk)) {
                    CardRender r;   // images from the disk cache; the layout (hover, popover) is cheap, redo it
                    QElapsedTimer lt;
                    lt.start();
                    r.panes = layoutCardPanes(*card, data.get(), p, cancel.get());
                    r.layoutMs = double(lt.nsecsElapsed()) / 1e6;
                    r.complete = !cancel->load();
                    r.images = std::move(disk.images);
                    r.paintMs = disk.paintMs;
                    r.fromDisk = true;
                    out = std::make_shared<const CardRender>(std::move(r));
                } else {
                    out = std::make_shared<const CardRender>(renderCard(*card, data.get(), p, cancel.get()));
                    if (!diskKey.isEmpty() && out->complete) storeDiskRender(diskKey, DiskRender{out->images, out->paintMs});
                }
            }
            if (!self) return;
            QMetaObject::invokeMethod(
                self.data(),
                [self, key, out, data, cancel] {
                    if (!self) return;
                    auto jt = self->jobs_.find(key);
                    if (jt == self->jobs_.end() || jt->cancel != cancel) {   // replaced by a newer job of the same key
                        if (out && out->complete) self->insertCache(key, out, data);
                        return;
                    }
                    self->finish(key, out, data);
                },
                Qt::QueuedConnection);
        },
        priority);
    return id;
}

void WdcRenderService::finish(const QByteArray& key, std::shared_ptr<const CardRender> r,
                              std::shared_ptr<const DashData> pin) {
    Job job = jobs_.take(key);
    if (r) {
        stats_.layoutMs += r->layoutMs;
        stats_.paintMs += r->paintMs;
    }
    if (!r || !r->complete || job.cancel->load()) {
        ++stats_.cancelled;
    } else {
        ++stats_.finished;
        insertCache(key, r, pin);
        for (Waiter& w : job.waiters)
            if (w.receiver && w.done) w.done(r);
    }
    if (jobs_.isEmpty()) emit idle();
}

void WdcRenderService::withdraw(const QByteArray& key, quint64 waiter) {
    auto it = jobs_.find(key);
    if (it == jobs_.end()) return;
    auto& ws = it->waiters;
    ws.erase(std::remove_if(ws.begin(), ws.end(), [waiter](const Waiter& w) { return w.id == waiter; }), ws.end());
    if (ws.empty()) it->cancel->store(true);   // the job stays registered until its worker reports back
}

std::shared_ptr<const CardRender> WdcRenderService::renderNow(const QByteArray& key, const CardSpec& card,
                                                              std::shared_ptr<const DashData> data,
                                                              const CardRenderParams& p) {
    if (auto c = cached(key)) return c;
    auto r = std::make_shared<const CardRender>(renderCard(card, data.get(), p, nullptr));
    insertCache(key, r, std::move(data));
    return r;
}

} // namespace fincept::screens::wdc
