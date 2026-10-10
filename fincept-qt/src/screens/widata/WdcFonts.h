#pragma once
// WdcFonts.h: Inter for the WiData clone (tab VĨ MÔ). Package E. DESIGN §6, §16 C6; UI §5.2.
//
// Search order (first directory that holds *.ttf wins):
//   $WDC_FONT_DIR, <app>/../Resources/fonts/widata (APP/Contents/Resources/fonts/widata),
//   <app>/resources/fonts/widata, the first resources/fonts/widata found walking up from the binary,
//   ~/Documents/GitHub/FinceptTerminal/fincept-qt/resources/fonts/widata (repo).
// Files expected (harness/widata_clone/fonts, package P0): InterVariable.ttf and the static instances
// Inter-{400,500,600}-opsz{14,16}.ttf (families "Inter Static opsz14" / "Inter Static opsz16"). theme::font() takes
// opsz 16 only for weight 600 at 16 px: 400 and 500 keep the opsz 14 outlines at every size, 16 px included, like the
// Google Fonts static subsets WiData serves (F2 FACT 04/10: chart-page h6 16/500 is 230.41 px wide with opsz 14).
//
// ensureFonts() reads files from disk: call it from a worker thread (WdcView does it inside its first
// QtConcurrent task). QFontDatabase is documented thread-safe. Choosing the face for a size and weight
// (static instance, else variable font with wght/opsz) is theme::font() of WdcTheme_p.h (package D).
#include <QString>
#include <QStringList>

namespace fincept::screens::wdc {

struct FontStatus {
    QString dir;            // directory the fonts came from, empty if none found
    QStringList families;   // families registered
    QStringList failed;     // files that QFontDatabase refused
    bool variable = false;  // "Inter Variable" registered
    bool statics = false;   // "Inter Static opsz14" registered
};

QStringList fontDirs();
const FontStatus& ensureFonts();   // idempotent, thread-safe, does disk I/O
bool fontsLoaded();                // ensureFonts() has completed (no I/O)

} // namespace fincept::screens::wdc
