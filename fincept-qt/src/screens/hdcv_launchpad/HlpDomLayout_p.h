// src/screens/hdcv_launchpad/HlpDomLayout_p.h
// PRIVATE to the Launchpad engine (HlpTheme / HlpFont* / HlpDom* / HlpView .cpp) — panel code never
// includes this. Two parts: `detail` = the text engine interface, `hlpdom` = the box engine's types
// (computed style, box tree, IFC, Layout, ViewImpl) shared by the HlpDom*.cpp files.
//
// Text measurement that reproduces Chrome-on-macOS glyph advances exactly (measured 27/09/2026,
// max error 0.01px over the 2 054 strings of the live Launchpad):
//   --sans  SF Pro (SFNS.ttf, variable): advance = hmtx + HVAR(opsz = clamp(px,17,96), wght = CSS
//           weight) + AAT `trak` track 0 at ptem = px, plus GPOS `kern` pair adjustments (+ GDEF
//           variation deltas) — this is what HarfBuzz does inside Chrome. Qt's own shaping (CoreText
//           kerning, 1/64-px truncated advances) differs by up to 1.5px per string, so we do not use it
//           for layout.
//   --mono  Menlo: every cluster is one 1233/2048 em advance (Menlo lacks some precomposed
//           Vietnamese letters; Chrome decomposes them and the zero-width marks keep the advance).
//   Chrome rounds each font's ascent/descent to the nearest 0.5px (not integers) before building
//   line boxes; vmetrics() returns those values.
// Characters the primary font cannot render go to the font CHROME picks (HlpFontFallback.cpp table,
// else Qt's cascade, which agrees elsewhere) and are shaped with Qt's HarfBuzz in that font; letters
// the primary font can compose from base + marks (Menlo: ế ủ…) keep the base advance and are drawn
// with the primary font's own AAT composition, like Chrome.
#pragma once

#include "screens/hdcv_launchpad/HlpDom.h"
#include "screens/hdcv_launchpad/HlpTheme.h"

#include <QColor>
#include <QFont>
#include <QHash>
#include <QJsonArray>
#include <QPainterPath>
#include <QPair>
#include <QPointF>
#include <QPointer>
#include <QRawFont>
#include <QRectF>
#include <QString>
#include <QVector>

#include <cmath>
#include <deque>
#include <limits>
#include <memory>

class QPainter;

namespace fincept::screens::hlp::detail {

enum class Fam : quint8 { Sans, Mono, Arial };

struct FontKey {
    Fam fam = Fam::Sans;
    float px = 12.0f;
    int weight = 400;
    bool italic = false;
    bool operator==(const FontKey& o) const {
        return fam == o.fam && px == o.px && weight == o.weight && italic == o.italic;
    }
};
size_t qHash(const FontKey& k, size_t seed = 0) noexcept;

/// Vertical metrics as Blink uses them for line layout: ascent/descent/lineGap rounded to 0.5px.
struct VMetrics {
    float ascent = 0.0f;
    float descent = 0.0f;
    float lineGap = 0.0f;
    float lineSpacing() const { return ascent + descent + lineGap; }
};
VMetrics vmetrics(const FontKey& k);

/// Result of shaping one string in one font.
struct Shaped {
    QString text;              ///< NFC-normalised text that was shaped
    QVector<float> x;          ///< size n+1: pen x before UTF-16 unit i (kerning included, letter-spacing not)
    QVector<quint16> clus;    ///< size n+1: letter-spacing clus (clusters) before unit i
    struct Run {
        int from = 0, to = 0;       ///< UTF-16 range
        bool fallback = false;      ///< one cluster in another font (or a composed mark sequence)
        QVector<quint32> glyphs;    ///< glyph ids (primary font, or `font` for a fallback run)
        QVector<float> gx;          ///< primary: glyph pen x in the string (no letter-spacing)
        QVector<int> gc;            ///< primary: UTF-16 index of each glyph (for letter-spacing)
        QRawFont font;              ///< fallback: the font Chrome draws the cluster with, at px
        QVector<QPointF> fpos;      ///< fallback: glyph offsets from the cluster pen (baseline y = 0)
    };
    QVector<Run> runs;
    float width(int from, int to, float ls) const { return x[to] - x[from] + ls * float(clus[to] - clus[from]); }
};
std::shared_ptr<const Shaped> shape(const FontKey& k, const QString& text);

/// Paint the UTF-16 range [from,to) of `s` with its pen origin (x of `from`, baseline y) at `origin`.
/// `yFrac`: Chrome's (half-pixel) text origin minus origin.y — Skia rounds every glyph's y on its own,
/// so a mark raised by a fraction lands on the row Chrome gives it only when the fraction is known.
void drawShaped(QPainter& p, const FontKey& k, const Shaped& s, int from, int to, QPointF origin, float ls,
                const QColor& color, float yFrac = 0.0f);

/// QFont for a key (letter-spacing not applied) — used for fallback text and embedded widgets.
QFont qfontFor(const FontKey& k);

/// Drop cached shaping results (called when the cache grows too large).
void trimShapeCache();

/// SkTextBlob::getIntercepts for [from,to) of `s`: per glyph, the x-range (relative to the pen origin
/// of `from`) where its outline crosses the band y0..y1 (baseline-relative, y down) — the stripes
/// text-decoration-skip-ink cuts out of an underline.
QVector<QPointF> textIntercepts(const FontKey& k, const Shaped& s, int from, int to, float ls, float y0, float y1);

} // namespace fincept::screens::hlp::detail

