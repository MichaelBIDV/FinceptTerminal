#pragma once
// ChbDom.h — public API of the chaebol_map CSS engine (DESIGN.md §3–§5). Qt-only (QtCore/QtGui), no app
// headers: builds into the standalone harness (harness/chaebol_map/qt) and into the app.
//
// Typical use (ChbView):
//     chb::ensure_fonts();                          // once, after QApplication exists
//     chb::Document doc;
//     doc.set_shell(read("shell.json"));            // root <body> with a {"t":"slot","id":"main"}
//     doc.set_tab_loader([&](QString id){ return read(manifest.tabs[id]); });
//     doc.set_inc_loader([&](QString key){ return read(manifest.inc[key]); });
//     doc.set_defaults(manifest.inventory.states → key/default); doc.reset_state();
//     doc.set_viewport(viewportW, viewportH);
//     doc.layout(viewportW);                        // resolve (if dirty) + style + layout
//     paintEvent: p.translate(0, -scrollY); doc.set_scroll_y(scrollY); doc.paint(p, visibleDocRect);
//     mousePress: Action a = doc.hit_test(docPoint); if (a.type == Action::Select) show QMenu → choose_option;
//                 else if (doc.activate(a)) { doc.layout(w); keep scrollY clamped; ensure a.region visible }
//
// Coordinates are CSS px in document space (origin = top-left of the page, unscrolled). Sticky boxes use
// scroll_y(); horizontal scroll regions (overflow-x auto/scroll) use the per-region scroll_x.
// State semantics = the Chrome oracle (ChbState.h). Geometry dump format = oracle ChbOracle.dump().
#include "screens/chaebol_map/ChbJson.h"

#include <QByteArray>
#include <QColor>
#include <QHash>
#include <QJsonObject>
#include <QPainter>
#include <QPointF>
#include <QRectF>
#include <QString>
#include <QStringList>

#include <functional>
#include <memory>
#include <vector>

namespace fincept::screens::chb {

/// One `on` handler (DOM click bubbling runs the target's handler, then each ancestor's).
struct ActionStep {
    std::vector<std::pair<QString, QString>> set;   ///< on.set
    bool sort = false;                               ///< on.sort present
    QString sortKey, sortDir, sortCol;
};

/// What a click on a point would do.
struct Action {
    enum Type { None, Set, Sort, SetAndSort, Select, Href };
    Type type = None;                                ///< kind of the innermost handler
    std::vector<ActionStep> steps;                   ///< Set/Sort: handlers innermost → outermost (bubbling)
    std::vector<std::pair<QString, QString>> set;   ///< innermost handler's on.set (convenience)
    QString sortKey, sortDir, sortCol;               ///< innermost handler's on.sort (convenience)
    QString bindKey, current;                        ///< Select: state key and current value
    QStringList optionValues, optionLabels;          ///< Select: options in order
    QString href;                                    ///< Href: http/https URL only
    QRectF rect;                                     ///< target border box, document coords (unscrolled)
    int region = -1;                                 ///< innermost horizontal scroll region holding the target
    bool pointer = false;                            ///< show a pointing-hand cursor
};

/// Horizontal scroll container (overflow-x auto/scroll).
struct ScrollRegion {
    int id = -1;
    QRectF rect;             ///< padding box, document coords (unscrolled, sticky not applied)
    float clientWidth = 0;
    float scrollWidth = 0;   ///< ≥ clientWidth
    float scrollX = 0;
    bool sticky = false;     ///< region lies in a position:sticky subtree (moves with scroll_y)
};

struct Timing {
    double resolveMs = 0, styleMs = 0, boxMs = 0, layoutMs = 0;
    int nodes = 0, boxes = 0;
};

class Document {
  public:
    Document();
    ~Document();
    Document(const Document&) = delete;
    Document& operator=(const Document&) = delete;

