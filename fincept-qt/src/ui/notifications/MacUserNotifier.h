// src/ui/notifications/MacUserNotifier.h
#pragma once
#include <QtGlobal>
#include <QString>

#include <functional>

/// macOS banners through UNUserNotificationCenter (THONGBAO_SPEC §4, phase 2).
/// QSystemTrayIcon::showMessage in Qt 6.8 still goes through the deprecated
/// NSUserNotificationCenter, which macOS 27 registers but never delivers for this
/// ad-hoc signed bundle (checked 03/10: 0 delivered records). Implemented in
/// MacUserNotifier.mm; every function is a no-op returning false off macOS.
namespace fincept::ui::macnotify {

#if defined(Q_OS_MACOS)
/// True when running from a .app bundle with a bundle identifier, the only case
/// in which UNUserNotificationCenter can be used at all.
bool available();

/// Install the UN delegate. on_click runs on the GUI thread with the record id
/// carried by the clicked banner (0 if unknown). Call once, on the GUI thread.
void init(std::function<void(qint64 record_id)> on_click);

/// Ask for banner permission once (system prompt). Call while the user is at the
/// machine (app launch); concurrent calls collapse into one request.
void request_authorization();

/// Post one banner. Permission not decided yet: asks (once) and drops this banner
/// (it is already in the bell). Turned off by the user: dropped silently.
/// fallback runs on the GUI thread only if macOS rejects an authorized request.
void post(qint64 record_id, const QString& title, const QString& body, bool critical,
          std::function<void()> fallback);

/// Remove every delivered/pending banner of this app from Notification Center
/// (terminal lock: no alert content may stay readable there).
void clear_delivered();
#else
inline void request_authorization() {}
inline void clear_delivered() {}
inline bool available() {
    return false;
}
inline void init(std::function<void(qint64)>) {}
inline void post(qint64, const QString&, const QString&, bool, std::function<void()> fallback) {
    if (fallback)
        fallback();
}
#endif

} // namespace fincept::ui::macnotify
