// src/screens/all_in_one/AllInOnePanel.cpp
// ALL-IN-ONE: fetch lifecycle, toolbar, ticker board (chips) and the bento grid of tiles. scripts/all_in_one.py
// shapes every tile (vnblocks/1 blocks, numbers pre-formatted and tiered); this file only lays them out.
// All data strings are HTML-escaped before they reach a rich-text QLabel. Private helpers carry an "aio_"
// prefix (unity-build safety).
#include "screens/all_in_one/AllInOnePanel.h"

#include "core/events/EventBus.h"
#include "core/logging/Logger.h"
#include "screens/sgi_fa/SgiCommon.h"
#include "screens/vnblocks/VnBlocks.h"
#include "screens/vnblocks/VnNavHint.h"
#include "services/economics/EconomicsService.h"

#include <QAbstractItemView>
#include <QCompleter>
#include <QDir>
#include <QEvent>
#include <QFile>
#include <QFileDialog>
#include <QFrame>
#include <QGridLayout>
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

constexpr QLatin1StringView kAioSourceId{"all_in_one"};
constexpr QLatin1StringView kAioScript{"all_in_one.py"};
constexpr int kAioRefreshAfterSec = 15 * 60;
constexpr int kAioMaRole = Qt::UserRole + 1;
constexpr int kAioTenMax = 40;
constexpr int kAioPopupRows = 14;
constexpr int kAioPopupMinW = 340;
constexpr int kAioSeqRing = 8;   ///< request ids cycle (EconomicsService keeps one DataHub topic per id)
constexpr int kAioCols = 12;     ///< bento grid columns
constexpr int kAioNarrowPx = 1100; ///< below this viewport width every tile spans the full row
constexpr int kAioChipW = 56;
constexpr int kAioChipH = 26;
constexpr int kAioRelayoutMs = 80; ///< resize debounce before re-checking narrow mode / chips per row

/// Chips per row of the ticker board for a viewport width (group label column + margins taken off).
int aio_per_row(int viewport_w) {
    const int avail = std::max(400, viewport_w - 60 - 150);
    return std::max(6, avail / (kAioChipW + 4));
}

/// Board scopes: (code sent to the script, button label).
const std::pair<const char*, const char*> kAioRo[] = {
    {"VN30", "VN30"}, {"VN100", "VN100"}, {"VN200", "VN200"}, {"CHAEBOL", "CHAEBOL MAP"}};

bool aio_is_ro(const QString& s) {
    for (const auto& [code, label] : kAioRo)
        if (s == QLatin1String(code))
            return true;
    return false;
}

bool aio_valid_ticker(const QString& s) {
    if (s.isEmpty() || s.size() > 10)
        return false;
    for (const QChar c : s)
        if (c.unicode() >= 128 || !c.isLetterOrNumber())
            return false;
    return true;
}

/// "vcb · Vietcombank" → "VCB".
QString aio_first_token(const QString& text) {
    QString t = text.trimmed().toUpper();
    const int cut = static_cast<int>(t.indexOf(QRegularExpression(QStringLiteral("[\\s\\x{00B7}]"))));
    if (cut >= 0)
        t.truncate(cut);
    return t;
}

