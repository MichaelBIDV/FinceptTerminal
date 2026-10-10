#pragma once
#include <QObject>
#include <QString>
#include <QStringList>

#include <deque>

class QFileSystemWatcher;
class QTimer;

namespace fincept::notifications {

/// Drop box for jobs outside the app (launchd, Python bridges): one JSON file per
/// message in AppPaths::inbox()/new, schema v1 (InboxSchema.h, THONGBAO_SPEC §2).
///
/// Protocol (maildir-like): the writer creates the file in tmp/ and renames it
/// into new/. The app claims a message by renaming new/ → cur/ (a failed rename
/// means another instance already took it), validates it, forwards it to
/// NotificationService as NotifTrigger::External (local_only), then moves it to
/// done/. Rejected files go to bad/ with a <name>.reason sidecar; expired ones go
/// to done/ as <stem>.expired.json without notifying.
///
/// GUI thread only. QFileSystemWatcher can coalesce or miss events (FSEvents,
/// sleep/wake), so a 30 s rescan backs it up. At most 30 messages per minute are
/// delivered; the rest wait for a later scan. done/ is swept after 7 days.
class InboxService : public QObject {
    Q_OBJECT
  public:
    static InboxService& instance();

    /// Idempotent. Call after NotificationService::instance() on the GUI thread.
    void start();

  private:
    InboxService();

    void schedule_scan();
    void scan();
    /// Handles a file already claimed into cur/. Returns true when it was delivered.
    bool process_claimed(const QString& name, const QStringList& screens);
    /// Moves `path` to bad/<name> and writes bad/<name>.reason.
    void reject(const QString& path, const QString& name, const QString& reason);
    void sweep_done();
    bool rate_limited();

    QString root_;
    QFileSystemWatcher* watcher_ = nullptr;
    QTimer* debounce_ = nullptr;
    QTimer* rescan_ = nullptr;
    std::deque<qint64> delivered_ms_; ///< delivery times inside the rolling rate window
    qint64 last_sweep_ms_ = 0;
    bool started_ = false;
};

} // namespace fincept::notifications
