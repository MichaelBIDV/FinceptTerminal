// src/screens/msn_reflex/MsnReflexScreen.cpp
#include "screens/msn_reflex/MsnReflexScreen.h"

#include "screens/msn_reflex/MsnReflexPanel.h"

#include <QShowEvent>
#include <QVBoxLayout>

namespace fincept::screens {

MsnReflexScreen::MsnReflexScreen(QWidget* parent) : QWidget(parent) {
    setObjectName("msnReflexScreen");

    auto* root = new QVBoxLayout(this);
    root->setContentsMargins(0, 0, 0, 0);
    root->setSpacing(0);

    panel_ = new MsnReflexPanel(this);
    root->addWidget(panel_);
}

void MsnReflexScreen::showEvent(QShowEvent* event) {
    QWidget::showEvent(event);
    // Lazy (nothing runs until the tab is opened); the panel decides whether a re-fetch is due.
    panel_->activate();
}

} // namespace fincept::screens
