// src/screens/all_in_one/AllInOneScreen.h
// Top-level dock screen "all_in_one" (F-key ALL-IN-ONE, right after DASHBOARD): thin host for AllInOnePanel.
// Activates the panel on every show, so the Python run only happens once the user actually opens the tab.
#pragma once

#include <QWidget>

class QShowEvent;

namespace fincept::screens {

class AllInOnePanel;

class AllInOneScreen : public QWidget {
    Q_OBJECT
  public:
    explicit AllInOneScreen(QWidget* parent = nullptr);

  protected:
    void showEvent(QShowEvent* event) override;

  private:
    AllInOnePanel* panel_ = nullptr;
};

} // namespace fincept::screens
