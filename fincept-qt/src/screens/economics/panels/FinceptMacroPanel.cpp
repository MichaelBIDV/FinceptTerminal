// src/screens/economics/panels/FinceptMacroPanel.cpp
// Fincept Macro — Real-time & Maximum Time Series Macro Explorer (dulieukinhte.com)
// Supports Vietnam (VN), United States (US), China (CN), European Union (EU)
#include "screens/economics/panels/FinceptMacroPanel.h"
#include "screens/economics/panels/FinceptMacroChartWidget.h"
#include "screens/economics/panels/MacroCardGrid.h"

#include "core/logging/Logger.h"
#include "services/economics/EconomicsService.h"
#include "ui/theme/Theme.h"

#include <QCoreApplication>
#include <QDesktopServices>
#include <QDir>
#include <QFile>
#include <QHBoxLayout>
#include <QJsonArray>
#include <QJsonObject>
#include <QUrl>

namespace fincept::screens {

namespace {

constexpr const char* kFinceptMacroSourceId = "fincept";
constexpr const char* kFinceptMacroScript = "fincept_macro.py";
constexpr const char* kFinceptMacroColor = "#d97706";

struct CountryItem {
    const char* code;
    const char* label;
    const char* flag;
};

static const CountryItem kCountries[] = {
    {"VN", "Việt Nam 🇻🇳", "🇻🇳"},
    {"US", "Hoa Kỳ 🇺🇸", "🇺🇸"},
    {"CN", "Trung Quốc 🇨🇳", "🇨🇳"},
    {"EU", "Liên Minh Châu Âu 🇪🇺", "🇪🇺"}
};

struct IndicatorItem {
    const char* label;
    int table_id;
};

static const QMap<QString, QVector<IndicatorItem>> kCountryIndicators = {
    {"VN", {
        {"[VN] Tăng Trưởng GDP (53 quý — 13 năm)", 268},
        {"[VN] Lạm Phát CPI (297 tháng — 25 năm)", 319},
        {"[VN] Bán Lẻ Hàng Hoá & Dịch Vụ (272 tháng — 23 năm)", 273},
        {"[VN] Xuất Khẩu Hàng Hóa (212 tháng — 18 năm)", 292},
        {"[VN] Nhập Khẩu Hàng Hóa (212 tháng — 18 năm)", 293},
        {"[VN] Khách Quốc Tế Đến VN (196 tháng — 16 năm)", 295},
        {"[VN] Vốn Đầu Tư Công NSNN (160 tháng — 13 năm)", 317},
        {"[VN] Doanh Nghiệp Mới Thành Lập (164 tháng — 14 năm)", 274}
    }},
    {"US", {
        {"[US] Lãi Suất Fed Funds Rate (6.484 ngày — 26 năm)", 444},
        {"[US] Lạm Phát CPI Toàn Phần (678 tháng — 56.5 năm)", 435},
        {"[US] Lạm Phát CPI Lõi Core CPI (678 tháng — 56.5 năm)", 436},
        {"[US] Chỉ Số Giá Sản Xuất PPI (198 tháng — 16.5 năm)", 438},
        {"[US] Tỷ Lệ Thất Nghiệp (326 tháng — 27 năm)", 439},
        {"[US] Việc Làm Phi Nông Nghiệp NFP (326 tháng — 27 năm)", 440},
        {"[US] Tăng Trưởng GDP Hàng Quý (318 quý — 79 năm)", 434},
        {"[US] Nợ Quá Hạn Thẻ Tín Dụng (166 quý — 41.5 năm)", 640},
        {"[US] Nợ Công Liên Bang (6.703 ngày — 27 năm)", 461},
        {"[US] Doanh Số Bán Lẻ (416 tháng — 35 năm)", 441},
        {"[US] Cán Cân Thương Mại (415 tháng — 35 năm)", 454},
        {"[US] Chỉ Số Biến Động VIX (6.749 ngày — 27 năm)", 459},
        {"[US] Lợi Suất TPCP 10 Năm (6.740 ngày — 27 năm)", 457},
        {"[US] Cung Tiền M2 (670 tháng — 56 năm)", 446}
    }},
    {"CN", {
        {"[CN] Tỷ Giá CNY/USD (321 tháng — 27 năm)", 574},
        {"[CN] Giá Sản Xuất PPI (248 tháng — 21 năm)", 550},
        {"[CN] Tăng Trưởng GDP (82 quý — 20.5 năm)", 546},
        {"[CN] PMI Sản Xuất NBS (224 tháng — 19 năm)", 544},
        {"[CN] Lạm Phát CPI (224 tháng — 19 năm)", 549},
        {"[CN] Lãi Suất LPR 1 Năm (1.537 mốc — 13 năm)", 556},
        {"[CN] Cung Tiền M2 (224 tháng — 19 năm)", 552},
        {"[CN] Cán Cân Thương Mại Với VN (172 tháng — 14.5 năm)", 660},
        {"[CN] Giá Nhà Mới Bắc Kinh (188 tháng — 16 năm)", 555}
    }},
    {"EU", {
        {"[EU] Lãi Suất ECB Deposit (7.091 ngày — 28 năm)", 503},
        {"[EU] Niềm Tin Kinh Tế ESI (560 tháng — 47 năm)", 514},
        {"[EU] Lạm Phát HICP Toàn Khối (321 tháng — 27 năm)", 491},
        {"[EU] Tỷ Lệ Thất Nghiệp (319 tháng — 27 năm)", 494},
        {"[EU] Tăng Trưởng GDP (126 quý — 31.5 năm)", 489},
        {"[EU] Cung Tiền M3 (559 tháng — 47 năm)", 497},
        {"[EU] Căng Thẳng Tài Chính CISS (7.231 ngày — 28 năm)", 525},
        {"[EU] Tỷ Giá EUR/USD (7.094 ngày — 28 năm)", 515},
        {"[EU] Nợ Công Trên GDP (105 quý — 26 năm)", 507},
        {"[EU] Bảng Cân Đối Eurosystem (1.445 tuần — 28 năm)", 501}
    }}
};

} // namespace

FinceptMacroPanel::FinceptMacroPanel(QWidget* parent)
    : EconPanelBase(kFinceptMacroSourceId, kFinceptMacroColor, parent) {
    build_base_ui(this);

    // Embed Native Bloomberg Macro Chart & Synced Table Widget
    chart_widget_ = new FinceptMacroChartWidget(this);
    chart_page_idx_ = add_content_page(chart_widget_);

    connect(chart_widget_, &FinceptMacroChartWidget::indicator_selected,
            this, &FinceptMacroPanel::on_chart_indicator_selected);

    // Bảng thẻ chỉ tiêu — bản dựng bằng widget của ~/Downloads/fincept_macro_dashboard.html.
    // Không nhúng được trang đó: kit Qt trên máy không có QtWebEngine, và bản thân tệp HTML là
    // ảnh chụp đóng băng (khối Việt Nam đóng dấu 05-09-2026). Xem MacroCardGrid.h.
    card_grid_ = new MacroCardGrid(this);
    card_page_idx_ = add_content_page(card_grid_);
    connect(card_grid_, &MacroCardGrid::indicator_activated,
            this, &FinceptMacroPanel::on_card_activated);

    connect(&services::EconomicsService::instance(), &services::EconomicsService::result_ready, this,
            &FinceptMacroPanel::on_result);
}

void FinceptMacroPanel::activate() {
    on_fetch();
}

void FinceptMacroPanel::build_controls(QHBoxLayout* thl) {
    // Quick country switcher buttons
    btn_vn_ = new QPushButton("🇻🇳 VN");
    btn_us_ = new QPushButton("🇺🇸 US");
    btn_cn_ = new QPushButton("🇨🇳 CN");
    btn_eu_ = new QPushButton("🇪🇺 EU");

    auto setup_country_btn = [this](QPushButton* btn, const QString& code) {
        btn->setFixedHeight(26);
        btn->setCursor(Qt::PointingHandCursor);
        connect(btn, &QPushButton::clicked, this, [this, code]() {
            set_country_by_code(code);
        });
    };
    setup_country_btn(btn_vn_, "VN");
    setup_country_btn(btn_us_, "US");
    setup_country_btn(btn_cn_, "CN");
    setup_country_btn(btn_eu_, "EU");

    thl->addWidget(btn_vn_);
    thl->addWidget(btn_us_);
    thl->addWidget(btn_cn_);
    thl->addWidget(btn_eu_);

    thl->addSpacing(8);

    // Country Dropdown
    country_lbl_ = new QLabel(tr("NỀN KINH TẾ"));
    country_lbl_->setStyleSheet(ctrl_label_style());
    country_combo_ = new QComboBox;
    country_combo_->setFixedHeight(26);
    country_combo_->setMinimumWidth(160);

    for (const auto& c : kCountries) {
        country_combo_->addItem(QString("%1 %2").arg(c.flag, c.label), QString(c.code));
    }
    connect(country_combo_, QOverload<int>::of(&QComboBox::currentIndexChanged),
            this, &FinceptMacroPanel::on_country_changed);

    thl->addWidget(country_lbl_);
    thl->addWidget(country_combo_);

    thl->addSpacing(8);

    // View Mode Dropdown
    view_lbl_ = new QLabel(tr("CHẾ ĐỘ XEM"));
    view_lbl_->setStyleSheet(ctrl_label_style());
    view_combo_ = new QComboBox;
    view_combo_->setFixedHeight(26);
    view_combo_->setMinimumWidth(210);

    // Thứ tự có nghĩa: bốn màn chẩn đoán (khung Lê Chí Phúc / SGI Capital) đứng trước ba màn
    // tra cứu cũ, nên index 0 — màn mở mặc định — là CỔNG chứ không phải một bảng số.
    view_combo_->addItem(tr("🚦 CỔNG — Chế Độ & Tỷ Trọng Tiền Mặt (SGI)"), "sgi_chedo");
    view_combo_->addItem(tr("① — ⑦ Bảy Khối Chỉ Báo (Trọng Số SGI)"), "sgi_khoi");
    view_combo_->addItem(tr("📐 Neo Lịch Sử — Số Hôm Nay Đứng Ở Đâu"), "sgi_neo");
    view_combo_->addItem(tr("🪞 Tự Kiểm — Track Record & Nghịch Đảo"), "sgi_tukiem");
    view_combo_->addItem(tr("🗂 Thẻ Chỉ Tiêu — 04 Nền Kinh Tế"), "cards");
    view_combo_->addItem(tr("🏆 Chỉ Tiêu Đầu Bảng (Leaderboard)"), "leaderboard");
    view_combo_->addItem(tr("📈 Chuỗi Thời Gian Tối Đa (Max Series)"), "max_series");
    view_combo_->addItem(tr("🌐 Ma Trận Xung Lực (04 Nền Kinh Tế)"), "pulse");

    connect(view_combo_, QOverload<int>::of(&QComboBox::currentIndexChanged),
            this, &FinceptMacroPanel::on_view_changed);

    thl->addWidget(view_lbl_);
    thl->addWidget(view_combo_);

    // Historical Indicator Dropdown (for max_series mode)
    indicator_lbl_ = new QLabel(tr("CHỈ TIÊU LỊCH SỬ"));
    indicator_lbl_->setStyleSheet(ctrl_label_style());
    indicator_lbl_->setVisible(false);

    indicator_combo_ = new QComboBox;
    indicator_combo_->setFixedHeight(26);
    indicator_combo_->setMinimumWidth(280);
    indicator_combo_->setVisible(false);
    connect(indicator_combo_, QOverload<int>::of(&QComboBox::currentIndexChanged),
            this, &FinceptMacroPanel::on_indicator_changed);

    thl->addWidget(indicator_lbl_);
    thl->addWidget(indicator_combo_);

    // Action Button: Open Graphic Dashboard in external browser if desired
    open_dash_btn_ = new QPushButton(tr("🌐 BROWSER DASHBOARD"));
    open_dash_btn_->setFixedHeight(26);
    open_dash_btn_->setCursor(Qt::PointingHandCursor);
    open_dash_btn_->setToolTip(tr("Mở bảng điều khiển HTML tương tác trong trình duyệt"));
    open_dash_btn_->setStyleSheet(
        "QPushButton { background: rgba(255,255,255,0.06); color: #94a3b8; font-weight: bold; border-radius: 4px; padding: 0 8px; border: 1px solid rgba(255,255,255,0.1); }"
        "QPushButton:hover { background: #d97706; color: #ffffff; }"
    );
    connect(open_dash_btn_, &QPushButton::clicked, this, &FinceptMacroPanel::on_open_dashboard);

    thl->addWidget(open_dash_btn_);

    update_indicator_combo();
    update_country_btn_styles();
}

void FinceptMacroPanel::set_country_by_code(const QString& code) {
    for (int i = 0; i < country_combo_->count(); ++i) {
        if (country_combo_->itemData(i).toString() == code) {
            country_combo_->setCurrentIndex(i);
            break;
        }
    }
}

void FinceptMacroPanel::update_country_btn_styles() {
    const QString current = country_combo_->currentData().toString();
    auto set_style = [current](QPushButton* btn, const QString& code) {
        if (!btn) return;
        if (code == current) {
            btn->setStyleSheet(
                "QPushButton { background: #d97706; color: #ffffff; font-weight: bold; border-radius: 3px; padding: 2px 8px; border: 1px solid #f59e0b; }"
            );
        } else {
            btn->setStyleSheet(
                "QPushButton { background: rgba(255,255,255,0.06); color: #cbd5e1; border-radius: 3px; padding: 2px 8px; border: 1px solid rgba(255,255,255,0.12); }"
                "QPushButton:hover { background: rgba(255,255,255,0.12); color: #ffffff; }"
            );
        }
    };
    set_style(btn_vn_, "VN");
    set_style(btn_us_, "US");
    set_style(btn_cn_, "CN");
    set_style(btn_eu_, "EU");
}

void FinceptMacroPanel::on_country_changed(int /*index*/) {
    update_country_btn_styles();
    update_indicator_combo();
    // Ở màn thẻ, bốn nền kinh tế đã nằm sẵn trong lưới — đổi nước là LỌC TẠI CHỖ, không bắn
    // lại bốn lượt tải về dulieukinhte.com (trang của bên thứ ba, phải tiết chế số lượt).
    if (view_combo_ && view_combo_->currentData().toString() == "cards" && card_grid_) {
        card_grid_->set_filter(country_combo_->currentData().toString());
        return;
    }
    on_fetch();
}

void FinceptMacroPanel::on_card_activated(int table_id, const QString& indicator_name) {
    on_chart_indicator_selected(table_id, indicator_name);
}

void FinceptMacroPanel::on_view_changed(int /*index*/) {
    const QString view_mode = view_combo_->currentData().toString();
    const bool is_series = (view_mode == "max_series");
    indicator_lbl_->setVisible(is_series);
    indicator_combo_->setVisible(is_series);
    on_fetch();
}

void FinceptMacroPanel::on_indicator_changed(int /*index*/) {
    const QString view_mode = view_combo_->currentData().toString();
    if (view_mode == "max_series") {
        on_fetch();
    }
}

void FinceptMacroPanel::on_chart_indicator_selected(int table_id, const QString& indicator_name) {
    LOG_INFO("FinceptMacroPanel", QString("Người dùng chọn chỉ tiêu từ bảng: %1 (ID %2)").arg(indicator_name).arg(table_id));
    // Switch to Max Series view and locate the matching table_id
    for (int i = 0; i < view_combo_->count(); ++i) {
        if (view_combo_->itemData(i).toString() == "max_series") {
            view_combo_->setCurrentIndex(i);
            break;
        }
    }
    for (int i = 0; i < indicator_combo_->count(); ++i) {
        if (indicator_combo_->itemData(i).toInt() == table_id) {
            indicator_combo_->setCurrentIndex(i);
            break;
        }
    }
}

void FinceptMacroPanel::update_indicator_combo() {
    indicator_combo_->blockSignals(true);
    indicator_combo_->clear();
    const QString code = country_combo_->currentData().toString();
    if (kCountryIndicators.contains(code)) {
        for (const auto& ind : kCountryIndicators[code]) {
            indicator_combo_->addItem(ind.label, ind.table_id);
        }
    }
    indicator_combo_->blockSignals(false);
}

void FinceptMacroPanel::on_open_dashboard() {
    const QStringList candidates = {
        QDir(QCoreApplication::applicationDirPath() + "/../Resources/scripts/fincept_macro_dashboard.html").canonicalPath(),
        QDir(QCoreApplication::applicationDirPath() + "/scripts/fincept_macro_dashboard.html").canonicalPath(),
        QDir(QDir::homePath() + "/Documents/GitHub/FinceptTerminal/fincept-qt/scripts/fincept_macro_dashboard.html").canonicalPath(),
        QDir(QDir::homePath() + "/Downloads/fincept_macro_dashboard.html").canonicalPath()
    };

    for (const QString& path : candidates) {
        if (!path.isEmpty() && QFile::exists(path)) {
            LOG_INFO("FinceptMacroPanel", QString("Mở Macro Dashboard từ: %1").arg(path));
            QDesktopServices::openUrl(QUrl::fromLocalFile(path));
            return;
        }
    }
    LOG_WARN("FinceptMacroPanel", "Không tìm thấy file fincept_macro_dashboard.html");
}

void FinceptMacroPanel::on_fetch() {
    const QString view_mode = view_combo_->currentData().toString();
    const QString country_code = country_combo_->currentData().toString();

    // In all views, we hide the legacy flat cards row to use the rich Bloomberg banner in chart_widget_
    set_stats_visible(false);

    if (view_mode == "cards") {
        show_loading(tr("Đang nạp thẻ chỉ tiêu của 04 nền kinh tế…"));
        card_grid_->clear_all();
        card_cho_ = 0;
        for (const auto& c : kCountries) {
            ++card_cho_;
            services::EconomicsService::instance().execute(kFinceptMacroSourceId, kFinceptMacroScript,
                                                           "leaderboard", {QString(c.code)},
                                                           QString("fmacro_cards_") + c.code);
        }
    } else if (view_mode.startsWith("sgi_")) {
        const QString which = view_mode.mid(4);
        show_loading(tr("Đang nạp bảng chẩn đoán vĩ mô (%1)…").arg(which));
        services::EconomicsService::instance().execute(kFinceptMacroSourceId, kFinceptMacroScript,
                                                       "sgi", {which},
                                                       "fmacro_sgi_" + which, /*force=*/true);
    } else if (view_mode == "leaderboard") {
        show_loading(tr("Đang nạp Chỉ tiêu đầu bảng cho %1 từ dulieukinhte.com…").arg(country_combo_->currentText()));
        services::EconomicsService::instance().execute(kFinceptMacroSourceId, kFinceptMacroScript,
                                                       "leaderboard", {country_code},
                                                       "fmacro_lb_" + country_code);
    } else if (view_mode == "max_series") {
        const int table_id = indicator_combo_->currentData().toInt();
        const QString ind_text = indicator_combo_->currentText();
        show_loading(tr("Đang nạp Dải chuỗi thời gian tối đa cho %1…").arg(ind_text));
        services::EconomicsService::instance().execute(kFinceptMacroSourceId, kFinceptMacroScript,
                                                       "series", {QString::number(table_id)},
                                                       "fmacro_s_" + QString::number(table_id));
    } else if (view_mode == "pulse") {
        show_loading(tr("Đang nạp Ma trận vĩ mô 04 Nền kinh tế…"));
        services::EconomicsService::instance().execute(kFinceptMacroSourceId, kFinceptMacroScript,
                                                       "pulse", {},
                                                       "fmacro_pulse");
    }
}

void FinceptMacroPanel::on_result(const QString& request_id, const services::EconomicsResult& result) {
    if (result.source_id != kFinceptMacroSourceId)
        return;
    if (!request_id.startsWith("fmacro_"))
        return;

    if (!result.success) {
        show_error(result.error);
        return;
    }

    QJsonArray rows = result.data["data"].toArray();
    if (rows.isEmpty()) {
        const QString err = result.data["error"].toString();
        show_error(err.isEmpty() ? tr("Không có dữ liệu trả về từ máy chủ dữ liệu") : err);
        return;
    }

    if (request_id.startsWith("fmacro_cards_")) {
        const QString code = request_id.mid(QStringLiteral("fmacro_cards_").size());
        QString ten = code;
        for (const auto& c : kCountries) {
            if (code == c.code)
                ten = QString::fromUtf8(c.label);
        }
        card_grid_->set_country_cards(code, ten, rows);
        if (card_cho_ > 0)
            --card_cho_;
        show_content_page(card_page_idx_);
        LOG_INFO("FinceptMacroPanel",
                 QString("Thẻ chỉ tiêu %1: %2 thẻ (còn chờ %3 nền)")
                     .arg(code).arg(rows.size()).arg(card_cho_));
        return;
    }

    if (request_id.startsWith("fmacro_sgi_")) {
        // Bốn bảng này là văn bản chẩn đoán có cấu trúc, không phải chuỗi số — vẽ chart ở đây
        // là vẽ sai loại dữ liệu. Dùng thẳng bảng phẳng của lớp cơ sở rồi thoát.
        QString title = result.data["title"].toString();
        if (title.isEmpty())
            title = view_combo_->currentText();
        display(rows, title);
        show_table();
        LOG_INFO("FinceptMacroPanel",
                 QString("Bảng chẩn đoán vĩ mô SGI: %1 dòng").arg(rows.size()));
        return;
    }

    const QString country_code = country_combo_->currentData().toString();

    if (request_id.startsWith("fmacro_lb_")) {
        chart_widget_->set_leaderboard(country_combo_->currentText(), rows, country_code);
    } else if (request_id.startsWith("fmacro_s_")) {
        QVector<MacroDataPoint> points;
        points.reserve(rows.size());
        QString unit = result.data["unit"].toString();
        if (unit.isEmpty() || unit == "—") {
            unit = "—";
        }

        for (const auto& v : rows) {
            QJsonObject obj = v.toObject();
            MacroDataPoint pt;
            pt.date = obj["NGÀY (DATE)"].toString();
            pt.value = obj["GIÁ TRỊ"].toDouble();
            pt.unit = obj["ĐƠN VỊ"].toString();
            if (unit == "—" && !pt.unit.isEmpty() && pt.unit != "—") {
                unit = pt.unit;
            }
            points.append(pt);
        }

        QString title = indicator_combo_->currentText();
        chart_widget_->set_time_series(title, unit, points, country_code);
    } else {
        chart_widget_->set_pulse_matrix(rows);
    }

    if (chart_page_idx_ >= 0) {
        show_content_page(chart_page_idx_);
    } else {
        show_table();
    }

    LOG_INFO("FinceptMacroPanel", QString("Hiển thị Đồ thị Vĩ mô & Bảng số liệu: %1 quan sát").arg(rows.size()));
}

void FinceptMacroPanel::changeEvent(QEvent* event) {
    if (event->type() == QEvent::LanguageChange)
        retranslateUi();
    EconPanelBase::changeEvent(event);
}

void FinceptMacroPanel::retranslateUi() {
    if (country_lbl_) country_lbl_->setText(tr("NỀN KINH TẾ"));
    if (view_lbl_) view_lbl_->setText(tr("CHẾ ĐỘ XEM"));
    if (indicator_lbl_) indicator_lbl_->setText(tr("CHỈ TIÊU LỊCH SỬ"));
    if (open_dash_btn_) open_dash_btn_->setText(tr("🌐 BROWSER DASHBOARD"));
    EconPanelBase::retranslateUi();
}

} // namespace fincept::screens