// ============================================================================================
// Box engine internals (HlpDom*.cpp / HlpView.cpp)
// ============================================================================================
namespace fincept::screens::hlp::hlpdom {


using detail::Fam;
using detail::FontKey;
using detail::Shaped;
using detail::VMetrics;

constexpr float kInf = std::numeric_limits<float>::infinity();
constexpr float kEps = 1.0f / 128.0f;
constexpr float kScrollbar = 7.0f; // ::-webkit-scrollbar{width:7px;height:7px}
const QChar kObj(0xFFFC);

// Chrome on this Mac lays out at an internal zoom of 2 (Retina) even under DPR-1 emulation, so its
// LayoutUnit (1/64 of a zoomed px) is 1/128 CSS px and every integer Floor()/Round() of LayoutNG lands
// on half CSS pixels (measured: 12px/1.45 → line box 17.3984375, baseline at 13).
constexpr float kLU = 128.0f;
inline float luFloor(float v) {
    return std::floor(v * kLU + 1e-3f) / kLU;
}
inline float luCeil(float v) {
    return std::ceil(v * kLU - 1e-3f) / kLU;
}
inline float halfFloor(float v) {
    return std::floor(v * 2.0f + 1e-4f) / 2.0f;
}
/// Chrome paints box edges snapped to half pixels (zoom-2 pixel snapping) and rasterises the half
/// pixel with 50% coverage; measured on 1px strips at every 1/16 offset.
inline float snap(float v) {
    return std::floor(v * 2.0f + 0.5f) / 2.0f;
}
/// Text baselines: half-pixel snap, then Skia rounds the glyph origin half-up to a whole pixel
/// (measured: baseline 32.1875 → row 32, 32.25 → 33).
inline float snapBaseline(float v) {
    return std::floor(snap(v) + 0.5f);
}

// ---- computed (inherited) style ----
struct LineH {
    quint8 kind = 1; // 0 normal · 1 factor · 2 px
    float v = 1.45f;
};

struct CS {
    FontKey font;
    VMetrics vm;
    LineH lhSpec;
    float lh = 17.390625f; // used line height (LayoutUnit)
    float ls = 0.0f;       // letter-spacing px
    bool upper = false;
    WhiteSpace ws = WhiteSpace::Normal;
    TextAlign align = TextAlign::Left;
    QColor color;
};

CS rootCS();

CS resolveCS(const Style& st, const CS& p);

/// Layout bounds of an inline box around its baseline: {above, below} (CSS 2.1 half-leading, Blink floor).
struct VB {
    float above = 0, below = 0;
};
VB inlineBounds(const CS& c);

// ---- box tree ----
enum class BK : quint8 { Block, Flex, Grid, Table, Row, Cell, Inline, Text, Br, Atomic };

struct Box;

struct IItem {
    enum T : quint8 { Text, Open, Close, Atomic, Br } t = Text;
    Box* box = nullptr;
    int start = 0, end = 0; // paragraph range (Open/Close: start == end)
    bool wrap = true;       // soft wraps allowed after characters of this item
};

struct Frag {
    Box* box = nullptr; // Text box or Atomic box
    int item = 0;
    int from = 0, to = 0; // paragraph range
    float x = 0, w = 0;   // relative to the container border box
};

struct Line {
    float top = 0, height = 0, baseline = 0; // relative to the container border box
    float left = 0, width = 0;               // content x of the line start, used width
    int from = 0, to = 0;                    // paragraph range
    QVector<Frag> frags;
    float ellX = -1; // x of the "…" (−1 none)
};

struct IFC {
    QString para;
    QVector<IItem> items;
    QVector<int> itemAt;    // paragraph index → item index (Text/Atomic/Br)
    QVector<quint8> brk;    // brk[i]=1: soft break opportunity before para[i]
    QVector<Line> lines;
    // per-layout scratch
    QVector<float> adv;     // width of para[i]
};

struct Box {
    Node* node = nullptr;
    Box* parent = nullptr;
    BK kind = BK::Block;
    const CS* cs = nullptr;
    const Style* st = nullptr;
    QVector<Box*> kids;
    std::unique_ptr<IFC> ifc;
    // text
    QString text;
    std::shared_ptr<const Shaped> shaped; // shaping run this text belongs to (shared by same-font neighbours)
    int shapedOff = 0;                     // index of text[0] inside shaped->text
    int paraStart = 0; // Text: where `text` starts in the container paragraph
    Box* container = nullptr; // Text/Inline/Atomic/Br: the IFC container
    bool custom = false, widget = false;
    bool bfcRoot = false;
    // intrinsic cache (border box)
    bool intrinsicDone = false;
    float minC = 0, maxC = 0;
    // layout (relative to parent layout box)
    float x = 0, y = 0, w = 0, h = 0;
    float ax = 0, ay = 0; // absolute (content coordinates of the view)
    float mtEff = 0;     // collapsed margins
    struct MSet {
        float pos = 0, neg = 0;
        void add(float m) {
            if (m > 0)
                pos = std::max(pos, m);
            else
                neg = std::min(neg, m);
        }
        void add(const MSet& o) {
            pos = std::max(pos, o.pos);
            neg = std::min(neg, o.neg);
        }
        float value() const { return pos + neg; }
    } mTop, mBot;
    bool selfCollapsing = false;
    float contentShiftY = 0; // table cells: vertical-align middle offset
    // table
    float halfTop = 0, halfBot = 0;
    int col = 0, span = 1;
    // inline boxes: content-area rects per line (absolute), for hit testing / dump
    QVector<QRectF> inlineRects;
    // flex/grid baseline
    float baseline = -1; // first baseline from border-box top (−1 = none)
};

struct Doc {
    std::deque<Box> boxes;
    std::deque<CS> styles;
    Box* root = nullptr;
    QVector<Box*> stickies;
    QVector<Box*> widgets;
    Box* make() {
        boxes.emplace_back();
        return &boxes.back();
    }
    const CS* cs(const CS& c) {
        styles.push_back(c);
        return &styles.back();
    }
};

bool isInlineLevel(const Box* b);

bool isWhitespace(const QString& s);

bool inlineRunIsBlank(const QVector<Box*>& run);


/// Normalise the children of a block container / flex / grid: anonymous wrappers for inline runs.
void normalizeKids(Doc& d, Box* b);

Box* build(Doc& d, Node* n, const CS& pcs, Box* parent);

void markBfc(Box* b, bool isRoot);

bool hasInlineContent(const Box* b);

QString collapseWs(const QString& s);

void buildIfcItems(IFC& f, Box* container, Box* b, bool& lastSpace);

void buildIfc(Box* b);
/// Two bare text nodes that are adjacent siblings (one text node in the web page).
bool textContinues(const Box* prev, const Box* cur);
/// Add each text item's LayoutUnit rounding (SnappedWidth) to the advance of its last character.
void snapItemWidths(const IFC& f, QVector<float>& adv);

void prepare(Box* b);


// ============================================================================================
// Layout
// ============================================================================================
struct Layout {
    explicit Layout(Doc& d) : d_(d) {}

