// src/screens/hsc_research/HscResearchScreen.cpp
#include "screens/hsc_research/HscResearchScreen.h"

#include "screens/hsc_research/HscResearchPanel.h"

#include <QShowEvent>
#include <QVBoxLayout>

namespace fincept::screens {

HscResearchScreen::HscResearchScreen(QWidget* parent) : QWidget(parent) {
    setObjectName("hscResearchScreen");

    auto* root = new QVBoxLayout(this);
    root->setContentsMargins(0, 0, 0, 0);
    root->setSpacing(0);

    panel_ = new HscResearchPanel(this);
    root->addWidget(panel_);
}

void HscResearchScreen::showEvent(QShowEvent* event) {
    QWidget::showEvent(event);
    // Lazy (nothing runs until the tab is opened); the panel decides whether a re-fetch is due.
    panel_->activate();
}

} // namespace fincept::screens
