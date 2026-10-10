// src/screens/so_nguon/SoNguonPanel.cpp
// Sổ nguồn — fetch lifecycle, refresh-run polling, toolbar and the one scrollable content page (command
// map in the header). scripts/so_nguon_tab.py shapes every section and formats every number; this file
// only routes payloads, keeps the run section current while a refresh runs, and hands `trang` to
// vnblocks::build_page(). All data strings reaching a rich-text QLabel are HTML-escaped.
#include "screens/so_nguon/SoNguonPanel.h"

#include "core/logging/Logger.h"
#include "screens/sgi_fa/SgiCommon.h"
#include "screens/vnblocks/VnBlocks.h"
#include "services/economics/EconomicsService.h"

#include <QDate>
#include <QDir>
#include <QFile>
#include <QFileDialog>
#include <QFrame>
#include <QHBoxLayout>
#include <QHideEvent>
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

using sgi::Role;

constexpr QLatin1StringView kSourceId{"songuon"};
constexpr QLatin1StringView kScript{"so_nguon_tab.py"};
constexpr QLatin1StringView kRunSection{"lam_moi"}; ///< id of the page section a poll may replace
constexpr int kRefreshAfterSec = 30 * 60;      ///< re-audit on show / tick once the last load is this old
constexpr int kRefreshTickMs = 15 * 60 * 1000; ///< how often the data age is re-evaluated
constexpr int kPollMs = 3000;                  ///< run-status poll interval while a refresh runs
constexpr int kPollGiveUp = 3;                 ///< consecutive failed polls before polling stops
constexpr int kStepNameMax = 48;               ///< longer step names are elided in the toolbar label

void set_status(QLabel* label, const QString& text, const QColor& color, const QString& tooltip = {}) {
    if (!label)
        return;
    label->setText(text);
    // Tooltips auto-detect rich text: an error or path containing "<" would be parsed as markup. Force the
    // rich-text path with the text escaped.
    QString tip = sgi::esc(tooltip);
    tip.replace(QLatin1Char('\n'), QStringLiteral("<br>"));
    label->setToolTip(tooltip.isEmpty() ? QString() : QStringLiteral("<p>%1</p>").arg(tip));
    label->setStyleSheet(
        QStringLiteral("QLabel { color:%1; font-size:10px; background:transparent; }").arg(sgi::css(color)));
    // The toolbar layout squeezes a label to its first letter (SgiFaPanel, seen offscreen); reserve the
    // width of the text explicitly.
    label->ensurePolished();
    label->setMinimumWidth(label->fontMetrics().horizontalAdvance(text) + 6);
}

/// ISO timestamp → local time; invalid when absent or unparsable.
QDateTime parse_time(const QJsonValue& v) {
    QDateTime t = QDateTime::fromString(v.toString().trimmed(), Qt::ISODate);
    return t.isValid() ? t.toLocalTime() : QDateTime();
}

/// "14:05" today, "23/09 14:05" on another day.
QString fmt_clock(const QDateTime& t) {
    if (!t.isValid())
        return {};
    return t.date() == QDate::currentDate() ? t.toString(QStringLiteral("HH:mm"))
                                            : t.toString(QStringLiteral("dd/MM HH:mm"));
}

bool step_done(const QString& st) {
    return st == QLatin1String("xong") || st == QLatin1String("loi") || st == QLatin1String("bo_qua");
}

/// Change key of a run: its id, whether it runs, and each step's state. Elapsed seconds and other
/// per-poll noise are left out, so an unchanged key means the run section needs no rebuild.
QString run_key(const QJsonObject& run) {
    QStringList parts{run.value("run_id").toVariant().toString(),
                      run.value("dang_chay").toBool() ? QStringLiteral("1") : QStringLiteral("0")};
    for (const QJsonValue& v : run.value("buoc").toArray()) {
        const QJsonObject b = v.toObject();
        parts << b.value("id").toString() + QLatin1Char('=') + b.value("trang_thai").toString();
    }
    return parts.join(QLatin1Char('|'));
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
    if (v.isString()) {
        // A text cell starting with = + - @ is evaluated as a formula (and is the CSV-injection vector):
        // force it to text with a leading apostrophe.
        QString s = v.toString();
        if (!s.isEmpty() && QStringLiteral("=+-@\t\r").contains(s.at(0)))
            s.prepend(QLatin1Char('\''));
        return s;
    }
    return {};
}

} // namespace

