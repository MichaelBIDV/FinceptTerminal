// src/services/news/NewsImpactRanker.h
// Xếp tin theo MỨC TÁC ĐỘNG THỊ TRƯỜNG, và chia về bốn thị trường Mỹ · Việt Nam · Trung Quốc ·
// Châu Âu.
//
// VÌ SAO KHÔNG DÙNG LẠI `NewsArticle::impact`
// -------------------------------------------
// Trường `impact` sẵn có được suy ra trong NewsService::enrich_article() từ CƯỜNG ĐỘ CẢM XÚC:
// priority thành FLASH khi tiêu đề chứa "breaking"/"alert", và impact thành HIGH khi priority là
// FLASH/URGENT hoặc |điểm cảm xúc| ≥ 6 — mà bảng trọng số cho "kill" 2, "attack" 2, "invasion" 3,
// "protest" 2. Hệ quả đo được trên màn hình ngày 21/09/2026: một vụ nổ súng ở Sydney mang nhãn
// tác động cao, còn tin Việt Nam được FTSE Russell nâng hạng — tin có sức dời dòng vốn lớn nhất
// hôm đó — nằm ở ROUTINE. Trường đó đo KỊCH TÍNH, không đo thị trường; xếp theo nó là xếp sai
// thứ nguyên. Nó vẫn được giữ nguyên và vẫn hiện trên dòng tin, chỉ không dùng để xếp băng này.
//
// LUẬT CHẤM SOI GƯƠNG BẢN PYTHON
// ------------------------------
// Luật dưới đây soi gương `_System/fincept_bridge/goi_tintop.py`. Sửa một bên thì PHẢI sửa bên
// kia, nếu không hai chỗ cùng nói về "tin quan trọng nhất" mà cho hai câu trả lời khác nhau.
// Bốn cái bẫy đã trả giá bên Python, chép nguyên sang đây:
//   1. Khớp theo BIÊN TỪ. "sbv" từng khớp bên trong chữ khác và đẩy một tin vi phạm công bố
//      thông tin lên hạng nhì Việt Nam — và bản thân "SBV" là mã của Siam Brothers Việt Nam
//      trên HOSE, nên từ này bị loại hẳn khỏi danh sách; báo trong nước gọi là NHNN.
//   2. Chỉ tính bậc từ khoá CAO NHẤT, không cộng dồn — nếu không một bài nhắc đủ thứ sẽ thắng
//      một bài nói đúng một điều quan trọng.
//   3. Tin của hãng tài chính mà không trúng từ khoá thị trường nào vẫn được điểm nguồn cộng
//      điểm tươi rồi lọt top (chuyến bay trễ, bầu cử địa phương). Phải phạt thẳng −4.
//   4. Tin quá cũ không còn là "tin quan trọng nhất hôm nay": một bài tháng 1 từng lọt hạng ba
//      Trung Quốc chỉ vì tiêu đề có chữ tariff.
#pragma once

#include "services/news/NewsService.h"

#include <QString>
#include <QStringList>
#include <QVector>

namespace fincept::services {

/// Bốn thị trường người dùng theo dõi. KHAC = không xếp được về thị trường nào — bài đó KHÔNG
/// vào băng, thay vì bị nhét bừa vào một cột.
enum class Market { VN, US, CN, EU, KHAC };

QString market_label(Market m);   // "VIỆT NAM" / "MỸ" / ...
QString market_code(Market m);    // "VN" / "US" / ...

/// Một bài đã chấm. `vi_sao` in đúng những tín hiệu ĐÃ CỘNG, để bác được từng dòng —
/// không có điểm nào không giải thích được.
struct RankedArticle {
    NewsArticle article;
    Market market = Market::KHAC;
    int score = 0;
    QStringList vi_sao;
};

/// Xếp `articles` về bốn thị trường và trả tối đa `per_market` bài mỗi thị trường, đã sắp giảm
/// dần theo điểm. Bài trùng chủ đề bị gộp (giữ bản điểm cao hơn). `now_ts` là unix seconds.
QVector<RankedArticle> top_by_market(const QVector<NewsArticle>& articles, int per_market,
                                     int64_t now_ts);

/// Chấm một bài. Dùng riêng khi cần xếp cả danh sách chứ không chỉ lấy top.
RankedArticle rank_article(const NewsArticle& a, int64_t now_ts);

} // namespace fincept::services
