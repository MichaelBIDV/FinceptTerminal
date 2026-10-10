// src/screens/hdcv_launchpad/HlpDom.h
// A small CSS-subset box model so every Launchpad panel can be written as a node tree that mirrors
// the HTML template in panels.js line for line, and be laid out + painted the way Chrome does it
// (fractional px, half-leading line boxes, margin collapsing, auto table layout, flex, grid,
// sticky, line-clamp). One HlpView widget renders one tree (= one panel body `.bd`).
//
// Why not QWidgets+layouts: the Launchpad is ~900 inline-styled HTML elements; QLabel rich text has
// no inline-block borders (tags/chips), no half-leading control and integer geometry. Why not
// QtWebEngine: not in this Qt kit.
//
// Contract for panel code (HlpPanels*.cpp): build nodes with the `N` builder below, never touch
// QPainter/QWidget directly except through `custom()` / `widget()` nodes.
#pragma once

#include "screens/hdcv_launchpad/HlpTheme.h"

#include <QColor>
#include <QFont>
#include <QPointF>
#include <QRectF>
#include <QString>
#include <QVector>
#include <QWidget>

#include <cmath>
#include <functional>
#include <memory>
#include <optional>

class QPainter;

namespace fincept::screens::hlp {

struct Node;
using NodeP = std::shared_ptr<Node>;

enum class Display { Block, Inline, InlineBlock, Flex, Grid, Table, TableRow, TableCell, None };
enum class WhiteSpace { Normal, NoWrap };
enum class TextAlign { Left, Right, Center };
enum class Justify { Start, Center, End, SpaceBetween };
enum class AlignItems { Stretch, Start, Center, End, Baseline };

/// One grid track: "70px" → px=70 · "1fr" → fr=1 · "minmax(0,1.05fr)" → minPx=0, fr=1.05.
struct Track {
    float px = -1.0f; ///< fixed size (>=0) or -1
    float fr = 0.0f;  ///< flexible factor
    float minPx = 0.0f;
};

struct GridSpec {
    QVector<Track> cols;    ///< explicit columns; ignored when autoFitMin > 0
    float autoFitMin = 0.0f; ///< >0 → `repeat(auto-fit, minmax(autoFitMin, 1fr))` (empty tracks collapse)
    float colGap = 0.0f, rowGap = 0.0f;
    /// Container query of `.wd-split`: when the grid's own width < minWidthForCols, use one column.
    float minWidthForCols = 0.0f;
};

/// Inherited properties are std::optional: unset = inherit from parent (root: sans 12px/1.45, ink).
struct Style {
    Display display = Display::Block;

    // ---- box (px; CSS box-sizing:border-box everywhere, like `*{box-sizing:border-box}`) ----
    float mt = 0, mr = 0, mb = 0, ml = 0;
    bool mlAuto = false;                       ///< `margin-left:auto` (flex item pushed right)
    float pt = 0, pr = 0, pb = 0, pl = 0;
    float bw[4] = {0, 0, 0, 0};                ///< border widths: top, right, bottom, left
    QColor bc[4];                              ///< border colors (invalid = currentColor)
    float radius[4] = {0, 0, 0, 0};            ///< tl, tr, br, bl
    QColor bg;                                 ///< invalid = transparent
    float width = NAN, height = NAN, minWidth = NAN, maxWidth = NAN, maxHeight = NAN;
    float widthPct = NAN;                      ///< width in % of containing block
    float opacity = 1.0f;

    // ---- flex (row direction only; the Launchpad never uses column flex in bodies) ----
    bool flexWrap = false;
    float gap = 0.0f;                          ///< `gap` (flex and chips)
    Justify justify = Justify::Start;
    AlignItems alignItems = AlignItems::Stretch; ///< flex AND grid containers (grid default = stretch)
    float flexGrow = 0.0f, flexShrink = 1.0f;
    /// `align-self` of a flex/grid item; unset = auto (the container's align-items).
    std::optional<AlignItems> alignSelf;

    /// `box-shadow: inset x y blur spread color` — painted inside the padding box, above the
    /// background and below the border, clipped to the inner (radius-adjusted) border shape like
    /// Chrome. Only blur 0 is exact; blur > 0 is drawn as a hard edge.
    struct InsetShadow {
        float x = 0.0f, y = 0.0f, blur = 0.0f, spread = 0.0f;
        QColor color;
    };
    std::optional<InsetShadow> boxShadowInset;

