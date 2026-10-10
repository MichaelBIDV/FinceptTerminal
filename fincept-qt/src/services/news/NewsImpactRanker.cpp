// src/services/news/NewsImpactRanker.cpp
// Soi gương `_System/fincept_bridge/goi_tintop.py` — xem NewsImpactRanker.h để biết vì sao
// không dùng lại NewsArticle::impact và bốn cái bẫy phải giữ.
#include "services/news/NewsImpactRanker.h"

#include "services/news/NewsViText.h"

#include <QHash>
#include <QSet>

#include <algorithm>
#include <array>

namespace fincept::services {

namespace {

// ── Chuẩn hoá: dùng chung vitext::fold (bỏ dấu, chữ thường, VÀ bỏ ký tự vô hình U+200B/C/D,
// U+2060, U+FEFF). Bản fold riêng trước đây không bỏ U+200C mà cầu dữ liệu chèn vào giữa từ khoá
// để né việc ghi đè category, nên "G<U+200C>DP Quý 3/2026 tăng 9.95%" trượt từ khoá "gdp" (13 bài hụt).
// Khớp theo BIÊN TỪ (bẫy #1): vitext::has_word kiểm hai ký tự hai bên, đúng cả cho từ ghép có dấu
// cách hoặc dấu chấm ("u.s.", "record high").
int count_words(const QString& hay, const QStringList& needles) {
    int n = 0;
    for (const auto& w : needles) {
        if (vitext::has_word(hay, w))
            n++;
    }
    return n;
}

QString first_hit(const QString& hay, const QStringList& needles) {
    for (const auto& w : needles) {
        if (vitext::has_word(hay, w))
            return w;
    }
    return {};
}

// ── Từ khoá tác động. Chỉ tính bậc CAO NHẤT, không cộng dồn (bẫy #2). ──
// Lưu ý: bản Python có vài tiền tố ("devalu", "foreign invest", "deport") mà \b khiến chúng
// KHÔNG BAO GIỜ khớp — ở đây viết đủ các dạng thật sự xuất hiện.
const QStringList& kw_policy() { // bậc 5 — chính sách · lãi suất · lạm phát
    static const QStringList k = {
        "lai suat",    "rate hike",   "rate cut",    "rate decision", "interest rate",
        "fomc",        "fed",         "ecb",         "pboc",          "nhnn",
        "central bank", "ngan hang nha nuoc", "lam phat", "cpi",      "inflation",
        "gdp",         "ty gia",      "exchange rate", "devaluation", "devalue",
        "devalued",    "pha gia",     "thue quan",   "tariff",        "tariffs",
        "sanction",    "sanctions",   "vo no",         "default",
        "omo",         "loi suat",    "yield",       "yields",        "chinh sach tien te",
        "monetary policy", "bond yield", "trai phieu", "rate path",   "quantitative easing"};
    return k;
}

const QStringList& kw_market() { // bậc 3 — thị trường · hàng hoá · dòng vốn
    static const QStringList k = {
        "chung khoan", "stock market", "stocks",      "equities",    "thi truong",
        "dong von",    "capital flow", "capital flows", "khoi ngoai", "foreign investment",
        "foreign investor", "foreign investors", "fdi", "credit growth",
        "xuat khau",   "export",      "exports",     "nhap khau",   "import",
        "imports",     "gia dau",     "oil price",   "oil prices",  "opec",
        "gia vang",    "gold",        "nang hang",   "upgrade",     "ftse",
        "msci",        "ipo",         "margin",      "thanh khoan", "liquidity",
        "bat dong san", "real estate", "ngan hang",  "banking",     "tang truong",
        "bond",        "bonds",       "currency",    "commodity",   "commodities"};
    return k;
}

const QStringList& kw_corp() { // bậc 1 — doanh nghiệp
    static const QStringList k = {"doanh nghiep", "loi nhuan", "earnings", "revenue",
                                  "co tuc",       "dividend",  "sap nhap", "merger",
                                  "acquisition",  "co phieu",  "profit",   "guidance"};
    return k;
}

// ── Từ khoá phải khớp CÓ DẤU ──
// Bỏ dấu tiếng Việt làm hai từ khác nghĩa trùng nhau. Đo được ngày 22/09/2026: "tập TRUNG PHÁT
// triển" bỏ dấu thành "trung phat" = "TRỪNG PHẠT", nên một tin về cảng biển được cộng điểm như tin
// trừng phạt; "tin dùng" cũng trùng "tín dụng". Những từ này so trên chữ thường GIỮ DẤU.
const QStringList& kw_exact_policy() {
    static const QStringList k = {QStringLiteral("trừng phạt")};
    return k;
}
const QStringList& kw_exact_market() {
    static const QStringList k = {QStringLiteral("tín dụng")};
    return k;
}

// ── Nhóm đời sống / thể thao / hình sự: thứ đang chiếm đầu bảng mà không liên quan thị trường ──
const QStringList& kw_phat() {
    // Thể thao thêm ngày 22/09/2026: "China's 13-year-old swimming sensation" lọt hạng ba Trung
    // Quốc vì tóm tắt có "gold medal" — "gold" là từ khoá hàng hoá (+3) mà không từ nào phạt.
    static const QStringList k = {
        "medal",        "medals",      "swimming",    "swimmer",    "swimmers",
        "athlete",      "athletes",    "tournament",  "championship", "championships",
        "olympics",     "nba",         "fifa",        "premier league", "grand slam",
        "marathon",     "gymnast",     "gymnastics",  "cricket",    "rugby",
        "formula one",  "boxing",
        "rebel wilson", "shot in",     "shoots",      "shooting",   "murder",
        "court hears",  "celebrity",   "football",    "soccer",     "world cup",
        "olympic",      "tennis",      "sex",         "coffin",     "sunlounger",
        "brawl",        "beach",       "birthrate",   "baby bonus", "childhood education",
        "hospital",     "hospitals",   "migrant",     "migrants",   "deport",
        "deported",     "deportation", "misdiagnos",  "wounds",     "airstrikes",
        "killed",       "dies",        "death",       "deaths"};
    return k;
}

// ── Bậc nguồn: theo NGƯỜI PHÁT NGÔN, không theo độ nổi tiếng của báo ──
int source_tier(const QString& source_up) {
    static const QStringList official = {
        "BAO CHINH PHU", "CHINHPHU",   "FEDERAL RESERVE", "FED",        "SEC",
        "ECB",           "BANK OF ENGLAND", "WHITE HOUSE", "NHA TRANG", "NHÀ TRẮNG",
        "USTR",          "XINHUA",     "TAN HOA XA",      "TÂN HOA XÃ", "NBS",
        "CUC THONG KE",  "CỤC THỐNG KÊ", "FOMC"};
    static const QStringList financial = {
        "BLOOMBERG", "FINANCIAL TIMES", "CNBC",    "MARKETWATCH", "VIETSTOCK",
        "CAFEF",     "VNECONOMY",       "NIKKEI",  "WSJ",         "REUTERS",
        "SEEKING ALPHA", "ECONOMIST",   "DAUTUCOPHIEU", "THANH NIEN", "TUOI TRE",
        "AXIOS",     "POLITICO",        "VNEXPRESS"};
    for (const auto& s : official) {
        if (source_up.contains(s))
            return 4;
    }
    for (const auto& s : financial) {
        if (source_up.contains(s))
            return 3;
    }
    return 1;
}

// ── Định tuyến thị trường ──
// Nội dung trước, vùng của nguồn sau: 30/54 nguồn dựng sẵn mang region "GLOBAL" — một cái thùng,
// không phải một thị trường — nên xếp theo region trước sẽ bỏ rơi gần hết tin quan trọng.
const QStringList& mk_vn() {
    static const QStringList k = {"viet nam", "vietnam",  "vietnamese", "vn-index", "vnindex",
                                  "hose",     "hnx",      "upcom",      "nhnn",
                                  "ngan hang nha nuoc",   "ha noi",     "hanoi",
                                  "ho chi minh", "vnd",   "vn30"};
    return k;
}
const QStringList& mk_us() {
    static const QStringList k = {"united states", "u.s.",   "usa",        "washington",
                                  "white house",   "fed",    "fomc",       "federal reserve",
                                  "treasury",      "wall street", "nasdaq", "dow jones",
                                  "dollar",        "dxy",    "powell",     "trump",
                                  "sec",           "ustr",   "s&p 500"};
    return k;
}
const QStringList& mk_cn() {
    static const QStringList k = {"china",     "chinese",  "beijing",  "shanghai", "shenzhen",
                                  "pboc",      "yuan",     "renminbi", "hong kong", "trung quoc",
                                  "xi jinping", "caixin",  "evergrande"};
    return k;
}
const QStringList& mk_eu() {
    static const QStringList k = {"ecb",       "euro",     "eurozone", "european", "europe",
                                  "germany",   "german",   "france",   "french",   "italy",
                                  "spain",     "brussels", "bundesbank", "lagarde", "britain",
                                  "bank of england",       "gilt",     "euribor"};
    return k;
}

// `region` KHÔNG phải thuộc tính của bài — NewsService_Parsing.cpp:61 chép thẳng `feed.region`,
// tức nó là nhãn của NGUỒN do người cấu hình feed gán. Đo trên kho sống ngày 21/09/2026
// (3.161 bài): nhóm region=VIETNAM chứa 41 bài US Federal Register, và 139 bài có nhãn vùng
// MÂU THUẪN với nội dung — Bloomberg/FT gắn region=US nhưng viết về ECB và Bundesbank.
// Vì vậy region CHỈ được dùng để phá thế hoà giữa hai ứng viên đọc ra từ nội dung, không bao
// giờ được dùng làm căn cứ duy nhất.
Market market_from_region(const QString& region_up) {
    if (region_up == "VIETNAM")
        return Market::VN;
    if (region_up == "US")
        return Market::US;
    if (region_up == "CHINA")
        return Market::CN;
    if (region_up == "EU" || region_up == "UK")
        return Market::EU;
    return Market::KHAC;
}

// Gộp trùng theo GỐC TỪ: 6 ký tự đầu của mỗi từ ≥5 ký tự. Hai tiêu đề chung ≥2 gốc là cùng một
// tin. Khoá cũ (4 từ dài nhất, so khớp tuyệt đối) để lọt "tokenised" / "tokenized": ngày 22/09 cột
// Châu Âu mất hai trong ba suất cho cùng một tin ECB mua trái phiếu token hoá.
QSet<QString> topic_stems(const QString& folded_title) {
    QSet<QString> out;
    QString cur;
    auto day = [&]() {
        if (cur.size() >= 5)
            out.insert(cur.left(6));
        cur.clear();
    };
    for (const QChar c : folded_title) {
        if (c.isLetterOrNumber())
            cur.append(c);
        else
            day();
    }
    day();
    return out;
}

} // namespace

QString market_label(Market m) {
    switch (m) {
    case Market::VN: return QStringLiteral("VIỆT NAM");
    case Market::US: return QStringLiteral("MỸ");
    case Market::CN: return QStringLiteral("TRUNG QUỐC");
    case Market::EU: return QStringLiteral("CHÂU ÂU");
    default: return QStringLiteral("KHÁC");
    }
}

QString market_code(Market m) {
    switch (m) {
    case Market::VN: return QStringLiteral("VN");
    case Market::US: return QStringLiteral("US");
    case Market::CN: return QStringLiteral("CN");
    case Market::EU: return QStringLiteral("EU");
    default: return QStringLiteral("--");
    }
}

RankedArticle rank_article(const NewsArticle& a, int64_t now_ts) {
    RankedArticle r;
    r.article = a;

    const QString txt = vitext::fold(a.headline + QLatin1Char(' ') + a.summary);
    const QString low = vitext::clean(a.headline + QLatin1Char(' ') + a.summary).toLower();

    // ── thị trường: nội dung trước, vùng của nguồn sau ──
    const int n_vn = count_words(txt, mk_vn());
    const int n_us = count_words(txt, mk_us());
    const int n_cn = count_words(txt, mk_cn());
    const int n_eu = count_words(txt, mk_eu());
    const int best = std::max({n_vn, n_us, n_cn, n_eu});
    const int ties = (n_vn == best) + (n_us == best) + (n_cn == best) + (n_eu == best);
    if (best == 0) {
        // Không một dấu hiệu thị trường nào trong tiêu đề lẫn tóm tắt ⇒ KHÔNG xếp vào đâu cả.
        // Trước đây chỗ này lùi về region, và đó chính là đường đưa 41 bài US Federal Register
        // vào ô VIỆT NAM. Thà cột thiếu bài còn hơn cột sai thị trường.
        r.market = Market::KHAC;
    } else if (ties == 1) {
        r.market = (n_vn == best) ? Market::VN
                 : (n_us == best) ? Market::US
                 : (n_cn == best) ? Market::CN
                                  : Market::EU;
    } else {
        // Hoà giữa nhiều thị trường — chỉ lúc này region mới được lên tiếng, và chỉ khi nó
        // trùng một trong các ứng viên đang hoà.
        const Market rm = market_from_region(a.region.toUpper());
        const bool rm_trong_hoa = (rm == Market::VN && n_vn == best) ||
                                  (rm == Market::US && n_us == best) ||
                                  (rm == Market::CN && n_cn == best) ||
                                  (rm == Market::EU && n_eu == best);
        r.market = rm_trong_hoa ? rm : Market::KHAC;
    }

    // ── điểm ──
    const int st = source_tier(a.source.toUpper());
    int score = st;
    r.vi_sao << (st == 4 ? QStringLiteral("nguồn gốc")
               : st == 3 ? QStringLiteral("hãng tài chính")
                         : QStringLiteral("báo chung"));

    QString hit = first_hit(txt, kw_policy());
    if (hit.isEmpty())
        hit = first_hit(low, kw_exact_policy());
    if (!hit.isEmpty()) {
        score += 5;
        r.vi_sao << QStringLiteral("chính sách/lãi suất: %1").arg(hit);
    } else if (!(hit = first_hit(txt, kw_market())).isEmpty() ||
               !(hit = first_hit(low, kw_exact_market())).isEmpty()) {
        score += 3;
        r.vi_sao << QStringLiteral("thị trường/dòng vốn: %1").arg(hit);
    } else if (!(hit = first_hit(txt, kw_corp())).isEmpty()) {
        score += 1;
        r.vi_sao << QStringLiteral("doanh nghiệp: %1").arg(hit);
    } else {
        // Bẫy #3: tin chung của một hãng tài chính vẫn được điểm nguồn + điểm tươi rồi lọt top.
        score -= 4;
        r.vi_sao << QStringLiteral("⚠ không có từ khoá thị trường");
    }

    if (a.sort_ts > 0) {
        const double gio = static_cast<double>(now_ts - a.sort_ts) / 3600.0;
        if (gio <= 6) {
            score += 3;
            r.vi_sao << QStringLiteral("%1 giờ trước").arg(qRound(gio));
        } else if (gio <= 24) {
            score += 1;
            r.vi_sao << QStringLiteral("%1 giờ trước").arg(qRound(gio));
        }
        if (gio > 72) { // bẫy #4
            score -= 6;
            r.vi_sao << QStringLiteral("⚠ cũ %1 ngày").arg(qRound(gio / 24));
        }
    } else {
        score -= 3;
        r.vi_sao << QStringLiteral("⚠ không rõ giờ đăng");
    }

    const QString bad = first_hit(txt, kw_phat());
    if (!bad.isEmpty()) {
        score -= 8;
        r.vi_sao << QStringLiteral("⚠ không liên quan thị trường: %1").arg(bad);
    }

    r.score = score;
    return r;
}

QVector<RankedArticle> top_by_market(const QVector<NewsArticle>& articles, int per_market,
                                     int64_t now_ts) {
    QVector<RankedArticle> all;
    all.reserve(articles.size());
    // Dưới 3 điểm là tin KHÔNG có dấu hiệu thị trường (điểm tối đa của loại đó là 0) — không lấp
    // cho đủ suất. Soi gương goi_tintop.DIEM_TOI_THIEU: ngày 22/09/2026 cột Trung Quốc bản Python
    // từng hiện "trẻ em Gaza đi học lại" với điểm 0 chỉ vì cột phải đủ 3 dòng.
    constexpr int kDiemToiThieu = 3;
    for (const auto& a : articles) {
        auto r = rank_article(a, now_ts);
        if (r.market != Market::KHAC && r.score >= kDiemToiThieu)
            all.append(r);
    }

    std::stable_sort(all.begin(), all.end(), [](const RankedArticle& x, const RankedArticle& y) {
        if (x.score != y.score)
            return x.score > y.score;
        if (x.article.tier != y.article.tier)
            return x.article.tier < y.article.tier; // 1=wire thắng 4=blog
        return x.article.sort_ts > y.article.sort_ts;
    });

    // Thứ tự cột cố định để mắt không phải đi tìm — không sắp theo số bài tìm được.
    static const std::array<Market, 4> order = {Market::US, Market::VN, Market::CN, Market::EU};
    QHash<int, int> taken;
    QVector<QSet<QString>> seen_topic;
    QVector<RankedArticle> out;
    for (const Market m : order) {
        for (const auto& r : all) {
            if (r.market != m || taken[static_cast<int>(m)] >= per_market)
                continue;
            const QSet<QString> goc = topic_stems(vitext::fold(r.article.headline));
            const bool trung = std::any_of(seen_topic.cbegin(), seen_topic.cend(), [&goc](const QSet<QString>& t) {
                return QSet<QString>(t).intersect(goc).size() >= 2;
            });
            if (trung)
                continue; // hai hãng cùng đưa một sự kiện: giữ bản điểm cao hơn
            seen_topic.append(goc);
            out.append(r);
            taken[static_cast<int>(m)]++;
        }
    }
    return out;
}

} // namespace fincept::services
