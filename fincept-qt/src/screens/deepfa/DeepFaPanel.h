// src/screens/deepfa/DeepFaPanel.h
// DEEP FA — HĐCV Deep FA research desk on the Fincept Macro chassis (EconPanelBase + EconomicsService
// running scripts/deepfa.py). Two pages inside the base content stack:
//   • Tổng quan — CỔNG banner · gates strip · triage table of the whole universe (DeepFaUniverseTable)
//   • Mã        — the research page of one ticker, rebuilt from the `ticker <TK>` payload by the
//                 section builders (DeepFaSections.h) in the spec order.
// Toolbar: MÃ [prefix-completing edit] · ◀ TỔNG QUAN · DM/State filters · deep/regen/cờ toggles ·
//          freshness · 🌐 BẢN WEB · TRẠNG THÁI (status dialog) · FETCH · CSV (visible triage rows).
// Nothing here computes a number: every value arrives pre-formatted from Python with its date and tier.
#pragma once

#include "screens/economics/panels/EconPanelBase.h"

#include <QDateTime>
#include <QJsonObject>
#include <QPointer>
#include <QString>

class QCheckBox;
class QComboBox;
class QCompleter;
class QDialog;
class QLabel;
class QLineEdit;
class QPushButton;
class QScrollArea;
class QStringListModel;
class QTimer;
class QWidget;

namespace fincept::screens {

namespace deepfa {
class DeepFaUniverseTable;
}

class DeepFaPanel : public EconPanelBase {
    Q_OBJECT
  public:
    explicit DeepFaPanel(QWidget* parent = nullptr);

    /// Fetches the overview when nothing is loaded yet or the last load is older than the refresh
    /// interval; otherwise only re-evaluates the freshness label. Called on every show of the tab.
    void activate() override;

    /// Open the research page of `ticker` (validated, upper-cased). Runs `deepfa.py ticker <TK>`.
    void open_ticker(const QString& ticker);

  protected:
    void build_controls(QHBoxLayout* thl) override;
    void on_fetch() override; ///< Enter in MÃ → open that ticker; otherwise re-run `overview` (cache bypassed)
    void on_result(const QString& request_id, const services::EconomicsResult& result) override;
    void refresh_panel_theme() override;
    void retranslateUi() override;

  private:
    void build_pages();
    void fetch_overview();
    void fetch_status();
    void apply_overview(const QJsonObject& data);
    void apply_ticker(const QString& ticker, const QJsonObject& data);
    void show_overview_page();
    void rebuild_ticker_page(bool keep_scroll);
    QWidget* build_ticker_page();
    void render_overview_top();  ///< CỔNG banner + gates strip + count
    void apply_filters();
    void render_fresh();
    void restyle_toolbar();
    void export_visible_csv();
    void open_web_page();
    void show_status_dialog(const QJsonObject& status);
    void on_refresh_tick();
    bool refresh_due() const;

    QJsonObject overview_;  ///< last successful `overview` payload
    QJsonObject ticker_;    ///< last successful `ticker` payload (the page on screen)
    QString ticker_tk_;     ///< ticker of `ticker_`
    bool loaded_ = false;
    bool fetching_ = false;
    QDateTime fetched_at_;
    QTimer* refresh_timer_ = nullptr;
    QString req_prefix_;    ///< "deepfa_<n>_"
    QString req_overview_;
    QString req_status_;
    QString req_ticker_;    ///< req_prefix_ + "tk_" (+ ticker)
    QString pending_tk_;    ///< ticker of the newest `ticker` request in flight

    // toolbar
    QLabel* ma_lbl_ = nullptr;
    QLineEdit* ma_edit_ = nullptr;
    QStringListModel* ma_model_ = nullptr;
    QCompleter* ma_completer_ = nullptr;
    QPushButton* back_btn_ = nullptr;
    QComboBox* dm_combo_ = nullptr;
    QComboBox* state_combo_ = nullptr;
    QCheckBox* deep_chk_ = nullptr;
    QCheckBox* regen_chk_ = nullptr;
    QCheckBox* flag_chk_ = nullptr;
    QLabel* fresh_lbl_ = nullptr;
    QPushButton* web_btn_ = nullptr;
    QPushButton* status_btn_ = nullptr;

    // pages
    int page_overview_idx_ = -1;
    int page_ticker_idx_ = -1;
    QWidget* overview_page_ = nullptr;
    QLabel* cong_lbl_ = nullptr;
    QLabel* gates_lbl_ = nullptr;
    QLabel* count_lbl_ = nullptr;
    deepfa::DeepFaUniverseTable* table_ = nullptr;
    QScrollArea* ticker_scroll_ = nullptr;
    QPointer<QDialog> status_dlg_;
};

} // namespace fincept::screens
