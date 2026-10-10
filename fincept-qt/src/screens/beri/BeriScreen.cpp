// src/screens/beri/BeriScreen.cpp
#include "screens/beri/BeriScreen.h"

#include "screens/beri/BeriPanel.h"

#include <QShowEvent>
#include <QVBoxLayout>

namespace fincept::screens {

BeriScreen::BeriScreen(QWidget* parent) : QWidget(parent) {
    setObjectName("beriScreen");

    auto* root = new QVBoxLayout(this);
    root->setContentsMargins(0, 0, 0, 0);
    root->setSpacing(0);

    panel_ = new BeriPanel(this);
    root->addWidget(panel_);
}

void BeriScreen::showEvent(QShowEvent* event) {
    QWidget::showEvent(event);
    // Lazy (nothing runs until the tab is opened); the panel decides whether a re-fetch is due.
    panel_->activate();
}

} // namespace fincept::screens