// ── Construction ─────────────────────────────────────────────────────────────

SoNguonPanel::SoNguonPanel(QWidget* parent)
    : EconPanelBase(QString(kSourceId), sgi::css(sgi::col(Role::Amber)), parent) {
    static int s_instances = 0;
    req_prefix_ = QStringLiteral("sn_%1_").arg(++s_instances);
    req_poll_ = req_prefix_ + QStringLiteral("trang_thai");

    build_base_ui(this);
    set_stats_visible(false);

    scroll_ = new QScrollArea(this);
    scroll_->setWidgetResizable(true);
    scroll_->setFrameShape(QFrame::NoFrame);
    // Tables of 8–9 columns keep a minimum width (~880 px); below that scroll instead of clipping.
    scroll_->setHorizontalScrollBarPolicy(Qt::ScrollBarAsNeeded);
    scroll_->setVerticalScrollBarPolicy(Qt::ScrollBarAsNeeded);
    scroll_->setWidget(new QWidget); // placeholder until the first payload
    page_idx_ = add_content_page(scroll_);
    restyle_toolbar();

    // The base CSV button exports the generic results table, which this panel never fills — point it
    // at the payload's own export rows.
    disconnect(export_btn_, &QPushButton::clicked, this, &SoNguonPanel::export_csv);
    connect(export_btn_, &QPushButton::clicked, this, &SoNguonPanel::export_payload_csv);
    export_btn_->setEnabled(false);

    connect(&services::EconomicsService::instance(), &services::EconomicsService::result_ready, this,
            &SoNguonPanel::on_result);

    poll_timer_ = new QTimer(this);
    poll_timer_->setInterval(kPollMs);
    connect(poll_timer_, &QTimer::timeout, this, &SoNguonPanel::on_poll_tick);

    // The tab can stay open for days: re-check the audit age on a timer so the re-audit does not wait
    // for a manual AUDIT.
    refresh_timer_ = new QTimer(this);
    refresh_timer_->setInterval(kRefreshTickMs);
    connect(refresh_timer_, &QTimer::timeout, this, &SoNguonPanel::on_refresh_tick);
    refresh_timer_->start();

    retranslateUi(); // tooltips of the base buttons
    show_empty(tr("Mở tab để nạp Sổ nguồn…"));
    update_buttons();
}

void SoNguonPanel::build_controls(QHBoxLayout* thl) {
    status_lbl_ = new QLabel;
    status_lbl_->setTextFormat(Qt::PlainText);
    thl->addWidget(status_lbl_);

    thl->addSpacing(8);

    audit_btn_ = new QPushButton(tr("AUDIT"));
    audit_btn_->setFixedHeight(26);
    audit_btn_->setCursor(Qt::PointingHandCursor);
    connect(audit_btn_, &QPushButton::clicked, this, [this]() {
        if (!fetching_)
            request_page(PageCmd::Overview);
    });
    thl->addWidget(audit_btn_);
}

// ── Fetch / results ──────────────────────────────────────────────────────────

void SoNguonPanel::activate() {
    if (polling_) {
        // Back on screen while a run is followed: catch up at once, then every kPollMs.
        if (!poll_timer_->isActive())
            poll_timer_->start();
        on_poll_tick();
        return;
    }
    if (fetching_)
        return;
    if (refresh_due())
        request_page(PageCmd::Overview);
    else
        render_status();
}

bool SoNguonPanel::refresh_due() const {
    return !loaded_ || !fetched_at_.isValid() ||
           fetched_at_.secsTo(QDateTime::currentDateTimeUtc()) >= kRefreshAfterSec;
}

void SoNguonPanel::on_refresh_tick() {
    if (!loaded_ || fetching_ || polling_)
        return; // a followed run ends with its own overview
    if (isVisible())
        activate(); // re-audit when due, else re-evaluate the label
    else
        render_status();
}

void SoNguonPanel::on_fetch() {
    // One runner at a time (so_nguon also refuses a second one); FETCH is disabled meanwhile.
    if (fetching_ || run_active())
        return;
    request_page(PageCmd::LamMoi);
}

