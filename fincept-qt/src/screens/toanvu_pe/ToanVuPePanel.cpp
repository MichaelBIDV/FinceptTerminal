// src/screens/toanvu_pe/ToanVuPePanel.cpp
// P/E×LS TV: fetch lifecycle, ticker box, toolbar and the one scrollable content page. scripts/toanvu_pe.py
// shapes every page as a vnblocks/1 "trang" (CỔNG · phương pháp luận · nội dung) with every number
// pre-formatted and tiered; vnblocks::build_page() lays it out. This file only adds the meta line and the
// ticker selector. All data strings are HTML-escaped before they reach a rich-text QLabel. Private helpers
// carry a "tvpe_" prefix (unity-build safety).
#include "screens/toanvu_pe/ToanVuPePanel.h"

#include "core/logging/Logger.h"
#include "screens/sgi_fa/SgiCommon.h"
#include "screens/vnblocks/VnBlocks.h"
#include "services/economics/EconomicsService.h"

#include <QAbstractItemView>
#include <QCompleter>
#include <QDate>
#include <QDir>
#include <QFile>
#include <QFileDialog>
#include <QFrame>
#include <QHBoxLayout>
#include <QKeyEvent>
#include <QLabel>
#include <QLineEdit>
#include <QMessageBox>
#include <QPointer>
#include <QPushButton>
#include <QRegularExpression>
#include <QScrollArea>
#include <QScrollBar>
#include <QStandardItemModel>
#include <QStringList>
#include <QTextStream>
#include <QTimer>
#include <QValidator>
#include <QVBoxLayout>

#include <algorithm>
#include <functional>
#include <utility>

