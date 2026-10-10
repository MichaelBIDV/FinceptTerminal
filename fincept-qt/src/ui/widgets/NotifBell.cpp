#include "ui/widgets/NotifBell.h"

#include "services/notifications/NotificationService.h"
#include "ui/theme/Theme.h"
#include "ui/theme/ThemeManager.h"
#include "ui/widgets/NotifPanel.h"

#include <QHideEvent>

namespace fincept::ui {

NotifBell::NotifBell(QWidget* parent) : QPushButton(parent) {
    setFlat(true);
    setFixedHeight(20);
    setCursor(Qt::PointingHandCursor);

    // Seed from the service: records restored at startup are already unread
    // before this bell exists, and unread_count_changed only fires on change.
    auto& svc = fincept::notifications::NotificationService::instance();
    unread_ = svc.unread_count();
    update_label();

    connect(&svc, &fincept::notifications::NotificationService::unread_count_changed, this, &NotifBell::set_unread);
    connect(&ThemeManager::instance(), &ThemeManager::theme_changed, this,
            [this](const ThemeTokens&) { update_label(); });
    connect(this, &QPushButton::clicked, this, &NotifBell::toggle_panel);
}

void NotifBell::set_unread(int count) {
    unread_ = count;
    update_label();
}

void NotifBell::changeEvent(QEvent* e) {
    if (e->type() == QEvent::LanguageChange)
        update_label();
    QPushButton::changeEvent(e);
}

void NotifBell::hideEvent(QHideEvent* e) {
    // The status bar hides on lock, auth, chat and focus mode: take the history
    // popup down with it so it never sits over the lock screen.
    if (panel_ && panel_->isVisible())
        panel_->hide();
    QPushButton::hideEvent(e);
}

void NotifBell::ensure_panel() {
    // Lazily create the panel parented to the window so it floats freely and
    // is destroyed with this frame.
    if (!panel_) {
        QWidget* root = window();
        panel_ = new NotifPanel(root ? root : this);
    }
}

void NotifBell::open_detail(const fincept::notifications::NotificationRecord& record) {
    ensure_panel();
    panel_->anchor_to(this);
    panel_->show();
    panel_->raise();
    panel_->show_detail(record);
}

void NotifBell::toggle_panel() {
    ensure_panel();
    if (panel_->isVisible()) {
        panel_->hide();
    } else {
        panel_->anchor_to(this);
        panel_->show();
        panel_->raise();
    }
}

void NotifBell::update_label() {
    const QString color = unread_ > 0 ? ui::colors::WARNING() : ui::colors::TEXT_SECONDARY();
    const QString text = unread_ > 0 ? tr("ALERTS") + QString(" [%1]").arg(unread_) : tr("ALERTS");

    setText(text);
    setStyleSheet(QString("QPushButton { background: transparent; color: %1; border: none; "
                          "font-size: 11px; font-weight: %2; padding: 0 4px; }"
                          "QPushButton:hover { color: %3; }")
                      .arg(color, unread_ > 0 ? "bold" : "normal", QString(ui::colors::AMBER())));
}

} // namespace fincept::ui