void aio_set_status(QLabel* label, const QString& text, const QColor& color, const QString& tooltip = {}) {
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

class AioUpperValidator : public QValidator {
  public:
    using QValidator::QValidator;
    State validate(QString& input, int& /*pos*/) const override {
        input = input.toUpper();
        return Acceptable;
    }
};

/// The completer swallows Enter when the popup is open with no row selected; this filter still opens the code.
class AioPopupEnter : public QObject {
  public:
    AioPopupEnter(QAbstractItemView* popup, std::function<void()> on_enter, QObject* parent)
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

QString aio_csv_quote(QString v) {
    if (v.contains(QLatin1Char(',')) || v.contains(QLatin1Char('"')) || v.contains(QLatin1Char('\n')) ||
        v.contains(QLatin1Char('\r')))
        v = QStringLiteral("\"") + v.replace(QStringLiteral("\""), QStringLiteral("\"\"")) + QStringLiteral("\"");
    return v;
}

QString aio_csv_cell(const QJsonValue& v) {
    if (v.isDouble())
        return QString::number(v.toDouble(), 'g', 15);
    if (v.isString()) {
        QString s = v.toString();
        if (!s.isEmpty() && QStringLiteral("=+-@\t\r").contains(s.at(0)))
            s.prepend(QLatin1Char('\'')); // CSV-injection guard
        return s;
    }
    return {};
}

QStringList aio_warnings(const QJsonObject& meta) {
    QStringList out;
    for (const QJsonValue& w : meta.value("warnings").toArray()) {
        const QString s = w.toString().trimmed();
        if (!s.isEmpty())
            out << s;
    }
    return out;
}

QColor aio_state_color(const QString& st) {
    if (st == QLatin1String("du"))
        return sgi::col(Role::Up);
    if (st == QLatin1String("cu"))
        return sgi::col(Role::Amber);
    return sgi::col(Role::Down);
}

QString aio_state_text(const QString& st) {
    if (st == QLatin1String("du"))
        return QStringLiteral("ĐỦ");
    if (st == QLatin1String("cu"))
        return QStringLiteral("CŨ");
    return QStringLiteral("THIẾU");
}

QString aio_chip_css(bool selected, const QColor& fg, bool live = true) {
    const QColor bg = selected ? sgi::col(Role::Amber) : sgi::col(Role::Surface2);
    const QColor ink = selected ? sgi::col(Role::Bg) : fg;
    return QStringLiteral("QPushButton { background:%1; color:%2; font-size:11px; font-weight:700; border:1px %6 %3;"
                          " border-radius:3px; padding:0; }"
                          "QPushButton:hover { border-color:%4; color:%5; }")
        .arg(sgi::css(bg), sgi::css(ink), sgi::css(sgi::col(Role::Line)), sgi::css(sgi::col(Role::Amber)),
             sgi::css(selected ? sgi::col(Role::Bg) : sgi::col(Role::Ink)),
             live ? QStringLiteral("solid") : QStringLiteral("dashed"));
}

} // namespace

// ── Construction ─────────────────────────────────────────────────────────────

AllInOnePanel::AllInOnePanel(QWidget* parent)
    : EconPanelBase(QString(kAioSourceId), sgi::css(sgi::col(Role::Amber)), parent) {
    static int s_instances = 0;
    req_prefix_ = QStringLiteral("aio_%1_").arg(++s_instances);

    build_base_ui(this);
    set_stats_visible(false);
    // build_base_ui wires Enter in every toolbar QLineEdit to on_fetch; the MÃ box has its own handler.
    disconnect(ma_edit_, &QLineEdit::returnPressed, this, nullptr);
    connect(ma_edit_, &QLineEdit::returnPressed, this, [this]() { on_ma_entered(ma_edit_->text()); });

    scroll_ = new QScrollArea(this);
    scroll_->setWidgetResizable(true);
    scroll_->setFrameShape(QFrame::NoFrame);
    scroll_->setHorizontalScrollBarPolicy(Qt::ScrollBarAlwaysOff);
    scroll_->setVerticalScrollBarPolicy(Qt::ScrollBarAsNeeded);
    scroll_->setWidget(new QWidget);
    scroll_->viewport()->installEventFilter(this);
    page_idx_ = add_content_page(scroll_);
    restyle_toolbar();

    relayout_timer_ = new QTimer(this);
    relayout_timer_->setSingleShot(true);
    relayout_timer_->setInterval(kAioRelayoutMs);
    connect(relayout_timer_, &QTimer::timeout, this, [this]() {
        if (!loaded_ || !scroll_)
            return;
        const int w = scroll_->viewport()->width();
        if ((w < kAioNarrowPx) != narrow_ || aio_per_row(w) != board_per_row_)
            rebuild_page(/*keep_scroll=*/true);
    });

    // FETCH opens what the MÃ box names (if it differs from the page on screen), otherwise refreshes the page.
    disconnect(fetch_btn_, &QPushButton::clicked, this, nullptr);
    connect(fetch_btn_, &QPushButton::clicked, this, [this]() {
        const QString t = ma_edit_ ? aio_first_token(ma_edit_->text()) : QString();
        if (!t.isEmpty() && t != shown_ma_)
            on_ma_entered(t);
        else
            on_fetch();
    });

    disconnect(export_btn_, &QPushButton::clicked, this, &AllInOnePanel::export_csv);
    connect(export_btn_, &QPushButton::clicked, this, &AllInOnePanel::export_payload_csv);
    export_btn_->setToolTip(tr("Xuất bảng tóm tắt của rổ đang xem (giá, định giá, FFT, chủ thể…) ra CSV"));
    export_btn_->setEnabled(false);

    connect(&services::EconomicsService::instance(), &services::EconomicsService::result_ready, this,
            &AllInOnePanel::on_result);

    show_empty(tr("Mở tab để nạp ALL-IN-ONE · VN30 / VN100 / VN200 / Chaebol MAP…"));
}

void AllInOnePanel::build_controls(QHBoxLayout* thl) {
    const QString btn_tip = tr("Bảng mã %1: bấm một mã để mở toàn bộ ô thông tin của mã đó");
    for (const auto& [code, label] : kAioRo) {
        const QString c = QString::fromLatin1(code);
        auto* b = new QPushButton(QString::fromLatin1(label));
        b->setProperty("aio_ro", c);
        b->setFixedHeight(26);
        b->setCursor(Qt::PointingHandCursor);
        b->setToolTip(c == QLatin1String("VN200")
                          ? tr("VN200 = bộ mã đóng băng của Lăng Kính (lk_vutru.json) ∪ VN100; không có danh sách VN200 chính thức")
                      : c == QLatin1String("CHAEBOL")
                          ? tr("Hệ sinh thái Chaebol MAP: vũ trụ tab VIETCAP IQ, chia theo nhóm V21 rồi các hệ sinh thái")
                          : btn_tip.arg(c));
        connect(b, &QPushButton::clicked, this, [this, c]() { open_board(c); });
        thl->addWidget(b);
        ro_btns_.append(b);
    }

    auto* lbl = new QLabel(tr("MÃ"));
    lbl->setStyleSheet(QStringLiteral("QLabel { color:%1; font-size:10px; font-weight:bold; background:transparent; }")
                           .arg(sgi::css(sgi::col(Role::Muted))));
    thl->addWidget(lbl);

    ma_edit_ = new QLineEdit;
    ma_edit_->setFixedHeight(26);
    ma_edit_->setFixedWidth(110);
    ma_edit_->setPlaceholderText(tr("gõ mã…"));
    ma_edit_->setValidator(new AioUpperValidator(ma_edit_));
    ma_model_ = new QStandardItemModel(this);
    ma_completer_ = new QCompleter(ma_model_, this);
    ma_completer_->setCompletionRole(kAioMaRole);
    ma_completer_->setCaseSensitivity(Qt::CaseInsensitive);
    ma_completer_->setFilterMode(Qt::MatchStartsWith);
    ma_completer_->setCompletionMode(QCompleter::PopupCompletion);
    ma_completer_->setMaxVisibleItems(kAioPopupRows);
    ma_completer_->popup()->setMinimumWidth(kAioPopupMinW);
    ma_edit_->setCompleter(ma_completer_);
    ma_completer_->popup()->installEventFilter(
        new AioPopupEnter(ma_completer_->popup(), [this]() { on_ma_entered(ma_edit_->text()); }, ma_completer_));
    connect(ma_completer_, QOverload<const QString&>::of(&QCompleter::activated), this,
            &AllInOnePanel::on_ma_entered);
    connect(ma_edit_, &QLineEdit::textEdited, this, [this]() {
        if (ma_invalid_) {
            ma_invalid_ = false;
            update_ma_style();
        }
    });
    thl->addWidget(ma_edit_);

    board_btn_ = new QPushButton(tr("BẢNG"));
    board_btn_->setFixedHeight(26);
    board_btn_->setCursor(Qt::PointingHandCursor);
    board_btn_->setToolTip(tr("Về bảng tóm tắt của rổ đang chọn"));
    connect(board_btn_, &QPushButton::clicked, this, [this]() { open_board(ro_); });
    thl->addWidget(board_btn_);

    fresh_lbl_ = new QLabel;
    fresh_lbl_->setTextFormat(Qt::PlainText);
    thl->addWidget(fresh_lbl_);
    update_ma_style();
}

// ── Fetch / results ──────────────────────────────────────────────────────────

void AllInOnePanel::activate() {
    if (fetching_)
        return;
    if (!loaded_ || !fetched_at_.isValid() ||
        fetched_at_.secsTo(QDateTime::currentDateTimeUtc()) >= kAioRefreshAfterSec)
        on_fetch();
    else
        render_fresh();
}

void AllInOnePanel::on_ma_entered(const QString& text) {
    const QString t = aio_first_token(text);
    if (t.isEmpty())
        return;
    if (aio_is_ro(t)) {
        open_board(t);
        return;
    }
    const bool known = ds_ma_.isEmpty() ? aio_valid_ticker(t) : ds_ma_.contains(t);
    ma_invalid_ = !known;
    update_ma_style();
    if (!known)
        return;
    if (fetching_ && ma_ == t)
        return; // popup Enter fires activated + returnPressed
    ma_ = t;
    ma_edit_->setText(t);
    on_fetch();
}

void AllInOnePanel::open_board(const QString& ro) {
    if (fetching_ && ma_.isEmpty() && ro_ == ro)
        return;
    ro_ = ro;
    ma_.clear();
    ma_invalid_ = false;
    if (ma_edit_)
        ma_edit_->clear();
    restyle_toolbar();
    on_fetch();
}

void AllInOnePanel::on_fetch() {
    if (fetching_) {
        refetch_pending_ = true; // latest wins: re-ask once the request in flight returns
        return;
    }
    fetching_ = true;
    req_seq_ = req_seq_ % kAioSeqRing + 1;
    req_current_ = req_prefix_ + QString::number(req_seq_);
    if (!loaded_) {
        show_loading(tr("Đang gom dữ liệu các module cho ALL-IN-ONE…"));
    } else {
        aio_set_status(fresh_lbl_, tr("đang nạp…"), sgi::col(Role::Muted));
        if (fetch_btn_)
            fetch_btn_->setEnabled(false);
    }
    QStringList args;
    QString cmd = QStringLiteral("bang");
    args << QStringLiteral("--ro") << ro_;
    if (!ma_.isEmpty()) {
        cmd = QStringLiteral("ma");
        args << QStringLiteral("--ma") << ma_;
    }
    services::EconomicsService::instance().execute(QString(kAioSourceId), QString(kAioScript), cmd, args,
                                                   req_current_, /*force=*/true);
}

void AllInOnePanel::on_result(const QString& request_id, const services::EconomicsResult& result) {
    if (result.source_id != kAioSourceId || !request_id.startsWith(req_prefix_) || request_id != req_current_)
        return;
    fetching_ = false;
    if (refetch_pending_) { // the user asked for another page meanwhile: drop this result, fetch the latest
        refetch_pending_ = false;
        on_fetch();
        return;
    }
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
    LOG_WARN("AllInOnePanel", "Nạp lỗi: " + err);

    if (loaded_) {
        const QString r = data_.value("meta").toObject().value("ro").toString();
        if (aio_is_ro(r))
            ro_ = r; // toolbar, BẢNG, CSV and the next --ro go back to the page on screen
        ma_ = shown_ma_;
        ma_invalid_ = false;
        if (ma_edit_)
            ma_edit_->setText(shown_ma_);
        restyle_toolbar();
        aio_set_status(fresh_lbl_, tr("⚠ nạp lỗi"), sgi::col(Role::Down), err); // after restyle_toolbar (render_fresh)
    } else {
        const QString failed = ma_;
        ma_.clear();
        if (ma_edit_)
            ma_edit_->clear();
        const QString cmd = failed.isEmpty() ? QStringLiteral("bang --ro ") + ro_ : QStringLiteral("ma --ma ") + failed;
        show_error(err.contains(QLatin1String("python3")) ? err
                                                          : err + tr("\nChạy thử: python3 scripts/all_in_one.py %1").arg(cmd));
    }
}

void AllInOnePanel::apply_payload(const QJsonObject& data) {
    const QJsonObject meta = data.value("meta").toObject();
    const QString new_ma = meta.value("ma").toString();
    const QString old_ro = data_.value("meta").toObject().value("ro").toString();
    const QString ro = meta.value("ro").toString();
    // same page = same ticker, or the same board; another board starts at the top
    const bool same_page = loaded_ && new_ma == shown_ma_ && (!new_ma.isEmpty() || ro == old_ro);
    data_ = data;
    shown_ma_ = new_ma;
    loaded_ = true;
    if (aio_is_ro(ro))
        ro_ = ro;

    fill_tickers(meta.value("ds_ma").toArray());
    restyle_toolbar();
    const QJsonObject csv = data_.value("csv").toObject();
    export_btn_->setEnabled(!csv.value("columns").toArray().isEmpty() && !csv.value("rows").toArray().isEmpty());
    export_btn_->setToolTip(new_ma.isEmpty()
                                ? tr("Xuất bảng tóm tắt của rổ đang xem (giá, định giá, FFT, chủ thể…) ra CSV")
                                : tr("Xuất các chỉ số của mã %1 (mỗi ô số một dòng) ra CSV").arg(new_ma));
    show_content_page(page_idx_); // first: lay the scroll area out so the page is built for its real width
    rebuild_page(/*keep_scroll=*/same_page);
    LOG_INFO("AllInOnePanel", QString("ALL-IN-ONE: %1 · %2 ô")
                                  .arg(new_ma.isEmpty() ? QStringLiteral("bảng ") + ro_ : new_ma)
                                  .arg(data_.value("o").toArray().size()));
}

void AllInOnePanel::fill_tickers(const QJsonArray& ds_ma) {
    if (!ma_model_)
        return;
    QVector<std::pair<QString, QString>> items;
    QSet<QString> codes;
    for (const auto& v : ds_ma) {
        const QJsonObject o = v.toObject();
        const QString m = o.value(QStringLiteral("ma")).toString().trimmed().toUpper();
        if (aio_valid_ticker(m) && !codes.contains(m)) {
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
        same = ma_model_->item(r)->data(kAioMaRole).toString() == items[r].first;
    if (same)
        return;
    ma_model_->clear();
    for (const auto& [m, ten] : std::as_const(items)) {
        const QString t = ten.size() > kAioTenMax ? ten.left(kAioTenMax - 1) + QChar(0x2026) : ten;
        auto* it = new QStandardItem(t.isEmpty() ? m : m + QStringLiteral(" · ") + t);
        it->setData(m, kAioMaRole);
        it->setEditable(false);
        ma_model_->appendRow(it);
    }
}

// ── Toolbar ──────────────────────────────────────────────────────────────────

void AllInOnePanel::render_fresh() {
    if (!fresh_lbl_)
        return;
    if (!loaded_) {
        aio_set_status(fresh_lbl_, QString(), sgi::col(Role::Muted));
        return;
    }
    if (fetching_) { // restyle_toolbar() during a fetch must not put the old page's freshness back
        aio_set_status(fresh_lbl_, tr("đang nạp…"), sgi::col(Role::Muted));
        return;
    }
    const QJsonObject meta = data_.value("meta").toObject();
    const QString to = meta.value("data_to").toString();
    QString txt = to.isEmpty() ? tr("giá [CẦN DATA]") : tr("giá tới %1").arg(to);
    const QString gen = meta.value("generated").toString();
    if (!gen.isEmpty())
        txt += tr(" · gom %1").arg(gen.right(5));
    const QStringList warns = aio_warnings(meta);
    if (!warns.isEmpty())
        aio_set_status(fresh_lbl_, txt + tr(" · ⚠ %1 cảnh báo").arg(warns.size()), sgi::col(Role::Amber),
                       warns.join(QLatin1Char('\n')));
    else
        aio_set_status(fresh_lbl_, txt, sgi::col(Role::Muted));
}

void AllInOnePanel::update_ma_style() {
    if (!ma_edit_)
        return;
    const QColor edge = ma_invalid_ ? sgi::col(Role::Down) : sgi::col(Role::Line);
    ma_edit_->setStyleSheet(QStringLiteral("QLineEdit { background:%1; color:%2; border:1px solid %3; border-radius:4px;"
                                           " font-size:11px; font-weight:700; padding:0 6px; }"
                                           "QLineEdit:focus { border-color:%4; }")
                                .arg(sgi::css(sgi::col(Role::Surface2)), sgi::css(sgi::col(Role::Ink)), sgi::css(edge),
                                     sgi::css(ma_invalid_ ? sgi::col(Role::Down) : sgi::col(Role::Amber))));
    ma_edit_->setToolTip(ma_invalid_ ? tr("Mã không thuộc VN200 hay hệ sinh thái Chaebol MAP")
                                     : tr("Gõ mã VN200 hoặc Chaebol MAP (vd V → các mã bắt đầu bằng V) rồi Enter"));
    if (ma_completer_ && ma_completer_->popup())
        ma_completer_->popup()->setStyleSheet(
            QStringLiteral("QAbstractItemView { background:%1; color:%2; border:1px solid %3; font-size:11px; outline:0; }"
                           "QAbstractItemView::item { padding:3px 6px; }"
                           "QAbstractItemView::item:selected { background:%4; color:%5; }")
                .arg(sgi::css(sgi::col(Role::Surface2)), sgi::css(sgi::col(Role::Ink)), sgi::css(sgi::col(Role::Line)),
                     sgi::css(sgi::col(Role::Amber)), sgi::css(sgi::col(Role::Bg))));
}

void AllInOnePanel::restyle_toolbar() {
    const QString base = QStringLiteral("QPushButton { background:%1; color:%2; font-weight:bold;"
                                        " border-radius:4px; padding:0 8px; border:1px solid %3; }"
                                        "QPushButton:hover { background:%4; color:%5; }"
                                        "QPushButton:disabled { color:%6; }");
    const QString btn_css = base.arg(sgi::css(sgi::col(Role::Surface2)), sgi::css(sgi::col(Role::Ink2)),
                                     sgi::css(sgi::col(Role::Line)), sgi::css(sgi::col(Role::Amber)),
                                     sgi::css(sgi::col(Role::Bg)), sgi::css(sgi::col(Role::Muted)));
    const QString on_css = base.arg(sgi::css(sgi::col(Role::Amber)), sgi::css(sgi::col(Role::Bg)),
                                    sgi::css(sgi::col(Role::Amber)), sgi::css(sgi::col(Role::Amber)),
                                    sgi::css(sgi::col(Role::Bg)), sgi::css(sgi::col(Role::Muted)));
    if (board_btn_)
        board_btn_->setStyleSheet(btn_css);
    for (QPushButton* b : std::as_const(ro_btns_))
        b->setStyleSheet(b->property("aio_ro").toString() == ro_ ? on_css : btn_css);
    update_ma_style();
    if (scroll_)
        scroll_->setStyleSheet(
            QStringLiteral("QScrollArea { background:%1; border:none; }").arg(sgi::css(sgi::col(Role::Bg))));
    render_fresh();
}

void AllInOnePanel::refresh_panel_theme() {
    EconPanelBase::refresh_panel_theme();
    restyle_toolbar();
    if (loaded_)
        rebuild_page(/*keep_scroll=*/true);
}

bool AllInOnePanel::eventFilter(QObject* obj, QEvent* event) {
    // debounced: the timer re-checks narrow mode and chips per row against the values the page was built with
    if (scroll_ && obj == scroll_->viewport() && event->type() == QEvent::Resize && loaded_ && relayout_timer_)
        relayout_timer_->start();
    return EconPanelBase::eventFilter(obj, event);
}

// ── Content page ─────────────────────────────────────────────────────────────

void AllInOnePanel::rebuild_page(bool keep_scroll) {
    if (!scroll_)
        return;
    narrow_ = scroll_->viewport()->width() < kAioNarrowPx;
    board_per_row_ = aio_per_row(scroll_->viewport()->width());
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

QWidget* AllInOnePanel::build_page() {
    const QJsonObject meta = data_.value("meta").toObject();

    auto* page = new QWidget;
    page->setObjectName("aioContent");
    page->setAttribute(Qt::WA_StyledBackground, true);
    page->setStyleSheet(QStringLiteral("QWidget#aioContent { background:%1; }").arg(sgi::css(sgi::col(Role::Bg))));
    auto* vl = new QVBoxLayout(page);
    vl->setContentsMargins(14, 10, 14, 24);
    vl->setSpacing(10);

    vl->addWidget(build_board(page));

    const QJsonObject cong = data_.value("cong").toObject();
    if (!cong.isEmpty())
        vl->addWidget(vnblocks::build_block(cong, page));

    const QStringList warns = aio_warnings(meta);
    if (!warns.isEmpty()) {
        QStringList lines;
        for (const QString& w : warns)
            lines << sgi::span(sgi::esc(QStringLiteral("⚠ ") + w), sgi::col(Role::Amber));
        auto* warn = sgi::make_label(page, sgi::col(Role::Ink2), 11, Qt::RichText);
        warn->setText(lines.join(QStringLiteral("<br>")));
        vl->addWidget(warn);
    }

    vl->addWidget(build_grid(page));
    vl->addStretch(1);
    return page;
}

/// Ticker board: one row of clickable chips per group of payload bang.nhom (Vietcap IQ style); the script decides
/// the groups (VN30 · rest of VN100 · VN101–200, or the Chaebol MAP groups).
QWidget* AllInOnePanel::build_board(QWidget* parent) {
    const QJsonObject bang = data_.value("bang").toObject();
    auto* box = new QFrame(parent);
    box->setObjectName("aioBoard");
    box->setStyleSheet(QStringLiteral("QFrame#aioBoard { background:%1; border:1px solid %2; border-radius:4px; }")
                           .arg(sgi::css(sgi::col(Role::Surface)), sgi::css(sgi::col(Role::Line))));
    auto* vl = new QVBoxLayout(box);
    vl->setContentsMargins(10, 8, 10, 8);
    vl->setSpacing(4);

    const int per_row = board_per_row_ > 0 ? board_per_row_ : aio_per_row(scroll_ ? scroll_->viewport()->width() : 1200);

    const auto add_group = [&](const QString& title, const QJsonArray& chips) {
        if (chips.isEmpty())
            return;
        auto* row = new QHBoxLayout;
        row->setSpacing(8);
        auto* lbl = sgi::make_label(box, sgi::col(Role::Muted), 10, Qt::PlainText);
        lbl->setText(title);
        lbl->setWordWrap(true);
        lbl->setFixedWidth(140);
        lbl->setAlignment(Qt::AlignLeft | Qt::AlignTop);
        row->addWidget(lbl, 0, Qt::AlignTop);
        auto* grid = new QGridLayout;
        grid->setHorizontalSpacing(4);
        grid->setVerticalSpacing(4);
        int i = 0;
        for (const QJsonValue& v : chips) {
            const QJsonObject c = v.toObject();
            const QString m = c.value("ma").toString();
            if (!aio_valid_ticker(m))
                continue;
            auto* b = new QPushButton(m, box);
            b->setFixedSize(kAioChipW, kAioChipH);
            b->setCursor(Qt::PointingHandCursor);
            const bool live = c.value("live").toBool(true);
            const QColor fg = c.value("mau").toString().isEmpty() ? sgi::col(Role::Ink2)
                              : live                           ? vnblocks::colour(c.value("mau").toString())
                                                               : sgi::col(Role::Muted);
            b->setStyleSheet(aio_chip_css(m == shown_ma_, fg, live));
            QStringList tip;
            tip << m + QStringLiteral(" · ") + c.value("ten").toString();
            if (!c.value("gia").toString().isEmpty())
                tip << (live ? tr("giá bảng %1 · %2").arg(c.value("gia").toString(), c.value("pct").toString())
                             : tr("đóng phiên Vietcap %1: %2 · %3")
                                   .arg(c.value("ngay").toString(), c.value("gia").toString(), c.value("pct").toString()));
            if (!c.value("truoc_gdkhq").toString().isEmpty())
                tip << tr("phiên cuối trước GDKHQ: giá điều chỉnh %1").arg(c.value("truoc_gdkhq").toString());
            b->setToolTip(tip.join(QLatin1Char('\n')));
            connect(b, &QPushButton::clicked, this, [this, m]() { on_ma_entered(m); });
            grid->addWidget(b, i / per_row, i % per_row);
            ++i;
        }
        grid->setColumnStretch(per_row, 1);
        row->addLayout(grid, 1);
        vl->addLayout(row);
    };
    for (const QJsonValue& g : bang.value("nhom").toArray()) {
        const QJsonObject go = g.toObject();
        add_group(go.value("nhan").toString(), go.value("ma").toArray());
    }
    return box;
}

/// Bento grid: tiles flow left→right in 12 columns, each spanning o.cot columns (full width when narrow).
QWidget* AllInOnePanel::build_grid(QWidget* parent) {
    auto* host = new QWidget(parent);
    auto* grid = new QGridLayout(host);
    grid->setContentsMargins(0, 0, 0, 0);
    grid->setHorizontalSpacing(10);
    grid->setVerticalSpacing(10);
    for (int c = 0; c < kAioCols; ++c)
        grid->setColumnStretch(c, 1);

    int row = 0, col = 0;
    for (const QJsonValue& v : data_.value("o").toArray()) {
        const QJsonObject o = v.toObject();
        int span = narrow_ ? kAioCols : std::clamp(o.value("cot").toInt(kAioCols), 1, kAioCols);
        if (col + span > kAioCols) {
            ++row;
            col = 0;
        }
        grid->addWidget(build_tile(o, host), row, col, 1, span);
        col += span;
        if (col >= kAioCols) {
            ++row;
            col = 0;
        }
    }
    return host;
}

QWidget* AllInOnePanel::build_tile(const QJsonObject& o, QWidget* parent) {
    auto* tile = new QFrame(parent);
    tile->setObjectName("aioTile");
    const QString st = o.value("trang_thai").toString();
    tile->setStyleSheet(QStringLiteral("QFrame#aioTile { background:%1; border:1px solid %2; border-top:2px solid %3;"
                                       " border-radius:4px; }")
                            .arg(sgi::css(sgi::col(Role::Surface)), sgi::css(sgi::col(Role::Line)),
                                 sgi::css(st == QLatin1String("thieu") ? sgi::col(Role::Line2) : sgi::col(Role::Amber))));
    auto* vl = new QVBoxLayout(tile);
    vl->setContentsMargins(12, 8, 12, 10);
    vl->setSpacing(6);

    // header: eyebrow / title · state pill · tier · MỞ <tab> ›
    auto* head = new QHBoxLayout;
    head->setSpacing(8);
    auto* title = sgi::make_label(tile, sgi::col(Role::Ink), 13, Qt::RichText);
    QString html;
    const QString eyebrow = o.value("eyebrow").toString();
    if (!eyebrow.isEmpty())
        html += QStringLiteral("<span style='color:%1; font-size:9px; font-weight:700; letter-spacing:1px;'>%2</span><br>")
                    .arg(sgi::css(sgi::col(Role::Amber)), sgi::esc(eyebrow.toUpper()));
    html += QStringLiteral("<b>%1</b>").arg(sgi::esc(o.value("tieu_de").toString()));
    title->setText(html);
    title->setWordWrap(true);
    head->addWidget(title, 1);

    if (!st.isEmpty()) {
        auto* pill = sgi::make_label(tile, aio_state_color(st), 10, Qt::RichText);
        pill->setText(sgi::pill_html(aio_state_text(st), aio_state_color(st), 9));
        const QString note = o.value("ghi_chu").toString();
        if (!note.isEmpty())
            pill->setToolTip(QStringLiteral("<p>%1</p>").arg(sgi::esc(note)));
        head->addWidget(pill, 0, Qt::AlignTop);
    }
    const QString tier = o.value("tier").toString();
    if (!tier.isEmpty()) {
        auto* tl = sgi::make_label(tile, sgi::col(Role::Muted), 10, Qt::RichText);
        tl->setText(sgi::tier_html(tier, 9));
        head->addWidget(tl, 0, Qt::AlignTop);
    }
    const QString tab = o.value("tab").toString();
    if (!tab.isEmpty()) {
        auto* go = new QPushButton(tr("MỞ %1 ›").arg(o.value("tab_nhan").toString(tab).toUpper()), tile);
        go->setCursor(Qt::PointingHandCursor);
        go->setFixedHeight(20);
        // Chaebol Reflex is the only tab that takes the ticker along (nav hint, VnNavHint.h).
        const bool deep_link = tab == QLatin1String("msn_reflex");
        if (shown_ma_.isEmpty())
            go->setToolTip(tr("Chuyển sang tab %1").arg(o.value("tab_nhan").toString(tab)));
        else if (deep_link)
            go->setToolTip(tr("Mở Chaebol Reflex ở nhóm của mã %1").arg(shown_ma_));
        else
            go->setToolTip(tr("Chuyển sang tab %1 (gõ lại mã %2 ở ô MÃ của tab đó nếu cần)")
                               .arg(o.value("tab_nhan").toString(tab), shown_ma_));
        go->setStyleSheet(QStringLiteral("QPushButton { background:transparent; color:%1; font-size:9px; font-weight:700;"
                                         " border:1px solid %2; border-radius:3px; padding:0 6px; }"
                                         "QPushButton:hover { background:%1; color:%3; }")
                              .arg(sgi::css(sgi::col(Role::Amber)), sgi::css(sgi::col(Role::AmberLine)),
                                   sgi::css(sgi::col(Role::Bg))));
        connect(go, &QPushButton::clicked, this, [this, tab, deep_link]() {
            // Only for the tab that takes it (a hint nobody takes is never cleared); "" clears an older one.
            if (deep_link)
                nav_hint::set(tab, shown_ma_);
            EventBus::instance().publish("nav.switch_screen", QVariantMap{{"screen_id", tab}});
        });
        head->addWidget(go, 0, Qt::AlignTop);
    }
    vl->addLayout(head);

    const QJsonArray khoi = o.value("khoi").toArray();
    if (khoi.isEmpty()) {
        auto* empty = sgi::make_label(tile, sgi::col(Role::Muted), 11, Qt::PlainText);
        const QString note = o.value("ghi_chu").toString();
        empty->setText(note.isEmpty() ? tr("[CẦN DATA] module chưa có dữ liệu cho mã này") : note);
        empty->setWordWrap(true);
        vl->addWidget(empty);
    }
    for (const QJsonValue& b : khoi)
        vl->addWidget(vnblocks::build_block(b.toObject(), tile));
    vl->addStretch(1);
    return tile;
}

// ── Actions ──────────────────────────────────────────────────────────────────

void AllInOnePanel::export_payload_csv() {
    if (!loaded_)
        return;
    const QJsonObject csv = data_.value("csv").toObject();
    const QJsonArray columns = csv.value("columns").toArray();
    const QJsonArray rows = csv.value("rows").toArray();
    if (columns.isEmpty() || rows.isEmpty())
        return;

    QString to = data_.value("meta").toObject().value("data_to").toString();
    to.remove(QRegularExpression(QStringLiteral("[^0-9A-Za-z]")));
    const QString suggested = QDir::homePath() + QStringLiteral("/Downloads/all_in_one_%1_%2.csv")
                                                     .arg(shown_ma_.isEmpty()
                                                              ? data_.value("meta").toObject().value("ro").toString(ro_)
                                                              : shown_ma_,
                                                          to.isEmpty() ? QStringLiteral("khong_ngay") : to);
    const QString path = QFileDialog::getSaveFileName(this, tr("Xuất CSV"), suggested, tr("CSV (*.csv)"));
    if (path.isEmpty())
        return;

    QFile file(path);
    if (!file.open(QIODevice::WriteOnly | QIODevice::Truncate)) {
        LOG_WARN("AllInOnePanel", "Không ghi được CSV " + path + ": " + file.errorString());
        QMessageBox::warning(this, tr("Xuất CSV"), tr("Không ghi được tệp:\n%1\n%2").arg(path, file.errorString()));
        return;
    }
    file.write("\xEF\xBB\xBF");
    QTextStream out(&file);
    out.setEncoding(QStringConverter::Utf8);
    const auto write_row = [&out](const QJsonArray& cells, qsizetype width) {
        QStringList quoted;
        for (qsizetype i = 0; i < width; ++i)
            quoted << aio_csv_quote(i < cells.size() ? aio_csv_cell(cells.at(i)) : QString());
        out << quoted.join(QLatin1Char(',')) << "\n";
    };
    const qsizetype width = columns.size();
    write_row(columns, width);
    for (const QJsonValue& rv : rows)
        write_row(rv.toArray(), std::max(width, rv.toArray().size()));
    out.flush();
    LOG_INFO("AllInOnePanel", QString("Xuất %1 dòng → %2").arg(rows.size()).arg(path));
}

} // namespace fincept::screens
