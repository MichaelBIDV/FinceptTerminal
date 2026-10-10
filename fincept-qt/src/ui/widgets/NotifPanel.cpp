#include "ui/widgets/NotifPanel.h"

#include "ui/theme/Theme.h"
#include "ui/theme/ThemeManager.h"
#include "ui/widgets/NotifToast.h"

#include <QFontMetrics>
#include <QHBoxLayout>
#include <QLabel>
#include <QMouseEvent>
#include <QPushButton>
#include <QScreen>
#include <QScrollArea>
#include <QShowEvent>
#include <QVBoxLayout>

#include <algorithm>

namespace fincept::ui {

using namespace fincept::notifications;

NotifPanel::NotifPanel(QWidget* parent) : QFrame(parent, Qt::Popup | Qt::FramelessWindowHint) {
    // The press that closes this popup must not be replayed onto the bell,
    // otherwise clicking the bell while open closes and immediately reopens it.
    setAttribute(Qt::WA_NoMouseReplay);
    setFixedSize(PANEL_W, PANEL_H);
    setStyleSheet(QString("QFrame { background: %1; border: 1px solid %2; border-radius: 4px; }")
                      .arg(ui::colors::BG_SURFACE(), ui::colors::BORDER_MED()));

    auto* vl = new QVBoxLayout(this);
    vl->setContentsMargins(0, 0, 0, 0);
    vl->setSpacing(0);

    // ── Header ────────────────────────────────────────────────────────────────
    auto* header = new QWidget;
    header->setFixedHeight(36);
    header->setStyleSheet(
        QString("background: %1; border-bottom: 1px solid %2;").arg(ui::colors::BG_RAISED(), ui::colors::BORDER_MED()));

    auto* hl = new QHBoxLayout(header);
    hl->setContentsMargins(12, 0, 8, 0);

    title_lbl_ = new QLabel(tr("NOTIFICATIONS"));
    title_lbl_->setStyleSheet(
        QString("color: %1; font-size: 11px; font-weight: bold; background: transparent;").arg(ui::colors::AMBER()));
    hl->addWidget(title_lbl_);
    hl->addStretch();

    mark_all_btn_ = new QPushButton(tr("Mark all read"));
    mark_all_btn_->setFlat(true);
    mark_all_btn_->setStyleSheet(
        QString("QPushButton { color: %1; background: transparent; border: none; font-size: 11px; }"
                "QPushButton:hover { color: %2; }")
            .arg(ui::colors::TEXT_SECONDARY(), ui::colors::AMBER()));
    connect(mark_all_btn_, &QPushButton::clicked, this, [this]() {
        NotificationService::instance().mark_all_read();
        refresh();
    });
    hl->addWidget(mark_all_btn_);
    vl->addWidget(header);

    // ── Scroll area ───────────────────────────────────────────────────────────
    scroll_ = new QScrollArea;
    scroll_->setWidgetResizable(true);
    scroll_->setFrameShape(QFrame::NoFrame);
    scroll_->setStyleSheet(QString("QScrollArea { background: transparent; border: none; }"
                                   "QScrollBar:vertical { background: %1; width: 4px; }"
                                   "QScrollBar::handle:vertical { background: %2; }")
                               .arg(ui::colors::BG_SURFACE(), ui::colors::BORDER_MED()));

    list_container_ = new QWidget;
    list_container_->setStyleSheet("background: transparent;");
    list_layout_ = new QVBoxLayout(list_container_);
    list_layout_->setContentsMargins(0, 0, 0, 0);
    list_layout_->setSpacing(0);
    list_layout_->addStretch();

    scroll_->setWidget(list_container_);

    // ── Detail page: one record in full ───────────────────────────────────────
    auto* detail = new QWidget;
    detail->setStyleSheet("background: transparent;");
    auto* dv = new QVBoxLayout(detail);
    dv->setContentsMargins(12, 10, 12, 10);
    dv->setSpacing(8);

    const QString link_btn_css = QString("QPushButton { color: %1; background: transparent; border: none; font-size: 11px; }"
                                         "QPushButton:hover { color: %2; }")
                                     .arg(ui::colors::TEXT_SECONDARY(), ui::colors::AMBER());
    auto* top = new QHBoxLayout;
    top->setContentsMargins(0, 0, 0, 0);
    back_btn_ = new QPushButton(tr("< Back"));
    back_btn_->setFlat(true);
    back_btn_->setCursor(Qt::PointingHandCursor);
    back_btn_->setStyleSheet(link_btn_css);
    connect(back_btn_, &QPushButton::clicked, this, &NotifPanel::show_list);
    top->addWidget(back_btn_);
    top->addStretch();
    open_btn_ = new QPushButton;
    open_btn_->setFlat(true);
    open_btn_->setCursor(Qt::PointingHandCursor);
    open_btn_->setStyleSheet(link_btn_css);
    connect(open_btn_, &QPushButton::clicked, this, [this]() {
        const fincept::notifications::NotificationRecord rec = detail_rec_; // hide() may refresh
        hide();
        notif_ui::open_record(this, rec);
    });
    top->addWidget(open_btn_);
    dv->addLayout(top);

    // Content may come from news feeds or inbox jobs: plain text only, selectable.
    d_title_ = new QLabel;
    d_title_->setTextFormat(Qt::PlainText);
    d_title_->setWordWrap(true);
    d_title_->setTextInteractionFlags(Qt::TextSelectableByMouse);
    d_title_->setStyleSheet(QString("color: %1; font-size: 13px; font-weight: bold; background: transparent;")
                                .arg(ui::colors::TEXT_PRIMARY()));
    dv->addWidget(d_title_);

    d_meta_ = new QLabel;
    d_meta_->setTextFormat(Qt::PlainText);
    d_meta_->setWordWrap(true);
    d_meta_->setStyleSheet(
        QString("color: %1; font-size: 10px; background: transparent;").arg(ui::colors::TEXT_TERTIARY()));
    dv->addWidget(d_meta_);

    auto* msg_scroll = new QScrollArea;
    msg_scroll->setWidgetResizable(true);
    msg_scroll->setFrameShape(QFrame::NoFrame);
    msg_scroll->setStyleSheet(scroll_->styleSheet());
    d_msg_ = new QLabel;
    d_msg_->setTextFormat(Qt::PlainText);
    d_msg_->setWordWrap(true);
    d_msg_->setAlignment(Qt::AlignTop | Qt::AlignLeft);
    d_msg_->setTextInteractionFlags(Qt::TextSelectableByMouse);
    d_msg_->setStyleSheet(
        QString("color: %1; font-size: 12px; background: transparent;").arg(ui::colors::TEXT_SECONDARY()));
    msg_scroll->setWidget(d_msg_);
    dv->addWidget(msg_scroll, 1);

    stack_ = new QStackedWidget;
    stack_->addWidget(scroll_); // 0: list
    stack_->addWidget(detail);  // 1: detail
    vl->addWidget(stack_, 1);

    // While open, follow the service: new records and read-state changes.
    auto& svc = NotificationService::instance();
    connect(&svc, &NotificationService::notification_received, this, [this](const NotificationRecord&) {
        if (isVisible())
            refresh();
    });
    connect(&svc, &NotificationService::unread_count_changed, this, [this](int) {
        if (isVisible())
            refresh();
    });
}

void NotifPanel::showEvent(QShowEvent* e) {
    QFrame::showEvent(e);
    stack_->setCurrentIndex(0); // a bell click opens the list; show_detail() switches after show()
    refresh();
}

void NotifPanel::show_list() {
    stack_->setCurrentIndex(0);
    refresh();
}

QString NotifPanel::level_name(NotifLevel level) const {
    switch (level) {
        case NotifLevel::Warning:
            return tr("Warning");
        case NotifLevel::Alert:
            return tr("Alert");
        case NotifLevel::Critical:
            return tr("Critical");
        case NotifLevel::Info:
            break;
    }
    return tr("Info");
}

void NotifPanel::show_detail(const NotificationRecord& record) {
    detail_rec_ = record;
    const auto& req = record.request;
    d_title_->setText(req.title.trimmed().isEmpty() ? tr("(no title)") : req.title);
    QStringList meta{level_name(req.level)};
    if (!req.source.isEmpty())
        meta << req.source;
    if (req.timestamp.isValid())
        meta << tr("event %1").arg(req.timestamp.toString("dd/MM/yyyy HH:mm"));
    meta << tr("received %1").arg(record.received_at.toString("dd/MM HH:mm:ss"));
    d_meta_->setText(meta.join(QStringLiteral("  ·  ")));
    d_msg_->setText(req.message.trimmed().isEmpty() ? tr("(no details)") : req.message);
    open_btn_->setVisible(!req.action_screen.isEmpty());
    open_btn_->setText(tr("Open %1 >").arg(req.action_screen));
    stack_->setCurrentIndex(1);
    if (record.id != 0 && !record.read)
        NotificationService::instance().mark_read(record.id); // refresh() keeps the detail page
}

void NotifPanel::refresh() {
    // Clear existing rows (keep the stretch at end). Hide first so a row that
    // is only deleteLater()'d cannot take a click meant for the new list.
    while (list_layout_->count() > 1) {
        auto* item = list_layout_->takeAt(0);
        if (item->widget()) {
            item->widget()->hide();
            item->widget()->deleteLater();
        }
        delete item;
    }

    rows_ = NotificationService::instance().history_snapshot(MAX_ROWS);
    if (rows_.isEmpty()) {
        auto* empty = new QLabel(tr("No notifications"));
        empty->setAlignment(Qt::AlignCenter);
        empty->setStyleSheet(QString("color: %1; font-size: 12px; background: transparent; padding: 24px;")
                                 .arg(ui::colors::TEXT_TERTIARY()));
        list_layout_->insertWidget(0, empty);
        return;
    }

    for (int i = 0; i < rows_.size(); ++i) {
        const auto& rec = rows_.at(i);
        const QString dot_color = notif_ui::level_color(rec.request.level);

        auto* row = new QWidget;
        row->setFixedHeight(52);
        row->setCursor(Qt::PointingHandCursor);
        row->setProperty("notif_row", i);
        row->installEventFilter(this);
        row->setStyleSheet(QString("QWidget { background: %1; border-bottom: 1px solid %2; }"
                                   "QWidget:hover { background: %3; }")
                               .arg(rec.read ? ui::colors::BG_SURFACE() : ui::colors::BG_RAISED(),
                                    ui::colors::BORDER_DIM(), ui::colors::BG_HOVER()));

        auto* rl = new QHBoxLayout(row);
        rl->setContentsMargins(12, 6, 12, 6);
        rl->setSpacing(8);

        auto* dot = new QLabel("●");
        dot->setFixedWidth(10);
        dot->setStyleSheet(QString("color: %1; font-size: 9px; background: transparent;").arg(dot_color));
        rl->addWidget(dot, 0, Qt::AlignTop);

        auto* text_col = new QWidget;
        text_col->setStyleSheet("background: transparent;");
        auto* tvl = new QVBoxLayout(text_col);
        tvl->setContentsMargins(0, 0, 0, 0);
        tvl->setSpacing(1);

        // Titles/messages may come from news feeds or inbox jobs: plain text only.
        const int text_w = PANEL_W - 12 * 2 - 10 - 8 * 2 - 60;
        auto* title_lbl = new QLabel;
        title_lbl->setText(QFontMetrics(title_lbl->font()).elidedText(rec.request.title.simplified(), Qt::ElideRight,
                                                                      text_w));
        title_lbl->setTextFormat(Qt::PlainText);
        title_lbl->setStyleSheet(QString("color: %1; font-size: 12px; font-weight: %2; background: transparent;")
                                     .arg(ui::colors::TEXT_PRIMARY(), rec.read ? "normal" : "bold"));
        tvl->addWidget(title_lbl);

        auto* msg_lbl = new QLabel;
        msg_lbl->setTextFormat(Qt::PlainText);
        msg_lbl->setText(QFontMetrics(msg_lbl->font()).elidedText(rec.request.message.simplified(), Qt::ElideRight,
                                                                  text_w));
        msg_lbl->setStyleSheet(
            QString("color: %1; font-size: 11px; background: transparent;").arg(ui::colors::TEXT_SECONDARY()));
        tvl->addWidget(msg_lbl);
        rl->addWidget(text_col, 1);

        auto* time_lbl = new QLabel(rec.received_at.toString("hh:mm:ss"));
        time_lbl->setTextFormat(Qt::PlainText);
        time_lbl->setStyleSheet(
            QString("color: %1; font-size: 10px; background: transparent;").arg(ui::colors::TEXT_TERTIARY()));
        time_lbl->setAlignment(Qt::AlignTop | Qt::AlignRight);
        rl->addWidget(time_lbl);

        list_layout_->insertWidget(list_layout_->count() - 1, row);
    }
}

bool NotifPanel::eventFilter(QObject* obj, QEvent* e) {
    const QVariant idx = obj->property("notif_row");
    if (idx.isValid() && (e->type() == QEvent::MouseButtonPress || e->type() == QEvent::MouseButtonRelease)) {
        auto* me = static_cast<QMouseEvent*>(e);
        if (me->button() != Qt::LeftButton)
            return QFrame::eventFilter(obj, e);
        me->accept();
        if (e->type() == QEvent::MouseButtonRelease) {
            const int i = idx.toInt();
            if (i >= 0 && i < rows_.size()) {
                // Copy first: mark_read() can trigger refresh(), which replaces rows_.
                const NotificationRecord rec = rows_.at(i);
                show_detail(rec); // read the whole record; "Open …" there navigates
            }
        }
        return true;
    }
    return QFrame::eventFilter(obj, e);
}

void NotifPanel::changeEvent(QEvent* event) {
    if (event->type() == QEvent::LanguageChange)
        retranslateUi();
    QFrame::changeEvent(event);
}

void NotifPanel::retranslateUi() {
    if (title_lbl_)
        title_lbl_->setText(tr("NOTIFICATIONS"));
    if (mark_all_btn_)
        mark_all_btn_->setText(tr("Mark all read"));
    if (back_btn_)
        back_btn_->setText(tr("< Back"));
    if (stack_ && stack_->currentIndex() == 1)
        show_detail(detail_rec_);
    // Rebuild the list so the empty-state label (and any future row labels)
    // pick up the new locale.
    refresh();
}

void NotifPanel::anchor_to(QWidget* ref_widget) {
    if (!ref_widget || !ref_widget->parentWidget())
        return;
    const QPoint global_pos = ref_widget->mapToGlobal(QPoint(0, 0));
    int x = global_pos.x() + ref_widget->width() - PANEL_W;
    int y = global_pos.y() - PANEL_H; // opens upward from the status-bar bell
    if (const QScreen* scr = ref_widget->screen()) {
        const QRect avail = scr->availableGeometry();
        if (y < avail.top())
            y = global_pos.y() + ref_widget->height(); // no room above: drop below the bell
        x = std::clamp(x, avail.left(), std::max(avail.left(), avail.right() + 1 - PANEL_W));
        y = std::clamp(y, avail.top(), std::max(avail.top(), avail.bottom() + 1 - PANEL_H));
    }
    move(x, y);
}

} // namespace fincept::ui