namespace fincept::screens {

namespace {

using sgi::Role;

constexpr QLatin1StringView kTvpeSourceId{"toanvu_pe"};
constexpr QLatin1StringView kTvpeScript{"toanvu_pe.py"};
constexpr int kTvpeRefreshAfterSec = 30 * 60; ///< data is rebuilt offline; 30' only catches the live price tile
constexpr int kTvpeMaRole = Qt::UserRole + 1;
constexpr int kTvpeTenMax = 40;
constexpr int kTvpePopupRows = 14;
constexpr int kTvpePopupMinW = 340;
/// Request ids cycle through this many values: EconomicsService keeps a dispatch record and publishes each
/// payload (~150 KB) to its own DataHub topic per id, held for hours; a never-reused id would pin one per fetch.
constexpr int kTvpeSeqRing = 8;

QString tvpe_fmt_date(const QString& iso) {
    const QDate d = QDate::fromString(iso.left(10), Qt::ISODate);
    return d.isValid() ? d.toString(QStringLiteral("dd/MM/yyyy")) : iso;
}

void tvpe_set_status(QLabel* label, const QString& text, const QColor& color, const QString& tooltip = {}) {
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

/// 1–10 ASCII letters/digits (used as CLI argument and request id).
bool tvpe_valid_ticker(const QString& s) {
    if (s.isEmpty() || s.size() > 10)
        return false;
    for (const QChar c : s)
        if (c.unicode() >= 128 || !c.isLetterOrNumber())
            return false;
    return true;
}

/// "vcb · Vietcombank" → "VCB".
QString tvpe_first_token(const QString& text) {
    QString t = text.trimmed().toUpper();
    const int cut = static_cast<int>(t.indexOf(QRegularExpression(QStringLiteral("[\\s\\x{00B7}]"))));
    if (cut >= 0)
        t.truncate(cut);
    return t;
}

/// Upper-cases while typing; validity is checked on Enter.
class TvpeUpperValidator : public QValidator {
  public:
    using QValidator::QValidator;
    State validate(QString& input, int& /*pos*/) const override {
        input = input.toUpper();
        return Acceptable;
    }
};

/// The completer swallows Enter when the popup is open with no row selected; this filter still opens the
/// typed code. With a row selected, QCompleter emits activated as usual.
class TvpePopupEnter : public QObject {
  public:
    TvpePopupEnter(QAbstractItemView* popup, std::function<void()> on_enter, QObject* parent)
        : QObject(parent), popup_(popup), on_enter_(std::move(on_enter)) {}
    bool eventFilter(QObject* obj, QEvent* e) override {
        if (e->type() == QEvent::KeyPress) {
            const int k = static_cast<QKeyEvent*>(e)->key();
            if ((k == Qt::Key_Return || k == Qt::Key_Enter) && !popup_->currentIndex().isValid())
                on_enter_();
        }
        return QObject::eventFilter(obj, e);
    }

  private:
    QAbstractItemView* popup_;
    std::function<void()> on_enter_;
};

QString tvpe_csv_quote(QString v) {
    if (v.contains(QLatin1Char(',')) || v.contains(QLatin1Char('"')) || v.contains(QLatin1Char('\n')) ||
        v.contains(QLatin1Char('\r')))
        v = QStringLiteral("\"") + v.replace(QStringLiteral("\""), QStringLiteral("\"\"")) + QStringLiteral("\"");
    return v;
}

QString tvpe_csv_cell(const QJsonValue& v) {
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

QStringList tvpe_warnings(const QJsonObject& meta) {
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

ToanVuPePanel::ToanVuPePanel(QWidget* parent)
    : EconPanelBase(QString(kTvpeSourceId), sgi::css(sgi::col(Role::Amber)), parent) {
    static int s_instances = 0;
    req_prefix_ = QStringLiteral("tvpe_%1_").arg(++s_instances);

    build_base_ui(this);
    set_stats_visible(false);
    // build_base_ui wires Enter in every toolbar QLineEdit to on_fetch; the MÃ box has its own Enter handling
    // (on_ma_entered), so drop every returnPressed → this connection (the base one cannot be named: on_fetch is
    // protected in EconPanelBase) and re-attach only ours. Otherwise one Enter starts two fetches.
    disconnect(ma_edit_, &QLineEdit::returnPressed, this, nullptr);
    connect(ma_edit_, &QLineEdit::returnPressed, this, [this]() { on_ma_entered(ma_edit_->text()); });

    scroll_ = new QScrollArea(this);
    scroll_->setWidgetResizable(true);
    scroll_->setFrameShape(QFrame::NoFrame);
    scroll_->setHorizontalScrollBarPolicy(Qt::ScrollBarAsNeeded);
    scroll_->setVerticalScrollBarPolicy(Qt::ScrollBarAsNeeded);
    scroll_->setWidget(new QWidget);
    page_idx_ = add_content_page(scroll_);
    restyle_toolbar();

    disconnect(export_btn_, &QPushButton::clicked, this, &ToanVuPePanel::export_csv);
    connect(export_btn_, &QPushButton::clicked, this, &ToanVuPePanel::export_payload_csv);
    export_btn_->setToolTip(tr("Xuất trạng thái luật Toàn Vũ của đủ 405 mã ra CSV"));
    export_btn_->setEnabled(false);

    connect(&services::EconomicsService::instance(), &services::EconomicsService::result_ready, this,
            &ToanVuPePanel::on_result);

    show_empty(tr("Mở tab để nạp Vùng P/E × Lãi suất (Toàn Vũ)…"));
}

void ToanVuPePanel::build_controls(QHBoxLayout* thl) {
    auto* lbl = new QLabel(tr("MÃ"));
    lbl->setStyleSheet(QStringLiteral("QLabel { color:%1; font-size:10px; font-weight:bold; background:transparent; }")
                           .arg(sgi::css(sgi::col(Role::Muted))));
    thl->addWidget(lbl);

    ma_edit_ = new QLineEdit;
    ma_edit_->setFixedHeight(26);
    ma_edit_->setFixedWidth(110);
    ma_edit_->setPlaceholderText(tr("gõ mã…"));
    ma_edit_->setValidator(new TvpeUpperValidator(ma_edit_));
    ma_model_ = new QStandardItemModel(this);
    ma_completer_ = new QCompleter(ma_model_, this);
    ma_completer_->setCompletionRole(kTvpeMaRole);
    ma_completer_->setCaseSensitivity(Qt::CaseInsensitive);
    ma_completer_->setFilterMode(Qt::MatchStartsWith);
    ma_completer_->setCompletionMode(QCompleter::PopupCompletion);
    ma_completer_->setMaxVisibleItems(kTvpePopupRows);
    ma_completer_->popup()->setMinimumWidth(kTvpePopupMinW);
    ma_edit_->setCompleter(ma_completer_);
    ma_completer_->popup()->installEventFilter(
        new TvpePopupEnter(ma_completer_->popup(), [this]() { on_ma_entered(ma_edit_->text()); }, ma_completer_));
    connect(ma_completer_, QOverload<const QString&>::of(&QCompleter::activated), this,
            &ToanVuPePanel::on_ma_entered);
    connect(ma_edit_, &QLineEdit::textEdited, this, [this]() {
        if (ma_invalid_) {
            ma_invalid_ = false;
            update_ma_style();
        }
    });
    thl->addWidget(ma_edit_);

    overview_btn_ = new QPushButton(tr("TỔNG QUAN"));
    overview_btn_->setFixedHeight(26);
    overview_btn_->setCursor(Qt::PointingHandCursor);
    overview_btn_->setToolTip(tr("Về trang tổng: phương pháp luận Toàn Vũ, kiểm định của Hội đồng và bảng tra"));
    connect(overview_btn_, &QPushButton::clicked, this, &ToanVuPePanel::open_overview);
    thl->addWidget(overview_btn_);

    for (const char* code : {"VNINDEX", "VN30", "VN100", "VN200", "REST"}) {
        const QString c = QString::fromLatin1(code);
        auto* b = new QPushButton(c);
        b->setFixedHeight(26);
        b->setCursor(Qt::PointingHandCursor);
        const QString what = c == QLatin1String("VN200")  ? tr("top 200 vốn hoá HOSE+HNX (phần có trong tệp Bloomberg)")
                             : c == QLatin1String("REST") ? tr("mọi mã của tệp Bloomberg nằm ngoài VN200")
                                                          : c;
        b->setToolTip(tr("Trang rổ %1: P/E × LS × ERP của rổ, xếp hạng tín hiệu từng mã, định giá HHP, lãi suất, "
                         "bảng tổng hợp bằng chứng").arg(what));
        connect(b, &QPushButton::clicked, this, [this, c]() { on_ma_entered(c); });
        thl->addWidget(b);
        scope_btns_.append(b);
    }

    fresh_lbl_ = new QLabel;
    fresh_lbl_->setTextFormat(Qt::PlainText);
    thl->addWidget(fresh_lbl_);
    update_ma_style();
}

// ── Fetch / results ──────────────────────────────────────────────────────────

void ToanVuPePanel::activate() {
    if (fetching_)
        return;
    if (!loaded_ || !fetched_at_.isValid() ||
        fetched_at_.secsTo(QDateTime::currentDateTimeUtc()) >= kTvpeRefreshAfterSec)
        on_fetch();
    else
        render_fresh();
}

void ToanVuPePanel::on_ma_entered(const QString& text) {
    const QString t = tvpe_first_token(text);
    if (t.isEmpty())
        return;
    const bool known = ds_ma_.isEmpty() ? tvpe_valid_ticker(t) : ds_ma_.contains(t);
    ma_invalid_ = !known;
    update_ma_style();
    if (!known)
        return;
    // Choosing a popup row with Enter fires both activated and returnPressed: ignore the second one.
    if (fetching_ && ma_ == t)
        return;
    ma_ = t;
    ma_edit_->setText(t);
    on_fetch();
}

void ToanVuPePanel::open_overview() {
    if (fetching_ && ma_.isEmpty())
        return;
    ma_.clear();
    if (ma_edit_)
        ma_edit_->clear();
    on_fetch();
}

void ToanVuPePanel::on_fetch() {
    fetching_ = true;
    req_seq_ = req_seq_ % kTvpeSeqRing + 1;
    req_current_ = req_prefix_ + QString::number(req_seq_);
    if (!loaded_) {
        show_loading(tr("Đang nạp Vùng P/E × Lãi suất · luật Toàn Vũ · kiểm định…"));
    } else {
        tvpe_set_status(fresh_lbl_, tr("đang nạp…"), sgi::col(Role::Muted));
        if (fetch_btn_)
            fetch_btn_->setEnabled(false);
    }
    QStringList args;
    QString cmd = QStringLiteral("overview");
    if (!ma_.isEmpty()) {
        cmd = QStringLiteral("ma");
        args << QStringLiteral("--ma") << ma_;
    }
    services::EconomicsService::instance().execute(QString(kTvpeSourceId), QString(kTvpeScript), cmd, args,
                                                   req_current_, /*force=*/true);
}

void ToanVuPePanel::on_result(const QString& request_id, const services::EconomicsResult& result) {
    if (result.source_id != kTvpeSourceId || !request_id.startsWith(req_prefix_) || request_id != req_current_)
        return;
    fetching_ = false;
    if (fetch_btn_)
        fetch_btn_->setEnabled(true);

    QString err = result.success ? result.data.value("error").toString() : result.error;
    if (result.success && err.isEmpty()) {
        fetched_at_ = QDateTime::currentDateTimeUtc();
        apply_payload(result.data);
        return;
    }
    if (err.isEmpty())
        err = tr("không rõ nguyên nhân");
    LOG_WARN("ToanVuPePanel", "Nạp lỗi: " + err);

    if (loaded_) {
        tvpe_set_status(fresh_lbl_, tr("⚠ nạp lỗi"), sgi::col(Role::Down), err);
        ma_ = shown_ma_; // the page on screen stays; the next refresh asks for it again
        if (ma_edit_)
            ma_edit_->setText(shown_ma_); // keep the box naming the ticker whose numbers are on screen
    } else {
        const QString failed = ma_;
        // Nothing loaded yet: fall back to the overview on the next activate/FETCH instead of repeating a bad ticker.
        ma_.clear();
        if (ma_edit_)
            ma_edit_->clear();
        const QString cmd = failed.isEmpty() ? QStringLiteral("overview") : QStringLiteral("ma --ma ") + failed;
        show_error(err.contains(QLatin1String("python3")) ? err
                                                          : err + tr("\nChạy thử: python3 scripts/toanvu_pe.py %1").arg(cmd));
    }
}

void ToanVuPePanel::apply_payload(const QJsonObject& data) {
    const QJsonObject meta = data.value("meta").toObject();
    const QString new_ma = meta.value("ma").toString();
    const bool same_page = loaded_ && new_ma == shown_ma_;
    data_ = data;
    shown_ma_ = new_ma;
    loaded_ = true;

    fill_tickers(meta.value("ds_ma").toArray());
    render_fresh();
    const QJsonObject csv = data_.value("csv").toObject();
    export_btn_->setEnabled(!csv.value("columns").toArray().isEmpty() && !csv.value("rows").toArray().isEmpty());

    const QJsonArray sections = data_.value("trang").toObject().value("sections").toArray();
    if (sections.isEmpty()) {
        QString msg = tr("[CẦN DATA] Trang không có mục nào để hiển thị.");
        const QStringList warns = tvpe_warnings(meta);
        if (!warns.isEmpty())
            msg += QStringLiteral("\n⚠ ") + warns.join(QStringLiteral("\n⚠ "));
        show_empty(msg);
    } else {
        rebuild_page(/*keep_scroll=*/same_page);
        show_content_page(page_idx_);
    }
    LOG_INFO("ToanVuPePanel", QString("P/E×LS TV: %1 · %2 mục")
                                  .arg(new_ma.isEmpty() ? QStringLiteral("tổng quan") : new_ma)
                                  .arg(sections.size()));
}

void ToanVuPePanel::fill_tickers(const QJsonArray& ds_ma) {
    if (!ma_model_)
        return;
    QVector<std::pair<QString, QString>> items; // (mã, tên)
    QSet<QString> codes;
    for (const auto& v : ds_ma) {
        const QJsonObject o = v.toObject();
        const QString m = o.value(QStringLiteral("ma")).toString().trimmed().toUpper();
        if (tvpe_valid_ticker(m) && !codes.contains(m)) {
            codes.insert(m);
            items.append({m, o.value(QStringLiteral("ten")).toString().simplified()});
        }
    }
    if (items.isEmpty())
        return;
    ds_ma_ = codes;
    std::sort(items.begin(), items.end());
    bool same = ma_model_->rowCount() == items.size();
    for (int r = 0; same && r < items.size(); ++r)
        same = ma_model_->item(r)->data(kTvpeMaRole).toString() == items[r].first;
    if (same)
        return; // unchanged → keep the model (the popup may be open)
    ma_model_->clear();
    for (const auto& [m, ten] : std::as_const(items)) {
        const QString t = ten.size() > kTvpeTenMax ? ten.left(kTvpeTenMax - 1) + QChar(0x2026) : ten;
        auto* it = new QStandardItem(t.isEmpty() ? m : m + QStringLiteral(" · ") + t);
        it->setData(m, kTvpeMaRole);
        it->setEditable(false);
        ma_model_->appendRow(it);
    }
}

// ── Toolbar ──────────────────────────────────────────────────────────────────

void ToanVuPePanel::render_fresh() {
    if (!fresh_lbl_)
        return;
    if (!loaded_) {
        tvpe_set_status(fresh_lbl_, QString(), sgi::col(Role::Muted));
        return;
    }
    const QJsonObject meta = data_.value("meta").toObject();
    const QString to = meta.value("data_to").toString();
    QString txt = to.isEmpty() ? tr("dữ liệu [CẦN DATA]") : tr("Bloomberg tới %1").arg(tvpe_fmt_date(to));
    const double ls = meta.value("ls").toDouble(-1.0);
    if (ls >= 0.0)
        txt += tr(" · LS %1% → ngưỡng P%2")
                   .arg(QString::number(ls, 'f', 2).replace(QLatin1Char('.'), QLatin1Char(',')),
                        QString::number(meta.value("nguong").toDouble(), 'f', 1).replace(QLatin1Char('.'), QLatin1Char(',')));
    QDateTime at = QDateTime::fromString(meta.value("generated").toString(), QStringLiteral("yyyy-MM-dd HH:mm"));
    if (!at.isValid())
        at = fetched_at_.toLocalTime();
    if (at.isValid())
        txt += tr(" · nạp %1").arg(at.toString(QStringLiteral("HH:mm")));
    if (meta.value("stale").toBool()) {
        const QString stale = meta.value("stale_text").toString().trimmed();
        tvpe_set_status(fresh_lbl_, txt + QStringLiteral(" · ⚠ ") + stale, sgi::col(Role::Down), stale);
    } else {
        tvpe_set_status(fresh_lbl_, txt, sgi::col(Role::Muted));
    }
}

void ToanVuPePanel::update_ma_style() {
    if (!ma_edit_)
        return;
    const QColor edge = ma_invalid_ ? sgi::col(Role::Down) : sgi::col(Role::Line);
    ma_edit_->setStyleSheet(QStringLiteral("QLineEdit { background:%1; color:%2; border:1px solid %3; border-radius:4px;"
                                           " font-size:11px; font-weight:700; padding:0 6px; }"
                                           "QLineEdit:focus { border-color:%4; }")
                                .arg(sgi::css(sgi::col(Role::Surface2)), sgi::css(sgi::col(Role::Ink)), sgi::css(edge),
                                     sgi::css(ma_invalid_ ? sgi::col(Role::Down) : sgi::col(Role::Amber))));
    ma_edit_->setToolTip(ma_invalid_ ? tr("Mã không có trong bộ Bloomberg của Toàn Vũ (405 mã VNINDEX)")
                                     : tr("Gõ mã (vd V → các mã bắt đầu bằng V) rồi Enter để mở trang của mã"));
    if (ma_completer_ && ma_completer_->popup())
        ma_completer_->popup()->setStyleSheet(
            QStringLiteral("QAbstractItemView { background:%1; color:%2; border:1px solid %3; font-size:11px; outline:0; }"
                           "QAbstractItemView::item { padding:3px 6px; }"
                           "QAbstractItemView::item:selected { background:%4; color:%5; }")
                .arg(sgi::css(sgi::col(Role::Surface2)), sgi::css(sgi::col(Role::Ink)), sgi::css(sgi::col(Role::Line)),
                     sgi::css(sgi::col(Role::Amber)), sgi::css(sgi::col(Role::Bg))));
}

void ToanVuPePanel::restyle_toolbar() {
    const QString btn_css = QStringLiteral("QPushButton { background:%1; color:%2; font-weight:bold;"
                                           " border-radius:4px; padding:0 8px; border:1px solid %3; }"
                                           "QPushButton:hover { background:%4; color:%5; }"
                                           "QPushButton:disabled { color:%6; }")
                                .arg(sgi::css(sgi::col(Role::Surface2)), sgi::css(sgi::col(Role::Ink2)),
                                     sgi::css(sgi::col(Role::Line)), sgi::css(sgi::col(Role::Amber)),
                                     sgi::css(sgi::col(Role::Bg)), sgi::css(sgi::col(Role::Muted)));
    if (overview_btn_)
        overview_btn_->setStyleSheet(btn_css);
    for (QPushButton* b : std::as_const(scope_btns_))
        b->setStyleSheet(btn_css);
    update_ma_style();
    if (scroll_)
        scroll_->setStyleSheet(
            QStringLiteral("QScrollArea { background:%1; border:none; }").arg(sgi::css(sgi::col(Role::Bg))));
    render_fresh();
}

void ToanVuPePanel::refresh_panel_theme() {
    EconPanelBase::refresh_panel_theme();
    restyle_toolbar();
    if (loaded_)
        rebuild_page(/*keep_scroll=*/true);
}

// ── Content page ─────────────────────────────────────────────────────────────

void ToanVuPePanel::rebuild_page(bool keep_scroll) {
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

QWidget* ToanVuPePanel::build_page() {
    const QJsonObject meta = data_.value("meta").toObject();

    auto* page = new QWidget;
    page->setObjectName("toanVuPeContent");
    page->setAttribute(Qt::WA_StyledBackground, true);
    page->setStyleSheet(
        QStringLiteral("QWidget#toanVuPeContent { background:%1; }").arg(sgi::css(sgi::col(Role::Bg))));
    auto* vl = new QVBoxLayout(page);
    vl->setContentsMargins(18, 14, 18, 24);
    vl->setSpacing(10);

    {
        QStringList parts;
        const QString ma = meta.value("ma").toString();
        parts << (ma.isEmpty() ? sgi::span(sgi::esc(tr("Tổng quan 405 mã")), sgi::col(Role::Amber), true)
                               : sgi::span(sgi::esc(ma), sgi::col(Role::Amber), true));
        parts << sgi::esc(tr("luật Toàn Vũ SS-T3 · Bloomberg/FiinProX FACT-T2 · tái lập & kiểm định EST"));
        const QString build = meta.value("build").toString();
        if (!build.isEmpty())
            parts << sgi::esc(tr("dựng %1").arg(build));
        if (meta.value("stale").toBool())
            parts << sgi::span(sgi::esc(meta.value("stale_text").toString()), sgi::col(Role::Down), true);
        auto* meta_lbl = sgi::make_label(page, sgi::col(Role::Muted), 12, Qt::RichText);
        meta_lbl->setText(parts.join(QStringLiteral(" · ")));
        vl->addWidget(meta_lbl);
    }

    const QStringList warns = tvpe_warnings(meta);
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

void ToanVuPePanel::export_payload_csv() {
    if (!loaded_)
        return;
    const QJsonObject csv = data_.value("csv").toObject();
    const QJsonArray columns = csv.value("columns").toArray();
    const QJsonArray rows = csv.value("rows").toArray();
    if (columns.isEmpty() || rows.isEmpty())
        return;

    QString to = data_.value("meta").toObject().value("data_to").toString();
    to.remove(QLatin1Char('-'));
    const QString suggested = QDir::homePath() + QStringLiteral("/Downloads/toanvu_pe_%1.csv")
                                                     .arg(to.isEmpty() ? QStringLiteral("khong_ngay") : to);
    const QString path = QFileDialog::getSaveFileName(this, tr("Xuất CSV"), suggested, tr("CSV (*.csv)"));
    if (path.isEmpty())
        return;

    QFile file(path);
    if (!file.open(QIODevice::WriteOnly | QIODevice::Truncate)) {
        LOG_WARN("ToanVuPePanel", "Không ghi được CSV " + path + ": " + file.errorString());
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
            quoted << tvpe_csv_quote(i < cells.size() ? tvpe_csv_cell(cells.at(i)) : QString());
        out << quoted.join(QLatin1Char(',')) << "\n";
    };
    const qsizetype width = columns.size();
    write_row(columns, width);
    for (const QJsonValue& rv : rows)
        write_row(rv.toArray(), std::max(width, rv.toArray().size()));
    out.flush();
    LOG_INFO("ToanVuPePanel", QString("Xuất %1 mã → %2").arg(rows.size()).arg(path));
}

} // namespace fincept::screens
