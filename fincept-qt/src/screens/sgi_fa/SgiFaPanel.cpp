// src/screens/sgi_fa/SgiFaPanel.cpp
// SGI FA — fetch lifecycle, toolbar and the one scrollable content page (section map in the header).
// Every number arrives pre-formatted from scripts/sgi_fa.py (`overview [ky]`); the section builders
// (SgiSectionsTop.cpp / SgiSectionsBottom.cpp) lay it out and show "[CẦN DATA]" for any gap, so this
// file only hands each builder its payload slice. A null issue still renders: the sections show their
// gaps and meta.warnings are surfaced at the top. All data strings are HTML-escaped before they reach
// a rich-text QLabel.
#include "screens/sgi_fa/SgiFaPanel.h"

#include "core/logging/Logger.h"
#include "screens/sgi_fa/SgiCommon.h"
#include "screens/sgi_fa/SgiSections.h"
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
#include <functional>

namespace fincept::screens {

namespace {

using sgi::Role;

constexpr QLatin1StringView kSourceId{"sgi"};
constexpr QLatin1StringView kScript{"sgi_fa.py"};
constexpr int kRefreshAfterSec = 30 * 60;      ///< re-fetch on show / tick once the last load is this old
constexpr int kRefreshTickMs = 15 * 60 * 1000; ///< how often the data age is re-evaluated

/// "2026-09-20" → "20/09/2026"; anything unparsable is returned as is.
QString fmt_date(const QString& iso) {
    const QDate d = QDate::fromString(iso.left(10), Qt::ISODate);
    return d.isValid() ? d.toString(QStringLiteral("dd/MM/yyyy")) : iso;
}

/// The issue's own weekly page. The URL comes from the issue JSON: only ever hand a web URL to the OS.
QUrl issue_url(const QJsonObject& payload) {
    const QUrl url(payload.value("issue").toObject().value("artifact_url").toString().trimmed());
    if (!url.isValid() || (url.scheme() != QLatin1String("http") && url.scheme() != QLatin1String("https")))
        return {};
    return url;
}

void set_status(QLabel* label, const QString& text, const QColor& color, const QString& tooltip = {}) {
    if (!label)
        return;
    label->setText(text);
    label->setToolTip(tooltip);
    label->setStyleSheet(
        QStringLiteral("QLabel { color:%1; font-size:10px; background:transparent; }").arg(sgi::css(color)));
    // The toolbar layout squeezed this label to its first letter (seen offscreen: "K" for
    // "Kỳ 20/09/2026 · cập nhật …"); reserve the width of the text explicitly.
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
    if (v.isBool())
        return v.toBool() ? QStringLiteral("true") : QStringLiteral("false");
    if (v.isString()) {
        // Spreadsheets evaluate a text cell starting with = + - @ as a formula ("+0,76 điểm %" → #NAME?,
        // and the same path is the CSV-injection vector): force it to text with a leading apostrophe.
        QString s = v.toString();
        if (!s.isEmpty() && QStringLiteral("=+-@\t\r").contains(s.at(0)))
            s.prepend(QLatin1Char('\''));
        return s;
    }
    return {};
}

} // namespace

// ── Construction ─────────────────────────────────────────────────────────────

SgiFaPanel::SgiFaPanel(QWidget* parent)
    : EconPanelBase(QString(kSourceId), sgi::css(sgi::col(Role::Amber)), parent) {
    static int s_instances = 0;
    req_prefix_ = QStringLiteral("sgi_%1_").arg(++s_instances);

    build_base_ui(this);
    set_stats_visible(false);

    scroll_ = new QScrollArea(this);
    scroll_->setWidgetResizable(true);
    scroll_->setFrameShape(QFrame::NoFrame);
    scroll_->setHorizontalScrollBarPolicy(Qt::ScrollBarAlwaysOff);
    scroll_->setVerticalScrollBarPolicy(Qt::ScrollBarAsNeeded);
    scroll_->setWidget(new QWidget); // placeholder until the first payload
    page_idx_ = add_content_page(scroll_);
    restyle_toolbar();

    // The base CSV button exports the generic results table, which this panel never fills —
    // point it at the payload's own export rows (lights, composites, thresholds, anchors).
    disconnect(export_btn_, &QPushButton::clicked, this, &SgiFaPanel::export_csv);
    connect(export_btn_, &QPushButton::clicked, this, &SgiFaPanel::export_payload_csv);
    export_btn_->setToolTip(tr("Xuất đèn · tổ hợp · ngưỡng · neo của kỳ đang xem ra CSV"));
    export_btn_->setEnabled(false);

    connect(&services::EconomicsService::instance(), &services::EconomicsService::result_ready, this,
            &SgiFaPanel::on_result);

    // The tab can stay open for days: re-check the data age on a timer so the stale warning and the
    // re-fetch do not wait for a manual FETCH.
    refresh_timer_ = new QTimer(this);
    refresh_timer_->setInterval(kRefreshTickMs);
    connect(refresh_timer_, &QTimer::timeout, this, &SgiFaPanel::on_refresh_tick);
    refresh_timer_->start();

    show_empty(tr("Mở tab để nạp Trạm Quan Trắc Vĩ Mô…"));
}

void SgiFaPanel::build_controls(QHBoxLayout* thl) {
    ky_lbl_ = new QLabel(tr("KỲ"));
    ky_lbl_->setStyleSheet(ctrl_label_style());
    thl->addWidget(ky_lbl_);

    issue_combo_ = new QComboBox;
    issue_combo_->setMinimumWidth(120);
    issue_combo_->setFixedHeight(26);
    issue_combo_->setToolTip(tr("Chọn bản tuần — mục đầu là kỳ mới nhất"));
    issue_combo_->setEnabled(false);
    connect(issue_combo_, &QComboBox::currentIndexChanged, this, &SgiFaPanel::on_issue_selected);
    thl->addWidget(issue_combo_);

    thl->addSpacing(12);

    fresh_lbl_ = new QLabel;
    fresh_lbl_->setTextFormat(Qt::PlainText);
    thl->addWidget(fresh_lbl_);

    web_btn_ = new QPushButton(tr("🌐 BẢN TUẦN"));
    web_btn_->setFixedHeight(26);
    web_btn_->setCursor(Qt::PointingHandCursor);
    web_btn_->setToolTip(tr("Mở bản tuần gốc (artifact) trong trình duyệt"));
    web_btn_->setEnabled(false);
    connect(web_btn_, &QPushButton::clicked, this, &SgiFaPanel::open_issue_page);
    thl->addWidget(web_btn_);
}

// ── Fetch / results ──────────────────────────────────────────────────────────

void SgiFaPanel::activate() {
    if (fetching_)
        return;
    if (refresh_due())
        on_fetch();
    else
        render_fresh();
}

bool SgiFaPanel::refresh_due() const {
    return !loaded_ || !fetched_at_.isValid() ||
           fetched_at_.secsTo(QDateTime::currentDateTimeUtc()) >= kRefreshAfterSec;
}

void SgiFaPanel::on_refresh_tick() {
    if (!loaded_ || fetching_)
        return;
    if (isVisible())
        activate(); // re-fetch when due, else re-evaluate the label
    else
        render_fresh();
}

void SgiFaPanel::on_fetch() {
    // The issue date only ever comes from the payload's own list; still, pass nothing that is not a date.
    if (!requested_ky_.isEmpty() && !QDate::fromString(requested_ky_, Qt::ISODate).isValid())
        requested_ky_.clear();

    fetching_ = true;
    req_current_ = req_prefix_ + QStringLiteral("overview_") +
                   (requested_ky_.isEmpty() ? QStringLiteral("latest") : requested_ky_);
    if (!loaded_) {
        show_loading(tr("Đang nạp Trạm Quan Trắc Vĩ Mô — bản tuần · engine §7 · dữ liệu live…"));
    } else {
        // Keep the current content on screen while the refresh runs.
        set_status(fresh_lbl_, tr("đang làm mới…"), sgi::col(Role::Muted));
        if (fetch_btn_)
            fetch_btn_->setEnabled(false);
    }
    QStringList args;
    if (!requested_ky_.isEmpty())
        args << requested_ky_;
    services::EconomicsService::instance().execute(QString(kSourceId), QString(kScript), QStringLiteral("overview"),
                                                   args, req_current_, /*force=*/true);
}

void SgiFaPanel::on_result(const QString& request_id, const services::EconomicsResult& result) {
    // result_ready reaches every connected panel — route strictly by source + this instance's prefix,
    // then drop answers superseded by a newer request (the user switched issue meanwhile).
    if (result.source_id != kSourceId || !request_id.startsWith(req_prefix_) || request_id != req_current_)
        return;
    fetching_ = false;

    // EconomicsService already turns a top-level "error" into a failure; the check here is a guard.
    QString err = result.success ? result.data.value("error").toString() : result.error;
    if (result.success && err.isEmpty()) {
        fetched_at_ = QDateTime::currentDateTimeUtc();
        apply_overview(result.data);
        return;
    }
    if (err.isEmpty())
        err = tr("không rõ nguyên nhân");
    LOG_WARN("SgiFaPanel", "Nạp Trạm Quan Trắc Vĩ Mô lỗi: " + err);

    if (loaded_) {
        // Keep the page on screen and put the combo back on the issue it shows.
        requested_ky_ = loaded_request_ky_;
        populate_issues();
        // Short text: the label sits in the fixed toolbar, a long message would widen the panel.
        set_status(fresh_lbl_, tr("⚠ làm mới lỗi"), sgi::col(Role::Down), err);
        if (fetch_btn_)
            fetch_btn_->setEnabled(true);
    } else {
        // Script errors already say what to do; add the run hint only for runner-level failures.
        show_error(err.contains(QLatin1String("python3"))
                       ? err
                       : err + tr("\nChạy thử: python3 scripts/sgi_fa.py overview"));
    }
}

void SgiFaPanel::apply_overview(const QJsonObject& data) {
    const QString prev_ky = data_.value("meta").toObject().value("ky").toString();
    data_ = data;
    const bool same_issue = loaded_ && prev_ky == data_.value("meta").toObject().value("ky").toString();
    loaded_ = true;
    loaded_request_ky_ = requested_ky_;

    populate_issues();
    render_fresh();
    web_btn_->setEnabled(issue_url(data_).isValid());
    const QJsonObject csv = data_.value("csv").toObject();
    export_btn_->setEnabled(!csv.value("columns").toArray().isEmpty() && !csv.value("rows").toArray().isEmpty());

    rebuild_page(/*keep_scroll=*/same_issue); // a periodic refresh keeps the reader's place
    show_content_page(page_idx_);

    const QJsonObject meta = data_.value("meta").toObject();
    LOG_INFO("SgiFaPanel", QString("Trạm Quan Trắc Vĩ Mô: kỳ %1 · %2 cảnh báo")
                               .arg(meta.value("ky").toString(QStringLiteral("—")))
                               .arg(meta.value("warnings").toArray().size()));
}

// ── Toolbar ──────────────────────────────────────────────────────────────────

void SgiFaPanel::populate_issues() {
    if (!issue_combo_)
        return;
    const QJsonObject meta = data_.value("meta").toObject();
    QStringList issues;
    for (const QJsonValue& v : meta.value("issues").toArray()) {
        const QString ky = v.toString().trimmed();
        if (!ky.isEmpty() && !issues.contains(ky))
            issues << ky;
    }
    // ISO dates sort lexically: newest first, whatever order the payload used.
    std::sort(issues.begin(), issues.end(), std::greater<QString>());

    const QSignalBlocker block(issue_combo_);
    issue_combo_->clear();
    if (issues.isEmpty()) {
        issue_combo_->addItem(tr("— chưa có bản tuần —"), QString());
        issue_combo_->setEnabled(false);
        return;
    }
    for (const QString& ky : issues)
        issue_combo_->addItem(fmt_date(ky), ky);
    issue_combo_->setEnabled(true);
    // Select the issue actually displayed; nothing (-1) rather than a wrong one when it is not listed.
    const QString shown = meta.value("ky").toString();
    issue_combo_->setCurrentIndex(shown.isEmpty() ? -1 : issue_combo_->findData(shown));
}

void SgiFaPanel::on_issue_selected(int index) {
    if (index < 0 || !issue_combo_)
        return;
    const QString ky = issue_combo_->itemData(index).toString();
    if (ky.isEmpty())
        return;
    // The newest entry means "follow the latest issue", so a new weekly file shows up on the next refresh.
    requested_ky_ = index == 0 ? QString() : ky;
    const QString shown = data_.value("meta").toObject().value("ky").toString();
    if (ky == shown && !fetching_) {
        loaded_request_ky_ = requested_ky_;
        return;
    }
    on_fetch();
}

void SgiFaPanel::render_fresh() {
    if (!fresh_lbl_)
        return;
    if (!loaded_) {
        set_status(fresh_lbl_, QString(), sgi::col(Role::Muted));
        return;
    }
    const QJsonObject meta = data_.value("meta").toObject();
    const QString ky = meta.value("ky").toString();
    QString txt = ky.isEmpty() ? tr("chưa có bản tuần") : tr("Kỳ %1").arg(fmt_date(ky));
    QDateTime at = QDateTime::fromString(meta.value("generated").toString(), Qt::ISODate);
    if (!at.isValid())
        at = fetched_at_;
    if (at.isValid())
        txt += tr(" · cập nhật %1").arg(at.toLocalTime().toString(QStringLiteral("HH:mm")));

    if (meta.value("stale").toBool()) {
        const QString stale = meta.value("stale_text").toString().trimmed();
        const QString stale_txt = stale.isEmpty() ? tr("BẢN TUẦN CŨ") : stale;
        set_status(fresh_lbl_, txt + QStringLiteral(" · ⚠ ") + stale_txt, sgi::col(Role::Down), stale_txt);
    } else {
        set_status(fresh_lbl_, txt, sgi::col(Role::Muted));
    }
}

void SgiFaPanel::restyle_toolbar() {
    if (web_btn_) {
        web_btn_->setStyleSheet(QStringLiteral("QPushButton { background:%1; color:%2; font-weight:bold;"
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
    render_fresh();
}

// ── Theme / language ─────────────────────────────────────────────────────────

void SgiFaPanel::refresh_panel_theme() {
    EconPanelBase::refresh_panel_theme();
    // Also runs from build_base_ui() inside the constructor, before the page exists — hence the guards.
    restyle_toolbar();
    if (loaded_)
        rebuild_page(/*keep_scroll=*/true); // builders read theme colours at call time
}

void SgiFaPanel::retranslateUi() {
    if (ky_lbl_)
        ky_lbl_->setText(tr("KỲ"));
    if (issue_combo_)
        issue_combo_->setToolTip(tr("Chọn bản tuần — mục đầu là kỳ mới nhất"));
    if (web_btn_) {
        web_btn_->setText(tr("🌐 BẢN TUẦN"));
        web_btn_->setToolTip(tr("Mở bản tuần gốc (artifact) trong trình duyệt"));
    }
    if (export_btn_)
        export_btn_->setToolTip(tr("Xuất đèn · tổ hợp · ngưỡng · neo của kỳ đang xem ra CSV"));
    if (loaded_)
        populate_issues(); // the empty-list placeholder is translated
    if (!fetching_)
        render_fresh();
    EconPanelBase::retranslateUi();
}

// ── Content page ─────────────────────────────────────────────────────────────

void SgiFaPanel::rebuild_page(bool keep_scroll) {
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

QWidget* SgiFaPanel::build_page() {
    const QJsonObject meta = data_.value("meta").toObject();
    const QJsonValue issue_v = data_.value("issue");
    const bool has_issue = issue_v.isObject();
    // A null issue / engine still renders: every builder gets an empty object and shows its gaps.
    const QJsonObject issue = issue_v.toObject();
    const QJsonObject engine = data_.value("engine").toObject();
    const QJsonObject live = data_.value("live").toObject();

    auto* page = new QWidget;
    page->setObjectName("sgiContent");
    page->setAttribute(Qt::WA_StyledBackground, true);
    page->setStyleSheet(QStringLiteral("QWidget#sgiContent { background:%1; }").arg(sgi::css(sgi::col(Role::Bg))));
    auto* vl = new QVBoxLayout(page);
    vl->setContentsMargins(18, 14, 18, 24);
    vl->setSpacing(10);

    // Meta line: method · kỳ · dữ liệu đến · kỳ sau · stale warning.
    {
        QStringList parts;
        const QString method = sgi::str(issue, "phuong_phap").trimmed();
        if (!method.isEmpty())
            parts << sgi::esc(method);
        const QString ky = has_issue ? sgi::str(issue, "ky") : meta.value("ky").toString();
        parts << sgi::esc(ky.isEmpty() ? tr("Kỳ [CẦN DATA]") : tr("Kỳ %1").arg(fmt_date(ky)));
        const QString den = sgi::str(issue, "du_lieu_den");
        if (!den.isEmpty())
            parts << sgi::esc(tr("dữ liệu đến %1").arg(fmt_date(den)));
        QString sau = sgi::str(issue, "ky_sau");
        if (sau.isEmpty())
            sau = meta.value("ky_sau").toString();
        if (!sau.isEmpty())
            parts << sgi::esc(tr("kỳ sau %1").arg(fmt_date(sau)));
        const QString stale = meta.value("stale_text").toString().trimmed();
        if (meta.value("stale").toBool() && !stale.isEmpty())
            parts << sgi::span(sgi::esc(stale), sgi::col(Role::Down), true);

        auto* meta_lbl = sgi::make_label(page, sgi::col(Role::Muted), 12, Qt::RichText);
        meta_lbl->setText(parts.join(QStringLiteral(" · ")));
        vl->addWidget(meta_lbl);
    }

    // No issue on disk (or not loadable): say so up front, with the script's own warnings.
    if (!has_issue) {
        QString html = sgi::span(sgi::esc(tr("[CẦN DATA] Không có bản tuần cho kỳ này — chỉ còn dữ liệu live; "
                                             "các mục của bản tuần để trống.")),
                                 sgi::col(Role::Down), true);
        for (const QJsonValue& w : meta.value("warnings").toArray()) {
            const QString s = w.toString().trimmed();
            if (!s.isEmpty())
                html += QStringLiteral("<br>") + sgi::span(sgi::esc(QStringLiteral("⚠ ") + s), sgi::col(Role::Amber));
        }
        auto* warn = sgi::make_label(page, sgi::col(Role::Ink2), 12, Qt::RichText);
        warn->setText(html);
        vl->addWidget(warn);
    }

    vl->addWidget(sgi::build_gate(data_.value("gate").toObject(), page));
    vl->addWidget(sgi::build_verdict(issue, engine, page));
    vl->addWidget(sgi::build_cycles(issue.value("chu_ky").toObject(), page));
    vl->addWidget(sgi::build_machine(issue, page));
    vl->addWidget(sgi::build_conditions(issue.value("dieu_kien_day").toArray(), engine.value("day").toObject(), page));
    vl->addWidget(sgi::build_blocks(issue, engine, page));
    vl->addWidget(sgi::build_hhp_crosscheck(issue.value("doi_chieu_hhp").toObject(), page));
    vl->addWidget(sgi::build_evidence(issue, live, data_.value("charts").toArray(), page));
    vl->addWidget(sgi::build_anchors(data_.value("neo").toArray(), page));
    vl->addWidget(sgi::build_thresholds(data_.value("nguong").toArray(), page));
    vl->addWidget(sgi::build_portfolio(issue.value("danh_muc").toObject(), page));
    vl->addWidget(sgi::build_track_record(issue.value("track_record").toObject(), page));
    vl->addWidget(sgi::build_inversion(issue.value("nghich_dao").toObject(), page));
    vl->addWidget(sgi::build_sources(meta, issue, page));
    vl->addStretch(1);
    return page;
}

// ── Actions ──────────────────────────────────────────────────────────────────

void SgiFaPanel::export_payload_csv() {
    if (!loaded_)
        return;
    const QJsonObject csv = data_.value("csv").toObject();
    const QJsonArray columns = csv.value("columns").toArray();
    const QJsonArray rows = csv.value("rows").toArray();
    if (columns.isEmpty() || rows.isEmpty())
        return;

    QString ky = data_.value("meta").toObject().value("ky").toString();
    ky.remove(QLatin1Char('-'));
    const QString suggested = QDir::homePath() + QStringLiteral("/Downloads/sgi_fa_%1_%2.csv")
                                                     .arg(ky.isEmpty() ? QStringLiteral("khong_ky") : ky,
                                                          QDate::currentDate().toString("yyyyMMdd"));
    const QString path = QFileDialog::getSaveFileName(this, tr("Xuất CSV"), suggested, tr("CSV (*.csv)"));
    if (path.isEmpty())
        return;

    QFile file(path);
    if (!file.open(QIODevice::WriteOnly | QIODevice::Truncate)) {
        LOG_WARN("SgiFaPanel", "Không ghi được CSV " + path + ": " + file.errorString());
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
    LOG_INFO("SgiFaPanel", QString("Xuất %1 dòng SGI FA → %2").arg(rows.size()).arg(path));
}

void SgiFaPanel::open_issue_page() {
    const QUrl url = issue_url(data_);
    if (!url.isValid())
        return;
    if (!QDesktopServices::openUrl(url))
        LOG_WARN("SgiFaPanel", "Không mở được bản tuần: " + url.toString());
}

} // namespace fincept::screens
