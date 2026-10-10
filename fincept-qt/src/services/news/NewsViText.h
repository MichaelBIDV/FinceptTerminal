// src/services/news/NewsViText.h
// Chuẩn hoá chữ cho News tiếng Việt: bỏ ký tự vô hình, bỏ dấu, tiêu đề lõi, biên từ Unicode,
// nhận diện tiếng Việt và nhận diện mã chứng khoán VN theo whitelist.
//
// Hàm thuần, chỉ cần QtCore. Dùng chung cho NewsService_Parsing, NewsViClassifier,
// NewsImpactRanker, NewsClusterService, NewsMonitorService và tests/tst_vi_classifier.cpp.
// Namespace CÓ TÊN: các tệp services/news được gộp unity build, nên `fold`/`has_word` trong
// namespace vô danh của hai tệp cùng lô sẽ đụng tên.
//
// BA CÁI BẪY ĐÃ ĐO (bản đồ news 03/10/2026)
//   1. Cầu dữ liệu chèn U+200C vào giữa từ khoá ("G<U+200C>DP", "F<U+200C>ed") để né việc C++ ghi đè category.
//      fold() PHẢI bỏ U+200B/C/D, U+2060, U+FEFF trước khi so khớp, nếu không từ khoá trượt.
//   2. QRegularExpression mặc định là ASCII: `\b`/`\W` băm tiếng Việt ở mọi ký tự có dấu.
//      has_word() kiểm biên bằng QChar::isLetterOrNumber nên đúng với chữ có dấu.
//   3. Mã CK rác (AI, NEWS, TP, USD, HCM…) đến từ regex `\b[A-Z]{2,5}\b`. Ở đây chỉ nhận mã có
//      trong whitelist do cầu dữ liệu xuất; mã nhập nhằng (USD, HCM, CPI…) chỉ nhận khi có neo.
#pragma once

#include <QSet>
#include <QString>
#include <QStringList>

namespace fincept::services::vitext {

/// Bỏ U+200B/C/D, U+2060, U+FEFF rồi đưa về NFC. Không hạ chữ, không bỏ dấu.
QString clean(const QString& s);

/// clean() rồi bỏ dấu, đ/Đ → d, hạ chữ thường. Dùng cho từ khoá viết không dấu.
QString fold(const QString& s);

/// Tiêu đề lõi: bỏ tiền tố "[…]" và hậu tố nhãn của cầu dữ liệu, dạng
/// "<gạch dài U+2014> Nguồn · NEWS" hoặc "· FACT-T2" / "· SS-T3" / "· EST".
QString core_title(const QString& headline);

/// `needle` có trong `hay` với biên chữ Unicode hai bên (ký tự kề không phải chữ hay số).
/// So nguyên văn: muốn khớp không dấu thì fold() cả hai vế, muốn khớp có dấu thì không fold.
bool has_word(const QString& hay, const QString& needle);

/// Văn bản tiếng Việt: ít nhất 2 ký tự có dấu kiểu Việt, trong đó ít nhất 1 ký tự CHỈ tiếng Việt
/// có (U+1EA0–U+1EF9, ơ, ư). ă/â/đ/ê/ô chỉ được đếm thêm vì tiếng Pháp/Bồ Đào Nha cũng dùng.
bool is_vietnamese(const QString& s);

// ── Mã chứng khoán VN ───────────────────────────────────────────────────────

struct TickerData {
    QSet<QString> ma;         ///< mã cổ phiếu HOSE/HNX/UPCOM
    QSet<QString> nhap_nhang; ///< mã trùng chữ thường gặp (USD, HCM, CPI…), chỉ nhận khi có neo
};

/// Tệp whitelist do cầu dữ liệu xuất: $HDCV_SYSTEM_DIR (mặc định ~/SECOND BRAIN-OBSIDIAN/_System)
/// + /fincept_bridge/data/vn_ma.json. Script xuất: _System/fincept_bridge/xuat_vn_ma.py.
QString default_ticker_file();

/// Nạp whitelist từ tệp JSON {"ma":[…], "nhap_nhang":[…]} và hoán đổi nguyên khối.
/// Thiếu tệp hoặc tệp hỏng: trả false, giữ bộ đang dùng.
bool load_ticker_file(const QString& path);

/// Đặt thẳng dữ liệu (cho test). Sau lời gọi này sẽ không tự nạp tệp mặc định nữa.
void set_ticker_data(const TickerData& data);

/// true khi đã có whitelist không rỗng (lần gọi đầu tự nạp default_ticker_file()).
bool tickers_available();

/// Mã CK trong `text`: mẫu 3 ký tự [A-Z][A-Z0-9]{2} có biên Unicode, có trong whitelist, không
/// dính dấu chấm kiểu "TP.HCM"/"PGS.TS"; mã nhập nhằng phải có neo ("(HOSE: X)", "X:HOSE",
/// "[X▲]", "mã CK: X", "cổ phiếu X"); mã kề từ 2 từ viết hoa có dấu trở lên trong cùng vế
/// ("TOP 8 TIN CHÍNH SÁCH") cũng phải có neo. Không có whitelist thì trả rỗng.
QStringList extract_tickers(const QString& text, int max_count = 5);

} // namespace fincept::services::vitext
