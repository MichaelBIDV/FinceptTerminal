// src/screens/hdcv_launchpad/HlpFontShape.cpp
// Launchpad text engine — shaping as Chrome does it on macOS: clusters, primary-font advances
// (hmtx + HVAR at opsz/wght + AAT trak), GPOS kerning, per-character font fallback, pen positions,
// Blink vertical metrics (0.5px rounding) and glyph painting through QGlyphRun.
#include "screens/hdcv_launchpad/HlpFont_p.h"

#include <QFontMetricsF>
#include <QGlyphRun>
#include <QPainter>
#include <QTextLayout>
#include <QTextOption>

#include <algorithm>
#include <cmath>
#include <limits>
#include <memory>

namespace fincept::screens::hlp::detail {

namespace {

float hlpfs_roundHalf(float v) {
    return std::floor(v * 2.0f + 0.5f) / 2.0f;
}

struct FaceKey {
    Fam fam;
    int weight;
    bool italic;
    bool operator==(const FaceKey& o) const { return fam == o.fam && weight == o.weight && italic == o.italic; }
};
size_t qHash(const FaceKey& k, size_t seed = 0) noexcept {
    return ::qHashMulti(seed, int(k.fam), k.weight, k.italic);
}

struct InstKey {
    const Face* face;
    int opsz64;
    int weight;
    bool operator==(const InstKey& o) const { return face == o.face && opsz64 == o.opsz64 && weight == o.weight; }
};
size_t qHash(const InstKey& k, size_t seed = 0) noexcept {
    return ::qHashMulti(seed, quintptr(k.face), k.opsz64, k.weight);
}

struct Engine {
    QHash<FaceKey, std::shared_ptr<Face>> faces;
    QHash<InstKey, std::shared_ptr<Inst>> insts;
    QHash<FontKey, QRawFont> paintFonts;
    QHash<FontKey, float> qtPx;
    QHash<FontKey, QHash<QString, std::shared_ptr<const Shaped>>> shapes;
    QHash<FontKey, QHash<QString, float>> fallbackAdv;
    QHash<FontKey, QHash<QString, QVector<Shaped::Run>>> fallbackRuns; // per cluster text
    std::shared_ptr<Face> fbFace[FbCount];
    std::shared_ptr<Inst> fbInst[FbCount];
    int shapeCount = 0;

    /// Instance of a FallbackFont (not variable: default coordinates), nullptr if not installed.
    Inst* fallbackInst(int id) {
        if (id <= FbNone || id >= FbCount)
            return nullptr;
        if (!fbInst[id]) {
            const QRawFont& raw = fallbackRawFont(id);
            if (!raw.isValid())
                return nullptr;
            fbFace[id] = std::make_shared<Face>();
            initFace(*fbFace[id], raw);
            fbInst[id] = std::make_shared<Inst>();
            fbInst[id]->face = fbFace[id].get();
        }
        return fbInst[id].get();
    }

    Face* face(const FontKey& k) {
        const FaceKey fk{k.fam, k.fam == Fam::Sans ? 400 : (k.weight >= 600 ? 700 : 400), k.italic};
        auto it = faces.find(fk);
        if (it != faces.end())
            return it->get();
        auto f = std::make_shared<Face>();
        FontKey ref = k;
        ref.px = 32.0f;
        ref.weight = fk.weight;
        initFace(*f, qfontFor(ref));
        faces.insert(fk, f);
        return f.get();
    }

    static int normalize(const Face& f, int axisIndex, float v) {
        const auto& ax = f.axes[axisIndex];
        v = std::clamp(v, ax.mn, ax.mx);
        float n = 0.0f;
        if (v < ax.def && ax.def > ax.mn)
            n = (v - ax.def) / (ax.def - ax.mn);
        else if (v > ax.def && ax.mx > ax.def)
            n = (v - ax.def) / (ax.mx - ax.def);
        int c = int(std::lround(n * 16384.0f));
        if (axisIndex < f.avarMaps.size()) {
            const auto& m = f.avarMaps[axisIndex];
            if (m.size() >= 2) {
                if (c <= m[0].first)
                    c = c - m[0].first + m[0].second;
                else {
                    int i = 1;
                    const int cnt = int(m.size()) - 1;
                    while (i < cnt && c > m[i].first)
                        ++i;
                    if (c >= m[i].first)
                        c = c - m[i].first + m[i].second;
                    else if (m[i - 1].first == m[i].first)
                        c = m[i - 1].second;
                    else {
                        const int denom = m[i].first - m[i - 1].first;
                        c = int(std::lround(float(m[i - 1].second) +
                                            float(m[i].second - m[i - 1].second) * float(c - m[i - 1].first) /
                                                float(denom)));
                    }
                }
            }
        }
        return c;
    }

