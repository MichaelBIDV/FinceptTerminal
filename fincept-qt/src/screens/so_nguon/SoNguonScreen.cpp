// src/screens/so_nguon/SoNguonScreen.cpp
#include "screens/so_nguon/SoNguonScreen.h"

#include "screens/so_nguon/SoNguonPanel.h"

#include <QShowEvent>
#include <QVBoxLayout>

namespace fincept::screens {

SoNguonScreen::SoNguonScreen(QWidget* parent) : QWidget(parent) {
    setObjectName("soNguonScreen");

    auto* root = new QVBoxLayout(this);
    root->setContentsMargins(0, 0, 0, 0);
    root->setSpacing(0);

    panel_ = new SoNguonPanel(this);
    root->addWidget(panel_);
}

void SoNguonScreen::showEvent(QShowEvent* event) {
    QWidget::showEvent(event);
    // Lazy (nothing runs until the tab is opened); the panel decides whether an audit is due and
    // resumes polling a refresh run that is still going.
    panel_->activate();
}

} // namespace fincept::screens
