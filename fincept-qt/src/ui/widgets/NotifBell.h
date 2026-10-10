#pragma once
#include <QEvent>
#include <QPointer>
#include <QPushButton>

namespace fincept::notifications {
struct NotificationRecord;
}

namespace fincept::ui {

class NotifPanel;

/// Bell button with unread badge, one per WindowFrame (lives in ui::StatusBar).
/// Seeds from NotificationService::unread_count(), follows unread_count_changed,
/// and owns the NotifPanel popup it toggles (created lazily on first click).
class NotifBell : public QPushButton {
    Q_OBJECT
  public:
    explicit NotifBell(QWidget* parent = nullptr);

    void set_unread(int count);

    /// Open the history popup on one record's detail page (toast / banner click).
    void open_detail(const fincept::notifications::NotificationRecord& record);

  protected:
    void changeEvent(QEvent* e) override;
    void hideEvent(QHideEvent* e) override;

  private:
    void update_label();
    void toggle_panel();
    void ensure_panel();

    int unread_{0};
    QPointer<NotifPanel> panel_;
};

} // namespace fincept::ui
