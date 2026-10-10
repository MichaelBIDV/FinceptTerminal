// src/services/news/NewsViText.cpp
// Xem NewsViText.h: vì sao phải bỏ ký tự vô hình, vì sao không dùng regex ASCII, vì sao mã CK
// đi qua whitelist.
#include "services/news/NewsViText.h"

#include "core/logging/Logger.h"

#include <QDir>
#include <QFile>
#include <QJsonArray>
#include <QJsonDocument>
#include <QJsonObject>
#include <QMutex>
#include <QMutexLocker>
#include <QRegularExpression>

#include <memory>
#include <mutex>

namespace fincept::services::vitext {

namespace {

// Trần kích thước tệp whitelist: ~1.500 mã chỉ cỡ 20 KB, quá 2 MB là tệp sai.
constexpr qint64 kMaxTickerFileBytes = 2 * 1024 * 1024;

// Số từ viết hoa có dấu kề mã để coi mã là chữ của tiêu đề viết hoa toàn bộ (caps_vi_words).
constexpr int kCapsPhraseWords = 2;

bool is_invisible(char16_t u) {
    return u == 0x200B || u == 0x200C || u == 0x200D || u == 0x2060 || u == 0xFEFF;
}

bool is_upper_ascii(QChar c) {
    return c.unicode() >= u'A' && c.unicode() <= u'Z';
}

bool is_upper_or_digit_ascii(QChar c) {
    return is_upper_ascii(c) || (c.unicode() >= u'0' && c.unicode() <= u'9');
}

bool is_code(const QString& s) {
    return s.size() == 3 && is_upper_ascii(s.at(0)) && is_upper_or_digit_ascii(s.at(1)) &&
           is_upper_or_digit_ascii(s.at(2));
}

// Whitelist dùng chung giữa luồng chính (enrich_article) và luồng nền. Hoán đổi nguyên khối
// bằng shared_ptr dưới mutex, người đọc giữ bản chụp của mình.
struct TickerStore {
    QMutex mutex;
    std::shared_ptr<const TickerData> data;
    bool preset = false; // set_ticker_data() đã chạy: không tự nạp tệp mặc định nữa
};

TickerStore& store() {
    static TickerStore s;
    return s;
}

std::shared_ptr<const TickerData> snapshot() {
    static std::once_flag once;
    std::call_once(once, []() {
        bool preset = false;
        {
            QMutexLocker lock(&store().mutex);
            preset = store().preset;
        }
        if (!preset)
            load_ticker_file(default_ticker_file());
    });
    QMutexLocker lock(&store().mutex);
    return store().data;
}

// Từ viết hoa CÓ DẤU (chữ ngoài ASCII, không chữ thường) đứng kề mã, đếm theo một chiều (step ±1)
// từ vị trí `k`. Đi qua số và từ hoa ASCII ("TOP 8"), dừng ở từ có chữ thường hoặc dấu ngắt vế.
// Mã là ASCII nên tiêu đề viết hoa toàn bộ kiểu "[CHÍNH PHỦ] TOP 8 TIN CHÍNH SÁCH" lộ ra nhờ các
// từ có dấu xung quanh; còn danh sách mã "MWG, DGW, GDA" hay nhãn "SS-T3" không có từ nào như vậy.
int caps_vi_words(const QString& t, int k, int step) {
    int n = 0;
    while (k >= 0 && k < t.size()) {
        const QChar c = t.at(k);
        if (!c.isLetterOrNumber()) {
            if (QStringLiteral(".,;:!?|\n").contains(c))
                break;
            k += step;
            continue;
        }
        bool lower = false;
        bool non_ascii = false;
        for (; k >= 0 && k < t.size() && t.at(k).isLetterOrNumber(); k += step) {
            lower = lower || t.at(k).isLower();
            non_ascii = non_ascii || (t.at(k).isLetter() && t.at(k).unicode() > 0x7F);
        }
        if (lower)
            break;
        if (non_ascii)
            ++n;
    }
    return n;
}

// Mã nhập nhằng chỉ được nhận khi văn bản tự neo nó là mã CK.
bool anchored_code(const QString& text, const QString& code) {
    const QString c = QRegularExpression::escape(code);
    const QRegularExpression re(
        QStringLiteral("\\((?i:HOSE|HNX|UPCOM)\\s*:\\s*%1\\)"
                       "|(?<![\\p{L}\\p{N}])%1\\s*:\\s*(?i:HOSE|HNX|UPCOM)(?![\\p{L}\\p{N}])"
                       "|\\[%1[\\x{25B2}\\x{25BC}\\x{2022}]\\]"
                       "|(?i:mã chứng khoán|mã ck|mã|cổ phiếu)\\s*:?\\s*%1(?![\\p{L}\\p{N}])")
            .arg(c),
        QRegularExpression::UseUnicodePropertiesOption);
    return re.match(text).hasMatch();
}

} // namespace

QString clean(const QString& s) {
    QString out;
    out.reserve(s.size());
    for (const QChar c : s) {
        if (!is_invisible(c.unicode()))
            out.append(c);
    }
    return out.normalized(QString::NormalizationForm_C);
}

QString fold(const QString& s) {
    QString t = clean(s);
    t.replace(QChar(0x0111), QLatin1Char('d')); // đ
    t.replace(QChar(0x0110), QLatin1Char('d')); // Đ
    t = t.normalized(QString::NormalizationForm_D);
    QString out;
    out.reserve(t.size());
    for (const QChar c : t) {
        if (c.category() != QChar::Mark_NonSpacing)
            out.append(c);
    }
    return out.toLower();
}

QString core_title(const QString& headline) {
    // "[Vietcap IQ·Tin] …" và hậu tố nhãn bậc bằng chứng mà cầu dữ liệu gắn vào cuối tiêu đề.
    // Phần nguồn sau gạch dài không chứa dấu phẩy: đuôi "<gạch dài> giữ tiền, chưa distress · EST" là nội dung.
    static const QRegularExpression prefix(QStringLiteral("^\\s*\\[[^\\]]{0,60}\\]\\s*"));
    static const QRegularExpression suffix_source(
        QStringLiteral("\\s*\\x{2014}\\s*[^\\x{2014}\\x{00B7},]{1,60}\\x{00B7}\\s*"
                       "(?:NEWS|FACT-T\\d|SS-T3|EST|UNVERIFIED)\\s*$"));
    static const QRegularExpression suffix_label(
        QStringLiteral("\\s*\\x{00B7}\\s*(?:NEWS|FACT-T\\d|SS-T3|EST|UNVERIFIED)\\s*$"));
    QString t = clean(headline);
    t.remove(prefix);
    t.remove(suffix_source);
    t.remove(suffix_label);
    return t.trimmed();
}

bool has_word(const QString& hay, const QString& needle) {
    if (needle.isEmpty())
        return false;
    int from = 0;
    while (true) {
        const int i = hay.indexOf(needle, from);
        if (i < 0)
            return false;
        const int e = i + needle.size();
        const bool left_ok = (i == 0) || !hay.at(i - 1).isLetterOrNumber();
        const bool right_ok = (e >= hay.size()) || !hay.at(e).isLetterOrNumber();
        if (left_ok && right_ok)
            return true;
        from = i + 1;
    }
}

bool is_vietnamese(const QString& s) {
    // ơ/ư và dải U+1EA0–U+1EF9 chỉ có trong tiếng Việt. ă/â/đ/ê/ô còn có trong tiếng Pháp ("fête"),
    // Bồ Đào Nha ("Você", "Três"), Romania, Croatia: chỉ được đếm thêm khi đã có một ký tự riêng.
    static const QString chi_vi = QStringLiteral("ơưƠƯ");
    static const QString dung_chung = QStringLiteral("ăâđêôĂÂĐÊÔ");
    int rieng = 0;
    int tong = 0;
    for (const QChar c : s.normalized(QString::NormalizationForm_C)) {
        const char16_t u = c.unicode();
        if ((u >= 0x1EA0 && u <= 0x1EF9) || chi_vi.contains(c)) {
            ++rieng;
            ++tong;
        } else if (dung_chung.contains(c)) {
            ++tong;
        }
        if (rieng >= 1 && tong >= 2)
            return true;
    }
    return false;
}

// ── Mã chứng khoán VN ───────────────────────────────────────────────────────

QString default_ticker_file() {
    // Cùng quy ước với HlpData::defaultSystemDir(): HDCV_SYSTEM_DIR ghi đè thư mục _System.
    const QString env = qEnvironmentVariable("HDCV_SYSTEM_DIR");
    const QString sys = env.isEmpty() ? QDir::homePath() + QStringLiteral("/SECOND BRAIN-OBSIDIAN/_System")
                                      : QDir::cleanPath(env);
    return sys + QStringLiteral("/fincept_bridge/data/vn_ma.json");
}

bool load_ticker_file(const QString& path) {
    QFile f(path);
    if (!f.open(QIODevice::ReadOnly)) {
        LOG_WARN("NewsViText", QString("Ticker whitelist not found (%1): VN ticker detection disabled").arg(path));
        return false;
    }
    if (f.size() > kMaxTickerFileBytes) {
        LOG_WARN("NewsViText", QString("Ticker whitelist too large (%1 bytes): %2").arg(f.size()).arg(path));
        return false;
    }
    QJsonParseError err;
    const QJsonDocument doc = QJsonDocument::fromJson(f.readAll(), &err);
    if (err.error != QJsonParseError::NoError || !doc.isObject()) {
        LOG_WARN("NewsViText", QString("Ticker whitelist unreadable (%1): %2").arg(err.errorString(), path));
        return false;
    }
    auto data = std::make_shared<TickerData>();
    const QJsonObject o = doc.object();
    for (const auto& v : o.value(QStringLiteral("ma")).toArray()) {
        const QString m = v.toString().trimmed().toUpper();
        if (is_code(m))
            data->ma.insert(m);
    }
    for (const auto& v : o.value(QStringLiteral("nhap_nhang")).toArray()) {
        const QString m = v.toString().trimmed().toUpper();
        if (is_code(m))
            data->nhap_nhang.insert(m);
    }
    if (data->ma.isEmpty()) {
        LOG_WARN("NewsViText", QString("Ticker whitelist has no codes: %1").arg(path));
        return false;
    }
    const int n_ma = data->ma.size();
    const int n_ambig = data->nhap_nhang.size();
    {
        QMutexLocker lock(&store().mutex);
        store().data = std::move(data);
    }
    LOG_INFO("NewsViText", QString("Loaded %1 VN tickers (%2 ambiguous) from %3").arg(n_ma).arg(n_ambig).arg(path));
    return true;
}

void set_ticker_data(const TickerData& data) {
    QMutexLocker lock(&store().mutex);
    store().preset = true;
    store().data = std::make_shared<const TickerData>(data);
}

bool tickers_available() {
    const auto data = snapshot();
    return data && !data->ma.isEmpty();
}

QStringList extract_tickers(const QString& text, int max_count) {
    const auto data = snapshot();
    if (!data || data->ma.isEmpty() || max_count <= 0)
        return {};
    const QString t = clean(text);
    const int n = t.size();
    QStringList out;
    for (int i = 0; i + 3 <= n; ++i) {
        if (!is_upper_ascii(t.at(i)) || !is_upper_or_digit_ascii(t.at(i + 1)) ||
            !is_upper_or_digit_ascii(t.at(i + 2)))
            continue;
        // Biên trái: không dính chữ/số, không đứng sau dấu chấm ("TP.HCM").
        if (i > 0 && (t.at(i - 1).isLetterOrNumber() || t.at(i - 1) == QLatin1Char('.')))
            continue;
        // Biên phải: không dính chữ/số, không phải "PGS.TS" (dấu chấm rồi chữ). "HPG." cuối câu vẫn nhận.
        const int e = i + 3;
        if (e < n && t.at(e).isLetterOrNumber())
            continue;
        if (e + 1 < n && t.at(e) == QLatin1Char('.') && t.at(e + 1).isLetter())
            continue;
        const QString code = t.mid(i, 3);
        if (!data->ma.contains(code) || out.contains(code))
            continue;
        if (data->nhap_nhang.contains(code) && !anchored_code(t, code))
            continue;
        // Giữa cụm chữ hoa có dấu ("TOP 8 TIN CHÍNH SÁCH") thì là chữ, trừ khi được neo.
        if (caps_vi_words(t, i - 1, -1) + caps_vi_words(t, e, 1) >= kCapsPhraseWords && !anchored_code(t, code))
            continue;
        out << code;
        if (out.size() >= max_count)
            break;
    }
    return out;
}

} // namespace fincept::services::vitext