    // ------------------------------------------------------------------ trees ({"cls":{...},"root":node})
    /// Single tree (suite/tests): the root renders inside an implicit <body> (oracle suite mode).
    bool load_tree(const QByteArray& json, QString* err = nullptr);
    bool load_tree(const JVal& tree, QString* err = nullptr);
    /// Build mode: shell.json whose root is <body> and contains {"t":"slot","id":"main"} → tab tree.
    bool set_shell(const QByteArray& json, QString* err = nullptr);
    void set_tab_tree(const QString& tabId, const QByteArray& json);
    void set_tab_loader(std::function<QByteArray(const QString& tabId)> loader);
    void set_inc_tree(const QString& key, const QByteArray& json);
    void set_inc_tree(const QString& key, const JVal& tree);
    void set_inc_loader(std::function<QByteArray(const QString& key)> loader);
    /// Convenience (key order of Qt JSON objects is alphabetical — prefer the byte overloads).
    bool load_tree(const QJsonObject& tree, QString* err = nullptr);
    void clear();

    // ------------------------------------------------------------------ state (DESIGN §4)
    void set_defaults(const QHash<QString, QString>& defaults);
    QHash<QString, QString> defaults() const;
    void reset_state();                                   ///< state = defaults
    void set_state(const QString& key, const QString& value);
    void merge_state(const QHash<QString, QString>& kv);
    void remove_state(const QString& key);
    QString get_state(const QString& key) const;
    QHash<QString, QString> state() const;
    QStringList scoped_keys() const;

    // ------------------------------------------------------------------ pipeline
    void set_viewport(float width, float height);         ///< vw/vh units + initial containing block height
    /// Resolve the render tree from the current state, then reset unrendered scoped keys (oracle commit).
    void resolve();
    /// Style + box tree + layout at `width` (resolves first when the state changed). Cheap when nothing changed.
    void layout(float width);
    bool is_laid_out() const;
    float content_width() const;                          ///< documentElement.scrollWidth
    float content_height() const;                         ///< documentElement.scrollHeight (≥ viewport height)
    QColor canvas_color() const;                          ///< page background (body/html propagated)
    /// Paint the document region `clipDoc`; the painter must map document coordinates (caller translates by
    /// −scrollY / −scrollX of the page). Nothing outside clipDoc is guaranteed to be painted.
    void paint(QPainter& p, const QRectF& clipDoc);

    // ------------------------------------------------------------------ scrolling
    void set_scroll_y(float y);                           ///< page scroll (sticky)
    float scroll_y() const;
    std::vector<ScrollRegion> scroll_regions() const;
    void set_scroll_x(int regionId, float x);             ///< clamped to [0, scrollWidth − clientWidth]
    float scroll_x(int regionId) const;
    /// Oracle rule: in each scroll region, the first node whose on.set matches the state is scrolled into view
    /// flush right (scrollLeft = max(0, ceil(right − clientWidth))); regions without one go to 0.
    void normalize_hscroll();

    // ------------------------------------------------------------------ interaction
    Action hit_test(QPointF docPoint) const;              ///< uses current scroll_y / scroll_x
    /// Apply a Set/Sort action to the state (oracle onClick). Returns true when the state changed.
    bool activate(const Action& a);
    /// Select: set the bound key to `value`. Returns true when the state changed.
    bool choose_option(const Action& a, const QString& value);
    /// Oracle `$click`: click the first rendered element (document order) whose `key` is `key` — its `on`
    /// handler and every ancestor's run (bubbling), then one render. Returns false when no such element.
    bool click_key(const QString& key);

    // ------------------------------------------------------------------ inspection
    /// {"width","height","nodes":[{p,t,key,x,y,w,h}],"texts":[{p,text,rects}]} like ChbOracle.dump().
    QString dump_geometry_json() const;
    QString plain_text() const;                           ///< innerText-like (blocks → newlines)
    QStringList warnings() const;
    Timing last_timing() const;

    struct Impl; ///< opaque (engine internals, ChbDom_p.h)

  private:
    std::unique_ptr<Impl> d;
};

} // namespace fincept::screens::chb
