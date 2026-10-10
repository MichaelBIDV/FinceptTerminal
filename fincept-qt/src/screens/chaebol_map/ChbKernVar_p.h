#pragma once
// ChbKernVar_p.h — kerning deltas of variable fonts. Included by ChbText.cpp only (no own translation unit).
//
// Qt shapes with its bundled HarfBuzz, which reads GPOS from the raw font tables WITHOUT the variation coordinates
// set on the QFont (advances come from CoreText and do vary). Chrome's HarfBuzz applies the full variation, so
// kerning pairs of Source Serif 4 (opsz pinned at 14, default 20) and Cormorant Garamond (default wght 300) differ
// by up to ~0.1 px per pair (measured 27/09: "AV To Ya" Source Serif 16/700 −0.92 px, table columns shift by
// 0.4 px). Qt already applied the default-instance values, so only the variation deltas are added here:
// GPOS 'kern' PairPos (types 2, 9→2) value-record XAdvance device tables of VariationIndex format, evaluated on the
// GDEF ItemVariationStore at the fvar/avar-normalized coordinates, following HarfBuzz (F2DOT14 rounding, region
// evaluation, PairSet-relative device offsets in format 1). Chained contextual kerning and mark anchors are not
// covered (their variation deltas are below 0.05 px for the page's text).
#include <QByteArray>
#include <QHash>
#include <QRawFont>

#include <cmath>
#include <memory>
#include <vector>

namespace fincept::screens::chb {

class ChbkFace {
  public:
    /// Face data for `raw` (cached per font file); nullptr when the font has no variable kerning to correct.
    static const ChbkFace* get(const QRawFont& raw) {
        static QHash<QByteArray, std::shared_ptr<ChbkFace>> cache;
        const QByteArray head = raw.fontTable("head");
        const QByteArray key = raw.familyName().toUtf8() + '|' + head.mid(8, 4) + head.mid(28, 8); // checkSumAdj + created
        auto it = cache.find(key);
        if (it == cache.end()) {
            auto f = std::make_shared<ChbkFace>();
            if (!f->load(raw)) f.reset();
            it = cache.insert(key, f);
        }
        return it.value().get();
    }

    /// Normalized F2DOT14 coordinates for the user-space axis values (wght/opsz; < 0 = axis default).
    std::vector<int> coords(float wght, float opsz) const {
        std::vector<int> c(axes.size(), 0);
        for (size_t i = 0; i < axes.size(); ++i) {
            const Axis& a = axes[i];
            float v = a.tag == tag("wght") ? wght : a.tag == tag("opsz") ? opsz : -1.0f;
            if (v < 0) continue;
            v = std::clamp(v, a.min, a.max);
            float n = 0;
            if (v < a.def) n = (v - a.def) / (a.def - a.min);
            else if (v > a.def) n = (v - a.def) / (a.max - a.def);
            int q = int(std::lround(n * 16384.0f));
            if (i < avar.size()) q = avar_map(avar[i], q);
            c[i] = q;
        }
        return c;
    }

    /// Advance deltas (font units) for a glyph sequence in visual order: out[i] is added to glyph i's advance.
    void deltas(const std::vector<quint32>& g, const std::vector<int>& co, std::vector<float>* out) const {
        out->assign(g.size(), 0.0f);
        bool any = false;
        for (int c : co) any = any || c != 0;
        if (!any) return;
        for (const Lookup& lk : lookups) {
            const bool skipMarks = (lk.flag & 0x0008) || (lk.flag & 0x0010);
            auto ignored = [&](size_t k) { return skipMarks && glyph_class(g[k]) == 3; };
            size_t i = 0;
            while (i < g.size()) {
                if (ignored(i)) { ++i; continue; }
                size_t j = i + 1;
                while (j < g.size() && ignored(j)) ++j;
                if (j >= g.size()) break;
                size_t next = j;
                for (unsigned st : lk.subtables) {
                    float d1 = 0, d2 = 0;
                    bool skipSecond = false;
                    if (pair(st, quint16(g[i]), quint16(g[j]), co, &d1, &d2, &skipSecond)) {
                        (*out)[i] += d1;
                        (*out)[j] += d2;
                        if (skipSecond) next = j + 1;
                        break;
                    }
                }
                i = next;
            }
        }
    }

