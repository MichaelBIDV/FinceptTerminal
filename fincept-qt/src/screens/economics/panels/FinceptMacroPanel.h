// src/screens/economics/panels/FinceptMacroPanel.h
// Fincept Macro — Real-time & Maximum Time Series Macro Explorer (dulieukinhte.com)
// Supports Vietnam (VN), United States (US), China (CN), European Union (EU)
// Includes native Bloomberg-style QtCharts and synchronized data tables
#pragma once

#include "screens/economics/panels/EconPanelBase.h"

#include <QComboBox>
#include <QLabel>
#include <QPushButton>

namespace fincept::screens {

class FinceptMacroChartWidget;
class MacroCardGrid;

class FinceptMacroPanel : public EconPanelBase {
    Q_OBJECT
  public:
    explicit FinceptMacroPanel(QWidget* parent = nullptr);
    void activate() override;

  protected:
    void build_controls(QHBoxLayout* thl) override;
    void on_fetch() override;
    void on_result(const QString& request_id, const services::EconomicsResult& result) override;
    void changeEvent(QEvent* event) override;

  private slots:
    void on_country_changed(int index);
    void on_view_changed(int index);
    void on_indicator_changed(int index);
    void on_open_dashboard();
    void on_card_activated(int table_id, const QString& indicator_name);
    void on_chart_indicator_selected(int table_id, const QString& indicator_name);

  private:
    void retranslateUi() override;
    void update_indicator_combo();
    void set_country_by_code(const QString& code);
    void update_country_btn_styles();

    QLabel* country_lbl_ = nullptr;
    QComboBox* country_combo_ = nullptr;
    QPushButton* btn_vn_ = nullptr;
    QPushButton* btn_us_ = nullptr;
    QPushButton* btn_cn_ = nullptr;
    QPushButton* btn_eu_ = nullptr;

    QLabel* view_lbl_ = nullptr;
    QComboBox* view_combo_ = nullptr;
    QLabel* indicator_lbl_ = nullptr;
    QComboBox* indicator_combo_ = nullptr;

    QPushButton* open_dash_btn_ = nullptr;

    FinceptMacroChartWidget* chart_widget_ = nullptr;
    int chart_page_idx_ = -1;

    // Bảng thẻ chỉ tiêu — bản dựng bằng widget của fincept_macro_dashboard.html.
    MacroCardGrid* card_grid_ = nullptr;
    int card_page_idx_ = -1;
    int card_cho_ = 0; // còn bao nhiêu nền kinh tế chưa về, để biết khi nào tắt "đang nạp" 
};

} // namespace fincept::screens
