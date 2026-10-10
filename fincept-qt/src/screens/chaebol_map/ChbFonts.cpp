// ChbFonts.cpp — font loading + CSS font matching (see ChbFonts.h).
#include "screens/chaebol_map/ChbFonts.h"
#include "screens/chaebol_map/ChbFontsChrome_p.h"
#include "screens/chaebol_map/ChbFontsFallback_p.h"

#include <QCoreApplication>
#include <QDir>
#include <QFileInfo>
#include <QFontDatabase>
#include <QGuiApplication>
#include <QHash>
#include <QRawFont>
#include <QScreen>

#include <algorithm>
#include <cmath>
#include <vector>

namespace fincept::screens::chb {

namespace {

QStringList chbf_dirs() {
    QStringList dirs;
    const QByteArray env = qgetenv("CHB_FONT_DIR");
    if (!env.isEmpty()) dirs << QString::fromLocal8Bit(env);
    const QString exe = QCoreApplication::applicationDirPath();
    dirs << exe + QStringLiteral("/../Resources/fonts/chaebol_map") << exe + QStringLiteral("/resources/fonts/chaebol_map");
    QDir d(exe);
    for (int i = 0; i < 8 && d.cdUp(); ++i) {
        const QString cand = d.filePath(QStringLiteral("resources/fonts/chaebol_map"));
        if (QFileInfo::exists(cand)) {
            dirs << cand;
            break;
        }
    }
    dirs << QDir::homePath() + QStringLiteral("/Documents/GitHub/FinceptTerminal/fincept-qt/resources/fonts/chaebol_map");
    return dirs;
}

// Google Fonts subset unicode-ranges (union of the page's subsets, Chrome 147, oracle/google_unicode_ranges.json).
struct ChbfRange { char32_t a, b; };
const std::vector<ChbfRange>& chbf_ranges_base() { // Cormorant Garamond (roman+italic), IBM Plex Mono
    static const std::vector<ChbfRange> r = {
        {0, 716}, {718, 727}, {730, 730}, {732, 769}, {771, 772}, {776, 777}, {803, 803}, {809, 809},
        {1024, 1327}, {7296, 7306}, {7424, 7615}, {7680, 7935}, {8192, 8303}, {8352, 8384}, {8467, 8467},
        {8470, 8470}, {8482, 8482}, {8593, 8593}, {8595, 8595}, {8722, 8722}, {8725, 8725}, {11360, 11391},
        {11744, 11775}, {42560, 42655}, {42784, 43007}, {65070, 65071}, {65279, 65279}, {65533, 65533}};
    return r;
}
const std::vector<ChbfRange>& chbf_ranges_greek() { // JetBrains Mono, Source Serif 4 (+ greek)
    static const std::vector<ChbfRange> r = {
        {0, 716}, {718, 727}, {730, 730}, {732, 769}, {771, 772}, {776, 777}, {803, 803}, {809, 809},
        {880, 887}, {890, 895}, {900, 906}, {908, 908}, {910, 929}, {931, 1327}, {7296, 7306}, {7424, 7615},
        {7680, 7935}, {8192, 8303}, {8352, 8384}, {8467, 8467}, {8470, 8470}, {8482, 8482}, {8593, 8593},
        {8595, 8595}, {8722, 8722}, {8725, 8725}, {11360, 11391}, {11744, 11775}, {42560, 42655},
        {42784, 43007}, {65070, 65071}, {65279, 65279}, {65533, 65533}};
    return r;
}

struct ChbfFaces {
    bool variable = false;
    int lo = 400, hi = 400;     ///< variable weight range (as declared by @font-face)
    int fileMax = 1000;         ///< variable axis max in the file
    std::vector<int> weights;   ///< static roman weights
    std::vector<int> italicWeights;
    bool hasItalic = false;
};

/// CSS Fonts 4 §5.2 weight matching over a discrete set.
int chbf_match_weight(int desired, std::vector<int> avail) {
    if (avail.empty()) return desired;
    std::sort(avail.begin(), avail.end());
    if (std::find(avail.begin(), avail.end(), desired) != avail.end()) return desired;
    auto firstAbove = [&](int from, int to) { // ascending in (from, to]
        for (int w : avail)
            if (w > from && w <= to) return w;
        return -1;
    };
    auto firstBelow = [&](int from) { // descending < from
        for (auto it = avail.rbegin(); it != avail.rend(); ++it)
            if (*it < from) return *it;
        return -1;
    };
    int w = -1;
    if (desired >= 400 && desired <= 500) {
        w = firstAbove(desired, 500);
        if (w < 0) w = firstBelow(desired);
        if (w < 0) w = firstAbove(500, 10000);
    } else if (desired < 400) {
        w = firstBelow(desired + 1);
        if (w < 0) w = firstAbove(desired, 10000);
    } else {
        w = firstAbove(desired - 1, 10000);
        if (w < 0) w = firstBelow(desired);
    }
    return w < 0 ? avail.front() : w;
}

const ChbfFaces& chbf_faces(const QString& family) {
    static QHash<QString, ChbfFaces> cache;
    auto it = cache.find(family);
    if (it != cache.end()) return it.value();
    ChbfFaces f;
    if (family == QLatin1String("Source Serif 4")) {
        f.variable = true; f.lo = 400; f.hi = 700; f.fileMax = 900;
    } else if (family == QLatin1String("Cormorant Garamond")) {
        f.variable = true; f.lo = 400; f.hi = 800; f.fileMax = 700;
        f.hasItalic = true;
        f.italicWeights = {400};
    } else if (family == QLatin1String("JetBrains Mono")) {
        f.variable = true; f.lo = 300; f.hi = 800; f.fileMax = 800;
    } else if (family == QLatin1String("IBM Plex Mono")) {
        f.weights = {300, 400, 500, 600, 700};
    } else {
        for (const QString& st : QFontDatabase::styles(family)) {
            const int w = QFontDatabase::weight(family, st);
            const bool it2 = QFontDatabase::italic(family, st) || st.contains(QLatin1String("Italic"), Qt::CaseInsensitive) ||
                             st.contains(QLatin1String("Oblique"), Qt::CaseInsensitive);
            if (w < 0) continue;
            (it2 ? f.italicWeights : f.weights).push_back(w);
            if (it2) f.hasItalic = true;
        }
        if (f.weights.empty()) f.weights = {400};
    }
    return cache.insert(family, f).value();
}

/// Lower-case CSS name → Qt family (after fonts are loaded).
QString chbf_lookup_family(const QString& css) {
    static QHash<QString, QString> idx;
    static bool built = false;
    if (!built) {
        for (const QString& fam : QFontDatabase::families()) idx.insert(fam.toLower(), fam);
        built = true;
    }
    return idx.value(css.toLower());
}

QString chbf_standard_family() {
    static const QString f = QFontDatabase::hasFamily(QStringLiteral("Times")) ? QStringLiteral("Times") : QStringLiteral("Times New Roman");
    return f;
}

/// Explicit CSS 'Courier' → the real "Courier" (Courier.ttc, registered by ensure_fonts()).
QString chbf_courier_family() {
    static const QString f = QFontDatabase::hasFamily(QStringLiteral("Courier")) ? QStringLiteral("Courier") : QStringLiteral("Courier New");
    return f;
}

/// Chrome's generic `monospace` on macOS once its WebPreferences are in effect = Menlo (metrics, coverage and
/// outlines). Measured 27/09 on Chromium 147: a fresh headless renderer starts with Courier until the first
/// captureBeyondViewport screenshot re-syncs the preferences; every ref/oracle PNG shows the Menlo state.
QString chbf_mono_family() {
    static const QString f = QFontDatabase::hasFamily(QStringLiteral("Menlo")) ? QStringLiteral("Menlo") : chbf_courier_family();
    return f;
}

float chbf_serif_opsz(float px) {
    static const QByteArray env = qgetenv("CHB_SERIF_OPSZ");
    if (env == "auto") return std::clamp(px, 8.0f, 60.0f);
    if (!env.isEmpty()) {
        bool ok = false;
        const float v = QString::fromLatin1(env).toFloat(&ok);
        if (ok) return v;
    }
    return 14.0f;
}

} // namespace

const FontStatus& ensure_fonts() {
    static const FontStatus st = [] {
        FontStatus s;
        for (const QString& dir : chbf_dirs()) {
            const QDir d(dir);
            if (!d.exists()) continue;
            const auto files = d.entryInfoList({QStringLiteral("*.ttf"), QStringLiteral("*.otf")}, QDir::Files, QDir::Name);
            if (files.isEmpty()) continue;
            for (const QFileInfo& fi : files) {
                const int id = QFontDatabase::addApplicationFont(fi.absoluteFilePath());
                if (id < 0) s.failed << fi.fileName();
                else s.families += QFontDatabase::applicationFontFamilies(id);
            }
            s.dir = d.absolutePath();
            break;
        }
        s.families.removeDuplicates();
        if (s.dir.isEmpty()) qWarning("[chaebol_map] không thấy thư mục font chaebol_map — dùng font dự phòng");
        // Chrome's standard (serif) font on macOS is the real "Times" (Times.ttc); Qt does not list it and would
        // substitute ".Times Fallback", whose extra glyphs (→ …) change fallback. Register the system file.
        // Same for Chrome's `monospace` = "Courier" (Courier.ttc).
        for (const auto& [fam, file] : {std::pair{QStringLiteral("Times"), QStringLiteral("/System/Library/Fonts/Times.ttc")},
                                        std::pair{QStringLiteral("Courier"), QStringLiteral("/System/Library/Fonts/Courier.ttc")}})
            if (!QFontDatabase::hasFamily(fam) && QFileInfo::exists(file)) QFontDatabase::addApplicationFont(file);
        return s;
    }();
    return st;
}

bool is_web_family(const QString& family) {
    return family == QLatin1String("Source Serif 4") || family == QLatin1String("Cormorant Garamond") ||
           family == QLatin1String("IBM Plex Mono") || family == QLatin1String("JetBrains Mono");
}

bool web_family_covers(const QString& family, bool italic, char32_t cp) {
    Q_UNUSED(italic);
    if (!is_web_family(family)) return true;
    const auto& r = (family == QLatin1String("Source Serif 4") || family == QLatin1String("JetBrains Mono"))
                        ? chbf_ranges_greek()
                        : chbf_ranges_base();
    for (const ChbfRange& x : r) {
        if (cp < x.a) return false;
        if (cp <= x.b) return true;
    }
    return false;
}

bool is_emoji_presentation(char32_t cp) {
    // Unicode 15.1 emoji-data.txt, Emoji_Presentation=Yes
    static const ChbfRange r[] = {
        {0x231A, 0x231B}, {0x23E9, 0x23EC}, {0x23F0, 0x23F0}, {0x23F3, 0x23F3}, {0x25FD, 0x25FE}, {0x2614, 0x2615},
        {0x2648, 0x2653}, {0x267F, 0x267F}, {0x2693, 0x2693}, {0x26A1, 0x26A1}, {0x26AA, 0x26AB}, {0x26BD, 0x26BE},
        {0x26C4, 0x26C5}, {0x26CE, 0x26CE}, {0x26D4, 0x26D4}, {0x26EA, 0x26EA}, {0x26F2, 0x26F3}, {0x26F5, 0x26F5},
        {0x26FA, 0x26FA}, {0x26FD, 0x26FD}, {0x2705, 0x2705}, {0x270A, 0x270B}, {0x2728, 0x2728}, {0x274C, 0x274C},
        {0x274E, 0x274E}, {0x2753, 0x2755}, {0x2757, 0x2757}, {0x2795, 0x2797}, {0x27B0, 0x27B0}, {0x27BF, 0x27BF},
        {0x2B1B, 0x2B1C}, {0x2B50, 0x2B50}, {0x2B55, 0x2B55}, {0x1F004, 0x1F004}, {0x1F0CF, 0x1F0CF},
        {0x1F18E, 0x1F18E}, {0x1F191, 0x1F19A}, {0x1F1E6, 0x1F1FF}, {0x1F201, 0x1F201}, {0x1F21A, 0x1F21A},
        {0x1F22F, 0x1F22F}, {0x1F232, 0x1F236}, {0x1F238, 0x1F23A}, {0x1F250, 0x1F251}, {0x1F300, 0x1F320},
        {0x1F32D, 0x1F335}, {0x1F337, 0x1F37C}, {0x1F37E, 0x1F393}, {0x1F3A0, 0x1F3CA}, {0x1F3CF, 0x1F3D3},
        {0x1F3E0, 0x1F3F0}, {0x1F3F4, 0x1F3F4}, {0x1F3F8, 0x1F43E}, {0x1F440, 0x1F440}, {0x1F442, 0x1F4FC},
        {0x1F4FF, 0x1F53D}, {0x1F54B, 0x1F54E}, {0x1F550, 0x1F567}, {0x1F57A, 0x1F57A}, {0x1F595, 0x1F596},
        {0x1F5A4, 0x1F5A4}, {0x1F5FB, 0x1F64F}, {0x1F680, 0x1F6C5}, {0x1F6CC, 0x1F6CC}, {0x1F6D0, 0x1F6D2},
        {0x1F6D5, 0x1F6D7}, {0x1F6DC, 0x1F6DF}, {0x1F6EB, 0x1F6EC}, {0x1F6F4, 0x1F6FC}, {0x1F7E0, 0x1F7EB},
        {0x1F7F0, 0x1F7F0}, {0x1F90C, 0x1F93A}, {0x1F93C, 0x1F945}, {0x1F947, 0x1F9FF}, {0x1FA70, 0x1FA7C},
        {0x1FA80, 0x1FA89}, {0x1FA8F, 0x1FAC6}, {0x1FACE, 0x1FADC}, {0x1FADF, 0x1FAE9}, {0x1FAF0, 0x1FAF8}};
    if (cp < 0x231A) return false;
    for (const ChbfRange& x : r) {
        if (cp < x.a) return false;
        if (cp <= x.b) return true;
    }
    return false;
}

QString emoji_family() { return QStringLiteral("Apple Color Emoji"); }

QString system_fallback_family(char32_t cp) {
    const auto* b = std::begin(kChbfSysFallback);
    const auto* e = std::end(kChbfSysFallback);
    const auto* it = std::upper_bound(b, e, cp, [](char32_t v, const auto& r) { return v < r.a; });
    if (it == b) return QString();
    --it;
    if (cp > it->b) return QString();
    return QString::fromLatin1(kChbfSysFamilies[it->f]);
}

QString chrome_fallback_family(const QString& primary, bool bold, char32_t cp) {
    const ChbcTable* t = nullptr;
    for (int pass = 0; pass < 3 && !t; ++pass)
        for (const ChbcTable& e : kChbcTables) {
            const bool nameOk = pass < 2 ? primary == QLatin1String(e.primary) : qstrcmp(e.primary, "Times") == 0;
            if (nameOk && (pass == 1 || e.bold == bold)) { t = &e; break; }
        }
    if (!t) return QString();
    const ChbcRange* b = t->r;
    const ChbcRange* e = t->r + t->n;
    const ChbcRange* it = std::upper_bound(b, e, cp, [](char32_t v, const ChbcRange& r) { return v < r.a; });
    if (it == b) return QString();
    --it;
    if (cp > it->b) return QString();
    return QString::fromUtf8(kChbcFamilies[it->f]);
}

bool family_covers(const QString& family, char32_t cp) {
    return web_family_covers(family, false, cp) && face_covers(family, cp);
}

bool primary_face_fallback() {
    static const bool local = qgetenv("CHB_FONT_MODE").trimmed().toLower() != "google";
    return local;
}

bool face_covers(const QString& family, char32_t cp) {
    static QHash<QString, QRawFont> faces;
    auto it = faces.find(family);
    if (it == faces.end()) {
        QFont f;
        f.setFamilies({family});
        f.setPixelSize(12);
        it = faces.insert(family, QRawFont::fromFont(f));
    }
    return it.value().isValid() && it.value().familyName().compare(family, Qt::CaseInsensitive) == 0 &&
           it.value().supportsCharacter(uint(cp));
}

QString FontSpec::key() const {
    return families.join(QLatin1Char(',')) + QLatin1Char('|') + QString::number(faceWeight) + QLatin1Char('|') +
           QString::number(int(italicFace)) + QString::number(int(fakeItalic)) + QString::number(int(fakeBold)) +
           QLatin1Char('|') + QString::number(double(wght)) + QLatin1Char('|') + QString::number(double(opsz));
}

FontSpec resolve_font(const QStringList& cssFamilies, int weight, bool italic, float px) {
    ensure_fonts();
    FontSpec s;
    s.cssWeight = weight;
    for (const QString& raw : cssFamilies) {
        const QString low = raw.toLower();
        QStringList mapped;
        if (low == QLatin1String("serif")) mapped << chbf_standard_family();
        else if (low == QLatin1String("sans-serif")) mapped << QStringLiteral("Helvetica");
        else if (low == QLatin1String("monospace") || low == QLatin1String("ui-monospace")) mapped << chbf_mono_family();
        else if (low == QLatin1String("system-ui") || low == QLatin1String("-apple-system") ||
                 low == QLatin1String("blinkmacsystemfont") || low == QLatin1String("cursive") ||
                 low == QLatin1String("fantasy") || low == QLatin1String("math") || low == QLatin1String("emoji"))
            continue;
        else if (low == QLatin1String("times")) mapped << chbf_standard_family();
        else if (low == QLatin1String("courier")) mapped << chbf_courier_family();
        else {
            const QString q = chbf_lookup_family(raw);
            if (!q.isEmpty()) mapped << q;
        }
        for (const QString& m : mapped)
            if (!s.families.contains(m)) s.families << m;
    }
    // Blink tries the standard font (Times) after the CSS list, before the system fallback
    if (!s.families.contains(chbf_standard_family())) s.families << chbf_standard_family();
    s.primary = s.families.first();

    const ChbfFaces& f = chbf_faces(s.primary);
    const bool wantItalic = italic;
    s.italicFace = wantItalic && f.hasItalic;
    s.fakeItalic = wantItalic && !f.hasItalic;
    if (s.italicFace) {
        s.faceWeight = chbf_match_weight(weight, f.italicWeights);
    } else if (f.variable) {
        s.faceWeight = std::clamp(weight, f.lo, f.hi);
        s.wght = float(std::min(s.faceWeight, f.fileMax));
    } else {
        s.faceWeight = chbf_match_weight(weight, f.weights);
    }
    s.fakeBold = weight >= 600 && s.faceWeight < 600;
    if (s.primary == QLatin1String("Source Serif 4")) s.opsz = chbf_serif_opsz(px);
    return s;
}

QFont make_qfont(const FontSpec& spec, float px, float scale, const QStringList& families) {
    QFont f;
    f.setFamilies(families.isEmpty() ? spec.families : families);
    // CSS px → points at the screen's logical DPI (72 in the app and the harness: 1 pt = 1 px).
    static const qreal dpi = [] {
        const QScreen* s = QGuiApplication::primaryScreen();
        const qreal d = s ? s->logicalDotsPerInchY() : 72.0;
        return d > 0 ? d : 72.0;
    }();
    f.setPointSizeF(qreal(px) * qreal(scale) * 72.0 / dpi);
    f.setWeight(QFont::Weight(std::clamp(spec.faceWeight, 1, 1000)));
    f.setItalic(spec.italicFace);
    f.setKerning(true);
    f.setHintingPreference(QFont::PreferNoHinting);
    if (spec.wght > 0) f.setVariableAxis(QFont::Tag("wght"), spec.wght);
    if (spec.opsz > 0) {
        // CoreText treats a value equal to the axis default as "unset" and then applies automatic optical
        // sizing from the point size (wrong for the scaled measuring font) → nudge off the default.
        float o = spec.opsz;
        if (std::fabs(o - 20.0f) < 1e-3f) o = 20.001f;
        f.setVariableAxis(QFont::Tag("opsz"), o);
    }
    return f;
}

} // namespace fincept::screens::chb
