// src/screens/hdcv_launchpad/HlpShell_p.h
// PRIVATE to the shell (HlpShell*.cpp) — not part of the module API. The shell is split by
// responsibility:
//   HlpShell.cpp       core: Impl construction, persistence (boot/save/theme), data poll, public API
//   HlpShellBar.cpp    #bar (tabs · MÃ · GO · + Component · Lưu View · Mặc định · ◐) + form controls
//   HlpShellGrid.cpp   #grid: .pnl frames (header/body/ring), layout, setCtx, drag & drop, overlay scroll
//   HlpShellSheet.cpp  "+ Component" #sheet
//   HlpShellDump.cpp   harness hooks (grabUnrolled, dumpGeometryJson)
// Shared helpers live in the named namespace hlp::shell_detail (hlpsh_ prefix, unity-safe); helpers
// used by one file stay in that file's anonymous namespace.
//
// Test hooks (behaviour-neutral): widgets carry a dynamic property "hlp_role" — "bar", "tick", "grid",
// "sheet", "pnl" (frame, plus "hlp_panel" = component id), "hd", "bd" — so shell_test can find them.
#pragma once

#include "screens/hdcv_launchpad/HlpDom.h"
#include "screens/hdcv_launchpad/HlpPanels.h"
#include "screens/hdcv_launchpad/HlpShell.h"

#include <QColor>
#include <QComboBox>
#include <QHash>
#include <QJsonArray>
#include <QJsonObject>
#include <QJsonValue>
#include <QLineEdit>
#include <QPoint>
#include <QPointer>
#include <QRectF>
#include <QString>
#include <QTimer>
#include <QVariantMap>
#include <QVector>
#include <QWidget>

#include <algorithm>
#include <functional>
#include <map>
#include <memory>

class QPainter;

namespace fincept::screens::hlp {

namespace shell_detail {

// ---- index.html measurements (SPEC §2, Chrome 2000×1120) ----
inline constexpr float hlpsh_kBarH = 34.0f;          ///< #bar height incl. its 1px border-bottom
inline constexpr float hlpsh_kGap = 6.0f;            ///< #grid gap and padding (--gap)
inline constexpr float hlpsh_kHdH = 23.7f;           ///< .hd: 4 + 14.7 (h2 line) + 4 + 1 border (fallback)
inline constexpr float hlpsh_kBdFallback = 320.0f;   ///< .bd max-height default var(--h,320px)
inline constexpr float hlpsh_kRadius = 14.0f;        ///< --r after design_system.css
inline constexpr int hlpsh_kNarrowPx = 900;          ///< @media(max-width:900px) → 4 columns, every panel span 4
inline constexpr int hlpsh_kPollMs = 60 * 1000;      ///< file mtime poll
inline constexpr int hlpsh_kAutoScrollMs = 16;       ///< grid auto-scroll tick while dragging a panel
inline constexpr int hlpsh_kAutoScrollZone = 40;     ///< px from the grid edge where dragging scrolls
inline constexpr int hlpsh_kScrollbarShowMs = 1000;  ///< overlay scrollbar stays visible after a scroll

// ---- HlpShell.cpp ----
const QString& hlpsh_brand();
/// Plain QWidget subclasses (no Q_OBJECT) get the app QSS `QWidget{background}` painted; the Shell's
/// own stylesheet makes widgets carrying this name transparent (they paint themselves).
void hlpsh_mark(QWidget* w);
/// panels.js safeUrl(): only http(s) leaves the page; anything else became '#' (a no-op).
void hlpsh_openUrl(const QString& url);

// ---- view model (index.html DEFAULTS, restricted to the three Fincept dashboards) ----
struct hlpsh_PanelSpec {
    QString id;
    int w = 4;   ///< grid columns
    int h = 300; ///< .bd max-height px
};

struct hlpsh_View {
    QString key;
    QString name;
    QVector<hlpsh_PanelSpec> panels;
};

// ---- geometry / painting (HlpShellGrid.cpp) ----
/// Integer rect covering a fractional CSS rect (outward) — for boxes painted antialiased inside it.
QRect hlpsh_outer(const QRectF& r);
/// Put an HlpView on a fractional CSS rect (parent coordinates): the widget covers it on whole pixels
/// (hlpsh_outer) and the engine gets the exact box, so it snaps text/boxes on the page pixel grid.
void hlpsh_place(HlpView* v, const QRectF& r);

/// Box edges on Chrome's half-pixel grid (each edge rounded to the nearest 0.5) — widget-local
/// coordinates of a widget placed on whole page pixels.
QRectF hlpsh_snapHalf(const QRectF& r);

struct hlpsh_Radii {
    float tl = 0, tr = 0, br = 0, bl = 0;
};
/// CSS Backgrounds 3 §5.5 corner overlap: scale every radius by the smallest side / (sum of its radii).
hlpsh_Radii hlpsh_fit(const QRectF& r, const hlpsh_Radii& k);
hlpsh_Radii hlpsh_all(float r);
/// Radii4 of fitted radii, each reduced by `inset` (≥ 0).
Radii4 hlpsh_r4(const hlpsh_Radii& k, float inset);
/// Paint a CSS box with a uniform 1px border as Chrome does: background half a pixel inside the border
/// edge (bleed avoidance), then the ring — both with Skia's analytic corner coverage (fillRRect).
void hlpsh_box(QPainter& p, const QRectF& r, const hlpsh_Radii& radii, const QColor& bg, const QColor& border);

// ---- form controls (HlpShellBar.cpp) ----
/// A QLineEdit whose text, selection and caret are painted by the engine's shaper, as Chrome paints an
/// <input> (focused or not), QLineEdit keeping the editing behaviour. While an input method composes
/// (marked text) or when the text is wider than the box (QLineEdit would scroll it), QLineEdit paints.
class hlpsh_EngineEdit : public QLineEdit {
  public:
    explicit hlpsh_EngineEdit(QWidget* parent);

