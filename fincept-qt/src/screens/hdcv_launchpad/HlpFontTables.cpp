// src/screens/hdcv_launchpad/HlpFontTables.cpp
// Launchpad text engine — OpenType table readers: ItemVariationStore deltas (HVAR / GDEF), Coverage
// and ClassDef lookups, GPOS pair kerning (formats 1 and 2, extension lookups), fvar/avar axis
// normalisation input, hmtx advances. Arithmetic follows HarfBuzz so advances equal Chrome's.
#include "screens/hdcv_launchpad/HlpFont_p.h"

#include <algorithm>
#include <cmath>

namespace fincept::screens::hlp::detail {

namespace {

// ---- OpenType helpers ------------------------------------------------------------------------
int hlpft_coverage(const Tbl& t, int cov, quint32 g) {
    const int fmt = t.u16(cov);
    if (fmt == 1) {
        int lo = 0, hi = int(t.u16(cov + 2)) - 1;
        while (lo <= hi) {
            const int mid = (lo + hi) / 2;
            const quint32 v = t.u16(cov + 4 + mid * 2);
            if (v == g)
                return mid;
            if (v < g)
                lo = mid + 1;
            else
                hi = mid - 1;
        }
        return -1;
    }
    if (fmt == 2) {
        int lo = 0, hi = int(t.u16(cov + 2)) - 1;
        while (lo <= hi) {
            const int mid = (lo + hi) / 2;
            const int r = cov + 4 + mid * 6;
            const quint32 s = t.u16(r), e = t.u16(r + 2);
            if (g < s)
                hi = mid - 1;
            else if (g > e)
                lo = mid + 1;
            else
                return int(t.u16(r + 4) + (g - s));
        }
    }
    return -1;
}

int hlpft_classDef(const Tbl& t, int cd, quint32 g) {
    const int fmt = t.u16(cd);
    if (fmt == 1) {
        const quint32 start = t.u16(cd + 2), cnt = t.u16(cd + 4);
        if (g >= start && g < start + cnt)
            return t.u16(cd + 6 + int(g - start) * 2);
        return 0;
    }
    if (fmt == 2) {
        int lo = 0, hi = int(t.u16(cd + 2)) - 1;
        while (lo <= hi) {
            const int mid = (lo + hi) / 2;
            const int r = cd + 4 + mid * 6;
            const quint32 s = t.u16(r), e = t.u16(r + 2);
            if (g < s)
                hi = mid - 1;
            else if (g > e)
                lo = mid + 1;
            else
                return t.u16(r + 4);
        }
    }
    return 0;
}

int hlpft_popcount(int v) {
    int c = 0;
    for (; v; v &= v - 1)
        ++c;
    return c;
}

} // namespace

float VarStore::regionScalar(int regionList, int axisCount, int region, const QVector<int>& coords) const {
    float v = 1.0f;
    const int rec = regionList + 4 + region * axisCount * 6;
    for (int a = 0; a < axisCount; ++a) {
        const int o = rec + a * 6;
        const int start = t->s16(o), peak = t->s16(o + 2), end = t->s16(o + 4);
        const int coord = a < coords.size() ? coords[a] : 0;
        float f = 1.0f;
        if (peak == 0 || coord == peak)
            f = 1.0f;
        else if (coord == 0)
            f = 0.0f;
        else if (start > peak || peak > end)
            f = 1.0f;
        else if (start < 0 && end > 0 && peak != 0)
            f = 1.0f;
        else if (coord <= start || end <= coord)
            f = 0.0f;
        else if (coord < peak)
            f = float(coord - start) / float(peak - start);
        else
            f = float(end - coord) / float(end - peak);
        if (f == 0.0f)
            return 0.0f;
        v *= f;
    }
    return v;
}

float VarStore::delta(int outer, int inner, const QVector<int>& coords) const {
    if (!valid() || coords.isEmpty())
        return 0.0f;
    if (t->u16(base) != 1)
        return 0.0f;
    const int regionList = base + int(t->u32(base + 2));
    const int dataCount = t->u16(base + 6);
    if (outer < 0 || outer >= dataCount)
        return 0.0f;
    const int vd = base + int(t->u32(base + 8 + outer * 4));
    const int itemCount = t->u16(vd);
    const int wordRaw = t->u16(vd + 2);
    const bool longWords = (wordRaw & 0x8000) != 0;
    const int wordCount = wordRaw & 0x7fff;
    const int regionCount = t->u16(vd + 4);
    if (inner < 0 || inner >= itemCount)
        return 0.0f;
    const int axisCount = t->u16(regionList);
    const int bigSz = longWords ? 4 : 2, smallSz = longWords ? 2 : 1;
    const int rowSize = wordCount * bigSz + (regionCount - wordCount) * smallSz;
    const int row = vd + 6 + regionCount * 2 + inner * rowSize;
    float sum = 0.0f;
    for (int r = 0; r < regionCount; ++r) {
        int d = 0;
        if (r < wordCount)
            d = longWords ? t->s32(row + r * 4) : t->s16(row + r * 2);
        else {
            const int o = row + wordCount * bigSz + (r - wordCount) * smallSz;
            d = longWords ? t->s16(o) : t->s8(o);
        }
        if (d == 0)
            continue;
        const int region = t->u16(vd + 6 + r * 2);
        const float s = regionScalar(regionList, axisCount, region, coords);
        sum += s * float(d);
    }
    return sum;
}

quint32 Face::glyph(quint32 cp) {
    auto it = cmap.constFind(cp);
    if (it != cmap.constEnd())
        return *it;
    QChar buf[2];
    int len = 0;
    if (QChar::requiresSurrogates(cp)) {
        buf[0] = QChar(QChar::highSurrogate(cp));
        buf[1] = QChar(QChar::lowSurrogate(cp));
        len = 2;
    } else {
        buf[0] = QChar(char16_t(cp));
        len = 1;
    }
    quint32 gl[2] = {0, 0};
    int ng = 2;
    if (!raw.glyphIndexesForChars(buf, len, gl, &ng))
        gl[0] = 0;
    cmap.insert(cp, gl[0]);
    return gl[0];
}

bool Face::isMark(quint32 g) const {
    return glyphClassDef && hlpft_classDef(gdef, glyphClassDef, g) == 3;
}

bool Face::glyphBounds(quint32 g, QRectF& out) {
    if (locaFormat == -1) {
        const QByteArray head = raw.fontTable("head");
        glyf.set(raw.fontTable("glyf"));
        loca.set(raw.fontTable("loca"));
        locaFormat = head.size() >= 54 && glyf.n > 0 && loca.n > 0
                         ? int(qint16((uchar(head[50]) << 8) | uchar(head[51])))
                         : -2;
    }
    if (locaFormat < 0)
        return false;
    const int o0 = locaFormat ? int(loca.u32(int(g) * 4)) : int(loca.u16(int(g) * 2)) * 2;
    const int o1 = locaFormat ? int(loca.u32(int(g) * 4 + 4)) : int(loca.u16(int(g) * 2 + 2)) * 2;
    if (o1 - o0 < 10 || !glyf.ok(o0, 10)) { // empty glyph (space): no ink
        out = QRectF();
        return true;
    }
    const float xMin = glyf.s16(o0 + 2), yMin = glyf.s16(o0 + 4), xMax = glyf.s16(o0 + 6), yMax = glyf.s16(o0 + 8);
    out = QRectF(xMin, yMin, xMax - xMin, yMax - yMin);
    return true;
}

void initFace(Face& f, const QFont& qf) {
    initFace(f, QRawFont::fromFont(qf));
}

void initFace(Face& f, const QRawFont& raw) {
    f.raw = raw;
    auto tab = [&](const char* tag) { return f.raw.fontTable(tag); };
    f.hhea.set(tab("hhea"));
    f.hmtx.set(tab("hmtx"));
    QByteArray head = tab("head");
    if (head.size() >= 20)
        f.upem = (uchar(head[18]) << 8) | uchar(head[19]);
    if (f.upem <= 0)
        f.upem = 2048;
    f.numH = f.hhea.u16(34);
    f.asc = f.hhea.s16(4);
    f.desc = -f.hhea.s16(6);
    f.gap = f.hhea.s16(8);
    if (f.hhea.n < 36) { // fall back to Qt's metrics
        const float s = float(f.upem) / float(f.raw.pixelSize() > 0 ? f.raw.pixelSize() : 1.0);
        f.asc = float(f.raw.ascent()) * s;
        f.desc = float(f.raw.descent()) * s;
        f.gap = float(f.raw.leading()) * s;
    }
    f.hvar.set(tab("HVAR"));
    f.gpos.set(tab("GPOS"));
    f.gdef.set(tab("GDEF"));
    f.trak.set(tab("trak"));
    f.fvar.set(tab("fvar"));
    f.avar.set(tab("avar"));

    // fvar axes
    if (f.fvar.n > 16) {
        const int axesOff = f.fvar.u16(4), count = f.fvar.u16(8), size = f.fvar.u16(10);
        for (int i = 0; i < count; ++i) {
            const int o = axesOff + i * size;
            f.axes.push_back({f.fvar.u32(o), f.fvar.fixed(o + 4), f.fvar.fixed(o + 8), f.fvar.fixed(o + 12)});
        }
    }
    // avar segment maps
    if (f.avar.n > 8) {
        const int count = f.avar.u16(6);
        int o = 8;
        for (int a = 0; a < count; ++a) {
            const int pc = f.avar.u16(o);
            o += 2;
            QVector<QPair<int, int>> m;
            for (int i = 0; i < pc; ++i, o += 4)
                m.push_back({f.avar.s16(o), f.avar.s16(o + 2)});
            f.avarMaps.push_back(m);
        }
    }
    // HVAR
    if (f.hvar.n > 20) {
        f.hvarStore = {&f.hvar, int(f.hvar.u32(4))};
        f.hvarMap = int(f.hvar.u32(8));
    }
    // GDEF
    if (f.gdef.n > 12) {
        f.glyphClassDef = f.gdef.u16(4);
        const quint32 ver = f.gdef.u32(0);
        if (ver >= 0x00010003 && f.gdef.n >= 18) {
            const int vs = int(f.gdef.u32(14));
            if (vs)
                f.gdefStore = {&f.gdef, vs};
        }
    }
    // GPOS kern lookups (script latn → DFLT, default LangSys)
    if (f.gpos.n > 10) {
        const Tbl& g = f.gpos;
        const int scriptList = g.u16(4), featureList = g.u16(6), lookupList = g.u16(8);
        int langSys = 0;
        for (const quint32 want : {0x6c61746eu /*latn*/, 0x44464c54u /*DFLT*/}) {
            const int sc = g.u16(scriptList);
            for (int i = 0; i < sc && !langSys; ++i) {
                const int r = scriptList + 2 + i * 6;
                if (g.u32(r) != want)
                    continue;
                const int script = scriptList + g.u16(r + 4);
                if (g.u16(script))
                    langSys = script + g.u16(script);
            }
            if (langSys)
                break;
        }
        QVector<int> lookups;
        if (langSys) {
            const int fc = g.u16(langSys + 4);
            for (int i = 0; i < fc; ++i) {
                const int fi = g.u16(langSys + 6 + i * 2);
                const int fr = featureList + 2 + fi * 6;
                if (g.u32(fr) != 0x6b65726eu /*kern*/)
                    continue;
                const int feat = featureList + g.u16(fr + 4);
                const int lc = g.u16(feat + 2);
                for (int j = 0; j < lc; ++j)
                    lookups.push_back(g.u16(feat + 4 + j * 2));
            }
        }
        std::sort(lookups.begin(), lookups.end());
        lookups.erase(std::unique(lookups.begin(), lookups.end()), lookups.end());
        for (const int li : lookups) {
            const int lk = lookupList + g.u16(lookupList + 2 + li * 2);
            const int type = g.u16(lk), flag = g.u16(lk + 2), sc = g.u16(lk + 4);
            f.kernLookupStart.push_back(f.kernSubtables.size());
            f.kernLookupFlag.push_back(quint16(flag));
            for (int s = 0; s < sc; ++s) {
                int st = lk + g.u16(lk + 6 + s * 2);
                int stType = type;
                if (type == 9) {
                    stType = g.u16(st + 2);
                    st = st + int(g.u32(st + 4));
                }
                if (stType == 2)
                    f.kernSubtables.push_back(st);
            }
        }
        f.kernLookupStart.push_back(f.kernSubtables.size());
    }
}

float Inst::advance(quint32 g) {
    auto it = adv.constFind(g);
    if (it != adv.constEnd())
        return *it;
    const Face& f = *face;
    float a = 0.0f;
    if (f.numH > 0) {
        const int i = int(std::min<quint32>(g, quint32(f.numH - 1)));
        a = f.hmtx.u16(i * 4);
    }
    if (f.hvarStore.valid() && !coords.isEmpty()) {
        int outer = 0, inner = int(g);
        if (f.hvarMap) {
            const Tbl& t = f.hvar;
            const int m = f.hvarMap;
            const int fmt = t.d[m];
            const int entryFormat = t.d[m + 1];
            const quint32 mapCount = fmt == 0 ? t.u16(m + 2) : t.u32(m + 2);
            const int dataOff = m + (fmt == 0 ? 4 : 6);
            const int esz = ((entryFormat & 0x30) >> 4) + 1;
            const int innerBits = (entryFormat & 0x0f) + 1;
            quint32 idx = std::min<quint32>(g, mapCount ? mapCount - 1 : 0);
            quint32 v = 0;
            for (int b = 0; b < esz; ++b)
                v = (v << 8) | (t.ok(dataOff + int(idx) * esz + b, 1) ? t.d[dataOff + int(idx) * esz + b] : 0);
            outer = int(v >> innerBits);
            inner = int(v & ((1u << innerBits) - 1));
        }
        a += std::round(f.hvarStore.delta(outer, inner, coords)); // CoreText/HarfBuzz: whole units
    }
    adv.insert(g, a);
    return a;
}

/// XAdvance (+ VariationIndex delta) of a ValueRecord; `base` = table its device offsets are relative to.
float Inst::valueXAdvance(const Tbl& t, int base, int rec, int vf) const {
    float v = 0.0f;
    int o = rec;
    for (int bit = 1; bit <= 0x80; bit <<= 1) {
        if (!(vf & bit))
            continue;
        if (bit == 0x04)
            v += t.s16(o);
        if (bit == 0x40) {
            const int dev = t.u16(o);
            if (dev && face->gdefStore.valid()) {
                const int d = base + dev;
                if (t.u16(d + 4) == 0x8000)
                    v += face->gdefStore.delta(t.u16(d), t.u16(d + 2), coords);
            }
        }
        o += 2;
    }
    return v;
}

/// Kerning of pair (a,b) in lookup `li`; NaN when no subtable matched.
float Inst::pairInLookup(int li, quint32 a, quint32 b) const {
    const Face& f = *face;
    const Tbl& t = f.gpos;
    for (int s = f.kernLookupStart[li]; s < f.kernLookupStart[li + 1]; ++s) {
        const int st = f.kernSubtables[s];
        const int fmt = t.u16(st);
        const int ci = hlpft_coverage(t, st + t.u16(st + 2), a);
        if (ci < 0)
            continue;
        const int vf1 = t.u16(st + 4), vf2 = t.u16(st + 6);
        const int sz1 = hlpft_popcount(vf1 & 0xff) * 2, sz2 = hlpft_popcount(vf2 & 0xff) * 2;
        if (fmt == 1) {
            if (ci >= t.u16(st + 8))
                continue;
            const int ps = st + t.u16(st + 10 + ci * 2);
            const int recSize = 2 + sz1 + sz2;
            int lo = 0, hi = int(t.u16(ps)) - 1;
            while (lo <= hi) {
                const int mid = (lo + hi) / 2;
                const int r = ps + 2 + mid * recSize;
                const quint32 sg = t.u16(r);
                if (sg == b)
                    return valueXAdvance(t, ps, r + 2, vf1); // device offsets: from the PairSet
                if (sg < b)
                    lo = mid + 1;
                else
                    hi = mid - 1;
            }
            continue; // format 1 without the pair does not apply
        }
        if (fmt == 2) {
            const int c1 = hlpft_classDef(t, st + t.u16(st + 8), a);
            const int c2 = hlpft_classDef(t, st + t.u16(st + 10), b);
            const int n1 = t.u16(st + 12), n2 = t.u16(st + 14);
            if (c1 >= n1 || c2 >= n2)
                continue;
            const int r = st + 16 + (c1 * n2 + c2) * (sz1 + sz2);
            return valueXAdvance(t, st, r, vf1);
        }
    }
    return std::nanf("");
}

/// Sum of kern adjustments for pair (a,b) over all kern lookups (design units).
float Inst::pair(quint32 a, quint32 b) {
    const quint64 key = (quint64(a) << 32) | b;
    auto it = kern.constFind(key);
    if (it != kern.constEnd())
        return *it;
    float sum = 0.0f;
    const int nl = int(face->kernLookupStart.size()) - 1;
    for (int li = 0; li < nl; ++li) {
        const float v = pairInLookup(li, a, b);
        if (!std::isnan(v))
            sum += v;
    }
    kern.insert(key, sum);
    return sum;
}

} // namespace fincept::screens::hlp::detail
