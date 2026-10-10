// src/screens/hsc_research/HscResearchScreen.h
// Top-level dock screen "hsc_research" (tab HSC RESEARCH) — a thin host for HscResearchPanel, which does
// all the work. Activates the panel on every show: the Python run only happens once the user actually
// opens the tab, and re-runs when the data is due.
#pragma once

#include <QWidget>

class QShowEvent;

namespace fincept::screens {

class HscResearchPanel;

class HscResearchScreen : public QWidget {
    Q_OBJECT
  public:
    explicit HscResearchScreen(QWidget* parent = nullptr);

  protected:
    void showEvent(QShowEvent* event) override;

  private:
    HscResearchPanel* panel_ = nullptr;
};

} // namespace fincept::screens
