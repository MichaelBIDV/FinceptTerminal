// src/screens/hhp_valuation/HhpValuationScreen.cpp
#include "screens/hhp_valuation/HhpValuationScreen.h"

#include "screens/hhp_valuation/HhpValuationPanel.h"

#include <QShowEvent>
#include <QVBoxLayout>

namespace fincept::screens {

HhpValuationScreen::HhpValuationScreen(QWidget* parent) : QWidget(parent) {
    setObjectName("hhpValuationScreen");

    auto* root = new QVBoxLayout(this);
    root->setContentsMargins(0, 0, 0, 0);
    root->setSpacing(0);

    panel_ = new HhpValuationPanel(this);
    root->addWidget(panel_);
}

void HhpValuationScreen::showEvent(QShowEvent* event) {
    QWidget::showEvent(event);
    // Lazy (nothing runs until the tab is opened); the panel decides whether a re-fetch is due.
    panel_->activate();
}

} // namespace fincept::screens
