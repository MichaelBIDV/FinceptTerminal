// src/ui/notifications/DesktopNotifier.h
#pragma once
#include "services/notifications/NotificationService.h"
#include "ui/notifications/DesktopNotifyPolicy.h"

#include <QElapsedTimer>
#include <QObject>
#include <QString>

class QSystemTrayIcon;
class QWidget;
class QLabel;
class QTimer;

namespace fincept::ui {

/// Native desktop notifications, backed by QSystemTrayIcon (macOS: Notification
/// Center). The source of truth is fincept::notifications::NotificationService:
/// each record it emits may raise one OS banner, subject to desktop_policy:
/// the notifications.desktop setting, no banner while the app is active unless
/// the level is Critical (the in-app toast covers it), no banner for stale
/// records, bursts of more than 3 in 10 s folded into "N new notifications", and
/// content hidden while the terminal is locked. The Dock badge mirrors the unread
/// count. ToastService posts (transient UI errors) only get the self-rendered
/// in-app window, never an OS banner. Singleton; GUI thread only.
class DesktopNotifier : public QObject {
    Q_OBJECT
  public:
    static DesktopNotifier& instance();

    /// Create the tray icon and wire NotificationService + ToastService. Call once
    /// at startup on the GUI thread, after Database::open() and after the
    /// app/window icon is set. No-op if already initialised or no system tray is
    /// available.
    void init();

    /// Raise a native OS notification immediately (no policy applied).
    /// macOS: UNUserNotificationCenter, falling back to the tray. record_id lets a
    /// clicked banner open its record (0 = summary banner, just raise the window).
    void notify(const QString& title, const QString& body,
                fincept::notifications::NotifLevel level = fincept::notifications::NotifLevel::Info,
                qint64 record_id = 0);

  private:
    DesktopNotifier() = default;
    Q_DISABLE_COPY(DesktopNotifier)

    void on_core_notification(const fincept::notifications::NotificationRecord& rec);
    void on_unread_changed(int count);
    /// One banner for one record: its title + trimmed body, or only "1 new
    /// notification" while the terminal is locked.
    void show_banner(const fincept::notifications::NotificationRecord& rec);
    /// Emit what a folded burst held back: the record itself if only one was
    /// folded, otherwise one "N new notifications" summary.
    void flush_burst();
    /// showNormal/raise/activate the main terminal window (banner click, tray menu).
    void raise_main_window();
    static QString count_text(int n);
    /// True when the in-app toast will show the record: app active, a visible
    /// (not minimised) terminal window has focus, and In-App toasts are on.
    static bool in_app_covers();

    /// Self-rendered in-app toast that stays visible ~20s, used for ToastService
    /// posts. `severity` is a ToastService::Severity cast to int.
    void show_inapp(const QString& title, const QString& body, int severity);
    /// Legacy QSystemTrayIcon::showMessage path (non-macOS, or macOS fallback).
    void notify_tray(const QString& title, const QString& body, fincept::notifications::NotifLevel level);

    bool initialised_ = false;
    QSystemTrayIcon* tray_ = nullptr; ///< null on macOS (see init())
    QWidget* toast_ = nullptr;
    QLabel* toast_lbl_ = nullptr;
    QTimer* toast_timer_ = nullptr;

    desktop_policy::BurstGate burst_;
    QElapsedTimer burst_clock_; ///< monotonic: a wall-clock step back must not freeze the window
    QTimer* burst_timer_ = nullptr;
    int burst_pending_ = 0;
    bool burst_critical_ = false;
    fincept::notifications::NotificationRecord burst_last_; ///< latest folded record
};

} // namespace fincept::ui
