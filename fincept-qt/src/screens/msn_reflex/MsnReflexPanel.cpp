// src/screens/msn_reflex/MsnReflexPanel.cpp
// Chaebol Reflex: fetch lifecycle, toolbar, the group chip row and the one scrollable content page (section
// map in the header). scripts/chaebol_reflex.py (`overview --nhom|--ma`) shapes the whole page as a
// vnblocks/1 "trang" with every number pre-formatted and tiered; vnblocks::build_page() lays it out. This file
// only adds the chip row (meta.ds_nhom) and the meta line (hồ sơ · dữ liệu đến · stale · the script's
// warnings) above it. All data strings are HTML-escaped before they reach a rich-text QLabel or a tooltip.
// Helpers added for the group selector carry a "cr_" / "Cr" prefix (unity-build safety).
#include "screens/msn_reflex/MsnReflexPanel.h"

#include "core/events/EventBus.h"
#include "core/logging/Logger.h"
#include "screens/sgi_fa/SgiCommon.h"
#include "screens/vnblocks/VnBlocks.h"
#include "screens/vnblocks/VnNavHint.h"
#include "services/economics/EconomicsService.h"

#include <QDate>
#include <QDesktopServices>
#include <QDir>
#include <QFile>
#include <QFileDialog>
#include <QFrame>
#include <QHBoxLayout>
#include <QJsonArray>
#include <QLabel>
#include <QLayout>
#include <QMessageBox>
#include <QPointer>
#include <QPushButton>
#include <QRegularExpression>
#include <QScrollArea>
#include <QScrollBar>
#include <QSet>
#include <QSettings>
#include <QStringList>
#include <QTextStream>
#include <QTimer>
#include <QUrl>
#include <QVBoxLayout>

#include <algorithm>

