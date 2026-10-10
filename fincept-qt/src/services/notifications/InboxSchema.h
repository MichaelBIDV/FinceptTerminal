#pragma once
// InboxSchema.h, pure validation of one external-job inbox message (schema v1).
//
// Header-only and Qt Core only, so tests/tst_inbox_schema.cpp can exercise it
// without linking the app. InboxService does the file-level checks (owner,
// symlink, size, rename protocol) and hands the bytes to parse_message().
//
// Schema v1 (one file <id>.json in <profile_root>/inbox/new):
//   {"v":1,"id":"…","source":"langkinh","level":"info|warning|alert|critical",
//    "title":"≤120 chars","message":"≤1000 chars, plain text","ts":"ISO-8601 with offset",
//    "key":"dedupe key","dedupe_s":86400,"ttl_s":86400,
//    "action":{"type":"open_screen","screen":"langkinh"}}

#include "services/notifications/NotificationService.h"

#include <QByteArray>
#include <QDateTime>
#include <QJsonDocument>
#include <QJsonObject>
#include <QJsonParseError>
#include <QJsonValue>
#include <QRegularExpression>
#include <QString>
#include <QStringList>

namespace fincept::notifications::inbox {

inline constexpr qint64 kMaxFileBytes = 16 * 1024;
inline constexpr int kMaxTitleChars = 120;
inline constexpr int kMaxMessageChars = 1000;
inline constexpr int kMaxKeyChars = 128;
inline constexpr qint64 kMaxWindowSecs = 30LL * 86400; // cap for dedupe_s / ttl_s

enum class ParseStatus { Ok, Expired, Invalid };

struct ParseResult {
    ParseStatus status = ParseStatus::Invalid;
    QString reason; ///< Invalid: why it was rejected. Ok: non-fatal note (e.g. action dropped).
    QString id;
    NotificationRequest request; ///< filled when status != Invalid
};

/// `source` field: ^[a-z0-9][a-z0-9._-]{0,47}$
inline bool valid_source(const QString& s) {
    static const QRegularExpression re(QStringLiteral("^[a-z0-9][a-z0-9._-]{0,47}$"));
    return re.match(s).hasMatch();
}

/// Syntactic check of a DockScreenRouter id (the live registry is checked separately).
inline bool valid_screen_id(const QString& s) {
    static const QRegularExpression re(QStringLiteral("^[a-z0-9_]{1,48}$"));
    return re.match(s).hasMatch();
}

/// Message `id` field.
inline bool valid_message_id(const QString& s) {
    static const QRegularExpression re(QStringLiteral("^[A-Za-z0-9._-]{1,96}$"));
    return re.match(s).hasMatch();
}

/// File name in new/: <id>.json, no path separators, not hidden.
inline bool valid_file_name(const QString& name) {
    static const QRegularExpression re(QStringLiteral("^[A-Za-z0-9_-][A-Za-z0-9._-]{0,95}\\.json$"));
    return re.match(name).hasMatch();
}

/// NFC, strip C0 (except \n and \t), DEL, C1, bidi embeddings/overrides/isolates,
/// LRM/RLM/ALM and zero-width characters (U+200B–U+200D, U+2060, U+FEFF). CRLF → LF.
inline QString clean_text(const QString& in) {
    QString s = in.normalized(QString::NormalizationForm_C);
    s.replace(QStringLiteral("\r\n"), QStringLiteral("\n"));
    QString out;
    out.reserve(s.size());
    for (const QChar c : s) {
        const char16_t u = c.unicode();
        const bool c0 = u < 0x20 && u != u'\n' && u != u'\t';
        const bool c1 = u >= 0x7F && u <= 0x9F;
        const bool zero_width = (u >= 0x200B && u <= 0x200D) || u == 0x2060 || u == 0xFEFF;
        const bool bidi = (u >= 0x200E && u <= 0x200F) || (u >= 0x202A && u <= 0x202E) ||
                          (u >= 0x2066 && u <= 0x2069) || u == 0x061C;
        if (!(c0 || c1 || zero_width || bidi))
            out.append(c);
    }
    return out.trimmed();
}

/// Length in Unicode code points (the helper truncates by code points too).
inline int code_points(const QString& s) {
    return static_cast<int>(s.toUcs4().size());
}

namespace detail {
inline bool read_window(const QJsonObject& o, const char* name, qint64 def, qint64& out) {
    const QJsonValue v = o.value(QLatin1String(name));
    if (v.isUndefined() || v.isNull()) {
        out = def;
        return true;
    }
    if (!v.isDouble())
        return false;
    const double d = v.toDouble();
    const qint64 i = v.toInteger(-1);
    if (static_cast<double>(i) != d || i < 0 || i > kMaxWindowSecs)
        return false;
    out = i;
    return true;
}

inline ParseResult invalid(const QString& why) {
    ParseResult r;
    r.status = ParseStatus::Invalid;
    r.reason = why;
    return r;
}
} // namespace detail

/// Validates and maps one message. `known_screens` is the live DockScreenRouter
/// registry; when it is empty (no window yet) a syntactically valid screen id is
/// kept and the router ignores it at click time if it turns out to be unknown.
inline ParseResult parse_message(const QByteArray& bytes, const QDateTime& now, const QStringList& known_screens) {
    if (bytes.size() > kMaxFileBytes)
        return detail::invalid(QStringLiteral("larger than 16 KB"));

    QJsonParseError perr{};
    const QJsonDocument doc = QJsonDocument::fromJson(bytes, &perr);
    if (perr.error != QJsonParseError::NoError || !doc.isObject())
        return detail::invalid(QStringLiteral("not a JSON object: %1").arg(perr.errorString()));
    const QJsonObject o = doc.object();

    const QJsonValue v = o.value(QLatin1String("v"));
    if (!v.isDouble() || v.toDouble() != 1.0)
        return detail::invalid(QStringLiteral("unsupported schema version"));

    const QString id = o.value(QLatin1String("id")).toString();
    if (!valid_message_id(id))
        return detail::invalid(QStringLiteral("bad id"));

    const QString source = o.value(QLatin1String("source")).toString();
    if (!valid_source(source))
        return detail::invalid(QStringLiteral("bad source"));

    NotifLevel level = NotifLevel::Info;
    const QString level_s = o.value(QLatin1String("level")).toString();
    if (level_s == QLatin1String("info"))
        level = NotifLevel::Info;
    else if (level_s == QLatin1String("warning"))
        level = NotifLevel::Warning;
    else if (level_s == QLatin1String("alert"))
        level = NotifLevel::Alert;
    else if (level_s == QLatin1String("critical"))
        level = NotifLevel::Critical;
    else
        return detail::invalid(QStringLiteral("bad level"));

    const QJsonValue title_v = o.value(QLatin1String("title"));
    const QJsonValue message_v = o.value(QLatin1String("message"));
    if (!title_v.isString() || !(message_v.isString() || message_v.isUndefined()))
        return detail::invalid(QStringLiteral("title/message must be strings"));
    const QString title = clean_text(title_v.toString());
    const QString message = clean_text(message_v.toString());
    if (title.isEmpty())
        return detail::invalid(QStringLiteral("empty title"));
    if (code_points(title) > kMaxTitleChars)
        return detail::invalid(QStringLiteral("title longer than 120 characters"));
    if (code_points(message) > kMaxMessageChars)
        return detail::invalid(QStringLiteral("message longer than 1000 characters"));

    const QDateTime ts = QDateTime::fromString(o.value(QLatin1String("ts")).toString(), Qt::ISODate);
    if (!ts.isValid())
        return detail::invalid(QStringLiteral("bad ts"));

    const QJsonValue key_v = o.value(QLatin1String("key"));
    if (!(key_v.isString() || key_v.isUndefined() || key_v.isNull()))
        return detail::invalid(QStringLiteral("key must be a string"));
    const QString key = clean_text(key_v.toString());
    if (code_points(key) > kMaxKeyChars)
        return detail::invalid(QStringLiteral("key longer than 128 characters"));

    qint64 dedupe_s = 0;
    qint64 ttl_s = 0;
    if (!detail::read_window(o, "dedupe_s", 0, dedupe_s))
        return detail::invalid(QStringLiteral("bad dedupe_s"));
    if (!detail::read_window(o, "ttl_s", 0, ttl_s))
        return detail::invalid(QStringLiteral("bad ttl_s"));

    ParseResult r;
    r.id = id;
    r.status = (ttl_s > 0 && now > ts.addSecs(ttl_s)) ? ParseStatus::Expired : ParseStatus::Ok;

    // A bad action never rejects the message: drop the action, keep the alert.
    QString screen;
    const QJsonValue action_v = o.value(QLatin1String("action"));
    if (!action_v.isUndefined() && !action_v.isNull()) {
        const QJsonObject a = action_v.toObject();
        const QString candidate = a.value(QLatin1String("screen")).toString();
        if (!action_v.isObject() || a.value(QLatin1String("type")).toString() != QLatin1String("open_screen"))
            r.reason = QStringLiteral("action dropped: unsupported type");
        else if (!valid_screen_id(candidate))
            r.reason = QStringLiteral("action dropped: bad screen id");
        else if (!known_screens.isEmpty() && !known_screens.contains(candidate))
            r.reason = QStringLiteral("action dropped: unknown screen '%1'").arg(candidate);
        else
            screen = candidate;
    }

    NotificationRequest& req = r.request;
    req.title = title;
    req.message = message;
    req.level = level;
    req.trigger = NotifTrigger::External;
    req.timestamp = ts;
    req.source = QStringLiteral("external:") + source;
    req.dedupe_key = key;
    req.dedupe_s = static_cast<int>(dedupe_s);
    req.local_only = true;
    req.action_screen = screen;
    return r;
}

} // namespace fincept::notifications::inbox
