// src/screens/bbg_research/BbgResearchScreen.h
// Top-level dock screen "bbg_research" (tab BBG RESEARCH) — a thin host for BbgResearchPanel, which does
// all the work. Activates the panel on every show: the Python run only happens once the user actually
// opens the tab, and re-runs when the data is due.
#pragma once

#include <QWidget>

class QShowEvent;

namespace fincept::screens {

class BbgResearchPanel;

class BbgResearchScreen : public QWidget {
    Q_OBJECT
  public:
    explicit BbgResearchScreen(QWidget* parent = nullptr);

  protected:
    void showEvent(QShowEvent* event) override;

  private:
    BbgResearchPanel* panel_ = nullptr;
};

} // namespace fincept::screens