namespace fincept::screens {

namespace {

using sgi::Role;

constexpr QLatin1StringView kSourceId{"msn"};
constexpr QLatin1StringView kScript{"chaebol_reflex.py"};
constexpr int kRefreshAfterSec = 30 * 60;      ///< re-fetch on show / tick once the last load is this old
constexpr int kRefreshTickMs = 15 * 60 * 1000; ///< how often the data age is re-evaluated
constexpr int kSeqRing = 8; ///< request ids cycle (EconomicsService keeps one dispatch record per id)

constexpr QLatin1StringView kCrTabId{"msn_reflex"};               ///< nav hint key = this tab's screen id
constexpr QLatin1StringView kCrSettingsKey{"chaebol_reflex/nhom"}; ///< last group shown
constexpr QLatin1StringView kCrTongQuan{"tong_quan"};             ///< overview page id (default group)
constexpr int kCrChipH = 26;
constexpr int kCrChipMinW = 56;
constexpr int kCrChipTenMax = 22; ///< longer group names are cut with "…" (full name in the tooltip)
constexpr int kCrChipGap = 4;

/// Group slug as the registry writes it ("vingroup", "masan_tcb"): the rule of chaebol_reflex.py (ID_RE
/// [a-z0-9_]+, else BAD_ARGS), capped at 64 here. It goes into argv; with no "-" at all it can never read as a flag.
bool cr_valid_nhom(const QString& s) {
    static const QRegularExpression re(QStringLiteral("^[a-z0-9_]{1,64}$"));
    return re.match(s).hasMatch();
}

/// objectName of the ADS dock widget hosting `w`: DockScreenRouter names every dock after its id ("msn_reflex",
/// "msn_reflex#dup2" …). "" outside a dock.
QString cr_dock_id(const QWidget* w) {
    for (const QWidget* p = w; p; p = p->parentWidget())
        if (p->inherits("ads::CDockWidget"))
            return p->objectName();
    return {};
}

/// VN ticker: 1–10 ASCII letters or digits (same rule as the ALL-IN-ONE box).
bool cr_valid_ticker(const QString& s) {
    if (s.isEmpty() || s.size() > 10)
        return false;
    for (const QChar c : s)
        if (c.unicode() >= 128 || !c.isLetterOrNumber())
            return false;
    return true;
}

/// Group restored from QSettings; anything unusable falls back to the overview.
QString cr_saved_nhom() {
    const QString v = QSettings().value(QString(kCrSettingsKey)).toString().trimmed();
    return cr_valid_nhom(v) ? v : QString(kCrTongQuan);
}

/// Row label of a trục code of the registry (ds_nhom order: TỔNG QUAN, NQ68 tư nhân, NQ79 nhà nước, Special…).
QString cr_truc_label(const QString& key) {
    if (key == QLatin1String("TONG_QUAN"))
        return QStringLiteral("TỔNG QUAN");
    if (key == QLatin1String("NQ68"))
        return QStringLiteral("NQ68 · TƯ NHÂN");
    if (key == QLatin1String("NQ79"))
        return QStringLiteral("NQ79 · NHÀ NƯỚC");
    if (key == QLatin1String("SPECIAL"))
        return QStringLiteral("SPECIAL");
    if (key == QLatin1String("KG21"))
        return QStringLiteral("KG-21 · BỔ SUNG");
    if (key == QLatin1String("V21"))
        return QStringLiteral("V21 · TAB NHÓM");
    return key.isEmpty() || key == QLatin1String("KHAC") ? QStringLiteral("KHÁC") : key;
}

/// Chip caption: shortened, and "&" doubled so QPushButton does not read it as a mnemonic ("T&T").
QString cr_chip_text(const QString& ten) {
    QString t = ten.size() > kCrChipTenMax ? ten.left(kCrChipTenMax - 1) + QChar(0x2026) : ten;
    return t.replace(QLatin1Char('&'), QStringLiteral("&&"));
}

/// Same look as the ALL-IN-ONE board chips (aio_chip_css), plus padding for text and a locked state.
QString cr_chip_css(bool selected) {
    const QColor bg = selected ? sgi::col(Role::Amber) : sgi::col(Role::Surface2);
    const QColor ink = selected ? sgi::col(Role::Bg) : sgi::col(Role::Ink2);
    return QStringLiteral("QPushButton { background:%1; color:%2; font-size:11px; font-weight:700; border:1px solid %3;"
                          " border-radius:3px; padding:0 8px; }"
                          "QPushButton:hover { border-color:%4; color:%5; }"
                          "QPushButton:disabled { color:%6; }")
        .arg(sgi::css(bg), sgi::css(ink), sgi::css(sgi::col(Role::Line)), sgi::css(sgi::col(Role::Amber)),
             sgi::css(selected ? sgi::col(Role::Bg) : sgi::col(Role::Ink)),
             sgi::css(selected ? sgi::col(Role::Bg) : sgi::col(Role::Muted)));
}

/// Left-to-right layout that wraps onto as many rows as the width needs (the Qt "flow layout" example,
/// trimmed), so the chip row reflows on resize without rebuilding the whole page.
class CrFlowLayout : public QLayout {
  public:
    explicit CrFlowLayout(QWidget* parent) : QLayout(parent) { setContentsMargins(0, 0, 0, 0); }
    ~CrFlowLayout() override {
        while (QLayoutItem* it = takeAt(0))
            delete it;
    }
    void addItem(QLayoutItem* item) override { items_.append(item); }
    int count() const override { return static_cast<int>(items_.size()); }
    QLayoutItem* itemAt(int i) const override { return items_.value(i); }
    QLayoutItem* takeAt(int i) override { return i >= 0 && i < items_.size() ? items_.takeAt(i) : nullptr; }
    Qt::Orientations expandingDirections() const override { return {}; }
    bool hasHeightForWidth() const override { return true; }
    int heightForWidth(int w) const override { return arrange(QRect(0, 0, w, 0), /*apply=*/false); }
    QSize sizeHint() const override { return minimumSize(); }
    QSize minimumSize() const override {
        QSize s;
        for (const QLayoutItem* it : items_)
            s = s.expandedTo(it->minimumSize());
        return s;
    }
    void setGeometry(const QRect& r) override {
        QLayout::setGeometry(r);
        arrange(r, /*apply=*/true);
    }

  private:
    /// Places the items row by row inside `r` (only when `apply`); returns the height used.
    int arrange(const QRect& r, bool apply) const {
        int x = r.x(), y = r.y(), row_h = 0;
        for (QLayoutItem* it : items_) {
            const QSize sz = it->sizeHint();
            if (x > r.x() && x + sz.width() > r.x() + r.width()) {
                x = r.x();
                y += row_h + kCrChipGap;
                row_h = 0;
            }
            if (apply)
                it->setGeometry(QRect(QPoint(x, y), sz));
            x += sz.width() + kCrChipGap;
            row_h = std::max(row_h, sz.height());
        }
        return y + row_h - r.y();
    }

