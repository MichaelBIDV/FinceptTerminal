// src/screens/bbg_research/BbgResearchPanel.cpp
// BBG RESEARCH — fetch lifecycle, batch selector, toolbar and the one scrollable content page (section
// map in the header). scripts/bbg_research.py (`overview [--ngay D]`) shapes the whole page as a
// vnblocks/1 "trang" with every number pre-formatted and tiered; vnblocks::build_page() lays it out.
// This file only adds the meta line above it. All data strings are HTML-escaped before they reach a
// rich-text QLabel. Private helpers carry an "br_" prefix (unity-build safety).
#include "screens/bbg_research/BbgResearchPanel.h"

#include "core/logging/Logger.h"
#include "screens/sgi_fa/SgiCommon.h"
#include "screens/vnblocks/VnBlocks.h"
#include "services/economics/EconomicsService.h"

#include <QComboBox>
#include <QDate>
#include <QDesktopServices>
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
#include <QSignalBlocker>
#include <QStringList>
#include <QTextStream>
#include <QTimer>
#include <QUrl>
#include <QVBoxLayout>

#include <algorithm>

namespace fincept::screens {

namespace {

using sgi::Role;

constexpr QLatin1StringView kBrSourceId{"bbg"};
constexpr QLatin1StringView kBrScript{"bbg_research.py"};
constexpr int kBrRefreshAfterSec = 30 * 60;      ///< the pipeline writes once a day; 30' is plenty
constexpr int kBrRefreshTickMs = 15 * 60 * 1000;

QString br_fmt_date(const QString& iso) {
    const QDate d = QDate::fromString(iso.left(10), Qt::ISODate);
    return d.isValid() ? d.toString(QStringLiteral("dd/MM/yyyy")) : iso;
}

/// meta.index_url — only ever hand an http(s) URL to the OS.
QUrl br_index_url(const QJsonObject& payload) {
    const QUrl url(payload.value("meta").toObject().value("index_url").toString().trimmed());
    if (!url.isValid() || (url.scheme() != QLatin1String("http") && url.scheme() != QLatin1String("https")))
        return {};
    return url;
}

void br_set_status(QLabel* label, const QString& text, const QColor& color, const QString& tooltip = {}) {
    if (!label)
        return;
    label->setText(text);
    QString tip = sgi::esc(tooltip);
    tip.replace(QLatin1Char('\n'), QStringLiteral("<br>"));
    label->setToolTip(tooltip.isEmpty() ? QString() : QStringLiteral("<p>%1</p>").arg(tip));
    label->setStyleSheet(
        QStringLiteral("QLabel { color:%1; font-size:10px; background:transparent; }").arg(sgi::css(color)));
    label->ensurePolished();
    label->setMinimumWidth(label->fontMetrics().horizontalAdvance(text) + 6);
}

QString br_csv_quote(QString v) {
    if (v.contains(QLatin1Char(',')) || v.contains(QLatin1Char('"')) || v.contains(QLatin1Char('\n')) ||
        v.contains(QLatin1Char('\r')))
        v = QStringLiteral("\"") + v.replace(QStringLiteral("\""), QStringLiteral("\"\"")) + QStringLiteral("\"");
    return v;
}

QString br_csv_cell(const QJsonValue& v) {
    if (v.isDouble())
        return QString::number(v.toDouble(), 'g', 15);
    if (v.isBool())
        return v.toBool() ? QStringLiteral("true") : QStringLiteral("false");
    if (v.isString()) {
        QString s = v.toString();
        if (!s.isEmpty() && QStringLiteral("=+-@\t\r").contains(s.at(0)))
            s.prepend(QLatin1Char('\'')); // CSV-injection guard
        return s;
    }
    return {};
}

QStringList br_warnings(const QJsonObject& meta) {
    QStringList out;
    for (const QJsonValue& w : meta.value("warnings").toArray()) {
        const QString s = w.toString().trimmed();
        if (!s.isEmpty())
            out << s;
    }
    return out;
}

} // namespace

// ── Construction ─────────────────────────────────────────────────────────────

BbgResearchPanel::BbgResearchPanel(QWidget* parent)
    : EconPanelBase(QString(kBrSourceId), sgi::css(sgi::col(Role::Amber)), parent) {
    static int s_instances = 0;
    req_prefix_ = QStringLiteral("bbg_%1_").arg(++s_instances);

    build_base_ui(this);
    set_stats_visible(false);

    scroll_ = new QScrollArea(this);
    scroll_->setWidgetResizable(true);
    scroll_->setFrameShape(QFrame::NoFrame);
    scroll_->setHorizontalScrollBarPolicy(Qt::ScrollBarAsNeeded);
    scroll_->setVerticalScrollBarPolicy(Qt::ScrollBarAsNeeded);
    scroll_->setWidget(new QWidget);
    page_idx_ = add_content_page(scroll_);
    restyle_toolbar();

    disconnect(export_btn_, &QPushButton::clicked, this, &BbgResearchPanel::export_csv);
    connect(export_btn_, &QPushButton::clicked, this, &BbgResearchPanel::export_payload_csv);
    export_btn_->setToolTip(tr("Xuất chuỗi khuyến nghị quốc tế (cắt tại lô đang xem) ra CSV"));
    export_btn_->setEnabled(false);

    connect(&services::EconomicsService::instance(), &services::EconomicsService::result_ready, this,
            &BbgResearchPanel::on_result);

    refresh_timer_ = new QTimer(this);
    refresh_timer_->setInterval(kBrRefreshTickMs);
    connect(refresh_timer_, &QTimer::timeout, this, &BbgResearchPanel::on_refresh_tick);
    refresh_timer_->start();

    show_empty(tr("Mở tab để nạp Bloomberg Research theo ngày…"));
}

void BbgResearchPanel::build_controls(QHBoxLayout* thl) {
    auto* lbl = new QLabel(tr("LÔ"));
    lbl->setStyleSheet(QStringLiteral("QLabel { color:%1; font-size:10px; font-weight:bold; background:transparent; }")
                           .arg(sgi::css(sgi::col(Role::Muted))));
    thl->addWidget(lbl);

    batch_combo_ = new QComboBox;
    batch_combo_->setFixedHeight(26);
    batch_combo_->setMinimumWidth(150);
    batch_combo_->setToolTip(tr("Chọn lô Bloomberg theo ngày lên Drive — chuỗi được cắt tại ngày đó. HĐ = có bản Hội đồng."));
    batch_combo_->setEnabled(false);
    connect(batch_combo_, &QComboBox::activated, this, &BbgResearchPanel::on_batch_chosen);
    thl->addWidget(batch_combo_);

    fresh_lbl_ = new QLabel;
    fresh_lbl_->setTextFormat(Qt::PlainText);
    thl->addWidget(fresh_lbl_);

    web_btn_ = new QPushButton(tr("🌐 TRANG CHUỖI"));
    web_btn_->setFixedHeight(26);
    web_btn_->setCursor(Qt::PointingHandCursor);
    web_btn_->setToolTip(tr("Mở trang chuỗi Bloomberg Research (hub localhost:9000) trong trình duyệt"));
    web_btn_->setEnabled(false);
    connect(web_btn_, &QPushButton::clicked, this, &BbgResearchPanel::open_index_page);
    thl->addWidget(web_btn_);
}

// ── Fetch / results ──────────────────────────────────────────────────────────

void BbgResearchPanel::activate() {
    if (fetching_)
        return;
    if (refresh_due())
        on_fetch();
    else
        render_fresh();
}

bool BbgResearchPanel::refresh_due() const {
    return !loaded_ || !fetched_at_.isValid() ||
           fetched_at_.secsTo(QDateTime::currentDateTimeUtc()) >= kBrRefreshAfterSec;
}

void BbgResearchPanel::on_refresh_tick() {
    if (!loaded_ || fetching_)
        return;
    if (isVisible())
        activate();
    else
        render_fresh();
}

void BbgResearchPanel::on_batch_chosen(int index) {
    if (!batch_combo_ || index < 0)
        return;
    const QString d = batch_combo_->itemData(index).toString();
    // The newest entry means "follow the newest batch", so a later refresh picks up new batches.
    batch_ = index == 0 ? QString() : d;
    on_fetch();
}

void BbgResearchPanel::on_fetch() {
    fetching_ = true;
    req_current_ = req_prefix_ + QStringLiteral("overview_%1").arg(++req_seq_);
    if (!loaded_) {
        show_loading(tr("Đang nạp Bloomberg Research — lô · Hội đồng · chuỗi khuyến nghị…"));
    } else {
        br_set_status(fresh_lbl_, tr("đang nạp…"), sgi::col(Role::Muted));
        if (fetch_btn_)
            fetch_btn_->setEnabled(false);
        if (batch_combo_)
            batch_combo_->setEnabled(false);
    }
    QStringList args;
    if (!batch_.isEmpty())
        args << QStringLiteral("--ngay") << batch_;
    services::EconomicsService::instance().execute(QString(kBrSourceId), QString(kBrScript),
                                                   QStringLiteral("overview"), args, req_current_, /*force=*/true);
}

void BbgResearchPanel::on_result(const QString& request_id, const services::EconomicsResult& result) {
    if (result.source_id != kBrSourceId || !request_id.startsWith(req_prefix_) || request_id != req_current_)
        return;
    fetching_ = false;
    if (fetch_btn_)
        fetch_btn_->setEnabled(true);
    if (batch_combo_)
        batch_combo_->setEnabled(batch_combo_->count() > 0);

    QString err = result.success ? result.data.value("error").toString() : result.error;
    if (result.success && err.isEmpty()) {
        fetched_at_ = QDateTime::currentDateTimeUtc();
        apply_overview(result.data);
        return;
    }
    if (err.isEmpty())
        err = tr("không rõ nguyên nhân");
    LOG_WARN("BbgResearchPanel", "Nạp Bloomberg Research lỗi: " + err);

    if (loaded_) {
        br_set_status(fresh_lbl_, tr("⚠ nạp lỗi"), sgi::col(Role::Down), err);
        fill_batch_combo(); // put the selector back on the batch still on screen
    } else {
        show_error(err.contains(QLatin1String("python3")) ? err
                                                          : err + tr("\nChạy thử: python3 scripts/bbg_research.py overview"));
    }
}

void BbgResearchPanel::apply_overview(const QJsonObject& data) {
    const QString prev_batch = data_.value("meta").toObject().value("lo").toString();
    data_ = data;
    const QJsonObject meta = data_.value("meta").toObject();
    const bool same_batch = loaded_ && prev_batch == meta.value("lo").toString();
    loaded_ = true;

    fill_batch_combo();
    render_fresh();
    web_btn_->setEnabled(br_index_url(data_).isValid());
    const QJsonObject csv = data_.value("csv").toObject();
    export_btn_->setEnabled(!csv.value("columns").toArray().isEmpty() && !csv.value("rows").toArray().isEmpty());

    const QJsonArray sections = data_.value("trang").toObject().value("sections").toArray();
    if (sections.isEmpty()) {
        QString msg = tr("[CẦN DATA] Lô này không có mục nào để hiển thị.");
        const QStringList warns = br_warnings(meta);
        if (!warns.isEmpty())
            msg += QStringLiteral("\n⚠ ") + warns.join(QStringLiteral("\n⚠ "));
        show_empty(msg);
    } else {
        rebuild_page(/*keep_scroll=*/same_batch);
        show_content_page(page_idx_);
    }

    LOG_INFO("BbgResearchPanel", QString("Bloomberg Research: lô %1 · %2 mục · %3 cảnh báo")
                                     .arg(meta.value("lo").toString(QStringLiteral("—")))
                                     .arg(sections.size())
                                     .arg(meta.value("warnings").toArray().size()));
}

void BbgResearchPanel::fill_batch_combo() {
    if (!batch_combo_)
        return;
    const QJsonObject meta = data_.value("meta").toObject();
    const QString shown = meta.value("lo").toString();
    const QSignalBlocker block(batch_combo_);
    batch_combo_->clear();
    int sel = 0;
    for (const QJsonValue& v : meta.value("ky_list").toArray()) {
        const QJsonObject k = v.toObject();
        const QString d = k.value("ngay").toString();
        if (d.isEmpty())
            continue;
        batch_combo_->addItem(k.value("nhan").toString(d), d);
        if (d == shown)
            sel = batch_combo_->count() - 1;
    }
    batch_combo_->setCurrentIndex(batch_combo_->count() > 0 ? sel : -1);
    batch_combo_->setEnabled(batch_combo_->count() > 0 && !fetching_);
}

// ── Toolbar ──────────────────────────────────────────────────────────────────

void BbgResearchPanel::render_fresh() {
    if (!fresh_lbl_)
        return;
    if (!loaded_) {
        br_set_status(fresh_lbl_, QString(), sgi::col(Role::Muted));
        return;
    }
    const QJsonObject meta = data_.value("meta").toObject();
    const QString newest = meta.value("lo_moi_nhat").toString();
    QString txt = newest.isEmpty() ? tr("lô mới nhất [CẦN DATA]") : tr("Lô mới nhất %1").arg(br_fmt_date(newest));
    QDateTime at = QDateTime::fromString(meta.value("generated").toString(), Qt::ISODate);
    if (!at.isValid())
        at = fetched_at_;
    if (at.isValid())
        txt += tr(" · nạp %1").arg(at.toLocalTime().toString(QStringLiteral("HH:mm")));

    if (meta.value("stale").toBool()) {
        const QString stale = meta.value("stale_text").toString().trimmed();
        br_set_status(fresh_lbl_, txt + QStringLiteral(" · ⚠ ") + stale, sgi::col(Role::Down), stale);
    } else {
        br_set_status(fresh_lbl_, txt, sgi::col(Role::Muted));
    }
}

void BbgResearchPanel::restyle_toolbar() {
    if (web_btn_) {
        web_btn_->setStyleSheet(QStringLiteral("QPushButton { background:%1; color:%2; font-weight:bold;"
                                               " border-radius:4px; padding:0 8px; border:1px solid %3; }"
                                               "QPushButton:hover { background:%4; color:%5; }"
                                               "QPushButton:disabled { color:%6; }")
                                    .arg(sgi::css(sgi::col(Role::Surface2)), sgi::css(sgi::col(Role::Ink2)),
                                         sgi::css(sgi::col(Role::Line)), sgi::css(sgi::col(Role::Amber)),
                                         sgi::css(sgi::col(Role::Bg)), sgi::css(sgi::col(Role::Muted))));
    }
    if (batch_combo_) {
        batch_combo_->setStyleSheet(QStringLiteral("QComboBox { background:%1; color:%2; border:1px solid %3;"
                                                   " border-radius:4px; padding:0 6px; font-size:11px; }"
                                                   "QComboBox QAbstractItemView { background:%1; color:%2;"
                                                   " selection-background-color:%4; selection-color:%5; }")
                                        .arg(sgi::css(sgi::col(Role::Surface2)), sgi::css(sgi::col(Role::Ink)),
                                             sgi::css(sgi::col(Role::Line)), sgi::css(sgi::col(Role::Amber)),
                                             sgi::css(sgi::col(Role::Bg))));
    }
    if (scroll_)
        scroll_->setStyleSheet(
            QStringLiteral("QScrollArea { background:%1; border:none; }").arg(sgi::css(sgi::col(Role::Bg))));
    render_fresh();
}

// ── Theme / language ─────────────────────────────────────────────────────────

void BbgResearchPanel::refresh_panel_theme() {
    EconPanelBase::refresh_panel_theme();
    restyle_toolbar();
    if (loaded_)
        rebuild_page(/*keep_scroll=*/true);
}

void BbgResearchPanel::retranslateUi() {
    if (web_btn_) {
        web_btn_->setText(tr("🌐 TRANG CHUỖI"));
        web_btn_->setToolTip(tr("Mở trang chuỗi Bloomberg Research (hub localhost:9000) trong trình duyệt"));
    }
    if (export_btn_)
        export_btn_->setToolTip(tr("Xuất chuỗi khuyến nghị quốc tế (cắt tại lô đang xem) ra CSV"));
    if (!fetching_)
        render_fresh();
    EconPanelBase::retranslateUi();
}

// ── Content page ─────────────────────────────────────────────────────────────

void BbgResearchPanel::rebuild_page(bool keep_scroll) {
    if (!scroll_)
        return;
    const int pos = keep_scroll ? scroll_->verticalScrollBar()->value() : 0;
    QWidget* old = scroll_->takeWidget();
    scroll_->setWidget(build_page());
    if (old)
        old->deleteLater();
    if (pos > 0) {
        QPointer<QScrollArea> sa = scroll_;
        QTimer::singleShot(0, this, [sa, pos]() {
            if (sa)
                sa->verticalScrollBar()->setValue(pos);
        });
    } else {
        scroll_->verticalScrollBar()->setValue(0);
    }
}

QWidget* BbgResearchPanel::build_page() {
    const QJsonObject meta = data_.value("meta").toObject();

    auto* page = new QWidget;
    page->setObjectName("bbgContent");
    page->setAttribute(Qt::WA_StyledBackground, true);
    page->setStyleSheet(QStringLiteral("QWidget#bbgContent { background:%1; }").arg(sgi::css(sgi::col(Role::Bg))));
    auto* vl = new QVBoxLayout(page);
    vl->setContentsMargins(18, 14, 18, 24);
    vl->setSpacing(10);

    // Meta line: lô · tên lô · Hội đồng có/không · stale.
    {
        QStringList parts;
        const QString lo = meta.value("lo").toString();
        parts << sgi::esc(lo.isEmpty() ? tr("Lô [CẦN DATA]") : tr("Lô %1").arg(br_fmt_date(lo)));
        const QString ten = meta.value("ten_lo").toString();
        if (!ten.isEmpty())
            parts << sgi::esc(ten);
        parts << (meta.value("co_hoi_dong").toBool()
                      ? sgi::span(sgi::esc(tr("có bản Hội đồng")), sgi::col(Role::Amber), true)
                      : sgi::esc(tr("chưa có bản Hội đồng")));
        parts << sgi::esc(tr("kho SS-T3 · Hội đồng EST"));
        if (meta.value("stale").toBool())
            parts << sgi::span(sgi::esc(meta.value("stale_text").toString()), sgi::col(Role::Down), true);

        auto* meta_lbl = sgi::make_label(page, sgi::col(Role::Muted), 12, Qt::RichText);
        meta_lbl->setText(parts.join(QStringLiteral(" · ")));
        const QString file = meta.value("lo_file").toString();
        if (!file.isEmpty())
            meta_lbl->setToolTip(QStringLiteral("<p>%1</p>").arg(sgi::esc(file)));
        vl->addWidget(meta_lbl);
    }

    const QStringList warns = br_warnings(meta);
    if (!warns.isEmpty()) {
        QStringList lines;
        for (const QString& w : warns)
            lines << sgi::span(sgi::esc(QStringLiteral("⚠ ") + w), sgi::col(Role::Amber));
        auto* warn = sgi::make_label(page, sgi::col(Role::Ink2), 11, Qt::RichText);
        warn->setText(lines.join(QStringLiteral("<br>")));
        vl->addWidget(warn);
    }

    vl->addWidget(vnblocks::build_page(data_.value("trang").toObject(), page));
    vl->addStretch(1);
    return page;
}

// ── Actions ──────────────────────────────────────────────────────────────────

void BbgResearchPanel::export_payload_csv() {
    if (!loaded_)
        return;
    const QJsonObject csv = data_.value("csv").toObject();
    const QJsonArray columns = csv.value("columns").toArray();
    const QJsonArray rows = csv.value("rows").toArray();
    if (columns.isEmpty() || rows.isEmpty())
        return;

    QString lo = data_.value("meta").toObject().value("lo").toString();
    lo.remove(QLatin1Char('-'));
    const QString suggested = QDir::homePath() + QStringLiteral("/Downloads/bbg_khuyen_nghi_%1.csv")
                                                     .arg(lo.isEmpty() ? QStringLiteral("khong_ngay") : lo);
    const QString path = QFileDialog::getSaveFileName(this, tr("Xuất CSV"), suggested, tr("CSV (*.csv)"));
    if (path.isEmpty())
        return;

    QFile file(path);
    if (!file.open(QIODevice::WriteOnly | QIODevice::Truncate)) {
        LOG_WARN("BbgResearchPanel", "Không ghi được CSV " + path + ": " + file.errorString());
        QMessageBox::warning(this, tr("Xuất CSV"), tr("Không ghi được tệp:\n%1\n%2").arg(path, file.errorString()));
        return;
    }
    file.write("\xEF\xBB\xBF");
    QTextStream out(&file);
    out.setEncoding(QStringConverter::Utf8);

    const auto write_row = [&out](const QJsonArray& cells, qsizetype width) {
        QStringList quoted;
        quoted.reserve(width);
        for (qsizetype i = 0; i < width; ++i)
            quoted << br_csv_quote(i < cells.size() ? br_csv_cell(cells.at(i)) : QString());
        out << quoted.join(QLatin1Char(',')) << "\n";
    };
    const qsizetype width = columns.size();
    write_row(columns, width);
    for (const QJsonValue& rv : rows)
        write_row(rv.toArray(), std::max(width, rv.toArray().size()));
    out.flush();
    LOG_INFO("BbgResearchPanel", QString("Xuất %1 dòng khuyến nghị quốc tế → %2").arg(rows.size()).arg(path));
}

void BbgResearchPanel::open_index_page() {
    const QUrl url = br_index_url(data_);
    if (!url.isValid())
        return;
    if (!QDesktopServices::openUrl(url))
        LOG_WARN("BbgResearchPanel", "Không mở được trang chuỗi: " + url.toString());
}

} // namespace fincept::screens