void SoNguonPanel::request_page(PageCmd cmd) {
    fetching_ = true;
    fetching_cmd_ = cmd;
    const QString command = cmd == PageCmd::LamMoi ? QStringLiteral("lam_moi") : QStringLiteral("overview");
    req_page_ = req_prefix_ + command;
    if (!loaded_)
        show_loading(cmd == PageCmd::LamMoi ? tr("Đang khởi động lượt làm mới các nguồn đến hạn…")
                                            : tr("Đang kiểm Sổ nguồn — độ tươi · vấn đề · lịch · nguồn gốc…"));
    // Otherwise keep the current page on screen while the request runs.
    render_status();
    update_buttons();
    // force: never replay a cached answer — lam_moi must reach the script to start the runner, and an
    // audit is only worth anything when it is fresh.
    services::EconomicsService::instance().execute(QString(kSourceId), QString(kScript), command, {}, req_page_,
                                                   /*force=*/true);
}

void SoNguonPanel::on_result(const QString& request_id, const services::EconomicsResult& result) {
    // result_ready reaches every connected panel — route strictly by source + this instance's prefix.
    if (result.source_id != kSourceId || !request_id.startsWith(req_prefix_))
        return;

    // EconomicsService already turns a top-level "error" into a failure; the check here is a guard.
    QString err = result.success ? result.data.value("error").toString() : result.error;
    const bool ok = result.success && err.isEmpty();
    if (err.isEmpty())
        err = tr("không rõ nguyên nhân");

    if (request_id == req_poll_) {
        if (!poll_in_flight_)
            return;
        poll_in_flight_ = false;
        if (!polling_)
            return; // the run was already seen finished (e.g. by a page payload) while this poll ran
        if (poll_for_run_ != run_.value("run_id").toVariant().toString())
            return; // sent while an earlier run was followed; a newer FETCH has started another since
        if (ok) {
            poll_failures_ = 0;
            apply_poll(result.data);
            return;
        }
        LOG_WARN("SoNguonPanel", "Theo dõi lượt làm mới lỗi: " + err);
        if (++poll_failures_ >= kPollGiveUp) {
            // Stop hammering a failing script; AUDIT (or the tab's next show) picks the run up again.
            stop_polling();
            poll_error_ = err;
            render_status();
            update_buttons();
        }
        return;
    }

    if (request_id != req_page_ || !fetching_)
        return; // superseded
    fetching_ = false;
    const bool was_lam_moi = fetching_cmd_ == PageCmd::LamMoi;
    if (ok) {
        fetched_at_ = QDateTime::currentDateTimeUtc();
        page_error_.clear();
        apply_page(result.data);
        return;
    }
    LOG_WARN("SoNguonPanel", QString(was_lam_moi ? "Làm mới lỗi: " : "Kiểm Sổ nguồn lỗi: ") + err);
    if (loaded_) {
        // Keep the page on screen; the short text sits in the fixed toolbar, the detail in the tooltip.
        page_error_ = (was_lam_moi ? tr("⚠ không khởi động được làm mới") : tr("⚠ kiểm lỗi")) +
                      QStringLiteral("\n") + err;
        render_status();
        update_buttons();
    } else {
        // Script errors already say what to do; add the run hint only for runner-level failures.
        show_error(err.contains(QLatin1String("python3"))
                       ? err
                       : err + tr("\nChạy thử: python3 scripts/so_nguon_tab.py overview"));
        update_buttons();
    }
}

void SoNguonPanel::apply_page(const QJsonObject& data) {
    const bool had_page = loaded_;
    data_ = data;
    loaded_ = true;
    poll_error_.clear();

    const QJsonObject csv = data_.value("csv").toObject();
    export_btn_->setEnabled(!csv.value("columns").toArray().isEmpty() && !csv.value("rows").toArray().isEmpty());

    set_run(data_.value("run").toObject());
    rebuild_page(/*keep_scroll=*/had_page); // a refresh keeps the reader's place
    show_content_page(page_idx_);
    render_status();
    update_buttons(); // after show_content_page, which re-enables FETCH

    const QJsonObject meta = data_.value("meta").toObject();
    LOG_INFO("SoNguonPanel", QString("Sổ nguồn: %1 cảnh báo · lượt làm mới %2")
                                 .arg(meta.value("warnings").toArray().size())
                                 .arg(run_active() ? QStringLiteral("đang chạy") : QStringLiteral("không chạy")));
}