    QList<QLayoutItem*> items_;
};

/// "2026-09-24" → "24/09/2026"; anything unparsable is returned as is.
QString fmt_date(const QString& iso) {
    const QDate d = QDate::fromString(iso.left(10), Qt::ISODate);
    return d.isValid() ? d.toString(QStringLiteral("dd/MM/yyyy")) : iso;
}

/// The dossier's own artifact page (meta.artifact_url, else the profile object's). The URL comes from
/// the profile JSON: only ever hand a web URL to the OS.
QUrl profile_url(const QJsonObject& payload) {
    QString raw = payload.value("meta").toObject().value("artifact_url").toString().trimmed();
    if (raw.isEmpty())
        raw = payload.value("profile").toObject().value("artifact_url").toString().trimmed();
    const QUrl url(raw);
    if (!url.isValid() || (url.scheme() != QLatin1String("http") && url.scheme() != QLatin1String("https")))
        return {};
    return url;
}

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
    // The toolbar layout squeezes this label to its first letter; reserve the width of the text explicitly.
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
        // Spreadsheets evaluate a text cell starting with = + - @ as a formula ("+12,4%" → #NAME?, and
        // the same path is the CSV-injection vector): force it to text with a leading apostrophe.
        QString s = v.toString();
        if (!s.isEmpty() && QStringLiteral("=+-@\t\r").contains(s.at(0)))
            s.prepend(QLatin1Char('\''));
        return s;
    }
    return {};
}

