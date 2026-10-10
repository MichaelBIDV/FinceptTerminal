// src/screens/chaebol_map/ChaebolMapScreen.cpp
#include "screens/chaebol_map/ChaebolMapScreen.h"

#include "screens/chaebol_map/ChaebolMapPanel.h"

#include <QShowEvent>
#include <QVBoxLayout>

namespace fincept::screens {

ChaebolMapScreen::ChaebolMapScreen(QWidget* parent) : QWidget(parent) {
    setObjectName("chaebolMapScreen");

    auto* root = new QVBoxLayout(this);
    root->setContentsMargins(0, 0, 0, 0);
    root->setSpacing(0);

    panel_ = new ChaebolMapPanel(this);
    root->addWidget(panel_);
}

void ChaebolMapScreen::showEvent(QShowEvent* event) {
    QWidget::showEvent(event);
    // Lazy (nothing runs until the tab is opened); the panel decides whether a rebuild is due.
    panel_->activate();
}

} // namespace fincept::screens
