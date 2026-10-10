#pragma once
// WdcRender.h: layout + chart painting of dashboard cards off the UI thread (DESIGN §16 C18), gói UI (đợt 3).
//
// A card asks for the chart images of its panes for one set of parameters (data, X window, visible series, chart
// sizes, DPR). The service answers from an LRU cache of images, or runs layoutChart (package B) + paintChart
// (package C) on a dedicated thread pool and posts the result back to the UI thread; the UI thread only blits.
// Identical requests in flight are merged; a request nobody waits for any more is cancelled before painting.
// layoutCardPanes() is also the synchronous path of WdcCard (chartModel / chartInput on demand), so both paths give
// the same model (DESIGN §4.6 two-pass right alignment of split cards).
#include "screens/widata/WdcData.h"

#include <QByteArray>
#include <QHash>
#include <QImage>
#include <QObject>
#include <QPointer>
#include <QSizeF>

#include <atomic>
#include <functional>
#include <memory>
#include <optional>
#include <vector>

class QThreadPool;

namespace fincept::screens::wdc {

/// Never null: an absent sid (or no data) gives a shared Missing entry.
const SeriesData* renderSeriesData(const DashData* d, const QString& sid);
/// Status not Missing and at least one finite value.
bool renderHasNumbers(const SeriesData* d);

struct CardRenderParams {
    std::vector<std::vector<bool>> visible;   // per pane, by series index of the pane
    std::optional<qint64> xMin, xMax;          // X window (WdcRange)
    bool padAuto = true;
    std::vector<QSizeF> sizes;                 // chart size per pane, CSS px (layoutCard)
    std::vector<QPointF> offsets;              // sub-device-pixel offset of each chart inside the image (CSS px)
    qreal dpr = 2.0;
};

struct PaneLayout {
    ChartSpec effSpec;       // spec actually laid out (margin[1] set by the pane alignment)
    ChartModel model{};
    bool allMissing = true;  // no series of the pane has a number: no layout, "[CẦN DATA]"
    /// isStock panes: (t, v) behind each plotted point (group start, average; WdcHcApi.h), for hitTest. Null otherwise.
    std::shared_ptr<const std::vector<std::vector<QPointF>>> processed;
};

/// ChartInput of pane k, pointing into `pane`, `*effSpec` and `*data`.
ChartInput renderPaneInput(const PaneSpec& pane, const ChartSpec* effSpec, const DashData* data,
                           const CardRenderParams& p, int k);
/// Pure, any thread: every pane of a card, two passes when align_panes_right (DESIGN §4.6), laid out at p.dpr
/// (layoutChartAtDpr, DESIGN §16 C13). `cancel` is polled between panes (the result is then incomplete, never shown).
std::vector<PaneLayout> layoutCardPanes(const CardSpec& card, const DashData* data, const CardRenderParams& p,
                                        const std::atomic<bool>* cancel = nullptr);

struct CardRender {
    std::vector<PaneLayout> panes;
    std::vector<QImage> images;   // per pane; null when allMissing. DPR = params.dpr, origin = floor of the device px
    double layoutMs = 0, paintMs = 0;   // paintMs: cost of painting these images (also when read back from disk)
    bool complete = true;         // false when cancelled half way (never cached)
    bool fromDisk = false;        // images read from the disk cache (WdcCache.h), layout computed afresh
};
/// Pure, any thread: layout + paint into images. `cancel` is polled between panes.
CardRender renderCard(const CardSpec& card, const DashData* data, const CardRenderParams& p,
                      const std::atomic<bool>* cancel = nullptr);

/// Cache key: dashboard, card, data identity, window, visibility, sizes, offsets, DPR. The memory key uses the address
/// of the data (pinned by the cache entry); the disk key (WdcCache.h) uses the build tag given by the view instead.
QByteArray cardRenderKey(const QString& dashId, const CardSpec& card, const QByteArray& dataId, const CardRenderParams& p);
QByteArray cardRenderKey(const QString& dashId, const CardSpec& card, const DashData* data, const CardRenderParams& p);

class WdcRenderService : public QObject {
    Q_OBJECT
  public:
    using Done = std::function<void(std::shared_ptr<const CardRender>)>;
    struct Stats { int submitted = 0, merged = 0, hits = 0, cancelled = 0, finished = 0; double layoutMs = 0, paintMs = 0; };

