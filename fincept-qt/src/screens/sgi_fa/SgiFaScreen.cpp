// src/screens/sgi_fa/SgiFaScreen.cpp
#include "screens/sgi_fa/SgiFaScreen.h"

#include "screens/sgi_fa/SgiFaPanel.h"

#include <QShowEvent>
#include <QVBoxLayout>

namespace fincept::screens {

SgiFaScreen::SgiFaScreen(QWidget* parent) : QWidget(parent) {
    setObjectName("sgiFaScreen");

    auto* root = new QVBoxLayout(this);
    root->setContentsMargins(0, 0, 0, 0);
    root->setSpacing(0);

    panel_ = new SgiFaPanel(this);
    root->addWidget(panel_);
}

void SgiFaScreen::showEvent(QShowEvent* event) {
    QWidget::showEvent(event);
    // Lazy (nothing runs until the tab is opened); the panel decides whether a re-fetch is due.
    panel_->activate();
}

} // namespace fincept::screens
