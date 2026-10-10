// src/screens/hhp_valuation/HhpValuationPanel.cpp
// ĐỊNH GIÁ HHP — lays out and fills the one scrollable content page (section map in the header).
// Every number arrives pre-computed from scripts/hhp_valuation.py (`overview`, `ticker <TK>`);
// this file only formats and places it. All data strings are HTML-escaped before they reach a
// rich-text QLabel, and every missing block hides or clears its widget instead of failing.
#include "screens/hhp_valuation/HhpValuationPanel.h"

#include "core/logging/Logger.h"
#include "screens/hhp_valuation/HhpChart.h"
#include "screens/hhp_valuation/HhpCommon.h"
#include "screens/hhp_valuation/HhpForecastView.h"
#include "screens/hhp_valuation/HhpHistoryView.h"
#include "screens/hhp_valuation/HhpScreenerTable.h"
#include "screens/hhp_valuation/HhpTickerDialog.h"
#include "screens/hhp_valuation/HhpWeeklyPage.h"
#include "services/economics/EconomicsService.h"

#include <QCheckBox>
#include <QComboBox>
#include <QDate>
#include <QDesktopServices>
#include <QDir>
#include <QElapsedTimer>
#include <QFile>
#include <QFileDialog>
#include <QFileInfo>
#include <QFrame>
#include <QHash>
#include <QSet>
#include <QSignalBlocker>
#include <QGridLayout>
#include <QHBoxLayout>
#include <QHeaderView>
#include <QJsonArray>
#include <QLabel>
#include <QLineEdit>
#include <QMessageBox>
#include <QPushButton>
#include <QScrollArea>
#include <QScrollBar>
#include <QStackedWidget>
#include <QStringList>
#include <QTextStream>
#include <QTimer>
#include <QUrl>
#include <QVBoxLayout>

#include <algorithm>
#include <iterator>
#include <utility>

