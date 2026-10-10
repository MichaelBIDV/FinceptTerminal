// src/screens/toanvu_pe/ToanVuPeScreen.cpp
#include "screens/toanvu_pe/ToanVuPeScreen.h"

#include "screens/toanvu_pe/ToanVuPePanel.h"

#include <QShowEvent>
#include <QVBoxLayout>

namespace fincept::screens {

ToanVuPeScreen::ToanVuPeScreen(QWidget* parent) : QWidget(parent) {
    setObjectName("toanVuPeScreen");

    auto* root = new QVBoxLayout(this);
    root->setContentsMargins(0, 0, 0, 0);
    root->setSpacing(0);

    panel_ = new ToanVuPePanel(this);
    root->addWidget(panel_);
}

void ToanVuPeScreen::showEvent(QShowEvent* event) {
    QWidget::showEvent(event);
    panel_->activate(); // lazy: the panel decides whether a fetch is due
}

} // namespace fincept::screens
