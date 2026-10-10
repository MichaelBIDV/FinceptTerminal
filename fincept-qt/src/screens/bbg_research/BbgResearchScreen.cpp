// src/screens/bbg_research/BbgResearchScreen.cpp
#include "screens/bbg_research/BbgResearchScreen.h"

#include "screens/bbg_research/BbgResearchPanel.h"

#include <QShowEvent>
#include <QVBoxLayout>

namespace fincept::screens {

BbgResearchScreen::BbgResearchScreen(QWidget* parent) : QWidget(parent) {
    setObjectName("bbgResearchScreen");

    auto* root = new QVBoxLayout(this);
    root->setContentsMargins(0, 0, 0, 0);
    root->setSpacing(0);

    panel_ = new BbgResearchPanel(this);
    root->addWidget(panel_);
}

void BbgResearchScreen::showEvent(QShowEvent* event) {
    QWidget::showEvent(event);
    // Lazy (nothing runs until the tab is opened); the panel decides whether a re-fetch is due.
    panel_->activate();
}

} // namespace fincept::screens