    // ---- grid ----
    GridSpec grid;

    // ---- table ----
    int colspan = 1;
    bool isHead = false;                       ///< TableRow inside <thead> (sticky `th`)

    // ---- inherited text properties ----
    std::optional<bool> monoFamily;            ///< true = --mono (Menlo), false = --sans (SF)
    std::optional<bool> arialFamily;           ///< form controls
    std::optional<float> fontSize;             ///< px
    std::optional<int> weight;                 ///< 400 / 600 / 700
    std::optional<bool> italic;
    std::optional<float> letterSpacingEm;      ///< CSS letter-spacing in em (→ px at resolve time)
    std::optional<bool> upper;                 ///< text-transform:uppercase
    std::optional<QColor> color;
    std::optional<float> lineHeightPx;         ///< line-height: Npx
    std::optional<float> lineHeightFactor;     ///< line-height: 1.45
    std::optional<bool> lineHeightNormal;      ///< line-height: normal
    std::optional<WhiteSpace> whiteSpace;
    std::optional<TextAlign> textAlign;
    std::optional<bool> tabularNums;           ///< font-variant-numeric: tabular-nums (Menlo is already tabular)

    // ---- not inherited ----
    bool underline = false;                    ///< text-decoration: underline
    int lineClamp = 0;                         ///< -webkit-line-clamp (with ellipsis)
    bool ellipsis = false;                     ///< text-overflow: ellipsis (nowrap overflow)
    bool sticky = false;                       ///< position: sticky
    float stickyTop = 0.0f;                    ///< `top` for sticky (th uses -8px)

    // ---- hover state (applied to this node while the pointer is inside its border box) ----
    std::optional<QColor> hoverBg, hoverColor, hoverBorderColor;
    bool hoverUnderline = false;
    bool pointer = false;                      ///< cursor: pointer
};

struct Node {
    Style st;
    QString text;      ///< text leaf (display Inline, no kids). Whitespace collapses unless NoWrap-pre.
    bool br = false;   ///< <br>
    /// A bare DOM text node (what `text()` builds), as opposed to an element (`span(t)`). Differs only
    /// inside flex/grid containers: every element becomes its own item, while consecutive text nodes
    /// share one anonymous item. (Replaces the old `lineClamp = -1` marker, which is still honoured.)
    bool textNode = false;
    QVector<NodeP> kids;

    // ---- interaction ----
    std::function<void()> onClick;      ///< click handler (rows, chips, dots, list items)
    QString href;                       ///< link: opened with QDesktopServices (http/https only)
    QString tip;                        ///< `title` attribute → tooltip
    QString key;                        ///< debug / geometry-dump name ("row", "item", "tile"…)
    /// `tabindex="0"`: Tab / Shift+Tab stop, focused by a click, Enter / Space run onClick (the web's
    /// keydown → pick). `focusRing` valid = `:focus-visible{outline:1px solid c;outline-offset:-1px}`.
    bool focusable = false;
    QColor focusRing;

    // ---- replaced / custom content ----
    /// Custom leaf (sparkline, σ bar, ruler, WiData chart): height for a given content width and a
    /// paint callback in the node's content box. Optional hover callback (local pos, inside?).
    std::function<float(float contentWidth)> customHeight;
    std::function<void(QPainter&, const QRectF& contentBox)> customPaint;
    std::function<void(QPointF local, bool inside)> customHover;
    std::function<bool(QPointF local)> customClick;   ///< return true if handled
    std::function<QString(QPointF local)> customTip;  ///< tooltip at a point (ruler dots)
    /// Cursor over a custom node: return true → pointing hand at that local point (content box).
    std::function<bool(QPointF local)> customPointer;
    /// innerText of a custom node: the HTML text the web renders in its place (axis labels painted by
    /// customPaint), one line per element. Only used by plainText(); never painted.
    QString customText;