  protected:
    /// Text / selection / caret in the CSS content box; false = let QLineEdit paint the content.
    bool paintContent(QPainter& p, float padX, float padY, float px, int weight, const QColor& color);
    void focusInEvent(QFocusEvent* e) override;
    void focusOutEvent(QFocusEvent* e) override;
    void inputMethodEvent(QInputMethodEvent* e) override;

  private:
    QTimer blink_;
    bool caretOn_ = true;
    bool composing_ = false;
    void restartBlink();
};

/// `#tick`: 96×24, mono 600 12px amber, bg #000 (light #fffbf2), 1px amber-dim border (focus amber),
/// radius r 0 0 r, uppercase, maxlength 8, placeholder "VCB".
class hlpsh_TickEdit final : public hlpsh_EngineEdit {
  public:
    explicit hlpsh_TickEdit(QWidget* parent);
    void restyle();
    std::function<void()> onFocusChange; ///< the bar re-renders (its node paints the frame)

  protected:
    void paintEvent(QPaintEvent* e) override;
    void focusInEvent(QFocusEvent* e) override;
    void focusOutEvent(QFocusEvent* e) override;
};

/// `input.f`: bg-2, 1px line-2 border (focus amber-dim), radius r, mono 11px ink, padding 3px 7px.
class hlpsh_FieldEdit final : public hlpsh_EngineEdit {
  public:
    explicit hlpsh_FieldEdit(QWidget* parent);

  protected:
    void paintEvent(QPaintEvent* e) override;
};

/// `<select>` baseline look (`.wd-bar select`): bg-2, ink, 1px line-2, radius r (clamped), Arial 10.5px,
/// padding 2px 5px. The panel may restyle it (the WiData panel does).
QComboBox* hlpsh_makeSelect(QWidget* parent);

// ---- panel frame (.pnl) and #grid (HlpShellGrid.cpp) ----
class hlpsh_Frame;

/// Overlay above a frame's children: page background outside the rounded box (clips the body like
/// `.pnl{overflow:hidden}`) and the 1px border (line / hover line-2 / drop target amber).
class hlpsh_Ring final : public QWidget {
  public:
    explicit hlpsh_Ring(hlpsh_Frame* frame);

  protected:
    void paintEvent(QPaintEvent* e) override;

  private:
    hlpsh_Frame* frame_;
};

/// One instance of a component in the current view, with everything the web keeps on the section
/// element (render closure state, embedded inputs, .asof text).
class hlpsh_Frame final : public QWidget {
  public:
    explicit hlpsh_Frame(QWidget* parent);
    ~hlpsh_Frame() override;

