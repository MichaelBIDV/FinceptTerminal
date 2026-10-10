#pragma once
// ChbView.h — the chaebol_map page as one scrolling widget (DESIGN.md §4, §5.1; integration.md §2.6).
//
// Loads a build written by scripts/chaebol_map.py (current.json → build dir → manifest.json → shell.json; tab trees
// and inc trees are read lazily from disk when the engine needs them), lays the page out at the widget width and
// paints the visible part. Behaviour follows the Chrome page:
//  * page scroll with thin overlay scrollbars (macOS style, no layout space taken — like Chrome's overlay bars);
//  * the sticky tab bar and nested horizontal scroll boxes (overflow-x auto): horizontal wheel / shift+wheel /
//    trackpad scroll the box under the cursor; after a click the clicked button is scrolled minimally into view;
//  * click → on.set / on.sort (bubbling), <select> → QMenu of its options, <a href> → browser (http/https only);
//  * a state change keeps the page scrollY (clamped to the new height); pointing-hand cursor on actionable nodes;
//  * no hover, no tooltip (the page has none). The canvas keeps the page's own colours (not the app theme).
// GUI thread only (the engine is not thread-safe).
#include <QHash>
#include <QImage>
#include <QJsonObject>
#include <QPointF>
#include <QRectF>
#include <QString>
#include <QStringList>
#include <QWidget>

#include <memory>

class QScrollBar;

namespace fincept::screens::chb {

class Document;
struct Action;

class ChbView : public QWidget {
    Q_OBJECT
  public:
    explicit ChbView(QWidget* parent = nullptr);
    ~ChbView() override;

    // ── loading ──────────────────────────────────────────────────────────────
    /// `chaebol_map.py build|status` result {"schema":"chaebol_map/1","build":"<dir>","manifest":{…}}.
    /// keep_state: carry the current tab / switches (when still valid) and the scroll position over to the new build.
    /// On failure the current page stays untouched and `err` gets a Vietnamese message (what + what to do).
    bool set_payload(const QJsonObject& payload, bool keep_state, QString* err = nullptr);
    /// Build directory holding manifest.json.
    bool load_build(const QString& build_dir, bool keep_state = false, QString* err = nullptr);
    /// `<state dir>/current.json` = {"build": "<dir>", "manifest": {…}}.
    bool load_current(const QString& current_json, bool keep_state = false, QString* err = nullptr);
    bool has_page() const;
    QString build_dir() const { return build_dir_; }
    QJsonObject manifest() const { return manifest_; }
    /// Absolute path of `rel` inside the build dir; "" when `rel` is empty/absolute/escapes the build dir.
    QString build_file(const QString& rel) const;

    // ── state (DESIGN §4) ────────────────────────────────────────────────────
    QString tab() const;
    QStringList tab_ids() const { return tab_ids_; } ///< manifest order
    /// Like clicking the tab button: state tab = id (sub-states of the old tab reset by scope), scrollY kept.
    bool set_tab(const QString& id);
    /// State keys (switch/filter/select) of the current tab, inventory order.
    QStringList switch_ids() const;
    QStringList options_of(const QString& key) const;
    QString state_of(const QString& key) const;
    QHash<QString, QString> state() const;     ///< full state (every key, incl. defaults)
    /// One render per call (oracle step: set → render → scope reset). Returns true when the state changed.
    bool set_state(const QString& key, const QString& value);
    bool merge_state(const QHash<QString, QString>& kv);

    // ── inspection (harness) ─────────────────────────────────────────────────
    /// Whole page at `width` × viewport height 1000, scrollY 0, horizontal boxes normalised like ref/README §1.2
    /// (active button flush right). The view's own layout/scroll state is restored afterwards.
    QImage grab_unrolled(int width) const;
    /// Oracle-format geometry dump. width > 0: in the grab_unrolled(width) state; 0: the view as shown.
    QString dump_geometry_json(int width = 0) const;
    QString plain_text() const;
    /// Files that could not be read + engine warnings (parse errors, missing classes …).
    QStringList warnings() const;

  signals:
    void tab_changed(const QString& id);

  protected:
    void paintEvent(QPaintEvent* event) override;
    void resizeEvent(QResizeEvent* event) override;
    void showEvent(QShowEvent* event) override;
    void wheelEvent(QWheelEvent* event) override;
    void mouseMoveEvent(QMouseEvent* event) override;
    void mousePressEvent(QMouseEvent* event) override;
    void mouseReleaseEvent(QMouseEvent* event) override;
    void keyPressEvent(QKeyEvent* event) override;
    void leaveEvent(QEvent* event) override;

  private:
    bool load_build_impl(const QString& dir, const QJsonObject& fallback_manifest, bool keep_state, QString* err);
    QByteArray read_build_file(const QString& rel, const QString& what) const;
    bool can_layout() const;
    void relayout();                      ///< layout at the widget size (or resolve only while hidden) + scrollbars
    void sync_scrollbars();
    void apply_pending();                 ///< scroll/reveal deferred while the view could not lay out
    void after_state_change(const QString& prev_tab, const Action* clicked, QPointF click_widget, QPointF click_doc);
    void perform(const Action& a, QPointF widget_pos, QPointF doc_pos);
    void open_select(const Action& a, QPointF widget_pos, QPointF doc_pos);
    void reveal_in_region(int region, const QRectF& target);
    void reveal_clicked(const Action& clicked, QPointF click_widget, QPointF click_doc);
    void reveal_active_buttons();         ///< each horizontal box: its active on.set button minimally into view
    int region_at(QPointF doc_pt) const;
    QPointF to_doc(QPointF widget_pt) const;
    void set_pointer(bool on);

    std::unique_ptr<Document> doc_;
    QJsonObject manifest_;
    QString build_dir_;
    QHash<QString, QString> tab_files_, inc_files_;
    QStringList tab_ids_;
    QStringList state_keys_;                   ///< inventory order
    QHash<QString, QStringList> options_;      ///< key → options
    QHash<QString, QString> key_tab_;          ///< key → tab id ("" = global / unknown)
    mutable QStringList load_errors_;
    float laid_w_ = 0, laid_h_ = 0;            ///< viewport the document is laid out for (0 = not yet)
    bool pending_layout_ = false;
    bool pending_reveal_ = false;
    int pending_scroll_y_ = -1;                ///< scrollY to restore at the first layout (reload while hidden)

    QScrollBar* vbar_ = nullptr;
    QScrollBar* hbar_ = nullptr;
    bool pointer_ = false;
    bool press_valid_ = false;
    QRectF press_rect_;
    int press_type_ = 0;
};

} // namespace fincept::screens::chb
