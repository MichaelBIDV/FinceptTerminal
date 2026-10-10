// WdcCache.cpp: disk cache of chart images (DESIGN §16 C18), gói UI (đợt 3). Render threads only.
#include "screens/widata/WdcCache.h"

#include "screens/widata/WdcData.h"

#include <QBuffer>
#include <QCoreApplication>
#include <QCryptographicHash>
#include <QDataStream>
#include <QDateTime>
#include <QDir>
#include <QFileInfo>
#include <QStandardPaths>

#include <algorithm>

namespace fincept::screens::wdc {

namespace {

constexpr quint32 kWdcCacheMagic = 0x57444331;   // "WDC1"

} // namespace

QString renderCacheDir() {
    static const QString dir = [] {
        const QByteArray env = qgetenv("WDC_RENDER_CACHE");
        if (env == "off") return QString();
        if (!env.isEmpty()) return QString::fromLocal8Bit(env);
        const QString base = QStandardPaths::writableLocation(QStandardPaths::CacheLocation);
        return base.isEmpty() ? QString() : base + QStringLiteral("/widata_render");
    }();
    return dir;
}

QByteArray engineStamp() {
    static const QByteArray stamp = [] {
        const QFileInfo fi(QCoreApplication::applicationFilePath());
        return (fi.absoluteFilePath() + QLatin1Char('|') + QString::number(fi.size()) + QLatin1Char('|') +
                QString::number(fi.lastModified().toMSecsSinceEpoch()))
            .toUtf8();
    }();
    return stamp;
}

QByteArray diskRenderKey(const QByteArray& tag, const QByteArray& key) {
    QCryptographicHash h(QCryptographicHash::Sha1);
    h.addData(tag);
    h.addData("\n");
    h.addData(engineStamp());
    h.addData("\n");
    h.addData(key);
    return h.result().toHex();
}

bool loadDiskRender(const QByteArray& diskKey, int panes, DiskRender* out) {
    const QString dir = renderCacheDir();
    if (dir.isEmpty() || diskKey.isEmpty()) return false;
    const QString path = dir + QLatin1Char('/') + QString::fromLatin1(diskKey) + QStringLiteral(".wdc");
    if (!fileExistsCounted(path)) return false;
    const QByteArray bytes = readFileCounted(path, nullptr);
    if (bytes.isEmpty()) return false;
    QDataStream in(bytes);
    in.setVersion(QDataStream::Qt_6_5);
    quint32 magic = 0;
    qint32 n = 0;
    double paintMs = 0;
    in >> magic >> n >> paintMs;
    if (magic != kWdcCacheMagic || n != panes) return false;
    DiskRender r;
    r.paintMs = paintMs;
    for (int k = 0; k < n; ++k) {
        QByteArray png;
        double dpr = 1;
        in >> dpr >> png;
        QImage img;
        if (!png.isEmpty() && !img.loadFromData(png, "PNG")) return false;
        if (!img.isNull()) {
            img = img.convertToFormat(QImage::Format_ARGB32_Premultiplied);
            img.setDevicePixelRatio(dpr);
        }
        r.images.push_back(std::move(img));
    }
    if (in.status() != QDataStream::Ok) return false;
    *out = std::move(r);
    return true;
}

bool storeDiskRender(const QByteArray& diskKey, const DiskRender& r) {
    const QString dir = renderCacheDir();
    if (dir.isEmpty() || diskKey.isEmpty()) return false;
    QByteArray bytes;
    {
        QDataStream o(&bytes, QIODevice::WriteOnly);
        o.setVersion(QDataStream::Qt_6_5);
        o << kWdcCacheMagic << qint32(r.images.size()) << r.paintMs;
        for (const QImage& img : r.images) {
            QByteArray png;
            if (!img.isNull()) {
                QBuffer buf(&png);
                buf.open(QIODevice::WriteOnly);
                img.save(&buf, "PNG", 80);   // light deflate (quality 80): these files are only a cache
            }
            o << double(img.isNull() ? 1.0 : img.devicePixelRatio()) << png;
        }
    }
    QDir().mkpath(dir);
    return writeFileCounted(dir + QLatin1Char('/') + QString::fromLatin1(diskKey) + QStringLiteral(".wdc"), bytes, nullptr);
}

void trimDiskCache(qint64 maxBytes) {
    const QString dir = renderCacheDir();
    if (dir.isEmpty()) return;
    QFileInfoList files = QDir(dir).entryInfoList({QStringLiteral("*.wdc")}, QDir::Files, QDir::Time | QDir::Reversed);
    qint64 total = 0;
    for (const QFileInfo& fi : files) total += fi.size();
    for (const QFileInfo& fi : files) {   // oldest first
        if (total <= maxBytes) break;
        total -= fi.size();
        QFile::remove(fi.absoluteFilePath());
    }
}

} // namespace fincept::screens::wdc
