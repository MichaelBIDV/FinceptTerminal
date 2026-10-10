// src/screens/beri/BeriPanel.cpp
// BERI — fetch lifecycle, toolbar and the one scrollable content page (section map in the header).
// Everything arrives pre-computed from scripts/beri.py (`overview`); the section builders
// (BeriSectionsLive.cpp / BeriSectionsCharter.cpp) lay it out and show "[CẦN DATA]" for any gap, so this
// file only hands each builder its payload slice. All data strings are HTML-escaped by the builders.
#include "screens/beri/BeriPanel.h"

#include "core/logging/Logger.h"
#include "screens/beri/BeriCommon.h"
#include "screens/beri/BeriSections.h"
#include "services/economics/EconomicsService.h"

#include <QDate>
#include <QDir>
#include <QFile>
#include <QFileDialog>
#include <QFrame>
#include <QHBoxLayout>
#include <QJsonArray>
#include <QLabel>
#include <QMessageBox>
#include <QPointer>
#include <QPushButton>
#include <QScrollArea>
#include <QScrollBar>
#include <QStringList>
#include <QTextStream>
#include <QTimer>
#include <QVBoxLayout>

#include <algorithm>

namespace fincept::screens {

namespace {

using beri::Role;

constexpr QLatin1StringView kSourceId{"beri"};
constexpr QLatin1StringView kScript{"beri.py"};
constexpr int kRefreshAfterSec = 30 * 60;      ///< re-fetch on show / tick once the last load is this old
constexpr int kRefreshTickMs = 15 * 60 * 1000; ///< how often the data age is re-evaluated

void set_status(QLabel* label, const QString& text, const QColor& color, const QString& tooltip = {}) {
    if (!label)
        return;
    label->setText(text);
    label->setToolTip(tooltip);
    label->setStyleSheet(
        QStringLiteral("QLabel { color:%1; font-size:10px; background:transparent; }").arg(beri::css(color)));
    // The toolbar layout squeezes labels to their first letter; reserve the width of the text.
    label->ensurePolished();
    label->setMinimumWidth(label->fontMetrics().horizontalAdvance(text) + 6);
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
    if (!v.isString())
        return {};
    // A text cell starting with = + - @ is a formula to a spreadsheet (and the CSV-injection vector).
    QString s = v.toString();
    if (!s.isEmpty() && QStringLiteral("=+-@\t\r").contains(s.at(0)))
        s.prepend(QLatin1Char('\''));
    return s;
}

} // namespace

// ── Construction ─────────────────────────────────────────────────────────────

BeriPanel::BeriPanel(QWidget* parent) : EconPanelBase(QString(kSourceId), beri::css(beri::teal()), parent) {
    static int s_instances = 0;
    req_prefix_ = QStringLiteral("beri_%1_").arg(++s_instances);

    build_base_ui(this);
    set_stats_visible(false);

    scroll_ = new QScrollArea(this);
    scroll_->setWidgetResizable(true);
    scroll_->setFrameShape(QFrame::NoFrame);
    scroll_->setHorizontalScrollBarPolicy(Qt::ScrollBarAlwaysOff);
    scroll_->setVerticalScrollBarPolicy(Qt::ScrollBarAsNeeded);
    scroll_->setWidget(new QWidget); // placeholder until the first payload
    page_idx_ = add_content_page(scroll_);

    // The base CSV button exports the generic results table, which this panel never fills —
    // point it at the payload's own export rows (lịch · sổ lệch · sổ nguồn).
    disconnect(export_btn_, &QPushButton::clicked, this, &BeriPanel::export_csv);
    connect(export_btn_, &QPushButton::clicked, this, &BeriPanel::export_payload_csv);
    export_btn_->setToolTip(tr("Xuất lịch · sổ lệch · sổ nguồn ra CSV"));
    export_btn_->setEnabled(false);

    connect(&services::EconomicsService::instance(), &services::EconomicsService::result_ready, this,
            &BeriPanel::on_result);

    // Countdowns change at midnight and the tab can stay open for days: re-check on a timer.
    refresh_timer_ = new QTimer(this);
    refresh_timer_->setInterval(kRefreshTickMs);
    connect(refresh_timer_, &QTimer::timeout, this, &BeriPanel::on_refresh_tick);
    refresh_timer_->start();

    show_empty(tr("Mở tab để nạp bàn điều hành BERI…"));
}

void BeriPanel::build_controls(QHBoxLayout* thl) {
    fresh_lbl_ = new QLabel;
    fresh_lbl_->setTextFormat(Qt::PlainText);
    thl->addWidget(fresh_lbl_);
}

// ── Fetch / results ──────────────────────────────────────────────────────────

void BeriPanel::activate() {
    if (fetching_)
        return;
    if (refresh_due())
        on_fetch();
    else
        render_fresh();
}

bool BeriPanel::refresh_due() const {
    if (!loaded_ || !fetched_at_.isValid())
        return true;
    // A new day moves every countdown, whatever the age of the last load.
    if (fetched_at_.toLocalTime().date() != QDate::currentDate())
        return true;
    return fetched_at_.secsTo(QDateTime::currentDateTimeUtc()) >= kRefreshAfterSec;
}

void BeriPanel::on_refresh_tick() {
    if (!loaded_ || fetching_)
        return;
    if (isVisible())
        activate();
    else
        render_fresh();
}

void BeriPanel::on_fetch() {
    fetching_ = true;
    req_current_ = req_prefix_ + QStringLiteral("overview_") +
                   QString::number(QDateTime::currentMSecsSinceEpoch());
    if (!loaded_) {
        show_loading(tr("Đang nạp BERI — beri-workspace · 8 tệp lõi · sổ nguồn · pipeline…"));
    } else {
        set_status(fresh_lbl_, tr("đang làm mới…"), beri::col(Role::Muted));
        if (fetch_btn_)
            fetch_btn_->setEnabled(false);
    }
    services::EconomicsService::instance().execute(QString(kSourceId), QString(kScript), QStringLiteral("overview"),
                                                   {}, req_current_, /*force=*/true);
}

void BeriPanel::on_result(const QString& request_id, const services::EconomicsResult& result) {
    if (result.source_id != kSourceId || !request_id.startsWith(req_prefix_) || request_id != req_current_)
        return;
    fetching_ = false;
    if (fetch_btn_)
        fetch_btn_->setEnabled(true);

    QString err = result.success ? result.data.value("error").toString() : result.error;
    if (result.success && err.isEmpty()) {
        fetched_at_ = QDateTime::currentDateTimeUtc();
        apply_overview(result.data);
        return;
    }
    if (err.isEmpty())
        err = tr("không rõ nguyên nhân");
    LOG_WARN("BeriPanel", "Nạp BERI lỗi: " + err);
    if (loaded_) {
        set_status(fresh_lbl_, tr("⚠ làm mới lỗi"), beri::crit(), err);
    } else {
        show_error(err.contains(QLatin1String("python3")) ? err
                                                          : err + tr("\nChạy thử: python3 scripts/beri.py overview"));
    }
}

void BeriPanel::apply_overview(const QJsonObject& data) {
    const bool same_day = loaded_ && data_.value("meta").toObject().value("today") ==
                                         data.value("meta").toObject().value("today");
    data_ = data;
    loaded_ = true;

    render_fresh();
    const QJsonObject csv = data_.value("csv").toObject();
    export_btn_->setEnabled(!csv.value("columns").toArray().isEmpty() && !csv.value("rows").toArray().isEmpty());

    rebuild_page(/*keep_scroll=*/same_day); // a periodic refresh keeps the reader's place
    show_content_page(page_idx_);

    const QJsonObject meta = data_.value("meta").toObject();
    LOG_INFO("BeriPanel", QString("BERI: hôm nay %1 · %2 cảnh báo")
                              .arg(meta.value("today").toString(QStringLiteral("—")))
                              .arg(meta.value("warnings").toArray().size()));
}

// ── Toolbar ──────────────────────────────────────────────────────────────────

void BeriPanel::render_fresh() {
    if (!fresh_lbl_)
        return;
    if (!loaded_) {
        set_status(fresh_lbl_, QString(), beri::col(Role::Muted));
        return;
    }
    const QJsonObject meta = data_.value("meta").toObject();
    QString txt;
    QDateTime at = QDateTime::fromString(meta.value("generated").toString(), Qt::ISODate);
    if (!at.isValid())
        at = fetched_at_;
    if (at.isValid())
        txt = tr("đọc tệp %1").arg(at.toLocalTime().toString(QStringLiteral("dd/MM HH:mm")));

    const QJsonObject dem = data_.value("lich").toObject().value("dem").toObject();
    const int crit = dem.value("crit").toInt();
    const int warns = meta.value("warnings").toArray().size();
    if (crit > 0 || warns > 0) {
        QStringList flags;
        if (crit > 0)
            flags << tr("%1 mốc ≤ 7 ngày").arg(crit);
        if (warns > 0)
            flags << tr("%1 cảnh báo nguồn").arg(warns);
        set_status(fresh_lbl_, txt + QStringLiteral(" · ⚠ ") + flags.join(QStringLiteral(" · ")), beri::crit());
    } else {
        set_status(fresh_lbl_, txt, beri::col(Role::Muted));
    }
}

// ── Theme / language ─────────────────────────────────────────────────────────

void BeriPanel::refresh_panel_theme() {
    EconPanelBase::refresh_panel_theme();
    // Also runs from build_base_ui() inside the constructor, before the page exists — hence the guards.
    if (scroll_)
        scroll_->setStyleSheet(
            QStringLiteral("QScrollArea { background:%1; border:none; }").arg(beri::css(beri::col(Role::Bg))));
    render_fresh();
    if (loaded_)
        rebuild_page(/*keep_scroll=*/true); // builders read theme colours at call time
}

void BeriPanel::retranslateUi() {
    if (export_btn_)
        export_btn_->setToolTip(tr("Xuất lịch · sổ lệch · sổ nguồn ra CSV"));
    if (!fetching_)
        render_fresh();
    EconPanelBase::retranslateUi();
}

// ── Content page ─────────────────────────────────────────────────────────────

void BeriPanel::rebuild_page(bool keep_scroll) {
    if (!scroll_)
        return;
    const int pos = keep_scroll ? scroll_->verticalScrollBar()->value() : 0;
    QWidget* old = scroll_->takeWidget();
    scroll_->setWidget(build_page());
    if (old)
        old->deleteLater();
    if (pos > 0) {
        // The new page's height is only known after its layout runs; restore once the loop turns.
        QPointer<QScrollArea> sa = scroll_;
        QTimer::singleShot(0, this, [sa, pos]() {
            if (sa)
                sa->verticalScrollBar()->setValue(pos);
        });
    } else {
        scroll_->verticalScrollBar()->setValue(0);
    }
}

QWidget* BeriPanel::build_page() {
    const QJsonObject meta = data_.value("meta").toObject();
    const auto obj = [this](const char* key) { return data_.value(QLatin1String(key)).toObject(); };

    auto* page = new QWidget;
    page->setObjectName("beriContent");
    page->setAttribute(Qt::WA_StyledBackground, true);
    page->setStyleSheet(
        QStringLiteral("QWidget#beriContent { background:%1; }").arg(beri::css(beri::col(Role::Bg))));
    auto* vl = new QVBoxLayout(page);
    vl->setContentsMargins(18, 14, 18, 24);
    vl->setSpacing(10);

    vl->addWidget(beri::build_masthead(obj("mandate"), meta, page));
    vl->addWidget(beri::build_alert(obj("alert"), page));
    vl->addWidget(beri::build_calendar(obj("lich"), page));
    vl->addWidget(beri::build_ledgers(obj("so_lech"), page));
    vl->addWidget(beri::build_commitments(obj("cam_ket"), obj("moc_neo"), page));
    vl->addWidget(beri::build_open_work(obj("viec_mo"), page));
    vl->addWidget(beri::build_registry(obj("so_nguon"), page));
    vl->addWidget(beri::build_store(obj("kho"), obj("pipeline"), page));
    vl->addWidget(beri::build_charter(obj("hien_chuong"), page));
    vl->addWidget(beri::build_experts(obj("tang_e"), page));
    vl->addWidget(beri::build_operating_seats(obj("bo_may"), page));
    vl->addWidget(beri::build_process(obj("quy_trinh"), obj("ket_luan"), page));
    vl->addWidget(beri::build_value_lines(obj("gia_tri"), page));
    vl->addWidget(beri::build_footer(meta, page));
    vl->addStretch(1);
    return page;
}

// ── Actions ──────────────────────────────────────────────────────────────────

void BeriPanel::export_payload_csv() {
    if (!loaded_)
        return;
    const QJsonObject csv = data_.value("csv").toObject();
    const QJsonArray columns = csv.value("columns").toArray();
    const QJsonArray rows = csv.value("rows").toArray();
    if (columns.isEmpty() || rows.isEmpty())
        return;

    const QString suggested = QDir::homePath() + QStringLiteral("/Downloads/beri_%1.csv")
                                                     .arg(QDate::currentDate().toString("yyyyMMdd"));
    const QString path = QFileDialog::getSaveFileName(this, tr("Xuất CSV"), suggested, tr("CSV (*.csv)"));
    if (path.isEmpty())
        return;

    QFile file(path);
    if (!file.open(QIODevice::WriteOnly | QIODevice::Truncate)) {
        LOG_WARN("BeriPanel", "Không ghi được CSV " + path + ": " + file.errorString());
        QMessageBox::warning(this, tr("Xuất CSV"), tr("Không ghi được tệp:\n%1\n%2").arg(path, file.errorString()));
        return;
    }
    file.write("\xEF\xBB\xBF"); // UTF-8 BOM so Excel reads the Vietnamese labels correctly
    QTextStream out(&file);
    out.setEncoding(QStringConverter::Utf8);

    const auto write_row = [&out](const QJsonArray& cells, qsizetype width) {
        QStringList quoted;
        quoted.reserve(width);
        for (qsizetype i = 0; i < width; ++i)
            quoted << csv_quote(i < cells.size() ? csv_cell(cells.at(i)) : QString());
        out << quoted.join(QLatin1Char(',')) << "\n";
    };
    const qsizetype width = columns.size();
    write_row(columns, width);
    for (const QJsonValue& rv : rows)
        write_row(rv.toArray(), std::max(width, rv.toArray().size()));
    out.flush();
    LOG_INFO("BeriPanel", QString("Xuất %1 dòng BERI → %2").arg(rows.size()).arg(path));
}

} // namespace fincept::screens
