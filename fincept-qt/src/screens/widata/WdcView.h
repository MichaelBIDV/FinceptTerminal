#pragma once
// WdcView.h: page of the WiData clone (tab VĨ MÔ): "Bố cục:" bar, scrolling 12-column grid of cards,
// "+ Thêm biểu đồ" block, tab menu, asynchronous loading. Package E. DESIGN §3, §4, §6, §6.1, §16 C4/C11;
// UI §1, §2; BEH §7; INT §3.4.
//
// Threading: the constructor and every slot are cheap and never touch the disk; current.json, layouts,
// dash_<id>.json, fonts and the view prefs are read/written inside QtConcurrent::run tasks.
// Cards: WdcCard of package D by default (signals wired to the view); a host or test may replace the factory,
// and package F hooks the X window / range popover / tooltip into every default card with set_card_hook().
// The expanded overlay (package F) comes from set_expand_factory(); this header includes neither.
//
// Đợt 3 (gói UI): every default card is wired here (no host hook needed): default X window and calendar popover of
// WdcRange (stored per (dash, card) in the view prefs), tooltip/crosshair/pan of WdcTooltip, expanded overlay
// (WdcExpanded::create) and chart page (openSingleChart / openCardSingle of WdcSingle) when package F's files are
// present. Cards render their charts off the UI thread (WdcRender.h); dashboardRendered() tells when they are shown.
#include "WdcData.h"
#include "WdcGrid.h"
#include "WdcRange.h"

#include <QHash>
#include <QImage>
#include <QJsonObject>
#include <QPointer>
#include <QTimer>
#include <QWidget>

#include <functional>
#include <memory>
#include <optional>

