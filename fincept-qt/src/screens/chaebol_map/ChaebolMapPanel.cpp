// src/screens/chaebol_map/ChaebolMapPanel.cpp
// Bản đồ Chaebol & VN30 — build lifecycle and toolbar around chb::ChbView (see the header). scripts/chaebol_map.py
// `build` writes the page trees to disk and answers with a small manifest; the view reads the files itself.
// File-local helpers carry the chb_ prefix (the TU is kept out of unity batches, the prefix still avoids clashes).
#include "screens/chaebol_map/ChaebolMapPanel.h"

#include "core/logging/Logger.h"
#include "screens/chaebol_map/ChbView.h"
#include "screens/sgi_fa/SgiCommon.h"
#include "services/economics/EconomicsService.h"

#include <QDate>
#include <QDesktopServices>
#include <QDir>
#include <QFile>
#include <QFileDialog>
#include <QFileInfo>
#include <QHBoxLayout>
#include <QJsonArray>
#include <QLabel>
#include <QMessageBox>
#include <QPushButton>
#include <QStringList>
#include <QTextStream>
#include <QTimer>
#include <QUrl>

#include <algorithm>

namespace fincept::screens {

namespace {

using sgi::Role;

constexpr QLatin1StringView kChbSourceId{"chaebol_map"};
constexpr QLatin1StringView kChbScript{"chaebol_map.py"};
constexpr QLatin1StringView kChbSourceUrl{"http://localhost:9000/dl/master_plan_v21_chaebol_vn30.html"};
constexpr int kChbRefreshAfterSec = 30 * 60;      ///< rebuild on show / tick once the build is this old
constexpr int kChbRefreshTickMs = 15 * 60 * 1000; ///< how often the build age is re-evaluated
constexpr int kChbMaxTipLines = 30;               ///< warnings listed in the freshness tooltip

/// Where chaebol_map.py writes current.json (same rule as its state_dir(): CHB_STATE_DIR, else
/// $CHB_SYSTEM_DIR|~/SECOND BRAIN-OBSIDIAN/_System + /fincept_bridge/state/chaebol_map).
QString chb_state_dir() {
    const QString env = qEnvironmentVariable("CHB_STATE_DIR");
    if (!env.isEmpty()) return QDir::cleanPath(env);
    QString sys = qEnvironmentVariable("CHB_SYSTEM_DIR");
    if (sys.isEmpty()) sys = QDir::homePath() + QStringLiteral("/SECOND BRAIN-OBSIDIAN/_System");
    return QDir::cleanPath(sys + QStringLiteral("/fincept_bridge/state/chaebol_map"));
}

void chb_set_status(QLabel* label, const QString& text, const QColor& color, const QString& tooltip = {}) {
    if (!label) return;
    label->setText(text);
    // Tooltips auto-detect rich text: an error or path containing "<" would be parsed as markup. Force the
    // rich-text path with the text escaped.
    QString tip = sgi::esc(tooltip);
    tip.replace(QLatin1Char('\n'), QStringLiteral("<br>"));
    label->setToolTip(tooltip.isEmpty() ? QString() : QStringLiteral("<p>%1</p>").arg(tip));
    label->setStyleSheet(QStringLiteral("QLabel { color:%1; font-size:10px; background:transparent; }").arg(sgi::css(color)));
    // The toolbar layout squeezes this label to its first letter; reserve the width of the text explicitly.
    label->ensurePolished();
    label->setMinimumWidth(label->fontMetrics().horizontalAdvance(text) + 6);
}

/// RFC 4180 reader (quoted fields, doubled quotes, CR/LF inside quotes).
QList<QStringList> chb_parse_csv(const QString& text) {
    QList<QStringList> rows;
    QStringList row;
    QString field;
    bool quoted = false, any = false;
    for (qsizetype i = 0; i < text.size(); ++i) {
        const QChar c = text.at(i);
        if (quoted) {
            if (c != QLatin1Char('"')) {
                field += c;
            } else if (i + 1 < text.size() && text.at(i + 1) == QLatin1Char('"')) {
                field += c; // "" inside quotes
                ++i;
            } else {
                quoted = false;
            }
            continue;
        }
        if (c == QLatin1Char('"')) {
            quoted = any = true;
        } else if (c == QLatin1Char(',')) {
            row << field;
            field.clear();
            any = true;
        } else if (c == QLatin1Char('\n') || c == QLatin1Char('\r')) {
            if (c == QLatin1Char('\r') && i + 1 < text.size() && text.at(i + 1) == QLatin1Char('\n')) ++i;
            row << field;
            rows << row;
            row.clear();
            field.clear();
            any = false;
        } else {
            field += c;
            any = true;
        }
    }
    if (any || !field.isEmpty() || !row.isEmpty()) rows << (row << field);
    return rows;
}

QString chb_csv_cell(QString v) {
    // Spreadsheets evaluate a text cell starting with = + - @ as a formula (the CSV-injection vector): force it
    // to text with a leading apostrophe — plain numbers ("-3.5") stay numbers.
    bool isNumber = false;
    v.toDouble(&isNumber);
    if (!v.isEmpty() && !isNumber && QStringLiteral("=+-@\t\r").contains(v.at(0))) v.prepend(QLatin1Char('\''));
    if (v.contains(QLatin1Char(',')) || v.contains(QLatin1Char('"')) || v.contains(QLatin1Char('\n')) ||
        v.contains(QLatin1Char('\r')))
        v = QStringLiteral("\"") + v.replace(QStringLiteral("\""), QStringLiteral("\"\"")) + QStringLiteral("\"");
    return v;
}

} // namespace

// ── Construction ─────────────────────────────────────────────────────────────

ChaebolMapPanel::ChaebolMapPanel(QWidget* parent)
    : EconPanelBase(QString(kChbSourceId), QStringLiteral("#caa75c"), parent) {
    static int s_instances = 0;
    req_prefix_ = QStringLiteral("chb_%1_").arg(++s_instances);

    build_base_ui(this);
    set_stats_visible(false);

    // The view is its own scroll area (no QScrollArea around it: one scrollbar, sticky tab bar inside).
    view_ = new chb::ChbView(this);
    page_idx_ = add_content_page(view_);
    restyle_toolbar();
    // Tabs load lazily: a newly opened tab may add file/parse warnings to the label.
    connect(view_, &chb::ChbView::tab_changed, this, [this](const QString&) { render_fresh(); });

    // The base CSV button exports the generic results table, which this panel never fills — point it at the
    // build's own export.csv.
    disconnect(export_btn_, &QPushButton::clicked, this, &ChaebolMapPanel::export_csv);
    connect(export_btn_, &QPushButton::clicked, this, &ChaebolMapPanel::export_build_csv);
    export_btn_->setToolTip(tr("Xuất export.csv của bản dựng (bảng dữ liệu các tab) ra CSV"));
    export_btn_->setEnabled(false);

    connect(&services::EconomicsService::instance(), &services::EconomicsService::result_ready, this,
            &ChaebolMapPanel::on_result);

    // The tab can stay open for days: re-check the build age on a timer.
    refresh_timer_ = new QTimer(this);
    refresh_timer_->setInterval(kChbRefreshTickMs);
    connect(refresh_timer_, &QTimer::timeout, this, &ChaebolMapPanel::on_refresh_tick);
    refresh_timer_->start();

    show_empty(tr("Mở tab để nạp Bản đồ Chaebol & VN30…"));
}

void ChaebolMapPanel::build_controls(QHBoxLayout* thl) {
    fresh_lbl_ = new QLabel;
    fresh_lbl_->setTextFormat(Qt::PlainText);
    thl->addWidget(fresh_lbl_);

    web_btn_ = new QPushButton(tr("🌐 BẢN GỐC"));
    web_btn_->setFixedHeight(26);
    web_btn_->setCursor(Qt::PointingHandCursor);
    web_btn_->setToolTip(tr("Mở trang gốc Master Plan V21 (localhost:9000) trong trình duyệt"));
    connect(web_btn_, &QPushButton::clicked, this, &ChaebolMapPanel::open_source_page);
    thl->addWidget(web_btn_);
}

// ── Build lifecycle ──────────────────────────────────────────────────────────

void ChaebolMapPanel::activate() {
    if (fetching_) return;
    if (!loaded_ && !tried_disk_) {
        tried_disk_ = true;
        load_from_disk(); // show the newest build at once; rebuilt below when it is too old
    }
    if (refresh_due()) on_fetch();
    else render_fresh();
}

bool ChaebolMapPanel::refresh_due() const {
    if (!loaded_) return true;
    const QDateTime at = build_time();
    return !at.isValid() || at.secsTo(QDateTime::currentDateTimeUtc()) >= kChbRefreshAfterSec;
}

QDateTime ChaebolMapPanel::build_time() const {
    if (!view_ || !view_->has_page()) return {};
    const QDateTime g = QDateTime::fromString(view_->manifest().value("generated").toString(), Qt::ISODate);
    if (g.isValid()) return g.toUTC();
    const QFileInfo fi(view_->build_file(QStringLiteral("manifest.json")));
    return fi.exists() ? fi.lastModified().toUTC() : QDateTime();
}

void ChaebolMapPanel::on_refresh_tick() {
    if (!loaded_ || fetching_) return;
    if (isVisible()) activate(); // rebuild when due, else re-evaluate the label
    else render_fresh();
}

bool ChaebolMapPanel::load_from_disk() {
    const QString path = QDir(chb_state_dir()).filePath(QStringLiteral("current.json"));
    if (!QFileInfo::exists(path)) return false;
    QString err;
    if (!view_->load_current(path, /*keep_state=*/false, &err)) {
        LOG_WARN("ChaebolMapPanel", "Bỏ qua bản dựng trên đĩa: " + err);
        return false;
    }
    on_loaded();
    return true;
}

void ChaebolMapPanel::on_fetch() {
    fetching_ = true;
    req_current_ = req_prefix_ + QStringLiteral("build_%1").arg(++req_seq_);
    if (!loaded_) {
        show_loading(tr("Đang dựng Bản đồ Chaebol & VN30 — 18 tab · cấu trúc cổ đông · dữ liệu sống…"));
    } else {
        // Keep the current page on screen while the rebuild runs.
        chb_set_status(fresh_lbl_, tr("đang dựng lại…"), sgi::col(Role::Muted));
        if (fetch_btn_) fetch_btn_->setEnabled(false);
    }
    // Always bypass the service cache: a cached answer may point at a build directory already pruned.
    services::EconomicsService::instance().execute(QString(kChbSourceId), QString(kChbScript), QStringLiteral("build"),
                                                   QStringList{}, req_current_, /*force=*/true);
}

void ChaebolMapPanel::on_result(const QString& request_id, const services::EconomicsResult& result) {
    // result_ready reaches every connected panel — route strictly by source + this instance's prefix, then drop
    // answers superseded by a newer FETCH.
    if (result.source_id != kChbSourceId || !request_id.startsWith(req_prefix_) || request_id != req_current_) return;
    fetching_ = false;
    if (fetch_btn_) fetch_btn_->setEnabled(true);

    // EconomicsService already turns a top-level "error" into a failure; the check here is a guard.
    QString err = result.success ? result.data.value("error").toString() : result.error;
    if (result.success && err.isEmpty() && view_->set_payload(result.data, /*keep_state=*/loaded_, &err)) {
        last_error_.clear();
        on_loaded();
        return;
    }
    if (err.isEmpty()) err = tr("không rõ nguyên nhân");
    LOG_WARN("ChaebolMapPanel", "Dựng Bản đồ Chaebol lỗi: " + err);
    if (loaded_) {
        // Keep the page; short label (fixed toolbar), the full error in the tooltip.
        last_error_ = err;
        render_fresh();
    } else {
        // Script errors already say what to do; add the run hint only for runner-level failures.
        show_error(err.contains(QLatin1String("chaebol_map.py"))
                       ? err
                       : err + tr("\nChạy thử: python3 scripts/chaebol_map.py build"));
    }
}

void ChaebolMapPanel::on_loaded() {
    loaded_ = true;
    show_content_page(page_idx_);
    const QJsonObject m = view_->manifest();
    const QJsonObject csv = m.value("csv").toObject();
    const QString csvPath = view_->build_file(csv.value("file").toString(QStringLiteral("export.csv")));
    export_btn_->setEnabled(!csvPath.isEmpty() && QFileInfo::exists(csvPath) && csv.value("rows").toInt(-1) != 0);
    render_fresh();
    LOG_INFO("ChaebolMapPanel", QString("Bản đồ Chaebol: bản dựng %1 · chế độ %2 · dữ liệu đến %3 · %4 cảnh báo")
                                    .arg(view_->build_dir(), m.value("mode").toString(QStringLiteral("—")),
                                         m.value("data_to").toString(QStringLiteral("—")))
                                    .arg(m.value("warnings").toArray().size()));
}

// ── Toolbar ──────────────────────────────────────────────────────────────────

void ChaebolMapPanel::render_fresh() {
    if (!fresh_lbl_) return;
    if (!loaded_ || !view_) {
        chb_set_status(fresh_lbl_, QString(), sgi::col(Role::Muted));
        return;
    }
    if (!last_error_.isEmpty()) {
        chb_set_status(fresh_lbl_, tr("⚠ dựng lại lỗi"), sgi::col(Role::Down), last_error_);
        return;
    }
    const QJsonObject m = view_->manifest();
    const QDate to = QDate::fromString(m.value("data_to").toString().left(10), Qt::ISODate);
    QString txt = to.isValid() ? tr("dữ liệu đến %1").arg(to.toString(QStringLiteral("dd/MM"))) : tr("dữ liệu đến [CẦN DATA]");
    const QDateTime at = build_time();
    if (at.isValid()) {
        const QDateTime local = at.toLocalTime();
        txt += tr(" · dựng %1").arg(local.toString(local.date() == QDate::currentDate() ? QStringLiteral("HH:mm")
                                                                                         : QStringLiteral("dd/MM HH:mm")));
    }
    QStringList warns;
    for (const QJsonValue& w : m.value("warnings").toArray()) {
        const QString s = w.toString().trimmed();
        if (!s.isEmpty()) warns << s;
    }
    warns += view_->warnings();
    warns.removeDuplicates();
    if (!warns.isEmpty()) txt += tr(" · %1 cảnh báo").arg(warns.size());
    if (!fetching_ && refresh_due()) txt += tr(" · ⚠ bản dựng cũ");

    QString tip;
    for (int i = 0; i < warns.size() && i < kChbMaxTipLines; ++i) tip += QStringLiteral("⚠ ") + warns[i] + QLatin1Char('\n');
    if (warns.size() > kChbMaxTipLines) tip += tr("… và %1 cảnh báo khác").arg(warns.size() - kChbMaxTipLines);
    chb_set_status(fresh_lbl_, txt, sgi::col(warns.isEmpty() ? Role::Muted : Role::Amber), tip.trimmed());
}

void ChaebolMapPanel::restyle_toolbar() {
    if (web_btn_) {
        web_btn_->setStyleSheet(QStringLiteral("QPushButton { background:%1; color:%2; font-weight:bold;"
                                               " border-radius:4px; padding:0 8px; border:1px solid %3; }"
                                               "QPushButton:hover { background:%4; color:%5; }"
                                               "QPushButton:disabled { color:%6; }")
                                    .arg(sgi::css(sgi::col(Role::Surface2)), sgi::css(sgi::col(Role::Ink2)),
                                         sgi::css(sgi::col(Role::Line)), sgi::css(sgi::col(Role::Amber)),
                                         sgi::css(sgi::col(Role::Bg)), sgi::css(sgi::col(Role::Muted))));
    }
    render_fresh();
}

// ── Theme / language ─────────────────────────────────────────────────────────

void ChaebolMapPanel::refresh_panel_theme() {
    EconPanelBase::refresh_panel_theme();
    // Also runs from build_base_ui() inside the constructor, before the view exists — hence the guards. The
    // canvas is not restyled: the page keeps its own fixed dark palette like the original.
    restyle_toolbar();
}

void ChaebolMapPanel::retranslateUi() {
    if (web_btn_) {
        web_btn_->setText(tr("🌐 BẢN GỐC"));
        web_btn_->setToolTip(tr("Mở trang gốc Master Plan V21 (localhost:9000) trong trình duyệt"));
    }
    if (export_btn_) export_btn_->setToolTip(tr("Xuất export.csv của bản dựng (bảng dữ liệu các tab) ra CSV"));
    if (!fetching_) render_fresh();
    EconPanelBase::retranslateUi();
}

// ── Actions ──────────────────────────────────────────────────────────────────

void ChaebolMapPanel::export_build_csv() {
    if (!loaded_ || !view_) return;
    const QJsonObject m = view_->manifest();
    const QString rel = m.value("csv").toObject().value("file").toString(QStringLiteral("export.csv"));
    const QString src = view_->build_file(rel);
    QFile in(src);
    if (src.isEmpty() || !in.open(QIODevice::ReadOnly)) {
        QMessageBox::warning(this, tr("Xuất CSV"), tr("Bản dựng không có %1 — bấm FETCH để dựng lại.").arg(rel));
        return;
    }
    QString text = QString::fromUtf8(in.readAll());
    if (text.startsWith(QChar(0xFEFF))) text.remove(0, 1);
    const QList<QStringList> rows = chb_parse_csv(text);
    if (rows.size() < 2) {
        QMessageBox::information(this, tr("Xuất CSV"), tr("export.csv chưa có dòng dữ liệu nào (các tab chưa xuất bảng)."));
        return;
    }

    QString to = m.value("data_to").toString();
    to.remove(QLatin1Char('-'));
    const QString suggested = QDir::homePath() + QStringLiteral("/Downloads/chaebol_map_%1_%2.csv")
                                                     .arg(to.isEmpty() ? QStringLiteral("khong_ngay") : to,
                                                          QDate::currentDate().toString("yyyyMMdd"));
    const QString path = QFileDialog::getSaveFileName(this, tr("Xuất CSV"), suggested, tr("CSV (*.csv)"));
    if (path.isEmpty()) return;

    QFile file(path);
    if (!file.open(QIODevice::WriteOnly | QIODevice::Truncate)) {
        LOG_WARN("ChaebolMapPanel", "Không ghi được CSV " + path + ": " + file.errorString());
        QMessageBox::warning(this, tr("Xuất CSV"), tr("Không ghi được tệp:\n%1\n%2").arg(path, file.errorString()));
        return;
    }
    file.write("\xEF\xBB\xBF"); // UTF-8 BOM so Excel reads the Vietnamese labels correctly
    QTextStream out(&file);
    out.setEncoding(QStringConverter::Utf8);
    qsizetype width = 0;
    for (const QStringList& r : rows) width = std::max(width, r.size());
    for (const QStringList& r : rows) {
        QStringList cells;
        cells.reserve(width);
        for (qsizetype i = 0; i < width; ++i) cells << chb_csv_cell(i < r.size() ? r.at(i) : QString()); // pad short rows
        out << cells.join(QLatin1Char(',')) << "\n";
    }
    out.flush();
    LOG_INFO("ChaebolMapPanel", QString("Xuất %1 dòng Bản đồ Chaebol → %2").arg(rows.size() - 1).arg(path));
}

void ChaebolMapPanel::open_source_page() {
    const QUrl url{QString(kChbSourceUrl)};
    if (!QDesktopServices::openUrl(url)) LOG_WARN("ChaebolMapPanel", "Không mở được trang gốc: " + url.toString());
}

} // namespace fincept::screens
