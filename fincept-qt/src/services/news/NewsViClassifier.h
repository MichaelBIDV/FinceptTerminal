// src/services/news/NewsViClassifier.h
// Xếp bậc tin (FLASH/URGENT/BREAKING/ROUTINE) và mức tác động cho tin TIẾNG VIỆT, kèm luật cũ
// cho tin tiếng Anh đã sửa hai chỗ. Hàm thuần, chỉ cần QtCore (test: tests/tst_vi_classifier.cpp).
//
// LUẬT (bản đồ news 03/10/2026, nguyên mẫu đã đo trên 1.300 tiêu đề VN thật)
//   - Chỉ chấm trên TIÊU ĐỀ LÕI (vitext::core_title), không chấm phần tóm tắt.
//   - Mỗi cụm khớp theo biên từ. Cụm bỏ dấu sẽ trùng chữ khác nghĩa thì PHẢI khớp có dấu:
//     "nằm sàn"→"nam san" trùng "Việt Nam sẵn sàng"; "bắt"→"bat" trùng "bất động sản";
//     "khẩn"→"khan" trùng "khan hiếm"; "hỏa hoạn"→"hoa hoan" trùng "hòa hoãn"; "cháy"→"chay"
//     trùng "chạy"; "bán tháo"→"ban thao" trùng "bàn thảo"; "miễn nhiệm" trùng "miễn nhiễm";
//     "vỡ nợ" trùng "vợ nó"; "công điện" trùng "công diễn".
//   - Neo chủ thể: tiêu đề lõi có mã CK (whitelist) hoặc cơ quan VN (NHNN, UBCK, Bộ Tài chính,
//     Chính phủ, Thủ tướng, Bộ Công an, Viện kiểm sát, HOSE, HNX, VSDC, VNX…). Cụm cần neo mà
//     thiếu neo thì hạ một bậc.
//   - NHNN đổi lãi suất (cụm định danh bắt buộc: điều hành / tái cấp vốn / chiết khấu / cơ bản)
//     có con số, chủ thể và động từ trong cùng một câu → FLASH; Fed/ECB/FOMC đổi lãi suất có con
//     số → URGENT. Lãi suất huy động / tiết kiệm / cho vay của ngân hàng thương mại không tính.
//   - "Thủ tướng/Chính phủ + tên nước" (Nhật Bản, Mỹ…) không phải neo.
//   - Nguồn sell-side (SS-T3, RESEARCH, BÁO CÁO, KHUYẾN NGHỊ) tối đa BREAKING.
//   - Văn bản hành chính (FEDERAL REGISTER, hoặc REGULATORY + tiêu đề tiếng Anh dạng Notice of /
//     Antidumping / …) ép ROUTINE, is_admin = true. Nguồn HDCV ARTIFACT không qua bộ phân loại:
//     các job tự đẩy tin vào hộp thư của app.
//   - Impact: FLASH/URGENT có neo → HIGH, thiếu neo → MEDIUM; BREAKING → MEDIUM; còn lại LOW.
#pragma once

#include <QString>
#include <QStringList>

namespace fincept::services::vinews {

/// Cùng thứ tự với fincept::services::Priority / Impact (NewsService.h) để ép kiểu trực tiếp;
/// NewsService_Parsing.cpp có static_assert giữ điều này.
enum class Priority { Flash = 0, Urgent = 1, Breaking = 2, Routine = 3 };
enum class Impact { High = 0, Medium = 1, Low = 2 };

struct Classification {
    Priority priority = Priority::Routine;
    Impact impact = Impact::Low;
    QStringList tickers;   ///< mã VN theo whitelist (tin tiếng Việt và văn bản hành chính)
    QString event_key;     ///< "<cụm luật>|<mã,…>": mã tiêu đề lõi, không có thì mã tóm tắt, không có nữa
                           ///< thì "|s:<story_key>"; rỗng khi ROUTINE
    QString story_key;     ///< 16 hex đầu SHA-1 của fold(core_title(headline)): gộp bài trùng giữa feed
    bool is_admin = false; ///< văn bản hành chính: ROUTINE, không thông báo
    bool anchored = false; ///< tiêu đề lõi có mã CK hoặc cơ quan VN
    QString rule;          ///< cụm luật quyết định bậc (để log/giải thích); rỗng khi ROUTINE
};

/// Phân loại một bài. Tin không phải tiếng Việt nhận bậc từ english_priority().
/// `region` là nhãn của NGUỒN (feed.region), không phải của bài, nên không dùng để xếp bậc.
Classification classify(const QString& headline, const QString& summary, const QString& source,
                        const QString& category, const QString& region);

/// Bậc tin tiếng Anh: luật cũ của enrich_article (breaking/alert → FLASH, urgent/emergency →
/// URGENT, announce/report → BREAKING), đổi đúng hai chỗ: bỏ câu đóng khung kiểu
/// "Get our breaking news email" trước khi dò, và khớp theo biên từ thay cho chuỗi con.
Priority english_priority(const QString& headline, const QString& summary);

/// Khoá câu chuyện ổn định giữa các lần fetch và giữa các feed đưa cùng một tin.
QString story_key(const QString& headline);

} // namespace fincept::services::vinews
