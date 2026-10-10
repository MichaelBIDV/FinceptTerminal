// WidataScreen.cpp: dock shell of the tab VĨ MÔ (see the header). Package H.
// Builder call modelled on ChaebolMapPanel (EconomicsService::execute with force, result filtered by source + per-instance
// request prefix + request in flight). File-local helpers carry the wdcscreen_ prefix (TU kept out of unity batches).
#include "screens/widata/WidataScreen.h"

#include "core/logging/Logger.h"
#include "core/session/ScreenStateManager.h"
#include "screens/economics/EconomicsScreen.h"
#include "screens/widata/WdcData.h"
#include "screens/widata/WdcRender.h"
#include "screens/widata/WdcView.h"
#include "services/economics/EconomicsService.h"

#include <QCoreApplication>
#include <QElapsedTimer>
#include <QHBoxLayout>
#include <QHideEvent>
#include <QJsonObject>
#include <QLabel>
#include <QPushButton>
#include <QShowEvent>
#include <QStackedWidget>
#include <QTimer>
#include <QVBoxLayout>

namespace fincept::screens {

namespace {

constexpr QLatin1StringView kWdcScreenSourceId{"widata_clone"};
constexpr QLatin1StringView kWdcScreenScript{"widata_clone.py"};
constexpr QLatin1StringView kWdcScreenTag{"WidataScreen"};
constexpr qint64 kWdcScreenMaxAgeSec = 6 * 3600;      ///< rebuild once manifest.generated is this old (DESIGN §3)
constexpr int kWdcScreenTickMs = 15 * 60 * 1000;      ///< age re-checked this often while shown (DESIGN §3)
constexpr qint64 kWdcScreenRetrySec = 15 * 60;        ///< no second automatic run within this delay (failing builder)

/// Why the build should be rebuilt now, empty when it is fresh. Memory only (the view read current.json already).
/// loadError: WdcView::load_error() (current.json unusable, or its layouts.json unreadable: page drawn from
/// layout_const.json with every series [CẦN DATA]).
QString wdcscreen_due_reason(const wdc::BuildState& b, const QString& loadError, const QDateTime& nowUtc) {
    if (!b.ok()) return QStringLiteral("bản dựng không dùng được (%1)").arg(b.errorCode);
    if (!loadError.isEmpty()) return QStringLiteral("bản dựng không đọc được (%1)").arg(loadError);
    const QDateTime gen = QDateTime::fromString(b.generated, Qt::ISODate);
    if (!gen.isValid()) return QStringLiteral("manifest.generated không đọc được (\"%1\")").arg(b.generated);
    const qint64 age = gen.toUTC().secsTo(nowUtc);
    if (age >= kWdcScreenMaxAgeSec) return QStringLiteral("bản dựng %1 đã %2 giờ").arg(b.generated).arg(age / 3600.0, 0, 'f', 1);
    return {};
}

/// App quit, after this screen's view is gone: cancel every render job, drop the queued ones and wait for the running
/// ones (a cancelled job stops before its next pane), so no worker paints text once QGuiApplication is torn down.
/// existing(), not instance(): when the last view released the service it is already stopped and deleted (WdcRender.h),
/// and a session that never rendered must not create one. Views of other windows may still hold it: stopping it at
/// quit does not depend on the order of the aboutToQuit slots.
void wdcscreen_stop_render_pool() {
    if (wdc::WdcRenderService* svc = wdc::WdcRenderService::existing()) svc->stopPool();
}

} // namespace

// ── Construction (cheap: widgets only, no disk, no script) ───────────────────

WidataScreen::WidataScreen(QWidget* parent) : QWidget(parent) {
    static int s_instances = 0;
    req_prefix_ = QStringLiteral("wdc_%1_").arg(++s_instances);
    setObjectName(QStringLiteral("widataScreen"));

    auto* root = new QVBoxLayout(this);
    root->setContentsMargins(0, 0, 0, 0);
    root->setSpacing(0);
    stack_ = new QStackedWidget(this);
    root->addWidget(stack_);

    view_ = new wdc::WdcView(stack_);   // reads current.json in a worker on its first showEvent
    stack_->addWidget(view_);

    legacy_page_ = new QWidget(stack_);
    auto* lay = new QVBoxLayout(legacy_page_);
    lay->setContentsMargins(0, 0, 0, 0);
    lay->setSpacing(0);
    auto* bar = new QWidget(legacy_page_);
    bar->setObjectName(QStringLiteral("widataLegacyBar"));
    auto* hl = new QHBoxLayout(bar);
    hl->setContentsMargins(8, 4, 8, 4);
    hl->setSpacing(10);
    auto* back = new QPushButton(tr("← Quay lại VĨ MÔ"), bar);
    back->setObjectName(QStringLiteral("widataBackButton"));
    back->setCursor(Qt::PointingHandCursor);
    back->setToolTip(tr("Về bảng VĨ MÔ kiểu WiData (bố cục, thẻ biểu đồ)"));
    hl->addWidget(back);
    hl->addWidget(new QLabel(tr("Nguồn quốc tế & bảng SGI (màn cũ)"), bar));
    hl->addStretch(1);
    lay->addWidget(bar);
    stack_->addWidget(legacy_page_);
    stack_->setCurrentWidget(view_);

    connect(back, &QPushButton::clicked, this, &WidataScreen::show_clone);
    connect(view_, &wdc::WdcView::legacySourcesRequested, this, &WidataScreen::show_legacy);
    // No card glue: the view wires range, tooltip, expanded overlay and chart page itself (see the header).
    connect(view_, &wdc::WdcView::loadStatusChanged, this, [this](const QString&) { on_view_loaded(); });
    connect(view_, &wdc::WdcView::dashboardChanged, this,
            [this](const QString&) { ScreenStateManager::instance().notify_changed(this); });
    connect(&services::EconomicsService::instance(), &services::EconomicsService::result_ready, this,
            &WidataScreen::on_result);

    refresh_timer_ = new QTimer(this);
    refresh_timer_->setInterval(kWdcScreenTickMs);
    connect(refresh_timer_, &QTimer::timeout, this, &WidataScreen::maybe_rebuild);
    connect(QCoreApplication::instance(), &QCoreApplication::aboutToQuit, this, &WidataScreen::on_app_quit);
}

// Tab closed: the view goes while this object is whole. Its cards withdraw their jobs; when it was the last view the
// service stops and waits for the paints still running (WdcRender.h), otherwise the pool keeps serving other windows.
WidataScreen::~WidataScreen() { teardown_view(); }

// ── Teardown (tab closed, app quit) ──────────────────────────────────────────

void WidataScreen::teardown_view() {
    if (!view_) return;
    refresh_timer_->stop();
    last_dash_ = view_->current_dashboard();
    view_->disconnect(this);   // the view's signals (the only ones this class listens to) stop reaching this shell
    wdc::WdcView* v = view_;
    view_ = nullptr;
    stack_->removeWidget(v);
    delete v;   // ~WdcCard withdraws its render job; WdcRenderService cancels a job nobody waits for
}

void WidataScreen::on_app_quit() {
    if (quitting_) return;
    quitting_ = true;
    disconnect(&services::EconomicsService::instance(), nullptr, this, nullptr);   // a late builder answer is dropped
    QElapsedTimer t;
    t.start();
    teardown_view();   // the last view releases the service: it is stopped (waited on) and deleted right here
    wdcscreen_stop_render_pool();
    if (t.elapsed() > 200) LOG_INFO(kWdcScreenTag, QStringLiteral("Thoát app: đã chờ luồng vẽ VĨ MÔ %1 ms").arg(t.elapsed()));
}

// ── Pages ────────────────────────────────────────────────────────────────────

bool WidataScreen::legacy_shown() const { return stack_->currentWidget() == legacy_page_; }

void WidataScreen::show_clone() {
    if (!view_) return;
    stack_->setCurrentWidget(view_);
    view_->setFocus(Qt::OtherFocusReason);
    maybe_rebuild();
}

void WidataScreen::show_legacy() {
    if (!economics_) {
        economics_ = new EconomicsScreen(legacy_page_);   // as before: activates its first source ("fincept")
        legacy_page_->layout()->addWidget(economics_);
        if (!legacy_state_.isEmpty()) economics_->restore_state(legacy_state_);
        LOG_INFO(kWdcScreenTag, "Mở màn cũ EconomicsScreen (nguồn quốc tế & bảng SGI)");
    }
    stack_->setCurrentWidget(legacy_page_);
}

// ── Builder ──────────────────────────────────────────────────────────────────

void WidataScreen::on_view_loaded() {
    view_loaded_ = true;
    apply_pending_dash();
    maybe_rebuild();
}

void WidataScreen::maybe_rebuild() {
    if (!view_ || !view_loaded_ || building_) return;
    const QDateTime now = QDateTime::currentDateTimeUtc();
    const QString why = wdcscreen_due_reason(view_->build_state(), view_->load_error(), now);
    if (why.isEmpty()) return;
    if (last_attempt_.isValid() && last_attempt_.secsTo(now) < kWdcScreenRetrySec) return;
    LOG_INFO(kWdcScreenTag, "Dựng lại dữ liệu VĨ MÔ: " + why);
    run_builder();
}

void WidataScreen::run_builder() {
    if (building_) return;
    building_ = true;
    last_attempt_ = QDateTime::currentDateTimeUtc();
    req_current_ = req_prefix_ + QStringLiteral("build_%1").arg(++req_seq_);
    emit builderStarted();
    // Always bypass the service cache: a cached answer may point at a build directory already pruned.
    services::EconomicsService::instance().execute(QString(kWdcScreenSourceId), QString(kWdcScreenScript),
                                                   QStringLiteral("build"), QStringList{}, req_current_, /*force=*/true);
}

void WidataScreen::on_result(const QString& request_id, const services::EconomicsResult& result) {
    if (result.source_id != kWdcScreenSourceId || !request_id.startsWith(req_prefix_) || request_id != req_current_)
        return;
    building_ = false;
    if (!view_) return;   // torn down (app quitting)
    QString err = result.success ? result.data.value(QStringLiteral("error")).toString() : result.error;
    if (result.success && err.isEmpty() && result.data.value(QStringLiteral("ok")).toBool()) {
        builder_error_.clear();
        LOG_INFO(kWdcScreenTag, "Đã dựng dữ liệu VĨ MÔ: " + result.data.value(QStringLiteral("build")).toString());
        view_->reload();   // the old page stays until the new files are read
        emit builderFinished(true, {});
        return;
    }
    if (err.isEmpty()) err = tr("không rõ nguyên nhân");
    builder_error_ = err;
    LOG_WARN(kWdcScreenTag, "Dựng dữ liệu VĨ MÔ lỗi (giữ bản đang hiện): " + err +
                                " · chạy thử: python3 scripts/widata_clone.py build");
    emit builderFinished(false, err);
}

int WidataScreen::refresh_interval_ms() const { return refresh_timer_->interval(); }

bool WidataScreen::refresh_timer_active() const { return refresh_timer_->isActive(); }

void WidataScreen::showEvent(QShowEvent* e) {
    QWidget::showEvent(e);
    if (view_) refresh_timer_->start();
    maybe_rebuild();   // no-op until the view has read current.json (it starts on its own showEvent)
}

void WidataScreen::hideEvent(QHideEvent* e) {
    QWidget::hideEvent(e);
    refresh_timer_->stop();
}

// ── IStatefulScreen ──────────────────────────────────────────────────────────

void WidataScreen::restore_state(const QVariantMap& state) {
    legacy_state_ = state.value(QStringLiteral("legacy")).toMap();
    if (economics_ && !legacy_state_.isEmpty()) economics_->restore_state(legacy_state_);
    pending_dash_ = state.value(QStringLiteral("dash")).toString();
    apply_pending_dash();
}

void WidataScreen::apply_pending_dash() {
    if (pending_dash_.isEmpty() || !view_) return;
    view_->select_dashboard(pending_dash_);   // before the first load: remembered by the view for its reload()
    if (view_->layouts()) pending_dash_.clear();
}

QVariantMap WidataScreen::save_state() const {
    QVariantMap s;
    const QString dash = !pending_dash_.isEmpty() ? pending_dash_ : view_ ? view_->current_dashboard() : last_dash_;
    if (!dash.isEmpty()) s.insert(QStringLiteral("dash"), dash);
    const QVariantMap legacy = economics_ ? economics_->save_state() : legacy_state_;
    if (!legacy.isEmpty()) s.insert(QStringLiteral("legacy"), legacy);
    return s;
}

} // namespace fincept::screens
