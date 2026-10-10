#pragma once
#include <QDateTime>
#include <QMutex>
#include <QObject>
#include <QString>
#include <QVector>

#include <functional>
#include <memory>
#include <vector>

namespace fincept::notifications {

// ── Enumerations ──────────────────────────────────────────────────────────────

enum class NotifLevel { Info, Warning, Alert, Critical };
// External MUST stay last: values are persisted as INT in notification_history.
enum class NotifTrigger { Manual, PriceAlert, OrderFill, NewsAlert, WorkflowNode, External };

// ── Data structures ───────────────────────────────────────────────────────────

struct NotificationRequest {
    QString title;
    QString message;
    NotifLevel level = NotifLevel::Info;
    NotifTrigger trigger = NotifTrigger::Manual;
    QDateTime timestamp{QDateTime::currentDateTime()}; ///< time of the EVENT (inbox: field "ts")
    QString source;          ///< "news" | "scan" | "workflow" | "trading" | "system" | "external:<src>"
    QString dedupe_key;      ///< empty = no de-duplication
    int dedupe_s{0};         ///< >0: drop if a record with the same dedupe_key exists within this window
    bool local_only{false};  ///< true: never forwarded to external providers (Telegram, Slack, ...)
    QString action_screen;   ///< DockScreenRouter screen id to open on click; empty = none
};

struct NotificationRecord {
    qint64 id{0};
    NotificationRequest request;
    bool read{false};
    QDateTime received_at{QDateTime::currentDateTime()};
};

// ── Provider interface ────────────────────────────────────────────────────────

/// Abstract base for every external notification channel.
/// Each provider is responsible for reading/writing its own credentials
/// from SettingsRepository under category "notif_<provider_id>".
class INotificationProvider {
  public:
    virtual ~INotificationProvider() = default;

    /// Unique machine-readable identifier, e.g. "telegram".
    virtual QString provider_id() const = 0;

    /// Human-readable name shown in UI, e.g. "Telegram".
    virtual QString display_name() const = 0;

    /// Icon/emoji character used in settings UI header.
    virtual QString icon() const = 0;

    /// Returns true when the minimum required credentials are present.
    virtual bool is_configured() const = 0;

    /// True when the user has enabled this provider in Settings.
    virtual bool is_enabled() const = 0;

    /// Perform the HTTP call to deliver req. Invoke cb with (ok, error_string).
    virtual void send(const NotificationRequest& req, std::function<void(bool ok, QString error)> cb) = 0;

    /// Reload credentials from SettingsRepository.
    virtual void load_config() = 0;

    /// Persist current credential state to SettingsRepository.
    virtual void save_config() = 0;
};

// ── Service ───────────────────────────────────────────────────────────────────

/// Central notification dispatcher.  Maintains in-process history, dispatches
/// to all configured+enabled providers, and emits Qt signals for UI layers.
class NotificationService : public QObject {
    Q_OBJECT
  public:
    static NotificationService& instance();

    /// Dispatch to all enabled+configured providers that match the trigger filter.
    /// Always adds to history and emits notification_received regardless of
    /// external delivery outcome.
    void send(const NotificationRequest& req);

    /// Deliver to a single named provider — used for Settings "Test Send" button.
    void send_to(const QString& provider_id, const NotificationRequest& req,
                 std::function<void(bool ok, QString error)> cb);

    // ── History ───────────────────────────────────────────────────────────────
    /// Most-recent-first copy, safe to call from any thread.
    QVector<NotificationRecord> history_snapshot(int limit = 200) const;
    int unread_count() const;
    /// Safe from any thread (re-dispatched to the application thread).
    void mark_read(qint64 id);
    void mark_all_read();

    /// Reads a boolean setting with the correct "absent/empty -> default" rule.
    /// Keys: notifications.inapp, notifications.desktop, notifications.external, ...
    static bool setting_enabled(const QString& key, bool def);

    // ── Provider access (for settings page) ──────────────────────────────────
    QVector<INotificationProvider*> providers() const;
    INotificationProvider* provider(const QString& id) const;

    /// Call after settings are saved to reload all provider configs.
    void reload_all_configs();

  signals:
    void notification_received(const fincept::notifications::NotificationRecord& record);
    void unread_count_changed(int count);

  private:
    explicit NotificationService();
    void register_providers();
    void load_history();
    bool is_duplicate(const NotificationRequest& req, const QDateTime& now) const;

    std::vector<std::unique_ptr<INotificationProvider>> providers_;
    // history_ / unread_ are written only on the application thread but read by
    // history_snapshot()/unread_count() from any thread (MCP tools run on workers).
    mutable QMutex mutex_;
    QVector<NotificationRecord> history_; ///< most recent first, capped in RAM; SQLite is the source of truth
    int unread_{0};
    qint64 transient_id_{0}; ///< negative ids for records the DB could not persist
};

} // namespace fincept::notifications
