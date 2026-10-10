// src/ui/notifications/DesktopNotifyPolicy.h
#pragma once
// Pure decision logic behind DesktopNotifier: which core notifications may raise a
// native OS banner, how the banner body is trimmed, and when a burst is folded into
// one "N new notifications" banner. Header-only and QtCore-only so that
// tests/tst_desktop_policy.cpp can exercise it without QtGui/QtWidgets.

#include <QChar>
#include <QDateTime>
#include <QString>
#include <QVector>

namespace fincept::ui::desktop_policy {

inline constexpr int kBodyMaxChars = 240;         ///< banner body cap, ellipsis included
inline constexpr qint64 kBurstWindowMs = 10'000;  ///< burst detection window
inline constexpr int kBurstMaxBanners = 3;        ///< individual banners allowed per window
inline constexpr qint64 kMaxReceivedAgeS = 15 * 60; ///< record received longer ago → no banner
inline constexpr qint64 kMaxEventAgeS = 6 * 3600;   ///< event (request.timestamp) older → no banner

enum class Gate { Show, Disabled, Stale, AppActive };

/// Whether a core notification may raise a native banner.
///  - `desktop_enabled` is the notifications.desktop setting.
///  - Stale records never raise one, whatever their level.
///  - While the app is the active application the in-app toast covers it, so only
///    `critical` records get an OS banner too.
/// Invalid timestamps are not treated as stale (nothing to judge by).
inline Gate gate(bool desktop_enabled, bool app_active, bool critical, const QDateTime& received_at,
                 const QDateTime& event_ts, const QDateTime& now) {
    if (!desktop_enabled)
        return Gate::Disabled;
    if (received_at.isValid() && received_at.secsTo(now) > kMaxReceivedAgeS)
        return Gate::Stale;
    if (event_ts.isValid() && event_ts.secsTo(now) > kMaxEventAgeS)
        return Gate::Stale;
    if (app_active && !critical)
        return Gate::AppActive;
    return Gate::Show;
}

inline const char* gate_name(Gate g) {
    switch (g) {
        case Gate::Show:
            return "show";
        case Gate::Disabled:
            return "disabled";
        case Gate::Stale:
            return "stale";
        case Gate::AppActive:
            return "app active";
    }
    return "?";
}

/// Plain-text banner body: trimmed, capped at kBodyMaxChars UTF-16 units including
/// the trailing ellipsis, never splitting a surrogate pair.
inline QString banner_body(const QString& message) {
    const QString s = message.trimmed();
    if (s.size() <= kBodyMaxChars)
        return s;
    int cut = kBodyMaxChars - 1; // leave room for U+2026
    if (s.at(cut - 1).isHighSurrogate())
        --cut;
    return s.left(cut) + QChar(0x2026);
}

/// Sliding-window burst detector. admit() records an event and returns true while at
/// most kBurstMaxBanners events fall inside the last kBurstWindowMs; beyond that it
/// returns false and the caller folds the event into a summary banner. Coalesced
/// events still count, so a sustained storm keeps being folded.
class BurstGate {
  public:
    bool admit(qint64 now_ms) {
        while (!times_.isEmpty() && now_ms - times_.first() >= kBurstWindowMs)
            times_.removeFirst();
        times_.append(now_ms);
        return times_.size() <= kBurstMaxBanners;
    }

  private:
    QVector<qint64> times_;
};

} // namespace fincept::ui::desktop_policy
