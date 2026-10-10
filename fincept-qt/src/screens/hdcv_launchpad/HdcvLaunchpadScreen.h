// src/screens/hdcv_launchpad/HdcvLaunchpadScreen.h
// Top-level dock screen "hdcv_launchpad" (tab HĐCV LAUNCHPAD): a native clone of the web Launchpad
// http://localhost:9000/sys/launchpad/index.html — same top bar (◤ HĐCV LAUNCHPAD · view tabs · MÃ
// input · GO · + Component · Lưu View · Mặc định · ◐), same 12-column panel grid, same panels, same
// data files. Scope (user, 27/09/2026): the three dashboards "Chứng khoán · Mã & Danh mục", "VĨ MÔ ·
// 4 chủ thể", "WIDATA · Tín hiệu"; the SGI Capital panel reads the weekly "Trạm Quan Trắc Vĩ Mô" issue
// instead of the Facebook-KOL channel.
//
// The shell (bar, grid, panel frames, add-component sheet, persistence) lives in HlpShell.*; this
// class only hosts it, loads data lazily on first show and polls file mtimes.
#pragma once

#include <QWidget>

class QShowEvent;

namespace fincept::screens {

namespace hlp {
class Shell;
}

class HdcvLaunchpadScreen : public QWidget {
    Q_OBJECT
  public:
    explicit HdcvLaunchpadScreen(QWidget* parent = nullptr);
    ~HdcvLaunchpadScreen() override;

    /// Test/harness hooks.
    hlp::Shell* shell() const { return shell_; }

  protected:
    void showEvent(QShowEvent* event) override;

  private:
    hlp::Shell* shell_ = nullptr;
};

} // namespace fincept::screens
