// src/services/news/NewsAlertService.cpp
// Xem NewsAlertService.h: vì sao cảnh báo News chuyển khỏi NewsScreen và chống trùng ra sao.
#include "services/news/NewsAlertService.h"

#include "core/logging/Logger.h"
#include "datahub/DataHub.h"
#include "datahub/DataHubMetaTypes.h"
#include "services/news/NewsClusterService.h"
#include "services/news/NewsMonitorService.h"
#include "services/news/NewsViClassifier.h"
#include "services/news/NewsViText.h"
#include "services/notifications/NotificationService.h"
#include "storage/cache/CacheManager.h"

#include <QDateTime>
#include <QJsonArray>
#include <QJsonDocument>
#include <QJsonObject>
#include <QSet>
#include <QTimer>

#include <algorithm>
#include <cmath>

namespace fincept::services {

namespace {

constexpr int kDebounceMs = 2000;           ///< gom các lần publish dồn dập của fetch progressive
constexpr int64_t kStartGraceSec = 30 * 60; ///< chỉ báo bài đăng sau (khởi động − 30 phút)
constexpr int kDedupeSec = 21600;           ///< 6 giờ (đặc tả thông báo §5)
constexpr int64_t kSeenKeepSec = 7 * 86400; ///< bài cũ hơn đã rời feed: quên khoá trong phiên
constexpr int kMaxHourlySamples = 168;      ///< một tuần mẫu theo giờ
constexpr int kMinHourlySamples = 24;       ///< chưa đủ một ngày mẫu thì chưa chấm độ lệch
constexpr int kBaselineTtlSec = 8 * 86400;  ///< nền DEVIATION trong cache.db: hơn một tuần mẫu
constexpr double kMinStddev = 0.5;
constexpr double kDeviationZ = 3.0;
constexpr double kCriticalZ = 5.0;
const QString kBaselineCacheKey = QStringLiteral("news:alert_baselines");

/// Chấm lại bài bằng bộ phân loại HIỆN HÀNH, đúng luật của NewsService::enrich_article. Nhãn bậc
/// trong cache có thể do bản cũ ghi (bài Guardian thành FLASH vì câu "Get our breaking news email"),
/// mà cache được phát lại lên hub ngay lúc khởi động. Trả cả khoá chống trùng của bài.
NewsArticle rescored(const NewsArticle& a, QString* dedupe_key) {
    const vinews::Classification c = vinews::classify(a.headline, a.summary, a.source, a.category, a.region);
    NewsArticle r = a;
    r.priority = static_cast<Priority>(static_cast<int>(c.priority));
    if (vitext::is_vietnamese(a.headline + QLatin1Char(' ') + a.summary))
        r.impact = static_cast<Impact>(static_cast<int>(c.impact));
    else if (c.is_admin)
        r.impact = Impact::LOW;
    if (dedupe_key)
        *dedupe_key = QStringLiteral("news:") + (c.event_key.isEmpty() ? c.story_key : c.event_key);
    return r;
}

bool more_urgent(Priority a, Priority b) {
    return static_cast<int>(a) < static_cast<int>(b);
}

notifications::NotificationRequest news_request(const NewsArticle& a) {
    notifications::NotificationRequest req;
    req.message = a.summary.isEmpty() ? a.source : a.summary.left(160);
    req.trigger = notifications::NotifTrigger::NewsAlert;
    req.source = QStringLiteral("news");
    req.action_screen = QStringLiteral("news");
    // News alerts stay inside the app: external pushes go through tg_gate, never
    // straight from here to a provider (THONGBAO_SPEC §5).
    req.local_only = true;
    if (a.sort_ts > 0)
        req.timestamp = QDateTime::fromSecsSinceEpoch(a.sort_ts);
    req.dedupe_s = kDedupeSec;
    return req;
}

} // namespace

NewsAlertService& NewsAlertService::instance() {
    static NewsAlertService s;
    return s;
}

NewsAlertService::NewsAlertService() {
    debounce_ = new QTimer(this);
    debounce_->setSingleShot(true);
    debounce_->setInterval(kDebounceMs);
    connect(debounce_, &QTimer::timeout, this, &NewsAlertService::process);
}

void NewsAlertService::start() {
    if (started_)
        return;
    started_ = true;
    since_ts_ = QDateTime::currentSecsSinceEpoch() - kStartGraceSec;
    load_baselines();
    datahub::DataHub::instance().subscribe(this, QStringLiteral("news:general"), [this](const QVariant& v) {
        if (!v.canConvert<QVector<NewsArticle>>())
            return;
        pending_ = v.value<QVector<NewsArticle>>();
        has_pending_ = true;
        // Không khởi động lại bộ đếm: fetch progressive publish liên tục, vẫn phải xử lý mỗi 2 giây.
        if (!debounce_->isActive())
            debounce_->start();
    });
    LOG_INFO("NewsAlertService", QString("Started: alerting on news:general articles published after %1")
                                     .arg(QDateTime::fromSecsSinceEpoch(since_ts_).toString(Qt::ISODate)));
}

void NewsAlertService::process() {
    if (!has_pending_)
        return;
    const QVector<NewsArticle> all = std::move(pending_);
    pending_.clear();
    has_pending_ = false;

    const int64_t now = QDateTime::currentSecsSinceEpoch();
    for (auto it = seen_.begin(); it != seen_.end();) {
        if (it.value() < now - kSeenKeepSec)
            it = seen_.erase(it);
        else
            ++it;
    }
    alerted_.erase(std::remove_if(alerted_.begin(), alerted_.end(),
                                  [now](const AlertedArticle& x) { return x.at < now - kDedupeSec; }),
                   alerted_.end());

    QVector<NewsArticle> fresh;
    for (const auto& a : all) {
        if (a.sort_ts >= since_ts_)
            fresh.append(a);
    }

    alert_urgent(fresh);
    if (notifications::NotificationService::setting_enabled(QStringLiteral("notifications.news_monitors"), true))
        alert_monitors(fresh);
    alert_deviations(all, now);
}

// BREAKING + FLASH: gom các bài FLASH/URGENT mới thành cụm (NewsClusterService đặt bài khẩn nhất
// làm lead của cụm khẩn), MỘT thông báo cho mỗi cụm. Bài khẩn đã xử lý trong 6 giờ qua (alerted_) đi
// TRƯỚC trong đầu vào để làm hạt cụm: bài mới cùng câu chuyện nhập vào cụm cũ và không báo lại, trừ
// khi lead mới khẩn hơn mọi bài đã báo của cụm. Lead FLASH + impact HIGH thì mang nhãn FLASH (công tắc
// news_flash), còn lại mang nhãn BREAKING (công tắc news_breaking).
void NewsAlertService::alert_urgent(const QVector<NewsArticle>& fresh) {
    using namespace fincept::notifications;
    const bool flash_on = NotificationService::setting_enabled(QStringLiteral("notifications.news_flash"), true);
    const bool breaking_on =
        NotificationService::setting_enabled(QStringLiteral("notifications.news_breaking"), true);
    if (!flash_on && !breaking_on)
        return;

    QVector<NewsArticle> urgent;
    QHash<QString, QString> key_of; // article.id → dedupe_key
    for (const auto& a : fresh) {
        // Nhãn đã chấm lúc parse; chỉ bài đang mang nhãn khẩn mới phải chấm lại (nhãn cũ trong cache).
        if (a.priority != Priority::FLASH && a.priority != Priority::URGENT)
            continue;
        if (seen_.contains(QStringLiteral("a:") + a.id))
            continue;
        QString key;
        const NewsArticle r = rescored(a, &key);
        if (r.priority != Priority::FLASH && r.priority != Priority::URGENT)
            continue;
        key_of.insert(r.id, key);
        urgent.append(r);
    }
    if (urgent.isEmpty())
        return;

    QVector<NewsArticle> input;
    QSet<QString> old_ids;
    for (const auto& x : alerted_) {
        input.append(x.article);
        old_ids.insert(x.article.id);
    }
    input += urgent;

    const int64_t now = QDateTime::currentSecsSinceEpoch();
    for (const auto& cluster : get_breaking_clusters(cluster_articles(input))) {
        bool has_old = false;
        Priority old_best = Priority::ROUTINE;
        for (const auto& m : cluster.articles) {
            if (old_ids.contains(m.id)) {
                has_old = true;
                if (more_urgent(m.priority, old_best))
                    old_best = m.priority;
                continue;
            }
            seen_.insert(QStringLiteral("a:") + m.id, m.sort_ts);
            alerted_.append({m, now});
        }

        const NewsArticle& lead = cluster.lead_article;
        if (has_old && (old_ids.contains(lead.id) || !more_urgent(lead.priority, old_best))) {
            if (!old_ids.contains(lead.id))
                LOG_INFO("NewsAlertService",
                         QString("Story already alerted, skipped: %1").arg(lead.headline.left(80)));
            continue;
        }

        // Chỉ FLASH tiếng Việt là Critical: FLASH tiếng Anh đến từ dò chữ "breaking"/"alert".
        const bool vi = vitext::is_vietnamese(lead.headline + QLatin1Char(' ') + lead.summary);
        const NotifLevel flash_level = vi ? NotifLevel::Critical : NotifLevel::Alert;
        NotificationRequest req = news_request(lead);
        if (flash_on && lead.priority == Priority::FLASH && lead.impact == Impact::HIGH) {
            req.title = tr("FLASH: %1").arg(lead.headline.left(80));
            req.level = flash_level;
        } else if (breaking_on) {
            req.title = tr("BREAKING: %1").arg(lead.headline.left(80));
            req.level = lead.priority == Priority::FLASH ? flash_level : NotifLevel::Alert;
        } else {
            continue;
        }
        req.dedupe_key = key_of.value(lead.id);
        NotificationService::instance().send(req);
    }
}

// WATCH: từ khoá của News monitor, trên bài mới, không qua bộ lọc của màn News.
void NewsAlertService::alert_monitors(const QVector<NewsArticle>& fresh) {
    using namespace fincept::notifications;
    auto& monitors_svc = NewsMonitorService::instance();
    const QVector<NewsMonitor> monitors = monitors_svc.get_monitors();
    if (monitors.isEmpty() || fresh.isEmpty())
        return;
    const auto matches = monitors_svc.scan_monitors(monitors, fresh);
    for (const auto& monitor : monitors) {
        if (!monitor.enabled)
            continue;
        for (const auto& article : matches.value(monitor.id)) {
            const QString seen_key = QStringLiteral("m:") + monitor.id + QLatin1Char(':') + article.id;
            if (seen_.contains(seen_key))
                continue;
            seen_.insert(seen_key, article.sort_ts);

            NotificationRequest req = news_request(article);
            req.title = tr("WATCH \"%1\": %2").arg(monitor.label, article.headline.left(70));
            req.level = NotifLevel::Warning;
            req.dedupe_key = QStringLiteral("news:watch:") + monitor.id + QLatin1Char(':') +
                             vinews::story_key(article.headline);
            NotificationService::instance().send(req);
        }
    }
}

// DEVIATION: số bài mỗi category trong giờ vừa qua so với nền theo giờ. Nền cũ của NewsScreen
// thêm một mẫu MỖI LẦN cập nhật giao diện; với nhịp refresh 30 giây thì đủ "24 mẫu" sau ~12 phút
// và z-score mất nghĩa "theo giờ". Ở đây mỗi giờ đồng hồ một mẫu cho MỌI category đã từng thấy
// (giờ không có bài là 0, nếu không mean/stddev lệch lên), mẫu của giờ hiện tại được cập nhật đến hết
// giờ, và nền được lưu bền mỗi khi sang giờ mới.
void NewsAlertService::alert_deviations(const QVector<NewsArticle>& all, int64_t now) {
    using namespace fincept::notifications;
    const int64_t hour_ago = now - 3600;
    const int64_t hour = now / 3600;
    QMap<QString, int> current;
    for (const auto& a : all) {
        if (a.sort_ts >= hour_ago)
            current[a.category]++;
    }

    const bool new_hour = hour != hourly_hour_;
    QStringList categories = hourly_counts_.keys();
    for (auto it = current.cbegin(); it != current.cend(); ++it) {
        if (!hourly_counts_.contains(it.key()))
            categories << it.key();
    }
    for (const auto& cat : categories) {
        QVector<int>& counts = hourly_counts_[cat];
        const int n = current.value(cat, 0);
        if (new_hour || counts.isEmpty()) {
            counts.append(n);
            while (counts.size() > kMaxHourlySamples)
                counts.removeFirst();
        } else {
            counts.last() = n;
        }
    }
    if (new_hour) {
        hourly_hour_ = hour;
        save_baselines();
    }

    if (!NotificationService::setting_enabled(QStringLiteral("notifications.news_deviations"), true))
        return;
    for (auto it = current.cbegin(); it != current.cend(); ++it) {
        const QVector<int>& counts = hourly_counts_.value(it.key());
        if (counts.size() < kMinHourlySamples)
            continue;

        double sum = 0;
        for (int c : counts)
            sum += c;
        const double mean = sum / counts.size();
        double var_sum = 0;
        for (int c : counts)
            var_sum += (c - mean) * (c - mean);
        const double stddev = std::sqrt(var_sum / counts.size());
        if (stddev < kMinStddev)
            continue;
        const double z = (it.value() - mean) / stddev;
        if (z < kDeviationZ || deviation_sent_.value(it.key(), 0) > now - kDedupeSec)
            continue;
        deviation_sent_.insert(it.key(), now);

        NotificationRequest req;
        req.title = tr("DEVIATION: %1 news spike").arg(it.key());
        req.message =
            tr("Unusual volume detected (z-score: %1). More %2 articles than normal.").arg(z, 0, 'f', 1).arg(it.key());
        req.level = z >= kCriticalZ ? NotifLevel::Critical : NotifLevel::Warning;
        req.trigger = NotifTrigger::NewsAlert;
        req.source = QStringLiteral("news");
        req.action_screen = QStringLiteral("news");
        req.dedupe_key = QStringLiteral("news:deviation:") + it.key();
        req.dedupe_s = kDedupeSec;
        req.local_only = true;
        NotificationService::instance().send(req);
    }
}

// Nền DEVIATION trong cache.db: {"v":1,"hour":<unix s / 3600>,"counts":{"<category>":[n,…]}}.
// Nền cũ hơn một tuần mẫu thì bỏ: thói quen đăng bài của các feed đã khác.
void NewsAlertService::load_baselines() {
    const auto cached = CacheManager::instance().try_get(kBaselineCacheKey);
    if (!cached)
        return;
    const QJsonObject o = QJsonDocument::fromJson(cached->toUtf8()).object();
    const int64_t hour = o.value(QStringLiteral("hour")).toInteger(-1);
    const int64_t now_hour = QDateTime::currentSecsSinceEpoch() / 3600;
    if (o.value(QStringLiteral("v")).toInt() != 1 || hour <= 0 || hour > now_hour ||
        now_hour - hour > kMaxHourlySamples) {
        LOG_INFO("NewsAlertService", "Deviation baseline in cache is stale or unreadable, starting fresh");
        return;
    }
    const QJsonObject counts = o.value(QStringLiteral("counts")).toObject();
    int samples = 0;
    for (auto it = counts.constBegin(); it != counts.constEnd(); ++it) {
        QVector<int> v;
        for (const auto& c : it.value().toArray())
            v.append(std::max(0, c.toInt()));
        while (v.size() > kMaxHourlySamples)
            v.removeFirst();
        if (!v.isEmpty()) {
            samples = std::max(samples, int(v.size()));
            hourly_counts_.insert(it.key(), v);
        }
    }
    hourly_hour_ = hour;
    LOG_INFO("NewsAlertService", QString("Deviation baseline restored: %1 categories, up to %2 hourly samples")
                                     .arg(hourly_counts_.size())
                                     .arg(samples));
}

void NewsAlertService::save_baselines() const {
    QJsonObject counts;
    for (auto it = hourly_counts_.cbegin(); it != hourly_counts_.cend(); ++it) {
        QJsonArray arr;
        for (int c : it.value())
            arr.append(c);
        counts.insert(it.key(), arr);
    }
    const QJsonObject o{{QStringLiteral("v"), 1},
                        {QStringLiteral("hour"), static_cast<qint64>(hourly_hour_)},
                        {QStringLiteral("counts"), counts}};
    CacheManager::instance().put(kBaselineCacheKey,
                                 QString::fromUtf8(QJsonDocument(o).toJson(QJsonDocument::Compact)),
                                 kBaselineTtlSec, QStringLiteral("news"));
}

} // namespace fincept::services
