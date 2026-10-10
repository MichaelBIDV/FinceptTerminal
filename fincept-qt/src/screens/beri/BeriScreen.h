// src/screens/beri/BeriScreen.h
// Top-level dock screen "beri" (tab BERI · HĐCV) — a thin host for BeriPanel, which does all the
// work. Activates the panel on every show: the Python run only happens once the user actually
// opens the tab, and re-runs when the data is due.
#pragma once

#include <QWidget>

class QShowEvent;

namespace fincept::screens {

class BeriPanel;

class BeriScreen : public QWidget {
    Q_OBJECT
  public:
    explicit BeriScreen(QWidget* parent = nullptr);

  protected:
    void showEvent(QShowEvent* event) override;

  private:
    BeriPanel* panel_ = nullptr;
};

} // namespace fincept::screens
