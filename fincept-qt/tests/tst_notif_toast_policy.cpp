// Unit tests for src/ui/widgets/NotifToastPolicy.h (header-only, QtCore only).
//
// The toast gate is what keeps a burst of stale records (cache-first News at
// startup, an inbox job replaying hours-old events) from popping toasts. Pin
// both age limits at their edges and the 4-8 s dismiss ladder.

#include "ui/widgets/NotifToastPolicy.h"

#include <QTest>

using fincept::notifications::NotificationRecord;
using fincept::notifications::NotifLevel;
namespace policy = fincept::ui::notif_toast_policy;

namespace {

NotificationRecord make_record(const QDateTime& received_at, const QDateTime& event_ts) {
    NotificationRecord rec;
    rec.received_at = received_at;
    rec.request.timestamp = event_ts;
    return rec;
}

} // namespace

class TstNotifToastPolicy : public QObject {
    Q_OBJECT
  private slots:
    void fresh_when_just_received() {
        const QDateTime now = QDateTime::currentDateTime();
        QVERIFY(policy::is_fresh(make_record(now, now), now));
    }

    void received_age_limit_is_15_minutes() {
        const QDateTime now = QDateTime::currentDateTime();
        QVERIFY(policy::is_fresh(make_record(now.addSecs(-(15 * 60 - 1)), now), now));
        QVERIFY(!policy::is_fresh(make_record(now.addSecs(-15 * 60), now), now));
    }

    void event_age_limit_is_6_hours() {
        const QDateTime now = QDateTime::currentDateTime();
        QVERIFY(policy::is_fresh(make_record(now, now.addSecs(-(6 * 3600 - 1))), now));
        QVERIFY(!policy::is_fresh(make_record(now, now.addSecs(-6 * 3600)), now));
        // A day-old inbox event delivered right now must not toast.
        QVERIFY(!policy::is_fresh(make_record(now, now.addDays(-1)), now));
    }

    void invalid_timestamps() {
        const QDateTime now = QDateTime::currentDateTime();
        // Unknown event time is not held against a freshly received record...
        QVERIFY(policy::is_fresh(make_record(now, QDateTime()), now));
        // ...but a record with no receive time never toasts.
        QVERIFY(!policy::is_fresh(make_record(QDateTime(), now), now));
    }

    void future_event_time_is_fresh() {
        // Clock skew on an external job ("ts" slightly ahead) must not block the toast.
        const QDateTime now = QDateTime::currentDateTime();
        QVERIFY(policy::is_fresh(make_record(now, now.addSecs(120)), now));
    }

    void dismiss_ladder_by_level() {
        QCOMPARE(policy::dismiss_ms(NotifLevel::Info), 4000);
        QCOMPARE(policy::dismiss_ms(NotifLevel::Warning), 5000);
        QCOMPARE(policy::dismiss_ms(NotifLevel::Alert), 6000);
        QCOMPARE(policy::dismiss_ms(NotifLevel::Critical), 8000);
    }
};

QTEST_APPLESS_MAIN(TstNotifToastPolicy)
#include "tst_notif_toast_policy.moc"
