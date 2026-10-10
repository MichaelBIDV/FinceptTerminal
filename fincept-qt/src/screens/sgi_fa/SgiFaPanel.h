// src/screens/sgi_fa/SgiFaPanel.h
// SGI FA — Trạm Quan Trắc Vĩ Mô (phương pháp Lê Chí Phúc / SGI Capital, skill deep-macro-sgi):
// the weekly issue, re-audited by the deterministic §7 engine and overlaid with live local data.
// Built on the Fincept Macro chassis (EconPanelBase + EconomicsService running scripts/sgi_fa.py).
//
// One `overview [ky]` fetch returns the whole page; this panel only lays it out. The content page
// (one QScrollArea) is rebuilt from scratch on every successful payload and on theme change,
// from the section builders in SgiSections.h, in this order:
//   meta line · CỔNG · VERDICT · I chu kỳ · II cỗ máy · III điều kiện đáy · IV tám khối ·
//   đối chiếu HHP · V bằng chứng · VI neo · VII ngưỡng · VIII danh mục · IX track record ·
//   X nghịch đảo · nguồn/cảnh báo.
//
// Toolbar: KỲ [issue combo] · freshness · 🌐 BẢN TUẦN · FETCH · CSV (payload csv.columns/rows).
#pragma once

#include "screens/economics/panels/EconPanelBase.h"

#include <QDateTime>
#include <QJsonObject>
#include <QString>

class QComboBox;
class QLabel;
class QPushButton;
class QScrollArea;
class QTimer;
class QWidget;

namespace fincept::screens {

class SgiFaPanel : public EconPanelBase {
    Q_OBJECT
  public:
    explicit SgiFaPanel(QWidget* parent = nullptr);

    /// Fetches when nothing is loaded yet or the last successful load is older than the refresh
    /// interval; otherwise only re-evaluates the freshness label. Called on every show of the tab.
    /// FETCH always forces a refresh.
    void activate() override;

  protected:
    void build_controls(QHBoxLayout* thl) override;
    void on_fetch() override; ///< re-runs `sgi_fa.py overview [ky]` (cache bypassed)
    void on_result(const QString& request_id, const services::EconomicsResult& result) override;
    void refresh_panel_theme() override; ///< base restyle + toolbar restyle + page rebuild
    void retranslateUi() override;

  private:
    void apply_overview(const QJsonObject& data);
    void rebuild_page(bool keep_scroll); ///< drops the old page widget and builds a new one from data_
    QWidget* build_page();

    void populate_issues();  ///< combo ← meta.issues (newest first), selection = displayed issue
    void render_fresh();     ///< toolbar freshness label
    void restyle_toolbar();
    void on_issue_selected(int index);

    void export_payload_csv();
    void open_issue_page();
    void on_refresh_tick(); ///< timer: re-evaluate data age; re-fetch when visible and due
    bool refresh_due() const;

    QJsonObject data_; ///< last successful `overview` payload
    bool loaded_ = false;
    bool fetching_ = false; ///< an `overview` request is in flight
    QDateTime fetched_at_;  ///< UTC time of the last successful `overview`
    QTimer* refresh_timer_ = nullptr;
    // Per-instance request ids: result_ready reaches every panel, and a duplicated SGI panel must
    // not take another instance's answer (or error) for its own. The id also carries the issue
    // date, so a late answer for an issue the user has already switched away from is dropped.
    QString req_prefix_;  ///< "sgi_<n>_"
    QString req_current_; ///< id of the newest `overview` request sent
    /// Issue explicitly chosen in the combo ("" = newest, which follows new issues as they land).
    QString requested_ky_;
    QString loaded_request_ky_; ///< requested_ky_ of the payload on screen (restored when a switch fails)

    // toolbar
    QLabel* ky_lbl_ = nullptr;
    QComboBox* issue_combo_ = nullptr;
    QLabel* fresh_lbl_ = nullptr;
    QPushButton* web_btn_ = nullptr;

    // content page
    int page_idx_ = -1;
    QScrollArea* scroll_ = nullptr;
};

} // namespace fincept::screens
