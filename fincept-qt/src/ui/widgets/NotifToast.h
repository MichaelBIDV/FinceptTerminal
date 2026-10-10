#pragma once
#include "services/notifications/NotificationService.h"

#include <QLabel>
#include <QPropertyAnimation>
#include <QTimer>
#include <QWidget>

namespace fincept::ui {

/// Slide-in toast notification overlay.
/// A CHILD widget (not a window) anchored to the top-right of its parent, so it
/// follows the parent across screens and hides with it (lock / auth / chat page).
/// Tracks parent resizes through an event filter, and re-raises itself when the
/// parent gains a child widget (ADS root-splitter swaps). Auto-dismisses after
/// 4-8 s by level; a burst while visible shows the newest record plus "+N" and
/// restarts the timer. Clicking marks the record read and opens its action_screen.
///
/// Usage (one per WindowFrame, see WindowFrame.cpp):
///   auto* toast = new NotifToast(dock_manager);
///   ... toast->show_notification(record);   // caller decides eligibility
class NotifToast : public QWidget {
    Q_OBJECT
  public:
    explicit NotifToast(QWidget* parent = nullptr);

  public slots:
    void show_notification(const fincept::notifications::NotificationRecord& record);

  protected:
    void paintEvent(QPaintEvent* e) override;
    void showEvent(QShowEvent* e) override;
    void hideEvent(QHideEvent* e) override;
    void mousePressEvent(QMouseEvent* e) override;
    void mouseReleaseEvent(QMouseEvent* e) override;
    bool eventFilter(QObject* obj, QEvent* e) override;

  private:
    QPoint shown_pos() const;
    QPoint hidden_pos() const;
    void reposition();
    void dismiss();
    void refresh_theme();
    void update_time_label();

    QLabel* level_dot_ = nullptr;
    QLabel* title_lbl_ = nullptr;
    QLabel* msg_lbl_ = nullptr;
    QLabel* time_lbl_ = nullptr;
    QTimer* auto_dismiss_ = nullptr;
    QPropertyAnimation* slide_anim_ = nullptr;

    fincept::notifications::NotificationRecord current_;
    int extra_count_ = 0;     ///< records that arrived while this toast was already visible
    bool dismissing_ = false; ///< slide-out in progress; its finished() hides the toast

    static constexpr int TOAST_W = 320;
    static constexpr int TOAST_H = 72;
    static constexpr int MARGIN = 12;
    /// Clears the ADS dock-area title bar (tabs menu / close buttons) at the top of dock_manager_.
    static constexpr int TOP_OFFSET = 36;
    static constexpr int ANIM_MS = 250;
};

namespace notif_ui {

/// Theme colour for a level's dot / accent bar (shared by NotifToast and NotifPanel).
QString level_color(fincept::notifications::NotifLevel level);

/// Marks `record` read (any non-zero id, including the negative ids of records
/// the DB could not persist) and, if it carries an action_screen, opens that
/// screen in the WindowFrame that hosts `from` (walks parentWidget() so popups
/// and floating dock containers resolve too). No navigation while that frame
/// is locked.
void open_record(QWidget* from, const fincept::notifications::NotificationRecord& record);

/// Show `record` in full: the history popup of the bell in the WindowFrame that
/// hosts `from`, on its detail page (marks it read). Falls back to open_record()
/// when that frame has no visible bell (focus / chat mode) or is locked.
void show_record(QWidget* from, const fincept::notifications::NotificationRecord& record);

} // namespace notif_ui

} // namespace fincept::ui
