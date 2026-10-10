// src/screens/hdcv_launchpad/HdcvLaunchpadScreen.cpp
// Top-level dock screen "hdcv_launchpad" — a thin host for hlp::Shell, which owns the Launchpad chrome,
// the data files and the 60 s poll. Nothing is read until the tab is first shown; every later show lets
// the shell re-read the files that changed meanwhile.
#include "screens/hdcv_launchpad/HdcvLaunchpadScreen.h"

#include "screens/hdcv_launchpad/HlpShell.h"

#include <QShowEvent>
#include <QVBoxLayout>

namespace fincept::screens {

HdcvLaunchpadScreen::HdcvLaunchpadScreen(QWidget* parent) : QWidget(parent) {
    setObjectName(QStringLiteral("hdcvLaunchpadScreen"));

    auto* root = new QVBoxLayout(this);
    root->setContentsMargins(0, 0, 0, 0);
    root->setSpacing(0);

    shell_ = new hlp::Shell(this);
    root->addWidget(shell_);
}

HdcvLaunchpadScreen::~HdcvLaunchpadScreen() = default;

void HdcvLaunchpadScreen::showEvent(QShowEvent* event) {
    QWidget::showEvent(event);
    shell_->activate();
}

} // namespace fincept::screens
