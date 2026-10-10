// src/screens/so_nguon/SoNguonScreen.h
// Top-level dock screen "so_nguon" (tab Sổ nguồn) — a thin host for SoNguonPanel, which does all the
// work. Activates the panel on every show: the audit only runs once the user actually opens the tab,
// and a refresh run that was being followed resumes its progress polling.
#pragma once

#include <QWidget>

class QShowEvent;

namespace fincept::screens {

class SoNguonPanel;

class SoNguonScreen : public QWidget {
    Q_OBJECT
  public:
    explicit SoNguonScreen(QWidget* parent = nullptr);

  protected:
    void showEvent(QShowEvent* event) override;

  private:
    SoNguonPanel* panel_ = nullptr;
};

} // namespace fincept::screens
