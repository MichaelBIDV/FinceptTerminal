// src/screens/hhp_valuation/HhpTickerDialog.h
// Per-ticker "vùng định giá" window: price vs the price bands implied by the ticker's own
// P/E or P/B history (band = base × (μ ± 1σ/2σ), base = EPS or BVPS reconstructed as
// price / ratio), with YTD…ALL ranges and the forward 2026F/2027F table.
// Mirrors the modal of hhp_vn100_valuation.html (openBand / drawTickerBand / renderFwd).
// When the payload carries a per-ticker `forecast` block (knowledge_os/hhp_forecast_tickers/<TK>.json via the
// script), the chart also shows the 3-year dashed bands, ◆ price targets (one per source) and ticker keynotes.
//
// The panel owns the fetch (`hhp_valuation.py ticker <TK>`); this dialog only renders.
#pragma once

#include <QDialog>
#include <QJsonObject>
#include <QString>

class QLabel;
class QPushButton;
class QTableWidget;

namespace fincept::screens::hhp {

class HhpChart;

class HhpTickerDialog : public QDialog {
    Q_OBJECT
  public:
    /// @param metric  initial metric, "pe" | "pb"
    HhpTickerDialog(const QString& ticker, const QString& metric, QWidget* parent = nullptr);

    QString ticker() const { return ticker_; }

    void set_loading();
    void set_error(const QString& message);
    /// `data` = the JSON object printed by `hhp_valuation.py ticker <TK>`.
    void set_data(const QJsonObject& data);

  private:
    void build_ui();
    void set_metric(const QString& metric);
    void render();          ///< stats row + chart + note for the current metric
    void render_forward();  ///< forward 2026F/2027F table + rating/TP lines + S&P CapIQ block (data.row.capiq)
    /// Forecast layers of the current metric (call before chart_->set_series): chart forecast region + notes,
    /// the stat line above the chart and the basis note under it. `has_fc` = dashed series were built.
    void render_forecast(const QJsonObject& band, bool has_fc);
    void clear_forecast();  ///< hide the forecast stat line + basis note
    void update_metric_buttons();

    QString ticker_;
    QString metric_ = QStringLiteral("pe");
    QJsonObject data_;
    bool has_data_ = false;

    QPushButton* btn_pe_ = nullptr;
    QPushButton* btn_pb_ = nullptr;
    QLabel* stats_lbl_ = nullptr;   ///< rich-text stats row
    QLabel* fc_lbl_ = nullptr;      ///< forecast stat line (EPS/BVPS growth per year, band at 31/12) + warnings
    HhpChart* chart_ = nullptr;
    QLabel* fc_note_lbl_ = nullptr; ///< forecast basis per year + caveats + run time; tooltip = every source
    QTableWidget* fwd_table_ = nullptr;
    QLabel* fwd_info_lbl_ = nullptr; ///< rating · analyst · TP · source legend · note · S&P CapIQ
    QLabel* note_lbl_ = nullptr;     ///< method note + generated time + disclaimer
};

} // namespace fincept::screens::hhp
