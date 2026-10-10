// Unit tests for src/ui/notifications/DesktopNotifyPolicy.h
//
// The policy decides which core notification records may raise a native macOS
// banner (THONGBAO_SPEC section 4). Header-only, QtCore-only, zero app sources.

#include "ui/notifications/DesktopNotifyPolicy.h"

#include <QDateTime>
#include <QString>
#include <QTest>
#include <QTimeZone>

namespace dp = fincept::ui::desktop_policy;

class TstDesktopPolicy : public QObject {
    Q_OBJECT

  private slots:
    void disabled_wins_over_everything();
    void inactive_app_shows();
    void active_app_suppresses_non_critical();
    void active_app_lets_critical_through();
    void stale_received_at_suppresses();
    void stale_event_suppresses_even_critical();
    void invalid_or_future_timestamps_are_not_stale();
    void body_short_is_trimmed_only();
    void body_long_is_capped_with_ellipsis();
    void body_cap_does_not_split_surrogate_pair();
    void burst_admits_three_then_folds();
    void burst_window_slides();
    void burst_storm_keeps_folding();
};

static QDateTime now_ts() {
    return QDateTime(QDate(2026, 10, 3), QTime(16, 10, 0), QTimeZone::UTC);
}

void TstDesktopPolicy::disabled_wins_over_everything() {
    const QDateTime n = now_ts();
    QCOMPARE(dp::gate(false, false, true, n, n, n), dp::Gate::Disabled);
    QCOMPARE(dp::gate(false, true, false, n.addSecs(-3600), n.addDays(-2), n), dp::Gate::Disabled);
}

void TstDesktopPolicy::inactive_app_shows() {
    const QDateTime n = now_ts();
    QCOMPARE(dp::gate(true, false, false, n, n, n), dp::Gate::Show);
}

void TstDesktopPolicy::active_app_suppresses_non_critical() {
    const QDateTime n = now_ts();
    QCOMPARE(dp::gate(true, true, false, n, n, n), dp::Gate::AppActive);
}

void TstDesktopPolicy::active_app_lets_critical_through() {
    const QDateTime n = now_ts();
    QCOMPARE(dp::gate(true, true, true, n, n, n), dp::Gate::Show);
}

void TstDesktopPolicy::stale_received_at_suppresses() {
    const QDateTime n = now_ts();
    // exactly 15 min is still fresh, one second more is stale
    QCOMPARE(dp::gate(true, false, false, n.addSecs(-15 * 60), n, n), dp::Gate::Show);
    QCOMPARE(dp::gate(true, false, false, n.addSecs(-15 * 60 - 1), n, n), dp::Gate::Stale);
}

void TstDesktopPolicy::stale_event_suppresses_even_critical() {
    const QDateTime n = now_ts();
    QCOMPARE(dp::gate(true, false, true, n, n.addSecs(-6 * 3600), n), dp::Gate::Show);
    QCOMPARE(dp::gate(true, false, true, n, n.addSecs(-6 * 3600 - 1), n), dp::Gate::Stale);
    QCOMPARE(dp::gate(true, true, true, n, n.addDays(-1), n), dp::Gate::Stale);
}

void TstDesktopPolicy::invalid_or_future_timestamps_are_not_stale() {
    const QDateTime n = now_ts();
    QCOMPARE(dp::gate(true, false, false, QDateTime(), QDateTime(), n), dp::Gate::Show);
    QCOMPARE(dp::gate(true, false, false, n, n.addSecs(3600), n), dp::Gate::Show);
    // same instant expressed in another zone is not "older"
    const QDateTime ict = n.toTimeZone(QTimeZone(7 * 3600));
    QCOMPARE(dp::gate(true, false, false, ict, ict, n), dp::Gate::Show);
}

void TstDesktopPolicy::body_short_is_trimmed_only() {
    QCOMPARE(dp::banner_body(QStringLiteral("  HAG <b>chan cau</b>\n")), QStringLiteral("HAG <b>chan cau</b>"));
    QCOMPARE(dp::banner_body(QString()), QString());
    const QString exact(dp::kBodyMaxChars, QLatin1Char('x'));
    QCOMPARE(dp::banner_body(exact), exact);
}

void TstDesktopPolicy::body_long_is_capped_with_ellipsis() {
    const QString out = dp::banner_body(QString(300, QLatin1Char('a')));
    QCOMPARE(out.size(), dp::kBodyMaxChars);
    QVERIFY(out.endsWith(QChar(0x2026)));
    QCOMPARE(out.left(dp::kBodyMaxChars - 1), QString(dp::kBodyMaxChars - 1, QLatin1Char('a')));
}

void TstDesktopPolicy::body_cap_does_not_split_surrogate_pair() {
    // 238 ASCII + one astral char (2 UTF-16 units at 238..239) + tail: the naive
    // cut at 239 would keep only the high surrogate.
    QString s(dp::kBodyMaxChars - 2, QLatin1Char('a'));
    s += QString::fromUcs4(U"\U0001F4C8");
    s += QString(20, QLatin1Char('b'));
    const QString out = dp::banner_body(s);
    QVERIFY(out.size() <= dp::kBodyMaxChars);
    QVERIFY(out.endsWith(QChar(0x2026)));
    QVERIFY(!out.at(out.size() - 2).isHighSurrogate());
    QCOMPARE(out.size(), dp::kBodyMaxChars - 1);
}

void TstDesktopPolicy::burst_admits_three_then_folds() {
    dp::BurstGate g;
    const qint64 t = 1'000'000;
    QVERIFY(g.admit(t));
    QVERIFY(g.admit(t + 100));
    QVERIFY(g.admit(t + 200));
    QVERIFY(!g.admit(t + 300));
    QVERIFY(!g.admit(t + 9'999));
}

void TstDesktopPolicy::burst_window_slides() {
    dp::BurstGate g;
    const qint64 t = 1'000'000;
    QVERIFY(g.admit(t));
    QVERIFY(g.admit(t + 1'000));
    QVERIFY(g.admit(t + 2'000));
    // t has left the 10 s window, so only 2 remain before this one
    QVERIFY(g.admit(t + 10'000));
    QVERIFY(!g.admit(t + 10'500));
    // a quiet minute resets everything
    QVERIFY(g.admit(t + 70'000));
}

void TstDesktopPolicy::burst_storm_keeps_folding() {
    dp::BurstGate g;
    qint64 t = 0;
    int shown = 0;
    for (int i = 0; i < 100; ++i, t += 1'000) // one event per second for 100 s
        shown += g.admit(t) ? 1 : 0;
    QCOMPARE(shown, 3); // folded events keep the window full
}

QTEST_APPLESS_MAIN(TstDesktopPolicy)
#include "tst_desktop_policy.moc"
