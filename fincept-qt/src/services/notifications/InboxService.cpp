#include "services/notifications/InboxService.h"

#include "app/DockScreenRouter.h"
#include "app/WindowFrame.h"
#include "core/config/AppPaths.h"
#include "core/logging/Logger.h"
#include "services/notifications/InboxSchema.h"
#include "services/notifications/NotificationService.h"

#include <QApplication>
#include <QDateTime>
#include <QDir>
#include <QFile>
#include <QFileInfo>
#include <QFileSystemWatcher>
#include <QTimer>

#ifdef Q_OS_UNIX
#    include <unistd.h>
#endif

namespace fincept::notifications {

// Named namespace (not anonymous) so nothing here can collide in a unity batch.
namespace inbox_svc {
constexpr const char* kTag = "InboxService";
constexpr int kDebounceMs = 250;
constexpr int kRescanMs = 30 * 1000;
constexpr int kMaxPerMinute = 30;
constexpr qint64 kRateWindowMs = 60 * 1000;
constexpr qint64 kDoneRetentionMs = 7LL * 86400 * 1000;
constexpr qint64 kSweepEveryMs = 60LL * 60 * 1000;

/// Live DockScreenRouter registry (every WindowFrame registers the same ids).
/// Empty before the first window exists, e.g. while the Python setup screen runs.
QStringList live_screen_ids() {
    const auto top_widgets = QApplication::topLevelWidgets();
    for (QWidget* w : top_widgets) {
        if (auto* frame = qobject_cast<fincept::WindowFrame*>(w)) {
            if (auto* router = frame->dock_router())
                return router->all_screen_ids();
        }
    }
    return {};
}

/// rename() that replaces an earlier file of the same name in done/ or bad/.
bool replace_into(const QString& from, const QString& to) {
    if (QFileInfo::exists(to) || QFileInfo(to).isSymLink())
        QFile::remove(to);
    return QFile::rename(from, to);
}

bool is_hidden(const QString& name) {
    return name.startsWith(QLatin1Char('.')); // .DS_Store, editor temp files
}
} // namespace inbox_svc

InboxService& InboxService::instance() {
    static InboxService s;
    return s;
}

InboxService::InboxService() : QObject(nullptr) {}

void InboxService::start() {
    if (started_)
        return;
    started_ = true;

    root_ = AppPaths::inbox();
    for (const char* sub : {"/tmp", "/new", "/cur", "/done", "/bad"})
        QDir().mkpath(root_ + QLatin1String(sub));

    // Files left in cur/ were claimed by a run that stopped before finishing them.
    const QStringList leftovers =
        QDir(root_ + "/cur").entryList(QDir::Files | QDir::System | QDir::NoDotAndDotDot, QDir::Name);
    if (!leftovers.isEmpty()) {
        const QStringList screens = inbox_svc::live_screen_ids();
        for (const QString& name : leftovers) {
            if (inbox_svc::is_hidden(name))
                continue;
            if (!inbox::valid_file_name(name)) {
                reject(root_ + "/cur/" + name, name, QStringLiteral("bad file name"));
                continue;
            }
            if (process_claimed(name, screens))
                delivered_ms_.push_back(QDateTime::currentMSecsSinceEpoch());
        }
    }

    watcher_ = new QFileSystemWatcher(this);
    if (!watcher_->addPath(root_ + "/new"))
        LOG_WARN(inbox_svc::kTag, "Cannot watch " + root_ + "/new, relying on the 30 s rescan");
    connect(watcher_, &QFileSystemWatcher::directoryChanged, this, [this]() { schedule_scan(); });

    debounce_ = new QTimer(this);
    debounce_->setSingleShot(true);
    debounce_->setInterval(inbox_svc::kDebounceMs);
    connect(debounce_, &QTimer::timeout, this, [this]() { scan(); });

    rescan_ = new QTimer(this);
    rescan_->setInterval(inbox_svc::kRescanMs);
    rescan_->setTimerType(Qt::VeryCoarseTimer);
    connect(rescan_, &QTimer::timeout, this, [this]() { scan(); });
    rescan_->start();

    LOG_INFO(inbox_svc::kTag, "Watching " + root_ + "/new");
    scan();
}

void InboxService::schedule_scan() {
    if (debounce_)
        debounce_->start(); // restarts: a burst of writes becomes one scan
}

bool InboxService::rate_limited() {
    const qint64 cutoff = QDateTime::currentMSecsSinceEpoch() - inbox_svc::kRateWindowMs;
    while (!delivered_ms_.empty() && delivered_ms_.front() < cutoff)
        delivered_ms_.pop_front();
    return delivered_ms_.size() >= static_cast<std::size_t>(inbox_svc::kMaxPerMinute);
}

void InboxService::scan() {
    if (!started_)
        return;

    const qint64 now_ms = QDateTime::currentMSecsSinceEpoch();
    if (now_ms - last_sweep_ms_ >= inbox_svc::kSweepEveryMs) {
        last_sweep_ms_ = now_ms;
        sweep_done();
    }

    // The watch is lost if new/ was deleted and recreated; re-arm it.
    if (watcher_ && watcher_->directories().isEmpty())
        watcher_->addPath(root_ + "/new");

    // QDir::System also lists broken symlinks so they reach the reject path.
    const QStringList names =
        QDir(root_ + "/new").entryList(QDir::Files | QDir::System | QDir::NoDotAndDotDot, QDir::Name);
    if (names.isEmpty())
        return;

    const QStringList screens = inbox_svc::live_screen_ids();
    int waiting = 0;
    for (const QString& name : names) {
        if (inbox_svc::is_hidden(name))
            continue;
        if (!inbox::valid_file_name(name)) {
            reject(root_ + "/new/" + name, name, QStringLiteral("bad file name"));
            continue;
        }
        const QString new_path = root_ + "/new/" + name;
        // Before the claim: QFile::rename() refuses a dangling symlink (its target
        // "does not exist"), which would leave it in new/ forever.
        if (QFileInfo(new_path).isSymLink()) {
            reject(new_path, name, QStringLiteral("symlink"));
            continue;
        }
        if (rate_limited()) {
            ++waiting;
            continue;
        }
        // Claim: a failed rename means another instance took it, or it vanished.
        if (!QFile::rename(new_path, root_ + "/cur/" + name))
            continue;
        if (process_claimed(name, screens))
            delivered_ms_.push_back(QDateTime::currentMSecsSinceEpoch());
    }
    if (waiting > 0)
        LOG_INFO(inbox_svc::kTag, QString("Rate limit (%1/min) reached; %2 message(s) left for a later scan")
                                      .arg(inbox_svc::kMaxPerMinute)
                                      .arg(waiting));
}

bool InboxService::process_claimed(const QString& name, const QStringList& screens) {
    const QString cur_path = root_ + "/cur/" + name;
    const QFileInfo fi(cur_path);

    if (fi.isSymLink()) {
        reject(cur_path, name, QStringLiteral("symlink"));
        return false;
    }
    if (!fi.isFile()) {
        reject(cur_path, name, QStringLiteral("not a regular file"));
        return false;
    }
#ifdef Q_OS_UNIX
    if (fi.ownerId() != static_cast<uint>(::getuid())) {
        reject(cur_path, name, QStringLiteral("owner is not the current user"));
        return false;
    }
#endif
    if (fi.size() > inbox::kMaxFileBytes) {
        reject(cur_path, name, QStringLiteral("larger than 16 KB"));
        return false;
    }

    QFile f(cur_path);
    if (!f.open(QIODevice::ReadOnly)) {
        reject(cur_path, name, QStringLiteral("unreadable: ") + f.errorString());
        return false;
    }
    const QByteArray bytes = f.read(inbox::kMaxFileBytes + 1);
    f.close();

    const auto parsed = inbox::parse_message(bytes, QDateTime::currentDateTime(), screens);
    switch (parsed.status) {
        case inbox::ParseStatus::Invalid:
            reject(cur_path, name, parsed.reason);
            return false;

        case inbox::ParseStatus::Expired: {
            const QString stem = name.left(name.size() - 5); // strip ".json"
            if (!inbox_svc::replace_into(cur_path, root_ + "/done/" + stem + ".expired.json"))
                LOG_WARN(inbox_svc::kTag, "Cannot move expired message to done/: " + name);
            LOG_INFO(inbox_svc::kTag, QString("Expired, not notified: %1 (%2)").arg(parsed.id, parsed.request.source));
            return false;
        }

        case inbox::ParseStatus::Ok:
            break;
    }

    if (!parsed.reason.isEmpty())
        LOG_WARN(inbox_svc::kTag, QString("%1: %2").arg(parsed.id, parsed.reason));

    NotificationService::instance().send(parsed.request);

    if (!inbox_svc::replace_into(cur_path, root_ + "/done/" + name))
        LOG_WARN(inbox_svc::kTag, "Cannot move delivered message to done/: " + name);
    LOG_INFO(inbox_svc::kTag, QString("Delivered %1 (%2)").arg(parsed.id, parsed.request.source));
    return true;
}

void InboxService::reject(const QString& path, const QString& name, const QString& reason) {
    const QString bad_path = root_ + "/bad/" + name;
    if (!inbox_svc::replace_into(path, bad_path)) {
        // Could not move it: delete so a poisoned file is not re-read every scan.
        QFile::remove(path);
    }
    QFile sidecar(bad_path + ".reason");
    if (sidecar.open(QIODevice::WriteOnly | QIODevice::Truncate | QIODevice::Text)) {
        sidecar.write(QString("%1\t%2\n")
                          .arg(QDateTime::currentDateTime().toString(Qt::ISODate), reason)
                          .toUtf8());
        sidecar.close();
    }
    LOG_WARN(inbox_svc::kTag, QString("Rejected %1: %2").arg(name, reason));
}

void InboxService::sweep_done() {
    const qint64 cutoff = QDateTime::currentMSecsSinceEpoch() - inbox_svc::kDoneRetentionMs;
    const QFileInfoList entries =
        QDir(root_ + "/done").entryInfoList(QDir::Files | QDir::System | QDir::Hidden | QDir::NoDotAndDotDot);
    int removed = 0;
    for (const QFileInfo& fi : entries) {
        if (fi.lastModified().toMSecsSinceEpoch() < cutoff && QFile::remove(fi.absoluteFilePath()))
            ++removed;
    }
    if (removed > 0)
        LOG_INFO(inbox_svc::kTag, QString("Swept %1 file(s) older than 7 days from done/").arg(removed));
}

} // namespace fincept::notifications
