// src/screens/chaebol_map/ChaebolMapScreen.h
// Top-level dock screen "chaebol_map" (Bản đồ Chaebol & VN30 — clone of Master Plan V21) — a thin host for
// ChaebolMapPanel, which does all the work. Activates the panel on every show: nothing runs until the tab is
// actually opened, and the build is redone only when it is older than 30 minutes.
#pragma once

#include <QWidget>

class QShowEvent;

namespace fincept::screens {

class ChaebolMapPanel;

class ChaebolMapScreen : public QWidget {
    Q_OBJECT
  public:
    explicit ChaebolMapScreen(QWidget* parent = nullptr);
    ChaebolMapPanel* panel() const { return panel_; } ///< harness

  protected:
    void showEvent(QShowEvent* event) override;

  private:
    ChaebolMapPanel* panel_ = nullptr;
};

} // namespace fincept::screens
