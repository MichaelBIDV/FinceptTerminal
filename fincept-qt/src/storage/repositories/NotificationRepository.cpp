// src/storage/repositories/NotificationRepository.cpp
#include "storage/repositories/NotificationRepository.h"

namespace fincept {

using notifications::NotificationRecord;
using notifications::NotifLevel;
using notifications::NotifTrigger;

namespace {
// Unique names on purpose: repositories may be batched together in a unity build.
const char* kNotifHistoryCols =
    "id, ts_event, received_at, title, message, level, trig, source, dedupe_key, action_screen, read";

// Coerce possibly-null QString to '' so NOT NULL TEXT binds never become SQL NULL.
QString notif_nn(const QString& s) {
    return s.isNull() ? QString::fromLatin1("") : s;
}
} // namespace

NotificationRepository& NotificationRepository::instance() {
    static NotificationRepository s;
    return s;
}

bool NotificationRepository::ensure_table() {
    if (table_ready_.load())
        return true;
    auto r = exec_raw("CREATE TABLE IF NOT EXISTS notification_history ("
                      "  id            INTEGER PRIMARY KEY AUTOINCREMENT,"
                      "  ts_event      INTEGER NOT NULL,"
                      "  received_at   INTEGER NOT NULL,"
                      "  title         TEXT NOT NULL DEFAULT '',"
                      "  message       TEXT NOT NULL DEFAULT '',"
                      "  level         INTEGER NOT NULL DEFAULT 0,"
                      "  trig          INTEGER NOT NULL DEFAULT 0,"
                      "  source        TEXT NOT NULL DEFAULT '',"
                      "  dedupe_key    TEXT NOT NULL DEFAULT '',"
                      "  action_screen TEXT NOT NULL DEFAULT '',"
                      "  read          INTEGER NOT NULL DEFAULT 0"
                      ")");
    if (r.is_err()) {
        LOG_ERROR("NotificationRepository",
                  QString("Failed to create notification_history: %1").arg(QString::fromStdString(r.error())));
        return false;
    }
    exec_raw("CREATE INDEX IF NOT EXISTS idx_notif_hist_key ON notification_history(dedupe_key, received_at)");
    exec_raw("CREATE INDEX IF NOT EXISTS idx_notif_hist_recv ON notification_history(received_at)");
    table_ready_.store(true);
    return true;
}

NotificationRecord NotificationRepository::map_row(QSqlQuery& q) {
    NotificationRecord rec;
    rec.id = q.value(0).toLongLong();
    rec.request.timestamp = QDateTime::fromMSecsSinceEpoch(q.value(1).toLongLong());
    rec.received_at = QDateTime::fromMSecsSinceEpoch(q.value(2).toLongLong());
    rec.request.title = q.value(3).toString();
    rec.request.message = q.value(4).toString();
    const int level = q.value(5).toInt();
    rec.request.level = (level >= 0 && level <= static_cast<int>(NotifLevel::Critical)) ? static_cast<NotifLevel>(level)
                                                                                       : NotifLevel::Info;
    const int trig = q.value(6).toInt();
    rec.request.trigger = (trig >= 0 && trig <= static_cast<int>(NotifTrigger::External))
                              ? static_cast<NotifTrigger>(trig)
                              : NotifTrigger::Manual;
    rec.request.source = q.value(7).toString();
    rec.request.dedupe_key = q.value(8).toString();
    rec.request.action_screen = q.value(9).toString();
    rec.read = q.value(10).toInt() != 0;
    // Already dispatched: a reloaded record must never be forwarded again.
    rec.request.local_only = true;
    return rec;
}

Result<qint64> NotificationRepository::insert(const NotificationRecord& rec) {
    if (!ensure_table())
        return Result<qint64>::err("notification_history unavailable");
    const qint64 received_ms = rec.received_at.isValid() ? rec.received_at.toMSecsSinceEpoch()
                                                         : QDateTime::currentMSecsSinceEpoch();
    const qint64 event_ms = rec.request.timestamp.isValid() ? rec.request.timestamp.toMSecsSinceEpoch() : received_ms;
    return exec_insert("INSERT INTO notification_history (ts_event, received_at, title, message, level, trig, source,"
                       " dedupe_key, action_screen, read) VALUES (?,?,?,?,?,?,?,?,?,?)",
                       {event_ms, received_ms, notif_nn(rec.request.title), notif_nn(rec.request.message),
                        static_cast<int>(rec.request.level), static_cast<int>(rec.request.trigger),
                        notif_nn(rec.request.source), notif_nn(rec.request.dedupe_key),
                        notif_nn(rec.request.action_screen), rec.read ? 1 : 0});
}

Result<QVector<NotificationRecord>> NotificationRepository::recent(int limit) {
    if (!ensure_table())
        return Result<QVector<NotificationRecord>>::err("notification_history unavailable");
    return query_list(QString("SELECT %1 FROM notification_history ORDER BY id DESC LIMIT ?").arg(kNotifHistoryCols),
                      {limit}, map_row);
}

Result<int> NotificationRepository::unread_count() {
    if (!ensure_table())
        return Result<int>::err("notification_history unavailable");
    auto r = db().execute("SELECT COUNT(*) FROM notification_history WHERE read = 0");
    if (r.is_err())
        return Result<int>::err(r.error());
    auto& q = r.value();
    return Result<int>::ok(q.next() ? q.value(0).toInt() : 0);
}

Result<bool> NotificationRepository::mark_read(qint64 id) {
    if (!ensure_table())
        return Result<bool>::err("notification_history unavailable");
    auto r = db().execute("UPDATE notification_history SET read = 1 WHERE id = ? AND read = 0", {id});
    if (r.is_err())
        return Result<bool>::err(r.error());
    return Result<bool>::ok(r.value().numRowsAffected() > 0);
}

Result<void> NotificationRepository::mark_all_read() {
    if (!ensure_table())
        return Result<void>::err("notification_history unavailable");
    return exec_write("UPDATE notification_history SET read = 1 WHERE read = 0");
}

Result<bool> NotificationRepository::has_key_since(const QString& dedupe_key, qint64 since_ms) {
    if (!ensure_table())
        return Result<bool>::err("notification_history unavailable");
    auto r = db().execute("SELECT 1 FROM notification_history WHERE dedupe_key = ? AND received_at >= ? LIMIT 1",
                          {dedupe_key, since_ms});
    if (r.is_err())
        return Result<bool>::err(r.error());
    return Result<bool>::ok(r.value().next());
}

} // namespace fincept
