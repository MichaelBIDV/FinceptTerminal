// Unit tests for src/services/notifications/InboxSchema.h (header-only).
//
// The schema validator is what stands between any process running as this user
// and the app's notification history (and, through profile_get_notifications, the
// LLM context). These cases pin the contract in THONGBAO_SPEC.md §2: strict
// fields, a bad action never rejects the message, ttl expiry, External mapping.
//
// Including NotificationService.h only pulls in the declarations; nothing from
// NotificationService.cpp is referenced, so this links against Qt Core + Test only.

#include "services/notifications/InboxSchema.h"

#include <QJsonDocument>
#include <QJsonObject>
#include <QTest>

using namespace fincept::notifications;
using namespace fincept::notifications::inbox;

namespace {

QJsonObject base_message() {
    return QJsonObject{
        {"v", 1},
        {"id", "20261003T161056-langkinh-ab12cd34"},
        {"source", "langkinh"},
        {"level", "warning"},
        {"title", "HAG chạm cầu"},
        {"message", "Mẫu hình chặn cầu 01/10"},
        {"ts", "2026-10-03T16:10:56+07:00"},
        {"key", "langkinh:mauhinh:HAG:chan_cau:2026-10-01"},
        {"dedupe_s", 86400},
        {"ttl_s", 86400},
        {"action", QJsonObject{{"type", "open_screen"}, {"screen", "langkinh"}}},
    };
}

QByteArray bytes_of(const QJsonObject& o) {
    return QJsonDocument(o).toJson(QJsonDocument::Compact);
}

QDateTime at(const char* iso) {
    return QDateTime::fromString(QString::fromLatin1(iso), Qt::ISODate);
}

const QStringList kScreens = {"dashboard", "langkinh", "hdcv_launchpad", "news"};

} // namespace

class TestInboxSchema : public QObject {
    Q_OBJECT

  private slots:
    void valid_message_maps_to_external_request() {
        const auto r = parse_message(bytes_of(base_message()), at("2026-10-03T16:20:00+07:00"), kScreens);
        QCOMPARE(r.status, ParseStatus::Ok);
        QVERIFY2(r.reason.isEmpty(), qPrintable(r.reason));
        QCOMPARE(r.id, QStringLiteral("20261003T161056-langkinh-ab12cd34"));
        QCOMPARE(r.request.trigger, NotifTrigger::External);
        QCOMPARE(r.request.level, NotifLevel::Warning);
        QCOMPARE(r.request.source, QStringLiteral("external:langkinh"));
        QCOMPARE(r.request.dedupe_key, QStringLiteral("langkinh:mauhinh:HAG:chan_cau:2026-10-01"));
        QCOMPARE(r.request.dedupe_s, 86400);
        QVERIFY(r.request.local_only);
        QCOMPARE(r.request.action_screen, QStringLiteral("langkinh"));
        QCOMPARE(r.request.title, QStringLiteral("HAG chạm cầu"));
        // ts is the EVENT time, not the time the app read the file.
        QCOMPARE(r.request.timestamp.toMSecsSinceEpoch(), at("2026-10-03T09:10:56Z").toMSecsSinceEpoch());
    }

    void unknown_screen_drops_action_but_keeps_message() {
        auto o = base_message();
        o["action"] = QJsonObject{{"type", "open_screen"}, {"screen", "no_such_screen"}};
        const auto r = parse_message(bytes_of(o), at("2026-10-03T16:20:00+07:00"), kScreens);
        QCOMPARE(r.status, ParseStatus::Ok);
        QVERIFY(r.request.action_screen.isEmpty());
        QVERIFY(r.reason.contains(QStringLiteral("unknown screen")));
    }

    void malformed_action_is_dropped() {
        auto o = base_message();
        o["action"] = QJsonObject{{"type", "run_shell"}, {"screen", "langkinh"}};
        auto r = parse_message(bytes_of(o), at("2026-10-03T16:20:00+07:00"), kScreens);
        QCOMPARE(r.status, ParseStatus::Ok);
        QVERIFY(r.request.action_screen.isEmpty());

        o["action"] = QJsonObject{{"type", "open_screen"}, {"screen", "../etc"}};
        r = parse_message(bytes_of(o), at("2026-10-03T16:20:00+07:00"), kScreens);
        QCOMPARE(r.status, ParseStatus::Ok);
        QVERIFY(r.request.action_screen.isEmpty());

        o["action"] = QStringLiteral("langkinh");
        r = parse_message(bytes_of(o), at("2026-10-03T16:20:00+07:00"), kScreens);
        QCOMPARE(r.status, ParseStatus::Ok);
        QVERIFY(r.request.action_screen.isEmpty());
    }

    void no_router_yet_keeps_syntactically_valid_screen() {
        const auto r = parse_message(bytes_of(base_message()), at("2026-10-03T16:20:00+07:00"), {});
        QCOMPARE(r.status, ParseStatus::Ok);
        QCOMPARE(r.request.action_screen, QStringLiteral("langkinh"));
    }

    void ttl_expiry() {
        // ts 16:10:56 + 86400 s; one minute after that the message is expired.
        auto r = parse_message(bytes_of(base_message()), at("2026-10-04T16:12:00+07:00"), kScreens);
        QCOMPARE(r.status, ParseStatus::Expired);
        r = parse_message(bytes_of(base_message()), at("2026-10-04T16:10:00+07:00"), kScreens);
        QCOMPARE(r.status, ParseStatus::Ok);
        // ttl_s absent or 0: never expires.
        auto o = base_message();
        o.remove("ttl_s");
        r = parse_message(bytes_of(o), at("2027-01-01T00:00:00+07:00"), kScreens);
        QCOMPARE(r.status, ParseStatus::Ok);
    }

