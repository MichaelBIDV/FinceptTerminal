// ChbText.cpp — precision shaping, Chrome metrics, glyph painting (see ChbText.h).
#include "screens/chaebol_map/ChbText.h"

#include "screens/chaebol_map/ChbKernVar_p.h"

#include <QDebug>
#include <QGlyphRun>
#include <QHash>
#include <QPainterPath>
#include <QTextBoundaryFinder>
#include <QTextLayout>
#include <QTextOption>

#include <algorithm>
#include <cmath>
#include <unordered_map>

namespace fincept::screens::chb {

namespace {

float chbt_round(float v) { return std::floor(v + 0.5f); } // SkScalarRoundToScalar

struct ChbtEntryCache {
    QHash<QString, std::shared_ptr<FontEntry>> entries;
};
ChbtEntryCache& chbt_entries() {
    static ChbtEntryCache c;
    return c;
}

struct ChbtKey {
    const FontEntry* fe;
    float ls;
    QString text;
    bool operator==(const ChbtKey& o) const { return fe == o.fe && ls == o.ls && text == o.text; }
};
struct ChbtKeyHash {
    size_t operator()(const ChbtKey& k) const {
        return qHash(k.text) ^ (std::hash<const void*>()(k.fe) * 31) ^ std::hash<float>()(k.ls);
    }
};
std::unordered_map<ChbtKey, std::unique_ptr<ShapedText>, ChbtKeyHash>& chbt_shapes() {
    static std::unordered_map<ChbtKey, std::unique_ptr<ShapedText>, ChbtKeyHash> m;
    return m;
}

/// scaled raw font → real-size raw font (cached by identity).
QRawFont chbt_real_raw(const QRawFont& scaled) {
    static std::vector<std::pair<QRawFont, QRawFont>> cache;
    for (const auto& e : cache)
        if (e.first == scaled) return e.second;
    QRawFont r = scaled;
    r.setPixelSize(scaled.pixelSize() / qreal(kShapeScale));
    cache.emplace_back(scaled, r);
    return r;
}

/// Chrome/HarfBuzz coverage: the character's own glyph, or (precomposed letters such as ố in Courier/Menlo) every
/// part of its canonical decomposition.
bool chbt_covers(const QString& family, char32_t cp, bool webRanges = true) {
    const auto has = [&](char32_t c) { return webRanges ? family_covers(family, c) : face_covers(family, c); };
    if (has(cp)) return true;
    static QHash<QPair<QString, uint>, bool> cache;
    const auto key = qMakePair(family + (webRanges ? QStringLiteral("|w") : QString()), uint(cp));
    auto it = cache.constFind(key);
    if (it != cache.constEnd()) return *it;
    const QString d = QString::fromUcs4(&cp, 1).normalized(QString::NormalizationForm_D);
    bool ok = d.size() > 1;
    for (char32_t part : d.toUcs4())
        if (ok && !has(part)) ok = false;
    cache.insert(key, ok);
    return ok;
}

bool chbt_is_bitmap(const QRawFont& r) { return r.familyName().contains(QLatin1String("Emoji"), Qt::CaseInsensitive); }

bool chbt_is_mark(char32_t cp) {
    const QChar::Category c = QChar::category(cp);
    return c == QChar::Mark_NonSpacing || c == QChar::Mark_SpacingCombining || c == QChar::Mark_Enclosing ||
           cp == 0x200D || (cp >= 0xFE00 && cp <= 0xFE0F) || (cp >= 0x1F3FB && cp <= 0x1F3FF) ||
           (cp >= 0xE0020 && cp <= 0xE007F);
}

/// Chrome adds no letter-spacing after a BMP Default_Ignorable_Code_Point (U+200B ZWSP, U+2060 WJ, U+FEFF, soft
/// hyphen, bidi controls, Hangul fillers…) nor after U+FFFC; supplementary ones (U+1D173, U+E0001…) are spaced,
/// as are spaces, controls, U+2028 and U+FFF9–FFFB. Measured 27/09 (Chromium 147, Plex + Source Serif, 68 code
/// points). Checked per UTF-16 unit at a grapheme start: ZWNJ/ZWJ, CGJ, variation selectors and tags already
/// join the previous grapheme.
bool chbt_no_letter_spacing(char16_t u) {
    return u == 0x00AD || u == 0x034F || u == 0x061C || (u >= 0x115F && u <= 0x1160) || (u >= 0x17B4 && u <= 0x17B5) ||
           (u >= 0x180B && u <= 0x180F) || (u >= 0x200B && u <= 0x200F) || (u >= 0x202A && u <= 0x202E) ||
           (u >= 0x2060 && u <= 0x206F) || u == 0x3164 || (u >= 0xFE00 && u <= 0xFE0F) || u == 0xFEFF || u == 0xFFA0 ||
           (u >= 0xFFF0 && u <= 0xFFF8) || u == 0xFFFC;
}

constexpr unsigned kEmojiMask = 0x80000000u;

float chbt_emoji_advance(float px) {
    const float extra = px <= 16.0f ? px / 4.0f : px >= 24.0f ? 0.0f : (24.0f - px) / 2.0f;
    return std::floor(px + extra + 0.5f);
}

} // namespace

LineMetrics chrome_line_metrics(const QRawFont& rf) {
    LineMetrics m;
    if (!rf.isValid()) return m;
    float asc = chbt_round(float(rf.ascent()));
    const float desc = chbt_round(float(rf.descent()));
    const QString fam = rf.familyName();
    if (fam == QLatin1String("Times") || fam == QLatin1String("Helvetica") || fam == QLatin1String("Courier"))
        asc += std::floor((asc + desc) * 0.15f + 0.5f);
    m.asc = asc;
    m.desc = desc;
    m.gap = chbt_round(float(rf.leading()));
    return m;
}

const FontEntry& font_entry(const QStringList& cssFamilies, float px, int weight, bool italic) {
    const QString key = cssFamilies.join(QLatin1Char(',')) + QLatin1Char('|') + QString::number(double(px), 'g', 8) +
                        QLatin1Char('|') + QString::number(weight) + QLatin1Char('|') + QString::number(int(italic));
    auto& c = chbt_entries();
    auto it = c.entries.find(key);
    if (it != c.entries.end()) return *it.value();
    auto fe = std::make_shared<FontEntry>();
    fe->px = px;
    fe->spec = resolve_font(cssFamilies, weight, italic, px);
    fe->font = make_qfont(fe->spec, px);
    // Real-size raw face of the primary family (single-family font so fallback never answers).
    QFont prim = make_qfont(fe->spec, px, 1.0f, QStringList{fe->spec.primary});
    fe->raw = QRawFont::fromFont(prim);
    // Metrics from a high-precision face (Qt rounds raw metrics to 1/64 px at the real size).
    QFont primBig = make_qfont(fe->spec, px, kShapeScale, QStringList{fe->spec.primary});
    const QRawFont big = QRawFont::fromFont(primBig);
    QRawFont metricFace = fe->raw;
    if (big.isValid()) {
        fe->ascRaw = float(big.ascent()) / kShapeScale;
        fe->descRaw = float(big.descent()) / kShapeScale;
        fe->xHeight = float(big.xHeight()) / kShapeScale;
        fe->underlinePos = float(big.underlinePosition()) / kShapeScale;
        fe->underlineThickness = std::max(1.0f, chbt_round(float(big.lineThickness()) / kShapeScale));
        LineMetrics m;
        float asc = chbt_round(fe->ascRaw);
        const float desc = chbt_round(fe->descRaw);
        const QString fam = big.familyName();
        if (fam == QLatin1String("Times") || fam == QLatin1String("Helvetica") || fam == QLatin1String("Courier"))
            asc += std::floor((asc + desc) * 0.15f + 0.5f);
        m.asc = asc;
        m.desc = desc;
        m.gap = chbt_round(float(big.leading()) / kShapeScale);
        fe->m = m;
    } else {
        fe->m = chrome_line_metrics(metricFace);
        fe->ascRaw = float(metricFace.ascent());
        fe->descRaw = float(metricFace.descent());
        fe->xHeight = float(metricFace.xHeight());
    }
    if (fe->xHeight <= 0) fe->xHeight = fe->ascRaw * 0.5f;
    fe->strikePos = fe->xHeight / 2.0f;
    c.entries.insert(key, fe);
    return *fe;
}

// ============================================================================================== shaping

namespace {

/// Face coverage cache: does `family` (at any size) have a glyph for `cp`?
bool chbt_family_has(const FontEntry& fe, const QString& family, char32_t cp) {
    static QHash<QString, QRawFont> faces;
    auto it = faces.find(family);
    if (it == faces.end()) it = faces.insert(family, QRawFont::fromFont(make_qfont(fe.spec, 12.0f, 1.0f, QStringList{family})));
    return it.value().isValid() && it.value().supportsCharacter(uint(cp));
}

/// HarfBuzz-style normalization (Chrome): a precomposed character missing from the run's first face but whose
/// NFD components all exist there is shaped decomposed in that face instead of falling back to another font.
/// Returns the text to shape and, per grapheme cluster, its start index in the original and shaped text.
QString chbt_normalize(const FontEntry& fe, const QString& family, const QString& text, const ShapedText* st, int strOffset,
                       std::vector<int>* origStarts, std::vector<int>* shapedStarts) {
    QString out;
    out.reserve(text.size());
    const int len = int(text.size());
    for (int i = 0; i < len;) {
        int j = i + 1;
        while (j < len && !st->graphemeStart[size_t(strOffset + j)]) ++j;
        origStarts->push_back(i);
        shapedStarts->push_back(int(out.size()));
        const QString cl = text.mid(i, j - i);
        bool replaced = false;
        if (cl.size() == 1 && cl[0].unicode() >= 0xC0) {
            const char32_t cp = cl[0].unicode();
            if (!chbt_family_has(fe, family, cp)) {
                const QString nfd = cl.normalized(QString::NormalizationForm_D);
                if (nfd.size() > 1) {
                    bool all = true;
                    for (const QChar c : nfd) all = all && chbt_family_has(fe, family, c.unicode());
                    if (all) { out += nfd; replaced = true; }
                }
            }
        }
        if (!replaced) out += cl;
        i = j;
    }
    return out;
}

struct Tmp { quint32 id; float x, y; int str; int run; float corr; };

void chbt_shape_group(const FontEntry& fe, const QString& origText, const QStringList& families, int strOffset,
                      float xOffset, float letterSpacingActive, ShapedText* st, float* outWidth,
                      const FontSpec* specOverride = nullptr) {
    std::vector<int> origStarts, shapedStarts;
    const QString groupText = chbt_normalize(fe, families.value(0), origText, st, strOffset, &origStarts, &shapedStarts);
    QFont big = make_qfont(specOverride ? *specOverride : fe.spec, fe.px, kShapeScale, families);
    if (letterSpacingActive != 0) {
        big.setFeature(QFont::Tag("liga"), 0);
        big.setFeature(QFont::Tag("clig"), 0);
        big.setFeature(QFont::Tag("calt"), 0);
    }
    QTextLayout layout(groupText, big);
    QTextOption opt;
    opt.setWrapMode(QTextOption::NoWrap);
    opt.setUseDesignMetrics(true);
    layout.setTextOption(opt);
    layout.beginLayout();
    QTextLine line = layout.createLine();
    if (!line.isValid()) {
        layout.endLayout();
        *outWidth = 0;
        return;
    }
    line.setLineWidth(1.0e7);
    layout.endLayout();
    const int len = int(groupText.size());
    // Cluster boundaries and their raw carets. QGlyphRun::stringIndexes() is unreliable once Qt merges fallback
    // fonts (indexes restart at 0), so glyphs are mapped to clusters by x.
    std::vector<int> bIdx = origStarts;
    std::vector<float> bX;
    bX.reserve(shapedStarts.size());
    for (int sidx : shapedStarts) bX.push_back(float(line.cursorToX(sidx)) / kShapeScale);
    const float asc = float(line.ascent());
    const QList<QGlyphRun> grs = layout.glyphRuns(0, len, QTextLayout::RetrieveGlyphIndexes | QTextLayout::RetrieveGlyphPositions);
    std::vector<Tmp> tmp;
    for (const QGlyphRun& gr : grs) {
        const QRawFont scaled = gr.rawFont();
        const QRawFont real = chbt_real_raw(scaled);
        int runIdx = -1;
        for (size_t r = 0; r < st->runs.size(); ++r)
            if (st->runs[r].raw == real) { runIdx = int(r); break; }
        if (runIdx < 0) {
            ShapedText::Run run;
            run.raw = real;
            run.lm = chrome_line_metrics(real);
            run.bitmap = chbt_is_bitmap(real);
            run.primary = real.familyName() == fe.raw.familyName() && real.styleName() == fe.raw.styleName();
            st->runs.push_back(run);
            runIdx = int(st->runs.size()) - 1;
        }
        const bool bitmap = st->runs[size_t(runIdx)].bitmap;
        const QList<quint32> ids = gr.glyphIndexes();
        const QList<QPointF> pos = gr.positions();
        std::vector<QPointF> advS;
        if (bitmap) {
            advS.resize(size_t(ids.size()));
            scaled.advancesForGlyphIndexes(ids.constData(), advS.data(), int(ids.size()));
        }
        // variable fonts: GPOS kerning deltas Qt's HarfBuzz leaves out (ChbKernVar_p.h)
        std::vector<float> kernDelta;
        if (!bitmap && ids.size() > 1 && real.familyName() == fe.raw.familyName()) {
            if (const ChbkFace* kf = ChbkFace::get(real)) {
                const FontSpec& sp = specOverride ? *specOverride : fe.spec;
                kf->deltas(std::vector<quint32>(ids.begin(), ids.end()), kf->coords(sp.wght, sp.opsz), &kernDelta);
                for (float& k : kernDelta) k *= fe.px / float(kf->upem);
            }
        }
        for (qsizetype i = 0; i < ids.size(); ++i) {
            Tmp t;
            t.id = ids[i];
            t.x = float(pos[i].x()) / kShapeScale;
            t.y = (float(pos[i].y()) - asc) / kShapeScale;
            // cluster = last boundary whose caret is ≤ the glyph origin
            const auto it = std::upper_bound(bX.begin(), bX.end(), t.x + 1e-3f);
            const size_t bi = it == bX.begin() ? 0 : size_t(it - bX.begin()) - 1;
            t.str = bIdx.empty() ? 0 : bIdx[bi];
            t.run = runIdx;
            // Chrome emoji advance (Apple Color Emoji): whole pixels = round(px + extra), extra = px/4 up to 16 px,
            // falling linearly to 0 at 24 px (measured 27/09 on 8–40 px in 1/4 px steps: every size exact)
            t.corr = bitmap ? chbt_emoji_advance(fe.px) - float(advS[size_t(i)].x()) / kShapeScale : 0.0f;
            if (!kernDelta.empty()) t.corr += kernDelta[size_t(i)];
            tmp.push_back(t);
        }
    }
    std::stable_sort(tmp.begin(), tmp.end(), [](const Tmp& a, const Tmp& b) { return a.str < b.str || (a.str == b.str && a.x < b.x); });
    // bitmap-advance and variable-kerning corrections shift every later cluster
    float shift = 0;
    int curStr = -1;
    float pendingCorr = 0;
    for (const Tmp& t : tmp) {
        if (t.str != curStr) {
            shift += pendingCorr;
            pendingCorr = 0;
            curStr = t.str;
        }
        ShapedText::Glyph g;
        g.id = t.id;
        g.x = xOffset + t.x + shift;
        g.y = t.y;
        g.str = strOffset + t.str;
        g.run = t.run;
        st->glyphs.push_back(g);
        pendingCorr += t.corr;
    }
    shift += pendingCorr;
    *outWidth = float(line.cursorToX(len)) / kShapeScale + shift;
}

} // namespace

const ShapedText& shape_text(const FontEntry& fe, const QString& text, float letterSpacing) {
    auto& cache = chbt_shapes();
    ChbtKey key{&fe, letterSpacing, text};
    auto it = cache.find(key);
    if (it != cache.end()) return *it->second;

    auto st = std::make_unique<ShapedText>();
    st->text = text;
    st->font = &fe;
    st->letterSpacing = letterSpacing;
    const int n = int(text.size());
    st->caret.assign(size_t(n) + 1, 0.0f);
    st->graphemeStart.assign(size_t(n) + 1, 0);
    if (n > 0) {
        QTextBoundaryFinder gb(QTextBoundaryFinder::Grapheme, text);
        for (qsizetype p = gb.toNextBoundary(); p >= 0 && p <= n; p = gb.toNextBoundary()) st->graphemeStart[size_t(p)] = 1;
        st->graphemeStart[0] = 1;

        // ---- split into groups with the same effective font list, the way Chrome/Blink resolves fonts:
        //  1. the CSS family list (Google subset unicode-ranges honoured) + standard font, per character;
        //  2. characters none of them covers: Blink's system-fallback loop over the "hint list" — the first
        //     unresolved character picks a font (measured Chrome table for this primary family, see
        //     ChbFontsChrome_p.h), every later unresolved character that font covers joins it, repeat;
        //  3. Emoji_Presentation / VS16 sequences are their own segment → Apple Color Emoji.
        const QStringList& fams = fe.spec.families;
        auto maskFor = [&](char32_t cp) {
            unsigned m = 0;
            for (int i = 0; i < fams.size() && i < 31; ++i)
                if (!web_family_covers(fams[i], fe.spec.italicFace, cp)) m |= 1u << i;
            return m;
        };
        constexpr unsigned kSysBase = 0x40000000u;
        constexpr unsigned kPrimaryFull = 0x3FFFFFFFu; // primary web font's own file, outside its unicode-range
        const bool bold = fe.spec.cssWeight >= 600;
        struct Ch { int i, len; char32_t cp; unsigned m; bool pending; int seg; };
        std::vector<Ch> chars;
        chars.reserve(size_t(n));
        for (int i = 0; i < n;) {
            char32_t cp = text[i].unicode();
            int len = 1;
            if (QChar::isHighSurrogate(text[i].unicode()) && i + 1 < n && QChar::isLowSurrogate(text[i + 1].unicode())) {
                cp = QChar::surrogateToUcs4(text[i], text[i + 1]);
                len = 2;
            }
            char32_t nextCp = 0;
            if (i + len < n) {
                nextCp = text[i + len].unicode();
                if (QChar::isHighSurrogate(char16_t(nextCp)) && i + len + 1 < n) nextCp = QChar::surrogateToUcs4(text[i + len], text[i + len + 1]);
            }
            Ch c{i, len, cp, 0, false, 0};
            const bool follow = !chars.empty() && (chbt_is_mark(cp) || cp == 0x200D || cp == 0xFE0F || cp == 0xFE0E);
            if (follow) {
                c.m = chars.back().m;
                c.pending = chars.back().pending;
            } else {
                const bool emojiSeq = nextCp == 0xFE0F || (!chars.empty() && chars.back().m == kEmojiMask && i > 0 && text[i - 1].unicode() == 0x200D);
                c.m = maskFor(cp);
                if (emojiSeq) {
                    c.m = kEmojiMask;
                } else if (cp >= 0xA0) {
                    bool covered = false;
                    for (int fi = 0; fi < fams.size() && !covered; ++fi)
                        if (!(fi < 31 && (c.m & (1u << fi)))) covered = chbt_covers(fams[fi], cp);
                    if (!covered) {
                        if (is_emoji_presentation(cp)) c.m = kEmojiMask;
                        else c.pending = true;
                    }
                }
            }
            chars.push_back(c);
            i += len;
        }
        // Blink shapes per script run (Common/Inherited characters join the preceding run, or the following one at
        // the start): the hint loop below never crosses a run boundary (e.g. symbols after a Greek Δ).
        {
            int seg = 0;
            QChar::Script cur = QChar::Script_Unknown;
            for (Ch& c : chars) {
                const QChar::Script sc = QChar::script(c.cp);
                const bool weak = sc == QChar::Script_Common || sc == QChar::Script_Inherited || sc == QChar::Script_Unknown;
                if (!weak) {
                    if (cur != QChar::Script_Unknown && sc != cur) ++seg;
                    cur = sc;
                }
                c.seg = seg;
            }
        }
        // Blink's hint loop over the unresolved characters
        QStringList sysFams;
        const QString primary = fams.value(0);
        for (size_t h = 0; h < chars.size(); ++h) {
            if (!chars[h].pending) continue;
            const char32_t hint = chars[h].cp;
            QString f = chrome_fallback_family(primary, bold, hint);
            if (f == primary && !primary_face_fallback()) f.clear(); // CHB_FONT_MODE=google: subset lacks it
            if (f.isEmpty() || !chbt_covers(f, hint, false)) f = system_fallback_family(hint);
            unsigned m;
            if (f.isEmpty()) {
                m = chars[h].m; // let Qt pick (its own fallback)
            } else if (f == primary && is_web_family(primary)) {
                m = kPrimaryFull;
            } else {
                int idx = int(sysFams.indexOf(f));
                if (idx < 0) { sysFams << f; idx = int(sysFams.size()) - 1; }
                m = kSysBase + unsigned(idx);
            }
            for (size_t k = h; k < chars.size() && chars[k].seg == chars[h].seg; ++k) {
                if (!chars[k].pending) continue;
                const bool takes = k == h || (!f.isEmpty() && chbt_covers(f, chars[k].cp, false));
                if (!takes) continue;
                chars[k].m = m;
                chars[k].pending = false;
                for (size_t q = k + 1; q < chars.size() && (chbt_is_mark(chars[q].cp) || chars[q].cp == 0x200D ||
                                                             chars[q].cp == 0xFE0F || chars[q].cp == 0xFE0E); ++q) {
                    chars[q].m = m;
                    chars[q].pending = false;
                }
            }
        }
        struct Group { int from, to; unsigned mask; };
        std::vector<Group> groups;
        for (const Ch& c : chars) {
            if (groups.empty() || groups.back().mask != c.m) groups.push_back(Group{c.i, c.i + c.len, c.m});
            else groups.back().to = c.i + c.len;
        }
        float x = 0;
        for (const Group& g : groups) {
            QStringList f;
            const FontSpec* spec = nullptr;
            FontSpec selfSpec;
            if (g.mask == kEmojiMask) f << emoji_family();
            else if (g.mask == kPrimaryFull) {
                f << primary;
                // Chrome's fallback instance of the primary file: automatic optical size (opsz = px)
                if (fe.spec.opsz > 0) {
                    selfSpec = fe.spec;
                    selfSpec.opsz = std::clamp(fe.px, 8.0f, 60.0f);
                    spec = &selfSpec;
                }
            } else if (g.mask >= kSysBase) f << sysFams.value(int(g.mask - kSysBase));
            else
                for (int i = 0; i < fams.size(); ++i)
                    if (!(i < 31 && (g.mask & (1u << i)))) f << fams[i];
            if (f.isEmpty()) f << QStringLiteral("Times New Roman");
            float w = 0;
            chbt_shape_group(fe, text.mid(g.from, g.to - g.from), f, g.from, x, letterSpacing, st.get(), &w, spec);
            if (qEnvironmentVariableIsSet("CHB_DEBUG_FONTS"))
                qDebug().noquote() << "[chb-font]" << f.join(QLatin1Char(',')) << (spec ? "opsz=px" : "") << w << text.mid(g.from, g.to - g.from);
            x += w;
        }
        float total = x;

        // ---- letter-spacing per grapheme cluster, none after default-ignorables (chbt_no_letter_spacing, E-9)
        std::vector<int> ordinal(size_t(n) + 1, 0); // spaced clusters before the one holding each index
        int k = 0;
        bool spaced = false;
        for (int i = 0; i < n; ++i) {
            if (st->graphemeStart[size_t(i)]) {
                if (spaced) ++k;
                spaced = !chbt_no_letter_spacing(text[i].unicode());
            }
            ordinal[size_t(i)] = k;
        }
        const int clusters = k + (spaced ? 1 : 0);
        if (letterSpacing != 0) {
            for (auto& g : st->glyphs) g.x += letterSpacing * float(ordinal[size_t(std::clamp(g.str, 0, n - 1))]);
            total += letterSpacing * float(clusters);
        }
        st->width = total;

        // ---- carets: first glyph x of the cluster at each index, carried from the right
        std::vector<float> minX(size_t(n), std::numeric_limits<float>::infinity());
        for (const auto& g : st->glyphs)
            if (g.str >= 0 && g.str < n) minX[size_t(g.str)] = std::min(minX[size_t(g.str)], g.x);
        st->caret[size_t(n)] = total;
        float next = total;
        for (int i = n - 1; i >= 0; --i) {
            if (std::isfinite(minX[size_t(i)])) next = minX[size_t(i)];
            st->caret[size_t(i)] = next;
        }
        std::stable_sort(st->glyphs.begin(), st->glyphs.end(),
                         [](const ShapedText::Glyph& a, const ShapedText::Glyph& b) { return a.str < b.str; });
        for (const auto& r : st->runs)
            if (!r.primary) st->multiFont = true;
    }
    ShapedText* raw = st.get();
    cache.emplace(std::move(key), std::move(st));
    return *raw;
}

void ShapedText::metrics_in_range(int from, int to, float* maxA, float* maxD) const {
    if (glyphs.empty()) return;
    auto lo = std::lower_bound(glyphs.begin(), glyphs.end(), from, [](const Glyph& g, int v) { return g.str < v; });
    std::vector<char> seen(runs.size(), 0);
    for (auto it = lo; it != glyphs.end() && it->str < to; ++it) {
        if (seen[size_t(it->run)]) continue;
        seen[size_t(it->run)] = 1;
        const LineMetrics& m = runs[size_t(it->run)].lm;
        const float halfTop = std::floor(m.gap / 2.0f); // Blink: floor((line-height − height) / 2)
        const float a = m.asc + halfTop;
        const float d = m.desc + (m.gap - halfTop);
        *maxA = std::max(*maxA, a);
        *maxD = std::max(*maxD, d);
    }
}

void ShapedText::paint(QPainter& p, QPointF origin, int from, int to, const QColor& color) const {
    if (glyphs.empty() || to <= from) return;
    const float x0 = x(from);
    auto lo = std::lower_bound(glyphs.begin(), glyphs.end(), from, [](const Glyph& g, int v) { return g.str < v; });
    auto hi = lo;
    while (hi != glyphs.end() && hi->str < to) ++hi;
    if (lo == hi) return;
    const bool fakeItalic = font && font->spec.fakeItalic;
    const bool fakeBold = font && font->spec.fakeBold;
    p.save();
    QTransform t = p.transform();
    t.translate(origin.x(), origin.y());
    if (fakeItalic) t = QTransform(1, 0, -0.25, 1, 0, 0) * t; // Skia fake italic: skewX −1/4
    p.setTransform(t);
    p.setPen(color);
    auto it = lo;
    while (it != hi) {
        const int run = it->run;
        QVector<quint32> ids;
        QVector<QPointF> pos;
        auto jt = it;
        for (; jt != hi && jt->run == run; ++jt) {
            ids.push_back(jt->id);
            pos.push_back(QPointF(qreal(jt->x - x0), qreal(jt->y)));
        }
        const Run& r = runs[size_t(run)];
        if (fakeBold && !r.bitmap) {
            // Skia embolden: outline stroked+filled with width = size × lerp(1/24 @9px … 1/32 @36px)
            const float sz = font->px;
            const float k = sz <= 9 ? 1.0f / 24 : (sz >= 36 ? 1.0f / 32 : 1.0f / 24 + (sz - 9) / 27.0f * (1.0f / 32 - 1.0f / 24));
            QPainterPath path;
            for (int i = 0; i < ids.size(); ++i) path.addPath(r.raw.pathForGlyph(ids[i]).translated(pos[i]));
            p.setRenderHint(QPainter::Antialiasing, true);
            p.fillPath(path, color);
            QPen pen(color, qreal(sz * k));
            pen.setJoinStyle(Qt::RoundJoin);
            p.strokePath(path, pen);
        } else {
            QGlyphRun g;
            g.setRawFont(r.raw);
            g.setGlyphIndexes(ids);
            g.setPositions(pos);
            // Qt's raster glyph cache has no subpixel positioning here: a glyph at device x lands on pixel
            // floor(x + 0.3125) (measured 27/09, offscreen and cocoa alike), i.e. ~0.19 px left of Chrome/Skia on
            // average (Skia: nearest 1/4 px). Drawing 0.1 px to the right recentres it (suite pixel match 98.73 →
            // 98.87 %, fixture 99.27 → 99.43 %, E1 tests 99.23 → 99.32 %). Env CHB_TEXT_BIAS=<px> overrides.
            // Chrome/Skia on macOS also draws text heavier than Qt's CoreText glyph cache (font smoothing + mask
            // contrast; measured ink ≈ +10 %): a second pass `darken` px further right matches it. Env
            // CHB_TEXT_DARKEN=off disables, =<px> sets the offset (0.05 best together with the bias above).
            static const auto envPx = [](const char* name, float def) {
                const QByteArray e = qgetenv(name).trimmed().toLower();
                if (e == "off" || e == "no") return -1.0f;
                bool ok = false;
                const float v = QString::fromLatin1(e).toFloat(&ok);
                return ok ? v : def;
            };
            static const float bias = envPx("CHB_TEXT_BIAS", 0.1f);
            static const float darken = envPx("CHB_TEXT_DARKEN", 0.05f);
            p.drawGlyphRun(QPointF(qreal(std::max(0.0f, bias)), 0), g);
            if (darken > 0 && !r.bitmap) p.drawGlyphRun(QPointF(qreal(std::max(0.0f, bias) + darken), 0), g);
        }
        it = jt;
    }
    p.restore();
}

void clear_text_caches() { chbt_shapes().clear(); }
int text_cache_size() { return int(chbt_shapes().size()); }

} // namespace fincept::screens::chb
