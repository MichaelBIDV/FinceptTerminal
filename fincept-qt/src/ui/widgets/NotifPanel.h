#pragma once
#include "services/notifications/NotificationService.h"

#include <QEvent>
#include <QFrame>
#include <QLabel>
#include <QPushButton>
#include <QScrollArea>
#include <QStackedWidget>
#include <QVBoxLayout>
#include <QVector>
#include <QWidget>

namespace fincept::ui {

/// Notification history popup.
/// Owned and toggled by NotifBell (one per WindowFrame status bar). Opens above
/// the bell, flips below when there is no room, and is clamped to the screen.
/// Clicking a row marks it read and shows its full content on a detail page,
/// with a button to open its action_screen in the host frame.
class NotifPanel : public QFrame {
    Q_OBJECT
  public:
    explicit NotifPanel(QWidget* parent = nullptr);

    /// Repopulate the list from NotificationService::history_snapshot(50).
    void refresh();

    /// Position relative to a reference widget (the bell button).
    void anchor_to(QWidget* ref_widget);

    /// Show one record in full (title, level, source, times, whole message) and
    /// mark it read. Used by row clicks, toast clicks and macOS banner clicks.
    void show_detail(const fincept::notifications::NotificationRecord& record);

  protected:
    void showEvent(QShowEvent* e) override;
    void changeEvent(QEvent* event) override;
    bool eventFilter(QObject* obj, QEvent* e) override;

  private:
    /// Re-apply tr() lookups to header + empty-state text after a language switch.
    void retranslateUi();
    void show_list();
    QString level_name(fincept::notifications::NotifLevel level) const;

    QLabel* title_lbl_ = nullptr;
    QPushButton* mark_all_btn_ = nullptr;
    QWidget* list_container_ = nullptr;
    QVBoxLayout* list_layout_ = nullptr;
    QScrollArea* scroll_ = nullptr;
    QStackedWidget* stack_ = nullptr; ///< page 0: list, page 1: detail

    QPushButton* back_btn_ = nullptr;
    QPushButton* open_btn_ = nullptr;
    QLabel* d_title_ = nullptr;
    QLabel* d_meta_ = nullptr;
    QLabel* d_msg_ = nullptr;
    fincept::notifications::NotificationRecord detail_rec_;

    /// Records behind the rows currently shown; a row's "notif_row" property indexes this.
    QVector<fincept::notifications::NotificationRecord> rows_;

    static constexpr int PANEL_W = 380;
    static constexpr int PANEL_H = 400;
    static constexpr int MAX_ROWS = 50;
};

} // namespace fincept::ui