    /// Embedded real widget (input.f → QLineEdit, <select> → QComboBox). HlpView reparents it,
    /// sizes it to the node's border box and moves it on scroll. Height = st.height if set, else
    /// widget->sizeHint().height(). The widget is NOT owned by the node (the panel keeps it alive
    /// across re-renders so focus/text survive). A widget with the dynamic property "hlp_paintsFrame" =
    /// true paints its own CSS box: it gets the covering whole pixels instead, plus "hlp_box" (QRectF,
    /// its own coordinates: the border box snapped like HlpView snaps boxes) and "hlp_css" (unsnapped).
    QWidget* widget = nullptr;
};

/// Fluent builder. `N` holds a NodeP; every setter returns *this.
///   div().cls_row() << span("…").c(pal().ink2) << span(v).mono().right()
class N {
  public:
    N();
    explicit N(NodeP p);
    operator NodeP() const { return p_; }
    Node* operator->() const { return p_.get(); }
    NodeP node() const { return p_; }

    // children
    N& operator<<(const NodeP& child);
    N& operator<<(const N& child);
    N& add(const QVector<NodeP>& kids);

    // display
    N& display(Display d);
    N& inlineBlock();
    N& flex(Justify j = Justify::Start, AlignItems a = AlignItems::Stretch, float gap = 0);
    N& wrap();
    N& grid(const GridSpec& g);
    N& none();

    // box
    N& m(float t, float r, float b, float l);
    N& mt(float v); N& mr(float v); N& mb(float v); N& ml(float v);
    N& mlAuto();
    N& p(float all);
    N& p(float v, float h);
    N& p(float t, float r, float b, float l);
    N& border(float w, const QColor& c);                    ///< all sides
    N& bt(float w, const QColor& c); N& br(float w, const QColor& c);
    N& bb(float w, const QColor& c); N& bl(float w, const QColor& c);
    N& radius(float r);
    N& radius(float tl, float tr, float brr, float bl);
    N& bg(const QColor& c);
    N& w(float px); N& h(float px); N& minW(float px); N& maxW(float px); N& maxH(float px);
    N& wPct(float pct);
    N& opacity(float o);
    N& grow(float g = 1.0f);
    N& shrink(float s);
    N& alignSelf(AlignItems a);     ///< `align-self` (flex / grid item)
    /// `box-shadow: inset x y blur spread color` (see Style::InsetShadow).
    N& shadowInset(float x, float y, float blur, float spread, const QColor& c);
    N& shadowInset(float x, float y, const QColor& c); ///< `inset x y 0 color`
    N& colspan(int n);
    N& head();

    // text (inherited)
    N& sans(float px, int weight = 400);
    N& mono();                      ///< family only
    N& mono(float px, int weight = 400);
    N& arial(float px, int weight = 400);
    N& size(float px);
    N& weight(int w);
    N& bold();                      ///< 700
    N& semibold();                  ///< 600
    N& italic(bool on = true);
    N& ls(float em);                ///< letter-spacing in em
    N& upper();
    N& c(const QColor& col);        ///< color
    N& lh(float px);                ///< line-height px
    N& lhf(float factor);           ///< line-height factor
    N& lhNormal();
    N& nowrap();
    N& normalWrap();
    N& right(); N& left(); N& center();
    N& tabnum();

    // not inherited
    N& underline();
    N& clamp(int lines);
    N& ellipsis();
    N& sticky(float top);

    // interaction
    /// Click handler. Clicks go to the DEEPEST node with a handler or an href and stop there — a link
    /// (href) inside a clickable row never triggers the row (panels.js `data-stop`); a node with both
    /// click() and link() runs its handler instead of opening the URL.
    N& click(std::function<void()> fn);
    N& link(const QString& href);
    N& tip(const QString& t);
    N& key(const QString& k);
    N& hoverBg(const QColor& c);
    N& hoverColor(const QColor& c);
    N& hoverBorder(const QColor& c);
    N& hoverUnderline();
    N& pointer();
    N& focusable(const QColor& ring); ///< see Node::focusable

    // replaced content
    N& custom(std::function<float(float)> height, std::function<void(QPainter&, const QRectF&)> paint);
    N& onHover(std::function<void(QPointF, bool)> fn);
    N& onCustomClick(std::function<bool(QPointF)> fn);
    N& customTip(std::function<QString(QPointF)> fn);
    N& customPointer(std::function<bool(QPointF)> fn);
    N& customText(const QString& t); ///< see Node::customText
    N& widget(QWidget* w);

