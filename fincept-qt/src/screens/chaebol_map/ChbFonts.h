#pragma once
// ChbFonts.h — font loading and CSS font matching for the chaebol_map engine (DESIGN.md §0.2, integration §6.4).
//
// Loads the page's four OFL families from resources/fonts/chaebol_map (env CHB_FONT_DIR first), then maps a
// CSS font-family list + weight + style onto Qt the way Chrome 147/macOS does for the reference page:
//  * generics: serif → Times (New Roman), sans-serif → Helvetica, monospace → Menlo (Chrome once its preferences
//    are synced — the state every ref/oracle screenshot shows; a fresh headless renderer briefly uses Courier);
//    system-ui/-apple-system are skipped (headless Chrome did not map them, see ref/README §4); the standard font
//    (Times) is appended.
//  * the four web families only cover the Google Fonts subset unicode-ranges (latin/latin-ext/vietnamese/…),
//    so e.g. ≤ in 'IBM Plex Mono', monospace falls to Menlo like in Chrome (web_family_covers()); what no CSS
//    family covers follows Chrome's measured system fallback (chrome_fallback_family(), ChbText hint loop).
//  * weights: variable faces get an explicit `wght` axis (Qt would otherwise pick the nearest named instance,
//    e.g. JetBrains 600 → Medium); the @font-face weight ranges of the oracle are honoured.
//  * Source Serif 4 gets opsz = 14 (Google serves an instance pinned at opsz 14 — measured against Chrome:
//    best fit 13.5–14.5 for 10–13 px text). Env CHB_SERIF_OPSZ=auto → opsz = px (DESIGN §0.2 literal).
//  * synthetic styles: italic without an italic face → fakeItalic (skew −0.25, drawn by ChbText); requested
//    weight ≥ 600 on a face < 600 (Cormorant italic) → fakeBold (outline stroke like Skia).
// Sizes: CSS px. make_qfont() converts to points with the screen DPI so the result is exact at any DPI.
#include <QFont>
#include <QString>
#include <QStringList>

namespace fincept::screens::chb {

struct FontStatus {
    QString dir;          ///< directory the fonts were loaded from ("" = none found)
    QStringList families; ///< families registered
    QStringList failed;   ///< files that failed to load
};
/// Load every .ttf/.otf of the first font directory found (once; thread-unsafe, call from the GUI thread).
const FontStatus& ensure_fonts();

/// Result of CSS font matching for one (family list, weight, style).
struct FontSpec {
    QStringList families;    ///< Qt family names in CSS order, available ones only, standard font appended
    QString primary;         ///< first available family
    int cssWeight = 400;
    int faceWeight = 400;    ///< weight Qt is asked for (static faces: nearest per CSS matching)
    bool italicFace = false; ///< ask Qt for a real italic face
    bool fakeItalic = false; ///< synthesize oblique (skew) when drawing
    bool fakeBold = false;   ///< synthesize bold (outline stroke) when drawing
    float wght = -1;         ///< variable `wght` axis value (<0: none)
    float opsz = -1;         ///< variable `opsz` axis value (<0: none; Source Serif 4 only)
    QString key() const;     ///< cache key
};

FontSpec resolve_font(const QStringList& cssFamilies, int weight, bool italic, float px);
/// QFont for `spec` at `px` CSS pixels × `scale` (scale > 1 = high-precision measuring font).
/// `families` overrides spec.families (fallback runs), empty = spec.families.
QFont make_qfont(const FontSpec& spec, float px, float scale = 1.0f, const QStringList& families = {});
/// True when `family` is one of the page's web fonts and `cp` lies inside its Google subset ranges
/// (always true for non-web families).
bool web_family_covers(const QString& family, bool italic, char32_t cp);
bool is_web_family(const QString& family);
/// Unicode Emoji_Presentation=Yes (Chrome's segmenter sends these to the emoji font first).
bool is_emoji_presentation(char32_t cp);
/// Family used for emoji runs (CoreText "AppleColorEmoji", not the ".AppleColorEmojiUI" Qt falls back to).
QString emoji_family();
/// Font Chrome really uses for a lone code point its CSS list does not cover, measured per primary family
/// (first family of the list) and weight class (ChbFontsChrome_p.h, tools/chrome_fallback_probe.py). "" = no data
/// (unknown primary → the Times table; code point outside the measured blocks).
QString chrome_fallback_family(const QString& primary, bool bold, char32_t cp);
/// Last-resort system fallback family for a code point ("" = let Qt decide).
/// Data from CoreText (CTFontCreateForString / default cascade of a web font), embedded — no runtime CoreText.
QString system_fallback_family(char32_t cp);
/// Glyph coverage of an installed/app family (web families also honour the Google subset ranges).
bool family_covers(const QString& family, char32_t cp);
/// Glyph coverage of the whole font file of `family` (Google subset ranges ignored).
bool face_covers(const QString& family, char32_t cp);
/// True (default) = Chrome with the page's fonts as local TTF files (oracle `fonts=local`): a character no CSS
/// family covers is looked up first in the primary font's own file (CoreText cascade returns the file itself,
/// e.g. `→` in Source Serif 4). Env CHB_FONT_MODE=google = Chrome with Google's woff2 subsets: the subset has no
/// such glyph, so it goes straight to the system cascade (Lucida Grande for `→`).
bool primary_face_fallback();

} // namespace fincept::screens::chb
