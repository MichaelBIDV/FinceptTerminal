// src/ui/notifications/DesktopNotifier.cpp
#include "ui/notifications/DesktopNotifier.h"

#include "app/WindowFrame.h"
#include "auth/InactivityGuard.h"
#include "core/keys/WindowCycler.h"
#include "core/logging/Logger.h"
#include "ui/notifications/MacUserNotifier.h"
#include "ui/notifications/NotificationService.h" // ToastService
#include "ui/widgets/NotifToast.h"                 // notif_ui::open_record

#include <QApplication>
#include <QDateTime>
#include <QGuiApplication>
#include <QIcon>
#include <QLabel>
#include <QMenu>
#include <QScreen>
#include <QStyle>
#include <QSystemTrayIcon>
#include <QTimer>
#include <QVBoxLayout>
#include <QWidget>

#include <utility>

namespace fincept::ui {

DesktopNotifier& DesktopNotifier::instance() {
    static DesktopNotifier s;
    return s;
}

void DesktopNotifier::init() {
    if (initialised_)
        return;
    initialised_ = true;

#if defined(Q_OS_MACOS)
    // No menu-bar icon on macOS: banners go through UNUserNotificationCenter, and
    // clicking the Qt 6.8.3 status item crashes on macOS 27 (QCocoaSystemTrayIcon::
    // emitActivated -> [NSEvent clickCount] assertion, abort at 03/10 22:34).
    const bool use_tray = false;
#else
    const bool use_tray = QSystemTrayIcon::isSystemTrayAvailable();
    if (!use_tray)
        LOG_WARN("DesktopNotifier", "No system tray available, native banners disabled");
#endif
    if (use_tray) {
        tray_ = new QSystemTrayIcon(this);
        QIcon ico = QApplication::windowIcon();
        if (ico.isNull())
            ico = qApp->style()->standardIcon(QStyle::SP_MessageBoxInformation);
        tray_->setIcon(ico);
        tray_->setToolTip(QStringLiteral("Fincept Terminal"));

        auto* menu = new QMenu();
        menu->addAction(QStringLiteral("Show Fincept"), this, [this]() { raise_main_window(); });
        menu->addSeparator();
        menu->addAction(QStringLiteral("Quit"), qApp, &QApplication::quit);
        tray_->setContextMenu(menu);
        tray_->show();

        // Clicking a banner brings the terminal forward.
        connect(tray_, &QSystemTrayIcon::messageClicked, this, &DesktopNotifier::raise_main_window);
    }

    // macOS: real banners go through UNUserNotificationCenter (the tray API above
    // is registered but never delivered on macOS 27). A clicked banner carries its
    // record id, so it opens that record like a click on the toast or the panel.
    fincept::ui::macnotify::init([this](qint64 record_id) {
        LOG_INFO("DesktopNotifier", QString("Banner clicked: record #%1").arg(record_id));
        raise_main_window();
        if (record_id <= 0)
            return;
        auto& svc = fincept::notifications::NotificationService::instance();
        for (const auto& rec : svc.history_snapshot(200)) {
            if (rec.id == record_id) {
                // Let the window come forward first, then show the record in full.
                QTimer::singleShot(150, this, [rec]() {
                    notif_ui::show_record(WindowCycler::instance().focused_frame(), rec);
                });
                return;
            }
        }
        svc.mark_read(record_id); // older than the in-memory window: at least clear it
    });
    // Ask for banner permission now, while the user is at the machine, rather than
    // on the first background alert (THONGBAO_SPEC §4).
    if (fincept::notifications::NotificationService::setting_enabled(QStringLiteral("notifications.desktop"), true))
        fincept::ui::macnotify::request_authorization();
    // Terminal lock: nothing readable may remain in Notification Center.
    connect(&auth::InactivityGuard::instance(), &auth::InactivityGuard::terminal_locked_changed, this,
            [](bool locked) {
                if (locked)
                    fincept::ui::macnotify::clear_delivered();
            });

    // ToastService carries transient UI errors (CommandPalette, QuickCommandBar,
    // ErrorPipeline): in-app window only, never an OS banner. Alerts reach the OS
    // through NotificationService below.
    connect(&ToastService::instance(), &ToastService::posted, this, [this](const ToastService::Notification& n) {
        show_inapp(QStringLiteral("Fincept Terminal"), n.message, static_cast<int>(n.severity));
    });

    burst_clock_.start();
    burst_timer_ = new QTimer(this);
    burst_timer_->setSingleShot(true);
    burst_timer_->setInterval(static_cast<int>(desktop_policy::kBurstWindowMs));
    connect(burst_timer_, &QTimer::timeout, this, &DesktopNotifier::flush_burst);

    // Core notification system. main.cpp constructs it just before init(), on the
    // GUI thread after Database::open(); instance() here only fetches it.
    auto& svc = fincept::notifications::NotificationService::instance();
    connect(&svc, &fincept::notifications::NotificationService::notification_received, this,
            &DesktopNotifier::on_core_notification);
    connect(&svc, &fincept::notifications::NotificationService::unread_count_changed, this,
            &DesktopNotifier::on_unread_changed);
    on_unread_changed(svc.unread_count());

    LOG_INFO("DesktopNotifier", "Native desktop notifications enabled");
}

void DesktopNotifier::notify(const QString& title, const QString& body, fincept::notifications::NotifLevel level,
                             qint64 record_id) {
    using fincept::notifications::NotifLevel;
    if (fincept::ui::macnotify::available()) {
        LOG_INFO("DesktopNotifier", QString("Banner requested (UN): %1").arg(title.left(60)));
        // Fallback (not authorized / delivery error): the legacy tray path.
        fincept::ui::macnotify::post(record_id, title, body, level == NotifLevel::Critical,
                                     [this, title, body, level]() { notify_tray(title, body, level); });
        return;
    }
    notify_tray(title, body, level);
}

void DesktopNotifier::notify_tray(const QString& title, const QString& body,
                                  fincept::notifications::NotifLevel level) {
    using fincept::notifications::NotifLevel;
    if (!tray_ || !QSystemTrayIcon::supportsMessages())
        return;
    QSystemTrayIcon::MessageIcon icon = QSystemTrayIcon::Information;
    switch (level) {
        case NotifLevel::Warning:
        case NotifLevel::Alert:
            icon = QSystemTrayIcon::Warning;
            break;
        case NotifLevel::Critical:
            icon = QSystemTrayIcon::Critical;
            break;
        case NotifLevel::Info:
            break;
    }
    // One INFO line per OS banner: the only on-disk trace that a banner was requested
    // (macOS gives no delivery callback for this legacy API).
    LOG_INFO("DesktopNotifier", QString("Banner requested (tray): %1").arg(title.left(60)));
    tray_->showMessage(title, body, icon, 30000);
}

void DesktopNotifier::on_core_notification(const fincept::notifications::NotificationRecord& rec) {
    using fincept::notifications::NotificationService;
    using fincept::notifications::NotifLevel;
    const auto& req = rec.request;
    const bool critical = req.level == NotifLevel::Critical;
    const desktop_policy::Gate g = desktop_policy::gate(
        NotificationService::setting_enabled(QStringLiteral("notifications.desktop"), true),
        in_app_covers(), critical, rec.received_at, req.timestamp,
        QDateTime::currentDateTime());
    if (g != desktop_policy::Gate::Show) {
        LOG_DEBUG("DesktopNotifier", QString("No banner for #%1 (%2)")
                                         .arg(rec.id)
                                         .arg(QLatin1String(desktop_policy::gate_name(g))));
        return;
    }

    if (!burst_.admit(burst_clock_.elapsed())) {
        ++burst_pending_;
        burst_critical_ = burst_critical_ || critical;
        burst_last_ = rec;
        if (!burst_timer_->isActive())
            burst_timer_->start();
        return;
    }
    show_banner(rec);
}

void DesktopNotifier::show_banner(const fincept::notifications::NotificationRecord& rec) {
    const auto& req = rec.request;
    if (auth::InactivityGuard::instance().is_terminal_locked()) {
        notify(QStringLiteral("Fincept Terminal"), count_text(1), req.level); // no content while locked
        return;
    }
    const QString title = req.title.trimmed().isEmpty() ? QStringLiteral("Fincept Terminal") : req.title;
    notify(title, desktop_policy::banner_body(req.message), req.level, rec.id);
}

void DesktopNotifier::flush_burst() {
    using fincept::notifications::NotificationService;
    using fincept::notifications::NotifLevel;
    const int n = std::exchange(burst_pending_, 0);
    const bool critical = std::exchange(burst_critical_, false);
    if (n <= 0)
        return;
    // Re-check what may have changed while the burst was folding.
    if (!NotificationService::setting_enabled(QStringLiteral("notifications.desktop"), true))
        return;
    if (in_app_covers() && !critical)
        return; // the user is back in the app: bell + toast cover it
    if (n == 1) {
        show_banner(burst_last_); // nothing to fold: show the record itself
        return;
    }
    notify(QStringLiteral("Fincept Terminal"), count_text(n), critical ? NotifLevel::Critical : NotifLevel::Info);
}

void DesktopNotifier::on_unread_changed(int count) {
#if QT_VERSION >= QT_VERSION_CHECK(6, 5, 0)
    qApp->setBadgeNumber(count); // Dock badge = unread (THONGBAO_SPEC §4)
#else
    Q_UNUSED(count);
#endif
}

void DesktopNotifier::raise_main_window() {
    QWidget* w = WindowCycler::instance().focused_frame();
    if (!w)
        return;
    // De-minimise without dropping a maximised / full-screen state.
    w->setWindowState((w->windowState() & ~Qt::WindowMinimized) | Qt::WindowActive);
    w->show();
    w->raise();
    w->activateWindow();
}

bool DesktopNotifier::in_app_covers() {
    // "Active" alone is not enough on macOS: after Cmd+M the app stays active with no
    // visible window, and with In-App toasts off nothing would show the record.
    if (QGuiApplication::applicationState() != Qt::ApplicationActive)
        return false;
    QWidget* w = QApplication::activeWindow();
    if (!w || w->isMinimized())
        return false;
    return fincept::notifications::NotificationService::setting_enabled(QStringLiteral("notifications.inapp"), true);
}

QString DesktopNotifier::count_text(int n) {
    return n == 1 ? tr("1 new notification") : tr("%1 new notifications").arg(n);
}

void DesktopNotifier::show_inapp(const QString& title, const QString& body, int severity) {
    QString accent = QStringLiteral("#00BFA5");
    switch (static_cast<ToastService::Severity>(severity)) {
        case ToastService::Severity::Warning:
            accent = QStringLiteral("#FFC400");
            break;
        case ToastService::Severity::Error:
            accent = QStringLiteral("#FF5252");
            break;
        case ToastService::Severity::Success:
            accent = QStringLiteral("#26C281");
            break;
        default:
            break;
    }
    if (!toast_) {
        toast_ = new QWidget(nullptr, Qt::ToolTip | Qt::FramelessWindowHint | Qt::WindowStaysOnTopHint);
        toast_->setAttribute(Qt::WA_ShowWithoutActivating);
        toast_->setFixedWidth(360);
        auto* lay = new QVBoxLayout(toast_);
        lay->setContentsMargins(14, 12, 14, 12);
        toast_lbl_ = new QLabel(toast_);
        toast_lbl_->setTextFormat(Qt::RichText);
        toast_lbl_->setWordWrap(true);
        lay->addWidget(toast_lbl_);
        toast_timer_ = new QTimer(this);
        toast_timer_->setSingleShot(true);
        connect(toast_timer_, &QTimer::timeout, toast_, [this]() {
            if (toast_)
                toast_->hide();
        });
    }
    toast_->setStyleSheet(QString("background:#15181d; border:1px solid %1; border-radius:8px;").arg(accent));
    toast_lbl_->setStyleSheet(QStringLiteral("color:#e6e6e6; font-size:12px; background:transparent; border:none;"));
    toast_lbl_->setText(QString("<b style='color:%1; font-size:13px;'>%2</b><br><span>%3</span>")
                            .arg(accent, title.toHtmlEscaped(), body.toHtmlEscaped()));
    toast_->adjustSize();
    if (auto* scr = QGuiApplication::primaryScreen()) {
        const QRect g = scr->availableGeometry();
        toast_->move(g.right() - toast_->width() - 24, g.top() + 24);
    }
    toast_->show();
    toast_->raise();
    toast_timer_->start(20000); // stay ~20s on screen
}

} // namespace fincept::ui
