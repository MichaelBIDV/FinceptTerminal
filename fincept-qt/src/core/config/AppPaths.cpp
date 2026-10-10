#include "core/config/AppPaths.h"

#include "core/config/ProfileManager.h"

#include <QDir>
#include <QFile>
#include <QFileInfo>
#include <QStandardPaths>

#include <cstdio>

namespace fincept {

QString AppPaths::root() {
#ifdef _WIN32
    // Use GenericDataLocation which returns %LOCALAPPDATA% directly on Windows,
    // avoiding the fragile double-cdUp() from AppLocalDataLocation.
    // GenericDataLocation = %LOCALAPPDATA% on Windows (Qt docs: QStandardPaths).
    const QString local_app_data = QStandardPaths::writableLocation(QStandardPaths::GenericDataLocation);
    return local_app_data + "/com.fincept.terminal";
#elif defined(__APPLE__)
    return QDir::homePath() + "/Library/Application Support/com.fincept.terminal";
#else
    return QDir::homePath() + "/.local/share/com.fincept.terminal";
#endif
}

QString AppPaths::data() {
    return ProfileManager::instance().profile_root() + "/data";
}

QString AppPaths::logs() {
    return ProfileManager::instance().profile_root() + "/logs";
}

QString AppPaths::files() {
    return ProfileManager::instance().profile_root() + "/files";
}

QString AppPaths::cache() {
    return ProfileManager::instance().profile_root() + "/cache";
}

QString AppPaths::models() {
    return root() + "/models";
}

QString AppPaths::runtime() {
    return root() + "/runtime";
}

QString AppPaths::workspaces() {
    return ProfileManager::instance().profile_root() + "/workspaces";
}

QString AppPaths::crashdumps() {
    return ProfileManager::instance().profile_root() + "/crashdumps";
}

QString AppPaths::inbox() {
    return ProfileManager::instance().profile_root() + "/inbox";
}

void AppPaths::ensure_all() {
    // Use fprintf to stderr (not qWarning) — main.cpp installs a Qt message
    // handler that routes qWarning into Logger, but Logger's file isn't open
    // yet when ensure_all() runs during startup. Raw stderr is the safe channel.
    const auto try_mkpath = [](const QString& p) {
        if (p.isEmpty()) {
            fprintf(stderr, "[AppPaths] empty path — skipping mkpath\n");
            return;
        }
        if (QDir().mkpath(p))
            return;
        const QFileInfo info(p);
        fprintf(stderr, "[AppPaths] mkpath failed: %s exists=%d isDir=%d writable=%d\n", qUtf8Printable(p),
                info.exists(), info.isDir(), info.isWritable());
    };
    try_mkpath(root());
    try_mkpath(data());
    try_mkpath(logs());
    try_mkpath(files());
    try_mkpath(cache());
    try_mkpath(models());
    try_mkpath(runtime());
    try_mkpath(workspaces());
    try_mkpath(crashdumps());

    // Inbox: any process running as this user may drop files here, so keep it
    // owner-only (the data/ tree is 0755). Re-applied on every start in case the
    // directory was created by the helper with a looser umask.
    const QFileDevice::Permissions owner_only = QFileDevice::ReadOwner | QFileDevice::WriteOwner |
                                                QFileDevice::ExeOwner | QFileDevice::ReadUser |
                                                QFileDevice::WriteUser | QFileDevice::ExeUser;
    const QString inbox_root = inbox();
    for (const char* sub : {"", "/tmp", "/new", "/cur", "/done", "/bad"}) {
        const QString p = inbox_root + QLatin1String(sub);
        try_mkpath(p);
        if (!QFile::setPermissions(p, owner_only))
            fprintf(stderr, "[AppPaths] chmod 0700 failed: %s\n", qUtf8Printable(p));
    }
}

} // namespace fincept
