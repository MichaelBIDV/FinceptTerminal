// src/screens/deepfa/DeepFaScreen.h
// Top-level dock screen "deepfa" (tab DEEP FA) — a thin host for DeepFaPanel, which does all the
// work: the HĐCV Deep FA research desk (memo 8 section + lớp tín hiệu + Vietcap IQ live), fed by
// scripts/deepfa.py through EconomicsService. Activates the panel on every show: the Python fetch
// only runs once the user actually opens the tab, and re-runs when the data is due.
#pragma once

#include <QWidget>

class QShowEvent;

namespace fincept::screens {

class DeepFaPanel;

class DeepFaScreen : public QWidget {
    Q_OBJECT
  public:
    explicit DeepFaScreen(QWidget* parent = nullptr);

    /// Open the research page of one ticker (used by other screens / command bar deep links).
    void open_ticker(const QString& ticker);

  protected:
    void showEvent(QShowEvent* event) override;

  private:
    DeepFaPanel* panel_ = nullptr;
};

} // namespace fincept::screens