    Inst* inst(const FontKey& k) {
        Face* f = face(k);
        const float opsz = k.px;
        const int wq = k.weight;
        const InstKey key{f, int(std::lround(opsz * 64.0f)), wq};
        auto it = insts.find(key);
        if (it != insts.end())
            return it->get();
        auto in = std::make_shared<Inst>();
        in->face = f;
        if (!f->axes.isEmpty()) {
            in->coords.resize(f->axes.size());
            for (int i = 0; i < f->axes.size(); ++i) {
                float v = f->axes[i].def;
                if (f->axes[i].tag == 0x6f70737au /*opsz*/)
                    v = opsz;
                else if (f->axes[i].tag == 0x77676874u /*wght*/)
                    v = float(wq);
                in->coords[i] = normalize(*f, i, v);
            }
        }
        insts.insert(key, in);
        return in.get();
    }

    /// AAT trak, track 0, at ptem (design units, rounded like HarfBuzz).
    static float trakValue(const Face& f, float ptem) {
        const Tbl& t = f.trak;
        if (t.n < 12 || ptem <= 0.0f)
            return 0.0f;
        const int horiz = t.u16(6);
        if (!horiz)
            return 0.0f;
        const int nTracks = t.u16(horiz), nSizes = t.u16(horiz + 2);
        const int sizeTable = int(t.u32(horiz + 4));
        if (nSizes == 0)
            return 0.0f;
        // track 0 (normal); a font without it (.CJK Symbols Fallback has only track 1) gets the track
        // closest to 0 — what CoreText hands Chrome for the cascade font (measured: ◤ ═ at 8–24px)
        int entry = -1;
        float bestTrack = 0.0f;
        for (int i = 0; i < nTracks; ++i) {
            const int e = horiz + 8 + i * 8;
            const float tr = std::abs(t.fixed(e));
            if (entry < 0 || tr < bestTrack) {
                entry = e;
                bestTrack = tr;
            }
            if (tr == 0.0f)
                break;
        }
        if (entry < 0)
            return 0.0f;
        const int values = t.u16(entry + 6);
        auto val = [&](int i) { return float(t.s16(values + i * 2)); };
        auto size = [&](int i) { return t.fixed(sizeTable + i * 4); };
        if (nSizes == 1)
            return val(0);
        int si = 0;
        for (si = 0; si < nSizes - 1; ++si)
            if (size(si) >= ptem)
                break;
        const int idx = si ? si - 1 : 0;
        const float s0 = size(idx), s1 = size(idx + 1);
        const float tt = s0 == s1 ? 0.0f : (ptem - s0) / (s1 - s0);
        return std::round(tt * val(idx + 1) + (1.0f - tt) * val(idx));
    }

    /// Qt resolves a fractional CSS size (10.5px, 9.5px…) to a font engine at the ROUNDED pixel size
    /// (measured: setPointSizeF(10.5) at 72 dpi → QRawFont::pixelSize() 11). Anything Qt shapes or
    /// measures with qfontFor(k) is therefore scaled by px / qtPx(k) before use.
    float qtScale(const FontKey& k) {
        auto it = qtPx.constFind(k);
        if (it == qtPx.constEnd()) {
            const QRawFont r = QRawFont::fromFont(qfontFor(k));
            it = qtPx.insert(k, r.isValid() && r.pixelSize() > 0 ? float(r.pixelSize()) : k.px);
        }
        return k.px / *it;
    }

    const QRawFont& paintFont(const FontKey& k) {
        auto it = paintFonts.find(k);
        if (it == paintFonts.end()) {
            QRawFont r = QRawFont::fromFont(qfontFor(k));
            if (r.isValid() && std::abs(r.pixelSize() - k.px) > 1e-4)
                r.setPixelSize(k.px); // exact CSS size, not Qt's rounded engine size
            it = paintFonts.insert(k, r);
        }
        return *it;
    }

