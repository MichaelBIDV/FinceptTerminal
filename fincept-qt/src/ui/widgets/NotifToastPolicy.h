#pragma once
// NotifToastPolicy.h, pure (QtCore-only) rules for the in-app notification toast.
//
// Kept header-only and free of QWidget so tests/tst_notif_toast_policy.cpp can
// exercise it while linking QtCore alone. Named namespace on purpose: the widget
// TUs that include this are unity-batched (see CMakeLists.txt UI_SOURCES).

#include "services/notifications/NotificationService.h"

#include <QDateTime>

namespace fincept::ui::notif_toast_policy {

/// A record must have reached the service less than this long ago to toast.
inline constexpr qint64 kMaxReceivedAgeS = 15 * 60;
/// The event itself (request.timestamp, e.g. an inbox job's "ts") must be younger than this.
inline constexpr qint64 kMaxEventAgeS = 6 * 60 * 60;

/// True when the record is recent enough to pop a toast. An invalid event
/// timestamp is not held against the record; an invalid received_at is.
inline bool is_fresh(const notifications::NotificationRecord& rec, const QDateTime& now) {
    if (!rec.received_at.isValid() || rec.received_at.secsTo(now) >= kMaxReceivedAgeS)
        return false;
    if (rec.request.timestamp.isValid() && rec.request.timestamp.secsTo(now) >= kMaxEventAgeS)
        return false;
    return true;
}

/// Auto-dismiss delay, 4–8 s by severity.
inline int dismiss_ms(notifications::NotifLevel level) {
    switch (level) {
        case notifications::NotifLevel::Warning:
            return 5000;
        case notifications::NotifLevel::Alert:
            return 6000;
        case notifications::NotifLevel::Critical:
            return 8000;
        default:
            return 4000;
    }
}

} // namespace fincept::ui::notif_toast_policy