namespace fincept::screens::wdc {

// Everything a card widget needs. `card` points into *layouts; keep the shared_ptrs alive.
struct CardContext {
    QString dashId;
    std::shared_ptr<const LayoutsDoc> layouts;
    const CardSpec* card = nullptr;
    std::shared_ptr<const DashData> data;   // null: still loading, or build missing/broken (all [CẦN DATA])
    bool loading = false;
    QString dataError;                      // why data is null once loading is over
};
class WdcCard;
using CardFactory = std::function<QWidget*(const CardContext&, QWidget* parent)>;
using OverlayFactory = std::function<QWidget*(const CardContext&, QWidget* parent)>;
using CardHook = std::function<void(WdcCard* card, const CardContext&)>;

// ---- "Bố cục:" bar geometry, pure (UI §1.2, TB[] of CAP; DESIGN §6.1 for the "<" button) -------------

struct ShellMetrics {
    std::function<double(const QString&)> label;   // Inter 14/400 ("Bố cục:")
    std::function<double(const QString&)> tab;     // Inter 13/500
    std::function<double(const QString&)> add;     // Inter 13/400 ("Thêm")
    std::function<QString(const QString&, double)> elideTab;   // text-overflow: ellipsis at 13/500
};
ShellMetrics qtShellMetrics();   // theme::textWidth / theme::elideKeepSpace (Chromium font-subset runs, package D)

struct ShellTabGeom { QRectF box, text; QString shown; bool active = false, elided = false; };
struct ShellGeom {
    QRectF row, label, cluster, frame, addBtn, addIcon, nextBtn, prevBtn, dropBtn;
    double labelBaseline = 0, tabBaseline = 0, addBaseline = 0, addTextX = 0;
    double contentW = 0, maxScroll = 0, scrollX = 0;
    bool showNext = false, showPrev = false;
    std::vector<ShellTabGeom> tabs;               // box/text in panel coordinates (scroll applied)
};
// panelW: width of the white panel (= the view); border: 1 device px in logical px (1/dpr).
ShellGeom layoutShell(double panelW, double border, const QStringList& names, int active, double scrollX,
                      const ShellMetrics& m);
// "+ Thêm biểu đồ" button content (UI §2.2): AddRounded 20 px icon rect; the label starts at icon.right() + 8.
QRectF addChartIconRect(const QRectF& btn, double border);

// ---- widgets -----------------------------------------------------------------------------------------

class WdcShell : public QWidget {   // tab bar (WdcShell.cpp)
    Q_OBJECT
  public:
    explicit WdcShell(QWidget* parent = nullptr);
    void setTabs(const QStringList& ids, const QStringList& names);
    void setActive(const QString& id);
    void refreshMetrics();          // after fonts are registered
    ShellGeom geom() const;
    double scrollX() const { return scrollX_; }
    void setScrollX(double x);
    void scrollNext();
    void scrollPrev();
  signals:
    void tabActivated(const QString& id);
    void menuRequested(const QRectF& anchor);
    void tipRequested(const QString& text, const QRectF& anchor);
    void tipHidden();
  protected:
    void paintEvent(QPaintEvent*) override;
    void mouseMoveEvent(QMouseEvent*) override;
    void mousePressEvent(QMouseEvent*) override;
    void mouseReleaseEvent(QMouseEvent*) override;
    void leaveEvent(QEvent*) override;
    void wheelEvent(QWheelEvent*) override;
    void keyPressEvent(QKeyEvent*) override;
    void focusInEvent(QFocusEvent*) override;
    void focusOutEvent(QFocusEvent*) override;
  private:
    enum class Part { None, Tab, Drop, Next, Prev, Add };
    struct HitRes { Part part = Part::None; int index = -1; bool operator==(const HitRes&) const = default; };
    HitRes hitAt(const QPointF& p) const;
    void ensureTabVisible(int i);
    QStringList ids_, names_;
    int active_ = -1, focus_ = -1;
    bool focusVisible_ = false;
    double scrollX_ = 0;
    HitRes hover_, press_;
    ShellMetrics metrics_;
    QTimer tipTimer_;
};

class WdcContent : public QWidget {   // grid content + "+ Thêm biểu đồ" (WdcShell.cpp)
    Q_OBJECT
  public:
    explicit WdcContent(QWidget* parent = nullptr);
    void setPage(const PageGeom& g) { page_ = g; update(); }
    const PageGeom& page() const { return page_; }
    void setNotice(const QString& s) { notice_ = s; update(); }   // shown when no layout at all
  signals:
    void tipRequested(const QString& text, const QRectF& anchor);
    void tipHidden();
  protected:
    void paintEvent(QPaintEvent*) override;
    void mouseMoveEvent(QMouseEvent*) override;
    void mousePressEvent(QMouseEvent*) override;
    void leaveEvent(QEvent*) override;
  private:
    PageGeom page_;
    QString notice_;
    bool hover_ = false;
    QTimer tipTimer_;
};

class WdcPopup : public QWidget {   // menu (popover token §6.1) or tip (title-tooltip token §6.1)
    Q_OBJECT
  public:
    struct Item { QString text, action; bool enabled = true; };
    explicit WdcPopup(QWidget* view);
    void showMenu(const QPointF& at, const std::vector<Item>& items);
    void showTip(const QString& text, const QRectF& anchor);
    void dismiss();
    bool isMenu() const { return menu_; }
    QRectF box() const { return box_; }
    const std::vector<Item>& items() const { return items_; }
  signals:
    void triggered(const QString& action);
  protected:
    void paintEvent(QPaintEvent*) override;
    void mouseMoveEvent(QMouseEvent*) override;
    void mousePressEvent(QMouseEvent*) override;
    void keyPressEvent(QKeyEvent*) override;
  private:
    int itemAt(const QPointF& p) const;
    bool menu_ = false;
    QRectF box_;
    QString tip_;
    std::vector<Item> items_;
    int hover_ = -1;
};

class WdcView : public QWidget {
    Q_OBJECT
  public:
    explicit WdcView(QWidget* parent = nullptr);
    ~WdcView() override;

