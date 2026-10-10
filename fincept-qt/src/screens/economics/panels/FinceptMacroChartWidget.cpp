// src/screens/economics/panels/FinceptMacroChartWidget.cpp
#include "screens/economics/panels/FinceptMacroChartWidget.h"

#include "ui/theme/Theme.h"

#include <QAreaSeries>
#include <QBarCategoryAxis>
#include <QBarSeries>
#include <QBarSet>
#include <QCategoryAxis>
#include <QChart>
#include <QChartView>
#include <QColor>
#include <QDateTime>
#include <QHBoxLayout>
#include <QHeaderView>
#include <QLabel>
#include <QLineSeries>
#include <QLocale>
#include <QPainter>
#include <QPushButton>
#include <QRegularExpression>
#include <QSplitter>
#include <QSet>
#include <QTableWidget>
#include <QVBoxLayout>
#include <QValueAxis>

#include <algorithm>
#include <cmath>

namespace fincept::screens {

namespace {

static QString format_num(double val) {
    if (std::abs(val) >= 1000000.0) {
        return QString("%L1").arg(val, 0, 'f', 1);
    } else if (std::abs(val) >= 1000.0) {
        return QString("%L1").arg(val, 0, 'f', 2);
    } else if (std::abs(val) >= 1.0) {
        return QString::number(val, 'f', 2);
    } else if (std::abs(val) > 0.0) {
        return QString::number(val, 'f', 3);
    } else {
        return "0";
    }
}

static QString format_y_tick(double val, const QString& unit) {
    if (unit.contains("%")) {
        return QString("%1%").arg(QString::number(val, 'f', 1));
    }
    double abs_v = std::abs(val);
    if (abs_v >= 1000000.0) {
        return QString("%1M").arg(QString::number(val / 1000000.0, 'f', 2));
    } else if (abs_v >= 10000.0) {
        return QString("%1K").arg(QString::number(val / 1000.0, 'f', 1));
    } else if (abs_v >= 1000.0) {
        return QString("%1K").arg(QString::number(val / 1000.0, 'f', 2));
    } else if (abs_v >= 10.0) {
        return QString::number(val, 'f', 1);
    } else if (abs_v >= 1.0) {
        return QString::number(val, 'f', 2);
    } else if (abs_v > 0.0) {
        return QString::number(val, 'f', 3);
    } else {
        return "0";
    }
}

static void style_chart_base(QChart* chart) {
    chart->setBackgroundBrush(QBrush(QColor("#080c14")));
    chart->setPlotAreaBackgroundBrush(QBrush(QColor("#03060a")));
    chart->setPlotAreaBackgroundVisible(true);
    chart->setMargins(QMargins(8, 8, 8, 8));
    chart->legend()->setVisible(false);
}

static double extract_display_number(QString text) {
    text.replace(QChar(0x2212), "-");
    text.remove(' ');
    text.replace(',', '.');

    static const QRegularExpression number_re(QStringLiteral("[-+]?\\d+(?:\\.\\d+)?"));
    const auto match = number_re.match(text);
    if (!match.hasMatch())
        return 0.0;

    bool ok = false;
    const double value = match.captured(0).toDouble(&ok);
    return ok ? value : 0.0;
}

static double pulse_metric_value(const QJsonObject& obj, const QString& numeric_key, const QString& display_key) {
    const auto numeric = obj.value(numeric_key);
    if (numeric.isDouble())
        return numeric.toDouble();
    if (numeric.isString()) {
        bool ok = false;
        const double value = numeric.toString().toDouble(&ok);
        if (ok)
            return value;
    }
    return extract_display_number(obj.value(display_key).toString());
}

} // namespace

FinceptMacroChartWidget::FinceptMacroChartWidget(QWidget* parent)
    : QWidget(parent) {
    build_ui();
}

QColor FinceptMacroChartWidget::country_color(const QString& code) const {
    if (code == "VN") return QColor("#f59e0b"); // Amber / Gold
    if (code == "US") return QColor("#06b6d4"); // Cyan
    if (code == "CN") return QColor("#f43f5e"); // Rose / Red
    if (code == "EU") return QColor("#10b981"); // Emerald
    return QColor("#f59e0b");
}

void FinceptMacroChartWidget::build_ui() {
    auto* root = new QVBoxLayout(this);
    root->setContentsMargins(0, 0, 0, 0);
    root->setSpacing(0);
    setStyleSheet("background: #080c14; color: #f8fafc;");

    // ── 1. Top Control Bar ────────────────────────────────────────────────────
    top_bar_ = new QWidget(this);
    top_bar_->setFixedHeight(42);
    top_bar_->setStyleSheet("background: #0d131f; border-bottom: 1px solid #1e293b;");
    auto* thl = new QHBoxLayout(top_bar_);
    thl->setContentsMargins(10, 0, 10, 0);
    thl->setSpacing(6);

    chart_title_lbl_ = new QLabel(tr("ĐỒ THỊ VĨ MÔ"));
    chart_title_lbl_->setStyleSheet("color: #f59e0b; font-size: 13px; font-weight: 800; letter-spacing: 0.5px;");
    thl->addWidget(chart_title_lbl_);

    unit_badge_lbl_ = new QLabel("");
    unit_badge_lbl_->setStyleSheet(
        "background: rgba(6, 182, 212, 0.15); color: #06b6d4; font-family: 'Consolas', monospace; "
        "font-size: 10px; font-weight: 800; padding: 2px 6px; border-radius: 3px; border: 1px solid rgba(6, 182, 212, 0.3);"
    );
    unit_badge_lbl_->setVisible(false);
    thl->addWidget(unit_badge_lbl_);

    thl->addSpacing(10);

    // View layout buttons: [📈 ĐỒ THỊ] | [⚡ CHIA ĐÔI] | [📋 BẢNG]
    auto make_tool_btn = [](const QString& text, const QString& tip) {
        auto* btn = new QPushButton(text);
        btn->setFixedHeight(24);
        btn->setCursor(Qt::PointingHandCursor);
        btn->setToolTip(tip);
        return btn;
    };

    btn_chart_only_ = make_tool_btn("📈 ĐỒ THỊ", tr("Chỉ xem biểu đồ toàn màn hình"));
    btn_split_ = make_tool_btn("⚡ CHIA ĐÔI", tr("Xem kết hợp biểu đồ + bảng số liệu"));
    btn_table_only_ = make_tool_btn("📋 BẢNG", tr("Chỉ xem bảng số liệu chi tiết"));

    connect(btn_chart_only_, &QPushButton::clicked, this, [this]() { on_layout_btn_clicked(MacroViewLayout::ChartOnly); });
    connect(btn_split_, &QPushButton::clicked, this, [this]() { on_layout_btn_clicked(MacroViewLayout::Split); });
    connect(btn_table_only_, &QPushButton::clicked, this, [this]() { on_layout_btn_clicked(MacroViewLayout::TableOnly); });

    thl->addWidget(btn_chart_only_);
    thl->addWidget(btn_split_);
    thl->addWidget(btn_table_only_);

    thl->addSpacing(8);

    // Chart Type buttons: [LINE] | [AREA] | [BAR]
    btn_type_line_ = make_tool_btn("LINE", tr("Biểu đồ đường"));
    btn_type_area_ = make_tool_btn("AREA", tr("Biểu đồ vùng có đổ bóng"));
    btn_type_bar_ = make_tool_btn("BAR", tr("Biểu đồ cột"));

    connect(btn_type_line_, &QPushButton::clicked, this, [this]() { on_chart_type_clicked(MacroChartType::Line); });
    connect(btn_type_area_, &QPushButton::clicked, this, [this]() { on_chart_type_clicked(MacroChartType::Area); });
    connect(btn_type_bar_, &QPushButton::clicked, this, [this]() { on_chart_type_clicked(MacroChartType::Bar); });

    thl->addWidget(btn_type_line_);
    thl->addWidget(btn_type_area_);
    thl->addWidget(btn_type_bar_);

    thl->addSpacing(8);

    // Range buttons: 1Y | 3Y | 5Y | 10Y | 20Y | MAX
    btn_range_1y_ = make_tool_btn("1Y", tr("1 Năm gần nhất"));
    btn_range_3y_ = make_tool_btn("3Y", tr("3 Năm gần nhất"));
    btn_range_5y_ = make_tool_btn("5Y", tr("5 Năm gần nhất"));
    btn_range_10y_ = make_tool_btn("10Y", tr("10 Năm gần nhất"));
    btn_range_20y_ = make_tool_btn("20Y", tr("20 Năm gần nhất"));
    btn_range_max_ = make_tool_btn("MAX", tr("Toàn bộ lịch sử tối đa"));

    auto hook_range = [this](QPushButton* b, const QString& r) {
        connect(b, &QPushButton::clicked, this, [this, r]() { on_range_btn_clicked(r); });
    };
    hook_range(btn_range_1y_, "1Y");
    hook_range(btn_range_3y_, "3Y");
    hook_range(btn_range_5y_, "5Y");
    hook_range(btn_range_10y_, "10Y");
    hook_range(btn_range_20y_, "20Y");
    hook_range(btn_range_max_, "MAX");

    thl->addWidget(btn_range_1y_);
    thl->addWidget(btn_range_3y_);
    thl->addWidget(btn_range_5y_);
    thl->addWidget(btn_range_10y_);
    thl->addWidget(btn_range_20y_);
    thl->addWidget(btn_range_max_);

    thl->addStretch(1);

    // Hover readout badge
    hover_info_lbl_ = new QLabel("📍 SẴN SÀNG");
    hover_info_lbl_->setStyleSheet(
        "background: rgba(15, 23, 42, 0.8); color: #38bdf8; font-family: 'Consolas', 'Courier New', monospace; "
        "font-size: 11px; font-weight: 700; padding: 3px 10px; border-radius: 4px; border: 1px solid #1e293b;"
    );
    thl->addWidget(hover_info_lbl_);

    root->addWidget(top_bar_);

    // ── 2. Stat Banner ────────────────────────────────────────────────────────
    auto* banner = new QWidget(this);
    banner->setFixedHeight(32);
    banner->setStyleSheet("background: #090e17; border-bottom: 1px solid #1e293b;");
    auto* bhl = new QHBoxLayout(banner);
    bhl->setContentsMargins(12, 0, 12, 0);
    bhl->setSpacing(16);

    auto make_stat = [](const QString& label, QLabel*& val_lbl) {
        auto* w = new QWidget;
        auto* hl = new QHBoxLayout(w);
        hl->setContentsMargins(0, 0, 0, 0);
        hl->setSpacing(4);
        auto* l = new QLabel(label);
        l->setStyleSheet("color: #64748b; font-size: 9px; font-weight: 800;");
        val_lbl = new QLabel("—");
        val_lbl->setStyleSheet("color: #f8fafc; font-size: 11px; font-weight: 700; font-family: 'Consolas', monospace;");
        hl->addWidget(l);
        hl->addWidget(val_lbl);
        return w;
    };

    bhl->addWidget(make_stat("MỚI NHẤT:", stat_latest_lbl_));
    bhl->addWidget(make_stat("ĐỈNH CAO NHẤT:", stat_high_lbl_));
    bhl->addWidget(make_stat("ĐÁY THẤP NHẤT:", stat_low_lbl_));
    bhl->addWidget(make_stat("TRUNG BÌNH:", stat_avg_lbl_));
    bhl->addWidget(make_stat("QUAN SÁT:", stat_points_lbl_));
    bhl->addStretch(1);

    root->addWidget(banner);

    // ── 3. Central Splitter (Chart + Table) ───────────────────────────────────
    splitter_ = new QSplitter(Qt::Vertical, this);
    splitter_->setHandleWidth(4);
    splitter_->setStyleSheet(
        "QSplitter::handle { background: #1e293b; }"
        "QSplitter::handle:hover { background: #d97706; }"
    );

    // Chart View
    chart_view_ = new QChartView(this);
    chart_view_->setRenderHint(QPainter::Antialiasing, true);
    chart_view_->setSizePolicy(QSizePolicy::Expanding, QSizePolicy::Expanding);
    auto* blank_chart = new QChart();
    style_chart_base(blank_chart);
    blank_chart->setTitle(tr("CHƯA CÓ DỮ LIỆU ĐỒ THỊ"));
    blank_chart->setTitleFont(QFont("Consolas", 11, QFont::Bold));
    blank_chart->setTitleBrush(QBrush(QColor("#64748b")));
    chart_view_->setChart(blank_chart);
    splitter_->addWidget(chart_view_);

    // Data Table
    data_table_ = new QTableWidget(this);
    data_table_->setEditTriggers(QAbstractItemView::NoEditTriggers);
    data_table_->setSelectionBehavior(QAbstractItemView::SelectRows);
    data_table_->verticalHeader()->setVisible(false);
    data_table_->setAlternatingRowColors(true);
    data_table_->setShowGrid(true);
    data_table_->setStyleSheet(
        "QTableWidget { background: #080c14; color: #cbd5e1; border: none; gridline-color: #1e293b; font-size: 11px; alternate-background-color: #0d131f; }"
        "QTableWidget::item { padding: 4px 8px; border-bottom: 1px solid #1e293b; }"
        "QTableWidget::item:selected { background: rgba(217, 119, 6, 0.2); color: #f59e0b; }"
        "QHeaderView::section { background: #0e1726; color: #94a3b8; border: none; border-bottom: 2px solid #1e293b; border-right: 1px solid #1e293b; padding: 5px 8px; font-size: 10px; font-weight: 700; }"
        "QScrollBar:vertical { background: #080c14; width: 6px; }"
        "QScrollBar::handle:vertical { background: #334155; min-height: 20px; border-radius: 3px; }"
    );
    connect(data_table_, &QTableWidget::cellClicked, this, &FinceptMacroChartWidget::on_table_cell_clicked);
    splitter_->addWidget(data_table_);

    root->addWidget(splitter_, 1);

    // Initial sizes for split (60% chart, 40% table)
    splitter_->setSizes({550, 350});

    update_active_buttons_style();
}

void FinceptMacroChartWidget::update_active_buttons_style() {
    auto set_btn_style = [](QPushButton* btn, bool active) {
        if (!btn) return;
        if (active) {
            btn->setStyleSheet(
                "QPushButton { background: #d97706; color: #ffffff; font-weight: bold; border-radius: 3px; padding: 2px 7px; border: 1px solid #f59e0b; font-size: 10px; }"
            );
        } else {
            btn->setStyleSheet(
                "QPushButton { background: rgba(255,255,255,0.06); color: #94a3b8; border-radius: 3px; padding: 2px 7px; border: 1px solid rgba(255,255,255,0.08); font-size: 10px; }"
                "QPushButton:hover { background: rgba(255,255,255,0.12); color: #ffffff; }"
            );
        }
    };

    // Layout
    set_btn_style(btn_chart_only_, current_layout_ == MacroViewLayout::ChartOnly);
    set_btn_style(btn_split_, current_layout_ == MacroViewLayout::Split);
    set_btn_style(btn_table_only_, current_layout_ == MacroViewLayout::TableOnly);

    // Chart Type
    set_btn_style(btn_type_line_, current_chart_type_ == MacroChartType::Line);
    set_btn_style(btn_type_area_, current_chart_type_ == MacroChartType::Area);
    set_btn_style(btn_type_bar_, current_chart_type_ == MacroChartType::Bar);

    // Range
    set_btn_style(btn_range_1y_, current_range_ == "1Y");
    set_btn_style(btn_range_3y_, current_range_ == "3Y");
    set_btn_style(btn_range_5y_, current_range_ == "5Y");
    set_btn_style(btn_range_10y_, current_range_ == "10Y");
    set_btn_style(btn_range_20y_, current_range_ == "20Y");
    set_btn_style(btn_range_max_, current_range_ == "MAX");
}

void FinceptMacroChartWidget::on_layout_btn_clicked(MacroViewLayout layout) {
    current_layout_ = layout;
    if (layout == MacroViewLayout::ChartOnly) {
        chart_view_->show();
        data_table_->hide();
    } else if (layout == MacroViewLayout::TableOnly) {
        chart_view_->hide();
        data_table_->show();
    } else {
        chart_view_->show();
        data_table_->show();
        splitter_->setSizes({550, 350});
    }
    update_active_buttons_style();
}

void FinceptMacroChartWidget::on_chart_type_clicked(MacroChartType type) {
    current_chart_type_ = type;
    update_active_buttons_style();
    update_chart();
}

void FinceptMacroChartWidget::on_range_btn_clicked(const QString& range) {
    current_range_ = range;
    update_active_buttons_style();
    if (display_kind_ == DisplayKind::TimeSeries) {
        active_points_ = filter_points_by_range(raw_series_points_, current_range_);
        update_chart();
        populate_table(active_points_, current_unit_);
        update_stats_badges(active_points_, current_unit_);
    }
}

void FinceptMacroChartWidget::on_table_cell_clicked(int row, int /*col*/) {
    if (display_kind_ == DisplayKind::Leaderboard) {
        if (row >= 0 && row < leaderboard_items_.size()) {
            QJsonObject obj = leaderboard_items_[row].toObject();
            int table_id = obj["MÃ BẢNG"].toInt();
            QString name = obj["CHỈ TIÊU"].toString();
            if (table_id > 0) {
                emit indicator_selected(table_id, name);
            }
        }
    }
}

QVector<MacroDataPoint> FinceptMacroChartWidget::filter_points_by_range(
    const QVector<MacroDataPoint>& all_pts, const QString& range) {
    if (range == "MAX" || all_pts.isEmpty()) {
        return all_pts;
    }

    int count = static_cast<int>(all_pts.size());
    int desired_points = count;

    if (range == "1Y") desired_points = std::min(count, 12);
    else if (range == "3Y") desired_points = std::min(count, 36);
    else if (range == "5Y") desired_points = std::min(count, 60);
    else if (range == "10Y") desired_points = std::min(count, 120);
    else if (range == "20Y") desired_points = std::min(count, 240);

    return all_pts.mid(count - desired_points);
}

void FinceptMacroChartWidget::set_time_series(
    const QString& title, const QString& unit,
    const QVector<MacroDataPoint>& points, const QString& country_code) {
    display_kind_ = DisplayKind::TimeSeries;
    current_country_code_ = country_code;
    current_title_ = title;
    current_unit_ = (unit.isEmpty() || unit == "—") ? "" : unit;

    // Series points from server might be reverse chronological (newest first).
    // Chart must flow left to right (oldest to newest).
    raw_series_points_ = points;
    if (raw_series_points_.size() >= 2) {
        if (raw_series_points_.first().date > raw_series_points_.last().date) {
            std::reverse(raw_series_points_.begin(), raw_series_points_.end());
        }
    }

    active_points_ = filter_points_by_range(raw_series_points_, current_range_);

    chart_title_lbl_->setText(title);
    chart_title_lbl_->setStyleSheet(QString("color: %1; font-size: 13px; font-weight: 800;").arg(country_color(country_code).name()));

    if (!current_unit_.isEmpty()) {
        unit_badge_lbl_->setText(QString("ĐƠN VỊ: %1").arg(current_unit_));
        unit_badge_lbl_->setVisible(true);
    } else {
        unit_badge_lbl_->setVisible(false);
    }

    update_stats_badges(active_points_, current_unit_);
    populate_table(active_points_, current_unit_);
    update_chart();
}

void FinceptMacroChartWidget::update_stats_badges(const QVector<MacroDataPoint>& points, const QString& unit) {
    if (points.isEmpty()) {
        stat_latest_lbl_->setText("—");
        stat_high_lbl_->setText("—");
        stat_low_lbl_->setText("—");
        stat_avg_lbl_->setText("—");
        stat_points_lbl_->setText("0 mốc");
        return;
    }

    double min_v = points[0].value;
    double max_v = points[0].value;
    double sum = 0.0;
    QString min_date = points[0].date;
    QString max_date = points[0].date;

    for (const auto& p : points) {
        if (p.value < min_v) {
            min_v = p.value;
            min_date = p.date;
        }
        if (p.value > max_v) {
            max_v = p.value;
            max_date = p.date;
        }
        sum += p.value;
    }

    double avg_v = sum / points.size();
    const auto& latest = points.last();

    QString u_suffix = unit.isEmpty() ? "" : " " + unit;

    stat_latest_lbl_->setText(QString("%1%2 (%3)").arg(format_num(latest.value), u_suffix, latest.date));
    stat_high_lbl_->setText(QString("%1%2 (%3)").arg(format_num(max_v), u_suffix, max_date));
    stat_low_lbl_->setText(QString("%1%2 (%3)").arg(format_num(min_v), u_suffix, min_date));
    stat_avg_lbl_->setText(QString("%1%2").arg(format_num(avg_v), u_suffix));
    stat_points_lbl_->setText(QString("%1 mốc (%2 → %3)").arg(points.size()).arg(points.first().date, points.last().date));
}

void FinceptMacroChartWidget::populate_table(const QVector<MacroDataPoint>& points, const QString& unit) {
    data_table_->clear();
    data_table_->setColumnCount(4);
    data_table_->setHorizontalHeaderLabels({"KỲ QUAN SÁT", "GIÁ TRỊ", "ĐƠN VỊ", "BIẾN ĐỘNG / TĂNG TRƯỞNG"});
    data_table_->setRowCount(points.size());

    QString col_unit = unit.isEmpty() ? "—" : unit;

    // Populate reverse chronological in table (newest at top)
    for (int i = 0; i < points.size(); ++i) {
        int pt_idx = points.size() - 1 - i;
        const auto& p = points[pt_idx];

        auto* item_date = new QTableWidgetItem(p.date);
        item_date->setTextAlignment(Qt::AlignCenter);

        auto* item_val = new QTableWidgetItem(format_num(p.value));
        item_val->setTextAlignment(Qt::AlignRight | Qt::AlignVCenter);
        item_val->setForeground(QColor("#f8fafc"));
        item_val->setFont(QFont("Consolas", 10, QFont::Bold));

        QString row_unit = (!p.unit.isEmpty() && p.unit != "—") ? p.unit : col_unit;
        auto* item_unit = new QTableWidgetItem(row_unit);
        item_unit->setTextAlignment(Qt::AlignCenter);
        item_unit->setForeground(QColor("#38bdf8"));
        item_unit->setFont(QFont("Consolas", 9, QFont::Bold));

        // Delta vs previous observation
        QString delta_str = "—";
        QColor delta_col = QColor("#94a3b8");
        if (pt_idx > 0) {
            double prev = points[pt_idx - 1].value;
            if (std::abs(prev) > 1e-9) {
                double pct = ((p.value - prev) / std::abs(prev)) * 100.0;
                delta_str = QString("%1%2%").arg(pct >= 0 ? "+" : "").arg(QString::number(pct, 'f', 2));
                delta_col = pct >= 0 ? QColor("#10b981") : QColor("#ef4444");
            }
        }

        auto* item_delta = new QTableWidgetItem(delta_str);
        item_delta->setTextAlignment(Qt::AlignRight | Qt::AlignVCenter);
        item_delta->setForeground(delta_col);
        item_delta->setFont(QFont("Consolas", 10, QFont::Bold));

        data_table_->setItem(i, 0, item_date);
        data_table_->setItem(i, 1, item_val);
        data_table_->setItem(i, 2, item_unit);
        data_table_->setItem(i, 3, item_delta);
    }

    data_table_->horizontalHeader()->setSectionResizeMode(0, QHeaderView::ResizeToContents);
    data_table_->horizontalHeader()->setSectionResizeMode(1, QHeaderView::ResizeToContents);
    data_table_->horizontalHeader()->setSectionResizeMode(2, QHeaderView::ResizeToContents);
    data_table_->horizontalHeader()->setSectionResizeMode(3, QHeaderView::Stretch);
}

void FinceptMacroChartWidget::set_leaderboard(
    const QString& country_name, const QJsonArray& items, const QString& country_code) {
    display_kind_ = DisplayKind::Leaderboard;
    current_country_code_ = country_code;
    current_unit_ = "%";
    leaderboard_items_ = items;

    chart_title_lbl_->setText(tr("CHỈ TIÊU ĐẦU BẢNG: %1").arg(country_name));
    chart_title_lbl_->setStyleSheet(QString("color: %1; font-size: 13px; font-weight: 800;").arg(country_color(country_code).name()));

    unit_badge_lbl_->setText("ĐƠN VỊ: % SO CÙNG KỲ");
    unit_badge_lbl_->setVisible(true);

    stat_latest_lbl_->setText(tr("%1 Chỉ tiêu kinh tế then chốt").arg(items.size()));
    stat_high_lbl_->setText(tr("Click dòng để xem đồ thị lịch sử 56 năm"));
    stat_low_lbl_->setText("—");
    stat_avg_lbl_->setText("dulieukinhte.com");
    stat_points_lbl_->setText(QString("%1 chỉ tiêu").arg(items.size()));

    // Populate Leaderboard Table
    data_table_->clear();
    data_table_->setColumnCount(6);
    data_table_->setHorizontalHeaderLabels({"CHỈ TIÊU KINH TẾ", "KỲ CÔNG BỐ", "GIÁ TRỊ", "ĐƠN VỊ", "BIẾN ĐỘNG", "XU HƯỚNG"});
    data_table_->setRowCount(items.size());

    for (int i = 0; i < items.size(); ++i) {
        QJsonObject obj = items[i].toObject();
        QString name = obj["CHỈ TIÊU"].toString();
        QString period = obj["KỲ BÁO CÁO"].toString();
        QString val = obj["GIÁ TRỊ"].toString();
        QString unit = obj["ĐƠN VỊ"].toString();
        QString delta = obj["BIẾN ĐỘNG"].toString();
        QString trend = obj["XU HƯỚNG"].toString();

        auto* i_name = new QTableWidgetItem(name);
        i_name->setFont(QFont("Consolas", 10, QFont::Bold));
        i_name->setForeground(QColor("#f8fafc"));

        auto* i_per = new QTableWidgetItem(period);
        i_per->setTextAlignment(Qt::AlignCenter);

        auto* i_val = new QTableWidgetItem(val);
        i_val->setTextAlignment(Qt::AlignRight | Qt::AlignVCenter);
        i_val->setFont(QFont("Consolas", 10, QFont::Bold));
        i_val->setForeground(country_color(country_code));

        auto* i_unit = new QTableWidgetItem(unit);
        i_unit->setTextAlignment(Qt::AlignCenter);
        i_unit->setForeground(QColor("#38bdf8"));
        i_unit->setFont(QFont("Consolas", 9, QFont::Bold));

        auto* i_delta = new QTableWidgetItem(delta);
        i_delta->setTextAlignment(Qt::AlignRight | Qt::AlignVCenter);
        i_delta->setFont(QFont("Consolas", 10, QFont::Bold));
        if (delta.contains("-") || delta.contains("−")) {
            i_delta->setForeground(QColor("#ef4444"));
        } else if (delta.contains("+")) {
            i_delta->setForeground(QColor("#10b981"));
        }

        auto* i_trend = new QTableWidgetItem(trend);
        i_trend->setTextAlignment(Qt::AlignCenter);
        if (trend.contains("TĂNG")) i_trend->setForeground(QColor("#10b981"));
        else if (trend.contains("GIẢM")) i_trend->setForeground(QColor("#ef4444"));

        data_table_->setItem(i, 0, i_name);
        data_table_->setItem(i, 1, i_per);
        data_table_->setItem(i, 2, i_val);
        data_table_->setItem(i, 3, i_unit);
        data_table_->setItem(i, 4, i_delta);
        data_table_->setItem(i, 5, i_trend);
    }

    data_table_->horizontalHeader()->setSectionResizeMode(0, QHeaderView::Stretch);
    data_table_->horizontalHeader()->setSectionResizeMode(1, QHeaderView::ResizeToContents);
    data_table_->horizontalHeader()->setSectionResizeMode(2, QHeaderView::ResizeToContents);
    data_table_->horizontalHeader()->setSectionResizeMode(3, QHeaderView::ResizeToContents);
    data_table_->horizontalHeader()->setSectionResizeMode(4, QHeaderView::ResizeToContents);
    data_table_->horizontalHeader()->setSectionResizeMode(5, QHeaderView::ResizeToContents);

    update_chart();
}

void FinceptMacroChartWidget::set_pulse_matrix(const QJsonArray& pulse_items) {
    display_kind_ = DisplayKind::Pulse;
    pulse_items_ = pulse_items;
    current_unit_ = "%";

    chart_title_lbl_->setText(tr("MA TRẬN VĨ MÔ SO SÁNH 04 NỀN KINH TẾ"));
    chart_title_lbl_->setStyleSheet("color: #38bdf8; font-size: 13px; font-weight: 800;");

    unit_badge_lbl_->setText("ĐƠN VỊ: % TĂNG TRƯỞNG / LÃI SUẤT");
    unit_badge_lbl_->setVisible(true);

    stat_latest_lbl_->setText("4 Nền kinh tế trụ cột");
    stat_high_lbl_->setText("Việt Nam · Hoa Kỳ · Trung Quốc · Châu Âu");
    stat_low_lbl_->setText("—");
    stat_avg_lbl_->setText("So sánh tương quan");
    stat_points_lbl_->setText("4 thực thể");

    data_table_->clear();
    data_table_->setColumnCount(6);
    data_table_->setHorizontalHeaderLabels({"NỀN KINH TẾ", "TĂNG TRƯỞNG GDP", "LẠM PHÁT (CPI)", "LÃI SUẤT ĐIỀU HÀNH", "TỶ LỆ THẤT NGHIỆP", "DẢI QUAN SÁT"});
    data_table_->setRowCount(pulse_items.size());

    for (int i = 0; i < pulse_items.size(); ++i) {
        QJsonObject obj = pulse_items[i].toObject();
        data_table_->setItem(i, 0, new QTableWidgetItem(obj["NỀN KINH TẾ"].toString()));
        data_table_->setItem(i, 1, new QTableWidgetItem(obj["GDP"].toString()));
        data_table_->setItem(i, 2, new QTableWidgetItem(obj["LẠM PHÁT"].toString()));
        data_table_->setItem(i, 3, new QTableWidgetItem(obj["LÃI SUẤT"].toString()));
        data_table_->setItem(i, 4, new QTableWidgetItem(obj["THẤT NGHIỆP"].toString()));
        data_table_->setItem(i, 5, new QTableWidgetItem(obj["DẢI QUAN SÁT"].toString()));
    }

    for (int c = 0; c < 6; ++c) {
        data_table_->horizontalHeader()->setSectionResizeMode(c, QHeaderView::Stretch);
    }

    update_chart();
}

void FinceptMacroChartWidget::update_chart() {
    auto* chart = new QChart();
    style_chart_base(chart);

    if (display_kind_ == DisplayKind::TimeSeries) {
        if (active_points_.isEmpty()) {
            chart->setTitle(tr("KHÔNG CÓ DỮ LIỆU ĐỒ THỊ CHO CHỈ TIÊU NÀY"));
        } else if (current_chart_type_ == MacroChartType::Bar) {
            render_series_bar(chart, active_points_);
        } else {
            render_line_or_area(chart, active_points_, current_chart_type_ == MacroChartType::Area);
        }
    } else if (display_kind_ == DisplayKind::Leaderboard) {
        render_leaderboard_bars(chart);
    } else if (display_kind_ == DisplayKind::Pulse) {
        render_pulse_bars(chart);
    }

    QChart* old = chart_view_->chart();
    chart_view_->setChart(chart);
    if (old) old->deleteLater();
}

void FinceptMacroChartWidget::render_line_or_area(
    QChart* chart, const QVector<MacroDataPoint>& points, bool is_area) {
    if (points.isEmpty()) return;

    double y_min = points[0].value;
    double y_max = points[0].value;
    double sum = 0.0;

    for (const auto& p : points) {
        y_min = std::min(y_min, p.value);
        y_max = std::max(y_max, p.value);
        sum += p.value;
    }
    double avg_val = sum / points.size();

    double span = y_max - y_min;
    if (span <= 0.0) span = std::abs(y_min) * 0.1 + 1.0;
    double y_pad = span * 0.08;

    // Floor clamping: if data is non-negative, don't let axis dip below zero!
    double bottom_y = (y_min >= 0.0) ? std::max(0.0, y_min - y_pad) : (y_min - y_pad);
    double top_y = y_max + y_pad;

    // ── Y Axis (Clean Bloomberg formatting — NO scientific e+06!) ─────────────
    auto* y_axis = new QCategoryAxis();
    y_axis->setLabelsPosition(QCategoryAxis::AxisLabelsPositionOnValue);
    double y_span = top_y - bottom_y;
    if (y_span <= 1e-6) {
        y_span = std::abs(bottom_y) * 0.1 + 1.0;
        top_y = bottom_y + y_span;
    }
    double delta_start = y_span * 0.001;
    y_axis->setRange(bottom_y, top_y);
    y_axis->setStartValue(bottom_y - delta_start);

    const int y_tick_count = 6;
    double y_step = y_span / (y_tick_count - 1);
    for (int t = 0; t < y_tick_count; ++t) {
        double v = bottom_y + t * y_step;
        QString lbl = format_y_tick(v, current_unit_);
        y_axis->append(lbl, v);
    }

    y_axis->setLabelsColor(QColor("#94a3b8"));
    y_axis->setGridLineColor(QColor("#1e293b"));
    y_axis->setLinePen(QPen(QColor("#334155")));

    if (!current_unit_.isEmpty()) {
        y_axis->setTitleText(QString("[%1]").arg(current_unit_));
        y_axis->setTitleVisible(true);
        y_axis->setTitleBrush(QBrush(QColor("#38bdf8")));
        y_axis->setTitleFont(QFont("Consolas", 9, QFont::Bold));
    }
    chart->addAxis(y_axis, Qt::AlignLeft);

    // ── X Axis (Clean multi-year / quarterly date labels) ─────────────────────
    auto* x_axis = new QCategoryAxis();
    x_axis->setRange(-0.5, points.size() - 0.5);
    x_axis->setStartValue(-0.5);
    x_axis->setLabelsColor(QColor("#94a3b8"));
    x_axis->setGridLineColor(QColor("#1e293b"));
    x_axis->setLinePen(QPen(QColor("#334155")));

    int num_ticks = std::min<int>(8, static_cast<int>(points.size()));
    if (num_ticks < 2) num_ticks = 2;
    int last_idx = -1;
    QSet<QString> seen_labels;

    for (int t = 0; t < num_ticks; ++t) {
        int idx = (t * (points.size() - 1)) / (num_ticks - 1);
        if (idx == last_idx) continue;
        last_idx = idx;

        QString raw_d = points[idx].date;
        QString clean_d = raw_d;
        if (points.size() > 20 && raw_d.length() >= 4) {
            clean_d = raw_d.left(4); // Just 4-digit year for long series
        } else if (raw_d.length() >= 7) {
            clean_d = raw_d.left(7); // YYYY-MM
        }

        // Ensure category label is unique for QCategoryAxis
        QString final_lbl = clean_d;
        int dup_counter = 1;
        while (seen_labels.contains(final_lbl)) {
            final_lbl = QString("%1 (%2)").arg(clean_d).arg(dup_counter++);
        }
        seen_labels.insert(final_lbl);

        x_axis->append(final_lbl, idx);
    }
    chart->addAxis(x_axis, Qt::AlignBottom);

    // ── Line Series ──────────────────────────────────────────────────────────
    QColor color = country_color(current_country_code_);
    auto* line = new QLineSeries();
    line->setName(current_title_);
    line->setColor(color);
    QPen pen(color, 2.2);
    pen.setCapStyle(Qt::RoundCap);
    pen.setJoinStyle(Qt::RoundJoin);
    line->setPen(pen);

    for (int i = 0; i < points.size(); ++i) {
        line->append(i, points[i].value);
    }

    // Connect hover for real-time tracker readout
    connect(line, &QLineSeries::hovered, this, [this](const QPointF& pt, bool state) {
        if (state) {
            int idx = qRound(pt.x());
            if (idx >= 0 && idx < active_points_.size()) {
                const auto& p = active_points_[idx];
                QString u_str = current_unit_.isEmpty() ? "" : " " + current_unit_;
                hover_info_lbl_->setText(QString("📍 KỲ: %1  |  GIÁ TRỊ: %2%3")
                    .arg(p.date, format_num(p.value), u_str));
            }
        } else {
            hover_info_lbl_->setText("📍 SẴN SÀNG");
        }
    });

    chart->addSeries(line);
    line->attachAxis(x_axis);
    line->attachAxis(y_axis);

    if (is_area) {
        auto* base_line = new QLineSeries();
        double baseline_y = bottom_y;
        for (int i = 0; i < points.size(); ++i) {
            base_line->append(i, baseline_y);
        }

        auto* area = new QAreaSeries(line, base_line);
        QLinearGradient grad(QPointF(0, 0), QPointF(0, 1));
        grad.setCoordinateMode(QGradient::ObjectBoundingMode);
        QColor top_col = color;
        top_col.setAlpha(80);
        QColor bot_col = color;
        bot_col.setAlpha(12);
        grad.setColorAt(0.0, top_col);
        grad.setColorAt(1.0, bot_col);

        area->setBrush(QBrush(grad));
        area->setPen(Qt::NoPen);

        chart->addSeries(area);
        area->attachAxis(x_axis);
        area->attachAxis(y_axis);
    }

    // Average reference line
    auto* avg_line = new QLineSeries();
    avg_line->setName("Average");
    QPen avg_pen(QColor("#64748b"), 1.0, Qt::DashLine);
    avg_line->setPen(avg_pen);
    avg_line->append(-0.5, avg_val);
    avg_line->append(points.size() - 0.5, avg_val);
    chart->addSeries(avg_line);
    avg_line->attachAxis(x_axis);
    avg_line->attachAxis(y_axis);
}

void FinceptMacroChartWidget::render_series_bar(QChart* chart, const QVector<MacroDataPoint>& points) {
    int show_count = std::min<int>(30, static_cast<int>(points.size()));
    auto sub_points = points.mid(points.size() - show_count);

    auto* set = new QBarSet(current_title_);
    set->setColor(country_color(current_country_code_));

    QStringList categories;
    double y_max = 0.0;
    double y_min = 0.0;

    for (const auto& p : sub_points) {
        *set << p.value;
        QString dt = p.date;
        if (dt.length() >= 7) dt = dt.left(7);
        categories << dt;
        y_max = std::max(y_max, p.value);
        y_min = std::min(y_min, p.value);
    }

    auto* series = new QBarSeries();
    series->append(set);
    chart->addSeries(series);

    auto* axisX = new QBarCategoryAxis();
    axisX->append(categories);
    axisX->setLabelsColor(QColor("#94a3b8"));
    axisX->setGridLineColor(QColor("#1e293b"));
    chart->addAxis(axisX, Qt::AlignBottom);
    series->attachAxis(axisX);

    double span = y_max - y_min;
    if (span <= 0.0) span = 1.0;
    double bottom_y = (y_min >= 0.0) ? 0.0 : (y_min - span * 0.1);
    double top_y = y_max + span * 0.1;

    auto* axisY = new QCategoryAxis();
    axisY->setLabelsPosition(QCategoryAxis::AxisLabelsPositionOnValue);
    double y_span = top_y - bottom_y;
    axisY->setRange(bottom_y, top_y);
    axisY->setStartValue(bottom_y - y_span * 0.001);

    for (int t = 0; t < 6; ++t) {
        double v = bottom_y + t * (y_span / 5.0);
        axisY->append(format_y_tick(v, current_unit_), v);
    }

    axisY->setLabelsColor(QColor("#94a3b8"));
    axisY->setGridLineColor(QColor("#1e293b"));
    if (!current_unit_.isEmpty()) {
        axisY->setTitleText(QString("[%1]").arg(current_unit_));
        axisY->setTitleVisible(true);
        axisY->setTitleBrush(QBrush(QColor("#38bdf8")));
        axisY->setTitleFont(QFont("Consolas", 9, QFont::Bold));
    }
    chart->addAxis(axisY, Qt::AlignLeft);
    series->attachAxis(axisY);
}

void FinceptMacroChartWidget::render_leaderboard_bars(QChart* chart) {
    if (leaderboard_items_.isEmpty()) return;

    chart->setTitle(tr("TĂNG TRƯỞNG CÁC CHỈ TIÊU ĐẦU BẢNG (SO CÙNG KỲ / THÁNG TRƯỚC)"));
    chart->setTitleFont(QFont("Consolas", 11, QFont::Bold));
    chart->setTitleBrush(QBrush(QColor("#f8fafc")));

    auto* pos_set = new QBarSet(tr("Tăng trưởng dương"));
    pos_set->setColor(QColor("#10b981")); // Emerald
    auto* neg_set = new QBarSet(tr("Tăng trưởng âm"));
    neg_set->setColor(QColor("#ef4444")); // Red

    QStringList categories;
    double y_max = 5.0;
    double y_min = -5.0;

    for (const auto& val : leaderboard_items_) {
        QJsonObject obj = val.toObject();
        QString name = obj["CHỈ TIÊU"].toString();
        // Shorten name for chart axis
        if (name.contains("Bán lẻ")) name = "Bán lẻ DV";
        else if (name.contains("Khách quốc tế")) name = "Khách QT";
        else if (name.contains("Đầu tư công")) name = "Đầu tư công";
        else if (name.contains("Doanh nghiệp")) name = "DN mới";
        categories << name;

        QString delta_str = obj["BIẾN ĐỘNG"].toString();
        delta_str = delta_str.replace("+", "").replace("%", "").replace("điểm", "").replace(",", ".").trimmed();
        double num = delta_str.toDouble();

        if (num >= 0.0) {
            *pos_set << num;
            *neg_set << 0.0;
        } else {
            *pos_set << 0.0;
            *neg_set << num;
        }
        y_max = std::max(y_max, num);
        y_min = std::min(y_min, num);
    }

    auto* series = new QBarSeries();
    series->append(pos_set);
    series->append(neg_set);
    chart->addSeries(series);

    auto* axisX = new QBarCategoryAxis();
    axisX->append(categories);
    axisX->setLabelsColor(QColor("#94a3b8"));
    axisX->setGridLineColor(QColor("#1e293b"));
    chart->addAxis(axisX, Qt::AlignBottom);
    series->attachAxis(axisX);

    double span = y_max - y_min;
    if (span <= 0.0) span = 10.0;
    double bottom_y = y_min - span * 0.1;
    double top_y = y_max + span * 0.1;

    auto* axisY = new QCategoryAxis();
    axisY->setLabelsPosition(QCategoryAxis::AxisLabelsPositionOnValue);
    double y_span = top_y - bottom_y;
    axisY->setRange(bottom_y, top_y);
    axisY->setStartValue(bottom_y - y_span * 0.001);

    for (int t = 0; t < 6; ++t) {
        double v = bottom_y + t * (y_span / 5.0);
        axisY->append(QString("%1%").arg(QString::number(v, 'f', 1)), v);
    }

    axisY->setLabelsColor(QColor("#94a3b8"));
    axisY->setGridLineColor(QColor("#1e293b"));
    axisY->setTitleText("[% Biến động]");
    axisY->setTitleVisible(true);
    axisY->setTitleBrush(QBrush(QColor("#38bdf8")));
    axisY->setTitleFont(QFont("Consolas", 9, QFont::Bold));
    chart->addAxis(axisY, Qt::AlignLeft);
    series->attachAxis(axisY);
}

void FinceptMacroChartWidget::render_pulse_bars(QChart* chart) {
    chart->setTitle(tr("SO SÁNH CÁC CHỈ TIÊU TRỌNG YẾU GIỮA 04 NỀN KINH TẾ (VN · US · CN · EU)"));
    chart->setTitleFont(QFont("Consolas", 11, QFont::Bold));
    chart->setTitleBrush(QBrush(QColor("#38bdf8")));

    QStringList categories;
    auto* gdp_set = new QBarSet("GDP (%)");
    gdp_set->setColor(QColor("#f59e0b")); // Amber

    auto* cpi_set = new QBarSet("CPI (%)");
    cpi_set->setColor(QColor("#06b6d4")); // Cyan

    auto* rate_set = new QBarSet("Lãi suất (%)");
    rate_set->setColor(QColor("#10b981")); // Emerald

    double y_min = 0.0;
    double y_max = 0.0;
    for (const auto& value : pulse_items_) {
        const QJsonObject obj = value.toObject();
        const QString economy = obj.value(QStringLiteral("NỀN KINH TẾ")).toString();
        categories.append(economy.isEmpty() ? tr("Nền kinh tế") : economy);

        const double gdp = pulse_metric_value(obj, QStringLiteral("GDP_VALUE"), QStringLiteral("GDP"));
        const double cpi = pulse_metric_value(obj, QStringLiteral("LẠM_PHÁT_VALUE"), QStringLiteral("LẠM PHÁT"));
        const double rate = pulse_metric_value(obj, QStringLiteral("LÃI_SUẤT_VALUE"), QStringLiteral("LÃI SUẤT"));

        *gdp_set << gdp;
        *cpi_set << cpi;
        *rate_set << rate;

        y_min = std::min({y_min, gdp, cpi, rate});
        y_max = std::max({y_max, gdp, cpi, rate});
    }

    if (categories.isEmpty()) {
        categories.append({"Việt Nam 🇻🇳", "Hoa Kỳ 🇺🇸", "Trung Quốc 🇨🇳", "Châu Âu 🇪🇺"});
        *gdp_set << 0.0 << 0.0 << 0.0 << 0.0;
        *cpi_set << 0.0 << 0.0 << 0.0 << 0.0;
        *rate_set << 0.0 << 0.0 << 0.0 << 0.0;
        y_max = 1.0;
    }

    auto* series = new QBarSeries();
    series->append(gdp_set);
    series->append(cpi_set);
    series->append(rate_set);
    chart->addSeries(series);

    auto* axisX = new QBarCategoryAxis();
    axisX->append(categories);
    axisX->setLabelsColor(QColor("#f8fafc"));
    axisX->setGridLineColor(QColor("#1e293b"));
    chart->addAxis(axisX, Qt::AlignBottom);
    series->attachAxis(axisX);

    auto* axisY = new QCategoryAxis();
    axisY->setLabelsPosition(QCategoryAxis::AxisLabelsPositionOnValue);
    double span = y_max - y_min;
    if (span <= 0.0)
        span = std::max(1.0, std::abs(y_max) * 0.1);
    double bottom_y = y_min >= 0.0 ? 0.0 : y_min - span * 0.12;
    double top_y = y_max + span * 0.12;
    if (top_y <= bottom_y)
        top_y = bottom_y + 1.0;

    axisY->setRange(bottom_y, top_y);
    axisY->setStartValue(bottom_y - (top_y - bottom_y) * 0.001);

    for (int t = 0; t <= 5; ++t) {
        double v = bottom_y + (top_y - bottom_y) * (static_cast<double>(t) / 5.0);
        axisY->append(QString("%1%").arg(QString::number(v, 'f', 1)), v);
    }

    axisY->setLabelsColor(QColor("#94a3b8"));
    axisY->setGridLineColor(QColor("#1e293b"));
    axisY->setTitleText("[% Tỷ lệ]");
    axisY->setTitleVisible(true);
    axisY->setTitleBrush(QBrush(QColor("#38bdf8")));
    axisY->setTitleFont(QFont("Consolas", 9, QFont::Bold));
    chart->addAxis(axisY, Qt::AlignLeft);
    series->attachAxis(axisY);

    chart->legend()->setVisible(true);
    chart->legend()->setAlignment(Qt::AlignBottom);
    chart->legend()->setLabelColor(QColor("#cbd5e1"));
}

void FinceptMacroChartWidget::clear() {
    active_points_.clear();
    raw_series_points_.clear();
    leaderboard_items_ = QJsonArray();
    pulse_items_ = QJsonArray();
    data_table_->clear();
    update_stats_badges({}, "");
    update_chart();
}

void FinceptMacroChartWidget::resizeEvent(QResizeEvent* event) {
    QWidget::resizeEvent(event);
}

} // namespace fincept::screens
