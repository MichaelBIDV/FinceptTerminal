#include "ui/widgets/NotifToast.h"

#include "app/DockScreenRouter.h"
#include "app/WindowFrame.h"
#include "core/logging/Logger.h"
#include "ui/theme/Theme.h"
#include "ui/theme/ThemeManager.h"
#include "ui/widgets/NotifBell.h"
#include "ui/widgets/NotifToastPolicy.h"

#include <QChildEvent>
#include <QFontMetrics>
#include <QHBoxLayout>
#include <QHideEvent>
#include <QMouseEvent>
#include <QPainter>
#include <QPropertyAnimation>
#include <QShowEvent>
#include <QVBoxLayout>

#include <algorithm>

namespace fincept::ui {

using namespace fincept::notifications;

NotifToast::NotifToast(QWidget* parent) : QWidget(parent) {
    // Child widget, not a Qt::ToolTip window: move() works in parent coordinates,
    // the toast travels with its window and hides with the page it sits on.
    setAttribute(Qt::WA_TranslucentBackground);
    setFixedSize(TOAST_W, TOAST_H);
    setCursor(Qt::PointingHandCursor);
    hide();

    // ── Layout ────────────────────────────────────────────────────────────────
    auto* outer = new QHBoxLayout(this);
    outer->setContentsMargins(12, 10, 12, 10);
    outer->setSpacing(10);

    level_dot_ = new QLabel("●");
    level_dot_->setFixedSize(10, 10);
    outer->addWidget(level_dot_, 0, Qt::AlignTop | Qt::AlignHCenter);

    auto* text_col = new QWidget;
    text_col->setStyleSheet("background: transparent;");
    auto* tvl = new QVBoxLayout(text_col);
    tvl->setContentsMargins(0, 0, 0, 0);
    tvl->setSpacing(2);

    // Titles and messages can come from outside the app (news feeds, inbox
    // jobs): never let QLabel's AutoText interpret them as rich text.
    title_lbl_ = new QLabel;
    title_lbl_->setTextFormat(Qt::PlainText);
    title_lbl_->setWordWrap(false);
    tvl->addWidget(title_lbl_);

    msg_lbl_ = new QLabel;
    msg_lbl_->setTextFormat(Qt::PlainText);
    msg_lbl_->setWordWrap(true);
    tvl->addWidget(msg_lbl_);

    outer->addWidget(text_col, 1);

    time_lbl_ = new QLabel;
    time_lbl_->setTextFormat(Qt::PlainText);
    time_lbl_->setAlignment(Qt::AlignTop | Qt::AlignRight);
    outer->addWidget(time_lbl_, 0, Qt::AlignTop);

    // ── Timers & animation (P3: start only in showEvent) ─────────────────────
    auto_dismiss_ = new QTimer(this);
    auto_dismiss_->setSingleShot(true);
    auto_dismiss_->setInterval(notif_toast_policy::dismiss_ms(NotifLevel::Info));
    connect(auto_dismiss_, &QTimer::timeout, this, &NotifToast::dismiss);

    slide_anim_ = new QPropertyAnimation(this, "pos", this);
    slide_anim_->setDuration(ANIM_MS);
    slide_anim_->setEasingCurve(QEasingCurve::OutCubic);
    // Permanent connection gated by dismissing_. stop() never emits finished(),
    // so a slide-out interrupted by a new record cannot leave a pending hide().
    connect(slide_anim_, &QPropertyAnimation::finished, this, [this]() {
        if (!dismissing_)
            return;
        dismissing_ = false;
        hide();
    });

    if (parent)
        parent->installEventFilter(this);

    connect(&ThemeManager::instance(), &ThemeManager::theme_changed, this,
            [this](const ThemeTokens&) { refresh_theme(); });
    refresh_theme();
}

// ── Slot ──────────────────────────────────────────────────────────────────────

void NotifToast::show_notification(const NotificationRecord& record) {
    // A parent that is not on screen would replay this record later, when the
    // parent is shown again. Drop it instead.
    if (parentWidget() && !parentWidget()->isVisible())
        return;

    const bool burst = isVisible();
    current_ = record;
    extra_count_ = burst ? extra_count_ + 1 : 0;

    // Fixed-size toast: elide instead of letting a long title run past the edge or a
    // wrapped message spill into a clipped third line. The full text stays in the panel.
    const int text_w = std::max(60, TOAST_W - 24 - 10 - 20 - time_lbl_->sizeHint().width());
    const QFontMetrics title_fm(title_lbl_->font());
    title_lbl_->setText(title_fm.elidedText(record.request.title.simplified(), Qt::ElideRight, text_w));
    const QFontMetrics msg_fm(msg_lbl_->font());
    msg_lbl_->setMaximumHeight(2 * msg_fm.lineSpacing());
    msg_lbl_->setText(msg_fm.elidedText(record.request.message.simplified(), Qt::ElideRight,
                                        2 * text_w - 4 * msg_fm.averageCharWidth()));
    update_time_label();
    refresh_theme(); // dot + accent bar follow the newest record's level
    auto_dismiss_->setInterval(notif_toast_policy::dismiss_ms(record.request.level));

    if (burst) {
        // Cancel a slide-out in progress and restart the countdown for the newest record.
        dismissing_ = false;
        slide_anim_->stop();
        move(shown_pos());
        auto_dismiss_->start();
    } else {
        move(hidden_pos());
        show(); // showEvent slides in and starts auto_dismiss_
    }
    raise();
}

// ── Events ────────────────────────────────────────────────────────────────────

void NotifToast::showEvent(QShowEvent* e) {
    QWidget::showEvent(e);
    dismissing_ = false;
    slide_anim_->stop();
    slide_anim_->setStartValue(hidden_pos());
    slide_anim_->setEndValue(shown_pos());
    slide_anim_->start();
    auto_dismiss_->start();
}

void NotifToast::hideEvent(QHideEvent* e) {
    QWidget::hideEvent(e);
    // hide() in the constructor delivers a hide event before the timer and the
    // animation exist (crash 03/10 18:54), so both may still be null here.
    if (auto_dismiss_)
        auto_dismiss_->stop();
    if (slide_anim_)
        slide_anim_->stop();
    dismissing_ = false;
    extra_count_ = 0;
    // Hidden together with an ancestor (lock screen, auth page, chat mode, tab
    // switch): turn it into an explicit hide so the stale toast does not slide
    // back in when that ancestor is shown again.
    if (!isHidden())
        QTimer::singleShot(0, this, [this]() {
            if (!isHidden())
                hide();
        });
}

void NotifToast::mousePressEvent(QMouseEvent* e) {
    if (e->button() == Qt::LeftButton) {
        e->accept();
        return;
    }
    QWidget::mousePressEvent(e);
}

void NotifToast::mouseReleaseEvent(QMouseEvent* e) {
    if (e->button() == Qt::LeftButton && rect().contains(e->position().toPoint())) {
        const NotificationRecord rec = current_;
        hide();
        notif_ui::show_record(this, rec);
        e->accept();
        return;
    }
    QWidget::mouseReleaseEvent(e);
}

bool NotifToast::eventFilter(QObject* obj, QEvent* e) {
    if (obj == parentWidget()) {
        if (e->type() == QEvent::Resize) {
            reposition();
        } else if (e->type() == QEvent::ChildAdded && isVisible() &&
                   static_cast<QChildEvent*>(e)->child()->isWidgetType()) {
            // ADS swaps the root splitter of dock_manager_ (a dock placed in a new
            // direction, restoreState); the new splitter lands on top of the z-order
            // and would bury a visible toast. Re-raise once the swap has finished.
            QTimer::singleShot(0, this, [this]() {
                if (isVisible())
                    raise();
            });
        }
    }
    return QWidget::eventFilter(obj, e);
}

void NotifToast::paintEvent(QPaintEvent*) {
    QPainter p(this);
    p.setRenderHint(QPainter::Antialiasing);

    // Background
    p.setPen(Qt::NoPen);
    p.setBrush(QColor(colors::BG_SURFACE.get()));
    p.drawRoundedRect(rect(), 6, 6);

    // Left accent bar
    p.setBrush(QColor(notif_ui::level_color(current_.request.level)));
    p.drawRoundedRect(0, 0, 3, height(), 2, 2);

    // Border
    p.setBrush(Qt::NoBrush);
    p.setPen(QPen(QColor(colors::BORDER_MED.get()), 1));
    p.drawRoundedRect(rect().adjusted(0, 0, -1, -1), 6, 6);
}

// ── Private ───────────────────────────────────────────────────────────────────

QPoint NotifToast::shown_pos() const {
    if (!parentWidget())
        return pos();
    return QPoint(std::max(0, parentWidget()->width() - TOAST_W - MARGIN), TOP_OFFSET);
}

QPoint NotifToast::hidden_pos() const {
    if (!parentWidget())
        return pos();
    return QPoint(parentWidget()->width() + 10, TOP_OFFSET);
}

void NotifToast::reposition() {
    if (!isVisible())
        return;
    if (dismissing_) {
        hide(); // already leaving; finishing the slide toward a stale x is pointless
        return;
    }
    slide_anim_->stop();
    move(shown_pos());
}

void NotifToast::dismiss() {
    if (!isVisible()) {
        hide();
        return;
    }
    // Slide back out to the right; the finished() handler hides the toast.
    dismissing_ = true;
    slide_anim_->stop();
    slide_anim_->setStartValue(pos());
    slide_anim_->setEndValue(hidden_pos());
    slide_anim_->start();
}

void NotifToast::refresh_theme() {
    level_dot_->setStyleSheet(QString("color: %1; background: transparent; font-size: 10px;")
                                  .arg(notif_ui::level_color(current_.request.level)));
    title_lbl_->setStyleSheet(QString("color: %1; font-size: 13px; font-weight: bold; background: transparent;")
                                  .arg(colors::TEXT_PRIMARY.get()));
    msg_lbl_->setStyleSheet(
        QString("color: %1; font-size: 12px; background: transparent;").arg(colors::TEXT_SECONDARY.get()));
    time_lbl_->setStyleSheet(
        QString("color: %1; font-size: 10px; background: transparent;").arg(colors::TEXT_TERTIARY.get()));
    update();
}

void NotifToast::update_time_label() {
    const QString time = current_.request.timestamp.toString("hh:mm:ss");
    time_lbl_->setText(extra_count_ > 0 ? QString("%1\n+%2").arg(time).arg(extra_count_) : time);
}

// ── Shared helpers (NotifToast + NotifPanel) ─────────────────────────────────

namespace notif_ui {

QString level_color(NotifLevel level) {
    switch (level) {
        case NotifLevel::Warning:
            return colors::WARNING.get();
        case NotifLevel::Alert:
            return colors::AMBER.get();
        case NotifLevel::Critical:
            return colors::NEGATIVE.get();
        default:
            return colors::CYAN.get();
    }
}

void open_record(QWidget* from, const NotificationRecord& record) {
    // id < 0: a record the DB could not persist; the service still flips it in RAM.
    if (record.id != 0 && !record.read)
        fincept::notifications::NotificationService::instance().mark_read(record.id);

    const QString screen = record.request.action_screen;
    if (screen.isEmpty())
        return;

    WindowFrame* frame = nullptr;
    for (QWidget* w = from; w && !frame; w = w->parentWidget())
        frame = qobject_cast<WindowFrame*>(w);
    if (!frame || frame->is_locked() || !frame->dock_router())
        return;

    auto* router = frame->dock_router();
    if (!router->all_screen_ids().contains(screen)) {
        LOG_WARN("NotifToast", "Notification action_screen is not a registered screen: " + screen);
        return;
    }
    router->navigate(screen);
}

void show_record(QWidget* from, const NotificationRecord& record) {
    WindowFrame* frame = nullptr;
    for (QWidget* w = from; w && !frame; w = w->parentWidget())
        frame = qobject_cast<WindowFrame*>(w);
    if (frame && !frame->is_locked()) {
        if (auto* bell = frame->findChild<NotifBell*>(); bell && bell->isVisible()) {
            bell->open_detail(record);
            return;
        }
    }
    open_record(from, record);
}

} // namespace notif_ui

} // namespace fincept::ui