    int upem = 1000;

  private:
    struct Axis { quint32 tag; float min, def, max; };
    struct Lookup { quint16 flag; std::vector<unsigned> subtables; };
    QByteArray gpos, gdef;
    std::vector<Axis> axes;
    std::vector<std::vector<std::pair<int, int>>> avar;
    std::vector<Lookup> lookups;
    unsigned glyphClassDef = 0, varStore = 0;

    static constexpr quint32 tag(const char (&s)[5]) {
        return (quint32(quint8(s[0])) << 24) | (quint32(quint8(s[1])) << 16) | (quint32(quint8(s[2])) << 8) | quint8(s[3]);
    }
    static quint16 u16(const QByteArray& b, unsigned o) {
        return o + 2 <= unsigned(b.size()) ? quint16((quint8(b[o]) << 8) | quint8(b[o + 1])) : 0;
    }
    static qint16 s16(const QByteArray& b, unsigned o) { return qint16(u16(b, o)); }
    static quint32 u32(const QByteArray& b, unsigned o) { return (quint32(u16(b, o)) << 16) | u16(b, o + 2); }
    static float fixed(const QByteArray& b, unsigned o) { return float(qint32(u32(b, o))) / 65536.0f; }

    static int avar_map(const std::vector<std::pair<int, int>>& m, int v) {
        if (m.size() < 2) return m.empty() ? v : v - m[0].first + m[0].second;
        if (v <= m[0].first) return v - m[0].first + m[0].second;
        size_t i = 1;
        while (i < m.size() - 1 && v > m[i].first) ++i;
        if (v >= m[i].first) return v - m[i].first + m[i].second;
        if (m[i - 1].first == m[i].first) return m[i - 1].second;
        const int den = m[i].first - m[i - 1].first;
        return int(std::lround(m[i - 1].second + float(m[i].second - m[i - 1].second) * float(v - m[i - 1].first) / float(den)));
    }

    bool load(const QRawFont& raw) {
        const QByteArray fvar = raw.fontTable("fvar");
        gpos = raw.fontTable("GPOS");
        gdef = raw.fontTable("GDEF");
        if (fvar.size() < 16 || gpos.size() < 10 || gdef.size() < 18) return false;
        const QByteArray head = raw.fontTable("head");
        upem = std::max(16, int(u16(head, 18)));
        const unsigned axOff = u16(fvar, 4), axCount = u16(fvar, 8), axSize = u16(fvar, 10);
        for (unsigned a = 0; a < axCount; ++a) {
            const unsigned o = axOff + a * axSize;
            axes.push_back({u32(fvar, o), fixed(fvar, o + 4), fixed(fvar, o + 8), fixed(fvar, o + 12)});
        }
        const QByteArray av = raw.fontTable("avar");
        if (av.size() >= 8) {
            unsigned o = 8;
            for (unsigned a = 0; a < u16(av, 6); ++a) {
                std::vector<std::pair<int, int>> seg;
                const unsigned n = u16(av, o);
                o += 2;
                for (unsigned k = 0; k < n; ++k, o += 4) seg.emplace_back(s16(av, o), s16(av, o + 2));
                avar.push_back(std::move(seg));
            }
        }
        if (u32(gdef, 0) < 0x00010003) return false;
        glyphClassDef = u16(gdef, 4);
        varStore = u32(gdef, 14);
        if (!varStore) return false;
        // 'kern' lookups of script latn (LangSys VIT if present, else default), else DFLT
        const unsigned sl = u16(gpos, 4), fl = u16(gpos, 6), ll = u16(gpos, 8);
        unsigned langSys = 0;
        for (const quint32 want : {tag("latn"), tag("DFLT")}) {
            for (unsigned s = 0; s < u16(gpos, sl) && !langSys; ++s) {
                if (u32(gpos, sl + 2 + s * 6) != want) continue;
                const unsigned so = sl + u16(gpos, sl + 2 + s * 6 + 4);
                for (unsigned l = 0; l < u16(gpos, so + 2); ++l)
                    if (u32(gpos, so + 4 + l * 6) == tag("VIT ")) langSys = so + u16(gpos, so + 4 + l * 6 + 4);
                if (!langSys && u16(gpos, so)) langSys = so + u16(gpos, so);
            }
            if (langSys) break;
        }
        if (!langSys) return false;
        std::vector<unsigned> idx;
        for (unsigned k = 0; k < u16(gpos, langSys + 4); ++k) {
            const unsigned fi = u16(gpos, langSys + 6 + k * 2);
            if (u32(gpos, fl + 2 + fi * 6) != tag("kern")) continue;
            const unsigned fo = fl + u16(gpos, fl + 2 + fi * 6 + 4);
            for (unsigned m = 0; m < u16(gpos, fo + 2); ++m) idx.push_back(u16(gpos, fo + 4 + m * 2));
        }
        std::sort(idx.begin(), idx.end());
        idx.erase(std::unique(idx.begin(), idx.end()), idx.end());
        for (unsigned li : idx) {
            const unsigned lo = ll + u16(gpos, ll + 2 + li * 2);
            Lookup lk;
            const unsigned type = u16(gpos, lo);
            lk.flag = u16(gpos, lo + 2);
            for (unsigned s = 0; s < u16(gpos, lo + 4); ++s) {
                unsigned so = lo + u16(gpos, lo + 6 + s * 2);
                unsigned t = type;
                if (t == 9) {
                    t = u16(gpos, so + 2);
                    so += u32(gpos, so + 4);
                }
                if (t == 2) lk.subtables.push_back(so);
            }
            if (!lk.subtables.empty()) lookups.push_back(std::move(lk));
        }
        return !lookups.empty();
    }