    // host + harness API (TASKS E)
    void set_state_dir(const QString& dir);              // reloads when already started
    QString state_dir() const { return stateDir_; }
    void set_prefs_path(const QString& path) { prefsPath_ = path; }
    void set_layout_const_path(const QString& path) { layoutConstPath_ = path; }
    void set_card_factory(CardFactory f);                // null restores the default (WdcCard)
    void set_card_hook(CardHook h);                      // on every default WdcCard: after build, again when its data arrives
    void set_expand_factory(OverlayFactory f) { expandFactory_ = std::move(f); }
    void set_grid_basis_override(std::optional<double> colW, std::optional<double> rowW);
    void select_dashboard(const QString& id);
    QString current_dashboard() const { return current_; }
    QStringList dashboards() const;
    bool expand_card(const QString& cardKey);
    bool export_card_png(const QString& cardKey, const QString& path = QString());   // empty path: save dialog
    QJsonObject dump_geometry_json() const;
    QImage grab_unrolled(qreal dpr = 0) const;
    bool is_idle() const { return pending_ == 0 && started_; }
    QString load_error() const { return loadError_; }
    BuildState build_state() const { return build_; }
    std::shared_ptr<const LayoutsDoc> layouts() const { return layouts_; }
    std::shared_ptr<const DashData> dash_data(const QString& id) const { return cache_.value(id); }
    QList<QWidget*> card_widgets() const;
    bool cards_rendered() const;                         // every current card shows the charts of its parameters
    const WdcRangeStore& range_store() const { return rangeStore_; }
    WdcShell* shell() const { return shell_; }
    WdcPopup* menu() const { return menu_; }
    void set_scroll_y(double y);
    double scroll_y() const { return scrollY_; }

  public slots:
    void start();                                        // first load (also on the first showEvent)
    void reload();                                       // re-read current.json, drop caches (old page stays)
    void reload_dashboard(const QString& id);            // sync button: re-read dash_<id>.json
    void close_expanded();
    void open_tab_menu();

  signals:
    void dashboardChanged(const QString& id);
    void dashboardReady(const QString& id);              // cards rebuilt with data, or with the failure
    void dashboardRendered(const QString& id);           // every card of `id` shows its charts (DESIGN §16 C18)
    void layoutsReady();
    void loadStatusChanged(const QString& error);        // empty = build read fine
    void legacySourcesRequested();                       // ▾ "Nguồn quốc tế & bảng SGI (màn cũ)" (DESIGN §16 C11)
    void singleChartRequested(const QString& id);        // ▾ "Biểu đồ: ..." (DESIGN §16 C4, package F)
    void expandRequested(const QString& dashId, const QString& cardKey);
    void calendarRequested(const QString& dashId, const QString& cardKey, const QRect& anchorGlobal);   // package F
    void cardSingleRequested(const QString& dashId, const QString& cardKey);   // gear "Mở dạng biểu đồ đơn"

  protected:
    void resizeEvent(QResizeEvent*) override;
    void showEvent(QShowEvent*) override;
    void wheelEvent(QWheelEvent*) override;
    void keyPressEvent(QKeyEvent*) override;

  private:
    struct InitResult;
    void applyInit(const InitResult& r, quint64 gen);
    void requestDash(const QString& id);
    void rebuildCards();
    void refreshCardData();
    void relayout();
    void savePrefs();
    void wireCard(WdcCard* card, const CardContext& ctx);
    QByteArray cacheTag() const;
    void applyRange(WdcCard* card);
    void checkRendered();
    void showTip(const QString& text, const QRectF& anchorInView);
    CardContext contextFor(const CardSpec& c) const;
    QWidget* makeDefaultCard(const CardContext& ctx, QWidget* parent);
    GridGeom currentGrid() const;

    WdcShell* shell_ = nullptr;
    QWidget* frame_ = nullptr;
    WdcContent* content_ = nullptr;
    QWidget* scrollbar_ = nullptr;
    WdcPopup* menu_ = nullptr;
    WdcPopup* tip_ = nullptr;
    QPointer<QWidget> expanded_;

    QString stateDir_, prefsPath_, layoutConstPath_, current_, loadError_;
    bool started_ = false;
    int pending_ = 0;
    quint64 gen_ = 0;
    BuildState build_;
    std::shared_ptr<const LayoutsDoc> layouts_;
    QHash<QString, std::shared_ptr<const DashData>> cache_;
    QHash<QString, QString> dashErrors_;
    QHash<QString, bool> loading_;
    std::vector<std::pair<QString, QPointer<QWidget>>> cards_;
    CardFactory cardFactory_;
    CardHook cardHook_;
    bool customFactory_ = false, cardsDefault_ = false;
    QString cardsDash_;   // dashboard the current card widgets were built for
    OverlayFactory expandFactory_;
    std::optional<double> colOverride_, rowOverride_;
    double scrollY_ = 0;
    WdcRangeStore rangeStore_;          // per (dash, card) button, saved with the prefs (worker thread)
    bool rangeLoaded_ = false;
    bool renderedEmitted_ = false;
};

} // namespace fincept::screens::wdc
