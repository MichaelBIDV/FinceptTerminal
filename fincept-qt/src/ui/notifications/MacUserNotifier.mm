// src/ui/notifications/MacUserNotifier.mm: UNUserNotificationCenter banners (macOS).
// Built with -fobjc-arc, outside the unity build and the C++ PCH (CMakeLists.txt).
#include "ui/notifications/MacUserNotifier.h"

#include "core/logging/Logger.h"

#include <QCoreApplication>

#include <atomic>
#include <memory>

#import <Foundation/Foundation.h>
#import <UserNotifications/UserNotifications.h>
#include <dispatch/dispatch.h>

namespace {
std::function<void(qint64)> g_on_click;
std::atomic<bool> g_auth_pending{false};
std::atomic<int> g_last_status{-1}; ///< last UNAuthorizationStatus seen, for log-on-change

/// Run fn on the GUI thread. UN completion handlers fire on a background queue;
/// Qt's GUI thread on macOS is the main dispatch queue, so no QObject is used as a
/// context (posting into qApp while ~QApplication runs would be a use-after-free).
void on_gui(std::function<void()> fn) {
    auto f = std::make_shared<std::function<void()>>(std::move(fn));
    dispatch_async(dispatch_get_main_queue(), ^{
      if (QCoreApplication::instance() && !QCoreApplication::closingDown())
          (*f)();
    });
}

void note_status(UNAuthorizationStatus status) {
    const int s = static_cast<int>(status);
    if (g_last_status.exchange(s) == s)
        return; // log only when the permission state changes, not once per banner
    on_gui([s]() {
        if (s == static_cast<int>(UNAuthorizationStatusDenied))
            LOG_WARN("MacUserNotifier", "Banners are turned off for Fincept Terminal in System Settings > "
                                        "Notifications; alerts stay in the bell and toast");
        else
            LOG_INFO("MacUserNotifier", QString("Notification permission status: %1").arg(s));
    });
}
} // namespace

@interface FinceptUNDelegate : NSObject <UNUserNotificationCenterDelegate>
@end

@implementation FinceptUNDelegate
- (void)userNotificationCenter:(UNUserNotificationCenter*)center
       willPresentNotification:(UNNotification*)notification
         withCompletionHandler:(void (^)(UNNotificationPresentationOptions))handler {
    // Only called while the app is in the foreground. DesktopNotifier posts
    // non-Critical banners only from the background, but a post can land after the
    // user came back: re-apply the policy here (Notification Center list only).
    NSNumber* critical = notification.request.content.userInfo[@"critical"];
    if (critical.boolValue)
        handler(UNNotificationPresentationOptionBanner | UNNotificationPresentationOptionList |
                UNNotificationPresentationOptionSound);
    else
        handler(UNNotificationPresentationOptionList);
}

- (void)userNotificationCenter:(UNUserNotificationCenter*)center
    didReceiveNotificationResponse:(UNNotificationResponse*)response
             withCompletionHandler:(void (^)(void))handler {
    NSNumber* rid = response.notification.request.content.userInfo[@"record_id"];
    const qint64 id = rid ? rid.longLongValue : 0;
    on_gui([id]() {
        if (g_on_click)
            g_on_click(id);
    });
    handler();
}
@end

namespace {
FinceptUNDelegate* g_delegate = nil; // UNUserNotificationCenter.delegate is weak: keep it alive
} // namespace

namespace fincept::ui::macnotify {

bool available() {
    NSBundle* b = [NSBundle mainBundle];
    return b.bundleIdentifier.length > 0 && [b.bundlePath hasSuffix:@".app"];
}

void init(std::function<void(qint64)> on_click) {
    g_on_click = std::move(on_click);
    if (!available() || g_delegate)
        return;
    g_delegate = [FinceptUNDelegate new];
    [UNUserNotificationCenter currentNotificationCenter].delegate = g_delegate;
    LOG_INFO("MacUserNotifier", "UNUserNotificationCenter delegate installed");
}

void request_authorization() {
    if (!available() || g_auth_pending.exchange(true))
        return; // one prompt at a time
    UNUserNotificationCenter* center = [UNUserNotificationCenter currentNotificationCenter];
    [center getNotificationSettingsWithCompletionHandler:^(UNNotificationSettings* settings) {
      if (settings.authorizationStatus != UNAuthorizationStatusNotDetermined) {
          note_status(settings.authorizationStatus);
          g_auth_pending = false;
          return;
      }
      [center requestAuthorizationWithOptions:(UNAuthorizationOptionAlert | UNAuthorizationOptionSound)
                            completionHandler:^(BOOL granted, NSError* error) {
                              note_status(granted ? UNAuthorizationStatusAuthorized : UNAuthorizationStatusDenied);
                              if (error) {
                                  const QString why = QString::fromNSString(error.localizedDescription);
                                  on_gui([why]() { LOG_WARN("MacUserNotifier", "Permission request failed: " + why); });
                              }
                              g_auth_pending = false;
                            }];
    }];
}

void post(qint64 record_id, const QString& title, const QString& body, bool critical,
          std::function<void()> fallback) {
    auto fb = std::make_shared<std::function<void()>>(std::move(fallback));
    if (!available()) {
        if (*fb)
            (*fb)();
        return;
    }

    UNUserNotificationCenter* center = [UNUserNotificationCenter currentNotificationCenter];
    NSString* ns_title = title.toNSString();
    NSString* ns_body = body.toNSString();

    [center getNotificationSettingsWithCompletionHandler:^(UNNotificationSettings* settings) {
      const UNAuthorizationStatus status = settings.authorizationStatus;
      note_status(status);
      if (status == UNAuthorizationStatusNotDetermined) {
          // Never hold a banner across the permission prompt: it could fire long
          // after the policy checks ran (stale, folded burst, terminal locked). The
          // record is already in the bell; ask once and drop this banner.
          request_authorization();
          return;
      }
      if (status != UNAuthorizationStatusAuthorized && status != UNAuthorizationStatusProvisional)
          return; // the user turned banners off: no tray fallback, it shares the same permission

      UNMutableNotificationContent* content = [UNMutableNotificationContent new];
      content.title = ns_title;
      content.body = ns_body;
      content.sound = [UNNotificationSound defaultSound];
      // Temporary (negative) record ids restart every session: a banner left in
      // Notification Center could otherwise open an unrelated record later.
      NSMutableDictionary* info = [NSMutableDictionary dictionaryWithObject:@(critical) forKey:@"critical"];
      if (record_id > 0)
          info[@"record_id"] = @(record_id);
      content.userInfo = info;
      // No interruptionLevel: time-sensitive needs an entitlement an ad-hoc
      // signature cannot carry, and macOS silently downgrades it anyway.
      NSString* ident = [NSString stringWithFormat:@"fincept-%lld-%@", (long long)record_id, [NSUUID UUID].UUIDString];
      UNNotificationRequest* request = [UNNotificationRequest requestWithIdentifier:ident content:content trigger:nil];
      [center addNotificationRequest:request
               withCompletionHandler:^(NSError* error) {
                 if (!error)
                     return;
                 const QString why = QString::fromNSString(error.localizedDescription);
                 on_gui([fb, why]() {
                     LOG_WARN("MacUserNotifier", QString("Banner not delivered (%1); tray fallback").arg(why));
                     if (*fb)
                         (*fb)();
                 });
               }];
    }];
}

void clear_delivered() {
    if (!available())
        return;
    UNUserNotificationCenter* center = [UNUserNotificationCenter currentNotificationCenter];
    [center removeAllDeliveredNotifications];
    [center removeAllPendingNotificationRequests];
}

} // namespace fincept::ui::macnotify
