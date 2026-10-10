// src/services/news/NewsAlertService.h
// Cảnh báo News ở MỨC APP: BREAKING / FLASH / WATCH / DEVIATION.
//
// Trước đây bốn nhánh này nằm trong NewsScreen nên chỉ chạy khi màn News đang hiện, chỉ tính
// trên danh sách ĐÃ LỌC của màn (bộ lọc category hay ô tìm kiếm âm thầm tắt luôn cảnh báo), và
// chống trùng bằng QSet trong RAM theo id bài, mà id lại đổi mỗi lần fetch. Dịch vụ này là QObject
// không phải widget nên DataHub luôn coi là active (DataHub.cpp: non-widget owner), nghe
// `news:general` (topic chung NewsService phát mọi danh sách bài đã gộp) và tính trên danh sách
// CHƯA lọc. NewsScreen giờ chỉ còn vẽ banner.
//
// Chống trùng ba tầng:
//   - Bền, giữa các feed và các lần khởi động: NotificationRequest.dedupe_key = "news:" + event_key
//     (luật + mã) hoặc story_key (tiêu đề lõi), dedupe_s = 6 giờ; NotificationService tra bảng
//     lịch sử.
//   - Trong phiên: khoá đã xử lý theo id bài (id ổn định từ đợt này), để không gửi lại cùng một bài
//     ở mỗi lần publish.
//   - Theo câu chuyện: bài khẩn đã báo trong 6 giờ qua được đưa lại vào bước gom cụm; cụm nào có
//     thành viên đã báo thì không báo nữa, trừ khi bài mới khẩn hơn hẳn (URGENT đã báo, nay FLASH).
// Chỉ báo bài đăng sau (thời điểm start() − 30 phút): khởi động kiểu cache-first phát lại các bài
// cũ trong cache lên hub, và chúng không được báo lại.
//
// Mức: chỉ FLASH của tin TIẾNG VIỆT là Critical (banner macOS cả khi app đang mở). Tin tiếng Anh
// lên FLASH nhờ dò chữ "breaking"/"alert" ở cả tóm tắt ("breaking point", "record-breaking"), luật
// mà đặc tả chỉ cho sửa hai chỗ, nên chỉ ở mức Alert.
//
// DEVIATION: nền là số bài mỗi category theo từng giờ đồng hồ app chạy (giờ không có bài là mẫu 0),
// lưu bền trong cache.db (CacheManager, khoá "news:alert_baselines", 8 ngày) nên cộng dồn qua các
// lần khởi động. Giờ app không chạy thì không có mẫu (không coi là 0).
// Cần 24 mẫu, tức 24 giờ app chạy, mới bắt đầu chấm độ lệch.
#pragma once

#include "services/news/NewsService.h"

#include <QHash>
#include <QMap>
#include <QObject>
#include <QString>
#include <QVector>

#include <cstdint>

class QTimer;

namespace fincept::services {

class NewsAlertService : public QObject {
    Q_OBJECT
  public:
    static NewsAlertService& instance();

    /// Đăng ký DataHub `news:general`. Idempotent. Gọi trên GUI thread, sau
    /// NewsService::instance().ensure_registered_with_hub().
    void start();

  private:
    NewsAlertService();

    void process();
    void alert_urgent(const QVector<NewsArticle>& fresh);
    void alert_monitors(const QVector<NewsArticle>& fresh);
    void alert_deviations(const QVector<NewsArticle>& all, int64_t now);
    void load_baselines();
    void save_baselines() const;

    QTimer* debounce_ = nullptr;
    QVector<NewsArticle> pending_;
    bool has_pending_ = false;
    bool started_ = false;
    int64_t since_ts_ = 0; ///< chỉ báo bài có sort_ts >= mốc này

    QHash<QString, int64_t> seen_;           ///< khoá đã xử lý trong phiên → sort_ts của bài
    QHash<QString, int64_t> deviation_sent_; ///< category → lần báo gần nhất (unix s)

    struct AlertedArticle {
        NewsArticle article; ///< bài khẩn (đã chấm lại) thuộc một cụm đã xử lý
        int64_t at = 0;      ///< lúc xử lý (unix s)
    };
    QVector<AlertedArticle> alerted_; ///< trong 6 giờ qua: đưa lại vào bước gom cụm

    QMap<QString, QVector<int>> hourly_counts_; ///< category → MỘT mẫu mỗi giờ đồng hồ, mới nhất ở cuối
    int64_t hourly_hour_ = -1;                  ///< giờ (unix s / 3600) của mẫu cuối
};

} // namespace fincept::services