    // Lifetime (VERIFY_W3: a worker touched QFontDatabase after QApplication was gone, abort rc 134). The service is
    // not a child of the app. Every job is cancelled, the queued ones dropped and the running ones awaited
    // (QThreadPool::waitForDone; a cancelled job stops before its next pane) when the last view releases it (the last
    // tab VĨ MÔ closes), on QCoreApplication::aboutToQuit, and in shutdown(), a post routine of the application
    // destructor (qAddPostRoutine runs at the start of ~QApplication, before fonts and the platform plugin go).
    // The last release waits at most kReleaseWaitMs on the UI thread (VERIFY_W4 UI3 (5)): a service whose workers are
    // still busy then is parked, no longer reachable through instance()/existing(), and deleted as soon as its pool is
    // idle; aboutToQuit and shutdown() still wait for it, so no worker outlives the application.
    static constexpr int kReleaseWaitMs = 2000;
    static WdcRenderService& instance();   // created on first use (UI thread)
    static WdcRenderService* existing();   // null when none exists (never creates one)
    static void retain();                  // a view starts using the service (WdcView ctor)
    static void release();                 // last release: stop, wait <= kReleaseWaitMs, delete or park (WdcView dtor)
    static void shutdown();                // stop + wait + delete (parked ones too); instance() makes a fresh one later
    /// Cancel every job, drop the queued ones, wait up to waitMs (-1: no limit) for the running ones. True when no
    /// worker is left.
    bool stopPool(int waitMs = -1);

    /// Cached result for `key`, or null. UI thread.
    std::shared_ptr<const CardRender> cached(const QByteArray& key);
    /// Starts (or joins) the job for `key`; `done` runs on the UI thread unless `receiver` was destroyed or the
    /// waiter was withdrawn. Returns a waiter id for withdraw(). UI thread.
    /// diskKey (WdcCache.h diskRenderKey) non-empty: the worker first tries the disk cache, and stores what it paints.
    quint64 submit(const QByteArray& key, std::shared_ptr<const CardSpec> card, std::shared_ptr<const DashData> data,
                   const CardRenderParams& p, int priority, QObject* receiver, Done done,
                   const QByteArray& diskKey = QByteArray());
    /// The waiter does not want the result any more; the job is cancelled when nobody else waits for it.
    void withdraw(const QByteArray& key, quint64 waiter);
    /// Synchronous path for harnesses and exports: same work on the calling thread, result cached.
    std::shared_ptr<const CardRender> renderNow(const QByteArray& key, const CardSpec& card,
                                                std::shared_ptr<const DashData> data, const CardRenderParams& p);

    int pending() const { return int(jobs_.size()); }
    qint64 cacheBytes() const { return cacheBytes_; }
    void setCacheLimitBytes(qint64 bytes);
    void clearCache();
    Stats stats() const { return stats_; }
    void resetStats() { stats_ = {}; }
    QThreadPool* pool() const { return pool_; }

  signals:
    void idle();   // the last job in flight has finished

  private:
    explicit WdcRenderService(QObject* parent = nullptr);
    ~WdcRenderService() override;
    static void retire(int waitMs);   // detach the current service: delete it, or park it while its workers finish
    void park();
    struct Waiter { quint64 id; QPointer<QObject> receiver; Done done; };
    struct Job { std::shared_ptr<std::atomic<bool>> cancel; std::vector<Waiter> waiters; };
    struct Entry { std::shared_ptr<const CardRender> render; std::shared_ptr<const DashData> pin; qint64 bytes = 0; quint64 used = 0; };
    void finish(const QByteArray& key, std::shared_ptr<const CardRender> r, std::shared_ptr<const DashData> pin);
    void insertCache(const QByteArray& key, std::shared_ptr<const CardRender> r, std::shared_ptr<const DashData> pin);

    QThreadPool* pool_ = nullptr;
    QHash<QByteArray, Job> jobs_;
    QHash<QByteArray, Entry> cache_;
    qint64 cacheBytes_ = 0, cacheLimit_ = 160ll * 1024 * 1024;
    quint64 nextWaiter_ = 1, useClock_ = 1;
    Stats stats_;
    WdcRenderService* parkedNext_ = nullptr;   // chain of parked services (UI thread)
};

} // namespace fincept::screens::wdc
