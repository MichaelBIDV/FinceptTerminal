// src/screens/sgi_fa/SgiFaScreen.h
// Top-level dock screen "sgi_fa" (tab SGI FA) — a thin host for SgiFaPanel, which does all the
// work. Activates the panel on every show: the Python run only happens once the user actually
// opens the tab, and re-runs when the data is due.
#pragma once

#include <QWidget>

class QShowEvent;

namespace fincept::screens {

class SgiFaPanel;

class SgiFaScreen : public QWidget {
    Q_OBJECT
  public:
    explicit SgiFaScreen(QWidget* parent = nullptr);

  protected:
    void showEvent(QShowEvent* event) override;

  private:
    SgiFaPanel* panel_ = nullptr;
};

} // namespace fincept::screens
