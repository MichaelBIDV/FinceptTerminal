// src/screens/toanvu_pe/ToanVuPePanel.h
// P/E×LS TV: "Vùng P/E × Lãi suất · Toàn Vũ". Toàn Vũ's per-stock rule (P/E ≤ rolling percentile X of its
// own 250 sessions, X = max(5, 40 − 4×(LS − 5)) with LS = VND deposit rate >12M), replicated on his own
// Bloomberg/FiinProX files, plus the Hội đồng's audit (same-date excess, independent episodes, LS
// direction, per-stock ERP). Built on the Fincept Macro chassis (EconPanelBase + EconomicsService running
// scripts/toanvu_pe.py), page rendered by vnblocks::build_page().
//
// Data is pre-built offline by scripts/toanvu_pe_build.py into fincept_bridge/state/toanvu_pe/; the
// script in the app is stdlib-only and only reads it (plus vnstore for the live P/E tile).
//
// Toolbar: MÃ (prefix-suggest ticker box, "VCB · <tên>", Enter opens the ticker page) · TỔNG QUAN
// (back to the overview page) · VNINDEX / VN30 / VN100 / VN200 / REST (scope pages, same as typing the code) · freshness ·
// FETCH · CSV (all tickers, payload csv.columns/rows).
// Every page opens with the market CỔNG line and the methodology note, then the content.
#pragma once

#include "screens/economics/panels/EconPanelBase.h"

#include <QDateTime>
#include <QJsonArray>
#include <QJsonObject>
#include <QList>
#include <QSet>
#include <QString>

class QCompleter;
class QLabel;
class QLineEdit;
class QPushButton;
class QScrollArea;
class QStandardItemModel;
class QWidget;

namespace fincept::screens {

class ToanVuPePanel : public EconPanelBase {
    Q_OBJECT
  public:
    explicit ToanVuPePanel(QWidget* parent = nullptr);

    /// Fetches when nothing is loaded yet or the last load is older than the refresh interval.
    void activate() override;

  protected:
    void build_controls(QHBoxLayout* thl) override;
    void on_fetch() override; ///< `toanvu_pe.py overview` or `ma --ma <MÃ>` (cache bypassed)
    void on_result(const QString& request_id, const services::EconomicsResult& result) override;
    void refresh_panel_theme() override;

  private:
    void apply_payload(const QJsonObject& data);
    void fill_tickers(const QJsonArray& ds_ma);
    void on_ma_entered(const QString& text);
    void open_overview();
    void rebuild_page(bool keep_scroll);
    QWidget* build_page();

    void render_fresh();
    void restyle_toolbar();
    void update_ma_style();
    void export_payload_csv();

    QJsonObject data_;
    bool loaded_ = false;
    bool fetching_ = false;
    QDateTime fetched_at_;
    QString ma_;       ///< ticker requested ("" = overview page)
    QString shown_ma_; ///< ticker of the page on screen
    QString req_prefix_; ///< "tvpe_<n>_"
    QString req_current_;
    int req_seq_ = 0;

    // toolbar
    QLineEdit* ma_edit_ = nullptr;
    QCompleter* ma_completer_ = nullptr;
    QStandardItemModel* ma_model_ = nullptr;
    QSet<QString> ds_ma_;
    bool ma_invalid_ = false;
    QPushButton* overview_btn_ = nullptr;
    QList<QPushButton*> scope_btns_; ///< VNINDEX · VN30 · VN100 · VN200 · REST
    QLabel* fresh_lbl_ = nullptr;

    // content page
    int page_idx_ = -1;
    QScrollArea* scroll_ = nullptr;
};

} // namespace fincept::screens