  private:
    NodeP p_;
};

// ---- element constructors (HTML tag → default display) ----
N div();                               ///< block
N span();                              ///< inline container
N span(const QString& text);           ///< inline text
N text(const QString& text);           ///< bare text leaf
N brk();                               ///< <br>
N table();                             ///< table, width:100%, border-collapse:collapse, 11px (see atoms)
N tr();
N td();
N th();

/// Shorthand for the web helper `const ND = '<span class="nd">[CẦN DATA]</span>'`.
NodeP nd(const QString& textOverride = QString());

// ---------------------------------------------------------------------------------------------
// HlpView — renders one node tree as a CSS scroll container (the panel body `.bd`):
//   border-box max-height (the web `--h`), overflow:auto on both axes, WebKit custom scrollbars
//   7px wide (thumb var(--line-2), radius 4, no track, no arrows) that TAKE layout space like
//   Chrome's ::-webkit-scrollbar does. The root node is laid out at the view's width.
// ---------------------------------------------------------------------------------------------
class HlpView : public QWidget {
    Q_OBJECT
  public:
    explicit HlpView(QWidget* parent = nullptr);
    ~HlpView() override;

    /// Replace the tree. keepScroll = keep the current scroll offsets (re-render after a chip/filter).
    void setRoot(const NodeP& root, bool keepScroll = false);
    NodeP root() const;

    /// Border-box max height (px). 0 = unbounded (grow with content).
    void setMaxContentHeight(float px);

    /// The exact (fractional) CSS box of this view, in THIS widget's own coordinates: the widget sits
    /// on whole pixels, the CSS box at r.topLeft() inside it (0 ≤ x,y < 1 typically) with size r.size().
    /// Layout uses r.width(); painting snaps boxes/baselines on the device pixel grid, i.e. Chrome's page
    /// grid, so text lands on the same rows as in Chrome even when the box origin is fractional.
    /// Typical call:  QRect g = outward-rounded(exact); v->setGeometry(g);
    ///                v->setSubpixelGeometry(QRectF(exact.topLeft() - g.topLeft(), exact.size()));
    /// Empty rect = use the widget rect. The dynamic property "hlp_subpixel" (QRectF) is still read
    /// when this was never called.
    void setSubpixelGeometry(const QRectF& r);
    QRectF subpixelGeometry() const;
    /// Height the view wants at a given width: min(content height, max height).
    float preferredHeight(float width) const;
    /// Content height at a given width, ignoring max height (for "unrolled" harness captures).
    float contentHeight(float width) const;

    int scrollY() const;
    void setScrollY(int y);

    /// Re-evaluate :hover at the pointer's current position without a mouse move — what Blink does after
    /// a DOM / layout change under a still pointer (panel added, ✕ ◀ ▶, #sheet closed). No mousemove
    /// handler runs, so custom hovers (chart crosshair) are left as they are.
    void syncHover();

    /// Geometry dump for the harness: every node with a non-empty `key` plus text leaves, in view
    /// coordinates (x, y, w, h, key, text). Used to diff against the Chrome dump.
    QString dumpGeometryJson() const;
    /// All visible text in document order, one block per line (to diff against innerText).
    QString plainText() const;

    QSize sizeHint() const override;
    bool hasHeightForWidth() const override { return true; }
    int heightForWidth(int w) const override;

  signals:
    void contentResized();

  protected:
    void paintEvent(QPaintEvent* e) override;
    void resizeEvent(QResizeEvent* e) override;
    void mouseMoveEvent(QMouseEvent* e) override;
    void mousePressEvent(QMouseEvent* e) override;
    void mouseReleaseEvent(QMouseEvent* e) override;
    void leaveEvent(QEvent* e) override;
    void wheelEvent(QWheelEvent* e) override;
    // focusable nodes (HlpDom.cpp): Tab order, Enter / Space, :focus-visible ring
    void keyPressEvent(QKeyEvent* e) override;
    void focusInEvent(QFocusEvent* e) override;
    void focusOutEvent(QFocusEvent* e) override;
    bool focusNextPrevChild(bool next) override;
    bool event(QEvent* e) override; // tooltips

  private:
    struct Impl;
    std::unique_ptr<Impl> d_;
};

} // namespace fincept::screens::hlp
