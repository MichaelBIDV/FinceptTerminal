#include "services/notifications/NotificationService.h"

#include "core/logging/Logger.h"
#include "storage/repositories/NotificationRepository.h"
#include "storage/repositories/SettingsRepository.h"

// Provider includes
#include "services/notifications/providers/DiscordProvider.h"
#include "services/notifications/providers/EmailProvider.h"
#include "services/notifications/providers/GotifyProvider.h"
#include "services/notifications/providers/MattermostProvider.h"
#include "services/notifications/providers/NtfyProvider.h"
#include "services/notifications/providers/OpsgenieProvider.h"
#include "services/notifications/providers/PagerDutyProvider.h"
#include "services/notifications/providers/PushbulletProvider.h"
#include "services/notifications/providers/PushoverProvider.h"
#include "services/notifications/providers/SMSProvider.h"
#include "services/notifications/providers/SlackProvider.h"
#include "services/notifications/providers/TeamsProvider.h"
#include "services/notifications/providers/TelegramProvider.h"
#include "services/notifications/providers/WebhookProvider.h"
#include "services/notifications/providers/WhatsAppProvider.h"

#include <QCoreApplication>
#include <QMutexLocker>
#include <QThread>

#include <algorithm>

namespace fincept::notifications {

// ── Singleton ─────────────────────────────────────────────────────────────────

// Named namespace on purpose: this TU is unity-batched with the 15 providers and,
// in some batches, with ui/notifications/NotificationService.cpp (ToastService).
namespace nsvc {
constexpr const char* kTag = "NotificationService";
constexpr int kHistoryRamCap = 200;

// The application thread, or nullptr before QCoreApplication exists.
QThread* app_thread() {
    auto* app = QCoreApplication::instance();
    return app ? app->thread() : nullptr;
}

const char* trigger_name(NotifTrigger t) {
    switch (t) {
        case NotifTrigger::Manual:
            return "manual";
        case NotifTrigger::PriceAlert:
            return "price_alert";
        case NotifTrigger::OrderFill:
            return "order_fill";
        case NotifTrigger::NewsAlert:
            return "news_alert";
        case NotifTrigger::WorkflowNode:
            return "workflow_node";
        case NotifTrigger::External:
            return "external";
    }
    return "?";
}
} // namespace nsvc

NotificationService& NotificationService::instance() {
    static NotificationService inst;
    return inst;
}

NotificationService::NotificationService() {
    // send()/mark_read() may be reached first from a worker (MCP tool handlers,
    // workflow nodes, EventBus publishers on QtConcurrent). Re-home the singleton
    // on the application thread so the queued re-dispatch below always lands on
    // the GUI thread (same pattern as RiskManager). Moving is only legal from the
    // object's current thread, which is exactly where construction runs.
    if (auto* app_thread = nsvc::app_thread(); app_thread && thread() != app_thread)
        moveToThread(app_thread);
    register_providers();
    load_history();
}

void NotificationService::register_providers() {
    providers_.clear();
    providers_.emplace_back(std::make_unique<TelegramProvider>());
    providers_.emplace_back(std::make_unique<DiscordProvider>());
    providers_.emplace_back(std::make_unique<SlackProvider>());
    providers_.emplace_back(std::make_unique<EmailProvider>());
    providers_.emplace_back(std::make_unique<WhatsAppProvider>());
    providers_.emplace_back(std::make_unique<PushoverProvider>());
    providers_.emplace_back(std::make_unique<NtfyProvider>());
    providers_.emplace_back(std::make_unique<PushbulletProvider>());
    providers_.emplace_back(std::make_unique<GotifyProvider>());
    providers_.emplace_back(std::make_unique<MattermostProvider>());
    providers_.emplace_back(std::make_unique<TeamsProvider>());
    providers_.emplace_back(std::make_unique<WebhookProvider>());
    providers_.emplace_back(std::make_unique<PagerDutyProvider>());
    providers_.emplace_back(std::make_unique<OpsgenieProvider>());
    providers_.emplace_back(std::make_unique<SMSProvider>());

    for (auto& p : providers_)
        p->load_config();

    LOG_INFO("NotificationService", "Registered 15 notification providers");
}

void NotificationService::load_history() {
    auto& repo = NotificationRepository::instance();
    auto rows = repo.recent(nsvc::kHistoryRamCap);
    auto unread = repo.unread_count();
    if (rows.is_err() || unread.is_err()) {
        LOG_WARN(nsvc::kTag, "Notification history unavailable — starting with an empty in-memory history");
        return;
    }
    QMutexLocker lock(&mutex_);
    history_ = std::move(rows.value());
    unread_ = unread.value();
    LOG_INFO(nsvc::kTag, QString("Loaded %1 notifications from history (%2 unread)").arg(history_.size()).arg(unread_));
}

bool NotificationService::setting_enabled(const QString& key, bool def) {
    // Absent or empty means "never set": use the default. Only a stored value
    // decides — an empty read used to compare "" == "1" and silently turned every
    // default-true switch off (the in-app history never emitted).
    auto r = SettingsRepository::instance().get(key);
    return r.is_ok() && !r.value().isEmpty() ? (r.value() == "1") : def;
}

bool NotificationService::is_duplicate(const NotificationRequest& req, const QDateTime& now) const {
    if (req.dedupe_key.isEmpty() || req.dedupe_s <= 0)
        return false;
    const qint64 since_ms = now.toMSecsSinceEpoch() - static_cast<qint64>(req.dedupe_s) * 1000;
    auto r = NotificationRepository::instance().has_key_since(req.dedupe_key, since_ms);
    if (r.is_ok())
        return r.value();
    // DB unavailable — fall back to the in-memory window rather than failing open.
    QMutexLocker lock(&mutex_);
    for (const auto& rec : history_) {
        if (rec.request.dedupe_key == req.dedupe_key && rec.received_at.toMSecsSinceEpoch() >= since_ms)
            return true;
    }
    return false;
}

// ── Send ──────────────────────────────────────────────────────────────────────

void NotificationService::send(const NotificationRequest& req_in) {
    if (auto* app_thread = nsvc::app_thread(); app_thread && QThread::currentThread() != app_thread) {
        QMetaObject::invokeMethod(
            this, [this, req_in]() { send(req_in); }, Qt::QueuedConnection);
        return;
    }

    NotificationRequest req = req_in;

    // Per-trigger filter. Manual / WorkflowNode always pass.
    bool trigger_allowed = true;
    const char* filter_key = nullptr;
    switch (req.trigger) {
        case NotifTrigger::PriceAlert:
            filter_key = "notifications.price_alerts";
            break;
        case NotifTrigger::OrderFill:
            filter_key = "notifications.order_fills";
            break;
        case NotifTrigger::NewsAlert:
            filter_key = "notifications.news_alerts";
            break;
        case NotifTrigger::External:
            filter_key = "notifications.external";
            break;
        case NotifTrigger::Manual:
        case NotifTrigger::WorkflowNode:
            break;
    }
    if (filter_key)
        trigger_allowed = setting_enabled(QString::fromLatin1(filter_key), true);
    if (!trigger_allowed) {
        LOG_INFO(nsvc::kTag, QString("Suppressed (%1 is off, trigger=%2, source=%3): %4")
                                   .arg(QString::fromLatin1(filter_key),
                                        QString::fromLatin1(nsvc::trigger_name(req.trigger)), req.source, req.title));
        return;
    }

    // Inbox / external jobs already have their own outbound gate (tg_gate):
    // never echo them to Telegram & co.
    if (req.trigger == NotifTrigger::External)
        req.local_only = true;

    const QDateTime now = QDateTime::currentDateTime();
    if (is_duplicate(req, now)) {
        LOG_INFO(nsvc::kTag, QString("Suppressed (dedupe key=%1 within %2s, source=%3): %4")
                                   .arg(req.dedupe_key, QString::number(req.dedupe_s), req.source, req.title));
        return;
    }

    // Always persist and emit — notifications.inapp only decides whether the UI
    // shows a toast; the bell, the panel and the desktop banner all need the record.
    NotificationRecord record;
    record.request = req;
    record.read = false;
    record.received_at = now;
    auto ins = NotificationRepository::instance().insert(record);
    if (ins.is_ok()) {
        record.id = ins.value();
    } else {
        LOG_WARN(nsvc::kTag, QString("Notification not persisted (%1): %2")
                                   .arg(QString::fromStdString(ins.error()), req.title));
    }

    int unread = 0;
    {
        QMutexLocker lock(&mutex_);
        if (record.id == 0)
            record.id = --transient_id_;
        history_.prepend(record);
        if (history_.size() > nsvc::kHistoryRamCap)
            history_.removeLast();
        unread = ++unread_;
    }

    emit notification_received(record);
    emit unread_count_changed(unread);

    if (req.local_only)
        return;

    // Dispatch to external providers
    for (auto& p : providers_) {
        if (!p->is_enabled() || !p->is_configured())
            continue;
        const QString pid = p->provider_id();
        p->send(req, [pid](bool ok, const QString& err) {
            if (ok) {
                LOG_INFO("NotificationService", QString("Delivered via %1").arg(pid).toStdString().c_str());
            } else {
                LOG_WARN("NotificationService",
                         QString("Delivery failed via %1: %2").arg(pid, err).toStdString().c_str());
            }
        });
    }
}

void NotificationService::send_to(const QString& provider_id, const NotificationRequest& req,
                                  std::function<void(bool, QString)> cb) {
    auto* p = provider(provider_id);
    if (!p) {
        cb(false, QString("Provider '%1' not found").arg(provider_id));
        return;
    }
    p->send(req, std::move(cb));
}

// ── History ───────────────────────────────────────────────────────────────────

QVector<NotificationRecord> NotificationService::history_snapshot(int limit) const {
    QMutexLocker lock(&mutex_);
    if (limit <= 0 || limit >= history_.size())
        return history_;
    return history_.mid(0, limit);
}

int NotificationService::unread_count() const {
    QMutexLocker lock(&mutex_);
    return unread_;
}

void NotificationService::mark_read(qint64 id) {
    if (auto* app_thread = nsvc::app_thread(); app_thread && QThread::currentThread() != app_thread) {
        QMetaObject::invokeMethod(
            this, [this, id]() { mark_read(id); }, Qt::QueuedConnection);
        return;
    }

    auto& repo = NotificationRepository::instance();
    auto flipped = id > 0 ? repo.mark_read(id) : Result<bool>::ok(false);
    bool changed = flipped.is_ok() && flipped.value();
    {
        QMutexLocker lock(&mutex_);
        for (auto& r : history_) {
            if (r.id == id) {
                changed = changed || !r.read; // transient (unpersisted) record, or DB update failed
                r.read = true;
                break;
            }
        }
    }
    if (!changed)
        return;

    // The DB count is authoritative (rows outside the RAM window, pruning).
    auto n = repo.unread_count();
    int unread = 0;
    {
        QMutexLocker lock(&mutex_);
        unread_ = n.is_ok() ? n.value() : std::max(0, unread_ - 1);
        unread = unread_;
    }
    emit unread_count_changed(unread);
}

void NotificationService::mark_all_read() {
    if (auto* app_thread = nsvc::app_thread(); app_thread && QThread::currentThread() != app_thread) {
        QMetaObject::invokeMethod(
            this, [this]() { mark_all_read(); }, Qt::QueuedConnection);
        return;
    }

    auto r = NotificationRepository::instance().mark_all_read();
    if (r.is_err())
        LOG_WARN(nsvc::kTag, QString("mark_all_read not persisted: %1").arg(QString::fromStdString(r.error())));
    {
        QMutexLocker lock(&mutex_);
        for (auto& rec : history_)
            rec.read = true;
        unread_ = 0;
    }
    emit unread_count_changed(0);
}

// ── Provider access ───────────────────────────────────────────────────────────

QVector<INotificationProvider*> NotificationService::providers() const {
    QVector<INotificationProvider*> out;
    out.reserve(static_cast<int>(providers_.size()));
    for (const auto& p : providers_)
        out.append(p.get());
    return out;
}

INotificationProvider* NotificationService::provider(const QString& id) const {
    for (const auto& p : providers_) {
        if (p->provider_id() == id)
            return p.get();
    }
    return nullptr;
}

void NotificationService::reload_all_configs() {
    for (auto& p : providers_)
        p->load_config();
    LOG_INFO("NotificationService", "All provider configs reloaded");
}

} // namespace fincept::notifications