    float fallbackAdvance(const FontKey& k, const QString& s) {
        auto& m = fallbackAdv[k];
        auto it = m.constFind(s);
        if (it != m.constEnd())
            return *it;
        const float w = float(QFontMetricsF(qfontFor(k)).horizontalAdvance(s)) * qtScale(k);
        m.insert(s, w);
        return w;
    }
};

Engine& hlpfs_engine() {
    static Engine e;
    return e;
}

char32_t hlpfs_cpAt(const QString& s, int i) {
    const QChar c = s.at(i);
    if (c.isHighSurrogate() && i + 1 < s.size() && s.at(i + 1).isLowSurrogate())
        return QChar::surrogateToUcs4(c, s.at(i + 1));
    return c.unicode();
}

bool hlpfs_isMarkChar(char32_t cp) {
    const auto c = QChar::category(cp);
    return c == QChar::Mark_NonSpacing || c == QChar::Mark_SpacingCombining || c == QChar::Mark_Enclosing;
}

bool hlpfs_joinsCluster(char32_t cp) {
    // variation selectors, ZWJ and emoji modifiers stay with the previous cluster
    return hlpfs_isMarkChar(cp) || cp == 0x200D || (cp >= 0xFE00 && cp <= 0xFE0F) || (cp >= 0x1F3FB && cp <= 0x1F3FF) ||
           (cp >= 0xE0100 && cp <= 0xE01EF);
}

bool hlpfs_isRegional(char32_t cp) {
    return cp >= 0x1F1E6 && cp <= 0x1F1FF;
}

/// Advance (px) Chrome gives Apple Color Emoji (measured in Chrome 153 on macOS 27): never below
/// 12px wide; smaller sizes step in half pixels. 0 = not an emoji.
float hlpfs_emojiPx(char32_t cp, float px) {
    if ((cp >= 0x1F000 && cp <= 0x1FAFF) || hlpfs_isRegional(cp))
        return px >= 12.0f ? px : std::ceil((px + 12.0f)) / 2.0f;
    return 0.0f;
}

/// Shape `text` with Qt's HarfBuzz in `font` (AAT morx / GPOS marks included) → fallback runs whose
/// glyph offsets are relative to the cluster pen, baseline at y = 0. Font merging follows `font`.
QVector<Shaped::Run> hlpfs_qtRuns(const QString& text, const QFont& font) {
    QTextLayout l(text, font);
    QTextOption o;
    o.setWrapMode(QTextOption::NoWrap);
    l.setTextOption(o);
    l.beginLayout();
    const QTextLine line = l.createLine();
    l.endLayout();
    const qreal asc = line.isValid() ? line.ascent() : 0.0;
    QVector<Shaped::Run> out;
    for (const QGlyphRun& g : l.glyphRuns()) {
        Shaped::Run r;
        r.fallback = true;
        r.font = g.rawFont();
        r.glyphs = g.glyphIndexes();
        for (const QPointF& pt : g.positions())
            r.fpos.push_back(QPointF(pt.x(), pt.y() - asc));
        out.push_back(r);
    }
    return out;
}

/// HarfBuzz's "shortest" canonical decomposition (hb-ot-shape-normalize.cc decompose()): a character
/// the font lacks is split one level at a time until the font has the first part (Menlo ổ → ô + ◌̉).
bool hlpfs_hbDecompose(Face* f, char32_t cp, QVector<char32_t>& out) {
    if (f->glyph(cp)) {
        out.push_back(cp);
        return true;
    }
    if (QChar::decompositionTag(cp) != QChar::Canonical)
        return false;
    const QString d = QChar::decomposition(cp);
    if (d.isEmpty())
        return false;
    const char32_t a = hlpfs_cpAt(d, 0);
    const int la = QChar::requiresSurrogates(a) ? 2 : 1;
    const char32_t b = la < d.size() ? hlpfs_cpAt(d, la) : 0;
    if ((b && !f->glyph(b)) || !hlpfs_hbDecompose(f, a, out))
        return false;
    if (b)
        out.push_back(b);
    return true;
}

/// HarfBuzz glyph extents in px, y up (h ≤ 0). Blink on macOS answers them with the bounds of the
/// glyph path (every point, off-curve included) — the glyf header for a static TrueType face.
struct hlpfs_Ext {
    float xb = 0.0f, yb = 0.0f, w = 0.0f, h = 0.0f;
};

hlpfs_Ext hlpfs_extents(Engine& E, Face* f, const FontKey& k, quint32 g) {
    hlpfs_Ext e;
    QRectF b;
    if (f->axes.isEmpty() && f->glyphBounds(g, b)) {
        const float s = k.px / float(f->upem);
        e.xb = float(b.left()) * s;
        e.yb = float(b.bottom()) * s; // yMax
        e.w = float(b.width()) * s;
        e.h = -float(b.height()) * s;
        return e;
    }
    const QRectF r = E.paintFont(k).pathForGlyph(g).controlPointRect(); // y down
    e.xb = float(r.left());
    e.yb = -float(r.top());
    e.w = float(r.width());
    e.h = -float(r.height());
    return e;
}

/// A cluster the primary font has no composed glyph for, shaped the way Chrome's HarfBuzz does it:
/// shortest canonical decomposition, then fallback mark positioning (Menlo has no GPOS; see
/// hb-ot-shape-fallback.cc position_around_base / position_mark) — each mark centred on the base's
/// advance and stacked on the ink above (below) it with a 1/16 em gap. The mark gets its own glyph
/// position, so Skia rounds its y to a whole pixel on its own. Empty: a part is missing (Qt shapes).
QVector<Shaped::Run> hlpfs_markRuns(Engine& E, const FontKey& k, const QString& s) {
    Face* f = E.face(k);
    QVector<char32_t> cps;
    for (int i = 0; i < s.size();) {
        const char32_t cp = hlpfs_cpAt(s, i);
        i += QChar::requiresSurrogates(cp) ? 2 : 1;
        if (!hlpfs_hbDecompose(f, cp, cps))
            return {};
    }
    if (cps.size() < 2 || QChar::combiningClass(cps[0]) != 0)
        return {};
    for (int i = 1; i < cps.size(); ++i)
        if (QChar::combiningClass(cps[i]) == 0)
            return {};
    std::stable_sort(cps.begin() + 1, cps.end(),
                     [](char32_t a, char32_t b) { return QChar::combiningClass(a) < QChar::combiningClass(b); });
    Inst* in = E.inst(k);
    Shaped::Run r;
    r.fallback = true;
    r.font = E.paintFont(k);
    const quint32 g0 = f->glyph(cps[0]);
    r.glyphs.push_back(g0);
    r.fpos.push_back(QPointF(0, 0));
    hlpfs_Ext base = hlpfs_extents(E, f, k, g0);
    base.xb = 0.0f; // HarfBuzz centres on the advance, not the ink (harfbuzz#1532)
    base.w = in->advance(g0) * k.px / float(f->upem);
    hlpfs_Ext cl = base;
    int last = 255;
    const float gap = k.px / 16.0f;
    for (int i = 1; i < cps.size(); ++i) {
        const quint32 g = f->glyph(cps[i]);
        const int cc = QChar::combiningClass(cps[i]);
        if (cc != last) {
            last = cc;
            cl = base;
        }
        const hlpfs_Ext m = hlpfs_extents(E, f, k, g);
        float xo = cl.xb + (cl.w - m.w) / 2.0f - m.xb; // centre
        if (cc == 233 || cc == 234)
            xo = cl.xb + cl.w - m.w / 2.0f - m.xb;
        else if (cc == 200 || cc == 218 || cc == 228)
            xo = cl.xb - m.xb;
        else if (cc == 216 || cc == 222 || cc == 232)
            xo = cl.xb + cl.w - m.w - m.xb;
        float yo = 0.0f;
        const bool below = cc == 233 || cc == 218 || cc == 220 || cc == 222;
        const bool above = cc == 234 || cc == 228 || cc == 230 || cc == 232;
        if (below || cc == 200 || cc == 202) {
            if (below)
                cl.h -= gap;
            yo = cl.yb + cl.h - m.yb;
            if (yo > 0.0f) { // never shift "below" marks up
                cl.h -= yo;
                yo = 0.0f;
            }
            cl.h += m.h;
        } else if (above || cc == 214 || cc == 216) {
            if (above) {
                cl.yb += gap;
                cl.h -= gap;
            }
            yo = cl.yb - (m.yb + m.h);
            if (yo <= 0.0f) { // don't shift "above" marks down too much
                const float c = -yo / 2.0f;
                cl.yb += c;
                cl.h -= c;
                yo += c;
            }
            cl.yb -= m.h;
            cl.h += m.h;
        }
        r.glyphs.push_back(g);
        r.fpos.push_back(QPointF(xo, -yo));
    }
    return {r};
}

/// Glyph runs for one fallback cluster (cached per font + cluster text).
/// decomposed: the primary font composes it from base + marks (Menlo ế) → primary font, NFD, no merging.
/// tableFont: Chrome's font from HlpFontFallback.cpp → that font's glyph at px. Else Qt's cascade.
QVector<Shaped::Run> hlpfs_fallbackRuns(Engine& E, const FontKey& k, const QString& s, bool decomposed,
                                         int tableFont, quint32 tableGlyph) {
    auto& cache = E.fallbackRuns[k];
    auto it = cache.constFind(s);
    if (it != cache.constEnd())
        return *it;
    QVector<Shaped::Run> runs;
    if (decomposed) {
        runs = hlpfs_markRuns(E, k, s);
        if (!runs.isEmpty()) { // exact px already: no Qt rounding to undo
            cache.insert(s, runs);
            return runs;
        }
        QFont pf = qfontFor(k);
        pf.setStyleStrategy(QFont::NoFontMerging);
        runs = hlpfs_qtRuns(s.normalized(QString::NormalizationForm_D), pf);
    } else if (tableFont != FbNone && tableGlyph) {
        Shaped::Run r;
        r.fallback = true;
        r.font = fallbackRawFont(tableFont);
        r.font.setPixelSize(k.px * fallbackScale(tableFont, k.px));
        r.glyphs = {tableGlyph};
        r.fpos = {QPointF(0, 0)};
        runs = {r};
    }
    if (runs.isEmpty())
        runs = hlpfs_qtRuns(s, qfontFor(k));
    if (!(tableFont != FbNone && tableGlyph) || decomposed) {
        const float f = E.qtScale(k); // Qt shaped at its rounded size
        if (std::abs(f - 1.0f) > 1e-5f)
            for (Shaped::Run& r : runs) {
                r.font.setPixelSize(r.font.pixelSize() * f);
                for (QPointF& pt : r.fpos)
                    pt *= f;
            }
    }
    cache.insert(s, runs);
    return runs;
}

std::shared_ptr<Shaped> hlpfs_shape(const FontKey& k, const QString& input) {
    Engine& E = hlpfs_engine();
    auto out = std::make_shared<Shaped>();
    const QString t = input.normalized(QString::NormalizationForm_C);
    out->text = t;
    const int n = int(t.size());
    out->x.fill(0.0f, n + 1);
    out->clus.fill(0, n + 1);

    Face* f = E.face(k);
    Inst* in = E.inst(k);
    const float scale = k.px / float(f->upem);
    const float trak = Engine::trakValue(*f, k.px);
    const bool isMono = k.fam == Fam::Mono;

    // 1. clusters
    struct Cl {
        int from, to;
        quint32 g;       // primary glyph (0 = fallback)
        float adv;       // px
        bool fb;         // fallback cluster (drawn with `fr`)
        QVector<Shaped::Run> fr;
    };
    QVector<Cl> cls;
    cls.reserve(n);
    for (int i = 0; i < n;) {
        const char32_t cp = hlpfs_cpAt(t, i);
        const int len = QChar::requiresSurrogates(cp) ? 2 : 1;
        const bool pairRegional = hlpfs_isRegional(cp) && !cls.isEmpty() && cls.last().to - cls.last().from == 2 &&
                                  hlpfs_isRegional(hlpfs_cpAt(t, cls.last().from));
        if (!cls.isEmpty() && (hlpfs_joinsCluster(cp) || pairRegional)) {
            cls.last().to = i + len;
            // a mark the primary font cannot compose keeps the base advance; paint via fallback
            if (!cls.last().fb && f->glyph(cp) == 0)
                cls.last().fb = true;
            i += len;
            continue;
        }
        Cl c{i, i + len, f->glyph(cp), 0.0f, false, {}};
        cls.push_back(c);
        i += len;
    }

    // 2. advances
    for (Cl& c : cls) {
        if (c.g != 0 && !c.fb) {
            c.adv = (in->advance(c.g) + trak) * scale;
            continue;
        }
        const QString s = t.mid(c.from, c.to - c.from);
        // Chrome decomposes letters the primary font lacks (Menlo: ế, ủ…) and keeps the base advance
        const QString nfd = s.normalized(QString::NormalizationForm_D);
        const char32_t base = nfd.isEmpty() ? 0 : hlpfs_cpAt(nfd, 0);
        const quint32 bg = base ? f->glyph(base) : 0;
        bool marksOk = bg != 0;
        for (int j = QChar::requiresSurrogates(base) ? 2 : 1; marksOk && j < nfd.size(); ++j)
            marksOk = f->glyph(nfd.at(j).unicode()) != 0;
        if (bg && marksOk && (isMono || c.g == 0)) {
            c.adv = (in->advance(bg) + trak) * scale;
            c.fr = hlpfs_fallbackRuns(E, k, s, true, FbNone, 0);
        } else {
            // the font Chrome falls back to (per character), with its own hmtx + trak advance
            const int tf = nfd.size() == (QChar::requiresSurrogates(base) ? 2 : 1) ? chromeFallbackFont(base, isMono)
                                                                                   : int(FbNone);
            Inst* fi = tf != FbNone ? E.fallbackInst(tf) : nullptr;
            const quint32 tg = fi ? fi->face->glyph(base) : 0;
            if (tg) {
                c.adv = (fi->advance(tg) + Engine::trakValue(*fi->face, k.px)) * k.px * fallbackScale(tf, k.px) /
                        float(fi->face->upem);
            } else {
                const float ex = hlpfs_emojiPx(base, k.px);
                c.adv = ex > 0.0f ? ex : E.fallbackAdvance(k, s);
            }
            c.fr = hlpfs_fallbackRuns(E, k, s, false, tg ? tf : int(FbNone), tg);
            if (!tg && hlpfs_emojiPx(base, k.px) <= 0.0f) {
                const float hw = c.fr.size() == 1 && c.fr[0].glyphs.size() == 1
                                     ? hmtxAdvance(c.fr[0].font, c.fr[0].glyphs[0])
                                     : -1.0f;
                if (hw >= 0.0f)
                    c.adv = hw;
            }
        }
        c.g = 0;
        c.fb = true;
    }

    // 3. GPOS kern (runs of primary glyphs only; marks are inside clusters already)
    if (!f->kernSubtables.isEmpty()) {
        for (int i = 0; i + 1 < cls.size(); ++i) {
            if (cls[i].fb || cls[i + 1].fb || !cls[i].g || !cls[i + 1].g)
                continue;
            if (f->isMark(cls[i].g) || f->isMark(cls[i + 1].g))
                continue;
            const float kv = in->pair(cls[i].g, cls[i + 1].g);
            if (kv != 0.0f)
                cls[i].adv += kv * scale;
        }
    }

    // 4. pen positions + runs
    float pen = 0.0f;
    int slot = 0;
    int ci = 0;
    for (int i = 0; i < n; ++i) {
        while (ci < cls.size() && cls[ci].to <= i)
            ++ci;
        out->x[i] = pen;
        out->clus[i] = quint16(std::min(slot, 65535));
        if (ci < cls.size() && cls[ci].from == i) {
            pen += cls[ci].adv;
            ++slot;
        }
    }
    out->x[n] = pen;
    out->clus[n] = quint16(std::min(slot, 65535));

    Shaped::Run cur;
    bool open = false;
    for (const Cl& c : cls) {
        if (c.fb) {
            if (open) {
                out->runs.push_back(cur);
                open = false;
            }
            for (Shaped::Run r : c.fr) { // one run per font the cluster needs
                r.from = c.from;
                r.to = c.to;
                out->runs.push_back(r);
            }
            continue;
        }
        if (!open) {
            cur = Shaped::Run();
            cur.from = c.from;
            open = true;
        }
        cur.to = c.to;
        cur.glyphs.push_back(c.g);
        cur.gx.push_back(out->x[c.from]);
        cur.gc.push_back(c.from);
    }
    if (open)
        out->runs.push_back(cur);
    ++E.shapeCount;
    return out;
}

} // namespace

VMetrics vmetrics(const FontKey& k) {
    Engine& E = hlpfs_engine();
    Face* f = E.face(k);
    const float s = k.px / float(f->upem);
    VMetrics m;
    m.ascent = hlpfs_roundHalf(f->asc * s);
    m.descent = hlpfs_roundHalf(f->desc * s);
    m.lineGap = hlpfs_roundHalf(f->gap * s);
    return m;
}

std::shared_ptr<const Shaped> shape(const FontKey& k, const QString& text) {
    Engine& E = hlpfs_engine();
    auto& m = E.shapes[k];
    auto it = m.constFind(text);
    if (it != m.constEnd())
        return *it;
    if (E.shapeCount > 60000)
        trimShapeCache();
    std::shared_ptr<const Shaped> s = hlpfs_shape(k, text);
    E.shapes[k].insert(text, s);
    return s;
}

void trimShapeCache() {
    Engine& E = hlpfs_engine();
    E.shapes.clear();
    E.fallbackAdv.clear();
    E.fallbackRuns.clear();
    E.shapeCount = 0;
}

namespace {

bool hlpfs_isColorFont(const QRawFont& f) {
    return f.familyName().contains(QLatin1String("Emoji"), Qt::CaseInsensitive);
}

} // namespace

QVector<QPointF> textIntercepts(const FontKey& k, const Shaped& s, int from, int to, float ls, float y0, float y1) {
    QVector<QPointF> out;
    if (from >= to)
        return out;
    Engine& E = hlpfs_engine();
    const float x0 = s.x[from];
    const int s0 = s.clus[from];
    QPainterPath band;
    band.addRect(QRectF(-1e5, double(y0), 2e5, double(y1 - y0)));
    const auto add = [&](const QRawFont& f, quint32 g, QPointF at) {
        const QPainterPath gp = f.pathForGlyph(g);
        if (gp.isEmpty())
            return;
        const QPainterPath hit = gp.translated(at).intersected(band);
        if (hit.isEmpty())
            return;
        const QRectF b = hit.boundingRect();
        if (b.width() > 0.0)
            out.push_back(QPointF(b.left(), b.right()));
    };
    for (const Shaped::Run& r : s.runs) {
        if (r.to <= from || r.from >= to)
            continue;
        if (r.fallback) {
            if (r.glyphs.isEmpty() || !r.font.isValid() || hlpfs_isColorFont(r.font))
                continue;
            const double px = double(s.x[r.from] - x0 + ls * float(s.clus[r.from] - s0));
            for (int i = 0; i < r.glyphs.size(); ++i)
                add(r.font, r.glyphs[i], QPointF(px + r.fpos[i].x(), r.fpos[i].y()));
            continue;
        }
        for (int i = 0; i < r.glyphs.size(); ++i) {
            const int c = r.gc[i];
            if (c < from || c >= to)
                continue;
            add(E.paintFont(k), r.glyphs[i], QPointF(double(r.gx[i] - x0 + ls * float(s.clus[c] - s0)), 0.0));
        }
    }
    return out;
}

void drawShaped(QPainter& p, const FontKey& k, const Shaped& s, int from, int to, QPointF origin, float ls,
                const QColor& color, float yFrac) {
    if (from >= to)
        return;
    Engine& E = hlpfs_engine();
    const float x0 = s.x[from];
    const int s0 = s.clus[from];
    // Collect the runs: monochrome glyph runs go through the Chrome-coverage blit, colour glyphs
    // (emoji) and Qt-shaped leftovers are drawn directly.
    QVector<QGlyphRun> mono, colour;
    QVector<QPair<QPointF, QString>> texts;
    // Skia places a glyph at x rounded to the nearest quarter device pixel (+1/8, floor to 1/4); Qt
    // floors to its own subpixel grid. Snapping the pen x first makes both land on Chrome's quarter.
    const QTransform D = p.deviceTransform();
    const bool quarter = D.type() <= QTransform::TxScale && D.m11() > 0.0;
    const auto qx = [&](double x) {
        if (!quarter)
            return x;
        const double dev = x * D.m11() + D.dx();
        return (std::floor((dev + 0.125) * 4.0) / 4.0 - D.dx()) / D.m11();
    };
    // A colour (bitmap) glyph lands on a whole pixel: the quarter-snapped x rounded half up — Chrome
    // moves 🇻🇳 one pixel right from fraction .375 on (not at .34375), 9–14px alike (measured 27/09);
    // Qt rounds the raw x instead (829.4 → 829, Chrome 830).
    const auto cx = [&](double x) {
        if (!quarter)
            return x;
        const double dev = x * D.m11() + D.dx();
        return (std::floor(std::floor((dev + 0.125) * 4.0) / 4.0 + 0.5) - D.dx()) / D.m11();
    };
    double xmin = std::numeric_limits<double>::max(), xmax = std::numeric_limits<double>::lowest();
    const auto extend = [&](const QVector<QPointF>& pos) {
        for (const QPointF& q : pos) {
            xmin = std::min(xmin, q.x());
            xmax = std::max(xmax, q.x());
        }
    };
    for (const Shaped::Run& r : s.runs) {
        if (r.to <= from || r.from >= to)
            continue;
        if (r.fallback) {
            const double px = double(origin.x()) + double(s.x[r.from] - x0 + ls * float(s.clus[r.from] - s0));
            if (r.glyphs.isEmpty() || !r.font.isValid()) {
                texts.push_back({QPointF(px, origin.y()), s.text.mid(r.from, r.to - r.from)});
                continue;
            }
            QVector<QPointF> pos;
            pos.reserve(r.fpos.size());
            const bool isColour = hlpfs_isColorFont(r.font);
            // each glyph's y rounded from Chrome's text origin (a mark's offset is fractional)
            for (const QPointF& o : r.fpos)
                pos.push_back(isColour ? QPointF(cx(px + o.x()), origin.y() + o.y())
                                       : QPointF(qx(px + o.x()),
                                                 origin.y() + std::floor(double(yFrac) + o.y() + 0.5)));
            QGlyphRun run;
            run.setRawFont(r.font);
            run.setGlyphIndexes(r.glyphs);
            run.setPositions(pos);
            if (isColour) {
                colour.push_back(run);
            } else {
                extend(pos);
                mono.push_back(run);
            }
            continue;
        }
        QVector<quint32> gl;
        QVector<QPointF> pos;
        gl.reserve(r.glyphs.size());
        pos.reserve(r.glyphs.size());
        for (int i = 0; i < r.glyphs.size(); ++i) {
            const int c = r.gc[i];
            if (c < from || c >= to)
                continue;
            gl.push_back(r.glyphs[i]);
            pos.push_back(QPointF(qx(double(origin.x()) + double(r.gx[i] - x0 + ls * float(s.clus[c] - s0))), origin.y()));
        }
        if (gl.isEmpty())
            continue;
        QGlyphRun run;
        run.setRawFont(E.paintFont(k));
        run.setGlyphIndexes(gl);
        run.setPositions(pos);
        extend(pos);
        mono.push_back(run);
    }
    p.save();
    p.setPen(color);
    if (!mono.isEmpty()) {
        // generous glyph box: stacked Vietnamese marks above caps, descenders + dot below, overhang
        const double em = double(k.px);
        const QRectF box(xmin - em, double(origin.y()) - 1.6 * em - 2.0, xmax - xmin + 3.0 * em, 2.2 * em + 4.0);
        const auto drawRuns = [&mono](QPainter& t) {
            for (const QGlyphRun& run : mono)
                t.drawGlyphRun(QPointF(0, 0), run);
        };
        if (!blitGlyphRuns(p, mono, color, box))
            drawRuns(p);
    }
    if (!colour.isEmpty() && !blitColourGlyphRuns(p, colour))
        for (const QGlyphRun& run : colour)
            p.drawGlyphRun(QPointF(0, 0), run);
    if (!texts.isEmpty()) {
        p.setFont(qfontFor(k));
        for (const auto& t : texts)
            p.drawText(t.first, t.second);
    }
    p.restore();
}

} // namespace fincept::screens::hlp::detail