void SoNguonPanel::apply_poll(const QJsonObject& data) {
    // `trang_thai` returns {"run": {...}, "section": {...}?}; accept a bare run object as well.
    const QJsonObject run = data.value("run").isObject() ? data.value("run").toObject() : data;
    const bool changed = run_key(run) != run_key_;

    // Merge the fresh run into the page payload: the run itself, and the ready-made run section when
    // the script sent one (it replaces the section with id "lam_moi"; nothing else is touched).
    bool section_replaced = false;
    const QJsonObject section = data.value("section").toObject();
    if (loaded_ && section.value("id").toString() == kRunSection) {
        QJsonObject trang = data_.value("trang").toObject();
        QJsonArray sections = trang.value("sections").toArray();
        for (qsizetype i = 0; i < sections.size(); ++i) {
            if (sections.at(i).toObject().value("id").toString() == kRunSection) {
                sections.replace(i, section);
                section_replaced = true;
                break;
            }
        }
        if (section_replaced) {
            trang.insert("sections", sections);
            data_.insert("trang", trang);
        }
    }
    if (loaded_)
        data_.insert("run", run);

    set_run(run);
    // Rebuild only on a state change of a step (not on every tick's elapsed seconds): the toolbar label
    // carries the live progress in between.
    if (changed && section_replaced)
        rebuild_page(/*keep_scroll=*/true);

    if (!run_active() && !fetching_)
        request_page(PageCmd::Overview); // run over: one full audit refreshes every section
    render_status();
    update_buttons();
}

void SoNguonPanel::set_run(const QJsonObject& run) {
    run_ = run;
    run_key_ = run_key(run);
    if (run_active())
        start_polling();
    else if (polling_)
        stop_polling();
}

bool SoNguonPanel::run_active() const {
    return run_.value("dang_chay").toBool();
}

// ── Polling ──────────────────────────────────────────────────────────────────

void SoNguonPanel::start_polling() {
    if (!polling_) {
        polling_ = true;
        poll_failures_ = 0;
        poll_error_.clear();
    }
    // The payload that started the run already carries its state: the first poll waits one interval.
    // Hidden → activate() restarts the timer on the next show.
    if (isVisible() && !poll_timer_->isActive())
        poll_timer_->start();
}

void SoNguonPanel::stop_polling() {
    polling_ = false;
    poll_timer_->stop();
    // A poll still in flight is left to arrive; on_result drops its answer since polling_ is off.
}

void SoNguonPanel::on_poll_tick() {
    if (!polling_ || poll_in_flight_)
        return;
    if (!isVisible()) {
        poll_timer_->stop();
        return;
    }
    poll_in_flight_ = true;
    poll_for_run_ = run_.value("run_id").toVariant().toString();
    services::EconomicsService::instance().execute(QString(kSourceId), QString(kScript), QStringLiteral("trang_thai"),
                                                   {}, req_poll_, /*force=*/true);
}

void SoNguonPanel::hideEvent(QHideEvent* event) {
    EconPanelBase::hideEvent(event);
    // No polling for a tab nobody looks at; polling_ stays set so activate() resumes it.
    if (poll_timer_)
        poll_timer_->stop();
}

// ── Toolbar ──────────────────────────────────────────────────────────────────

