// src/screens/hhp_valuation/HhpValuationScreen.h
// Top-level dock screen "hhp_valuation" (tab ĐỊNH GIÁ HHP) — a thin host for
// HhpValuationPanel, which does all the work. Activates the panel on every show: the Python
// fetch only runs once the user actually opens the tab, and re-runs when the data is due.
#pragma once

#include <QWidget>

class QShowEvent;

namespace fincept::screens {

class HhpValuationPanel;

class HhpValuationScreen : public QWidget {
    Q_OBJECT
  public:
    explicit HhpValuationScreen(QWidget* parent = nullptr);

  protected:
    void showEvent(QShowEvent* event) override;

  private:
    HhpValuationPanel* panel_ = nullptr;
};

} // namespace fincept::screens