    void rejects_schema_violations_data() {
        QTest::addColumn<QString>("field");
        QTest::addColumn<QJsonValue>("value");
        QTest::newRow("version 2") << "v" << QJsonValue(2);
        QTest::newRow("version string") << "v" << QJsonValue("1");
        QTest::newRow("source upper") << "source" << QJsonValue("LangKinh");
        QTest::newRow("source slash") << "source" << QJsonValue("a/b");
        QTest::newRow("source too long") << "source" << QJsonValue(QString(49, QLatin1Char('a')));
        QTest::newRow("level unknown") << "level" << QJsonValue("debug");
        QTest::newRow("title empty") << "title" << QJsonValue("   ");
        QTest::newRow("title only zero-width") << "title" << QJsonValue(QString(QChar(0x200C)));
        QTest::newRow("title too long") << "title" << QJsonValue(QString(121, QLatin1Char('x')));
        QTest::newRow("title number") << "title" << QJsonValue(5);
        QTest::newRow("message too long") << "message" << QJsonValue(QString(1001, QLatin1Char('x')));
        QTest::newRow("ts garbage") << "ts" << QJsonValue("hôm qua");
        QTest::newRow("key too long") << "key" << QJsonValue(QString(129, QLatin1Char('k')));
        QTest::newRow("key object") << "key" << QJsonValue(QJsonObject{});
        QTest::newRow("dedupe negative") << "dedupe_s" << QJsonValue(-1);
        QTest::newRow("dedupe fractional") << "dedupe_s" << QJsonValue(1.5);
        QTest::newRow("ttl string") << "ttl_s" << QJsonValue("86400");
        QTest::newRow("ttl above cap") << "ttl_s" << QJsonValue(31LL * 86400);
        QTest::newRow("id with slash") << "id" << QJsonValue("../x");
    }

    void rejects_schema_violations() {
        QFETCH(QString, field);
        QFETCH(QJsonValue, value);
        auto o = base_message();
        o[field] = value;
        const auto r = parse_message(bytes_of(o), at("2026-10-03T16:20:00+07:00"), kScreens);
        QCOMPARE(r.status, ParseStatus::Invalid);
        QVERIFY(!r.reason.isEmpty());
    }

    void rejects_non_object_and_oversize() {
        const QDateTime now = at("2026-10-03T16:20:00+07:00");
        QCOMPARE(parse_message("[1,2]", now, kScreens).status, ParseStatus::Invalid);
        QCOMPARE(parse_message("{not json", now, kScreens).status, ParseStatus::Invalid);
        QCOMPARE(parse_message(QByteArray(), now, kScreens).status, ParseStatus::Invalid);

        auto o = base_message();
        o["padding"] = QString(kMaxFileBytes, QLatin1Char('p')); // unknown fields are fine, size is not
        QCOMPARE(parse_message(bytes_of(o), now, kScreens).status, ParseStatus::Invalid);
    }

    void optional_fields_default() {
        auto o = base_message();
        o.remove("key");
        o.remove("dedupe_s");
        o.remove("action");
        o.remove("message");
        o["origin"] = QJsonObject{{"tg_kind", "launchpad"}}; // forward-compatible extra field
        const auto r = parse_message(bytes_of(o), at("2026-10-03T16:20:00+07:00"), kScreens);
        QCOMPARE(r.status, ParseStatus::Ok);
        QVERIFY(r.request.dedupe_key.isEmpty());
        QCOMPARE(r.request.dedupe_s, 0);
        QVERIFY(r.request.message.isEmpty());
        QVERIFY(r.request.action_screen.isEmpty());
    }

    void clean_text_strips_controls_bidi_and_zero_width() {
        // e + combining acute (NFD) must come out as precomposed é (NFC).
        const QString nfd = QStringLiteral("Cafe") + QChar(0x0301);
        QCOMPARE(clean_text(nfd), QStringLiteral("Café"));

        QString dirty = QStringLiteral("A");
        dirty += QChar(0x202E); // RIGHT-TO-LEFT OVERRIDE
        dirty += QStringLiteral("B");
        dirty += QChar(0x200C); // ZWNJ
        dirty += QChar(0xFEFF); // BOM
        dirty += QChar(0x0007); // BEL
        dirty += QStringLiteral("C\r\nD\tE");
        QCOMPARE(clean_text(dirty), QStringLiteral("ABC\nD\tE"));

        // Markup is NOT stripped here; the UI renders with Qt::PlainText.
        QCOMPARE(clean_text(QStringLiteral("<b>x</b>")), QStringLiteral("<b>x</b>"));
    }

    void title_limit_counts_code_points_not_utf16_units() {
        auto o = base_message();
        // 120 emoji = 240 UTF-16 units but 120 code points: allowed.
        QString emoji;
        for (int i = 0; i < 120; ++i)
            emoji += QString::fromUcs4(U"\U0001F514", 1);
        o["title"] = emoji;
        QCOMPARE(parse_message(bytes_of(o), at("2026-10-03T16:20:00+07:00"), kScreens).status, ParseStatus::Ok);
    }

    void file_name_rules() {
        QVERIFY(valid_file_name(QStringLiteral("20261003T161056-langkinh-ab12cd34.json")));
        QVERIFY(!valid_file_name(QStringLiteral(".20261003.json"))); // hidden / temp
        QVERIFY(!valid_file_name(QStringLiteral("a b.json")));
        QVERIFY(!valid_file_name(QStringLiteral("x.json.part")));
        QVERIFY(!valid_file_name(QStringLiteral("x.txt")));
        QVERIFY(!valid_file_name(QStringLiteral("../x.json")));
    }
};

QTEST_GUILESS_MAIN(TestInboxSchema)
#include "tst_inbox_schema.moc"
