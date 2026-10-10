#pragma once
// WidataScreen.h: dock shell of the tab VĨ MÔ (MACRO), id "economics". Package H (DESIGN §3, §9, §16 C11, C12, C18).
//
//   page 0  wdc::WdcView        clone of the WiData Dashboard (built eagerly, cheap: no disk I/O in its constructor)
//   page 1  EconomicsScreen     the old screen, UNCHANGED (sources incl. "fincept" + 4 SGI views), built lazily the
//                               first time the tab menu item "Nguồn quốc tế & bảng SGI (màn cũ)" is picked; a thin bar
//                               above it goes back to page 0
//
// Data: scripts/widata_clone.py `build` (through EconomicsService, source_id "widata_clone", cache bypassed) writes
// <state>/current.json + builds/<ts>/; the view reads the files itself in worker threads. The builder runs in the
// background when the build is missing/unreadable or its manifest.generated is older than 6 hours, and the age is
// re-checked every 15 minutes while the screen is shown. The decision uses the BuildState the view already read
// (memory only): this class never touches the disk.
//
// No card glue here. WdcView wires every default card itself (UI_w3): X window/range popover (WdcRange), tooltip and
// crosshair (WdcTooltip), the expanded overlay (WdcExpanded::create) and the chart page (openSingleChart /
// openCardSingle). This class calls neither set_card_hook nor set_expand_factory and does not connect
// singleChartRequested / cardSingleRequested: a second connection would open every chart page twice.
//
// Teardown (DESIGN §16 C18: layout + paint run on the wdc-render pool of WdcRenderService, WdcRender.h lifetime):
//   tab closed (destructor)   the view goes first, while this object is whole: its signals are cut from this shell,
//                             then it is deleted. Its cards withdraw their render jobs (cancelled when nobody else
//                             waits); WdcView releases the service, and the last release stops it (queued jobs
//                             dropped, running paints awaited) and deletes it. With views in other windows the pool
//                             keeps serving them.
//   app quit (aboutToQuit)    same teardown, then WdcRenderService::existing()->stopPool() when other windows still
//                             hold the service, so no worker paints text once QGuiApplication goes away (abort "Must
//                             construct a QGuiApplication before accessing QFontDatabase"). save_state() keeps
//                             answering from the last dashboard; view() is null from then on.
//
// This is the only TU of the module that depends on the app (EconomicsService, EconomicsScreen, ScreenStateManager,
// Logger); every Wdc* file builds without it (harness H1).
#include "screens/common/IStatefulScreen.h"

#include <QDateTime>
#include <QString>
#include <QVariantMap>
#include <QWidget>

class QStackedWidget;
class QTimer;

namespace fincept::services {
struct EconomicsResult;
}

namespace fincept::screens {

class EconomicsScreen;
namespace wdc {
class WdcView;
}

class WidataScreen : public QWidget, public IStatefulScreen {
    Q_OBJECT
  public:
    explicit WidataScreen(QWidget* parent = nullptr);
    ~WidataScreen() override;

    // IStatefulScreen. New key so the state of the embedded EconomicsScreen ("economics", v1) is never fed into
    // this class; version 2 drops the v1 row stored under the dock UUID of the old screen (TabSessionStore).
    void restore_state(const QVariantMap& state) override;
    QVariantMap save_state() const override;
    QString state_key() const override { return QStringLiteral("economics_widata"); }
    int state_version() const override { return 2; }

    // harness / H2 API
    wdc::WdcView* view() const { return view_; }   // null once the app is quitting (view torn down)
    EconomicsScreen* legacy_screen() const { return economics_; }   // null until first opened
    bool legacy_shown() const;
    bool builder_running() const { return building_; }
    QString builder_error() const { return builder_error_; }
    QDateTime last_builder_start() const { return last_attempt_; }
    int refresh_interval_ms() const;
    bool refresh_timer_active() const;
    bool quitting() const { return quitting_; }

  public slots:
    void show_clone();
    void show_legacy();
    void run_builder();   // `widata_clone.py build` now (no age check)

  signals:
    void builderStarted();
    void builderFinished(bool ok, const QString& error);

  protected:
    void showEvent(QShowEvent* e) override;
    void hideEvent(QHideEvent* e) override;

  private:
    void on_result(const QString& request_id, const services::EconomicsResult& result);
    void on_view_loaded();
    void maybe_rebuild();        // build missing/unreadable or older than 6 h, at most one try per 15 min
    void apply_pending_dash();
    void on_app_quit();          // aboutToQuit: teardown_view, then stop the render pool
    void teardown_view();        // ordered: timer, view signals, view (its cards withdraw their render jobs)

    QStackedWidget* stack_ = nullptr;
    wdc::WdcView* view_ = nullptr;
    QWidget* legacy_page_ = nullptr;
    EconomicsScreen* economics_ = nullptr;
    QTimer* refresh_timer_ = nullptr;

    bool view_loaded_ = false;   // the view has applied at least one read of current.json
    bool building_ = false;
    bool quitting_ = false;
    QDateTime last_attempt_;     // UTC, start of the last builder run
    QString builder_error_;
    // result_ready reaches every connected screen: per-instance prefix + id of the request in flight
    QString req_prefix_, req_current_;
    int req_seq_ = 0;

    QString pending_dash_;       // restored before the first load: applied once the view has its layouts
    QString last_dash_;          // dashboard of the view when it was torn down (save_state after quit)
    QVariantMap legacy_state_;   // state of the embedded EconomicsScreen, restored when it is first built
};

} // namespace fincept::screens