    int coverage(unsigned o, quint16 g) const {
        const unsigned fmt = u16(gpos, o), n = u16(gpos, o + 2);
        unsigned lo = 0, hi = n;
        while (lo < hi) {
            const unsigned mid = (lo + hi) / 2;
            if (fmt == 1) {
                const quint16 v = u16(gpos, o + 4 + mid * 2);
                if (v == g) return int(mid);
                if (v < g) lo = mid + 1; else hi = mid;
            } else {
                const unsigned r = o + 4 + mid * 6;
                if (g < u16(gpos, r)) hi = mid;
                else if (g > u16(gpos, r + 2)) lo = mid + 1;
                else return int(u16(gpos, r + 4) + g - u16(gpos, r));
            }
        }
        return -1;
    }

    static unsigned class_of(const QByteArray& b, unsigned o, quint16 g) {
        if (!o) return 0;
        if (u16(b, o) == 1) {
            const unsigned start = u16(b, o + 2), n = u16(b, o + 4);
            return g >= start && g < start + n ? u16(b, o + 6 + (g - start) * 2) : 0;
        }
        unsigned lo = 0, hi = u16(b, o + 2);
        while (lo < hi) {
            const unsigned mid = (lo + hi) / 2, r = o + 4 + mid * 6;
            if (g < u16(b, r)) hi = mid;
            else if (g > u16(b, r + 2)) lo = mid + 1;
            else return u16(b, r + 4);
        }
        return 0;
    }
    unsigned glyph_class(quint32 g) const { return glyphClassDef ? class_of(gdef, glyphClassDef, quint16(g)) : 0; }

