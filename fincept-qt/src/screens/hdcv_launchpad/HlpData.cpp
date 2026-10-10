// src/screens/hdcv_launchpad/HlpData.cpp
// DataStore — reads exactly the files the web Launchpad fetches (paths relative to the _System root,
// $HDCV_SYSTEM_DIR or ~/SECOND BRAIN-OBSIDIAN/_System), plus the newest weekly SGI issue for the SGI
// Capital panel. Read-only. Each file's mtime is remembered so the screen's 60 s poll re-parses only
// what a builder (LaunchAgent / routine) actually rewrote. A file caught half-written (the builders
// rewrite in place) fails to parse; when it was modified in the last few seconds the poll leaves it for
// the next round instead of flashing an error.
#include "screens/hdcv_launchpad/HlpData.h"

#include <QDir>
#include <QFile>
#include <QFileInfo>
#include <QJsonDocument>
#include <QJsonParseError>

namespace fincept::screens::hlp {

namespace {

/// Keys in load order (HlpData.h): D, vimo, tien, wd, alerts, sgi.
const QStringList& hlpdata_keys() {
    static const QStringList k{QStringLiteral("D"),  QStringLiteral("vimo"),   QStringLiteral("tien"),
                               QStringLiteral("wd"), QStringLiteral("alerts"), QStringLiteral("sgi"),
                               // Vietcap IQ (vietcapma / vietcaptin components)
                               QStringLiteral("vcma"), QStringLiteral("vctin")};
    return k;
}

/// A parse failure on a file modified less than this long ago is treated as "still being written".
constexpr qint64 hlpdata_kWriteGraceSec = 5;

/// Read one JSON object file. `err` explains a failure (open error / parse error / not an object).
bool hlpdata_read(const QString& path, QJsonObject& out, QString& err) {
    out = QJsonObject();
    err.clear();
    if (path.isEmpty()) {
        err = QStringLiteral("không có tệp");
        return false;
    }
    QFile f(path);
    if (!f.open(QIODevice::ReadOnly)) {
        err = f.errorString();
        return false;
    }
    QJsonParseError pe{};
    const QJsonDocument doc = QJsonDocument::fromJson(f.readAll(), &pe);
    if (pe.error != QJsonParseError::NoError) {
        err = pe.errorString();
        return false;
    }
    if (!doc.isObject()) {
        err = QStringLiteral("không phải object JSON");
        return false;
    }
    out = doc.object();
    return true;
}

/// Store one parsed file into its Data slot.
void hlpdata_assign(Data& d, const QString& key, const QString& path, const QJsonObject& obj, bool ok,
                    const QString& err) {
    if (key == QLatin1String("D")) {
        d.D = obj;
        d.dOk = ok;
        d.dErr = err;
    } else if (key == QLatin1String("vimo")) {
        d.vimo = obj;
        d.vimoOk = ok;
    } else if (key == QLatin1String("tien")) {
        d.tien = obj;
        d.tienOk = ok;
    } else if (key == QLatin1String("wd")) {
        d.wd = obj;
        d.wdOk = ok;
    } else if (key == QLatin1String("alerts")) {
        d.alerts = obj;
        d.alertsOk = ok;
    } else if (key == QLatin1String("sgi")) {
        d.sgi = obj;
        d.sgiOk = ok;
        d.sgiFile = path;
    } else if (key == QLatin1String("vcma")) {
        d.vcMa = obj;
        d.vcMaOk = ok;
    } else if (key == QLatin1String("vctin")) {
        d.vcTin = obj;
        d.vcTinOk = ok;
    }
}

QDateTime hlpdata_mtime(const QString& path) {
    const QFileInfo fi(path);
    return (!path.isEmpty() && fi.exists()) ? fi.lastModified() : QDateTime();
}

} // namespace

DataStore::DataStore(QObject* parent) : QObject(parent) {
    data_.systemDir = defaultSystemDir();
}

QString DataStore::defaultSystemDir() {
    const QString env = qEnvironmentVariable("HDCV_SYSTEM_DIR");
    if (!env.isEmpty())
        return QDir::cleanPath(env);
    return QDir::homePath() + QStringLiteral("/SECOND BRAIN-OBSIDIAN/_System");
}

QString DataStore::pathFor(const QString& key) const {
    const QString root = data_.systemDir;
    // panels.js / index.html fetch these relative to launchpad/index.html
    if (key == QLatin1String("D"))
        return root + QStringLiteral("/launchpad/data/launchpad_data.json");
    if (key == QLatin1String("vimo"))
        return root + QStringLiteral("/launchpad/data/vimo.json");
    if (key == QLatin1String("tien"))
        return root + QStringLiteral("/launchpad/data/tien.json");
    if (key == QLatin1String("wd"))
        return root + QStringLiteral("/launchpad/data/wdsignal.json");
    if (key == QLatin1String("alerts"))
        return root + QStringLiteral("/launchpad/alerts_state.json");
    if (key == QLatin1String("sgi")) {
        // Newest weekly issue = greatest file name (YYYY-MM-DD.json); "_…" files are not issues.
        const QDir dir(root + QStringLiteral("/knowledge_os/sgi_ky"));
        const QStringList names = dir.entryList({QStringLiteral("*.json")}, QDir::Files, QDir::Name);
        for (auto it = names.crbegin(); it != names.crend(); ++it)
            if (!it->startsWith(QLatin1Char('_')))
                return dir.filePath(*it);
        return {};
    }
    // panels.js vietcapma / vietcaptin fetch '../fincept_bridge/data/…' relative to launchpad/
    if (key == QLatin1String("vcma"))
        return root + QStringLiteral("/fincept_bridge/data/vietcap_ma.json");
    if (key == QLatin1String("vctin"))
        return root + QStringLiteral("/fincept_bridge/data/vietcap_tin.json");
    return {};
}

bool DataStore::loadOne(const QString& key) {
    const QString path = pathFor(key);
    QJsonObject obj;
    QString err;
    const bool ok = hlpdata_read(path, obj, err);
    mtimes_.insert(key, hlpdata_mtime(path));
    hlpdata_assign(data_, key, path, obj, ok, err);
    return ok;
}

bool DataStore::loadAll() {
    data_ = Data{};
    data_.systemDir = defaultSystemDir(); // re-read: the harness may set HDCV_SYSTEM_DIR late
    mtimes_.clear();
    for (const QString& key : hlpdata_keys())
        loadOne(key);
    emit changed(hlpdata_keys());
    return data_.dOk;
}

QStringList DataStore::reloadChanged() {
    QStringList keys;
    for (const QString& key : hlpdata_keys()) {
        const QString path = pathFor(key);
        const QDateTime m = hlpdata_mtime(path);
        const bool newIssue = key == QLatin1String("sgi") && path != data_.sgiFile;
        if (!newIssue && m == mtimes_.value(key))
            continue;
        QJsonObject obj;
        QString err;
        const bool ok = hlpdata_read(path, obj, err);
        if (!ok && m.isValid() && m.secsTo(QDateTime::currentDateTime()) < hlpdata_kWriteGraceSec)
            continue; // probably mid-write: mtime not recorded, so the next poll retries
        mtimes_.insert(key, m);
        hlpdata_assign(data_, key, path, obj, ok, err);
        keys << key;
    }
    if (!keys.isEmpty())
        emit changed(keys);
    return keys;
}

} // namespace fincept::screens::hlp
