// WdcFonts.cpp: discovery and registration of the Inter files for the WiData clone. Package E (DESIGN §6, §16 C6).
// Loading precedent: src/screens/chaebol_map/ChbFonts.cpp:172-200 (no cross-module call).
#include "WdcFonts.h"

#include "WdcData.h"

#include <QCoreApplication>
#include <QDir>
#include <QFileInfo>
#include <QFontDatabase>

#include <atomic>

namespace fincept::screens::wdc {
namespace {

std::atomic<bool> wdcfonts_done{false};

} // namespace

QStringList fontDirs() {
    QStringList dirs;
    const QByteArray env = qgetenv("WDC_FONT_DIR");
    if (!env.isEmpty()) dirs << QString::fromLocal8Bit(env);
    if (QCoreApplication::instance()) {
        const QString exe = QCoreApplication::applicationDirPath();
        dirs << QDir::cleanPath(exe + QStringLiteral("/../Resources/fonts/widata"))
             << exe + QStringLiteral("/resources/fonts/widata");
        QDir d(exe);
        for (int i = 0; i < 8 && d.cdUp(); ++i) dirs << d.filePath(QStringLiteral("resources/fonts/widata"));
    }
    dirs << QDir::homePath() + QStringLiteral("/Documents/GitHub/FinceptTerminal/fincept-qt/resources/fonts/widata");
    dirs.removeDuplicates();
    return dirs;
}

const FontStatus& ensureFonts() {
    static const FontStatus st = [] {
        FontStatus s;
        for (const QString& dir : fontDirs()) {
            const QDir d(dir);
            const auto files = d.entryInfoList({QStringLiteral("*.ttf"), QStringLiteral("*.otf")}, QDir::Files, QDir::Name);
            if (files.isEmpty()) continue;
            for (const QFileInfo& fi : files) {
                QString err;
                const QByteArray bytes = readFileCounted(fi.absoluteFilePath(), &err);
                const int id = bytes.isEmpty() ? -1 : QFontDatabase::addApplicationFontFromData(bytes);
                if (id < 0) s.failed << fi.fileName();
                else s.families += QFontDatabase::applicationFontFamilies(id);
            }
            s.dir = d.absolutePath();
            break;
        }
        s.families.removeDuplicates();
        s.variable = s.families.contains(QStringLiteral("Inter Variable"));
        s.statics = s.families.contains(QStringLiteral("Inter Static opsz14"));
        if (s.dir.isEmpty()) qWarning("[widata] không thấy thư mục font widata, dùng font hệ thống (lệch bề rộng chữ)");
        wdcfonts_done.store(true);
        return s;
    }();
    return st;
}

bool fontsLoaded() { return wdcfonts_done.load(); }

} // namespace fincept::screens::wdc