void SoNguonPanel::render_status() {
    if (!status_lbl_)
        return;
    const QColor muted = sgi::col(Role::Muted);

    if (fetching_ && loaded_) {
        set_status(status_lbl_,
                   fetching_cmd_ == PageCmd::LamMoi ? tr("đang khởi động làm mới…") : tr("đang kiểm…"), muted);
        return;
    }

    if (run_active()) {
        const QJsonArray steps = run_.value("buoc").toArray();
        int done = 0;
        QString current;
        for (const QJsonValue& v : steps) {
            const QJsonObject b = v.toObject();
            const QString st = b.value("trang_thai").toString();
            if (step_done(st))
                ++done;
            else if (st == QLatin1String("dang_chay") && current.isEmpty())
                current = b.value("ten").toString().trimmed().isEmpty() ? b.value("id").toString()
                                                                        : b.value("ten").toString().trimmed();
        }
        QString txt = tr("đang làm mới %1/%2 bước").arg(done).arg(steps.size());
        if (!current.isEmpty()) {
            if (current.size() > kStepNameMax)
                current = current.left(kStepNameMax - 1) + QStringLiteral("…");
            txt += QStringLiteral(" · ") + current;
        }
        QString tip = tr("Lượt %1").arg(run_.value("run_id").toVariant().toString());
        const QDateTime start = parse_time(run_.value("bat_dau"));
        if (start.isValid())
            tip += tr(" · bắt đầu %1").arg(fmt_clock(start));
        set_status(status_lbl_, txt, sgi::col(Role::Amber), tip);
        return;
    }

    if (!page_error_.isEmpty()) {
        const qsizetype nl = page_error_.indexOf(QLatin1Char('\n'));
        set_status(status_lbl_, page_error_.left(nl), sgi::col(Role::Down), page_error_.mid(nl + 1));
        return;
    }
    if (!poll_error_.isEmpty()) {
        set_status(status_lbl_, tr("⚠ mất theo dõi lượt làm mới — bấm AUDIT"), sgi::col(Role::Down), poll_error_);
        return;
    }
    if (!loaded_) {
        set_status(status_lbl_, QString(), muted);
        return;
    }

    const QJsonObject meta = data_.value("meta").toObject();
    QDateTime audited = parse_time(meta.value("generated"));
    if (!audited.isValid())
        audited = parse_time(meta.value("cap_nhat"));
    if (!audited.isValid() && fetched_at_.isValid())
        audited = fetched_at_.toLocalTime();
    const QString audit_tip = audited.isValid() ? tr("Kiểm lúc %1").arg(fmt_clock(audited)) : QString();

    const QDateTime finished = parse_time(run_.value("xong_luc"));
    if (!run_.value("run_id").toVariant().toString().isEmpty() && finished.isValid()) {
        int errors = 0;
        for (const QJsonValue& v : run_.value("buoc").toArray())
            if (v.toObject().value("trang_thai").toString() == QLatin1String("loi"))
                ++errors;
        set_status(status_lbl_, tr("làm mới xong %1 · %2 lỗi").arg(fmt_clock(finished)).arg(errors),
                   errors > 0 ? sgi::col(Role::Down) : muted, audit_tip);
        return;
    }
    set_status(status_lbl_, audited.isValid() ? tr("cập nhật %1").arg(fmt_clock(audited)) : QString(), muted);
}

void SoNguonPanel::update_buttons() {
    if (fetch_btn_) {
        fetch_btn_->setEnabled(!fetching_ && !run_active());
        fetch_btn_->setToolTip(run_active() ? tr("Đang có lượt làm mới — chờ xong")
                                            : tr("Làm mới mọi nguồn đến hạn của toàn app (bộ điều phối + producer "
                                                 "đến hạn), rồi theo dõi tiến độ từng bước"));
    }
    if (audit_btn_)
        audit_btn_->setEnabled(!fetching_);
}

void SoNguonPanel::restyle_toolbar() {
    if (audit_btn_) {
        audit_btn_->setStyleSheet(QStringLiteral("QPushButton { background:%1; color:%2; font-weight:bold;"
                                                 " border-radius:4px; padding:0 8px; border:1px solid %3; }"
                                                 "QPushButton:hover { background:%4; color:%5; }"
                                                 "QPushButton:disabled { color:%6; }")
                                      .arg(sgi::css(sgi::col(Role::Surface2)), sgi::css(sgi::col(Role::Ink2)),
                                           sgi::css(sgi::col(Role::Line)), sgi::css(sgi::col(Role::Amber)),
                                           sgi::css(sgi::col(Role::Bg)), sgi::css(sgi::col(Role::Muted))));
    }
    if (scroll_)
        scroll_->setStyleSheet(
            QStringLiteral("QScrollArea { background:%1; border:none; }").arg(sgi::css(sgi::col(Role::Bg))));
    render_status();
}

// ── Theme / language ─────────────────────────────────────────────────────────