    float contentHeight = 0;
    float overflowRight = 0;

    void run(float width);

    // ---- intrinsic sizes ----
    void intrinsic(Box* b);

    Doc& d_;

    // ---------------------------------------------------------------------------------------
    // IFC helpers
    // ---------------------------------------------------------------------------------------
    float atomicOuter(Box* a, bool useMin);

    /// advance of every paragraph position for a layout (atomics laid out shrink-to-fit in `avail`)
    void computeAdvances(Box* c, float avail);

    void ifcIntrinsic(Box* c, float& mn, float& mx);

    /// line layout of an IFC container; returns content height
    float layoutLines(Box* c, float cw, float contentX, float contentY);

    /// first (or last, for inline-block) baseline from the border-box top; −1 if none
    float firstOrLastBaseline(Box* b, bool last);

    // ---------------------------------------------------------------------------------------
    // Box layout
    // ---------------------------------------------------------------------------------------
    float usedWidth(Box* b, float cbW);

    /// Lay out `b` in a containing block of width cbW (forcedW = border-box width decided by the parent).
    void layoutBox(Box* b, float cbW, float forcedW);

    float layoutFlow(Box* b, float cw, float pl, float pt, float pb);

    // ---- flex (row) ----
    float layoutFlex(Box* b, float cw, float pl, float pt);

