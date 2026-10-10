// src/screens/so_nguon/SoNguonPanel.h
// Sổ nguồn — the app's data-asset ledger: freshness audit of every file/feed the tabs read, the
// problems to fix, the update schedules, the origin registry (hệ Chứng khoán / hệ BERI, never mixed)
// and the legal/rate-limit notes. Built on the Fincept Macro chassis (EconPanelBase + EconomicsService
// running scripts/so_nguon_tab.py); the script shapes the whole page (contract vnblocks/1) and this
// panel renders it with vnblocks::build_page().
//
// Commands:
//   overview   — audit + current run status → page. Run on show when due, and by AUDIT.
//   lam_moi    — FETCH: starts ONE detached refresh run of every due source (so_nguon.bat_dau_lam_moi),
//                then returns the overview with the plan.
//   trang_thai — small run-status payload {"run", "section"?}; polled every 3 s while run.dang_chay
//                (one poll in flight at most, paused while the tab is hidden). A "section" (id
//                "lam_moi") replaces that section of the page; the page is rebuilt only when a step
//                changes state. When the run ends, one `overview` refreshes the whole page.
//
// Toolbar: status (audit time / "đang làm mới k/n bước · <bước>" / "làm mới xong hh:mm · n lỗi") ·
// AUDIT · FETCH · CSV (payload csv.columns/rows).
#pragma once

#include "screens/economics/panels/EconPanelBase.h"

#include <QDateTime>
#include <QJsonObject>
#include <QString>

class QHideEvent;
class QLabel;
class QPushButton;
class QScrollArea;
class QTimer;
class QWidget;

namespace fincept::screens {

class SoNguonPanel : public EconPanelBase {
    Q_OBJECT
  public:
    explicit SoNguonPanel(QWidget* parent = nullptr);

    /// Resumes polling when a run is being followed; otherwise runs `overview` when nothing is loaded
    /// yet or the last load is older than the refresh interval. Called on every show of the tab.
    void activate() override;

  protected:
    void build_controls(QHBoxLayout* thl) override;
    void on_fetch() override; ///< FETCH → `so_nguon_tab.py lam_moi` (starts the refresh runner)
    void on_result(const QString& request_id, const services::EconomicsResult& result) override;
    void refresh_panel_theme() override; ///< base restyle + toolbar restyle + page rebuild
    void retranslateUi() override;
    void hideEvent(QHideEvent* event) override; ///< pauses the progress poll

  private:
    enum class PageCmd { Overview, LamMoi };

    void request_page(PageCmd cmd);   ///< overview / lam_moi (both return a full page)
    void apply_page(const QJsonObject& data);
    void apply_poll(const QJsonObject& data);
    void set_run(const QJsonObject& run); ///< stores run_, starts/stops polling accordingly

    void start_polling();  ///< timer runs only while visible; the first poll waits one interval
    void stop_polling();
    void on_poll_tick();
    bool run_active() const;

    void rebuild_page(bool keep_scroll);
    QWidget* build_page();

    void render_status(); ///< toolbar status label from fetching_/run_/data_
    void update_buttons();
    void restyle_toolbar();

    void export_payload_csv();
    void on_refresh_tick(); ///< timer: re-evaluate the label; re-audit when visible and due
    bool refresh_due() const;

    QJsonObject data_; ///< last successful overview / lam_moi payload (its run section kept current)
    QJsonObject run_;  ///< newest run status (from a page payload or a poll)
    QString run_key_;  ///< run id + step states of run_ — the page is rebuilt only when it changes
    bool loaded_ = false;
    bool fetching_ = false; ///< an overview / lam_moi request is in flight
    PageCmd fetching_cmd_ = PageCmd::Overview;
    QDateTime fetched_at_; ///< UTC time of the last successful page payload
    QString page_error_;   ///< last page-request error while a page is on screen ("" after a success)

    bool polling_ = false;       ///< a run is being followed (timer may be paused while hidden)
    bool poll_in_flight_ = false;
    QString poll_for_run_;  ///< run id the in-flight poll was sent for (a stale answer is dropped)
    int poll_failures_ = 0; ///< consecutive failed polls; polling gives up after a few
    QString poll_error_;    ///< last poll error once polling gave up (shown in the label tooltip)
    QTimer* poll_timer_ = nullptr;
    QTimer* refresh_timer_ = nullptr;

    // Per-instance request ids: result_ready reaches every panel, and a duplicated Sổ nguồn panel must
    // not take another instance's answer for its own. Page and poll requests are separate channels.
    QString req_prefix_; ///< "sn_<n>_"
    QString req_page_;   ///< id of the newest page request sent
    QString req_poll_;   ///< id of the poll request (at most one in flight)

    // toolbar
    QLabel* status_lbl_ = nullptr;
    QPushButton* audit_btn_ = nullptr;

    // content page
    int page_idx_ = -1;
    QScrollArea* scroll_ = nullptr;
};

} // namespace fincept::screens
