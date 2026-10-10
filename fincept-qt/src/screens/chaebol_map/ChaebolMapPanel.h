// src/screens/chaebol_map/ChaebolMapPanel.h
// Bản đồ Chaebol & VN30 — clone of the Master Plan V21 page (localhost:9000/dl/master_plan_v21_chaebol_vn30.html)
// with the live data layer (DESIGN.md §5.1). Built on the Fincept Macro chassis (EconPanelBase +
// EconomicsService running scripts/chaebol_map.py `build`).
//
// The script writes the page as JSON trees into <state dir>/builds/<stamp>/ and prints only a small manifest
// ({"schema":"chaebol_map/1","build":"<dir>","manifest":{…}}); chb::ChbView reads the trees from disk (tabs and
// inc branches lazily) and paints the page with its own palette — the app theme never recolours the canvas.
// On show: the newest build on disk (current.json) is shown at once; it is rebuilt when older than 30 minutes.
//
// Toolbar: freshness (dữ liệu đến · dựng · cảnh báo, warnings in the tooltip) · 🌐 BẢN GỐC · FETCH (rebuild) ·
// CSV (the build's export.csv, re-quoted, formula-guarded, UTF-8 BOM).
#pragma once

#include "screens/economics/panels/EconPanelBase.h"

#include <QDateTime>
#include <QJsonObject>
#include <QString>

class QLabel;
class QPushButton;
class QTimer;

namespace fincept::screens {

namespace chb {
class ChbView;
}

class ChaebolMapPanel : public EconPanelBase {
    Q_OBJECT
  public:
    explicit ChaebolMapPanel(QWidget* parent = nullptr);

    /// Shows the newest build on disk the first time, then rebuilds when nothing is loaded or the loaded build
    /// is older than 30 minutes; otherwise only re-evaluates the freshness label. Called on every show.
    void activate() override;
    chb::ChbView* view() const { return view_; } ///< harness

  protected:
    void build_controls(QHBoxLayout* thl) override;
    void on_fetch() override; ///< `chaebol_map.py build` (cache bypassed)
    void on_result(const QString& request_id, const services::EconomicsResult& result) override;
    void refresh_panel_theme() override; ///< toolbar only: the canvas keeps the page's own colours
    void retranslateUi() override;

  private:
    bool load_from_disk(); ///< <state dir>/current.json, no Python run
    void on_loaded();      ///< a build is on screen: timestamps, buttons, label
    void render_fresh();
    void restyle_toolbar();
    void export_build_csv();
    void open_source_page();
    void on_refresh_tick();
    bool refresh_due() const;
    QDateTime build_time() const; ///< manifest.generated (UTC), else the manifest file time

    bool loaded_ = false;
    bool fetching_ = false;
    bool tried_disk_ = false;
    QString last_error_;          ///< last failed rebuild while a page is shown ("" = none)
    QTimer* refresh_timer_ = nullptr;
    // Per-instance request ids: result_ready reaches every panel; a duplicated panel must not take another
    // instance's answer, and a late answer superseded by a newer FETCH is dropped.
    QString req_prefix_;  ///< "chb_<n>_"
    QString req_current_; ///< id of the newest `build` request sent
    int req_seq_ = 0;

    QLabel* fresh_lbl_ = nullptr;
    QPushButton* web_btn_ = nullptr;
    chb::ChbView* view_ = nullptr;
    int page_idx_ = -1;
};

} // namespace fincept::screens
