// src/screens/economics/panels/FinceptMacroChartWidget.h
// Bloomberg-style Interactive Macroeconomic Chart & Table Widget
// Supports 56-year time series, Leaderboard comparisons, and 4-Economy Pulse Matrix
#pragma once

#include <QCategoryAxis>
#include <QChart>
#include <QChartView>
#include <QColor>
#include <QComboBox>
#include <QFrame>
#include <QHBoxLayout>
#include <QHeaderView>
#include <QJsonArray>
#include <QJsonObject>
#include <QLabel>
#include <QPushButton>
#include <QResizeEvent>
#include <QSplitter>
#include <QTableWidget>
#include <QVBoxLayout>
#include <QValueAxis>
#include <QVector>
#include <QWidget>

namespace fincept::screens {

enum class MacroChartType {
    Line,
    Area,
    Bar
};

enum class MacroViewLayout {
    ChartOnly,
    Split,
    TableOnly
};

struct MacroDataPoint {
    QString date;      // ISO or period string e.g. "2026-06-01" or "1990"
    double value;      // numeric observation
    QString raw_date;
    QString unit;
    QString change_str;
};

class FinceptMacroChartWidget : public QWidget {
    Q_OBJECT
  public:
    explicit FinceptMacroChartWidget(QWidget* parent = nullptr);

    /// Set time series data (for Max Historical Series mode)
    void set_time_series(const QString& title, const QString& unit,
                        const QVector<MacroDataPoint>& points,
                        const QString& country_code = "VN");

    /// Set leaderboard data (comparison of top indicators for a country)
    void set_leaderboard(const QString& country_name, const QJsonArray& items,
                         const QString& country_code = "VN");

    /// Set pulse matrix data (cross-country comparison)
    void set_pulse_matrix(const QJsonArray& pulse_items);

    /// Clear chart and table
    void clear();

  signals:
    /// Emitted when an indicator row is clicked in Leaderboard table
    void indicator_selected(int table_id, const QString& indicator_name);

  protected:
    void resizeEvent(QResizeEvent* event) override;

  private slots:
    void on_layout_btn_clicked(MacroViewLayout layout);
    void on_chart_type_clicked(MacroChartType type);
    void on_range_btn_clicked(const QString& range);
    void on_table_cell_clicked(int row, int col);

  private:
    void build_ui();
    void update_chart();
    void render_line_or_area(QChart* chart, const QVector<MacroDataPoint>& points, bool is_area);
    void render_series_bar(QChart* chart, const QVector<MacroDataPoint>& points);
    void render_leaderboard_bars(QChart* chart);
    void render_pulse_bars(QChart* chart);
    void populate_table(const QVector<MacroDataPoint>& points, const QString& unit);
    void update_stats_badges(const QVector<MacroDataPoint>& points, const QString& unit);
    void update_active_buttons_style();

    QVector<MacroDataPoint> filter_points_by_range(const QVector<MacroDataPoint>& all_pts, const QString& range);
    QColor country_color(const QString& code) const;

    // UI elements
    QWidget* top_bar_ = nullptr;
    QLabel* chart_title_lbl_ = nullptr;
    QLabel* unit_badge_lbl_ = nullptr;
    QLabel* stat_latest_lbl_ = nullptr;
    QLabel* stat_high_lbl_ = nullptr;
    QLabel* stat_low_lbl_ = nullptr;
    QLabel* stat_avg_lbl_ = nullptr;
    QLabel* stat_points_lbl_ = nullptr;
    QLabel* hover_info_lbl_ = nullptr;

    // View layout buttons
    QPushButton* btn_chart_only_ = nullptr;
    QPushButton* btn_split_ = nullptr;
    QPushButton* btn_table_only_ = nullptr;

    // Chart type buttons
    QPushButton* btn_type_line_ = nullptr;
    QPushButton* btn_type_area_ = nullptr;
    QPushButton* btn_type_bar_ = nullptr;

    // Range buttons
    QPushButton* btn_range_1y_ = nullptr;
    QPushButton* btn_range_3y_ = nullptr;
    QPushButton* btn_range_5y_ = nullptr;
    QPushButton* btn_range_10y_ = nullptr;
    QPushButton* btn_range_20y_ = nullptr;
    QPushButton* btn_range_max_ = nullptr;

    // Central Splitter & Widgets
    QSplitter* splitter_ = nullptr;
    QChartView* chart_view_ = nullptr;
    QTableWidget* data_table_ = nullptr;

    // Current State
    enum class DisplayKind { TimeSeries, Leaderboard, Pulse };
    DisplayKind display_kind_ = DisplayKind::TimeSeries;

    MacroViewLayout current_layout_ = MacroViewLayout::Split;
    MacroChartType current_chart_type_ = MacroChartType::Area;
    QString current_range_ = "MAX";
    QString current_country_code_ = "VN";
    QString current_title_;
    QString current_unit_;

    QVector<MacroDataPoint> raw_series_points_;
    QVector<MacroDataPoint> active_points_;
    QJsonArray leaderboard_items_;
    QJsonArray pulse_items_;
};

} // namespace fincept::screens
