// src/screens/all_in_one/AllInOneScreen.cpp
#include "screens/all_in_one/AllInOneScreen.h"

#include "screens/all_in_one/AllInOnePanel.h"

#include <QShowEvent>
#include <QVBoxLayout>

namespace fincept::screens {

AllInOneScreen::AllInOneScreen(QWidget* parent) : QWidget(parent) {
    setObjectName("allInOneScreen");

    auto* root = new QVBoxLayout(this);
    root->setContentsMargins(0, 0, 0, 0);
    root->setSpacing(0);

    panel_ = new AllInOnePanel(this);
    root->addWidget(panel_);
}

void AllInOneScreen::showEvent(QShowEvent* event) {
    QWidget::showEvent(event);
    panel_->activate(); // lazy: the panel decides whether a fetch is due
}

} // namespace fincept::screens
