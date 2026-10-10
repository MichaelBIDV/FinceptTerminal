// src/services/news/NewsViClassifier.cpp
// Bảng luật xếp bậc tin tiếng Việt. Vì sao từng cụm khớp có dấu hay bỏ dấu, cần neo hay không:
// xem NewsViClassifier.h.
#include "services/news/NewsViClassifier.h"

#include "services/news/NewsViText.h"

#include <QCryptographicHash>
#include <QRegularExpression>

#include <algorithm>
#include <vector>

namespace fincept::services::vinews {

namespace {

struct Rule {
    Priority tier;
    bool exact;       ///< true: so trên chữ thường GIỮ DẤU; false: so trên fold()
    bool need_anchor; ///< thiếu neo chủ thể thì hạ một bậc
    QStringList phrases;
    QStringList keys = {}; ///< dạng đem so: phrases (exact) hoặc fold(phrases), dựng một lần
};

// Thứ tự trong bảng không quan trọng: luôn lấy bậc CAO NHẤT trong các cụm khớp.
const std::vector<Rule>& rules() {
    static const std::vector<Rule> r = [] {
        std::vector<Rule> t = {
            // FLASH: thị trường ngừng (không cần neo)
            {Priority::Flash, false, false,
             {QStringLiteral("đình chỉ giao dịch"), QStringLiteral("tạm ngừng giao dịch"),
              QStringLiteral("tạm dừng giao dịch"), QStringLiteral("ngừng giao dịch"),
              QStringLiteral("cấm giao dịch")}},
            {Priority::Flash, false, false,
             {QStringLiteral("hủy niêm yết"), QStringLiteral("hủy bỏ niêm yết"),
              QStringLiteral("hủy đăng ký giao dịch")}},
            // FLASH: pháp lý, tín dụng, văn bản khẩn (cần neo)
            {Priority::Flash, false, true,
             {QStringLiteral("khởi tố"), QStringLiteral("bắt tạm giam"), QStringLiteral("truy nã")}},
            {Priority::Flash, true, true, {QStringLiteral("bị bắt"), QStringLiteral("bắt giữ")}},
            {Priority::Flash, false, true, {QStringLiteral("phá sản"), QStringLiteral("mất khả năng thanh toán")}},
            {Priority::Flash, true, true, {QStringLiteral("vỡ nợ")}},
            {Priority::Flash, true, true,
             {QStringLiteral("hỏa tốc"), QStringLiteral("hoả tốc"), QStringLiteral("thượng khẩn")}},
            // URGENT
            {Priority::Urgent, true, true, {QStringLiteral("khẩn cấp")}},
            {Priority::Urgent, false, false,
             {QStringLiteral("kiểm soát đặc biệt"), QStringLiteral("truy tố"), QStringLiteral("giải chấp"),
              QStringLiteral("call margin"), QStringLiteral("diện cảnh báo"), QStringLiteral("diện kiểm soát"),
              QStringLiteral("hạn chế giao dịch"), QStringLiteral("ý kiến ngoại trừ"),
              QStringLiteral("từ chối đưa ra ý kiến")}},
            {Priority::Urgent, false, false,
             {QStringLiteral("nới room"), QStringLiteral("room ngoại"), QStringLiteral("hết room"),
              QStringLiteral("điều chỉnh room"), QStringLiteral("sở hữu nước ngoài tối đa")}},
            {Priority::Urgent, true, true,
             {QStringLiteral("hỏa hoạn"), QStringLiteral("hoả hoạn"), QStringLiteral("cháy nổ"),
              QStringLiteral("vụ cháy"), QStringLiteral("phát nổ")}},
            {Priority::Urgent, false, false,
             {QStringLiteral("siêu bão"), QStringLiteral("lũ quét"), QStringLiteral("động đất")}},
            // BREAKING
            {Priority::Breaking, false, true,
             {QStringLiteral("bị xử phạt"), QStringLiteral("truy thu thuế"), QStringLiteral("bị cưỡng chế"),
              QStringLiteral("bị thanh tra"), QStringLiteral("kết luận thanh tra"), QStringLiteral("đình chỉ")}},
            {Priority::Breaking, true, false,
             {QStringLiteral("giảm sàn"), QStringLiteral("nằm sàn"), QStringLiteral("trắng bên mua"),
              QStringLiteral("tăng trần")}},
            {Priority::Breaking, false, false,
             {QStringLiteral("từ nhiệm"), QStringLiteral("bãi nhiệm"), QStringLiteral("chào mua công khai"),
              QStringLiteral("thâu tóm"), QStringLiteral("thoái vốn"), QStringLiteral("giải trình")}},
            {Priority::Breaking, true, false, {QStringLiteral("bán tháo"), QStringLiteral("miễn nhiệm")}},
        };
        for (auto& rule : t) {
            for (const auto& p : rule.phrases)
                rule.keys << (rule.exact ? p : vitext::fold(p));
        }
        return t;
    }();
    return r;
}

// Chỉ đạo của Thủ tướng: BREAKING, lên URGENT khi nhắm vào một đối tượng thị trường.
const QStringList& directive_fold() {
    static const QStringList k = {QStringLiteral("thu tuong chi dao"), QStringLiteral("thu tuong yeu cau")};
    return k;
}
const QString& directive_exact() {
    static const QString k = QStringLiteral("công điện");
    return k;
}
const QStringList& market_objects() { // dạng fold
    static const QStringList k = {QStringLiteral("gia dien"), QStringLiteral("xang dau"),
                                  QStringLiteral("chung khoan"), QStringLiteral("lai suat"),
                                  QStringLiteral("ty gia"), QStringLiteral("gia vang"),
                                  QStringLiteral("trai phieu")};
    return k;
}

// Cơ quan VN làm neo chủ thể (dạng fold). "so giao dich" để nguyên cụm "chứng khoán" vì bỏ dấu
// nó trùng "số giao dịch".
const QStringList& vn_authorities() {
    static const QStringList k = {
        QStringLiteral("nhnn"),          QStringLiteral("ngan hang nha nuoc"), QStringLiteral("thong doc"),
        QStringLiteral("ubck"),          QStringLiteral("ubcknn"),             QStringLiteral("bo tai chinh"),
        QStringLiteral("chinh phu"),     QStringLiteral("thu tuong"),          QStringLiteral("bo cong an"),
        QStringLiteral("vien kiem sat"), QStringLiteral("hose"),               QStringLiteral("hnx"),
        QStringLiteral("vsdc"),          QStringLiteral("vnx"),
        QStringLiteral("so giao dich chung khoan")};
    return k;
}

// Ngân hàng trung ương đổi lãi suất: CHỦ THỂ, rồi trong cùng một câu (không qua . ! ? ; và không
// qua tên một ngân hàng trung ương khác) động từ + "lãi suất" [+ cụm định danh] + CON SỐ. Chạy trên
// fold() của tiêu đề + tóm tắt (nối bằng dấu cách, để tiêu đề "NHNN giảm lãi suất tái cấp vốn" đi
// với con số ở đầu tóm tắt).
//   - NHNN: cụm định danh BẮT BUỘC (điều hành / tái cấp vốn / chiết khấu / cơ bản). Thiếu nó thì
//     "NHNN: nhiều ngân hàng tăng lãi suất thêm 0,5%" hay tóm tắt "Vietcombank giảm lãi suất 0,5%"
//     là lãi suất của ngân hàng thương mại, từng ra FLASH (mức Critical) khi đo.
//   - Fed/FOMC/ECB: "lãi suất" trơn đã là lãi suất chính sách; vẫn loại huy động / tiết kiệm /
//     cho vay / liên ngân hàng.
QString rate_pattern(const QString& subjects, bool designator_required) {
    const QString designator = QStringLiteral("\\s+(?:dieu hanh|tai cap von|chiet khau|co ban)");
    return QStringLiteral("(?<![\\p{L}\\p{N}])(?:%1)(?![\\p{L}\\p{N}])"
                          "(?:(?!(?:nhnn|ngan hang nha nuoc|fed|fomc|ecb|boj|pboc)(?![\\p{L}\\p{N}]))[^.!?;]){0,40}?"
                          "(?<![\\p{L}\\p{N}])(?:tang|giam|ha|nang|cat|dieu chinh)\\s+lai suat"
                          "(?!\\s+(?:huy dong|tiet kiem|cho vay|lien ngan hang))%2(?![\\p{L}\\p{N}])"
                          "[^.!?;]{0,40}?\\d+(?:[.,]\\d+)?\\s*(?:%|diem co ban|bps|diem phan tram)")
        .arg(subjects, designator_required ? designator : QStringLiteral("(?:%1)?").arg(designator));
}

const QRegularExpression& sbv_rate_decision() {
    static const QRegularExpression re(rate_pattern(QStringLiteral("nhnn|ngan hang nha nuoc"), true),
                                       QRegularExpression::UseUnicodePropertiesOption);
    return re;
}

const QRegularExpression& foreign_rate_decision() {
    static const QRegularExpression re(rate_pattern(QStringLiteral("fed|fomc|ecb"), false),
                                       QRegularExpression::UseUnicodePropertiesOption);
    return re;
}

// "Thủ tướng Nhật Bản", "Chính phủ Mỹ" không phải cơ quan VN. So trên chữ thường GIỮ DẤU: bỏ dấu
// thì "Chính phủ nhất trí" trùng "chinh phu nhat".
const QRegularExpression& foreign_government() {
    static const QRegularExpression re(
        QStringLiteral("(?<![\\p{L}\\p{N}])(?:thủ tướng|chính phủ)\\s+(?:các nước|nước ngoài|nhật|mỹ|hoa kỳ|"
                       "trung quốc|thái lan|hàn quốc|triều tiên|anh|pháp|đức|nga|ấn độ|úc|canada|ý|"
                       "tây ban nha|singapore|malaysia|indonesia|philippines|campuchia|lào|myanmar|"
                       "israel|ukraine|iran|đài loan|hà lan|thụy sĩ|thuỵ sĩ|thụy điển|thuỵ điển|na uy|"
                       "brazil|mexico|argentina|thổ nhĩ kỳ|new zealand|pakistan|bangladesh)"
                       "(?![\\p{L}\\p{N}])"),
        QRegularExpression::UseUnicodePropertiesOption);
    return re;
}

// Văn bản hành chính tiếng Anh trong category REGULATORY.
const QRegularExpression& admin_title() {
    static const QRegularExpression re(
        QStringLiteral("\\b(?:Antidumping|Countervailing|Administrative Review|Notice of|Final Results|"
                       "Preliminary Results|Agency Information Collection|Five-Year Review|Proposed Rule|"
                       "Final Rule|Requests? for Comments?|Sunshine Act|Scope Ruling|Determinations?)\\b"),
        QRegularExpression::CaseInsensitiveOption);
    return re;
}

// Câu đóng khung của báo (Guardian): "Get our breaking news email, free app or daily news
// podcast", "Sign up for the breaking news US email". Báo dán liền vào chữ trước nên KHÔNG đòi
// biên từ bên trái.
const QRegularExpression& boilerplate() {
    static const QRegularExpression re(
        QStringLiteral("(?:get our|sign up for (?:the|our)) breaking news[^.]{0,40}?email"
                       "(?:, free app or daily news podcast)?"),
        QRegularExpression::CaseInsensitiveOption);
    return re;
}

Priority lower(Priority p) {
    return p == Priority::Routine ? p : static_cast<Priority>(static_cast<int>(p) + 1);
}

bool better(Priority a, Priority b) {
    return static_cast<int>(a) < static_cast<int>(b);
}

bool is_research(const QString& source, const QString& headline, const QString& summary) {
    const QString all = source.toUpper() + QLatin1Char(' ') + headline + QLatin1Char(' ') + summary;
    for (const auto& k : {QStringLiteral("SS-T3"), QStringLiteral("RESEARCH"), QStringLiteral("BÁO CÁO"),
                          QStringLiteral("KHUYẾN NGHỊ")}) {
        if (all.contains(k))
            return true;
    }
    return false;
}

} // namespace

QString story_key(const QString& headline) {
    const QByteArray core = vitext::fold(vitext::core_title(headline)).simplified().toUtf8();
    return QString::fromLatin1(QCryptographicHash::hash(core, QCryptographicHash::Sha1).toHex().left(16));
}

Priority english_priority(const QString& headline, const QString& summary) {
    QString text = (headline + QLatin1Char(' ') + summary).toLower();
    text.remove(boilerplate());
    if (vitext::has_word(text, QStringLiteral("breaking")) || vitext::has_word(text, QStringLiteral("alert")))
        return Priority::Flash;
    if (vitext::has_word(text, QStringLiteral("urgent")) || vitext::has_word(text, QStringLiteral("emergency")))
        return Priority::Urgent;
    if (vitext::has_word(text, QStringLiteral("announce")) || vitext::has_word(text, QStringLiteral("report")))
        return Priority::Breaking;
    return Priority::Routine;
}

Classification classify(const QString& headline, const QString& summary, const QString& source,
                        const QString& category, const QString& region) {
    Q_UNUSED(region);
    Classification r;
    r.story_key = story_key(headline);

    const QString src_up = source.toUpper();
    const bool vi = vitext::is_vietnamese(headline + QLatin1Char(' ') + summary);

    if (src_up.contains(QLatin1String("FEDERAL REGISTER")) ||
        (category == QLatin1String("REGULATORY") && !vitext::is_vietnamese(headline) &&
         admin_title().match(headline).hasMatch())) {
        r.is_admin = true;
        r.tickers = vitext::extract_tickers(headline + QLatin1Char(' ') + summary);
        return r;
    }
    if (!vi) {
        r.priority = english_priority(headline, summary);
        r.impact = Impact::Low; // tin tiếng Anh: impact do enrich_article tính từ cảm xúc
        return r;
    }

    r.tickers = vitext::extract_tickers(headline + QLatin1Char(' ') + summary);
    if (src_up.contains(QLatin1String("HDCV ARTIFACT")))
        return r;

    const QString core = vitext::core_title(headline);
    const QString low = vitext::clean(core).toLower();
    const QString fol = vitext::fold(core);

    // "trái phiếu chính phủ" (đo được trong tin bán tháo trái phiếu toàn cầu) và "Thủ tướng Nhật Bản",
    // "Chính phủ Mỹ" không phải cơ quan VN ra quyết định: bỏ các cụm này trước khi dò cơ quan làm neo.
    QString low_anchor = low;
    low_anchor.replace(foreign_government(), QStringLiteral(" "));
    QString fol_anchor = vitext::fold(low_anchor);
    fol_anchor.replace(QStringLiteral("trai phieu chinh phu"), QStringLiteral(" "));
    // Mã của TIÊU ĐỀ LÕI: vừa làm neo vừa dựng event_key. Có mã ở tiêu đề thì mã thêm ở tóm tắt không
    // vào khoá, nếu không cùng một tin "KOS giải chấp" ra hai khoá "KOS" và "KOS,PNJ".
    const QStringList core_tickers = vitext::extract_tickers(core);
    r.anchored = !core_tickers.isEmpty();
    for (const auto& a : vn_authorities()) {
        if (r.anchored)
            break;
        r.anchored = vitext::has_word(fol_anchor, a);
    }

    Priority best = Priority::Routine;
    QString why;
    auto consider = [&](Priority tier, bool need_anchor, const QString& phrase) {
        const Priority t = (need_anchor && !r.anchored) ? lower(tier) : tier;
        if (better(t, best)) {
            best = t;
            why = phrase;
        }
    };
    for (const auto& rule : rules()) {
        for (int i = 0; i < rule.phrases.size(); ++i) {
            if (vitext::has_word(rule.exact ? low : fol, rule.keys.at(i)))
                consider(rule.tier, rule.need_anchor, rule.phrases.at(i));
        }
    }

    // Chỉ đạo của Thủ tướng: BREAKING, có đối tượng thị trường thì URGENT.
    bool directive = vitext::has_word(low, directive_exact());
    for (const auto& d : directive_fold())
        directive = directive || vitext::has_word(fol, d);
    if (directive) {
        const bool market = std::any_of(market_objects().cbegin(), market_objects().cend(),
                                        [&fol](const QString& m) { return vitext::has_word(fol, m); });
        consider(market ? Priority::Urgent : Priority::Breaking, false,
                 market ? QStringLiteral("chỉ đạo + đối tượng thị trường") : QStringLiteral("chỉ đạo"));
    }

    // Đổi lãi suất chính sách có con số: chủ thể phải ở tiêu đề, con số có thể nằm ở tóm tắt.
    const QString full_fold = vitext::fold(headline + QLatin1Char(' ') + summary);
    if (vitext::has_word(fol, QStringLiteral("nhnn")) || vitext::has_word(fol, QStringLiteral("ngan hang nha nuoc"))) {
        if (sbv_rate_decision().match(full_fold).hasMatch())
            consider(Priority::Flash, false, QStringLiteral("nhnn đổi lãi suất"));
    } else if (vitext::has_word(fol, QStringLiteral("fed")) || vitext::has_word(fol, QStringLiteral("fomc")) ||
               vitext::has_word(fol, QStringLiteral("ecb"))) {
        if (foreign_rate_decision().match(full_fold).hasMatch())
            consider(Priority::Urgent, false, QStringLiteral("fed/ecb đổi lãi suất"));
    }

    // Đổi khuyến nghị / giá mục tiêu của sell-side là SS-T3: trần BREAKING.
    if (better(best, Priority::Breaking) && is_research(source, headline, summary))
        best = Priority::Breaking;

    r.priority = best;
    if (best == Priority::Routine)
        return r;

    r.rule = why;
    r.impact = (best == Priority::Breaking) ? Impact::Medium : (r.anchored ? Impact::High : Impact::Medium);
    // Khoá theo mã của tiêu đề lõi; tiêu đề không nêu mã ("Ông Nguyễn Việt Cường bị bán giải chấp…",
    // mã KOS ở tóm tắt) thì mới lấy mã của tóm tắt, để ba bài cùng tin KOS chung một khoá.
    QStringList key_tickers = core_tickers.isEmpty() ? r.tickers : core_tickers;
    key_tickers.sort();
    r.event_key = why + QLatin1Char('|') +
                  (key_tickers.isEmpty() ? QStringLiteral("s:") + r.story_key : key_tickers.join(QLatin1Char(',')));
    return r;
}

} // namespace fincept::services::vinews