    float var_delta(unsigned outer, unsigned inner, const std::vector<int>& co) const {
        const unsigned vs = varStore;
        if (outer >= u16(gdef, vs + 6)) return 0;
        const unsigned rl = vs + u32(gdef, vs + 2);
        const unsigned axisCount = u16(gdef, rl);
        const unsigned d = vs + u32(gdef, vs + 8 + outer * 4);
        const unsigned itemCount = u16(gdef, d), wordRaw = u16(gdef, d + 2), regionCount = u16(gdef, d + 4);
        if (inner >= itemCount) return 0;
        const bool longWords = wordRaw & 0x8000;
        const unsigned words = wordRaw & 0x7FFF;
        const unsigned wsz = longWords ? 4 : 2, ssz = longWords ? 2 : 1;
        const unsigned rowSize = words * wsz + (regionCount - words) * ssz;
        const unsigned row = d + 6 + regionCount * 2 + inner * rowSize;
        float sum = 0;
        for (unsigned r = 0; r < regionCount; ++r) {
            float delta;
            if (r < words) delta = longWords ? float(qint32(u32(gdef, row + r * 4))) : float(s16(gdef, row + r * 2));
            else {
                const unsigned o = row + words * wsz + (r - words) * ssz;
                delta = longWords ? float(s16(gdef, o)) : float(qint8(quint8(o < unsigned(gdef.size()) ? gdef[o] : 0)));
            }
            if (delta == 0) continue;
            const unsigned region = u16(gdef, d + 6 + r * 2);
            float scalar = 1.0f;
            for (unsigned a = 0; a < axisCount && scalar != 0; ++a) {
                const unsigned ro = rl + 4 + (region * axisCount + a) * 6;
                const int start = s16(gdef, ro), peak = s16(gdef, ro + 2), end = s16(gdef, ro + 4);
                const int c = a < co.size() ? co[a] : 0;
                if (peak == 0 || c == peak) continue;
                if (c == 0) { scalar = 0; break; }
                if (start > peak || peak > end) continue;
                if (start < 0 && end > 0) continue;
                if (c <= start || end <= c) { scalar = 0; break; }
                scalar *= c < peak ? float(c - start) / float(peak - start) : float(end - c) / float(end - peak);
            }
            sum += scalar * delta;
        }
        return sum;
    }

    /// XAdvance device delta of the value record at `v` (format `fmt`), device offsets relative to `base`.
    float value_delta(unsigned base, unsigned v, unsigned fmt, const std::vector<int>& co) const {
        if (!(fmt & 0x40)) return 0;
        unsigned o = v;
        for (unsigned bit = 0x1; bit < 0x40; bit <<= 1)
            if (fmt & bit) o += 2;
        const unsigned dev = u16(gpos, o);
        if (!dev || u16(gpos, base + dev + 4) != 0x8000) return 0;
        return var_delta(u16(gpos, base + dev), u16(gpos, base + dev + 2), co);
    }

    static unsigned vsize(unsigned fmt) {
        unsigned n = 0;
        for (unsigned b = fmt & 0xFF; b; b >>= 1) n += b & 1;
        return n * 2;
    }

    bool pair(unsigned st, quint16 g1, quint16 g2, const std::vector<int>& co, float* d1, float* d2, bool* skip2) const {
        const unsigned fmt = u16(gpos, st);
        const int ci = coverage(st + u16(gpos, st + 2), g1);
        if (ci < 0) return false;
        const unsigned vf1 = u16(gpos, st + 4), vf2 = u16(gpos, st + 6);
        const unsigned s1 = vsize(vf1), s2 = vsize(vf2);
        *skip2 = vf2 != 0;
        if (fmt == 1) {
            if (unsigned(ci) >= u16(gpos, st + 8)) return false;
            const unsigned ps = st + u16(gpos, st + 10 + unsigned(ci) * 2);
            const unsigned rec = 2 + s1 + s2;
            unsigned lo = 0, hi = u16(gpos, ps);
            while (lo < hi) {
                const unsigned mid = (lo + hi) / 2, r = ps + 2 + mid * rec;
                const quint16 sg = u16(gpos, r);
                if (sg == g2) {
                    *d1 = value_delta(ps, r + 2, vf1, co);
                    *d2 = value_delta(ps, r + 2 + s1, vf2, co);
                    return true;
                }
                if (sg < g2) lo = mid + 1; else hi = mid;
            }
            return false;
        }
        if (fmt != 2) return false;
        const unsigned c1 = class_of(gpos, st + u16(gpos, st + 8), g1), c2 = class_of(gpos, st + u16(gpos, st + 10), g2);
        const unsigned n1 = u16(gpos, st + 12), n2 = u16(gpos, st + 14);
        if (c1 >= n1 || c2 >= n2) return false;
        const unsigned r = st + 16 + (c1 * n2 + c2) * (s1 + s2);
        *d1 = value_delta(st, r, vf1, co);
        *d2 = value_delta(st, r + s1, vf2, co);
        return true;
    }
};

} // namespace fincept::screens::chb