    // ---- grid ----
    float layoutGrid(Box* b, float cw, float pl, float pt);

    // ---- table ----
    struct TableModel {
        int nCols = 0;
        QVector<QVector<Box*>> rows; // cells per row
        QVector<float> colMin, colMax;
        QVector<bool> colFixed; ///< a single-column cell of it has a fixed width (Blink is_constrained)
    };

    float cellHPad(Box* c);

    void buildTable(Box* t, TableModel& tm);

    void cellIntrinsic(Box* cell);

    float layoutTable(Box* t, float cw, float pl, float pt);

    void layoutCell(Box* cell, float w);

    float layoutFlowCell(Box* cell, float cw, float pl, float pt);

    // ---------------------------------------------------------------------------------------
    // absolute positions
    // ---------------------------------------------------------------------------------------
    void finalize(Box* b, float ox, float oy);
};

// ============================================================================================
// HlpView state (lives in hlpdom so no using-directive leaks into other files of a unity build)
// ============================================================================================
/// a:hover underline with Blink's thickness/offset and text-decoration-skip-ink (HlpDomInline.cpp).
/// `baseY` = Chrome's half-pixel text origin, painter coordinates; [from,to) = UTF-16 range of tb->shaped.
void paintUnderline(QPainter& p, const Box* tb, int from, int to, float x, float baseY, float w, const QColor& c);

struct ViewImpl {
    HlpView* q = nullptr;
    NodeP root;
    std::unique_ptr<Doc> doc;
    float maxH = 0;
    float laidW = -1;        // layout width of the current geometry
    float contentH = 0, overflowW = 0;
    bool vbar = false, hbar = false;
    float scrollX = 0, scrollY = 0;
    QHash<int, QPair<float, float>> hcache; // layout width ×64 → (content height, overflow right)
    // interaction
    QVector<Box*> hover;      // deepest first
    Box* pressBox = nullptr;
    bool dragV = false, dragH = false;
    float dragStart = 0, dragScroll0 = 0;
    QPointF lastMouse;
    Box* customHoverBox = nullptr;
    // embedded widgets are borrowed: remember their parent so a destroyed view never deletes them
    QHash<QWidget*, QPointer<QWidget>> borrowed;
    QRectF subRect;         // setSubpixelGeometry(); empty = property "hlp_subpixel" / widget rect
    // paint-time offset of content coordinates on the page grid of the scroller's contents layer
    // (= layerOrigin(); widget pixels are Chrome's page pixels). Snapping helpers work on that grid;
    // the scroll offset is applied after snapping, like the compositor moving a rastered layer.
    float pox = 0, poy = 0;
    /// The scrollport (padding box) snapped to the half-pixel grid, widget coordinates, with the top,
    /// bottom and right edges then taken down to the whole pixel (HlpView::paintEvent) — Chrome clips a
    /// box's CONTENT there (only a .5 left edge shows half the clipped column); the root's own
    /// background/border are not clipped by it.
    QRectF contentClip;
    bool stripPass = false; ///< painting a half-covered edge strip: no root decoration, no content clip
    // keyboard focus among Node::focusable boxes (HlpDom.cpp)
    const Node* focusNode = nullptr;
    bool focusVisible = false;              ///< :focus-visible — focus came from the keyboard
    QVector<Box*> focusables() const;       ///< focusable element boxes in document order
    void focusBox(Box* b, bool visible);    ///< focus b's node (nullptr clears), scroll it into view

    void release(QWidget* w);
    /// Intersect the painter's clip with the whole pixels inside contentClip; the painter is in content
    /// coordinates (translated by paintOrigin()). Half-covered edge pixels: paintEdgeStrips().
    void clipContent(QPainter& p) const;
    /// Chrome's antialiased clip at a .5 content edge (only the left one stays fractional) shows the
    /// clipped column at half coverage
    /// (QPainter clip paths are not antialiased): repaint the content of each such 1px strip into a
    /// layer and blend it at opacity 0.5. `p` is the widget painter, untransformed.
    void paintEdgeStrips(QPainter& p, const QRect& dirty);

