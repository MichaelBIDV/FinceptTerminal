// src/storage/repositories/NotificationRepository.h
#pragma once
#include "services/notifications/NotificationService.h"
#include "storage/repositories/BaseRepository.h"

#include <QString>
#include <QVector>

#include <atomic>

namespace fincept {

/// Persistent in-app notification history (table `notification_history`).
///
/// The table is created lazily with CREATE TABLE IF NOT EXISTS (same precedent as
/// AuditLogger::ensure_table) instead of a numbered migration: this repo is a fork
/// and a local v052 could collide with upstream's next migration number.
/// Timestamps are stored as epoch milliseconds. Retention (30 days / 5,000 rows)
/// is applied by StorageManager::prune_all().
class NotificationRepository : public BaseRepository<notifications::NotificationRecord> {
  public:
    static NotificationRepository& instance();

    /// Inserts the record (its id is ignored) and returns the new row id.
    Result<qint64> insert(const notifications::NotificationRecord& rec);
    /// Most recent first.
    Result<QVector<notifications::NotificationRecord>> recent(int limit);
    Result<int> unread_count();
    /// ok(true) when a row flipped from unread to read.
    Result<bool> mark_read(qint64 id);
    Result<void> mark_all_read();
    /// ok(true) when a record with this dedupe_key was received at or after since_ms.
    Result<bool> has_key_since(const QString& dedupe_key, qint64 since_ms);

  private:
    NotificationRepository() = default;
    bool ensure_table();
    static notifications::NotificationRecord map_row(QSqlQuery& q);

    std::atomic<bool> table_ready_{false};
};

} // namespace fincept