void SoNguonPanel::refresh_panel_theme() {
    EconPanelBase::refresh_panel_theme();
    // Also runs from build_base_ui() inside the constructor, before the page exists — hence the guards.
    restyle_toolbar();
    if (loaded_)
        rebuild_page(/*keep_scroll=*/true); // builders read theme colours at call time
}

void SoNguonPanel::retranslateUi() {
    EconPanelBase::retranslateUi();
    if (audit_btn_) {
        audit_btn_->setText(tr("AUDIT"));
        audit_btn_->setToolTip(tr("Chỉ kiểm lại độ tươi, vấn đề và lịch — không chạy producer nào"));
    }
    if (export_btn_)
        export_btn_->setToolTip(tr("Xuất bảng tài sản dữ liệu của Sổ nguồn ra CSV"));
    update_buttons();
    render_status();
}

// ── Content page ─────────────────────────────────────────────────────────────

void SoNguonPanel::rebuild_page(bool keep_scroll) {
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

QWidget* SoNguonPanel::build_page() {
    auto* page = new QWidget;
    page->setObjectName("soNguonContent");
    page->setAttribute(Qt::WA_StyledBackground, true);
    page->setStyleSheet(
        QStringLiteral("QWidget#soNguonContent { background:%1; }").arg(sgi::css(sgi::col(Role::Bg))));
    auto* vl = new QVBoxLayout(page);
    vl->setContentsMargins(18, 14, 18, 24);
    vl->setSpacing(10);

    // Script warnings (missing registry, unreadable status files …) go above the page.
    QStringList warns;
    for (const QJsonValue& w : data_.value("meta").toObject().value("warnings").toArray()) {
        const QString s = w.toString().trimmed();
        if (!s.isEmpty())
            warns << sgi::span(sgi::esc(QStringLiteral("⚠ ") + s), sgi::col(Role::Amber));
    }
    if (!warns.isEmpty()) {
        auto* warn = sgi::make_label(page, sgi::col(Role::Ink2), 12, Qt::RichText);
        warn->setText(warns.join(QStringLiteral("<br>")));
        vl->addWidget(warn);
    }

    const QJsonObject trang = data_.value("trang").toObject();
    if (trang.value("sections").toArray().isEmpty()) {
        auto* empty = sgi::make_label(page, sgi::col(Role::Down), 12, Qt::RichText);
        empty->setText(sgi::esc(tr("[CẦN DATA] Payload không có trang để hiển thị.")));
        vl->addWidget(empty);
    } else {
        vl->addWidget(vnblocks::build_page(trang, page));
    }
    vl->addStretch(1);
    return page;
}

// ── Actions ──────────────────────────────────────────────────────────────────

void SoNguonPanel::export_payload_csv() {
    if (!loaded_)
        return;
    const QJsonObject csv = data_.value("csv").toObject();
    const QJsonArray columns = csv.value("columns").toArray();
    const QJsonArray rows = csv.value("rows").toArray();
    if (columns.isEmpty() || rows.isEmpty())
        return;

    const QString suggested = QDir::homePath() + QStringLiteral("/Downloads/so_nguon_%1.csv")
                                                     .arg(QDateTime::currentDateTime().toString("yyyyMMdd_HHmm"));
    const QString path = QFileDialog::getSaveFileName(this, tr("Xuất CSV"), suggested, tr("CSV (*.csv)"));
    if (path.isEmpty())
        return;

    QFile file(path);
    if (!file.open(QIODevice::WriteOnly | QIODevice::Truncate)) {
        LOG_WARN("SoNguonPanel", "Không ghi được CSV " + path + ": " + file.errorString());
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
            quoted << csv_quote(i < cells.size() ? csv_cell(cells.at(i)) : QString()); // pad short rows
        out << quoted.join(QLatin1Char(',')) << "\n";
    };
    const qsizetype width = columns.size();
    write_row(columns, width);
    for (const QJsonValue& rv : rows)
        write_row(rv.toArray(), std::max(width, rv.toArray().size()));
    out.flush();
    LOG_INFO("SoNguonPanel", QString("Xuất %1 dòng Sổ nguồn → %2").arg(rows.size()).arg(path));
}

} // namespace fincept::screens