    // ---- instance ----
    quint64 uid = 0;
    int index = -1;                 ///< position in views[view].panels (−1: the no-data panel)
    hlpsh_PanelSpec spec;
    const PanelDef* def = nullptr;  ///< nullptr = "launchpad_data.json unreadable" panel (no .hd)
    QString rawTitle;               ///< C.title(ctx) — the h2 textContent (CSS uppercases it)
    QString asof;                   ///< .asof text written by stamp()
    QVariantMap state;              ///< RenderCtx::state
    std::unique_ptr<RenderCtx> rc;
    QHash<QString, QPointer<QLineEdit>> edits;
    QHash<QString, QPointer<QComboBox>> combos;
    QJsonValue wdVer;               ///< wdsignal: `cap_nhat` last drawn (web bd._wdVer)
    bool wdPending = false;         ///< wdsignal: redraw postponed while the user works in the panel
    bool rerenderQueued = false;

    HlpView* hd = nullptr;          ///< .hd
    HlpView* body = nullptr;        ///< .bd
    hlpsh_Ring* ring = nullptr;

    // ---- layout (fractional CSS px, #grid content coordinates) ----
    QRectF exact;
    QPointF off;                    ///< exact.topLeft() − geometry().topLeft()
    float hdH = 0.0f, bdH = 0.0f;
    int row = 0, col = 0, span = 4;

    // ---- interaction ----
    bool hovered = false, over = false, dragging = false;
    std::function<void(hlpsh_Frame*)> onDragStart;
    std::function<void(hlpsh_Frame*, QPoint)> onDragMove;
    std::function<void(hlpsh_Frame*, QPoint)> onDragEnd;

    float maxBody() const { return def ? float(spec.h) : hlpsh_kBdFallback; }
    void setOver(bool on);
    /// .pnl border: line · :hover line-2 · drop target amber.
    QColor borderColor() const;

  protected:
    void paintEvent(QPaintEvent* e) override;
    void enterEvent(QEnterEvent* e) override;
    void leaveEvent(QEvent* e) override;
    /// `.hd` is draggable: press + move past the drag distance picks the panel up; a plain click goes
    /// on to the header view (◀ ▶ ✕ nodes).
    bool eventFilter(QObject* o, QEvent* e) override;

  private:
    bool armed_ = false;
    QPoint pressGlobal_;
};

/// #grid content: page background (body{background:var(--bg)}); also the shell's backdrop.
class hlpsh_GridContent final : public QWidget {
  public:
    explicit hlpsh_GridContent(QWidget* parent);

  protected:
    void paintEvent(QPaintEvent* e) override;
};

/// Overlay scrollbar thumb (Chrome on macOS: takes no layout space, fades after a scroll).
class hlpsh_ScrollThumb final : public QWidget {
  public:
    explicit hlpsh_ScrollThumb(QWidget* parent);
    void flash(int contentH, int viewH, int scroll);

  protected:
    void paintEvent(QPaintEvent* e) override;

  private:
    QTimer hide_;
    bool shown_ = false;
    int contentH_ = 0, viewH_ = 0, scroll_ = 0;
};

/// #grid viewport: scrolls `content` by moving it; wheel events the bodies leave unhandled chain here.
class hlpsh_GridVp final : public QWidget {
  public:
    explicit hlpsh_GridVp(QWidget* parent);

    hlpsh_GridContent* content = nullptr;
    hlpsh_ScrollThumb* thumb = nullptr;
    int scrollY = 0;
    std::function<void()> onResized;

    int maxScroll() const { return std::max(0, content->height() - height()); }
    void setScrollY(int y);

  protected:
    void wheelEvent(QWheelEvent* e) override;
    void resizeEvent(QResizeEvent* e) override;
};

// ---- #sheet (HlpShellSheet.cpp) ----
/// "+ Component": rgba(0,0,0,.66) overlay, centred .box (min(620px,92vw), max 78vh, radius 5).
class hlpsh_Sheet final : public QWidget {
  public:
    explicit hlpsh_Sheet(QWidget* parent);

    HlpView* view = nullptr;
    QRectF box;
    std::function<void()> onClose;

    void relayout();

