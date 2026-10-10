// src/screens/beri/BeriPanel.h
// BERI — bàn điều hành Hội đồng Cố vấn AI của Viện Nghiên cứu Kinh tế BIDV: the living version of the
// "BERI · Advisory Council v2.0" artifact (9/8/2026). The artifact froze its calendar and ledgers on the
// day it was drawn; this panel re-reads the files the Viện keeps current (beri-workspace, the 8 core
// files, the source registry, the sector pipeline) through scripts/beri.py and recomputes every
// countdown against today. Built on the Fincept Macro chassis (EconPanelBase + EconomicsService).
//
// One `overview` fetch returns the whole page; this panel only lays it out. The content page (one
// QScrollArea) is rebuilt from scratch on every successful payload and on theme change, from the
// section builders in BeriSections.h, in this order:
//   masthead · alert · I lịch · II sổ lệch · III cam kết & mốc neo · IV việc mở · V sổ nguồn ·
//   VI kho & pipeline · VII hiến chương · VIII tầng E · IX bộ máy · X quy trình · XI giá trị · footer.
//
// Toolbar: freshness · FETCH · CSV (payload csv.columns/rows). Local only — nothing leaves the machine.
#pragma once

#include "screens/economics/panels/EconPanelBase.h"

#include <QDateTime>
#include <QJsonObject>
#include <QString>

class QLabel;
class QScrollArea;
class QTimer;
class QWidget;

namespace fincept::screens {

class BeriPanel : public EconPanelBase {
    Q_OBJECT
  public:
    explicit BeriPanel(QWidget* parent = nullptr);

    /// Fetches when nothing is loaded yet or the last successful load is older than the refresh
    /// interval; otherwise only re-evaluates the freshness label. Called on every show of the tab.
    /// FETCH always forces a refresh.
    void activate() override;

  protected:
    void build_controls(QHBoxLayout* thl) override;
    void on_fetch() override; ///< re-runs `beri.py overview` (cache bypassed)
    void on_result(const QString& request_id, const services::EconomicsResult& result) override;
    void refresh_panel_theme() override; ///< base restyle + page rebuild
    void retranslateUi() override;

  private:
    void apply_overview(const QJsonObject& data);
    void rebuild_page(bool keep_scroll);
    QWidget* build_page();

    void render_fresh();
    void export_payload_csv();
    void on_refresh_tick();
    bool refresh_due() const;

    QJsonObject data_; ///< last successful `overview` payload
    bool loaded_ = false;
    bool fetching_ = false;
    QDateTime fetched_at_; ///< UTC time of the last successful `overview`
    QTimer* refresh_timer_ = nullptr;
    // Per-instance request ids: result_ready reaches every panel, and a duplicated BERI panel must not
    // take another instance's answer for its own.
    QString req_prefix_;  ///< "beri_<n>_"
    QString req_current_; ///< id of the newest `overview` request sent

    QLabel* fresh_lbl_ = nullptr;
    int page_idx_ = -1;
    QScrollArea* scroll_ = nullptr;
};

} // namespace fincept::screens
