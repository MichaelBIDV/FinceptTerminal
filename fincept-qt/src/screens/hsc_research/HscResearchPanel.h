// src/screens/hsc_research/HscResearchPanel.h
// HSC RESEARCH — the HSC sell-side research store by day (kho/<ngày>.jsonl, SS-T3) with the Hội đồng's
// reading of each batch (phan_tich/<ngày>.json, EST), filled by the 12:30 T2–T6 pipeline in
// ~/SECOND BRAIN-OBSIDIAN/_System/hsc_research/. Built on the Fincept Macro chassis (EconPanelBase +
// EconomicsService running scripts/hsc_research.py).
//
// One `overview [--ngay D]` fetch returns the whole page already shaped as a vnblocks/1 page (payload
// "trang"): Cổng · I Lô (7 nhóm) · II Hội đồng · III Chuỗi khuyến nghị · IV Chuỗi thị trường · V Vĩ mô ·
// VI Sự kiện · VII Nguồn. Every chain is cut at the selected batch date, so an old batch reads as it did
// that day. This panel only adds the batch selector, a meta line, and hands "trang" to
// vnblocks::build_page().
//
// Toolbar: LÔ (batch combo, newest first, from meta.ky_list) · freshness · 🌐 TRANG CHUỖI · FETCH ·
// CSV (recommendation chain as of the batch, payload csv.columns/rows).
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

class HscResearchPanel : public EconPanelBase {
    Q_OBJECT
  public:
    explicit HscResearchPanel(QWidget* parent = nullptr);

    /// Fetches when nothing is loaded yet or the last successful load is older than the refresh
    /// interval; otherwise only re-evaluates the freshness label. Called on every show of the tab.
    void activate() override;

  protected:
    void build_controls(QHBoxLayout* thl) override;
    void on_fetch() override; ///< re-runs `hsc_research.py overview` for the selected batch (cache bypassed)
    void on_result(const QString& request_id, const services::EconomicsResult& result) override;
    void refresh_panel_theme() override;
    void retranslateUi() override;

  private:
    void apply_overview(const QJsonObject& data);
    void fill_batch_combo(); ///< from meta.ky_list, keeping the shown batch selected, signals blocked
    void on_batch_chosen(int index);
    void rebuild_page(bool keep_scroll);
    QWidget* build_page();

    void render_fresh();
    void restyle_toolbar();

    void export_payload_csv();
    void open_index_page();
    void on_refresh_tick();
    bool refresh_due() const;

    QJsonObject data_;
    bool loaded_ = false;
    bool fetching_ = false;
    QDateTime fetched_at_;
    QString batch_; ///< batch date requested ("" = newest); the newest one follows new batches on refresh
    QTimer* refresh_timer_ = nullptr;
    QString req_prefix_;  ///< "hsc_<n>_"
    QString req_current_;
    int req_seq_ = 0;

    // toolbar
    QComboBox* batch_combo_ = nullptr;
    QLabel* fresh_lbl_ = nullptr;
    QPushButton* web_btn_ = nullptr;

    // content page
    int page_idx_ = -1;
    QScrollArea* scroll_ = nullptr;
};

} // namespace fincept::screens