/// Non-empty warning strings of meta.warnings, in payload order.
QStringList warnings_of(const QJsonObject& meta) {
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

MsnReflexPanel::MsnReflexPanel(QWidget* parent)
    : EconPanelBase(QString(kSourceId), sgi::css(sgi::col(Role::Amber)), parent) {
    static int s_instances = 0;
    req_prefix_ = QStringLiteral("msn_%1_").arg(++s_instances);
    nhom_ = cr_saved_nhom();

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

    // The base CSV button exports the generic results table, which this panel never fills —
    // point it at the payload's own export rows.
    disconnect(export_btn_, &QPushButton::clicked, this, &MsnReflexPanel::export_csv);
    connect(export_btn_, &QPushButton::clicked, this, &MsnReflexPanel::export_payload_csv);
    export_btn_->setToolTip(tr("Xuất tín hiệu · nhật ký tuần · số live của nhóm đang xem ra CSV"));
    export_btn_->setEnabled(false);

    connect(&services::EconomicsService::instance(), &services::EconomicsService::result_ready, this,
            &MsnReflexPanel::on_result);

    // Deep link into a tab that is already on screen: DockScreenRouter::navigate() only raises a visible dock (no
    // QShowEvent, so activate() would not run). Take the hint here too, queued behind WindowFrame's own queued
    // navigate, and only in the visible dock "msn_reflex" (the one navigate opens). A showEvent that follows finds
    // the hint gone (take() clears it), and fetch_if_due() returns while that fetch runs. Queued on this object, so
    // a publish() from a worker thread is safe as well.
    EventBus::instance().subscribe(this, "nav.switch_screen", [this](const QVariantMap& d) {
        if (d.value("screen_id").toString() != kCrTabId)
            return;
        QMetaObject::invokeMethod(
            this,
            [this]() {
                if (isVisible() && cr_dock_id(this) == kCrTabId)
                    activate();
            },
            Qt::QueuedConnection);
    });

    // The tab can stay open for days: re-check the data age on a timer so the stale warning and the
    // re-fetch do not wait for a manual FETCH.
    refresh_timer_ = new QTimer(this);
    refresh_timer_->setInterval(kRefreshTickMs);
    connect(refresh_timer_, &QTimer::timeout, this, &MsnReflexPanel::on_refresh_tick);
    refresh_timer_->start();

    show_empty(tr("Mở tab để nạp Chaebol Reflex, hồ sơ độ trễ chaebol…"));
}

void MsnReflexPanel::build_controls(QHBoxLayout* thl) {
    fresh_lbl_ = new QLabel;
    fresh_lbl_->setTextFormat(Qt::PlainText);
    thl->addWidget(fresh_lbl_);

    web_btn_ = new QPushButton(tr("🌐 BẢN GỐC"));
    web_btn_->setFixedHeight(26);
    web_btn_->setCursor(Qt::PointingHandCursor);
    web_btn_->setToolTip(tr("Mở hồ sơ gốc (artifact) trong trình duyệt"));
    web_btn_->setEnabled(false);
    connect(web_btn_, &QPushButton::clicked, this, &MsnReflexPanel::open_profile_page);
    thl->addWidget(web_btn_);
}

// ── Fetch / results ──────────────────────────────────────────────────────────

void MsnReflexPanel::activate() {
    // A deep link (ALL-IN-ONE tile "MỞ CHAEBOL REFLEX ›") comes first: open the ticker's group, even when a
    // fetch is in flight (on_fetch() re-asks once it returns). Only the dock "msn_reflex" takes it, the one that
    // nav.switch_screen opens: a "#dup" copy, or a panel outside a dock, leaves the hint for that dock.
    const QString hint =
        cr_dock_id(this) == kCrTabId ? nav_hint::take(QString(kCrTabId)).trimmed().toUpper() : QString();
    if (cr_valid_ticker(hint)) {
        ma_ = hint;
        on_fetch();
        return;
    }
    fetch_if_due();
}

void MsnReflexPanel::fetch_if_due() {
    if (fetching_)
        return;
    if (refresh_due())
        on_fetch();
    else
        render_fresh();
}

bool MsnReflexPanel::refresh_due() const {
    return !loaded_ || !fetched_at_.isValid() ||
           fetched_at_.secsTo(QDateTime::currentDateTimeUtc()) >= kRefreshAfterSec;
}

void MsnReflexPanel::on_refresh_tick() {
    if (!loaded_ || fetching_)
        return;
    if (isVisible())
        fetch_if_due(); // re-fetch when due, else re-evaluate the label (deep links only come through activate())
    else
        render_fresh();
}

void MsnReflexPanel::on_fetch() {
    if (fetching_) {
        refetch_pending_ = true; // latest wins: re-ask once the request in flight returns
        return;
    }
    fetching_ = true;
    req_seq_ = req_seq_ % kSeqRing + 1;
    req_current_ = req_prefix_ + QStringLiteral("overview_%1").arg(req_seq_);
    update_nhom_chips(); // locked until the answer is in
    if (!loaded_) {
        show_loading(tr("Đang nạp Chaebol Reflex: hồ sơ độ trễ chaebol · khối LIVE · biểu đồ…"));
    } else {
        // Keep the current content on screen while the refresh runs.
        set_status(fresh_lbl_, tr("đang làm mới…"), sgi::col(Role::Muted));
        if (fetch_btn_)
            fetch_btn_->setEnabled(false);
    }
    const QStringList args = ma_.isEmpty() ? QStringList{QStringLiteral("--nhom"), nhom_}
                                           : QStringList{QStringLiteral("--ma"), ma_};
    services::EconomicsService::instance().execute(QString(kSourceId), QString(kScript), QStringLiteral("overview"),
                                                   args, req_current_, /*force=*/true);
}

void MsnReflexPanel::on_result(const QString& request_id, const services::EconomicsResult& result) {
    // result_ready reaches every connected panel: route strictly by source + this instance's prefix,
    // then drop answers superseded by a newer FETCH.
    if (result.source_id != kSourceId || !request_id.startsWith(req_prefix_) || request_id != req_current_)
        return;
    fetching_ = false;
    if (refetch_pending_) { // a newer page was asked meanwhile (deep link, FETCH): drop this one, fetch that
        refetch_pending_ = false;
        on_fetch();
        return;
    }
    if (fetch_btn_)
        fetch_btn_->setEnabled(true);

    // EconomicsService already turns a top-level "error" into a failure; the check here is a guard.
    QString err = result.success ? result.data.value("error").toString() : result.error;
    if (result.success && err.isEmpty()) {
        fetched_at_ = QDateTime::currentDateTimeUtc();
        apply_overview(result.data);
        return;
    }
    if (err.isEmpty())
        err = tr("không rõ nguyên nhân");
    const bool by_group = ma_.isEmpty();
    const QString failed = by_group ? QStringLiteral("--nhom ") + nhom_ : QStringLiteral("--ma ") + ma_;
    LOG_WARN("MsnReflexPanel", "Nạp Chaebol Reflex (" + failed + ") lỗi: " + err);
    ma_.clear();

    if (loaded_) {
        nhom_ = shown_nhom_; // chips, FETCH and the next --nhom go back to the page on screen
        update_nhom_chips();
        // Keep the page on screen. Short text: the label sits in the fixed toolbar, a long message
        // would widen the panel; the full error is in the tooltip.
        set_status(fresh_lbl_, tr("⚠ làm mới lỗi"), sgi::col(Role::Down), err);
    } else {
        // No page means no chips to pick another group with: when a group failed, let the next FETCH open the
        // overview, so a saved group that no longer loads cannot lock the tab.
        QString msg = err.contains(QLatin1String("python3"))
                          ? err // script errors already say what to do; the run hint is for runner-level failures
                          : err + tr("\nChạy thử: python3 scripts/chaebol_reflex.py overview %1").arg(failed);
        if (by_group && nhom_ != kCrTongQuan) {
            // The script rejected the group itself (renamed / removed from the registry, or not a valid slug):
            // forget it, so the next start opens the overview instead of this error. Other failures (runner,
            // timeout, INTERNAL) may pass, so the saved group stays.
            if (err.startsWith(QLatin1String("[UNKNOWN_GROUP]")) || err.startsWith(QLatin1String("[BAD_ARGS]")))
                QSettings().setValue(QString(kCrSettingsKey), QString(kCrTongQuan));
            nhom_ = QString(kCrTongQuan);
            msg += tr("\nFETCH để mở TỔNG QUAN.");
        }
        show_error(msg);
    }
}

void MsnReflexPanel::apply_overview(const QJsonObject& data) {
    const QString prev_profile = data_.value("meta").toObject().value("profile_file").toString();
    const QString prev_nhom = shown_nhom_;
    data_ = data;
    const QJsonObject meta = data_.value("meta").toObject();
    QString nhom = meta.value("nhom").toObject().value("id").toString().trimmed();
    const bool known = cr_valid_nhom(nhom);
    if (!known) {
        // Payload without meta.nhom: a `--nhom` page is the group asked for. A `--ma` page names no group, so
        // nhom_ (the group before the deep link) and the saved group stay as they are.
        if (!ma_.isEmpty())
            LOG_WARN("MsnReflexPanel", "Trang --ma " + ma_ + " không có meta.nhom.id hợp lệ: giữ nhóm " + nhom_);
        nhom = nhom_;
    }
    // Keep the reader's place only on a refresh of the same group (and the same dossier file).
    const bool same_profile =
        loaded_ && prev_nhom == nhom && prev_profile == meta.value("profile_file").toString();
    const bool persist = known || ma_.isEmpty();
    loaded_ = true;
    ma_.clear();
    nhom_ = nhom;
    shown_nhom_ = nhom;
    if (persist)
        QSettings().setValue(QString(kCrSettingsKey), nhom);

    render_fresh();
    web_btn_->setEnabled(profile_url(data_).isValid());
    const QJsonObject csv = data_.value("csv").toObject();
    export_btn_->setEnabled(!csv.value("columns").toArray().isEmpty() && !csv.value("rows").toArray().isEmpty());

    const QJsonArray sections = data_.value("trang").toObject().value("sections").toArray();
    if (sections.isEmpty() && meta.value("ds_nhom").toArray().isEmpty()) {
        // Nothing to lay out and no chips to move on with: say so with the script's own warnings.
        QString msg = tr("[CẦN DATA] Hồ sơ không có mục nào để hiển thị.");
        const QStringList warns = warnings_of(meta);
        if (!warns.isEmpty())
            msg += QStringLiteral("\n⚠ ") + warns.join(QStringLiteral("\n⚠ "));
        show_empty(msg);
    } else {
        rebuild_page(/*keep_scroll=*/same_profile); // a periodic refresh keeps the reader's place
        show_content_page(page_idx_);
    }

    LOG_INFO("MsnReflexPanel", QString("Chaebol Reflex: nhóm %1 · hồ sơ %2 · dữ liệu đến %3 · %4 mục · %5 cảnh báo")
                                   .arg(nhom, meta.value("profile_date").toString(QStringLiteral("—")),
                                        meta.value("data_to").toString(QStringLiteral("—")))
                                   .arg(sections.size())
                                   .arg(meta.value("warnings").toArray().size()));
}

void MsnReflexPanel::open_nhom(const QString& id) {
    if (fetching_ || !cr_valid_nhom(id)) // chips are locked while a request is in flight
        return;
    nhom_ = id;
    ma_.clear();
    on_fetch();
}

void MsnReflexPanel::update_nhom_chips() {
    for (const QPointer<QPushButton>& b : std::as_const(nhom_chips_)) {
        if (!b)
            continue;
        b->setStyleSheet(cr_chip_css(b->property("cr_nhom").toString() == nhom_));
        b->setEnabled(!fetching_);
    }
}

// ── Toolbar ──────────────────────────────────────────────────────────────────

void MsnReflexPanel::render_fresh() {
    if (!fresh_lbl_)
        return;
    if (!loaded_) {
        set_status(fresh_lbl_, QString(), sgi::col(Role::Muted));
        return;
    }
    const QJsonObject meta = data_.value("meta").toObject();
    const QString to = meta.value("data_to").toString();
    QString txt = to.isEmpty() ? tr("dữ liệu đến [CẦN DATA]") : tr("Dữ liệu đến %1").arg(fmt_date(to));
    QDateTime at = QDateTime::fromString(meta.value("generated").toString(), Qt::ISODate);
    if (!at.isValid())
        at = fetched_at_;
    if (at.isValid())
        txt += tr(" · cập nhật %1").arg(at.toLocalTime().toString(QStringLiteral("HH:mm")));

    if (meta.value("stale").toBool()) {
        QString stale = meta.value("stale_text").toString().trimmed();
        if (stale.isEmpty()) {
            const QJsonValue age = meta.value("age_days");
            stale = age.isDouble() ? tr("DỮ LIỆU CŨ %1 ngày").arg(age.toInt()) : tr("DỮ LIỆU CŨ");
        }
        set_status(fresh_lbl_, txt + QStringLiteral(" · ⚠ ") + stale, sgi::col(Role::Down), stale);
    } else {
        set_status(fresh_lbl_, txt, sgi::col(Role::Muted));
    }
}

void MsnReflexPanel::restyle_toolbar() {
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

void MsnReflexPanel::refresh_panel_theme() {
    EconPanelBase::refresh_panel_theme();
    // Also runs from build_base_ui() inside the constructor, before the page exists — hence the guards.
    restyle_toolbar();
    if (loaded_)
        rebuild_page(/*keep_scroll=*/true); // vnblocks resolves theme colours at build time
}

void MsnReflexPanel::retranslateUi() {
    if (web_btn_) {
        web_btn_->setText(tr("🌐 BẢN GỐC"));
        web_btn_->setToolTip(tr("Mở hồ sơ gốc (artifact) trong trình duyệt"));
    }
    if (export_btn_)
        export_btn_->setToolTip(tr("Xuất tín hiệu · nhật ký tuần · số live của nhóm đang xem ra CSV"));
    if (!fetching_)
        render_fresh();
    EconPanelBase::retranslateUi();
}

// ── Content page ─────────────────────────────────────────────────────────────

void MsnReflexPanel::rebuild_page(bool keep_scroll) {
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

QWidget* MsnReflexPanel::build_page() {
    const QJsonObject meta = data_.value("meta").toObject();

    auto* page = new QWidget;
    page->setObjectName("msnContent");
    page->setAttribute(Qt::WA_StyledBackground, true);
    page->setStyleSheet(QStringLiteral("QWidget#msnContent { background:%1; }").arg(sgi::css(sgi::col(Role::Bg))));
    auto* vl = new QVBoxLayout(page);
    vl->setContentsMargins(18, 14, 18, 24);
    vl->setSpacing(10);

    // Group chips (meta.ds_nhom) first, so they scroll with the page.
    if (QWidget* bar = build_nhom_bar(page))
        vl->addWidget(bar);

    // Meta line: hồ sơ · dữ liệu đến · live sources · stale warning.
    {
        QStringList parts;
        const QString prof = meta.value("profile_date").toString();
        parts << sgi::esc(prof.isEmpty() ? tr("Hồ sơ [CẦN DATA]") : tr("Hồ sơ %1").arg(fmt_date(prof)));
        const QString to = meta.value("data_to").toString();
        parts << sgi::esc(to.isEmpty() ? tr("dữ liệu đến [CẦN DATA]") : tr("dữ liệu đến %1").arg(fmt_date(to)));
        const int n_live = static_cast<int>(meta.value("sources_live").toArray().size());
        if (n_live > 0)
            parts << sgi::esc(tr("%1 nguồn live").arg(n_live));
        if (meta.value("stale").toBool()) {
            QString stale = meta.value("stale_text").toString().trimmed();
            if (stale.isEmpty()) {
                const QJsonValue age = meta.value("age_days");
                stale = age.isDouble() ? tr("DỮ LIỆU CŨ %1 ngày").arg(age.toInt()) : tr("DỮ LIỆU CŨ");
            }
            parts << sgi::span(sgi::esc(stale), sgi::col(Role::Down), true);
        }

        auto* meta_lbl = sgi::make_label(page, sgi::col(Role::Muted), 12, Qt::RichText);
        meta_lbl->setText(parts.join(QStringLiteral(" · ")));
        const QString file = meta.value("profile_file").toString();
        if (!file.isEmpty())
            meta_lbl->setToolTip(QStringLiteral("<p>%1</p>").arg(sgi::esc(file)));
        vl->addWidget(meta_lbl);
    }

    // Data-quality warnings of this run (share-count gap, μ/σ fallback, missing live sources …): shown
    // up front, not only in the Nguồn section, because they qualify the LIVE numbers below.
    const QStringList warns = warnings_of(meta);
    if (!warns.isEmpty()) {
        QStringList lines;
        for (const QString& w : warns)
            lines << sgi::span(sgi::esc(QStringLiteral("⚠ ") + w), sgi::col(Role::Amber));
        auto* warn = sgi::make_label(page, sgi::col(Role::Ink2), 11, Qt::RichText);
        warn->setText(lines.join(QStringLiteral("<br>")));
        vl->addWidget(warn);
    }

    const QJsonObject trang = data_.value("trang").toObject();
    if (trang.value("sections").toArray().isEmpty()) {
        // Kept on screen for the chips (the warnings above say why the dossier is empty).
        auto* empty = sgi::make_label(page, sgi::col(Role::Muted), 12, Qt::PlainText);
        empty->setText(tr("[CẦN DATA] Hồ sơ nhóm này không có mục nào để hiển thị."));
        vl->addWidget(empty);
    } else {
        vl->addWidget(vnblocks::build_page(trang, page));
    }
    vl->addStretch(1);
    return page;
}

/// Group selector: one row per trục (in meta.ds_nhom order: TỔNG QUAN, NQ68, NQ79, Special…), a small label on
/// the left and the chips of that trục on the right, wrapping as the width needs. Laid out like the
/// ALL-IN-ONE ticker board; the chip of nhom_ is highlighted and every chip is locked while a fetch runs.
QWidget* MsnReflexPanel::build_nhom_bar(QWidget* parent) {
    nhom_chips_.clear();

    struct CrRow {
        QString key; ///< trục code ("TONG_QUAN" for the overview chip)
        QList<QJsonObject> items;
    };
    QList<CrRow> rows;
    QSet<QString> seen;
    for (const QJsonValue& v : data_.value("meta").toObject().value("ds_nhom").toArray()) {
        const QJsonObject o = v.toObject();
        const QString id = o.value("id").toString().trimmed();
        if (!cr_valid_nhom(id) || seen.contains(id))
            continue;
        seen.insert(id);
        const QString key =
            id == kCrTongQuan ? QStringLiteral("TONG_QUAN") : o.value("truc").toString().trimmed().toUpper();
        auto it = std::find_if(rows.begin(), rows.end(), [&key](const CrRow& r) { return r.key == key; });
        if (it == rows.end())
            rows.append({key, {o}});
        else
            it->items.append(o);
    }
    if (rows.isEmpty())
        return nullptr;

    auto* box = new QFrame(parent);
    box->setObjectName("crNhomBar");
    box->setStyleSheet(QStringLiteral("QFrame#crNhomBar { background:%1; border:1px solid %2; border-radius:4px; }")
                           .arg(sgi::css(sgi::col(Role::Surface)), sgi::css(sgi::col(Role::Line))));
    auto* vl = new QVBoxLayout(box);
    vl->setContentsMargins(10, 8, 10, 8);
    vl->setSpacing(4);

    for (const CrRow& r : std::as_const(rows)) {
        auto* row = new QHBoxLayout;
        row->setSpacing(8);
        auto* lbl = sgi::make_label(box, sgi::col(Role::Muted), 10, Qt::PlainText);
        lbl->setText(cr_truc_label(r.key));
        lbl->setFixedWidth(140);
        lbl->setAlignment(Qt::AlignLeft | Qt::AlignTop);
        row->addWidget(lbl, 0, Qt::AlignTop);

        auto* host = new QWidget(box);
        host->setObjectName("crNhomChips");
        host->setAttribute(Qt::WA_StyledBackground, true);
        host->setStyleSheet(QStringLiteral("QWidget#crNhomChips { background:transparent; }"));
        auto* flow = new CrFlowLayout(host);
        for (const QJsonObject& o : r.items) {
            const QString id = o.value("id").toString().trimmed();
            const QString ten = o.value("ten").toString().simplified();
            auto* b = new QPushButton(cr_chip_text(ten.isEmpty() ? id : ten), host);
            b->setFixedHeight(kCrChipH);
            b->setMinimumWidth(kCrChipMinW);
            b->setCursor(Qt::PointingHandCursor);
            b->setProperty("cr_nhom", id);

            QStringList tip;
            tip << (ten.isEmpty() ? id : ten);
            if (id == kCrTongQuan) {
                tip << tr("Bảng các nhóm · capture xuyên chaebol · thư viện khung");
            } else {
                const QString me = o.value("me").toString().trimmed();
                tip << (me.isEmpty() ? tr("không có mẹ niêm yết") : tr("mẹ niêm yết %1").arg(me));
                if (o.value("co_hoi_dong").toBool())
                    tip << tr("có Hội đồng");
            }
            // Tooltips auto-detect rich text: escape the data and force the rich-text path.
            b->setToolTip(QStringLiteral("<p>%1</p>").arg(sgi::esc(tip.join(QLatin1Char('\n')))
                                                              .replace(QLatin1Char('\n'), QStringLiteral("<br>"))));
            connect(b, &QPushButton::clicked, this, [this, id]() { open_nhom(id); });
            flow->addWidget(b);
            nhom_chips_.append(b);
        }
        row->addWidget(host, 1);
        vl->addLayout(row);
    }
    update_nhom_chips();
    return box;
}

// ── Actions ──────────────────────────────────────────────────────────────────

void MsnReflexPanel::export_payload_csv() {
    if (!loaded_)
        return;
    const QJsonObject csv = data_.value("csv").toObject();
    const QJsonArray columns = csv.value("columns").toArray();
    const QJsonArray rows = csv.value("rows").toArray();
    if (columns.isEmpty() || rows.isEmpty())
        return;

    // chaebol_reflex_<nhom>_<data_to>.csv; both parts reduced to [0-9A-Za-z_] (data_to comes from the payload).
    QString to = data_.value("meta").toObject().value("data_to").toString();
    to.remove(QRegularExpression(QStringLiteral("[^0-9A-Za-z]")));
    QString nhom = shown_nhom_;
    nhom.replace(QRegularExpression(QStringLiteral("[^0-9A-Za-z_]")), QStringLiteral("_"));
    const QString suggested = QDir::homePath() + QStringLiteral("/Downloads/chaebol_reflex_%1_%2.csv")
                                                     .arg(nhom.isEmpty() ? QString(kCrTongQuan) : nhom,
                                                          to.isEmpty() ? QStringLiteral("khong_ngay") : to);
    const QString path = QFileDialog::getSaveFileName(this, tr("Xuất CSV"), suggested, tr("CSV (*.csv)"));
    if (path.isEmpty())
        return;

    QFile file(path);
    if (!file.open(QIODevice::WriteOnly | QIODevice::Truncate)) {
        LOG_WARN("MsnReflexPanel", "Không ghi được CSV " + path + ": " + file.errorString());
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
    LOG_INFO("MsnReflexPanel",
             QString("Xuất %1 dòng Chaebol Reflex (nhóm %2) → %3").arg(rows.size()).arg(shown_nhom_, path));
}

void MsnReflexPanel::open_profile_page() {
    const QUrl url = profile_url(data_);
    if (!url.isValid())
        return;
    if (!QDesktopServices::openUrl(url))
        LOG_WARN("MsnReflexPanel", "Không mở được hồ sơ gốc: " + url.toString());
}

} // namespace fincept::screens
