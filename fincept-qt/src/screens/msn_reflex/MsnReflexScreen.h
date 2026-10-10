// src/screens/msn_reflex/MsnReflexScreen.h
// Top-level dock screen (tab Chaebol Reflex, id msn_reflex): a thin host for MsnReflexPanel, which does all the
// work. Activates the panel on every show: the Python run only happens once the user actually opens the tab,
// and re-runs when the data is due.
#pragma once

#include <QWidget>

class QShowEvent;

namespace fincept::screens {

class MsnReflexPanel;

class MsnReflexScreen : public QWidget {
    Q_OBJECT
  public:
    explicit MsnReflexScreen(QWidget* parent = nullptr);

  protected:
    void showEvent(QShowEvent* event) override;

  private:
    MsnReflexPanel* panel_ = nullptr;
};

} // namespace fincept::screens
