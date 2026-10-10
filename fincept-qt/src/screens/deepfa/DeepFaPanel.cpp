// src/screens/deepfa/DeepFaPanel.cpp
// DEEP FA — fetch lifecycle, toolbar and the two pages (Tổng quan / Mã). Section builders lay out the
// ticker payload (DeepFaSectionsTop.cpp / Bottom.cpp); the triage table renders the overview rows
// (DeepFaUniverseTable.cpp). All data strings are HTML-escaped before they reach a rich-text QLabel.
#include "screens/deepfa/DeepFaPanel.h"

#include "core/logging/Logger.h"
#include "screens/deepfa/DeepFaCommon.h"
#include "screens/deepfa/DeepFaSections.h"
#include "screens/deepfa/DeepFaUniverseTable.h"
#include "services/economics/EconomicsService.h"

#include <QAbstractItemView>
#include <QCheckBox>
#include <QComboBox>
#include <QCompleter>
#include <QDate>
#include <QDesktopServices>
#include <QDialog>
#include <QDir>
#include <QFile>
#include <QFileDialog>
#include <QFrame>
#include <QHBoxLayout>
#include <QJsonArray>
#include <QLabel>
#include <QLineEdit>
#include <QMessageBox>
#include <QPushButton>
#include <QRegularExpression>
#include <QScrollArea>
#include <QScrollBar>
#include <QStringList>
#include <QStringListModel>
#include <QTextBrowser>
#include <QTextStream>
#include <QTimer>
#include <QUrl>
#include <QVBoxLayout>

#include <algorithm>

