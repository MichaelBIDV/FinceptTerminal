// src/screens/msn_reflex/MsnReflexPanel.h
// Chaebol Reflex, "hồ sơ độ trễ chaebol": the parent–child lag casebook of the 32 ownership groups of Chaebol
// Map, plus a TỔNG QUAN page. The tab id stays "msn_reflex" (factory key, saved dock layouts, the ALL-IN-ONE
// tile). Each group page is a frozen dossier (knowledge_os/chaebol_reflex/<id>/ho_so_*.json; Masan keeps
// knowledge_os/msn_reflex/) with LIVE blocks recomputed from local data on every run. Built on the Fincept Macro
// chassis (EconPanelBase + EconomicsService running scripts/chaebol_reflex.py).
//
// One `overview --nhom <id>` fetch (or `overview --ma <MÃ>` for a deep link) returns the whole page already
// shaped as a vnblocks/1 page (payload "trang"). meta.nhom {id, ten, …} names the group on the page and
// meta.ds_nhom [{id, ten, truc, me, co_hoi_dong}] lists every group, first "tong_quan". This panel adds a chip
// row of the groups (one row per trục), the meta line and the warnings, then hands "trang" to
// vnblocks::build_page(). The content page (one QScrollArea) is rebuilt from scratch on every successful payload
// and on theme change.
//
// The last group shown is kept in QSettings "chaebol_reflex/nhom" (default "tong_quan"; reset to it when the
// script rejects the saved group with UNKNOWN_GROUP / BAD_ARGS). activate() first takes the nav hint "msn_reflex"
// (VnNavHint.h; the ALL-IN-ONE tile leaves the ticker there) and, if one is waiting, opens that ticker's group.
// activate() runs on every show of the tab and, for a tab already on screen (navigate only raises it), on
// "nav.switch_screen" to "msn_reflex". Only the instance in the dock "msn_reflex" takes the hint, never a "#dup".
//
// Toolbar: freshness (dữ liệu đến · cập nhật hh:mm) · 🌐 BẢN GỐC · FETCH · CSV (payload csv.columns/rows).
#pragma once

#include "screens/economics/panels/EconPanelBase.h"

#include <QDateTime>
#include <QJsonObject>
#include <QList>
#include <QPointer>
#include <QString>

class QLabel;
class QPushButton;
class QScrollArea;
class QTimer;
class QWidget;

namespace fincept::screens {

class MsnReflexPanel : public EconPanelBase {
    Q_OBJECT
  public:
    explicit MsnReflexPanel(QWidget* parent = nullptr);

    /// Takes the deep-link hint first (a ticker → fetch `--ma`; dock "msn_reflex" only). Otherwise fetches when
    /// nothing is loaded yet or the last successful load is older than the refresh interval, else only
    /// re-evaluates the freshness label. Called on every show of the tab and, while visible, on a
    /// "nav.switch_screen" to this tab. FETCH always forces a refresh.
    void activate() override;

  protected:
    void build_controls(QHBoxLayout* thl) override;
    void on_fetch() override; ///< re-runs `chaebol_reflex.py overview --nhom|--ma` (cache bypassed)
    void on_result(const QString& request_id, const services::EconomicsResult& result) override;
    void refresh_panel_theme() override; ///< base restyle + toolbar restyle + page rebuild
    void retranslateUi() override;

  private:
    void apply_overview(const QJsonObject& data);
    void rebuild_page(bool keep_scroll); ///< drops the old page widget and builds a new one from data_
    QWidget* build_page();
    QWidget* build_nhom_bar(QWidget* parent); ///< chip row from meta.ds_nhom; nullptr when the list is empty

    void open_nhom(const QString& id); ///< chip click: fetch that group
    void update_nhom_chips();          ///< highlight nhom_, lock the chips while a request is in flight
    void fetch_if_due();               ///< activate() without the deep link (also the refresh timer's path)

    void render_fresh(); ///< toolbar freshness label
    void restyle_toolbar();

    void export_payload_csv();
    void open_profile_page();
    void on_refresh_tick(); ///< timer: re-evaluate data age; re-fetch when visible and due
    bool refresh_due() const;

    QJsonObject data_; ///< last successful `overview` payload
    bool loaded_ = false;
    bool fetching_ = false;        ///< an `overview` request is in flight
    bool refetch_pending_ = false; ///< a newer page was asked while a fetch was in flight (latest wins)
    QDateTime fetched_at_;         ///< UTC time of the last successful `overview`
    QTimer* refresh_timer_ = nullptr;
    // Per-instance request ids: result_ready reaches every panel, and a duplicated panel must not take another
    // instance's answer (or error) for its own. The sequence number cycles through a small ring
    // (EconomicsService keeps one dispatch record per id) and drops a late answer superseded by a newer FETCH.
    QString req_prefix_;  ///< "msn_<n>_"
    QString req_current_; ///< id of the newest `overview` request sent
    int req_seq_ = 0;

    // group selection
    QString nhom_;       ///< group asked for (`--nhom`); restored from QSettings, "tong_quan" by default
    QString shown_nhom_; ///< meta.nhom.id of the page on screen
    QString ma_;         ///< deep-link ticker of the request in flight (`--ma`); "" = by group
    QList<QPointer<QPushButton>> nhom_chips_; ///< chips of the page on screen (property "cr_nhom" = id)

    // toolbar
    QLabel* fresh_lbl_ = nullptr;
    QPushButton* web_btn_ = nullptr;

    // content page
    int page_idx_ = -1;
    QScrollArea* scroll_ = nullptr;
};

} // namespace fincept::screens