  protected:
    void paintEvent(QPaintEvent* e) override;
    void mousePressEvent(QMouseEvent* e) override;
    void keyPressEvent(QKeyEvent* e) override;
    void resizeEvent(QResizeEvent* e) override;
};

} // namespace shell_detail

// =================================================================================================
// Shell::Impl — index.html's script block. Methods are defined in the file named on each group.
// =================================================================================================

struct Shell::Impl {
    explicit Impl(Shell* shell) : q(shell) {}

    Shell* q;
    DataStore* store = nullptr;
    shell_detail::hlpsh_GridContent* backdrop = nullptr; ///< page background under everything (body{background})
    HlpView* bar = nullptr;
    shell_detail::hlpsh_TickEdit* tick = nullptr;
    shell_detail::hlpsh_GridVp* grid = nullptr;
    shell_detail::hlpsh_Sheet* sheet = nullptr;
    QTimer* poll = nullptr;
    QTimer* autoScroll = nullptr;

    QVector<shell_detail::hlpsh_View> views;
    QString view = QStringLiteral("ck");
    QString ctx = QStringLiteral("VCB");
    QString statePath;
    bool booted = false, dataOk = false, dying = false, relayoutQueued = false, hoverQueued = false;
    QVector<shell_detail::hlpsh_Frame*> frames;
    std::map<QString, QVariantMap> viewStates; ///< WD_ST-like state per (view, panel id); node-stable
    quint64 nextUid = 1;
    float contentH = 0.0f;                     ///< exact #grid scroll height (padding included)

    // drag & drop of panels
    QPointer<shell_detail::hlpsh_Frame> dragSrc;
    QPointer<QObject> hoverRecheck; ///< one-shot app filter armed by syncHoverSoon (next mouse move re-syncs)
    QPoint dragGlobal;
    int autoDy = 0;

    // ---- HlpShell.cpp: construction, lookups, persistence, poll ----
    void build();
    void shutdown();
    /// Run `fn` after the current event (node handlers must not rebuild their own tree mid-dispatch).
    void defer(std::function<void()> fn);
    void syncChrome();
    shell_detail::hlpsh_View* cur();
    int indexOfView(const QString& key) const;
    shell_detail::hlpsh_Frame* frameByUid(quint64 uid) const;
    QJsonObject readState() const;
    void writeState(const QJsonObject& o) const;
    void saveState() const;
    void saveTheme() const;
    void removeState() const;
    void boot(const QJsonObject* st);
    void bootFromFile();
    void pollData();
    QWidget* dialogParent() const;

    // ---- HlpShellBar.cpp ----
    void renderBar();
    void saveViewPrompt();

    // ---- HlpShellGrid.cpp ----
    void render();
    void clearFrames();
    shell_detail::hlpsh_Frame* makeFrame(const shell_detail::hlpsh_PanelSpec& spec, int index, const PanelDef* def);
    std::unique_ptr<RenderCtx> makeRc(shell_detail::hlpsh_Frame* f);
    void renderHeader(shell_detail::hlpsh_Frame* f);
    void renderBody(shell_detail::hlpsh_Frame* f, bool keepScroll, bool viaSetCtx);
    void queueRerender(quint64 uid);
    void headerAction(quint64 uid, int a);
    void relayoutSoon();
    void layoutGrid();
    /// :hover of the frames and views under a still pointer after the grid changed (Blink re-hovers after
    /// layout; Qt only enters a widget on the next mouse move). Deferred, coalesced.
    void syncHoverSoon();
    /// The sync itself; arms `hoverRecheck` so the next mouse move syncs again — Qt never sent those
    /// frames/views an Enter, so it would not send them a Leave either.
    void syncHoverNow(bool rearm);
    void setCtx(const QString& raw);
    shell_detail::hlpsh_Frame* frameAtGlobal(const QPoint& g) const;
    void dragStart(shell_detail::hlpsh_Frame* f);
    void dragMove(const QPoint& g);
    void dragAutoTick();
    void dragEnd(shell_detail::hlpsh_Frame* src, const QPoint& g);

    // ---- HlpShellSheet.cpp ----
    void openSheet();
    void closeSheet();
    void addPanel(const QString& id);
};

} // namespace fincept::screens::hlp