namespace fincept::screens {

namespace {

using deepfa::Role;

constexpr QLatin1StringView kSourceId{"deepfa"};
constexpr QLatin1StringView kScript{"deepfa.py"};
constexpr int kRefreshAfterSec = 30 * 60;      ///< re-fetch on show / tick once the last load is this old
constexpr int kRefreshTickMs = 15 * 60 * 1000; ///< how often the data age is re-evaluated

const QRegularExpression& ticker_re() {
    static const QRegularExpression re(QStringLiteral("^[A-Z0-9]{2,6}$"));
    return re;
}

void set_status(QLabel* label, const QString& text, const QColor& color, const QString& tooltip = {}) {
    if (!label)
        return;
    label->setText(text);
    label->setToolTip(tooltip);
    label->setStyleSheet(QStringLiteral("QLabel { color:%1; font-size:10px; background:transparent; }").arg(deepfa::css(color)));
}

QString csv_quote(QString v) {
    if (v.contains(QLatin1Char(',')) || v.contains(QLatin1Char('"')) || v.contains(QLatin1Char('\n')) || v.contains(QLatin1Char('\r')))
        v = QStringLiteral("\"") + v.replace(QStringLiteral("\""), QStringLiteral("\"\"")) + QStringLiteral("\"");
    return v;
}

QString cell_txt(const QJsonObject& r, const char* key) {
    const QJsonValue v = r.value(QLatin1String(key));
    if (v.isObject())
        return deepfa::num_txt(v.toObject());
    if (v.isDouble())
        return QString::number(v.toDouble(), 'g', 12);
    if (v.isBool())
        return v.toBool() ? QStringLiteral("true") : QStringLiteral("false");
    if (v.isArray()) {
        QStringList out;
        for (const QJsonValue& x : v.toArray())
            out << x.toString();
        return out.join(QStringLiteral(" | "));
    }
    return v.toString();
}

} // namespace

// ── Construction ─────────────────────────────────────────────────────────────

DeepFaPanel::DeepFaPanel(QWidget* parent) : EconPanelBase(QString(kSourceId), deepfa::css(deepfa::col(Role::Amber)), parent) {
    static int s_instances = 0;
    req_prefix_ = QStringLiteral("deepfa_%1_").arg(++s_instances);
    req_overview_ = req_prefix_ + QStringLiteral("overview");
    req_status_ = req_prefix_ + QStringLiteral("status");
    req_ticker_ = req_prefix_ + QStringLiteral("tk_");

    build_base_ui(this);
    set_stats_visible(false);
    build_pages();
    restyle_toolbar();

    // The base CSV button exports the generic results table, which this panel never fills —
    // point it at the triage rows currently shown instead.
    disconnect(export_btn_, &QPushButton::clicked, this, &DeepFaPanel::export_csv);
    connect(export_btn_, &QPushButton::clicked, this, &DeepFaPanel::export_visible_csv);
    export_btn_->setToolTip(tr("Xuất bảng triage đang lọc ra CSV"));
    export_btn_->setEnabled(false);

    connect(&services::EconomicsService::instance(), &services::EconomicsService::result_ready, this, &DeepFaPanel::on_result);

    refresh_timer_ = new QTimer(this);
    refresh_timer_->setInterval(kRefreshTickMs);
    connect(refresh_timer_, &QTimer::timeout, this, &DeepFaPanel::on_refresh_tick);
    refresh_timer_->start();

    show_empty(tr("Mở tab để nạp bàn triage DEEP FA…"));
}

void DeepFaPanel::build_controls(QHBoxLayout* thl) {
    ma_lbl_ = new QLabel(tr("MÃ"));
    ma_lbl_->setStyleSheet(ctrl_label_style());
    thl->addWidget(ma_lbl_);

    ma_edit_ = new QLineEdit;
    ma_edit_->setFixedHeight(26);
    ma_edit_->setFixedWidth(150);
    ma_edit_->setPlaceholderText(tr("Gõ mã… vd V"));
    ma_edit_->setAccessibleName(tr("Mã cổ phiếu"));
    ma_model_ = new QStringListModel(this);
    ma_completer_ = new QCompleter(ma_model_, this);
    ma_completer_->setCaseSensitivity(Qt::CaseInsensitive);
    ma_completer_->setFilterMode(Qt::MatchStartsWith);
    ma_completer_->setCompletionMode(QCompleter::PopupCompletion);
    ma_completer_->setMaxVisibleItems(12);
    ma_completer_->popup()->setMinimumWidth(320);
    ma_edit_->setCompleter(ma_completer_);
    connect(ma_edit_, &QLineEdit::textEdited, this, [this](const QString& t) {
        const QString up = t.toUpper();
        if (up != t) {
            const int pos = ma_edit_->cursorPosition();
            ma_edit_->setText(up);
            ma_edit_->setCursorPosition(pos);
        }
    });
    connect(ma_completer_, QOverload<const QString&>::of(&QCompleter::activated), this, [this](const QString& entry) {
        open_ticker(entry.section(QStringLiteral(" — "), 0, 0));
    });
    thl->addWidget(ma_edit_);

    back_btn_ = new QPushButton(tr("◀ TỔNG QUAN"));
    back_btn_->setFixedHeight(26);
    back_btn_->setCursor(Qt::PointingHandCursor);
    back_btn_->setEnabled(false);
    connect(back_btn_, &QPushButton::clicked, this, &DeepFaPanel::show_overview_page);
    thl->addWidget(back_btn_);

    thl->addSpacing(8);
    dm_combo_ = new QComboBox;
    dm_combo_->setFixedHeight(26);
    dm_combo_->addItem(tr("Tất cả"), QString());
    dm_combo_->addItem(tr("Danh mục + watch"), QStringLiteral("DM"));
    dm_combo_->addItem(QStringLiteral("NAV"), QStringLiteral("NAV"));
    dm_combo_->addItem(QStringLiteral("WATCH"), QStringLiteral("WATCH"));
    dm_combo_->addItem(QStringLiteral("AVOID"), QStringLiteral("AVOID"));
    connect(dm_combo_, &QComboBox::currentIndexChanged, this, [this](int) { apply_filters(); });
    thl->addWidget(dm_combo_);

    state_combo_ = new QComboBox;
    state_combo_->setFixedHeight(26);
    state_combo_->addItem(tr("State: tất cả"), QString());
    for (const char* s : {"A", "B", "C", "D"})
        state_combo_->addItem(QStringLiteral("State %1").arg(QLatin1String(s)), QLatin1String(s));
    connect(state_combo_, &QComboBox::currentIndexChanged, this, [this](int) { apply_filters(); });
    thl->addWidget(state_combo_);

    deep_chk_ = new QCheckBox(tr("deep"));
    regen_chk_ = new QCheckBox(tr("cần regen"));
    flag_chk_ = new QCheckBox(tr("có cờ"));
    for (QCheckBox* c : {deep_chk_, regen_chk_, flag_chk_}) {
        c->setStyleSheet(ctrl_label_style());
        connect(c, &QCheckBox::toggled, this, [this](bool) { apply_filters(); });
        thl->addWidget(c);
    }

    thl->addSpacing(10);
    fresh_lbl_ = new QLabel;
    fresh_lbl_->setTextFormat(Qt::PlainText);
    thl->addWidget(fresh_lbl_);

    web_btn_ = new QPushButton(tr("🌐 BẢN WEB"));
    web_btn_->setFixedHeight(26);
    web_btn_->setCursor(Qt::PointingHandCursor);
    web_btn_->setToolTip(tr("Mở báo cáo HTML HSC-grade trên hub localhost:9000/baocao/"));
    connect(web_btn_, &QPushButton::clicked, this, &DeepFaPanel::open_web_page);
    thl->addWidget(web_btn_);

    status_btn_ = new QPushButton(tr("TRẠNG THÁI"));
    status_btn_->setFixedHeight(26);
    status_btn_->setCursor(Qt::PointingHandCursor);
    status_btn_->setToolTip(tr("Bảng lớp dữ liệu / mốc / 🟢🟡🔴 + việc cần chạy (deepfa.py status)"));
    connect(status_btn_, &QPushButton::clicked, this, &DeepFaPanel::fetch_status);
    thl->addWidget(status_btn_);
}

void DeepFaPanel::build_pages() {
    // Overview page
    overview_page_ = new QWidget(this);
    overview_page_->setObjectName(QStringLiteral("deepfaOverview"));
    overview_page_->setAttribute(Qt::WA_StyledBackground, true);
    auto* vl = new QVBoxLayout(overview_page_);
    vl->setContentsMargins(14, 10, 14, 10);
    vl->setSpacing(8);
    cong_lbl_ = deepfa::make_label(overview_page_, deepfa::col(Role::Amber), 13, Qt::RichText, true);
    vl->addWidget(cong_lbl_);
    gates_lbl_ = deepfa::make_label(overview_page_, deepfa::col(Role::Ink2), 11, Qt::RichText);
    vl->addWidget(gates_lbl_);
    table_ = new deepfa::DeepFaUniverseTable(overview_page_);
    connect(table_, &deepfa::DeepFaUniverseTable::ticker_activated, this, &DeepFaPanel::open_ticker);
    connect(table_, &deepfa::DeepFaUniverseTable::count_changed, this, [this](int n) {
        if (count_lbl_)
            count_lbl_->setText(tr("%1 mã đang hiện · bấm mã hoặc Enter để mở trang nghiên cứu").arg(n));
    });
    vl->addWidget(table_, 1);
    count_lbl_ = deepfa::make_label(overview_page_, deepfa::col(Role::Muted), 11, Qt::PlainText);
    vl->addWidget(count_lbl_);
    page_overview_idx_ = add_content_page(overview_page_);

    // Ticker page
    ticker_scroll_ = new QScrollArea(this);
    ticker_scroll_->setWidgetResizable(true);
    ticker_scroll_->setFrameShape(QFrame::NoFrame);
    ticker_scroll_->setHorizontalScrollBarPolicy(Qt::ScrollBarAlwaysOff);
    ticker_scroll_->setVerticalScrollBarPolicy(Qt::ScrollBarAsNeeded);
    ticker_scroll_->setWidget(new QWidget);
    page_ticker_idx_ = add_content_page(ticker_scroll_);
}

// ── Fetch / results ──────────────────────────────────────────────────────────

void DeepFaPanel::activate() {
    if (fetching_)
        return;
    if (refresh_due())
        fetch_overview();
    else
        render_fresh();
}

bool DeepFaPanel::refresh_due() const {
    return !loaded_ || !fetched_at_.isValid() || fetched_at_.secsTo(QDateTime::currentDateTimeUtc()) >= kRefreshAfterSec;
}

void DeepFaPanel::on_refresh_tick() {
    if (!loaded_ || fetching_)
        return;
    if (isVisible() && refresh_due())
        fetch_overview();
    else
        render_fresh();
}

void DeepFaPanel::on_fetch() {
    // The base connects returnPressed of every toolbar QLineEdit here: Enter in MÃ opens that ticker.
    if (ma_edit_ && ma_edit_->hasFocus() && !ma_edit_->text().trimmed().isEmpty()) {
        open_ticker(ma_edit_->text());
        return;
    }
    fetch_overview();
}

void DeepFaPanel::fetch_overview() {
    fetching_ = true;
    if (!loaded_)
        show_loading(tr("Đang nạp bàn triage DEEP FA — 247 mã · memo · lớp tín hiệu · Vietcap IQ…"));
    else
        set_status(fresh_lbl_, tr("đang làm mới…"), deepfa::col(Role::Muted));
    if (fetch_btn_)
        fetch_btn_->setEnabled(false);
    services::EconomicsService::instance().execute(QString(kSourceId), QString(kScript), QStringLiteral("overview"), {}, req_overview_, /*force=*/true);
}

void DeepFaPanel::fetch_status() {
    services::EconomicsService::instance().execute(QString(kSourceId), QString(kScript), QStringLiteral("status"), {}, req_status_, /*force=*/true);
    set_status(fresh_lbl_, tr("đang đo đĩa…"), deepfa::col(Role::Muted));
}

void DeepFaPanel::open_ticker(const QString& ticker) {
    const QString tk = ticker.trimmed().toUpper();
    if (!ticker_re().match(tk).hasMatch()) {
        set_status(fresh_lbl_, tr("mã không hợp lệ: %1").arg(tk), deepfa::col(Role::Down));
        return;
    }
    if (ma_edit_)
        ma_edit_->setText(tk);
    pending_tk_ = tk;
    set_status(fresh_lbl_, tr("đang dựng trang %1…").arg(tk), deepfa::col(Role::Muted));
    services::EconomicsService::instance().execute(QString(kSourceId), QString(kScript), QStringLiteral("ticker"), QStringList{tk}, req_ticker_ + tk, /*force=*/true);
}

void DeepFaPanel::on_result(const QString& request_id, const services::EconomicsResult& result) {
    if (result.source_id != kSourceId || !request_id.startsWith(req_prefix_))
        return;
    QString err = result.success ? result.data.value(QLatin1String("error")).toString() : result.error;
    const bool ok = result.success && err.isEmpty();
    if (err.isEmpty() && !ok)
        err = tr("không rõ nguyên nhân");

    if (request_id == req_overview_) {
        fetching_ = false;
        if (ok) {
            fetched_at_ = QDateTime::currentDateTimeUtc();
            apply_overview(result.data);
            return;
        }
        LOG_WARN("DeepFaPanel", "Nạp overview DEEP FA lỗi: " + err);
        if (loaded_) {
            set_status(fresh_lbl_, tr("⚠ làm mới lỗi"), deepfa::col(Role::Down), err);
            if (fetch_btn_)
                fetch_btn_->setEnabled(true);
        } else {
            show_error(err.contains(QLatin1String("python3")) ? err : err + tr("\nChạy thử: python3 scripts/deepfa.py overview"));
        }
        return;
    }
    if (request_id == req_status_) {
        if (ok)
            show_status_dialog(result.data);
        else
            set_status(fresh_lbl_, tr("⚠ status lỗi"), deepfa::col(Role::Down), err);
        render_fresh();
        return;
    }
    if (request_id.startsWith(req_ticker_)) {
        const QString tk = request_id.mid(req_ticker_.size());
        if (tk != pending_tk_)
            return; // superseded by a newer request
        pending_tk_.clear();
        if (ok) {
            apply_ticker(tk, result.data);
        } else {
            LOG_WARN("DeepFaPanel", "Trang mã " + tk + " lỗi: " + err);
            set_status(fresh_lbl_, tr("⚠ trang %1 lỗi").arg(tk), deepfa::col(Role::Down), err);
        }
    }
}

void DeepFaPanel::apply_overview(const QJsonObject& data) {
    overview_ = data;
    loaded_ = true;
    const QJsonArray rows = overview_.value(QLatin1String("rows")).toArray();
    table_->set_rows(rows);
    if (ma_model_)
        ma_model_->setStringList(table_->completer_entries());
    apply_filters();
    render_overview_top();
    render_fresh();
    export_btn_->setEnabled(!rows.isEmpty());
    if (ticker_tk_.isEmpty())
        show_overview_page();
    else
        show_content_page(page_ticker_idx_);
    if (fetch_btn_)
        fetch_btn_->setEnabled(true);
    LOG_INFO("DeepFaPanel", QString("DEEP FA overview: %1 mã").arg(rows.size()));
}

void DeepFaPanel::apply_ticker(const QString& tk, const QJsonObject& data) {
    ticker_ = data;
    ticker_tk_ = tk;
    rebuild_ticker_page(/*keep_scroll=*/false);
    show_content_page(page_ticker_idx_);
    if (back_btn_)
        back_btn_->setEnabled(true);
    render_fresh();
    if (fetch_btn_)
        fetch_btn_->setEnabled(true);
}

void DeepFaPanel::show_overview_page() {
    ticker_tk_.clear();
    ticker_ = QJsonObject();
    if (back_btn_)
        back_btn_->setEnabled(false);
    if (loaded_)
        show_content_page(page_overview_idx_);
    render_fresh();
}

// ── Rendering ────────────────────────────────────────────────────────────────

void DeepFaPanel::render_overview_top() {
    const QJsonObject gates = overview_.value(QLatin1String("gates")).toObject();
    const bool dung = gates.value(QLatin1String("cong_dung")).toBool(true);
    const QString cong = deepfa::str(gates, "cong");
    cong_lbl_->setText(deepfa::span(deepfa::esc(cong.isEmpty() ? QStringLiteral("CỔNG: [CẦN DATA]") : cong), dung ? deepfa::col(Role::Amber) : deepfa::col(Role::Up), true));
    QStringList g;
    const QString fg = deepfa::str(gates, "fund_intent");
    // GATE-BLIND (stale) → Down · CHƯA LỌC (fresh universe export, no per-fund detail) → Amber · ok → Up
    const QColor fgc = fg == QLatin1String("GATE-BLIND") ? deepfa::col(Role::Down)
                       : (fg == QStringLiteral("CHƯA LỌC") ? deepfa::col(Role::Amber) : deepfa::col(Role::Up));
    g << deepfa::span(deepfa::esc(deepfa::str(gates, "fund_intent_txt")), fgc);
    g << deepfa::span(deepfa::esc(deepfa::str(gates, "ledger")), deepfa::col(Role::Ink2));
    const QJsonObject meta = overview_.value(QLatin1String("meta")).toObject();
    for (const QJsonValue& w : meta.value(QLatin1String("warnings")).toArray())
        g << deepfa::span(deepfa::esc(QStringLiteral("⚠ ") + w.toString()), deepfa::col(Role::Amber));
    gates_lbl_->setText(g.join(QStringLiteral(" &nbsp;·&nbsp; ")));
}

void DeepFaPanel::apply_filters() {
    if (!table_)
        return;
    deepfa::DeepFaUniverseTable::Filter f;
    f.dm = dm_combo_ ? dm_combo_->currentData().toString() : QString();
    f.state = state_combo_ ? state_combo_->currentData().toString() : QString();
    f.deep_only = deep_chk_ && deep_chk_->isChecked();
    f.regen_only = regen_chk_ && regen_chk_->isChecked();
    f.flagged_only = flag_chk_ && flag_chk_->isChecked();
    // search is via the MÃ completer (opens a page); the table itself shows every filtered row
    table_->apply(f);
}

void DeepFaPanel::render_fresh() {
    if (!fresh_lbl_)
        return;
    if (!loaded_) {
        set_status(fresh_lbl_, QString(), deepfa::col(Role::Muted));
        return;
    }
    const QJsonObject meta = overview_.value(QLatin1String("meta")).toObject();
    QString txt = tr("%1 mã").arg(meta.value(QLatin1String("n_rows")).toInt());
    if (!ticker_tk_.isEmpty())
        txt = tr("trang %1").arg(ticker_tk_);
    QDateTime at = QDateTime::fromString(meta.value(QLatin1String("generated")).toString(), Qt::ISODate);
    if (!at.isValid())
        at = fetched_at_;
    if (at.isValid())
        txt += tr(" · đo đĩa %1").arg(at.toLocalTime().toString(QStringLiteral("HH:mm")));
    const int nw = meta.value(QLatin1String("warnings")).toArray().size();
    if (nw > 0)
        set_status(fresh_lbl_, txt + tr(" · ⚠ %1 lớp cũ/thiếu").arg(nw), deepfa::col(Role::Amber));
    else
        set_status(fresh_lbl_, txt, deepfa::col(Role::Muted));
}

void DeepFaPanel::restyle_toolbar() {
    const QString btn = QStringLiteral("QPushButton { background:%1; color:%2; font-weight:bold; border-radius:4px; padding:0 8px; border:1px solid %3; }"
                                       "QPushButton:hover { background:%4; color:%5; } QPushButton:disabled { color:%6; }")
                            .arg(deepfa::css(deepfa::col(Role::Surface2)), deepfa::css(deepfa::col(Role::Ink2)), deepfa::css(deepfa::col(Role::Line)),
                                 deepfa::css(deepfa::col(Role::Amber)), deepfa::css(deepfa::col(Role::Bg)), deepfa::css(deepfa::col(Role::Muted)));
    for (QPushButton* b : {web_btn_, status_btn_, back_btn_})
        if (b)
            b->setStyleSheet(btn);
    if (overview_page_)
        overview_page_->setStyleSheet(QStringLiteral("QWidget#deepfaOverview { background:%1; }").arg(deepfa::css(deepfa::col(Role::Bg))));
    if (ticker_scroll_)
        ticker_scroll_->setStyleSheet(QStringLiteral("QScrollArea { background:%1; border:none; }").arg(deepfa::css(deepfa::col(Role::Bg))));
    render_fresh();
}

void DeepFaPanel::refresh_panel_theme() {
    EconPanelBase::refresh_panel_theme();
    restyle_toolbar();
    if (loaded_) {
        render_overview_top();
        apply_filters(); // the table re-reads theme colours when it rebuilds
    }
    if (!ticker_tk_.isEmpty())
        rebuild_ticker_page(/*keep_scroll=*/true);
}

void DeepFaPanel::retranslateUi() {
    if (ma_lbl_)
        ma_lbl_->setText(tr("MÃ"));
    if (back_btn_)
        back_btn_->setText(tr("◀ TỔNG QUAN"));
    if (web_btn_)
        web_btn_->setText(tr("🌐 BẢN WEB"));
    if (status_btn_)
        status_btn_->setText(tr("TRẠNG THÁI"));
    render_fresh();
    EconPanelBase::retranslateUi();
}

// ── Ticker page ──────────────────────────────────────────────────────────────

void DeepFaPanel::rebuild_ticker_page(bool keep_scroll) {
    if (!ticker_scroll_)
        return;
    const int pos = keep_scroll ? ticker_scroll_->verticalScrollBar()->value() : 0;
    QWidget* old = ticker_scroll_->takeWidget();
    ticker_scroll_->setWidget(build_ticker_page());
    if (old)
        old->deleteLater();
    if (pos > 0) {
        QPointer<QScrollArea> sa = ticker_scroll_;
        QTimer::singleShot(0, this, [sa, pos]() {
            if (sa)
                sa->verticalScrollBar()->setValue(pos);
        });
    } else {
        ticker_scroll_->verticalScrollBar()->setValue(0);
    }
}

QWidget* DeepFaPanel::build_ticker_page() {
    auto* page = new QWidget;
    page->setObjectName(QStringLiteral("deepfaContent"));
    page->setAttribute(Qt::WA_StyledBackground, true);
    page->setStyleSheet(QStringLiteral("QWidget#deepfaContent { background:%1; }").arg(deepfa::css(deepfa::col(Role::Bg))));
    auto* vl = new QVBoxLayout(page);
    vl->setContentsMargins(18, 12, 18, 24);
    vl->setSpacing(10);
    const QJsonObject& d = ticker_;
    const QJsonObject meta = d.value(QLatin1String("meta")).toObject();
    vl->addWidget(deepfa::build_cong(d.value(QLatin1String("cong")).toObject(), page));
    vl->addWidget(deepfa::build_header(meta, d.value(QLatin1String("header")).toObject(), page));
    vl->addWidget(deepfa::build_thesis(d.value(QLatin1String("thesis")).toObject(), page));
    vl->addWidget(deepfa::build_conditions(d.value(QLatin1String("dieu_kien")).toObject(), page));
    vl->addWidget(deepfa::build_tension(d.value(QLatin1String("tension")).toObject(), page));
    vl->addWidget(deepfa::build_chu_the(d.value(QLatin1String("chu_the")).toObject(), page));
    vl->addWidget(deepfa::build_dinh_gia(d.value(QLatin1String("dinh_gia")).toObject(), page));
    vl->addWidget(deepfa::build_filing(d.value(QLatin1String("filing")).toObject(), page));
    vl->addWidget(deepfa::build_codex(d.value(QLatin1String("codex")).toObject(), page));
    vl->addWidget(deepfa::build_kg(d.value(QLatin1String("kg")).toObject(), page));
    vl->addWidget(deepfa::build_ledger(d.value(QLatin1String("ledger")).toObject(), page));
    vl->addWidget(deepfa::build_phu_luc(d.value(QLatin1String("phu_luc")).toObject(), meta, page));
    vl->addStretch(1);
    return page;
}

// ── Actions ──────────────────────────────────────────────────────────────────

void DeepFaPanel::open_web_page() {
    QString url;
    if (!ticker_tk_.isEmpty())
        url = deepfa::str(ticker_.value(QLatin1String("meta")).toObject(), "web_url");
    if (url.isEmpty())
        url = deepfa::str(overview_.value(QLatin1String("meta")).toObject(), "web_index");
    if (url.isEmpty())
        url = QStringLiteral("http://localhost:9000/baocao/index.html");
    const QUrl u(url);
    if (u.isValid() && (u.scheme() == QLatin1String("http") || u.scheme() == QLatin1String("https")))
        QDesktopServices::openUrl(u);
}

void DeepFaPanel::export_visible_csv() {
    if (!loaded_ || !table_)
        return;
    const QJsonArray rows = table_->visible_rows();
    if (rows.isEmpty())
        return;
    const QString suggested = QDir::homePath() + QStringLiteral("/Downloads/deepfa_triage_%1.csv").arg(QDate::currentDate().toString("yyyyMMdd"));
    const QString path = QFileDialog::getSaveFileName(this, tr("Xuất CSV"), suggested, tr("CSV (*.csv)"));
    if (path.isEmpty())
        return;
    QFile file(path);
    if (!file.open(QIODevice::WriteOnly | QIODevice::Truncate)) {
        QMessageBox::warning(this, tr("Xuất CSV"), tr("Không ghi được tệp:\n%1\n%2").arg(path, file.errorString()));
        return;
    }
    file.write("\xEF\xBB\xBF");
    QTextStream out(&file);
    out.setEncoding(QStringConverter::Utf8);
    const QStringList cols = {"tk", "ten", "nhom", "dm", "nav_pct", "state", "memo_date", "memo_age_days", "memo_status", "deep", "engine", "can_regen", "can_regen_ly_do",
                              "gia", "delta_pct", "pe", "pb", "sigma_pe", "zone_pe", "edi", "edi_stage", "bld_tone", "align", "street_up", "street_down",
                              "tp", "tp_upside_pct", "tp_stale", "rating", "fund_gate", "fund_label", "foreign_net_20", "prop_net_20", "n_filings", "worksheet_engine", "flags"};
    out << cols.join(QLatin1Char(',')) << "\n";
    for (const QJsonValue& rv : rows) {
        const QJsonObject r = rv.toObject();
        QStringList cells;
        for (const QString& c : cols)
            cells << csv_quote(cell_txt(r, c.toUtf8().constData()));
        out << cells.join(QLatin1Char(',')) << "\n";
    }
    out.flush();
    LOG_INFO("DeepFaPanel", QString("Xuất %1 dòng triage DEEP FA → %2").arg(rows.size()).arg(path));
}

void DeepFaPanel::show_status_dialog(const QJsonObject& st) {
    if (!status_dlg_) {
        status_dlg_ = new QDialog(this);
        status_dlg_->setWindowTitle(tr("DEEP FA — trạng thái dữ liệu (đo đĩa)"));
        status_dlg_->resize(980, 680);
        auto* vl = new QVBoxLayout(status_dlg_);
        auto* tb = new QTextBrowser(status_dlg_);
        tb->setObjectName(QStringLiteral("deepfaStatusText"));
        tb->setOpenExternalLinks(false);
        vl->addWidget(tb);
    }
    auto* tb = status_dlg_->findChild<QTextBrowser*>(QStringLiteral("deepfaStatusText"));
    if (!tb)
        return;
    QString html = QStringLiteral("<body style=\"color:%1; background:%2; font-size:12px;\">").arg(deepfa::css(deepfa::col(Role::Ink)), deepfa::css(deepfa::col(Role::Bg)));
    const QJsonObject meta = st.value(QLatin1String("meta")).toObject();
    html += QStringLiteral("<p><b>Đo đĩa %1</b> · vault %2</p>").arg(deepfa::esc(deepfa::str(meta, "generated")), deepfa::esc(deepfa::str(meta, "vault")));
    const QJsonObject gates = st.value(QLatin1String("gates")).toObject();
    html += QStringLiteral("<p>%1<br>%2<br>%3</p>").arg(deepfa::esc(deepfa::str(gates, "cong")), deepfa::esc(deepfa::str(gates, "fund_intent_txt")), deepfa::esc(deepfa::str(gates, "ledger")));
    // fund-level flows (status.fund_flows): the only surface possible without per-fund detail — top redemptions / inflows 1M
    const QJsonObject ff = st.value(QLatin1String("fund_flows")).toObject();
    if (!ff.isEmpty()) {
        auto list = [](const QJsonArray& arr) {
            QStringList o;
            for (const QJsonValue& v : arr) {
                const QJsonObject r = v.toObject();
                o << deepfa::esc(QStringLiteral("%1 %2 tỷ").arg(deepfa::str(r, "quy"), deepfa::str(r.value(QLatin1String("flow_1m")).toObject(), "txt")));
            }
            return o.join(QStringLiteral(" · "));
        };
        html += QStringLiteral("<p><b>Dòng tiền quỹ 1M</b> (%1 · %2/%3 quỹ có NAV ≤45 ngày · %4)<br>rút: %5<br>vào: %6<br><span style=\"color:%7\">%8</span></p>")
                    .arg(deepfa::esc(deepfa::str(ff, "as_of")), QString::number(ff.value(QLatin1String("n_usable")).toInt()),
                         QString::number(ff.value(QLatin1String("n_funds")).toInt()), deepfa::esc(deepfa::str(ff, "b")),
                         list(ff.value(QLatin1String("top_redemptions_1m")).toArray()), list(ff.value(QLatin1String("top_inflows_1m")).toArray()),
                         deepfa::css(deepfa::col(Role::Muted)), deepfa::esc(deepfa::str(ff, "caveat")));
    }
    html += QStringLiteral("<table cellpadding=\"4\"><tr><th align=\"left\">Lớp</th><th>Mốc</th><th>Tuổi</th><th>Bậc→hiệu lực</th><th>Trạng thái</th></tr>");
    for (const QJsonValue& v : st.value(QLatin1String("layers")).toArray()) {
        const QJsonObject l = v.toObject();
        html += QStringLiteral("<tr><td>%1 %2</td><td>%3</td><td>%4</td><td>%5 → %6</td><td style=\"color:%7\">%8</td></tr>")
                    .arg(deepfa::esc(deepfa::str(l, "light")), deepfa::esc(deepfa::str(l, "label")), deepfa::esc(deepfa::str(l, "as_of_txt")), deepfa::esc(deepfa::str(l, "age_txt")),
                         deepfa::esc(deepfa::str(l, "tier")), deepfa::esc(deepfa::str(l, "tier_hieu_luc")), deepfa::css(deepfa::status_color(deepfa::str(l, "status"))), deepfa::esc(deepfa::str(l, "status")));
    }
    html += QStringLiteral("</table>");
    const QJsonObject counts = st.value(QLatin1String("counts")).toObject();
    QStringList cs;
    for (const QString& k : counts.keys())
        cs << deepfa::esc(QStringLiteral("%1 %2").arg(k, QString::number(counts.value(k).toDouble(), 'f', 0)));
    html += QStringLiteral("<p><b>Đếm:</b> %1</p>").arg(cs.join(QStringLiteral(" · ")));
    QStringList md;
    for (const QJsonValue& v : st.value(QLatin1String("memo_dates")).toArray()) {
        const QJsonObject m = v.toObject();
        md << deepfa::esc(QStringLiteral("%1 (%2)").arg(deepfa::str(m, "date"), QString::number(m.value(QLatin1String("n")).toInt())));
    }
    html += QStringLiteral("<p><b>Memo theo ngày:</b> %1</p>").arg(md.join(QStringLiteral(" · ")));
    html += QStringLiteral("<p><b>Việc cần chạy</b></p><ol>");
    for (const QJsonValue& v : st.value(QLatin1String("actions")).toArray()) {
        const QJsonObject a = v.toObject();
        const QString muc = deepfa::str(a, "muc");
        const QColor c = muc == QLatin1String("chan") ? deepfa::col(Role::Down) : (muc == QLatin1String("nen") ? deepfa::col(Role::Amber) : deepfa::col(Role::Muted));
        html += QStringLiteral("<li><span style=\"color:%1\"><b>[%2]</b></span> %3<br><code>%4</code><br><span style=\"color:%5\">%6</span></li>")
                    .arg(deepfa::css(c), deepfa::esc(muc), deepfa::esc(deepfa::str(a, "viec")), deepfa::esc(deepfa::str(a, "lenh")), deepfa::css(deepfa::col(Role::Muted)), deepfa::esc(deepfa::str(a, "ly_do")));
    }
    html += QStringLiteral("</ol></body>");
    tb->setHtml(html);
    status_dlg_->show();
    status_dlg_->raise();
}

} // namespace fincept::screens
