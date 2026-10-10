// src/screens/toanvu_pe/ToanVuPeScreen.h
// Top-level dock screen "toanvu_pe" (tab P/E×LS TV): thin host for ToanVuPePanel. Activates the panel on
// every show, so the Python run only happens once the user actually opens the tab.
#pragma once

#include <QWidget>

class QShowEvent;

namespace fincept::screens {

class ToanVuPePanel;

class ToanVuPeScreen : public QWidget {
    Q_OBJECT
  public:
    explicit ToanVuPeScreen(QWidget* parent = nullptr);

  protected:
    void showEvent(QShowEvent* event) override;

  private:
    ToanVuPePanel* panel_ = nullptr;
};

} // namespace fincept::screens
