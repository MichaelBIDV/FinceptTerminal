// src/screens/deepfa/DeepFaScreen.cpp
#include "screens/deepfa/DeepFaScreen.h"

#include "screens/deepfa/DeepFaPanel.h"

#include <QShowEvent>
#include <QVBoxLayout>

namespace fincept::screens {

DeepFaScreen::DeepFaScreen(QWidget* parent) : QWidget(parent) {
    setObjectName("deepFaScreen");

    auto* root = new QVBoxLayout(this);
    root->setContentsMargins(0, 0, 0, 0);
    root->setSpacing(0);

    panel_ = new DeepFaPanel(this);
    root->addWidget(panel_);
}

void DeepFaScreen::open_ticker(const QString& ticker) {
    if (panel_)
        panel_->open_ticker(ticker);
}

void DeepFaScreen::showEvent(QShowEvent* event) {
    QWidget::showEvent(event);
    // Lazy (nothing runs until the tab is opened); the panel decides whether a re-fetch is due.
    panel_->activate();
}

} // namespace fincept::screens