namespace fincept::screens {

namespace {

constexpr QLatin1StringView kSourceId{"hhp"};
constexpr QLatin1StringView kScript{"hhp_valuation.py"};
constexpr QLatin1StringView kDefaultWebUrl{"http://localhost:9000/sys/knowledge_os/hhp_vn100_valuation.html"};
constexpr int kRowPx = 30;                      ///< fallback screener row height when the header reports no length yet
constexpr int kRefreshAfterSec = 30 * 60;       ///< re-fetch on show / tick once the last load is this old
constexpr int kRefreshTickMs = 15 * 60 * 1000;  ///< how often the data age is re-evaluated
constexpr double kStaleHours = 30.0;            ///< same threshold as hhp_valuation.py STALE_HOURS
constexpr QLatin1StringView kWeeklyScript{"hhp_weekly.py"};
constexpr int kWeeklyRefreshAfterSec = 60 * 60; ///< the issue is weekly; the live overlay moves 3×/day

using Kind = hhp::HhpChartSeries::Kind;

/// Zone chips above the screener, in display order.
struct ZoneChip {
    const char* key;       ///< zone_key filter value ("" = all)
    const char* label;     ///< chip caption (UTF-8)
    const char* count_key; ///< key inside zone_counts[universe][metric]
};
constexpr ZoneChip kZoneChips[] = {
    {"", "Tất cả", "total"},
    {"cheap", "RẺ <−1σ", "cheap"},
    {"neutral", "Trung tính", "neutral"},
    {"rich", "ĐẮT >+1σ", "rich"},
};

QString metric_label(const QString& metric) {
    return metric == QLatin1String("pb") ? QStringLiteral("P/B") : QStringLiteral("P/E");
}

QString esc(const QString& s) {
    return s.toHtmlEscaped();
}

/// Always-on statement, independent of whatever the upstream meta.disclaimer says (or omits).
QString not_advice() {
    return QObject::tr("Tái hiện phương pháp HHP — tham khảo, KHÔNG phải khuyến nghị.");
}

/// Index level like the page's vnd(): Vietnamese grouping, no trailing ",0" ("3.042", "2.694,1").
QString fmt_level(double v) {
    QString s = hhp::fmt_vi(v, 1);
    if (s.endsWith(QStringLiteral(",0")))
        s.chop(2);
    return s;
}

QString member_flag(const QString& universe) {
    return universe == QLatin1String("VN100") ? QStringLiteral("in_vn100") : QStringLiteral("in_vn30");
}

/// `html` wrapped in a colour span (caller escapes data inside `html`).
QString span(const QString& html, const QColor& c) {
    return QStringLiteral("<span style=\"color:%1;\">%2</span>").arg(hhp::css(c), html);
}

/// "-1.29σ · RẺ (<−1σ)" — escaped.
QString sigma_zone(double sigma, const QString& zone) {
    QString t = hhp::fmt_sigma(sigma) + QStringLiteral("σ");
    if (!zone.isEmpty())
        t += QStringLiteral(" · ") + zone;
    return esc(t);
}

/// One block of a stat row: small muted caption above a large coloured value.
struct Stat {
    Stat(QString caption_, QString value_html_, QColor color_, int px_ = 18)
        : caption(std::move(caption_)), value_html(std::move(value_html_)), color(std::move(color_)), px(px_) {}
    QString caption;    ///< plain text (escaped here)
    QString value_html; ///< rich text — the caller escapes data strings
    QColor color;
    int px;
};

QString stat_row_html(const QVector<Stat>& stats) {
    QString h = QStringLiteral("<table cellspacing=\"0\" cellpadding=\"0\"><tr>");
    for (const Stat& s : stats) {
        h += QStringLiteral("<td valign=\"top\" style=\"padding-right:26px;\">"
                            "<div style=\"color:%1; font-size:11px;\">%2</div>"
                            "<div style=\"color:%3; font-size:%4px; font-weight:bold;\">%5</div></td>")
                 .arg(hhp::css(hhp::c_muted()), esc(s.caption), hhp::css(s.color), QString::number(s.px),
                      s.value_html);
    }
    h += QStringLiteral("</tr></table>");
    return h;
}

QString list_html(const QJsonArray& items, const QColor& color) {
    QString h;
    for (const QJsonValue& it : items) {
        const QString s = it.toString();
        if (!s.isEmpty())
            h += QStringLiteral("<li style=\"color:%1; font-size:12px;\">%2</li>").arg(hhp::css(color), esc(s));
    }
    if (h.isEmpty())
        return span(QStringLiteral("—"), hhp::c_muted());
    return QStringLiteral("<ul style=\"margin-top:4px; margin-bottom:0px;\">") + h + QStringLiteral("</ul>");
}

/// Forecast milestone at 31/12 of the year after `as_of` (the stat row's "next year-end"); else the last one.
/// Values are read from the payload — never interpolated here.
QJsonObject forecast_milestone(const QJsonObject& fc, const QString& as_of) {
    const QJsonArray ms = fc.value("milestones").toArray();
    if (ms.isEmpty())
        return {};
    const QDate d = QDate::fromString(as_of.left(10), Qt::ISODate);
    if (d.isValid()) {
        const QString want = QStringLiteral("%1-12-31").arg(d.year() + 1);
        for (const QJsonValue& v : ms) {
            if (v.toObject().value("date").toString().startsWith(want))
                return v.toObject();
        }
    }
    return ms.last().toObject();
}

/// forecast.meta.generated "2026-09-26 12:08 ICT" → "26/09/2026 12:08 ICT"; anything else as is.
QString fcast_generated_text(const QString& raw) {
    const QDateTime dt = QDateTime::fromString(raw.left(16), QStringLiteral("yyyy-MM-dd HH:mm"));
    return dt.isValid() ? dt.toString(QStringLiteral("dd/MM/yyyy HH:mm")) + raw.mid(16) : raw.trimmed();
}

/// Key line under a chart that carries keynote / target markers.
QString notes_key(bool targets) {
    QString t = QObject::tr("▲ đỉnh · ▼ đáy");
    if (targets)
        t += QObject::tr(" · ◆ mục tiêu VN-Index của CTCK (trung vị theo kỳ hạn)");
    t += QObject::tr(" · ký hiệu rỗng = đỉnh/đáy tạm hoặc UNVERIFIED — rê chuột vào ký hiệu để xem bối cảnh & nguồn");
    return span(esc(t), hhp::c_muted());
}

/// Zone key from a milestone zone ("cheap" | "RẺ (<−1σ)" …) for zone_color().
QString zone_key_of(const QString& zone) {
    if (zone == QLatin1String("cheap") || zone == QLatin1String("neutral") || zone == QLatin1String("rich"))
        return zone;
    const QString u = zone.toUpper();
    if (u.contains(QStringLiteral("RẺ")))
        return QStringLiteral("cheap");
    if (u.contains(QStringLiteral("ĐẮT")))
        return QStringLiteral("rich");
    return QStringLiteral("neutral");
}

hhp::HhpChartSeries make_series(Kind kind, const QString& name, const QColor& color, double width, double opacity,
                                const QVector<QPointF>& points, const QVector<QPointF>& lower = {}) {
    hhp::HhpChartSeries s;
    s.kind = kind;
    s.name = name;
    s.color = color;
    s.width = width;
    s.opacity = opacity;
    s.points = points;
    s.lower = lower;
    return s;
}

/// set_series() when at least one series has points, otherwise clear(empty_msg).
void plot(hhp::HhpChart* chart, const QVector<hhp::HhpChartSeries>& series, const QString& y_title, int decimals,
          bool floor_zero, const QString& empty_msg) {
    const bool any = std::any_of(series.cbegin(), series.cend(),
                                 [](const hhp::HhpChartSeries& s) { return !s.points.isEmpty(); });
    if (any)
        chart->set_series(series, y_title, decimals, floor_zero);
    else
        chart->clear(empty_msg);
}

QLabel* make_label(QWidget* parent, const QColor& color, int px, Qt::TextFormat format, bool bold = false) {
    auto* l = new QLabel(parent);
    l->setTextFormat(format);
    l->setWordWrap(true);
    l->setStyleSheet(QStringLiteral("QLabel { color:%1; font-size:%2px; font-weight:%3; background:transparent; }")
                         .arg(hhp::css(color), QString::number(px),
                              bold ? QStringLiteral("bold") : QStringLiteral("normal")));
    return l;
}

QLabel* make_section_header(QWidget* parent) {
    auto* l = new QLabel(parent);
    l->setTextFormat(Qt::PlainText);
    l->setWordWrap(true);
    l->setStyleSheet(QStringLiteral("QLabel { color:%1; font-size:12px; font-weight:bold; letter-spacing:0.5px;"
                                    " margin-top:14px; background:transparent; }")
                         .arg(hhp::css(hhp::c_gold())));
    return l;
}

QFrame* make_card(QWidget* parent, QVBoxLayout*& layout) {
    auto* card = new QFrame(parent);
    card->setObjectName("hhpCard");
    card->setStyleSheet(QStringLiteral("QFrame#hhpCard { background:%1; border:1px solid %2; border-radius:12px; }")
                            .arg(hhp::css(hhp::c_card()), hhp::css(hhp::c_line())));
    layout = new QVBoxLayout(card);
    layout->setContentsMargins(12, 12, 12, 12);
    layout->setSpacing(6);
    return card;
}

/// Card holding an optional muted caption and one chart; `chart` receives the new widget.
QFrame* make_chart_card(QWidget* parent, const QString& caption, bool ranges, int min_h, hhp::HhpChart*& chart) {
    QVBoxLayout* lay = nullptr;
    QFrame* card = make_card(parent, lay);
    if (!caption.isEmpty()) {
        auto* cap = make_label(card, hhp::c_muted(), 12, Qt::PlainText);
        cap->setText(caption);
        lay->addWidget(cap);
    }
    chart = new hhp::HhpChart(ranges, card);
    chart->set_plot_min_height(min_h);
    lay->addWidget(chart);
    return card;
}

void set_status(QLabel* label, const QString& text, const QColor& color, const QString& tooltip = {}) {
    if (!label)
        return;
    label->setText(text);
    label->setToolTip(tooltip);
    label->setStyleSheet(
        QStringLiteral("QLabel { color:%1; font-size:10px; background:transparent; }").arg(hhp::css(color)));
}

QString pill_style(bool on) {
    if (on)
        return QStringLiteral("QPushButton { background:%1; color:#1a1208; font-weight:bold; border-radius:3px;"
                              " padding:2px 8px; border:1px solid %1; }")
            .arg(hhp::css(hhp::c_gold()));
    return QStringLiteral("QPushButton { background: rgba(255,255,255,0.06); color: #cbd5e1; border-radius: 3px;"
                          " padding: 2px 8px; border: 1px solid rgba(255,255,255,0.12); }"
                          "QPushButton:hover { background: rgba(255,255,255,0.12); color: #ffffff; }");
}

QString chip_style(bool on) {
    return QStringLiteral("QPushButton { background:%1; border:1px solid %2; border-radius:12px; padding:0; }"
                          "QPushButton:hover { border-color:%3; }")
        .arg(hhp::css(hhp::c_card()), hhp::css(on ? hhp::c_gold() : hhp::c_line()),
             hhp::css(on ? hhp::c_gold() : hhp::c_muted()));
}

QString csv_quote(QString v) {
    if (v.contains(QLatin1Char(',')) || v.contains(QLatin1Char('"')) || v.contains(QLatin1Char('\n')) ||
        v.contains(QLatin1Char('\r')))
        v = QStringLiteral("\"") + v.replace(QStringLiteral("\""), QStringLiteral("\"\"")) + QStringLiteral("\"");
    return v;
}

QString csv_cell(const QJsonValue& v) {
    if (v.isDouble())
        return QString::number(v.toDouble(), 'g', 15);
    if (v.isBool())
        return v.toBool() ? QStringLiteral("true") : QStringLiteral("false");
    if (v.isString())
        return v.toString();
    return {};
}

} // namespace

// ── Construction ─────────────────────────────────────────────────────────────

HhpValuationPanel::HhpValuationPanel(QWidget* parent)
    : EconPanelBase(QString(kSourceId), hhp::css(hhp::c_gold()), parent) {
    static int s_instances = 0;
    req_prefix_ = QStringLiteral("hhp_%1_").arg(++s_instances);
    req_overview_ = req_prefix_ + QStringLiteral("overview");
    req_ticker_ = req_prefix_ + QStringLiteral("tk_");
    req_brief_ = req_prefix_ + QStringLiteral("brief");
    req_history_ = req_prefix_ + QStringLiteral("history");

    build_base_ui(this);
    set_stats_visible(false);

    build_content_page();
    page_idx_ = add_content_page(scroll_);

    // BẢN TUẦN view: its own scroll page, filled by apply_weekly().
    weekly_scroll_ = new QScrollArea(this);
    weekly_scroll_->setWidgetResizable(true);
    weekly_scroll_->setFrameShape(QFrame::NoFrame);
    weekly_scroll_->setHorizontalScrollBarPolicy(Qt::ScrollBarAlwaysOff);
    weekly_scroll_->setStyleSheet(
        QStringLiteral("QScrollArea { background:%1; border:none; }").arg(hhp::css(hhp::c_bg())));
    weekly_page_ = new hhp::weekly::HhpWeeklyPage;
    weekly_scroll_->setWidget(weekly_page_);
    weekly_page_idx_ = add_content_page(weekly_scroll_);
    connect(weekly_page_, &hhp::weekly::HhpWeeklyPage::section_requested, this, [this](QWidget* target) {
        if (target && weekly_page_ && weekly_page_->isAncestorOf(target))
            weekly_scroll_->verticalScrollBar()->setValue(target->mapTo(weekly_page_, QPoint(0, 0)).y());
    });
    connect(weekly_page_, &hhp::weekly::HhpWeeklyPage::ticker_activated, this, &HhpValuationPanel::open_ticker);

    // The base CSV button exports the generic results table, which this panel never fills —
    // point it at the screener rows currently shown instead (live or weekly, by view).
    disconnect(export_btn_, &QPushButton::clicked, this, &HhpValuationPanel::export_csv);
    connect(export_btn_, &QPushButton::clicked, this, [this]() {
        if (view_ == QLatin1String("weekly"))
            export_weekly_csv();
        else
            export_screener_csv();
    });
    export_btn_->setToolTip(tr("Xuất bộ lọc đang hiển thị ra CSV"));

    connect(&services::EconomicsService::instance(), &services::EconomicsService::result_ready, this,
            &HhpValuationPanel::on_result);

    // The pipeline rebuilds 3×/day and the tab can stay open for days: re-check the data age on a
    // timer so the stale warning and the re-fetch do not wait for a manual FETCH.
    refresh_timer_ = new QTimer(this);
    refresh_timer_->setInterval(kRefreshTickMs);
    connect(refresh_timer_, &QTimer::timeout, this, &HhpValuationPanel::on_refresh_tick);
    refresh_timer_->start();

    show_empty(tr("Mở tab để nạp định giá HHP…"));
}

void HhpValuationPanel::build_controls(QHBoxLayout* thl) {
    auto add_label = [thl](const QString& text) {
        auto* lbl = new QLabel(text);
        lbl->setStyleSheet(ctrl_label_style());
        thl->addWidget(lbl);
        return lbl;
    };
    auto add_pill = [thl](const QString& text) {
        auto* btn = new QPushButton(text);
        btn->setFixedHeight(26);
        btn->setCursor(Qt::PointingHandCursor);
        thl->addWidget(btn);
        return btn;
    };

    add_label(tr("XEM"));
    btn_view_live_ = add_pill(QStringLiteral("LIVE"));
    btn_view_live_->setToolTip(tr("Định giá sống — pipeline HHP refresh 3×/ngày"));
    btn_view_weekly_ = add_pill(tr("BẢN TUẦN"));
    btn_view_weekly_->setToolTip(tr("Bản tuần của Hội đồng cố vấn AI (hhp_weekly_*.html) + kiểm so với live"));
    connect(btn_view_live_, &QPushButton::clicked, this, [this]() { set_view(QStringLiteral("live")); });
    connect(btn_view_weekly_, &QPushButton::clicked, this, [this]() { set_view(QStringLiteral("weekly")); });

    thl->addSpacing(8);

    live_ctrls_ << add_label(tr("RỔ"));
    btn_vn30_ = add_pill(QStringLiteral("VN30"));
    btn_vn100_ = add_pill(QStringLiteral("VN100"));
    live_ctrls_ << btn_vn30_ << btn_vn100_;
    connect(btn_vn30_, &QPushButton::clicked, this, [this]() { set_universe(QStringLiteral("VN30")); });
    connect(btn_vn100_, &QPushButton::clicked, this, [this]() { set_universe(QStringLiteral("VN100")); });

    thl->addSpacing(8);

    live_ctrls_ << add_label(tr("CHỈ SỐ"));
    btn_pe_ = add_pill(QStringLiteral("P/E"));
    btn_pb_ = add_pill(QStringLiteral("P/B"));
    live_ctrls_ << btn_pe_ << btn_pb_;
    connect(btn_pe_, &QPushButton::clicked, this, [this]() { set_metric(QStringLiteral("pe")); });
    connect(btn_pb_, &QPushButton::clicked, this, [this]() { set_metric(QStringLiteral("pb")); });

    weekly_ctrls_ << add_label(tr("KỲ"));
    issue_combo_ = new QComboBox;
    issue_combo_->setFixedHeight(26);
    issue_combo_->setMinimumWidth(200);
    issue_combo_->setSizeAdjustPolicy(QComboBox::AdjustToContents);
    issue_combo_->setCursor(Qt::PointingHandCursor);
    issue_combo_->setToolTip(tr("Chọn bản tuần (mới nhất ở trên)"));
    issue_combo_->setStyleSheet(QStringLiteral("QComboBox { background: rgba(255,255,255,0.06); color:#cbd5e1;"
                                               " border:1px solid rgba(255,255,255,0.12); border-radius:3px;"
                                               " padding:0 8px; font-size:11px; }"
                                               "QComboBox QAbstractItemView { background:%1; color:%2;"
                                               " selection-background-color:%3; selection-color:#1a1208; }")
                                    .arg(hhp::css(hhp::c_card()), hhp::css(hhp::c_text()), hhp::css(hhp::c_gold())));
    connect(issue_combo_, qOverload<int>(&QComboBox::activated), this, &HhpValuationPanel::on_issue_selected);
    thl->addWidget(issue_combo_);
    weekly_ctrls_ << issue_combo_;
    for (QWidget* w : std::as_const(weekly_ctrls_))
        w->hide();

    thl->addSpacing(12);

    fresh_lbl_ = new QLabel;
    fresh_lbl_->setTextFormat(Qt::PlainText);
    set_status(fresh_lbl_, QString(), hhp::c_muted());
    thl->addWidget(fresh_lbl_);

    web_btn_ = new QPushButton(tr("🌐 BẢN WEB"));
    web_btn_->setFixedHeight(26);
    web_btn_->setCursor(Qt::PointingHandCursor);
    web_btn_->setToolTip(tr("Mở trang Cowork hhp_vn100_valuation.html trong trình duyệt"));
    web_btn_->setStyleSheet(QStringLiteral("QPushButton { background: rgba(255,255,255,0.06); color: #94a3b8;"
                                           " font-weight: bold; border-radius: 4px; padding: 0 8px;"
                                           " border: 1px solid rgba(255,255,255,0.1); }"
                                           "QPushButton:hover { background: %1; color: #1a1208; }")
                                .arg(hhp::css(hhp::c_gold())));
    connect(web_btn_, &QPushButton::clicked, this, &HhpValuationPanel::open_web_page);
    thl->addWidget(web_btn_);

    update_toggle_styles();
}

void HhpValuationPanel::build_content_page() {
    const QColor muted = hhp::c_muted();
    const QColor text = hhp::c_text();
    const QString bg = hhp::css(hhp::c_bg());

    scroll_ = new QScrollArea(this);
    scroll_->setWidgetResizable(true);
    scroll_->setFrameShape(QFrame::NoFrame);
    scroll_->setHorizontalScrollBarPolicy(Qt::ScrollBarAlwaysOff);
    scroll_->setVerticalScrollBarPolicy(Qt::ScrollBarAsNeeded);
    scroll_->setStyleSheet(QStringLiteral("QScrollArea { background:%1; border:none; }").arg(bg));

    auto* page = new QWidget;
    page->setObjectName("hhpContent");
    page->setAttribute(Qt::WA_StyledBackground, true);
    page->setStyleSheet(QStringLiteral("QWidget#hhpContent { background:%1; }").arg(bg));
    auto* vl = new QVBoxLayout(page);
    vl->setContentsMargins(18, 14, 18, 24);
    vl->setSpacing(10);

    // 1. Method + freshness
    meta_lbl_ = make_label(page, muted, 12, Qt::RichText);
    vl->addWidget(meta_lbl_);

    // 1b. Link to the latest weekly issue (filled by apply_brief; hidden without one). A word-wrapped
    // label, not a button: a one-line button this long would set the page's minimum width.
    weekly_banner_ = make_label(page, muted, 12, Qt::RichText);
    weekly_banner_->setStyleSheet(QStringLiteral("QLabel { background:%1; color:%2; border:1px solid %3;"
                                                 " border-left:3px solid %4; border-radius:8px; padding:7px 12px;"
                                                 " font-size:12px; }")
                                      .arg(hhp::css(hhp::c_card()), hhp::css(muted), hhp::css(hhp::c_line()),
                                           hhp::css(hhp::c_gold())));
    weekly_banner_->setTextInteractionFlags(Qt::LinksAccessibleByMouse);
    connect(weekly_banner_, &QLabel::linkActivated, this, [this]() {
        // The banner advertises the LATEST issue: follow it, even if an older one was picked before.
        const QString shown = weekly_data_.value("meta").toObject().value("ky").toString();
        if (!requested_ky_.isEmpty() || shown != brief_.value("ky").toString()) {
            requested_ky_.clear();
            weekly_fetched_at_ = QDateTime(); // due → set_view fetches the newest issue
        }
        set_view(QStringLiteral("weekly"));
    });
    weekly_banner_->hide();
    vl->addWidget(weekly_banner_);

    // 2. Hội đồng Cố vấn AI verdict
    verdict_card_ = new QFrame(page);
    verdict_card_->setObjectName("hhpVerdict");
    verdict_card_->setStyleSheet(QStringLiteral("QFrame#hhpVerdict { background:%1; border:1px solid %2;"
                                                " border-left:3px solid %3; border-radius:12px; }")
                                     .arg(hhp::css(hhp::c_card()), hhp::css(hhp::c_line()), hhp::css(hhp::c_gold())));
    auto* vcl = new QVBoxLayout(verdict_card_);
    vcl->setContentsMargins(16, 14, 16, 14);
    vcl->setSpacing(6);
    auto* vhead = new QHBoxLayout;
    vhead->setSpacing(10);
    auto* vtitle = make_label(verdict_card_, hhp::c_gold(), 11, Qt::PlainText, true);
    vtitle->setWordWrap(false);
    vtitle->setText(tr("⚖︎ HỘI ĐỒNG CỐ VẤN AI"));
    auto* vsub = make_label(verdict_card_, muted, 11, Qt::PlainText);
    vsub->setWordWrap(false);
    vsub->setText(tr("tổng hợp 2 dashboard · refresh 3×/ngày"));
    verdict_chip_ = new QLabel(verdict_card_);
    verdict_chip_->setTextFormat(Qt::PlainText);
    vhead->addWidget(vtitle);
    vhead->addWidget(vsub);
    vhead->addStretch(1);
    vhead->addWidget(verdict_chip_);
    vcl->addLayout(vhead);
    verdict_lbl_ = make_label(verdict_card_, text, 13, Qt::RichText);
    vcl->addWidget(verdict_lbl_);
    verdict_card_->hide();
    vl->addWidget(verdict_card_);

    // 3. VNINDEX price inside its own P/E (P/B) bands. Title row: [8 NĂM] (engine window, default) · [TOÀN SỬ 2000→]
    // (+ [LOG] there). The card holds a stack: page 0 = index_chart_ exactly as before, page 1 = the TOÀN SỬ chart,
    // created on first use.
    index_title_ = make_section_header(page);
    auto* ix_head = new QHBoxLayout;
    ix_head->setContentsMargins(0, 0, 0, 0);
    ix_head->setSpacing(6);
    ix_head->addWidget(index_title_, 1);
    const auto ix_pill = [page, ix_head](const QString& label, const QString& tip) {
        auto* b = new QPushButton(label, page);
        b->setFixedHeight(22);
        b->setCursor(Qt::PointingHandCursor);
        b->setFocusPolicy(Qt::NoFocus);
        b->setToolTip(tip);
        ix_head->addWidget(b, 0, Qt::AlignBottom);
        return b;
    };
    btn_ix_8y_ = ix_pill(tr("8 NĂM"), tr("Cửa sổ engine (VnDirect finfo từ 12/2017) — cách đọc chính"));
    btn_ix_full_ = ix_pill(tr("TOÀN SỬ 2000→"), tr("VNINDEX từ 28/07/2000: giá toàn sử, dải σ dài hạn, điểm định giá rời ◇ "
                                                  "và hai cửa sổ σ đặt cạnh nhau"));
    btn_ix_log_ = ix_pill(QStringLiteral("LOG"), QString());
    btn_ix_log_->hide();
    connect(btn_ix_8y_, &QPushButton::clicked, this, [this]() { set_index_view(QStringLiteral("8y")); });
    connect(btn_ix_full_, &QPushButton::clicked, this, [this]() { set_index_view(QStringLiteral("full")); });
    connect(btn_ix_log_, &QPushButton::clicked, this, [this]() { set_full_log(!full_log_); });
    vl->addLayout(ix_head);
    index_stats_ = make_label(page, text, 13, Qt::RichText);
    vl->addWidget(index_stats_);
    QVBoxLayout* ix_lay = nullptr;
    QFrame* ix_card = make_card(page, ix_lay);
    index_stack_ = new QStackedWidget(ix_card);
    index_chart_ = new hhp::HhpChart(true, index_stack_);
    index_chart_->set_plot_min_height(800);
    index_stack_->addWidget(index_chart_);
    ix_lay->addWidget(index_stack_);
    vl->addWidget(ix_card);
    update_index_view_styles();
    index_fc_note_ = make_label(page, muted, 11, Qt::RichText);
    index_fc_note_->hide();
    vl->addWidget(index_fc_note_);

    // 4. Basket (VN30 / VN100) ratio vs its own history
    basket_title_ = make_section_header(page);
    vl->addWidget(basket_title_);
    basket_stats_ = make_label(page, text, 13, Qt::RichText);
    vl->addWidget(basket_stats_);
    vl->addWidget(make_chart_card(page, QString(), true, 720, basket_chart_));
    basket_note_ = make_label(page, muted, 11, Qt::RichText); // + forecast basis line (rich text)
    vl->addWidget(basket_note_);

    // 5. Non-VIC3 (independent of the metric toggle, like the Cowork page)
    ex_section_ = new QWidget(page);
    auto* exl = new QVBoxLayout(ex_section_);
    exl->setContentsMargins(0, 0, 0, 0);
    exl->setSpacing(10);
    auto* ex_title = make_section_header(ex_section_);
    ex_title->setText(tr("🏛 NON-VIC3 — ĐỊNH GIÁ THỰC SAU KHI LOẠI HỌ VIN (VIC+VHM+VRE) · LOGIC HSC/FIINTRADE"));
    exl->addWidget(ex_title);
    ex_stats_ = make_label(ex_section_, text, 13, Qt::RichText);
    exl->addWidget(ex_stats_);
    auto* grid = new QGridLayout;
    grid->setContentsMargins(0, 0, 0, 0);
    grid->setHorizontalSpacing(12);
    grid->setVerticalSpacing(12);
    grid->addWidget(make_chart_card(ex_section_, tr("VN-Index P/E: Toàn bộ vs Non-VIC3"), true, 280, ex_pe_chart_), 0,
                    0);
    grid->addWidget(make_chart_card(ex_section_, tr("VN-Index P/B: Toàn bộ vs Non-VIC3"), true, 280, ex_pb_chart_), 0,
                    1);
    grid->setColumnStretch(0, 1);
    grid->setColumnStretch(1, 1);
    exl->addLayout(grid);
    exl->addWidget(make_chart_card(ex_section_,
                                   tr("Tỷ trọng vốn hóa họ Vin trong VNINDEX — mức độ \"méo\" chỉ số chung"), false,
                                   190, ex_w3_chart_));
    ex_note_ = make_label(ex_section_, muted, 12, Qt::RichText);
    exl->addWidget(ex_note_);
    vl->addWidget(ex_section_);

    // 6. Screener
    screener_title_ = make_section_header(page);
    vl->addWidget(screener_title_);
    auto* hint = make_label(page, muted, 12, Qt::PlainText);
    hint->setText(tr("👉 Bấm vào mã (hoặc double-click / Enter) để mở chart vùng định giá P/E·P/B từng mã — "
                     "lịch sử YTD…ALL + forward 2026F/2027F. Chuột phải: VietCap IQ · MiQuant · Simplize."));
    vl->addWidget(hint);

    auto* bar = new QWidget(page);
    auto* bl = new QHBoxLayout(bar);
    bl->setContentsMargins(0, 2, 0, 2);
    bl->setSpacing(10);

    chips_row_ = new QWidget(bar);
    auto* chl = new QHBoxLayout(chips_row_);
    chl->setContentsMargins(0, 0, 0, 0);
    chl->setSpacing(8);
    for (const ZoneChip& zc : kZoneChips) {
        auto* btn = new QPushButton(chips_row_);
        btn->setCursor(Qt::PointingHandCursor);
        btn->setFixedHeight(26);
        auto* inner = new QHBoxLayout(btn);
        inner->setContentsMargins(12, 0, 12, 0);
        // Rich-text label (count coloured by zone) — clicks pass through to the button.
        auto* lbl = new QLabel(btn);
        lbl->setTextFormat(Qt::RichText);
        lbl->setAlignment(Qt::AlignCenter);
        lbl->setAttribute(Qt::WA_TransparentForMouseEvents);
        lbl->setStyleSheet(QStringLiteral("QLabel { background:transparent; font-size:12px; }"));
        inner->addWidget(lbl);
        const QString key = QString::fromLatin1(zc.key);
        connect(btn, &QPushButton::clicked, this, [this, key]() { set_zone(key); });
        chl->addWidget(btn);
        chip_btns_.append(btn);
        chip_lbls_.append(lbl);
    }
    bl->addWidget(chips_row_);

    search_edit_ = new QLineEdit(bar);
    search_edit_->setPlaceholderText(tr("Lọc mã…"));
    search_edit_->setMinimumWidth(160);
    search_edit_->setClearButtonEnabled(true);
    search_edit_->setStyleSheet(QStringLiteral("QLineEdit { background:%1; color:%2; border:1px solid %3;"
                                               " border-radius:8px; padding:4px 10px; font-size:12px; }"
                                               "QLineEdit:focus { border-color:%4; }")
                                    .arg(hhp::css(hhp::c_card()), hhp::css(text), hhp::css(hhp::c_line()),
                                         hhp::css(hhp::c_gold())));
    connect(search_edit_, &QLineEdit::textChanged, this, [this]() { apply_screener_filter(); });
    bl->addWidget(search_edit_);

    reliable_chk_ = new QCheckBox(tr("chỉ mã band đáng tin"), bar);
    reliable_chk_->setCursor(Qt::PointingHandCursor);
    reliable_chk_->setStyleSheet(
        // Explicit indicator: under the inherited panel stylesheet the default box rendered invisible.
        QStringLiteral("QCheckBox { color:%1; font-size:12px; background:transparent; spacing:6px; }"
                       "QCheckBox::indicator { width:13px; height:13px; border:1px solid %2; border-radius:3px;"
                       " background:%3; }"
                       "QCheckBox::indicator:checked { background:%4; border-color:%4; }")
            .arg(hhp::css(muted), hhp::css(hhp::c_neutral()), hhp::css(hhp::c_card()), hhp::css(hhp::c_gold())));
    connect(reliable_chk_, &QCheckBox::toggled, this, [this]() { apply_screener_filter(); });
    bl->addWidget(reliable_chk_);

    bl->addStretch(1);
    count_lbl_ = make_label(bar, muted, 12, Qt::RichText);
    count_lbl_->setWordWrap(false);
    bl->addWidget(count_lbl_);
    vl->addWidget(bar);

    // The table never scrolls on its own: its height follows the visible rows so the whole page
    // scrolls as one (wheel events fall through to scroll_ because the table has no range).
    table_ = new hhp::HhpScreenerTable(page);
    table_->setVerticalScrollBarPolicy(Qt::ScrollBarAlwaysOff);
    connect(table_, &hhp::HhpScreenerTable::ticker_activated, this, &HhpValuationPanel::open_ticker);
    connect(table_, &hhp::HhpScreenerTable::count_changed, this, [this](int) { update_count_and_height(); });
    vl->addWidget(table_);
    screener_msg_ = make_label(page, hhp::c_rich(), 13, Qt::PlainText);
    screener_msg_->hide();
    vl->addWidget(screener_msg_);

    // 7. Footer
    foot_lbl_ = new QLabel(page);
    foot_lbl_->setTextFormat(Qt::RichText);
    foot_lbl_->setWordWrap(true);
    foot_lbl_->setStyleSheet(QStringLiteral("QLabel { color:%1; font-size:11px; background:transparent;"
                                            " border-top:1px solid %2; padding-top:12px; margin-top:12px; }")
                                 .arg(hhp::css(muted), hhp::css(hhp::c_line())));
    vl->addWidget(foot_lbl_);
    vl->addStretch(1);

    scroll_->setWidget(page);
    update_count_and_height();
}

// ── Fetch / results ──────────────────────────────────────────────────────────

void HhpValuationPanel::activate() {
    if (view_ == QLatin1String("weekly")) {
        if (weekly_fetching_)
            return;
        if (weekly_refresh_due())
            fetch_weekly();
        else
            render_weekly_fresh();
        return;
    }
    if (fetching_)
        return;
    if (refresh_due())
        on_fetch();
    else
        render_meta(); // the data age moves with the clock, not only with fetches
}

bool HhpValuationPanel::refresh_due() const {
    return !loaded_ || !fetched_at_.isValid() ||
           fetched_at_.secsTo(QDateTime::currentDateTimeUtc()) >= kRefreshAfterSec;
}

void HhpValuationPanel::on_refresh_tick() {
    if (view_ == QLatin1String("weekly")) {
        if (!weekly_loaded_ || weekly_fetching_)
            return;
        if (isVisible())
            activate();
        else
            render_weekly_fresh();
        return;
    }
    if (!loaded_ || fetching_)
        return;
    if (isVisible())
        activate(); // re-fetch when due, else re-evaluate the age
    else
        render_meta();
}

void HhpValuationPanel::on_fetch() {
    if (view_ == QLatin1String("weekly")) {
        fetch_weekly();
        return;
    }
    fetch_brief(); // tiny; keeps the banner and the screener marks in step with new issues
    if (index_view_ == QLatin1String("full")) {
        if (!history_fetching_)
            fetch_history(); // TOÀN SỬ on screen: refresh it with the overview
    } else if (history_loaded_) {
        history_fetched_at_ = QDateTime(); // overview newer than the history → the next TOÀN SỬ open re-fetches
    }
    fetching_ = true;
    if (!loaded_) {
        show_loading(tr("Đang nạp định giá HHP — VNINDEX · VN30 · VN100…"));
    } else {
        // Keep the current content on screen while the refresh runs.
        set_status(fresh_lbl_, tr("đang làm mới…"), hhp::c_muted());
        if (fetch_btn_)
            fetch_btn_->setEnabled(false);
    }
    services::EconomicsService::instance().execute(QString(kSourceId), QString(kScript), QStringLiteral("overview"), {},
                                                   req_overview_, /*force=*/true);
}

void HhpValuationPanel::on_result(const QString& request_id, const services::EconomicsResult& result) {
    // result_ready reaches every connected panel — route strictly by source + this instance's prefix.
    if (result.source_id != kSourceId || !request_id.startsWith(req_prefix_))
        return;

    if (request_id == req_brief_) {
        if (result.success)
            apply_brief(result.data);
        else
            LOG_WARN("HhpValuationPanel", "Bản tuần (brief) lỗi: " + result.error);
        return;
    }

    if (request_id == req_history_) {
        history_fetching_ = false;
        if (result.success) {
            history_fetched_at_ = QDateTime::currentDateTimeUtc();
            apply_history(result.data);
            return;
        }
        history_err_ = result.error.isEmpty() ? tr("không rõ nguyên nhân") : result.error;
        LOG_WARN("HhpValuationPanel", "Nạp toàn sử VNINDEX lỗi: " + history_err_);
        render_index_full(); // TOÀN SỬ only: overlay (nothing loaded yet) or a warning line (keeps the last good one)
        return;
    }

    if (request_id.startsWith(req_prefix_ + QStringLiteral("wk_"))) {
        if (request_id != req_weekly_)
            return; // answer for an issue the user already switched away from
        weekly_fetching_ = false;
        if (fetch_btn_)
            fetch_btn_->setEnabled(true);
        if (result.success) {
            weekly_fetched_at_ = QDateTime::currentDateTimeUtc();
            loaded_request_ky_ = requested_ky_;
            apply_weekly(result.data);
            return;
        }
        const QString err = result.error.isEmpty() ? tr("không rõ nguyên nhân") : result.error;
        LOG_WARN("HhpValuationPanel", "Nạp bản tuần HHP lỗi: " + err);
        if (weekly_loaded_) {
            requested_ky_ = loaded_request_ky_; // a failed switch keeps the issue on screen selected
            populate_issue_combo();
            if (view_ == QLatin1String("weekly")) // the label is shared: never overwrite the LIVE data age
                set_status(fresh_lbl_, tr("⚠ nạp bản tuần lỗi"), hhp::c_rich(), err);
        } else if (view_ == QLatin1String("weekly")) {
            show_error(err + tr("\nBản tuần đọc từ knowledge_os/hhp_weekly/hhp_weekly_YYYY-MM-DD.html "
                                "(scripts/hhp_weekly.py)."));
        }
        return;
    }

    if (request_id == req_overview_) {
        fetching_ = false;
        if (result.success) {
            fetched_at_ = QDateTime::currentDateTimeUtc();
            apply_overview(result.data);
            return;
        }
        const QString err = result.error.isEmpty() ? tr("không rõ nguyên nhân") : result.error;
        LOG_WARN("HhpValuationPanel", "Nạp định giá HHP lỗi: " + err);
        if (view_ == QLatin1String("weekly")) {
            // The user is on BẢN TUẦN: the live failure resurfaces on the next LIVE fetch.
            if (fetch_btn_ && !weekly_fetching_)
                fetch_btn_->setEnabled(true);
        } else if (loaded_) {
            // Short text: the label sits in the fixed toolbar, a long message would widen the panel.
            set_status(fresh_lbl_, tr("⚠ làm mới lỗi"), hhp::c_rich(), err);
            if (fetch_btn_)
                fetch_btn_->setEnabled(true);
        } else {
            // Script errors already say what to run; add the pipeline hint only for runner-level failures.
            show_error(err.contains(QLatin1String("python3"))
                           ? err
                           : err + tr("\nKiểm tra pipeline HHP trong knowledge_os (python3 hhp_vn100_valuation.py)."));
        }
        return;
    }

    if (request_id.startsWith(req_ticker_)) {
        const QString ticker = request_id.mid(req_ticker_.size());
        if (!dialog_ || dialog_->ticker() != ticker)
            return;
        if (result.success)
            dialog_->set_data(result.data);
        else
            dialog_->set_error(result.error);
    }
}

void HhpValuationPanel::apply_overview(const QJsonObject& data) {
    data_ = data;
    loaded_ = true;
    const QJsonArray rows = data_.value("rows").toArray();
    table_->set_rows(rows);
    render_all();
    if (view_ == QLatin1String("weekly"))
        render_weekly_fresh(); // a live refresh finishing late must not pull the user out of BẢN TUẦN
    else
        show_content_page(page_idx_);
    LOG_INFO("HhpValuationPanel", QString("Định giá HHP: %1 mã VN30 ∪ VN100").arg(rows.size()));
}

// ── State toggles (no re-fetch: one overview carries both universes and metrics) ───

void HhpValuationPanel::set_universe(const QString& universe) {
    if (universe == universe_)
        return;
    universe_ = universe;
    update_toggle_styles();
    if (!loaded_)
        return;
    render_meta(); // coverage line is per universe
    render_basket();
    render_zone_chips();
    apply_screener_filter();
}

void HhpValuationPanel::set_metric(const QString& metric) {
    if (metric == metric_)
        return;
    metric_ = metric;
    zone_key_.clear(); // zone counts differ per metric — same reset as the page's setMetric()
    update_toggle_styles();
    if (!loaded_)
        return;
    render_index();
    render_index_full(); // TOÀN SỬ only
    render_basket();
    render_zone_chips();
    apply_screener_filter();
}

void HhpValuationPanel::set_zone(const QString& zone_key) {
    zone_key_ = zone_key;
    if (!loaded_)
        return;
    render_zone_chips();
    apply_screener_filter();
}

void HhpValuationPanel::update_toggle_styles() {
    const auto style = [](QPushButton* b, bool on) {
        if (b)
            b->setStyleSheet(pill_style(on));
    };
    style(btn_vn30_, universe_ == QLatin1String("VN30"));
    style(btn_vn100_, universe_ == QLatin1String("VN100"));
    style(btn_pe_, metric_ == QLatin1String("pe"));
    style(btn_pb_, metric_ == QLatin1String("pb"));
    style(btn_view_live_, view_ == QLatin1String("live"));
    style(btn_view_weekly_, view_ == QLatin1String("weekly"));
}

// ── Rendering ────────────────────────────────────────────────────────────────

void HhpValuationPanel::render_all() {
    render_meta();
    render_verdict();
    render_index();
    render_index_full(); // TOÀN SỬ only (no-op in 8 NĂM)
    render_basket();
    render_exvic3();
    render_zone_chips();
    apply_screener_filter();
}

void HhpValuationPanel::render_meta() {
    const QJsonObject meta = data_.value("meta").toObject();
    const QString generated = meta.value("generated").toString();
    const QString generated_txt = generated.isEmpty() ? QStringLiteral("—") : generated;
    // Age from the file mtime against the clock NOW, so the warning appears while the tab stays open;
    // the script's own figures (computed at fetch time) are the fallback.
    double age = hhp::num(meta.value("age_hours"));
    bool stale = meta.value("stale").toBool();
    const QDateTime mtime = QDateTime::fromString(meta.value("file_mtime").toString(), Qt::ISODate);
    if (mtime.isValid()) {
        age = static_cast<double>(std::max<qint64>(0, mtime.secsTo(QDateTime::currentDateTimeUtc()))) / 3600.0;
        stale = age > kStaleHours;
    }
    const QString age_txt = hhp::has(age) ? QString::number(qRound(age)) : QStringLiteral("?");
    const QString disclaimer = meta.value("disclaimer").toString();

    QString html;
    if (stale) {
        html += span(esc(tr("⚠ Dữ liệu đã %1 giờ chưa làm mới — pipeline HHP (launchd com.hoidongcovanai.hhp-refresh) "
                            "có thể đã dừng.")
                             .arg(age_txt)),
                     hhp::c_rich()) +
                QStringLiteral("<br>");
    }
    QString expert = meta.value("expert").toString();
    if (expert.isEmpty())
        expert = QStringLiteral("Huỳnh Hoàng Phương");
    // Coverage of the selected basket (members with valuation data / members), not the pipeline's
    // whole VN200 set — that total is only given as context.
    const qsizetype n_members = data_.value("members").toObject().value(universe_).toArray().size();
    const QString flag = member_flag(universe_);
    qsizetype n_with_data = 0;
    for (const QJsonValue& rv : data_.value("rows").toArray()) {
        if (rv.toObject().value(flag).toBool())
            ++n_with_data;
    }
    QString coverage = n_members > 0 ? tr("%1: %2/%3 mã có dữ liệu").arg(universe_).arg(n_with_data).arg(n_members)
                                     : tr("%1: thiếu danh sách rổ").arg(universe_);
    const double n_tickers = hhp::num(meta.value("n_tickers"));
    if (hhp::has(n_tickers))
        coverage += tr(" (pipeline %1 mã)").arg(qRound(n_tickers));
    // Price feed and CapIQ export behind the rows, as stamped upstream (meta.prices / meta.capiq).
    const QJsonObject prices = meta.value("prices").toObject();
    const QDate prices_date = QDate::fromString(prices.value("as_of").toString(), Qt::ISODate);
    if (prices_date.isValid()) {
        coverage += tr(" · giá Vietcap %1").arg(prices_date.toString(QStringLiteral("dd/MM")));
        const double n_vietcap = hhp::num(prices.value("n_vietcap"));
        const double n_all = hhp::has(n_tickers) ? n_tickers : n_vietcap + hhp::num(prices.value("n_fallback"));
        if (hhp::has(n_vietcap) && hhp::has(n_all))
            coverage += QStringLiteral(" (%1/%2)").arg(qRound(n_vietcap)).arg(qRound(n_all));
    }
    const QJsonValue capiq = meta.value("capiq");
    const QDate capiq_date = QDate::fromString(capiq.toObject().value("exported_date").toString(), Qt::ISODate);
    // One entry per CapIQ screen export once the CIQ overlay is merged upstream (meta.capiq.screens):
    // several → "(n bảng)" here and each screen's export time in the meta line's tooltip.
    const QJsonObject screens = capiq.toObject().value("screens").toObject();
    const bool multi_screen = screens.size() > 1;
    if (capiq_date.isValid())
        coverage += tr(" · CapIQ xuất %1").arg(capiq_date.toString(QStringLiteral("dd/MM"))) +
                    (multi_screen ? tr(" (%1 bảng)").arg(screens.size()) : QString());
    else if (meta.contains("capiq") && capiq.isNull())
        coverage += tr(" · chưa có bản xuất CapIQ");
    html += QStringLiteral("Phương pháp <b style=\"color:%1;\">%2</b>: P = E×P/E và P = BVPS×P/B · vùng giá theo "
                           "μ±1σ/±2σ của <b>chính ratio lịch sử</b> (thực, VnDirect finfo ~8.5 năm). "
                           "%3 · cập nhật %4.")
                .arg(hhp::css(hhp::c_gold()), esc(expert), esc(coverage), esc(generated_txt));
    html += QStringLiteral("<br>") +
            span(esc(disclaimer.isEmpty() ? not_advice() : disclaimer), QColor(0x7d, 0x82, 0x8b));
    QStringList warnings;
    for (const QJsonValue& w : meta.value("warnings").toArray()) {
        if (!w.toString().isEmpty())
            warnings << w.toString();
    }
    if (!warnings.isEmpty())
        html += QStringLiteral("<br>") + span(esc(QStringLiteral("⚠ ") + warnings.join(QStringLiteral(" · "))),
                                             hhp::c_muted());
    // Tickers without a Vietcap price arrive in meta.warnings (hhp_valuation.py) — not repeated here.
    meta_lbl_->setText(html);
    QStringList screen_lines; // rich-text tooltip: every data string escaped
    if (multi_screen) {
        for (auto it = screens.begin(); it != screens.end(); ++it) {
            const QJsonObject s = it.value().toObject();
            const QString raw = s.value("exported_ict").toString();
            const QDateTime t = QDateTime::fromString(raw, Qt::ISODate);
            QString line = it.key() + QStringLiteral(": ") +
                           (t.isValid() ? t.toTimeZone(QTimeZone::fromSecondsAheadOfUtc(7 * 3600))
                                                  .toString(QStringLiteral("dd/MM/yyyy HH:mm")) +
                                              QStringLiteral(" ICT")
                                        : raw);
            const double n = hhp::num(s.value("n"));
            if (hhp::has(n))
                line += tr(" · %1 mã").arg(qRound(n));
            const QString file = s.value("file").toString();
            if (!file.isEmpty())
                line += QStringLiteral(" · ") + file;
            screen_lines << esc(line);
        }
    }
    meta_lbl_->setToolTip(screen_lines.isEmpty()
                              ? QString()
                              : QStringLiteral("<b>%1</b><br>%2")
                                    .arg(esc(tr("S&P CapIQ — %1 bảng xuất").arg(screens.size())),
                                         screen_lines.join(QStringLiteral("<br>"))));

    const QString tip = tr("Tệp dữ liệu: %1\nThư mục: %2")
                            .arg(meta.value("file_mtime").toString(), meta.value("data_dir").toString());
    if (stale)
        set_status(fresh_lbl_, tr("⚠ dữ liệu cũ %1 giờ").arg(age_txt), hhp::c_rich(), tip);
    else
        set_status(fresh_lbl_, tr("dữ liệu %1").arg(generated_txt), hhp::c_muted(), tip);

    QStringList sources;
    for (const QJsonValue& s : meta.value("sources").toArray()) {
        if (!s.toString().isEmpty())
            sources << esc(s.toString());
    }
    foot_lbl_->setText(
        QStringLiteral("Nguồn: %1. Vùng rẻ/đắt = ±1–2 độ lệch chuẩn của <b>chính P/E·P/B</b> lịch sử mỗi mã "
                       "(winsorize P5–P95 loại nhiễu ratio chu kỳ). <b>Toggle P/E↔P/B</b>: ngân hàng &amp; mã chu kỳ "
                       "(thép/BĐS) nên đọc bằng <b>P/B</b> (P/E méo khi LN biến động). ⚠ = ratio biến động lớn → "
                       "band kém tin. %2")
            // meta.disclaimer is already shown in the header line — repeating it here doubled the text.
            .arg(sources.isEmpty() ? QStringLiteral("—") : sources.join(QStringLiteral(" · ")), esc(not_advice())));
}

void HhpValuationPanel::render_verdict() {
    const QJsonObject v = data_.value("verdict").toObject();
    const QString headline = v.value("headline").toString();
    if (headline.isEmpty()) {
        verdict_card_->hide();
        return;
    }

    const bool brain = v.value("mode").toString() == QLatin1String("brain");
    const QColor chip_color = brain ? hhp::c_cheap() : hhp::c_muted();
    QString chip = brain ? tr("🧠 brain") : tr("⚙︎ deterministic");
    const QString updated = v.value("updated").toString();
    if (!updated.isEmpty())
        chip += QStringLiteral(" · ") + updated;
    verdict_chip_->setText(chip);
    const QString by = v.value("by").toString();
    verdict_chip_->setToolTip(by.isEmpty() ? QString() : tr("Nguồn verdict: %1").arg(by));
    verdict_chip_->setStyleSheet(QStringLiteral("QLabel { color:%1; border:1px solid %1; border-radius:10px;"
                                                " padding:2px 8px; font-size:10px; background:transparent; }")
                                     .arg(hhp::css(chip_color)));

    verdict_lbl_->setText(
        QStringLiteral("<div style=\"font-size:17px; font-weight:bold; color:%1;\">%2</div>"
                       "<div style=\"font-size:13px; color:%1; margin-top:4px;\">%3</div>"
                       "<table width=\"100%\" cellspacing=\"0\" cellpadding=\"0\" style=\"margin-top:10px;\"><tr>"
                       "<td width=\"50%\" valign=\"top\" style=\"padding-right:14px;\">"
                       "<div style=\"font-size:10px; color:%4;\">ĐỌC BẬC 2</div>%5</td>"
                       "<td width=\"50%\" valign=\"top\">"
                       "<div style=\"font-size:10px; color:%6;\">RỦI RO · ĐIỂM GÃY</div>%7</td>"
                       "</tr></table>")
            .arg(hhp::css(hhp::c_text()), esc(v.value("stance").toString()), esc(headline), hhp::css(hhp::c_muted()),
                 list_html(v.value("reads").toArray(), hhp::c_text()), hhp::css(hhp::c_rich()),
                 list_html(v.value("risks").toArray(), hhp::c_muted())) +
        // The card is the most advice-like block on screen: always close it with its own disclaimer.
        QStringLiteral("<div style=\"font-size:11px; color:%1; margin-top:8px;\">%2</div>")
            .arg(hhp::css(hhp::c_muted()), esc(v.value("disclaimer").toString().isEmpty()
                                                   ? tr("Tham khảo, KHÔNG khuyến nghị.")
                                                   : v.value("disclaimer").toString())));
    verdict_card_->show();
}

void HhpValuationPanel::render_index() {
    const QString m = metric_label(metric_);
    const bool book = metric_ == QLatin1String("pb");
    index_title_->setText(tr("🇻🇳 VNINDEX — VÙNG ĐỊNH GIÁ THỰC (±1σ / ±2σ) · %1").arg(m));
    // The chart instance is reused across P/E↔P/B: forget the previous metric's notes and forecast first.
    index_chart_->set_forecast(0, {}, {});
    index_chart_->set_notes({});
    index_fc_note_->clear();
    index_fc_note_->setToolTip(QString());
    index_fc_note_->hide();

    const QJsonObject ix = data_.value("index").toObject().value(metric_).toObject();
    if (ix.isEmpty()) {
        index_stats_->clear();
        index_stats_->hide();
        index_chart_->clear(tr("Thiếu dữ liệu index %1").arg(m));
        return;
    }

    // 3-year forecast block (null when missing, off-anchor or malformed — hhp_valuation.py says why in
    // meta.warnings) and the sell-side targets of the index.
    const QJsonObject fc_scope = data_.value("forecast").toObject().value("VNINDEX").toObject();
    const QJsonObject fc = fc_scope.value(metric_).toObject();
    const QVector<hhp::HhpChartSeries> fc_series = hhp::index_forecast_series(fc);
    const bool has_fc = !fc_series.isEmpty();

    QVector<Stat> stats = {
        {tr("%1 hiện tại").arg(m), esc(hhp::fmt_ratio(hhp::num(ix.value("now")), 3)), hhp::c_text()},
        {tr("%1 trung bình").arg(m), esc(hhp::fmt_ratio(hhp::num(ix.value("mean")), 3)), hhp::c_muted()},
        {tr("Độ lệch chuẩn σ"), sigma_zone(hhp::num(ix.value("sigma")), ix.value("zone").toString()),
         hhp::zone_color(ix.value("zone_key").toString())},
        {QStringLiteral("VNINDEX"), esc(fmt_level(hhp::num(ix.value("price_now")))), hhp::c_idx()},
    };
    const QJsonObject fwd = ix.value("forward").toObject();
    if (has_fc) {
        // Growth per year from the forecast consensus ('*' = EST year) + the band at 31/12 of next year.
        QStringList years, values;
        for (const QJsonValue& gv : fc.value("growth").toArray()) {
            const QJsonObject g = gv.toObject();
            if (g.value("year").toInt(0) <= 0 || years.size() >= 4)
                continue;
            years << QString::number(g.value("year").toInt());
            values << hhp::growth_text(g);
        }
        if (!years.isEmpty())
            stats.append({(book ? QStringLiteral("BVPS ") : QStringLiteral("EPS ")) + years.join(QStringLiteral(" · ")),
                          esc(values.join(QStringLiteral(" · "))), hhp::c_text(), 14});
        const QJsonObject ms = forecast_milestone(fc, ix.value("as_of").toString());
        if (!ms.isEmpty())
            stats.append({tr("Dải DP %1").arg(hhp::fcview::date_vn(ms.value("date").toString())),
                          esc(tr("TB %1 · đắt %2")
                                  .arg(fmt_level(hhp::num(ms.value("fair"))), fmt_level(hhp::num(ms.value("rich1"))))),
                          hhp::c_muted()});
    } else if (!fwd.isEmpty()) {
        const QString raw_date = fwd.value("date").toString();
        const QDate date = QDate::fromString(raw_date, Qt::ISODate);
        const QString date_txt = date.isValid() ? date.toString(QStringLiteral("dd/MM/yyyy")) : raw_date;
        QString caption = tr("Dự phóng %1").arg(date_txt);
        const double growth = hhp::num(fwd.value("growth"));
        if (hhp::has(growth))
            caption += QStringLiteral(" (") + hhp::fmt_pct(growth * 100.0, 0) + tr(", giả định HHP)");
        stats.append({caption,
                      esc(tr("TB %1 · đắt %2")
                              .arg(fmt_level(hhp::num(fwd.value("fair"))), fmt_level(hhp::num(fwd.value("rich1"))))),
                      hhp::c_muted()});
    }
    index_stats_->setText(stat_row_html(stats));
    index_stats_->show();

    // Chart levels are index POINTS; all six arrays share one x-grid. Forecast series go before the price
    // line: HhpChart snaps keynotes onto the last non-forecast line.
    const QJsonObject chart = ix.value("chart").toObject();
    const auto pts = [&chart](const char* key) { return hhp::to_points(chart.value(QLatin1String(key)).toArray()); };
    QVector<hhp::HhpChartSeries> series = {
        make_series(Kind::Band, tr("Vùng rẻ theo %1 (−2σ…−1σ)").arg(m), hhp::c_cheap(), 1.6, 0.30, pts("cheap1"),
                    pts("cheap2")),
        make_series(Kind::Band, tr("Vùng mắc theo %1 (+1σ…+2σ)").arg(m), hhp::c_rich(), 1.6, 0.26, pts("rich2"),
                    pts("rich1")),
        make_series(Kind::Dashed, tr("Điểm số %1 trung bình").arg(m), hhp::c_fair(), 1.2, 1.0, pts("fair")),
    };
    series += fc_series;
    series << make_series(Kind::Line, QStringLiteral("VNINDEX"), hhp::c_idx(), 2.4, 1.0, pts("price"));

    const QJsonArray targets = fc_scope.value("targets").toArray();
    QVector<hhp::HhpChartNote> notes = hhp::keynote_notes(data_.value("keynotes").toArray(), QStringLiteral("VNINDEX"),
                                                          metric_);
    const bool has_keynotes = !notes.isEmpty();
    if (has_fc)
        notes += hhp::target_notes(targets);
    if (has_fc) {
        double x0 = hhp::num(fc.value("x0"));
        if (!hhp::has(x0))
            x0 = fc_series.last().points.first().x();
        index_chart_->set_forecast(x0, tr("Dự phóng 3 năm (nét đứt)"), hhp::forecast_basis_spans(fc, book));
    }
    index_chart_->set_notes(notes);

    QStringList note_parts;
    if (has_fc) {
        note_parts << hhp::forecast_basis_html(fc, book);
        // Always state it — unless the bridge's caveats (shown by forecast_basis_html) already do.
        const QJsonArray caveats = fc.value("caveats").toArray();
        if (std::none_of(caveats.begin(), caveats.end(), [](const QJsonValue& c) {
                return c.toString().contains(QStringLiteral("KHÔNG dự báo giá"));
            }))
            note_parts << span(esc(tr("Chỉ dải định giá dịch theo %1 dự phóng — KHÔNG dự báo giá. Tham khảo, không "
                                      "khuyến nghị.")
                                       .arg(book ? QStringLiteral("BVPS") : QStringLiteral("EPS"))),
                               hhp::c_muted());
        // Run time of the bridge + its warnings (dispersion, thin sources, dropped CapIQ values …): the line
        // names the time, the tooltip lists the warnings — this chart's scope first.
        const QJsonObject fmeta = data_.value("forecast").toObject().value("meta").toObject();
        QStringList fwarn, other_scope;
        for (const QJsonValue& w : fmeta.value("warnings").toArray()) {
            const QString t = w.toString().trimmed();
            if (t.isEmpty())
                continue;
            (t.startsWith(QLatin1String("VN30")) || t.startsWith(QLatin1String("VN100")) ? other_scope : fwarn) << t;
        }
        fwarn += other_scope;
        const QString generated = fcast_generated_text(fmeta.value("generated").toString());
        QString run_line = tr("Dự phóng cập nhật %1").arg(generated.isEmpty() ? QStringLiteral("[CẦN DATA]") : generated);
        if (!fwarn.isEmpty())
            run_line += tr(" · %1 cảnh báo của cầu nối — rê chuột để xem").arg(fwarn.size());
        note_parts << span(esc(run_line), hhp::c_muted());
        QString tip = hhp::forecast_sources_html(fc, book);
        if (!fwarn.isEmpty()) {
            constexpr int kMaxWarn = 8;
            QStringList lines;
            for (int i = 0; i < std::min<int>(kMaxWarn, fwarn.size()); ++i)
                lines << QStringLiteral("⚠ ") + fwarn.at(i);
            if (fwarn.size() > kMaxWarn)
                lines << tr("… và %1 cảnh báo khác (forecast.meta.warnings)").arg(fwarn.size() - kMaxWarn);
            tip += QStringLiteral("<br><br><b>%1</b><br>").arg(esc(tr("Cảnh báo của cầu nối dự phóng"))) +
                   span(esc(lines.join(QStringLiteral("\n"))).replace(QStringLiteral("\n"), QStringLiteral("<br>")),
                        hhp::c_rich());
        }
        index_fc_note_->setToolTip(tip);
    }
    if (has_keynotes || (has_fc && !targets.isEmpty()))
        note_parts << notes_key(has_fc && !targets.isEmpty());
    if (!note_parts.isEmpty()) {
        index_fc_note_->setText(note_parts.join(QStringLiteral("<br>")));
        index_fc_note_->show();
    }
    // Right axis in the ratio itself: index points ÷ current EPS (BVPS). base = fair ÷ μ at the last
    // point — the same base the right edge of the bands is built on, so μ ± kσ read off exactly there.
    const QVector<QPointF> fair = pts("fair");
    const double mean = hhp::num(ix.value("mean"));
    const double base = (!fair.isEmpty() && hhp::has(mean) && mean > 0) ? fair.last().y() / mean : hhp::kNaN;
    index_chart_->set_right_scale(hhp::has(base) ? base : 0.0,
                                  metric_ == QLatin1String("pb") ? tr("P/B (lần) · theo BVPS hiện tại")
                                                                 : tr("P/E (lần) · theo EPS hiện tại"),
                                  1);
    plot(index_chart_, series, tr("Điểm số"), 0, true, tr("Thiếu dữ liệu index %1").arg(m));
}

// ── VNINDEX TOÀN SỬ view ─────────────────────────────────────────────────────

void HhpValuationPanel::set_index_view(const QString& view) {
    const QString v = view == QLatin1String("full") ? QStringLiteral("full") : QStringLiteral("8y");
    if (v == index_view_) {
        update_index_view_styles();
        return;
    }
    index_view_ = v;
    if (v == QLatin1String("full")) {
        if (!index_full_chart_) {
            index_full_chart_ = new hhp::HhpChart(true, index_stack_);
            index_full_chart_->set_plot_min_height(800);
            index_full_chart_->set_log_y(full_log_); // no series yet: stored, applied by the first plot
            // The LOG pill follows the axis actually drawn: a range / DỰ PHÓNG change can bring a value ≤ 0 into view.
            index_full_chart_->set_log_active_listener([this](bool) { update_index_view_styles(); });
            index_stack_->addWidget(index_full_chart_);
            // Label density follows the years on screen (ALL / 10Y / 5Y …).
            connect(index_full_chart_, &hhp::HhpChart::range_changed, this, [this](const QString&) { apply_full_notes(); });
        }
        index_stack_->setCurrentWidget(index_full_chart_);
        // Lazy: first open, or an overview fetch ran in 8 NĂM since the last history (on_fetch invalidates
        // history_fetched_at_; in TOÀN SỬ, FETCH refreshes both).
        if (!history_fetching_ && (!history_loaded_ || !history_fetched_at_.isValid()))
            fetch_history();
        render_index_full();
    } else {
        index_stack_->setCurrentWidget(index_chart_);
        index_stats_->setToolTip(QString());
        if (loaded_)
            render_index(); // re-sets title, stats and note line: the 8 NĂM path as before
    }
    update_index_view_styles();
}

void HhpValuationPanel::set_full_log(bool on) {
    full_log_ = on;
    if (index_full_chart_)
        index_full_chart_->set_log_y(on); // series unchanged: a rebuild is enough
    update_index_view_styles();
}

void HhpValuationPanel::update_index_view_styles() {
    const bool full = index_view_ == QLatin1String("full");
    if (btn_ix_8y_)
        btn_ix_8y_->setStyleSheet(pill_style(!full));
    if (btn_ix_full_)
        btn_ix_full_->setStyleSheet(pill_style(full));
    if (!btn_ix_log_)
        return;
    btn_ix_log_->setVisible(full);
    const bool drawn = history_.value("history").toObject().value("price").toObject().value("points").toArray().size() >= 2;
    const bool fallback = full_log_ && index_full_chart_ && drawn && !index_full_chart_->log_active();
    // Gold only while the log axis is in effect; asked for but not applicable (fallback) → unlit with a dashed red
    // outline, so the pill never claims a log axis over a linear chart.
    btn_ix_log_->setStyleSheet(fallback ? pill_style(false) + QStringLiteral("QPushButton { border: 1px dashed %1; }")
                                                                  .arg(hhp::css(hhp::c_rich()))
                                        : pill_style(full_log_));
    btn_ix_log_->setToolTip(fallback    ? tr("Thang log không áp dụng (có giá trị ≤ 0) — đang vẽ tuyến tính")
                            : full_log_ ? tr("Trục log (mặc định ở TOÀN SỬ): dải giá theo P/E·P/B giữ độ dày không đổi "
                                             "qua các thời kỳ, bong bóng 2001/2007 vẫn đọc được. Bấm để chuyển tuyến tính.")
                                        : tr("Đang vẽ tuyến tính. Bấm để bật trục log (mặc định ở TOÀN SỬ)."));
}

void HhpValuationPanel::fetch_history() {
    history_fetching_ = true;
    services::EconomicsService::instance().execute(QString(kSourceId), QString(kScript), QStringLiteral("history"), {},
                                                   req_history_, /*force=*/true);
}

void HhpValuationPanel::apply_history(const QJsonObject& data) {
    history_ = data;
    history_loaded_ = true;
    history_err_.clear();
    render_index_full();
    LOG_INFO("HhpValuationPanel",
             QString("Toàn sử VNINDEX: %1").arg(data.value("history").isObject() ? "nạp xong" : "không có (history null)"));
}

void HhpValuationPanel::apply_full_notes() {
    if (!index_full_chart_)
        return;
    const QJsonObject hist = history_.value("history").toObject();
    const QVector<QPointF> price = hhp::to_points(hist.value("price").toObject().value("points").toArray());
    if (index_view_ != QLatin1String("full") || price.isEmpty()) {
        index_full_chart_->set_notes({});
        return;
    }
    const QJsonObject hm = hist.value(metric_).toObject();
    const QJsonArray keynotes = hist.value("keynotes").toArray();
    QHash<QString, QJsonObject> by_id;
    for (const QJsonValue& v : keynotes)
        by_id.insert(v.toObject().value("id").toString(), v.toObject());
    QVector<hhp::HhpChartNote> notes = hhp::keynote_notes(keynotes, QStringLiteral("VNINDEX"), metric_);
    for (hhp::HhpChartNote& n : notes) {
        const QJsonObject ev = by_id.value(n.id);
        const int pf = ev.value("priority_full").toInt(0); // one rule for the whole history (zigzag 30% = P1)
        if (pf >= 1 && pf <= 3)
            n.priority = pf;
        if (n.x_ms < price.first().x())
            n.y = hhp::fcview::event_close(ev, QStringLiteral("VNINDEX")); // before the line: at its own close
    }
    if (!hm.isEmpty())
        notes += hhp::hist::ratio_point_notes(hm.value("points").toArray(), metric_, hm.value("long").toObject());
    // ◆ sell-side targets (overview): always passed — a target is an index level, independent of the metric's growth
    // path. The note layer hides those beyond the drawn x-range (no long-window forecast or DỰ PHÓNG off → the axis ends
    // at the last close); render_index_full() says so in the note lines.
    notes += hhp::target_notes(
        data_.value("forecast").toObject().value("VNINDEX").toObject().value("targets").toArray());
    const QVector<QPointF> fc_fair =
        hhp::to_points(hm.value("forecast").toObject().value("points").toObject().value("fair").toArray());
    qreal last = price.last().x();
    if (!fc_fair.isEmpty() && index_full_chart_->forecast_visible())
        last = std::max(last, fc_fair.last().x());
    const double years = hhp::hist::years_visible(index_full_chart_->range(), price.first().x(), last);
    index_full_chart_->set_notes(hhp::hist::thin_labels(notes, years));
}

void HhpValuationPanel::render_index_full() {
    if (index_view_ != QLatin1String("full") || !index_full_chart_)
        return;
    const QString m = metric_label(metric_);
    const bool book = metric_ == QLatin1String("pb");
    hhp::HhpChart* chart = index_full_chart_;
    chart->set_forecast(0, {}, {});
    chart->set_notes({});
    index_fc_note_->clear();
    index_fc_note_->setToolTip(QString());
    index_fc_note_->hide();

    // Overview (engine, 8 NĂM) block of this metric: the current ratio and the fallback stat row.
    const QJsonObject ix = data_.value("index").toObject().value(metric_).toObject();
    const QJsonObject hist = history_.value("history").toObject();
    const QJsonObject hm = hist.value(metric_).toObject();
    QStringList warnings;
    for (const QJsonValue& w : history_.value("meta").toObject().value("warnings").toArray())
        if (!w.toString().trimmed().isEmpty())
            warnings << w.toString().trimmed();
    for (const QJsonValue& w : hist.value("meta").toObject().value("warnings").toArray())
        if (!w.toString().trimmed().isEmpty() && !warnings.contains(w.toString().trimmed()))
            warnings << w.toString().trimmed();

    // Stat row without the long window (not loaded / null / failed): the engine reading + σ DÀI HẠN [CẦN DATA].
    const auto fallback_stats = [&]() {
        const QVector<Stat> stats = {
            {tr("%1 hiện tại").arg(m), esc(hhp::fmt_ratio(hhp::num(ix.value("now")), 3)), hhp::c_text()},
            {tr("σ 8 NĂM · μ %1").arg(hhp::fmt_ratio(hhp::num(ix.value("mean")), 2)),
             sigma_zone(hhp::num(ix.value("sigma")), ix.value("zone").toString()),
             hhp::zone_color(ix.value("zone_key").toString())},
            {tr("σ DÀI HẠN"), esc(QStringLiteral("[CẦN DATA]")), hhp::c_muted()},
            {QStringLiteral("VNINDEX"), esc(fmt_level(hhp::num(ix.value("price_now")))), hhp::c_idx()},
        };
        index_stats_->setText(stat_row_html(stats));
        index_stats_->setToolTip(warnings.isEmpty() ? QString()
                                                    : QStringLiteral("<span>%1</span>")
                                                          .arg(esc(warnings.join(QStringLiteral("\n")))
                                                                   .replace(QStringLiteral("\n"), QStringLiteral("<br>"))));
        index_stats_->show();
    };

    const QVector<QPointF> price = hhp::to_points(hist.value("price").toObject().value("points").toArray());
    if (!history_loaded_ || hist.isEmpty() || price.isEmpty()) {
        index_title_->setText(tr("🇻🇳 VNINDEX TOÀN SỬ · %1").arg(m));
        fallback_stats();
        QString msg;
        if (!history_loaded_ && history_fetching_)
            msg = tr("Đang nạp toàn sử VNINDEX…");
        else if (!history_err_.isEmpty())
            msg = tr("⚠ Nạp toàn sử lỗi — %1\nBấm FETCH để thử lại · 8 NĂM không bị ảnh hưởng.").arg(history_err_);
        else if (!history_loaded_)
            msg = tr("Chưa nạp toàn sử VNINDEX — bấm FETCH.");
        else if (!hist.isEmpty())
            msg = tr("Toàn sử VNINDEX thiếu chuỗi giá (price.points).");
        else
            msg = warnings.isEmpty() ? tr("Chưa có dữ liệu toàn sử VNINDEX (history null).")
                                     : QStringLiteral("⚠ ") + warnings.join(QStringLiteral("\n⚠ "));
        chart->clear(msg);
        update_index_view_styles();
        return;
    }

    const QJsonObject lng = hm.value("long").toObject();
    const QJsonObject eight = hm.value("eight").toObject();
    const QString first_iso = hist.value("price").toObject().value("first_date").toString();
    QString title = tr("🇻🇳 VNINDEX TOÀN SỬ %1→").arg(first_iso.isEmpty() ? hhp::fmt_date(price.first().x())
                                                                          : hhp::fcview::date_vn(first_iso));
    if (!hm.isEmpty())
        title += tr(" · DẢI σ DÀI HẠN %1→").arg(hhp::hist::month_vn(hhp::hist::band_from_iso(hm)));
    else
        title += tr(" · THIẾU DẢI %1 DÀI HẠN").arg(m);
    index_title_->setText(title + QStringLiteral(" · ") + m);

    // ── Series: long bands (from long.from) → long-window forecast → the price line (last: the main line) ──
    QVector<hhp::HhpChartSeries> series;
    const QJsonObject hfc = hm.value("forecast").toObject();
    QVector<hhp::HhpChartSeries> fc_series;
    if (!hm.isEmpty()) {
        series += hhp::hist::band_series(hm.value("chart").toObject());
        fc_series = hhp::index_forecast_series(hfc);
        series += fc_series;
    }
    series << make_series(Kind::Line, QStringLiteral("VNINDEX"), hhp::c_idx(), 2.4, 1.0, price);
    const bool has_hfc = !fc_series.isEmpty();

    // Overview forecast (growth consensus, ◆ targets): shared with 8 NĂM — the long band only changes the multiple.
    const QJsonObject fc = data_.value("forecast").toObject().value("VNINDEX").toObject().value(metric_).toObject();
    const bool has_fc = !hhp::index_forecast_series(fc).isEmpty();
    if (has_hfc) {
        double x0 = hhp::num(hfc.value("x0"));
        if (!hhp::has(x0))
            x0 = fc_series.last().points.first().x();
        chart->set_forecast(x0, tr("Dự phóng 3 năm (nét đứt) · dải dài hạn"),
                            has_fc ? hhp::forecast_basis_spans(fc, book) : QVector<hhp::HhpChartSpan>());
    }
    // Right axis in the ratio: index points ÷ current EPS (BVPS) = fair ÷ μ_long at the last band point (= engine base).
    const QVector<QPointF> fair = hhp::to_points(hm.value("chart").toObject().value("fair").toArray());
    const double mean_long = hhp::num(lng.value("mean"));
    const double base = (!fair.isEmpty() && hhp::has(mean_long) && mean_long > 0) ? fair.last().y() / mean_long : hhp::kNaN;
    chart->set_right_scale(hhp::has(base) ? base : 0.0,
                           book ? tr("P/B (lần) · theo BVPS hiện tại") : tr("P/E (lần) · theo EPS hiện tại"), 1);
    QElapsedTimer timer;
    timer.start();
    plot(chart, series, tr("Điểm số"), 0, true, tr("Thiếu dữ liệu toàn sử VNINDEX"));
    apply_full_notes();
    LOG_DEBUG("HhpValuationPanel", QString("render_index_full %1 ms").arg(timer.elapsed()));

    // ── Stat rows: both σ windows side by side + the chip ──
    const double now = hhp::has(hhp::num(ix.value("now"))) ? hhp::num(ix.value("now")) : hhp::num(lng.value("now"));
    QVector<Stat> row1 = {{tr("%1 hiện tại").arg(m), esc(hhp::fmt_ratio(now, 3)), hhp::c_text()}};
    if (!eight.isEmpty())
        row1.append({tr("σ 8 NĂM · %1→ · μ %2 · phân vị %3")
                         .arg(hhp::hist::month_vn(eight.value("from").toString()),
                              hhp::fmt_ratio(hhp::num(eight.value("mean")), 2),
                              hhp::hist::pct_text(hhp::num(eight.value("pct")))),
                     sigma_zone(hhp::num(eight.value("sigma")), eight.value("zone").toString()),
                     hhp::zone_color(eight.value("zone_key").toString())});
    else
        row1.append({tr("σ 8 NĂM · μ %1").arg(hhp::fmt_ratio(hhp::num(ix.value("mean")), 2)),
                     sigma_zone(hhp::num(ix.value("sigma")), ix.value("zone").toString()),
                     hhp::zone_color(ix.value("zone_key").toString())});
    if (!lng.isEmpty())
        row1.append({tr("σ DÀI HẠN · %1→ · μ %2 · phân vị %3")
                         .arg(hhp::hist::month_vn(lng.value("from").toString()),
                              hhp::fmt_ratio(hhp::num(lng.value("mean")), 2),
                              hhp::hist::pct_text(hhp::num(lng.value("pct")))),
                     sigma_zone(hhp::num(lng.value("sigma")), lng.value("zone").toString()),
                     hhp::zone_color(lng.value("zone_key").toString())});
    else
        row1.append({tr("σ DÀI HẠN"), esc(QStringLiteral("[CẦN DATA]")), hhp::c_muted()});
    const QJsonValue agree = hm.value("windows_agree");
    if (agree.isBool() && !lng.isEmpty())
        row1.append({tr("HAI CỬA SỔ"), esc(agree.toBool() ? tr("CÙNG VÙNG") : tr("LỆCH VÙNG")),
                     agree.toBool() ? hhp::c_muted() : hhp::c_gold()});
    const QJsonObject pr = hist.value("price").toObject();
    const QJsonObject hbase = hist.value("base").toObject();
    const double lxb = hhp::num(pr.value("level_x_base"));
    QString idx_cap = QStringLiteral("VNINDEX");
    if (hhp::has(lxb) && hhp::has(hhp::num(hbase.value("value"))))
        idx_cap += tr(" · ×%1 từ gốc %2").arg(hhp::fmt_ratio(lxb, 1), fmt_level(hhp::num(hbase.value("value"))));
    const double price_now = hhp::has(hhp::num(ix.value("price_now"))) ? hhp::num(ix.value("price_now")) : price.last().y();
    row1.append({idx_cap, esc(fmt_level(price_now)), hhp::c_idx()});
    QString stats_html = stat_row_html(row1);
    if (has_fc && has_hfc) {
        QVector<Stat> row2;
        QStringList years, values;
        for (const QJsonValue& gv : fc.value("growth").toArray()) {
            const QJsonObject g = gv.toObject();
            if (g.value("year").toInt(0) <= 0 || years.size() >= 4)
                continue;
            years << QString::number(g.value("year").toInt());
            values << hhp::growth_text(g);
        }
        if (!years.isEmpty())
            row2.append({(book ? QStringLiteral("BVPS ") : QStringLiteral("EPS ")) + years.join(QStringLiteral(" · ")),
                         esc(values.join(QStringLiteral(" · "))), hhp::c_text(), 14});
        const QJsonObject ms = forecast_milestone(hfc, ix.value("as_of").toString());
        if (!ms.isEmpty())
            row2.append({tr("Dải DP dài hạn %1").arg(hhp::fcview::date_vn(ms.value("date").toString())),
                         esc(tr("TB %1 · đắt %2")
                                 .arg(fmt_level(hhp::num(ms.value("fair"))), fmt_level(hhp::num(ms.value("rich1"))))),
                         hhp::c_muted()});
        if (!row2.isEmpty())
            stats_html += stat_row_html(row2);
    }
    index_stats_->setText(stats_html);
    index_stats_->setToolTip(hm.isEmpty() ? (warnings.isEmpty() ? QString()
                                                                : QStringLiteral("<span>%1</span>")
                                                                      .arg(esc(warnings.join(QStringLiteral(" · ")))))
                                          : hhp::hist::windows_tooltip_html(hm, warnings));
    index_stats_->show();

    // ── Note lines (every date read from the payload) ──
    const auto muted = [](const QString& t) { return span(esc(t), hhp::c_muted()); };
    QStringList lines;
    const QString spans = hhp::hist::price_spans_text(pr.value("src_spans").toArray());
    if (!spans.isEmpty())
        lines << muted(spans);
    if (hm.isEmpty()) {
        lines << span(esc(tr("Thiếu dải %1 dài hạn — chỉ vẽ giá và keynote.").arg(m)), hhp::c_rich());
    } else {
        lines << muted(hhp::hist::band_note_text(hm));
        lines << muted(hhp::hist::pre_band_note_text(hm, metric_));
    }
    QStringList gap_txt;
    for (const QJsonValue& gv : hist.value("gaps").toArray()) {
        const QJsonObject g = gv.toObject();
        gap_txt << QStringLiteral("%1–%2 %3").arg(hhp::fcview::date_vn(g.value("from").toString()),
                                                  hhp::fcview::date_vn(g.value("to").toString()),
                                                  g.value("what").toString());
    }
    if (!gap_txt.isEmpty())
        lines << span(esc(tr("⚠ Lỗ dữ liệu: %1").arg(gap_txt.join(QStringLiteral(" · ")))), hhp::c_rich());
    if (has_hfc) {
        if (has_fc)
            lines << hhp::forecast_basis_html(fc, book);
        lines << muted(tr("Dải dự phóng dài hạn = cùng đường %1 × (μ ± kσ) dài hạn — KHÔNG dự báo giá. Tham khảo, không "
                          "khuyến nghị.")
                           .arg(book ? QStringLiteral("BVPS") : QStringLiteral("EPS")));
    } else {
        // ◆ past the last close cannot show without the long-window forecast (the x-axis ends there): say so.
        int n_hidden = 0;
        for (const hhp::HhpChartNote& t :
             hhp::target_notes(data_.value("forecast").toObject().value("VNINDEX").toObject().value("targets").toArray()))
            n_hidden += t.x_ms > price.last().x() ? 1 : 0;
        if (n_hidden > 0)
            lines << muted(tr("◆ %1 mục tiêu VN-Index của CTCK không hiện: kỳ hạn sau phiên cuối %2, mà khung này thiếu dải "
                              "dự phóng dài hạn%3.")
                               .arg(QString::number(n_hidden), hhp::fmt_date(price.last().x()),
                                    has_fc ? tr(" — xem ở 8 NĂM") : QString()));
    }
    if (!history_err_.isEmpty())
        lines << span(esc(tr("⚠ Làm mới toàn sử lỗi — %1 (đang hiện bản đã nạp trước)").arg(history_err_)), hhp::c_rich());
    lines << muted(tr("▲ đỉnh · ▼ đáy · ◇ điểm định giá rời (viền chấm) · ◆ mục tiêu VN-Index của CTCK — khung dài chỉ gắn "
                      "nhãn mốc ưu tiên; rê chuột vào mọi ký hiệu."));
    index_fc_note_->setText(lines.join(QStringLiteral("<br>")));
    const QJsonObject hmeta = hist.value("meta").toObject();
    const QJsonObject hfile = history_.value("meta").toObject().value("history_file").toObject();
    QString note_tip = tr("Toàn sử dựng lúc %1").arg(hmeta.value("generated").toString(QStringLiteral("[CẦN DATA]")));
    if (!hfile.isEmpty())
        note_tip += tr(" · tệp %1").arg(hfile.value("mtime").toString());
    index_fc_note_->setToolTip(QStringLiteral("<span>%1</span>").arg(esc(note_tip)));
    index_fc_note_->show();
    update_index_view_styles();
}

void HhpValuationPanel::render_basket() {
    const QString m = metric_label(metric_);
    basket_title_->setText(tr("🧺 RỔ %1 — %2 SO VỚI LỊCH SỬ CHÍNH RỔ").arg(universe_, m));

    // Reused across VN30↔VN100 and P/E↔P/B: forget the previous notes and forecast first.
    basket_chart_->set_forecast(0, {}, {});
    basket_chart_->set_notes({});
    basket_note_->setToolTip(QString());

    const QJsonValue baskets = data_.value("baskets");
    const QJsonObject basket = baskets.toObject().value(universe_).toObject();
    const QJsonObject b = basket.value(metric_).toObject();
    const QVector<QPointF> ratio = hhp::to_points(b.value("series").toArray());
    if (b.isEmpty() || ratio.isEmpty()) {
        basket_stats_->clear();
        basket_stats_->hide();
        // Name the actual cause: a missing file is not a missing metric.
        if (!baskets.isObject())
            basket_chart_->clear(
                tr("Chưa có hhp_baskets.json — chạy: python3 hhp_index_baskets.py (thư mục knowledge_os)."));
        else if (basket.isEmpty())
            basket_chart_->clear(
                tr("hhp_baskets.json chưa có rổ %1 — chạy: python3 hhp_index_baskets.py.").arg(universe_));
        else
            basket_chart_->clear(tr("Rổ này chưa có %1.").arg(m));
        basket_note_->clear();
        basket_note_->hide();
        return;
    }

    const double mean = hhp::num(b.value("mean"));
    const double p1 = hhp::num(b.value("p1"));
    const double p2 = hhp::num(b.value("p2"));
    const double m1 = hhp::num(b.value("m1"));
    const double m2 = hhp::num(b.value("m2"));

    // Ratio "nếu giá đứng yên" along the forecast EPS (BVPS) path + flat bands extended (null → history only).
    const bool book = metric_ == QLatin1String("pb");
    const QJsonObject fc = data_.value("forecast").toObject().value(universe_).toObject().value(metric_).toObject();
    const QVector<hhp::HhpChartSeries> fc_series = hhp::basket_forecast_series(fc, m);
    const bool has_fc = !fc_series.isEmpty();

    QVector<Stat> stats = {
        {tr("%1 hiện tại").arg(m), esc(hhp::fmt_ratio(hhp::num(b.value("now")), 3)), hhp::c_text()},
        {tr("Trung bình"), esc(hhp::fmt_ratio(mean, 3)), hhp::c_muted()},
        {tr("Vị thế σ"), sigma_zone(hhp::num(b.value("sigma")), b.value("zone").toString()),
         hhp::zone_color(b.value("zone_key").toString())},
        {tr("Dải định giá"), esc(tr("rẻ <%1 · đắt >%2").arg(hhp::fmt_ratio(m1, 2), hhp::fmt_ratio(p1, 2))),
         hhp::c_text(), 14},
    };
    QString stats_tip;
    if (has_fc) {
        const QJsonObject ms = forecast_milestone(fc, b.value("as_of").toString());
        if (!ms.isEmpty()) {
            // zone null/"—" (e.g. σ bands inflated by known bad source data) → the σ reading is withheld: "—",
            // the bridge's zone_note (or note) goes into the tooltip.
            const QString zone = ms.value("zone").toString().trimmed();
            const bool zone_known = !zone.isEmpty() && zone != QStringLiteral("—");
            const QString ratio_txt = hhp::fmt_ratio(hhp::num(ms.value("ratio")), 2);
            stats.append({tr("%1 %2 nếu giá đứng yên").arg(m, hhp::fcview::date_vn(ms.value("date").toString())),
                          esc(ratio_txt + QStringLiteral(" · ") +
                              (zone_known ? hhp::fmt_sigma(hhp::num(ms.value("sigma"))) + QStringLiteral("σ")
                                          : QStringLiteral("—"))),
                          zone_known ? hhp::zone_color(zone_key_of(zone)) : hhp::c_muted(), 14});
            if (!zone_known) {
                QString zn = ms.value("zone_note").toString().trimmed();
                if (zn.isEmpty())
                    zn = ms.value("note").toString().trimmed();
                // In a tag: the tooltip is then read as rich text and the escaped entities render.
                stats_tip = QStringLiteral("<span>%1</span>")
                                .arg(esc(tr("Vị thế σ của mốc %1 để trống: %2")
                                             .arg(hhp::fcview::date_vn(ms.value("date").toString()),
                                                  zn.isEmpty() ? QStringLiteral("[CẦN DATA]") : zn)));
            }
        }
    }
    basket_stats_->setToolTip(stats_tip);
    basket_stats_->setText(stat_row_html(stats));
    basket_stats_->show();

    // Flat ±1σ/±2σ levels drawn on the ratio series' own x-grid.
    QVector<hhp::HhpChartSeries> series;
    if (hhp::has(m1) && hhp::has(m2))
        series << make_series(Kind::Band, tr("Vùng rẻ %1 (−2σ…−1σ)").arg(m), hhp::c_cheap(), 1.6, 0.30,
                              hhp::flat_like(ratio, m1), hhp::flat_like(ratio, m2));
    if (hhp::has(p1) && hhp::has(p2))
        series << make_series(Kind::Band, tr("Vùng mắc %1 (+1σ…+2σ)").arg(m), hhp::c_rich(), 1.6, 0.26,
                              hhp::flat_like(ratio, p2), hhp::flat_like(ratio, p1));
    if (hhp::has(mean))
        series << make_series(Kind::Dashed, tr("Trung bình"), hhp::c_fair(), 1.2, 1.0, hhp::flat_like(ratio, mean));
    series += fc_series; // before the ratio line: keynotes snap onto the last non-forecast line
    series << make_series(Kind::Line, QStringLiteral("%1 %2").arg(universe_, m), hhp::c_idx(), 2.4, 1.0, ratio);
    const QVector<hhp::HhpChartNote> notes = hhp::keynote_notes(data_.value("keynotes").toArray(), universe_, metric_);
    if (has_fc) {
        double x0 = hhp::num(fc.value("x0"));
        if (!hhp::has(x0))
            x0 = fc_series.last().points.first().x();
        basket_chart_->set_forecast(x0, tr("Dự phóng 3 năm (nét đứt)"), hhp::forecast_basis_spans(fc, book));
    }
    basket_chart_->set_notes(notes);
    basket_chart_->set_series(series, tr("%1 (lần)").arg(m), 1, false);

    QString label = basket.value("label").toString();
    if (label.isEmpty())
        label = universe_;
    const QString generated = data_.value("meta").toObject().value("baskets_generated").toString();
    QString note = tr("Vùng rẻ/đắt = ±1–2σ của CHÍNH rổ (Vietcap IQ index-valuation). %1. ").arg(label);
    if (!generated.isEmpty())
        note += tr("Cập nhật %1. ").arg(generated);
    note += tr("Tham khảo, không khuyến nghị.");
    QString html = esc(note);
    if (has_fc) {
        // Basket P/B reuses the VNINDEX BV growth (see its flag) → quote the VNINDEX retention ratio.
        const double r_vni = hhp::num(data_.value("forecast").toObject().value("VNINDEX").toObject().value("pb").toObject()
                                          .value("retention").toObject().value("r"));
        html += QStringLiteral("<br>") + hhp::forecast_basis_html(fc, book, r_vni) + QStringLiteral("<br>") +
                span(esc(tr("\"%1 nếu giá đứng yên\" = %1 hiện tại × %2 nay ÷ %2 dự phóng — KHÔNG dự báo giá.")
                             .arg(m, book ? QStringLiteral("BVPS") : QStringLiteral("EPS"))),
                     hhp::c_muted());
        basket_note_->setToolTip(hhp::forecast_sources_html(fc, book));
    }
    if (!notes.isEmpty())
        html += QStringLiteral("<br>") + notes_key(false);
    basket_note_->setText(html);
    basket_note_->show();
}

void HhpValuationPanel::render_exvic3() {
    const QJsonObject ex = data_.value("exvic3").toObject();
    if (ex.isEmpty()) {
        ex_section_->hide();
        return;
    }
    ex_section_->show();

    const double pe_full = hhp::num(ex.value("pe_full_now"));
    const double pe_ex = hhp::num(ex.value("pe_exv3_now"));
    const double pb_full = hhp::num(ex.value("pb_full_now"));
    const double pb_ex = hhp::num(ex.value("pb_exv3_now"));
    const double w3 = hhp::num(ex.value("w3_now"));
    const double sigma = hhp::num(ex.value("exv3_pe_sigma"));
    const QString zone = ex.value("exv3_pe_zone").toString();
    const QColor zone_c = hhp::zone_color(ex.value("exv3_pe_zone_key").toString());

    const auto arrow = [](double full, double ex_v3, const QColor& c, int decimals) {
        return esc(hhp::fmt_ratio(full, decimals)) + QStringLiteral(" → ") +
               span(esc(hhp::fmt_ratio(ex_v3, decimals)), c);
    };
    const QVector<Stat> stats = {
        {tr("P/E toàn bộ → Non-VIC3"), arrow(pe_full, pe_ex, hhp::c_cheap(), 2), hhp::c_text()},
        {tr("Vị thế Non-VIC3 (σ riêng)"), sigma_zone(sigma, zone), zone_c},
        {tr("P/B toàn bộ → Non-VIC3"), arrow(pb_full, pb_ex, hhp::c_blue(), 3), hhp::c_text()},
        {tr("Tỷ trọng họ Vin"), esc(hhp::has(w3) ? hhp::fmt_ratio(w3, 1) + QStringLiteral("%") : QStringLiteral("—")),
         hhp::c_idx()},
    };
    ex_stats_->setText(stat_row_html(stats));

    const QJsonObject s = ex.value("series").toObject();
    const auto pts = [&s](const char* key) { return hhp::to_points(s.value(QLatin1String(key)).toArray()); };
    const QString none = tr("Thiếu dữ liệu");
    plot(ex_pe_chart_,
         {make_series(Kind::Line, tr("P/E toàn bộ"), hhp::c_muted(), 1.4, 1.0, pts("pe_full")),
          make_series(Kind::Line, tr("P/E Non-VIC3"), hhp::c_gold(), 2.6, 1.0, pts("pe_exv3"))},
         tr("P/E (lần)"), 1, false, none);
    plot(ex_pb_chart_,
         {make_series(Kind::Line, tr("P/B toàn bộ"), hhp::c_muted(), 1.4, 1.0, pts("pb_full")),
          make_series(Kind::Line, tr("P/B Non-VIC3"), hhp::c_blue(), 2.6, 1.0, pts("pb_exv3"))},
         tr("P/B (lần)"), 2, false, none);
    plot(ex_w3_chart_, {make_series(Kind::Area, tr("Tỷ trọng họ Vin (%)"), hhp::c_rich(), 1.6, 0.25, pts("w3"))},
         QStringLiteral("%"), 0, true, none);

    // Data-driven only: every figure below comes from the payload.
    QString html = QStringLiteral("<b style=\"color:%1;\">Góc nhìn HHP / FiinTrade:</b> Chỉ số chung bị chi phối lớn "
                                  "bởi họ Vingroup")
                       .arg(hhp::css(hhp::c_gold()));
    const QJsonArray vic3 = ex.value("vic3").toArray();
    if (!vic3.isEmpty()) {
        const QJsonObject top = vic3.first().toObject();
        QString ticker = top.value("ticker").toString();
        if (ticker.isEmpty())
            ticker = QStringLiteral("VIC");
        html += esc(QStringLiteral(" (%1 P/E ~%2, vốn hóa %3 ngh.tỷ)")
                        .arg(ticker, hhp::fmt_ratio(hhp::num(top.value("pe")), 2),
                             hhp::fmt_vi(hhp::num(top.value("mcap_kty")))));
    }
    html += QStringLiteral(". Loại nhóm V, P/E phần còn lại của VNINDEX chỉ <b style=\"color:%1;\">%2×</b> "
                           "(vs %3× toàn bộ) — đang ở <b style=\"color:%4;\">%5</b> so lịch sử của chính nó.")
                .arg(hhp::css(hhp::c_cheap()), esc(hhp::fmt_ratio(pe_ex, 2)), esc(hhp::fmt_ratio(pe_full, 2)),
                     hhp::css(zone_c),
                     esc(hhp::fmt_sigma(sigma) + QStringLiteral("σ") +
                         (zone.isEmpty() ? QString() : QStringLiteral(" (") + zone + QStringLiteral(")"))));
    if (hhp::has(w3))
        html += QStringLiteral("<br>") +
                esc(tr("Tỷ trọng họ Vin %1% vốn hóa VNINDEX → rủi ro tập trung, \"méo\" định giá chỉ số chung.")
                        .arg(hhp::fmt_ratio(w3, 1)));
    ex_note_->setText(html);
}

void HhpValuationPanel::render_zone_chips() {
    const QJsonObject counts =
        data_.value("zone_counts").toObject().value(universe_).toObject().value(metric_).toObject();
    const qsizetype n = std::min<qsizetype>(chip_btns_.size(), static_cast<qsizetype>(std::size(kZoneChips)));
    for (qsizetype i = 0; i < n; ++i) {
        const ZoneChip& zc = kZoneChips[i];
        const QString key = QString::fromLatin1(zc.key);
        const bool on = zone_key_ == key;
        const QColor base = on ? hhp::c_gold() : hhp::c_text();
        // Count colour: green for cheap, red for rich, muted for neutral; "Tất cả" follows the caption.
        const QColor count_color = key.isEmpty() ? base : hhp::zone_color(key);
        const QJsonValue count = counts.value(QLatin1String(zc.count_key));
        const QString count_txt = count.isDouble() ? QString::number(count.toInt()) : QStringLiteral("—");
        chip_lbls_[i]->setText(QStringLiteral("%1 <b>%2</b>")
                                   .arg(span(esc(QString::fromUtf8(zc.label)), base), span(count_txt, count_color)));
        chip_btns_[i]->setStyleSheet(chip_style(on));
        chip_btns_[i]->setFixedWidth(chip_lbls_[i]->sizeHint().width() + 26);
    }
}

void HhpValuationPanel::apply_screener_filter() {
    screener_title_->setText(
        tr("🔎 BỘ LỌC ĐỊNH GIÁ %1 — MỖI MÃ ĐANG Ở ĐÂU SO VỚI LỊCH SỬ CỦA CHÍNH NÓ").arg(universe_));
    table_->apply(universe_, metric_, zone_key_, search_edit_->text().trimmed(), reliable_chk_->isChecked());
    // No member list → no rows at all: say why instead of a "no match" that blames the filters.
    const bool no_members = loaded_ && data_.value("members").toObject().value(universe_).toArray().isEmpty();
    if (no_members)
        screener_msg_->setText(tr("Thiếu danh sách rổ %1 (hhp_basket_members.json) — chạy: python3 "
                                  "hhp_index_baskets.py (thư mục knowledge_os).")
                                   .arg(universe_));
    screener_msg_->setVisible(no_members);
    table_->setVisible(!no_members);
    update_count_and_height();
}

void HhpValuationPanel::update_count_and_height() {
    if (!table_)
        return;
    const int visible = table_->visible_count();

    QString html = esc(tr("%1 mã · %2").arg(QString::number(visible), metric_label(metric_)));
    QStringList missing;
    for (const QJsonValue& v : data_.value("missing").toObject().value(universe_).toArray()) {
        if (!v.toString().isEmpty())
            missing << v.toString();
    }
    const QColor dim(0x6b, 0x70, 0x79);
    if (!missing.isEmpty())
        html += span(esc(tr(" · chưa có dữ liệu: %1").arg(missing.join(QStringLiteral(", ")))), dim);
    // Members that have data but not this ratio (VPL has no P/E), and ratios stale upstream — so the
    // basket arithmetic adds up.
    QStringList no_metric;
    QStringList stale;
    const QString flag = member_flag(universe_);
    for (const QJsonValue& rv : data_.value("rows").toArray()) {
        const QJsonObject r = rv.toObject();
        if (!r.value(flag).toBool())
            continue;
        const QJsonValue b = r.value(metric_);
        if (!b.isObject())
            no_metric << r.value("tk").toString();
        else if (b.toObject().value("stale").toBool())
            stale << r.value("tk").toString();
    }
    const QString m = metric_label(metric_);
    if (!no_metric.isEmpty())
        html += span(esc(tr(" · không có %1: %2").arg(m, no_metric.join(QStringLiteral(", ")))), dim);
    if (!stale.isEmpty())
        html += span(esc(tr(" · %1 cũ, không xếp vùng: %2").arg(m, stale.join(QStringLiteral(", ")))), dim);
    count_lbl_->setText(html);

    // Fixed height = header + every visible row, so the table never scrolls by itself.
    const QHeaderView* header = table_->horizontalHeader();
    const int header_h = header->isHidden() ? 0 : header->sizeHint().height();
    int body = table_->verticalHeader()->length();
    if (body <= 0)
        body = std::max(1, visible) * kRowPx;
    const int hbar = table_->horizontalScrollBar()->sizeHint().height();
    table_->setFixedHeight(header_h + body + 2 * table_->frameWidth() + hbar + 4);
}

// ── Actions ──────────────────────────────────────────────────────────────────

void HhpValuationPanel::open_ticker(const QString& ticker) {
    const QString tk = ticker.trimmed();
    if (tk.isEmpty())
        return;
    if (dialog_)
        dialog_->close(); // WA_DeleteOnClose → QPointer clears itself

    auto* dlg = new hhp::HhpTickerDialog(tk, metric_, this);
    dlg->setAttribute(Qt::WA_DeleteOnClose);
    dialog_ = dlg;
    dlg->set_loading();
    dlg->show();
    dlg->raise();
    dlg->activateWindow();

    services::EconomicsService::instance().execute(QString(kSourceId), QString(kScript), QStringLiteral("ticker"), {tk},
                                                   req_ticker_ + tk, /*force=*/true);
}

void HhpValuationPanel::export_screener_csv() {
    if (!loaded_ || !table_)
        return;
    const QJsonArray rows = table_->visible_rows();
    if (rows.isEmpty())
        return;

    const QString m = metric_;
    const QString suggested = QDir::homePath() + QStringLiteral("/Downloads/hhp_%1_%2_%3.csv")
                                                     .arg(universe_, m, QDate::currentDate().toString("yyyyMMdd"));
    const QString path = QFileDialog::getSaveFileName(this, tr("Xuất CSV"), suggested, tr("CSV (*.csv)"));
    if (path.isEmpty())
        return;

    QFile file(path);
    if (!file.open(QIODevice::WriteOnly | QIODevice::Truncate)) {
        LOG_WARN("HhpValuationPanel", "Không ghi được CSV " + path + ": " + file.errorString());
        QMessageBox::warning(this, tr("Xuất CSV"), tr("Không ghi được tệp:\n%1\n%2").arg(path, file.errorString()));
        return;
    }
    file.write("\xEF\xBB\xBF"); // UTF-8 BOM so Excel reads the Vietnamese zone labels correctly
    QTextStream out(&file);
    out.setEncoding(QStringConverter::Utf8);

    const QStringList header = {
        QStringLiteral("ticker"),         QStringLiteral("in_vn30"),         QStringLiteral("price_now"),
        QStringLiteral("price_date"),     QStringLiteral("price_src"),
        m + QStringLiteral("_now"),       m + QStringLiteral("_mean"),       m + QStringLiteral("_sd"),
        m + QStringLiteral("_sigma"),     QStringLiteral("zone"),            QStringLiteral("reliable"),
        QStringLiteral("band_cheap2"),    QStringLiteral("band_cheap1"),     QStringLiteral("band_fair"),
        QStringLiteral("band_rich1"),     QStringLiteral("band_rich2"),      QStringLiteral("upside_to_fair_pct"),
        QStringLiteral("fa_rec"),         QStringLiteral("fwd_") + m + QStringLiteral("_2026F"),
        QStringLiteral("fwd_src"),        QStringLiteral("catalyst_rec"),    QStringLiteral("catalyst_upside"),
        QStringLiteral("catalyst_title"), QStringLiteral("capiq_fwd_pe_2026F"), QStringLiteral("capiq_fwd_pb_2026F"),
        QStringLiteral("capiq_tp"),       QStringLiteral("capiq_rec"),       QStringLiteral("capiq_upside_pct"),
        QStringLiteral("capiq_exported"),
    };
    out << header.join(QLatin1Char(',')) << "\n";

    for (const QJsonValue& rv : rows) {
        const QJsonObject r = rv.toObject();
        const QJsonObject b = r.value(m).toObject();
        const QJsonObject fwd = r.value("forward").toObject();
        const QJsonObject cat = r.value("fa_catalyst").toObject();
        const QJsonObject ciq = r.value("capiq").toObject();
        const QStringList cells = {
            csv_cell(r.value("tk")),
            csv_cell(r.value("in_vn30")),
            csv_cell(r.value("price_now")),
            csv_cell(r.value("price_date")),
            csv_cell(r.value("price_src")),
            csv_cell(b.value("now")),
            csv_cell(b.value("mean")),
            csv_cell(b.value("sd")),
            csv_cell(b.value("sigma")),
            csv_cell(b.value("zone")),
            csv_cell(b.value("reliable")),
            csv_cell(b.value("band_cheap2")),
            csv_cell(b.value("band_cheap1")),
            csv_cell(b.value("band_fair")),
            csv_cell(b.value("band_rich1")),
            csv_cell(b.value("band_rich2")),
            csv_cell(b.value("upside_to_fair_pct")),
            csv_cell(r.value("fa_rec")),
            csv_cell(fwd.value(m)),
            csv_cell(fwd.value("src")),
            csv_cell(cat.value("rec")),
            csv_cell(cat.value("upside")),
            csv_cell(cat.value("latest").toObject().value("title")),
            csv_cell(ciq.value("pe")),
            csv_cell(ciq.value("pb")),
            csv_cell(ciq.value("tp")),
            csv_cell(ciq.value("rec")),
            csv_cell(ciq.value("upside_pct")),
            csv_cell(ciq.value("exported")),
        };
        QStringList quoted;
        quoted.reserve(cells.size());
        for (const QString& c : cells)
            quoted << csv_quote(c);
        out << quoted.join(QLatin1Char(',')) << "\n";
    }
    out.flush();
    LOG_INFO("HhpValuationPanel", QString("Xuất %1 dòng bộ lọc HHP → %2").arg(rows.size()).arg(path));
}

void HhpValuationPanel::open_web_page() {
    if (view_ == QLatin1String("weekly")) {
        // The issue's own HTML file — only ever a local file inside the weekly issue dir.
        const QJsonObject wm = weekly_data_.value("meta").toObject();
        const QString path = wm.value("issue_file").toString();
        const QString dir = wm.value("issue_dir").toString();
        if (!path.isEmpty() && !dir.isEmpty() && QFileInfo(path).absolutePath() == QFileInfo(dir).absoluteFilePath() &&
            QFileInfo(path).fileName().startsWith(QLatin1String("hhp_weekly_")) &&
            QFileInfo(path).suffix() == QLatin1String("html") && QFileInfo::exists(path)) {
            if (!QDesktopServices::openUrl(QUrl::fromLocalFile(path)))
                LOG_WARN("HhpValuationPanel", "Không mở được bản tuần: " + path);
        } else {
            LOG_WARN("HhpValuationPanel", "Bản tuần chưa nạp hoặc tệp không hợp lệ: " + path);
        }
        return;
    }
    QUrl url(data_.value("meta").toObject().value("web_url").toString());
    // web_url comes from the pipeline JSON: only ever hand a web URL to the OS.
    if (!url.isValid() || (url.scheme() != QLatin1String("http") && url.scheme() != QLatin1String("https")))
        url = QUrl(QString(kDefaultWebUrl));
    if (!QDesktopServices::openUrl(url))
        LOG_WARN("HhpValuationPanel", "Không mở được trang web HHP: " + url.toString());
}

// ── BẢN TUẦN view ────────────────────────────────────────────────────────────

void HhpValuationPanel::set_view(const QString& view) {
    const QString v = view == QLatin1String("weekly") ? QStringLiteral("weekly") : QStringLiteral("live");
    if (v == view_)
        return;
    view_ = v;
    const bool weekly = view_ == QLatin1String("weekly");
    for (QWidget* w : std::as_const(live_ctrls_))
        w->setVisible(!weekly);
    for (QWidget* w : std::as_const(weekly_ctrls_))
        w->setVisible(weekly);
    update_toggle_styles();
    if (web_btn_)
        web_btn_->setToolTip(weekly ? tr("Mở tệp HTML của bản tuần đang xem trong trình duyệt")
                                    : tr("Mở trang Cowork hhp_vn100_valuation.html trong trình duyệt"));

    if (weekly) {
        if (weekly_loaded_) {
            show_content_page(weekly_page_idx_);
            render_weekly_fresh();
        } else if (weekly_fetching_) {
            show_loading(tr("Đang nạp bản tuần HHP…"));
        }
        if (!weekly_fetching_ && weekly_refresh_due())
            fetch_weekly();
        return;
    }
    if (loaded_) {
        show_content_page(page_idx_);
        render_meta();
    } else if (fetching_) {
        show_loading(tr("Đang nạp định giá HHP — VNINDEX · VN30 · VN100…"));
    }
    activate();
}

bool HhpValuationPanel::weekly_refresh_due() const {
    return !weekly_loaded_ || !weekly_fetched_at_.isValid() ||
           weekly_fetched_at_.secsTo(QDateTime::currentDateTimeUtc()) >= kWeeklyRefreshAfterSec;
}

void HhpValuationPanel::fetch_weekly() {
    weekly_fetching_ = true;
    const QString ky = requested_ky_;
    req_weekly_ = req_prefix_ + QStringLiteral("wk_") + (ky.isEmpty() ? QStringLiteral("latest") : ky);
    if (!weekly_loaded_) {
        if (view_ == QLatin1String("weekly"))
            show_loading(tr("Đang nạp bản tuần HHP…"));
    } else {
        set_status(fresh_lbl_, tr("đang nạp bản tuần…"), hhp::c_muted());
        if (fetch_btn_)
            fetch_btn_->setEnabled(false);
    }
    QStringList args;
    if (!ky.isEmpty())
        args << ky;
    services::EconomicsService::instance().execute(QString(kSourceId), QString(kWeeklyScript), QStringLiteral("weekly"),
                                                   args, req_weekly_, /*force=*/true);
}

void HhpValuationPanel::fetch_brief() {
    services::EconomicsService::instance().execute(QString(kSourceId), QString(kWeeklyScript), QStringLiteral("brief"),
                                                   {}, req_brief_, /*force=*/true);
}

void HhpValuationPanel::apply_weekly(const QJsonObject& data) {
    const QString prev_ky = weekly_data_.value("meta").toObject().value("ky").toString();
    const QString ky = data.value("meta").toObject().value("ky").toString();
    const int keep_scroll = (weekly_loaded_ && ky == prev_ky) ? weekly_scroll_->verticalScrollBar()->value() : 0;

    weekly_data_ = data;
    weekly_loaded_ = true;
    weekly_page_->set_payload(weekly_data_);
    populate_issue_combo();
    render_weekly_fresh();
    if (view_ == QLatin1String("weekly"))
        show_content_page(weekly_page_idx_);
    // The rebuilt page gets its geometry on the next layout pass — restore the position after it.
    QTimer::singleShot(0, this, [this, keep_scroll]() {
        if (weekly_scroll_)
            weekly_scroll_->verticalScrollBar()->setValue(keep_scroll);
    });
    LOG_INFO("HhpValuationPanel", QString("Bản tuần HHP kỳ %1 nạp xong").arg(ky));
}

void HhpValuationPanel::populate_issue_combo() {
    if (!issue_combo_)
        return;
    const QJsonObject meta = weekly_data_.value("meta").toObject();
    const QString shown = meta.value("ky").toString();
    const QSignalBlocker block(issue_combo_);
    issue_combo_->clear();
    int sel = -1;
    int i = 0;
    for (const QJsonValue& v : meta.value("issues").toArray()) {
        const QString ky = v.toString();
        const QDate d = QDate::fromString(ky, Qt::ISODate);
        if (!d.isValid())
            continue;
        QString label = d.toString(QStringLiteral("dd/MM/yyyy"));
        if (i == 0)
            label += tr(" · mới nhất");
        issue_combo_->addItem(label, ky);
        if (ky == shown)
            sel = i;
        ++i;
    }
    if (sel >= 0)
        issue_combo_->setCurrentIndex(sel);
}

void HhpValuationPanel::on_issue_selected(int index) {
    if (!issue_combo_ || index < 0)
        return;
    const QString ky = issue_combo_->itemData(index).toString();
    // The newest issue is requested as "" so the view follows the next issue when it lands.
    const QString next = index == 0 ? QString() : ky;
    if (next == requested_ky_ && weekly_loaded_ && !weekly_fetching_)
        return;
    requested_ky_ = next;
    fetch_weekly();
}

void HhpValuationPanel::render_weekly_fresh() {
    if (view_ != QLatin1String("weekly"))
        return;
    if (!weekly_loaded_) {
        set_status(fresh_lbl_, QString(), hhp::c_muted());
        return;
    }
    const QJsonObject meta = weekly_data_.value("meta").toObject();
    const QDate ky = QDate::fromString(meta.value("ky").toString(), Qt::ISODate);
    const QDate next_due = QDate::fromString(meta.value("next_due").toString(), Qt::ISODate);
    const QDate today = QDate::currentDate();
    const QString tip = tr("Tệp: %1\nLive: %2")
                            .arg(meta.value("issue_file").toString(), meta.value("live_as_of_txt").toString());
    if (!ky.isValid()) {
        set_status(fresh_lbl_, tr("bản tuần —"), hhp::c_muted(), tip);
        return;
    }
    const qint64 age = ky.daysTo(today);
    // The kỳ itself is shown in the combo right beside this label. Same rule as hhp_weekly.py: stale once the next issue is 2 days overdue.
    if (next_due.isValid() && next_due.addDays(2) <= today)
        set_status(fresh_lbl_, tr("⚠ cũ %1 ngày").arg(age), hhp::c_rich(), tip);
    else
        set_status(fresh_lbl_, tr("%1 ngày trước").arg(age), hhp::c_muted(), tip);
}

void HhpValuationPanel::apply_brief(const QJsonObject& data) {
    brief_ = data;
    const QString ky = data.value("ky").toString();
    if (ky.isEmpty()) {
        weekly_banner_->hide();
        table_->set_marks({}, {}, {}, {});
        return;
    }
    const QDate d = QDate::fromString(ky, Qt::ISODate);
    const QString source = tr("bản tuần %1").arg(d.isValid() ? d.toString(QStringLiteral("dd/MM")) : ky);

    QSet<QString> mine, avoid;
    for (const QJsonValue& v : data.value("mine").toArray())
        mine.insert(v.toString());
    for (const QJsonValue& v : data.value("avoid").toArray())
        avoid.insert(v.toString());
    QHash<QString, QString> notes;
    for (const QJsonValue& v : data.value("advisors").toArray()) {
        const QJsonObject a = v.toObject();
        const QString tk = a.value("ticker").toString();
        if (!tk.isEmpty())
            notes.insert(tk, tr("Hội đồng cố vấn: %1").arg(a.value("verdict").toString()));
    }
    table_->set_marks(mine, avoid, notes, source);

    QString title = data.value("title").toString().simplified();
    const QString rev = data.value("rev").toString();
    const double age = hhp::num(data.value("age_days"));
    QString head = tr("📰  BẢN TUẦN kỳ %1").arg(data.value("ky_txt").toString());
    if (!rev.isEmpty())
        head += QStringLiteral(" · ") + rev;
    QString html = QStringLiteral("<a href=\"weekly\" style=\"color:%1; text-decoration:none; font-weight:bold;\">%2"
                                  "&nbsp;&nbsp;→&nbsp;xem bản tuần + kiểm so với live</a>")
                       .arg(hhp::css(hhp::c_gold()), esc(head));
    QString rest;
    if (!title.isEmpty())
        rest += title;
    if (hhp::has(age))
        rest += (rest.isEmpty() ? QString() : QStringLiteral(" · ")) + tr("%1 ngày trước").arg(qRound(age));
    if (!rest.isEmpty())
        html += QStringLiteral("<br>") + esc(rest);
    if (data.value("stale").toBool())
        html += QStringLiteral(" · ") + span(esc(QStringLiteral("⚠ ") + data.value("stale_text").toString()),
                                             hhp::c_rich());
    weekly_banner_->setText(html);
    weekly_banner_->setToolTip(tr("◆ danh mục %1 mã · ⊘ tránh %2 mã được đánh dấu trong bộ lọc bên dưới")
                                   .arg(mine.size())
                                   .arg(avoid.size()));
    weekly_banner_->show();
}

void HhpValuationPanel::export_weekly_csv() {
    if (!weekly_loaded_ || !weekly_page_)
        return;
    const QStringList header = weekly_page_->csv_header();
    const QVector<QStringList> rows = weekly_page_->csv_rows();
    if (header.isEmpty() || rows.isEmpty())
        return;
    const QString ky = weekly_data_.value("meta").toObject().value("ky").toString();
    const QString suggested = QDir::homePath() + QStringLiteral("/Downloads/hhp_ban_tuan_%1_%2.csv")
                                                     .arg(ky, QDate::currentDate().toString("yyyyMMdd"));
    const QString path = QFileDialog::getSaveFileName(this, tr("Xuất CSV"), suggested, tr("CSV (*.csv)"));
    if (path.isEmpty())
        return;
    QFile file(path);
    if (!file.open(QIODevice::WriteOnly | QIODevice::Truncate)) {
        LOG_WARN("HhpValuationPanel", "Không ghi được CSV " + path + ": " + file.errorString());
        QMessageBox::warning(this, tr("Xuất CSV"), tr("Không ghi được tệp:\n%1\n%2").arg(path, file.errorString()));
        return;
    }
    file.write("\xEF\xBB\xBF");
    QTextStream out(&file);
    out.setEncoding(QStringConverter::Utf8);
    const auto line = [](const QStringList& cells) {
        QStringList quoted;
        quoted.reserve(cells.size());
        for (const QString& c : cells)
            quoted << csv_quote(c);
        return quoted.join(QLatin1Char(','));
    };
    out << line(header) << "\n";
    for (const QStringList& r : rows)
        out << line(r) << "\n";
    out.flush();
    LOG_INFO("HhpValuationPanel", QString("Xuất %1 dòng bộ lọc bản tuần → %2").arg(rows.size()).arg(path));
}

} // namespace fincept::screens