    // ---- geometry helpers ----
    QRectF sub() const;
    float viewW() const { return float(sub().width()); }
    float viewH() const { return float(sub().height()); }
    float layoutW() const { return viewW() - (vbar ? kScrollbar : 0.0f); }
    float portH() const { return viewH() - (hbar ? kScrollbar : 0.0f); }

    void rebuild();

    /// layout at width w (no scrollbar logic); caches height
    QPair<float, float> measure(float w);

    void layoutAt(float w);

    /// decide scrollbars for the current widget size and lay out the active geometry
    void relayout();

    // scroll offsets live on Chrome's half-pixel grid (max offset 404.695 − 360 → 44.5)
    float maxScrollY() const { return std::max(0.0f, std::floor((contentH - portH()) * 2.0f) / 2.0f); }
    float maxScrollX() const { return std::max(0.0f, std::floor((overflowW - layoutW()) * 2.0f) / 2.0f); }
    void clampScroll();

    QPointF toContent(QPointF widgetPos) const;

    /// Chrome draws the contents of a composited scroller (overflow:auto WITH scrollable overflow) half
    /// a pixel lower / further right when the scroller's page position has a fraction in [0.25, 0.75)
    /// on that axis: the contents layer sits on the half-pixel grid (measured 27/09 on 300 probes: boxes,
    /// text x and baselines all move by exactly +0.5; a non-overflowing overflow:auto box does not).
    QPointF scrollerShift() const;
    /// Contents-layer origin in widget pixels: sub-pixel origin + scrollerShift().
    QPointF layerOrigin() const;
    /// Content → widget offset for painting: layerOrigin() − scroll offset.
    QPointF paintOrigin() const;

    // ---- sticky ----
    float stickyShift(Box* b) const;

    // ---- widgets ----
    void placeWidgets();

    // ---- hit testing ----
    Box* hitBox(Box* b, QPointF p);

    QVector<Box*> chainAt(QPointF widgetPos);

    bool hovered(const Box* b) const { return hover.contains(const_cast<Box*>(b)); }

    // ---- painting ----
    QColor colorOf(const Box* b, const QColor& inherited) const;

    /// Box edges snapped to the device half-pixel grid (Chrome's zoom-2 snapping) — in content coords.
    QRectF snapped(const QRectF& r) const;
    /// Text baseline y (content coords) snapped the way Skia places glyphs on the device grid.
    float baselineY(float v) const;

    static QPainterPath rrect(const QRectF& r, const float rad[4]);

    /// inner border path: radii shrink by the adjacent border widths (per axis)
    static QPainterPath innerPath(const QRectF& o, const float rad[4], const float bw[4], float shrink = 0.0f, QPointF shift = QPointF());

    enum DecorPart { DecorAll, DecorBg, DecorBorder };
    void paintBoxDecor(QPainter& p, const Box* b, const QRectF& r, const QColor& color, bool collapsedCell, DecorPart part = DecorAll);

    void paintText(QPainter& p, const Box* container, const Line& L, const Frag& fr, const QColor& color, bool underline);

    void paintIfc(QPainter& p, Box* b, const QColor& inherited, bool underlineInh, const QRectF& clip);

    void paintBox(QPainter& p, Box* b, const QColor& inherited, bool underlineInh, const QRectF& clip, bool stickyPass = false);

    /// Chrome's order: row + cell backgrounds, then the table's collapsed borders, then cell content;
    /// sticky cells (th) are positioned layers painted last — their opaque background covers the upper
    /// half of the header's bottom border (measured: only the lower half-pixel row shows).
    void paintTable(QPainter& p, Box* t, const QColor& color, bool ul, const QRectF& clip);

    void paintCellContent(QPainter& p, Box* cell, const QColor& inherited, bool ulInh, const QRectF& clip);

    void paintStickies(QPainter& p, const QRectF& clip);

    void paintScrollbars(QPainter& p);

    QRectF vThumb() const;
    QRectF hThumb() const;

    // ---- dump / text ----
    void dumpBox(const Box* b, QJsonArray& out, const QPointF& off) const;

    void textOf(const Box* b, QString& out) const;
};

} // namespace fincept::screens::hlp::hlpdom

namespace fincept::screens::hlp {
struct HlpView::Impl : hlpdom::ViewImpl {};
} // namespace fincept::screens::hlp
