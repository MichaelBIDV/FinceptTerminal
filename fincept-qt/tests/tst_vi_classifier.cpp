// Unit tests for src/services/news/NewsViText.{h,cpp} + NewsViClassifier.{h,cpp}
//
// Mỗi ca dưới đây là một cái bẫy ĐÃ ĐO trên tiêu đề tiếng Việt thật ngày 03/10/2026 (bản đồ news
// của đợt nâng cấp thông báo). Bộ phân loại cũ dò chuỗi con tiếng Anh nên cả 1.300 bài VN đều
// ROUTINE; bộ mới phải bắt được tin khẩn mà KHÔNG mắc các trùng chữ do bỏ dấu.
//
// Whitelist mã được đặt thẳng bằng set_ticker_data() để test không phụ thuộc tệp của cầu dữ liệu.

#include "services/news/NewsViClassifier.h"
#include "services/news/NewsViText.h"

#include <QString>
#include <QTest>

using namespace fincept::services;
using vinews::Impact;
using vinews::Priority;

namespace {

const QChar kZwnj(0x200C);
const QString kEmDash(QChar(0x2014)); // gạch dài, viết bằng mã để không lẫn với gạch ngang

vinews::Classification vi(const QString& headline, const QString& source = QStringLiteral("VIETSTOCK"),
                          const QString& category = QStringLiteral("MARKETS"),
                          const QString& summary = QString()) {
    return vinews::classify(headline, summary, source, category, QStringLiteral("VIETNAM"));
}

} // namespace

class TstViClassifier : public QObject {
    Q_OBJECT

  private slots:
    void init(); // chạy trước MỖI ca: đặt lại whitelist, để ca hỏng giữa chừng không lây sang ca sau

    void fold_strips_marks_and_invisible();
    void core_title_strips_bridge_labels();
    void detects_vietnamese();

    void nam_san_does_not_match_viet_nam_san_sang();
    void bi_bat_does_not_match_bat_dong_san();
    void khan_hiem_is_not_khan_cap();
    void zero_width_inside_keyword_still_matches();
    void huy_variants_both_match();

    void federal_register_is_routine_admin();
    void regulatory_english_notice_is_admin();

    void ambiguous_codes_need_anchor();
    void anchored_codes_are_kept();
    void codes_inside_all_caps_vietnamese_are_words();

    void khoi_to_is_flash_with_anchor();
    void khoi_to_is_downgraded_without_anchor();
    void nhnn_policy_rate_with_number_is_flash();
    void deposit_rate_or_no_number_is_not_flash();
    void commercial_bank_rates_are_not_sbv_flash();
    void government_bonds_are_not_an_anchor();
    void foreign_government_is_not_an_anchor();
    void event_key_uses_title_tickers_first();
    void fed_rate_change_is_urgent();
    void sell_side_capped_at_breaking();
    void artifact_source_is_not_classified();

    void english_boilerplate_is_not_flash();
    void english_uses_word_boundaries();

    void story_key_ignores_bridge_labels();
    void runs_without_ticker_whitelist();
};

void TstViClassifier::init() {
    vitext::TickerData d;
    d.ma = {QStringLiteral("HPG"), QStringLiteral("VNM"), QStringLiteral("USD"), QStringLiteral("HCM"),
            QStringLiteral("PGS"), QStringLiteral("CPI"), QStringLiteral("PNJ"), QStringLiteral("BID"),
            QStringLiteral("SGI"), QStringLiteral("FPT"), QStringLiteral("KOS")};
    d.nhap_nhang = {QStringLiteral("USD"), QStringLiteral("HCM"), QStringLiteral("PGS"), QStringLiteral("CPI"),
                    QStringLiteral("BID"), QStringLiteral("SGI")};
    vitext::set_ticker_data(d);
    QVERIFY(vitext::tickers_available());
}

// ── Chuẩn hoá ───────────────────────────────────────────────────────────────

void TstViClassifier::fold_strips_marks_and_invisible() {
    QCOMPARE(vitext::fold(QStringLiteral("Đình chỉ GIAO DỊCH")), QStringLiteral("dinh chi giao dich"));
    // Cầu dữ liệu chèn U+200C giữa chữ: "G<U+200C>DP" phải về "gdp".
    QCOMPARE(vitext::fold(QStringLiteral("G") + kZwnj + QStringLiteral("DP")), QStringLiteral("gdp"));
    for (const char16_t u : {char16_t(0x200B), char16_t(0x200D), char16_t(0x2060), char16_t(0xFEFF)})
        QCOMPARE(vitext::fold(QStringLiteral("F") + QChar(u) + QStringLiteral("ed")), QStringLiteral("fed"));
    // NFD (dấu tách rời) và NFC cho cùng một kết quả.
    const QString nfd = QStringLiteral("khởi tố").normalized(QString::NormalizationForm_D);
    QCOMPARE(vitext::fold(nfd), QStringLiteral("khoi to"));
    QCOMPARE(vitext::clean(nfd), QStringLiteral("khởi tố"));
}

void TstViClassifier::core_title_strips_bridge_labels() {
    QCOMPARE(vitext::core_title(QStringLiteral("[Vietcap IQ·Tin] CTB bị xử phạt ") + kEmDash +
                                QStringLiteral(" Vietstock · NEWS")),
             QStringLiteral("CTB bị xử phạt"));
    QCOMPARE(vitext::core_title(QStringLiteral("[Vietcap·đổi KN] TPB: TP 17.400→15.150 · SS-T3")),
             QStringLiteral("TPB: TP 17.400→15.150"));
    QCOMPARE(vitext::core_title(QStringLiteral("Áp dụng từ ngày 02/10/2026 · FACT-T2")),
             QStringLiteral("Áp dụng từ ngày 02/10/2026"));
    // Đuôi sau gạch dài có dấu phẩy là nội dung, không phải tên nguồn: chỉ bỏ nhãn.
    QCOMPARE(vitext::core_title(QStringLiteral("Thanh khoản cạn ") + kEmDash +
                                QStringLiteral(" giữ tiền, chưa distress · EST")),
             QStringLiteral("Thanh khoản cạn ") + kEmDash + QStringLiteral(" giữ tiền, chưa distress"));
}

void TstViClassifier::detects_vietnamese() {
    QVERIFY(vitext::is_vietnamese(QStringLiteral("Khối ngoại bán ròng")));
    QVERIFY(!vitext::is_vietnamese(QStringLiteral("Fed cuts rates by 25 basis points")));
    QVERIFY(!vitext::is_vietnamese(QStringLiteral("Café crème à Paris")));
    // â/ê/ô có cả trong tiếng Pháp và Bồ Đào Nha: không đủ để nhận là tiếng Việt.
    QVERIFY(!vitext::is_vietnamese(QStringLiteral("La Bourse de Paris recule, la fête est finie pour le CAC 40 "
                                                  "Les marchés européens ont été plutôt prudents")));
    QVERIFY(!vitext::is_vietnamese(QStringLiteral("Você sabe quanto o dólar subiu? Três motivos para a alta")));
    // Tiếng Việt chỉ có một ký tự riêng ("ầ") cộng các chữ dùng chung ("ô", "ê") vẫn được nhận.
    QVERIFY(vitext::is_vietnamese(QStringLiteral("Công ty lên sàn tuần sau")));
}

// ── Bẫy bỏ dấu ──────────────────────────────────────────────────────────────

void TstViClassifier::nam_san_does_not_match_viet_nam_san_sang() {
    // Đo được: "nam san" (bỏ dấu của "nằm sàn") khớp nhầm "Việt Nam sẵn sàng".
    QCOMPARE(vi(QStringLiteral("Việt Nam sẵn sàng đón dòng vốn ngoại")).priority, Priority::Routine);
    const auto r = vi(QStringLiteral("KOS nằm sàn 9 phiên liên tiếp"));
    QCOMPARE(r.priority, Priority::Breaking);
    QCOMPARE(r.impact, Impact::Medium);
}

void TstViClassifier::bi_bat_does_not_match_bat_dong_san() {
    // "bị bắt"/"bắt" bỏ dấu thành "bi bat"/"bat", trùng "bất động sản", "bị bất ngờ": phải khớp có dấu.
    QCOMPARE(vi(QStringLiteral("Bộ Công an: thị trường bất động sản phía Nam ấm lên")).priority, Priority::Routine);
    QCOMPARE(vi(QStringLiteral("Cổ đông HPG bị bất ngờ vì giá thép")).priority, Priority::Routine);
    QCOMPARE(vi(QStringLiteral("Bộ Công an bắt giữ nhóm thao túng giá")).priority, Priority::Flash);
    const auto r = vi(QStringLiteral("Nguyên Chủ tịch HPG bị bắt"));
    QCOMPARE(r.priority, Priority::Flash);
    QCOMPARE(r.event_key, QStringLiteral("bị bắt|HPG"));
}

void TstViClassifier::khan_hiem_is_not_khan_cap() {
    QCOMPARE(vi(QStringLiteral("Nguồn cung xăng dầu khan hiếm cục bộ")).priority, Priority::Routine);
    const auto r = vi(QStringLiteral("Thủ tướng chỉ thị khẩn cấp ứng phó bão"));
    QCOMPARE(r.priority, Priority::Urgent);
    QVERIFY(r.anchored);
}

void TstViClassifier::zero_width_inside_keyword_still_matches() {
    const QString h = QStringLiteral("Bộ Công an kh") + kZwnj + QStringLiteral("ởi tố nguyên Chủ tịch HĐQT");
    QCOMPARE(vi(h).priority, Priority::Flash);
}

void TstViClassifier::huy_variants_both_match() {
    QCOMPARE(vi(QStringLiteral("HOSE huỷ niêm yết bắt buộc cổ phiếu XYZ")).priority, Priority::Flash);
    QCOMPARE(vi(QStringLiteral("HOSE hủy niêm yết bắt buộc cổ phiếu XYZ")).priority, Priority::Flash);
}

// ── Văn bản hành chính ──────────────────────────────────────────────────────

void TstViClassifier::federal_register_is_routine_admin() {
    // Tiêu đề có "breaking"/"report" vẫn phải ROUTINE: nguồn là văn bản hành chính.
    const auto r = vinews::classify(QStringLiteral("Antidumping Duty Order on Steel From Vietnam: breaking report"),
                                    QStringLiteral("emergency notice"), QStringLiteral("US FEDERAL REGISTER"),
                                    QStringLiteral("REGULATORY"), QStringLiteral("VIETNAM"));
    QCOMPARE(r.priority, Priority::Routine);
    QCOMPARE(r.impact, Impact::Low);
    QVERIFY(r.is_admin);
}

void TstViClassifier::regulatory_english_notice_is_admin() {
    const auto r = vinews::classify(QStringLiteral("Notice of Intent to Conduct Five-Year Review"), QString(),
                                    QStringLiteral("USTR"), QStringLiteral("REGULATORY"), QStringLiteral("US"));
    QVERIFY(r.is_admin);
    QCOMPARE(r.priority, Priority::Routine);
    // Tiêu đề tiếng Việt trong REGULATORY không phải văn bản hành chính kiểu Federal Register.
    QVERIFY(!vi(QStringLiteral("Bộ Tài chính thông báo kết luận thanh tra"), QStringLiteral("BAO CHINH PHU"),
                QStringLiteral("REGULATORY"))
                 .is_admin);
}

// ── Mã chứng khoán ──────────────────────────────────────────────────────────

void TstViClassifier::ambiguous_codes_need_anchor() {
    QVERIFY(vitext::extract_tickers(QStringLiteral("Xuất siêu trở lại với 1,27 tỷ USD")).isEmpty());
    QVERIFY(vitext::extract_tickers(QStringLiteral("Chống ngập 10.000 tỷ đồng ở TP.HCM")).isEmpty());
    QVERIFY(vitext::extract_tickers(QStringLiteral("Kho hàng tại TP. HCM mở rộng")).isEmpty());
    QVERIFY(vitext::extract_tickers(QStringLiteral("PGS.TS Nguyễn Văn A nhận định")).isEmpty());
    QVERIFY(vitext::extract_tickers(QStringLiteral("CPI tháng 9 tăng 0,62%")).isEmpty());
    // Không có trong whitelist thì không bao giờ là mã: AI, NEWS, TP, SS, VN, FACT.
    QVERIFY(vitext::extract_tickers(QStringLiteral("[SS·NEWS] AI và TP VN · FACT-T2")).isEmpty());
    QVERIFY(vi(QStringLiteral("Tỷ giá USD tại TP.HCM tăng")).tickers.isEmpty());

    // Luật dấu chấm tự nó loại "TP.HCM"/"PGS.TS", kể cả khi mã không nằm trong nhóm nhập nhằng.
    vitext::TickerData plain;
    plain.ma = {QStringLiteral("HCM"), QStringLiteral("PGS")};
    vitext::set_ticker_data(plain);
    QVERIFY(vitext::extract_tickers(QStringLiteral("Chống ngập ở TP.HCM")).isEmpty());
    QVERIFY(vitext::extract_tickers(QStringLiteral("PGS.TS Nguyễn Văn A")).isEmpty());
    QCOMPARE(vitext::extract_tickers(QStringLiteral("Lãi quý của HCM.")), QStringList({QStringLiteral("HCM")}));
}

void TstViClassifier::anchored_codes_are_kept() {
    QCOMPARE(vitext::extract_tickers(QStringLiteral("Hòa Phát (HOSE: HPG) và cổ phiếu BID")),
             QStringList({QStringLiteral("HPG"), QStringLiteral("BID")}));
    QCOMPARE(vitext::extract_tickers(QStringLiteral("HCM:HOSE tăng trần")), QStringList({QStringLiteral("HCM")}));
    const QString up_arrow(QChar(0x25B2));
    QCOMPARE(vitext::extract_tickers(QStringLiteral("[SGI") + up_arrow + QStringLiteral("] tăng mạnh")),
             QStringList({QStringLiteral("SGI")}));
    QCOMPARE(vitext::extract_tickers(QStringLiteral("Khối ngoại mua FPT, VNM.")),
             QStringList({QStringLiteral("FPT"), QStringLiteral("VNM")}));
}

void TstViClassifier::codes_inside_all_caps_vietnamese_are_words() {
    // Đo được: "[CHÍNH PHỦ] TOP 8 TIN CHÍNH SÁCH" cho mã TIN. TIN, TOP đặt ngoài nhóm nhập nhằng để
    // thử riêng luật chữ hoa có dấu.
    vitext::TickerData d;
    d.ma = {QStringLiteral("TIN"), QStringLiteral("TOP"), QStringLiteral("MWG"), QStringLiteral("DGW"),
            QStringLiteral("FRT"), QStringLiteral("HPG")};
    vitext::set_ticker_data(d);
    QVERIFY(vitext::extract_tickers(QStringLiteral("[CHÍNH PHỦ] TOP 8 TIN CHÍNH SÁCH")).isEmpty());
    QVERIFY(vitext::extract_tickers(QStringLiteral("TỔNG HỢP THÔNG TIN GIAO DỊCH")).isEmpty());
    // Danh sách mã và nhãn bậc bằng chứng không có từ hoa có dấu: giữ nguyên.
    QCOMPARE(vitext::extract_tickers(QStringLiteral("MWG, DGW đồng loạt tăng; SS-T3 FRT")),
             QStringList({QStringLiteral("MWG"), QStringLiteral("DGW"), QStringLiteral("FRT")}));
    // Dấu ngắt vế tách mã khỏi phần viết hoa; mã được neo thì vẫn nhận.
    QCOMPARE(vitext::extract_tickers(QStringLiteral("HPG: LỢI NHUẬN QUÝ 3 TĂNG MẠNH")),
             QStringList({QStringLiteral("HPG")}));
    QCOMPARE(vitext::extract_tickers(QStringLiteral("CỔ PHIẾU (HOSE: TIN) TĂNG TRẦN")),
             QStringList({QStringLiteral("TIN")}));
}

// ── Luật bậc ────────────────────────────────────────────────────────────────

void TstViClassifier::khoi_to_is_flash_with_anchor() {
    const auto by_authority = vi(QStringLiteral("Bộ Công an khởi tố nguyên Chủ tịch HĐQT"));
    QCOMPARE(by_authority.priority, Priority::Flash);
    QCOMPARE(by_authority.impact, Impact::High);
    QVERIFY(by_authority.anchored);

    const auto by_ticker = vi(QStringLiteral("Khởi tố lãnh đạo HPG"));
    QCOMPARE(by_ticker.priority, Priority::Flash);
    QCOMPARE(by_ticker.tickers, QStringList({QStringLiteral("HPG")}));
    QCOMPARE(by_ticker.event_key, QStringLiteral("khởi tố|HPG"));
}

void TstViClassifier::khoi_to_is_downgraded_without_anchor() {
    // Đo được ~5 bài "khởi tố"/ngày, phần lớn doanh nghiệp không niêm yết: thiếu neo hạ một bậc.
    const auto r = vi(QStringLiteral("Khởi tố giám đốc doanh nghiệp vận tải"));
    QCOMPARE(r.priority, Priority::Urgent);
    QCOMPARE(r.impact, Impact::Medium);
    QVERIFY(!r.anchored);
    QVERIFY(r.event_key.startsWith(QStringLiteral("khởi tố|s:")));
}

void TstViClassifier::nhnn_policy_rate_with_number_is_flash() {
    const auto r = vi(QStringLiteral("NHNN tăng lãi suất điều hành thêm 0,5 điểm phần trăm"));
    QCOMPARE(r.priority, Priority::Flash);
    QCOMPARE(r.impact, Impact::High);
    // Con số nằm ở tóm tắt vẫn tính, miễn chủ thể NHNN ở tiêu đề.
    const auto s = vi(QStringLiteral("Ngân hàng Nhà nước giảm lãi suất tái cấp vốn"), QStringLiteral("CAFEF"),
                      QStringLiteral("ECONOMIC"), QStringLiteral("giảm lãi suất tái cấp vốn xuống 4,5%/năm"));
    QCOMPARE(s.priority, Priority::Flash);
}

void TstViClassifier::deposit_rate_or_no_number_is_not_flash() {
    QCOMPARE(vi(QStringLiteral("NHNN: nhiều ngân hàng tăng lãi suất huy động thêm 0,5%")).priority,
             Priority::Routine);
    QCOMPARE(vi(QStringLiteral("NHNN tăng lãi suất điều hành")).priority, Priority::Routine);
}

void TstViClassifier::commercial_bank_rates_are_not_sbv_flash() {
    // Đo khi rà soát: bốn ca đầu từng ra FLASH/HIGH (thông báo Critical) vì cụm định danh để tuỳ chọn,
    // phép loại "huy động" chỉ xét chữ ngay sau "lãi suất", và động từ + con số ở tóm tắt thuộc ngân
    // hàng thương mại.
    const auto econ = [](const QString& headline, const QString& summary) {
        return vi(headline, QStringLiteral("CAFEF"), QStringLiteral("ECONOMIC"), summary).priority;
    };
    QCOMPARE(econ(QStringLiteral("NHNN: nhiều ngân hàng tăng lãi suất thêm 0,5% kỳ hạn 6 tháng"), QString()),
             Priority::Routine);
    QCOMPARE(econ(QStringLiteral("NHNN yêu cầu kiểm soát tín dụng bất động sản"),
                  QStringLiteral("Trong tháng 9, Vietcombank giảm lãi suất 0,5% cho các khoản vay mua nhà")),
             Priority::Routine);
    QCOMPARE(econ(QStringLiteral("NHNN yêu cầu giảm lãi suất cho vay"),
                  QStringLiteral("Vietcombank hạ lãi suất xuống 5,5%/năm từ tuần sau.")),
             Priority::Routine);
    QCOMPARE(econ(QStringLiteral("Ngân hàng Nhà nước: lãi suất tiết kiệm tiếp tục giảm"),
                  QStringLiteral("Nhiều ngân hàng thương mại đã giảm lãi suất 0,2-0,5% ở kỳ hạn 6 tháng.")),
             Priority::Routine);
    // Cụm định danh của ngân hàng trung ương khác trong tóm tắt không thành quyết định của NHNN.
    QCOMPARE(econ(QStringLiteral("NHNN theo dõi sát diễn biến tỷ giá"),
                  QStringLiteral("Fed giảm lãi suất cơ bản 0,25 điểm phần trăm")),
             Priority::Routine);
}

void TstViClassifier::government_bonds_are_not_an_anchor() {
    // "trái phiếu chính phủ" chứa chữ "chính phủ" nhưng không phải cơ quan VN ra quyết định.
    QVERIFY(!vi(QStringLiteral("Bán tháo trái phiếu chính phủ toàn cầu tiếp diễn")).anchored);
    QVERIFY(vi(QStringLiteral("Chính phủ ban hành nghị định mới")).anchored);
}

void TstViClassifier::foreign_government_is_not_an_anchor() {
    const auto r = vi(QStringLiteral("Thủ tướng Nhật Bản bị bắt giữ? Tin đồn lan truyền"));
    QVERIFY(!r.anchored);
    QCOMPARE(r.priority, Priority::Urgent);
    QVERIFY(!vi(QStringLiteral("Chính phủ Mỹ đóng cửa tuần thứ hai")).anchored);
    // So có dấu: "Chính phủ nhất trí" (bỏ dấu "chinh phu nhat") vẫn là Chính phủ VN.
    QVERIFY(vi(QStringLiteral("Chính phủ nhất trí phương án giá điện")).anchored);
    QVERIFY(vi(QStringLiteral("Thủ tướng yêu cầu không tăng giá điện")).anchored);
}

void TstViClassifier::event_key_uses_title_tickers_first() {
    // Cùng tin KOS giải chấp từng ra hai khoá "KOS" và "KOS,PNJ" (PNJ ở tóm tắt): ba bài thật, một khoá.
    const auto a = vi(QStringLiteral("KOS giảm sàn 9 phiên liên tiếp, lãnh đạo liên tục bị bán giải chấp"),
                      QStringLiteral("CAFEF"), QStringLiteral("MARKETS"),
                      QStringLiteral("Cổ phiếu KOS tiếp tục bị bán tháo, trong khi PNJ đi ngang"));
    const auto b = vi(QStringLiteral("Ông Nguyễn Việt Cường bị bán giải chấp trong phiên 1/10"),
                      QStringLiteral("CAFEF"), QStringLiteral("MARKETS"),
                      QStringLiteral("KOS đã mất hơn 52% thị giá chỉ sau nửa tháng."));
    QCOMPARE(a.event_key, QStringLiteral("giải chấp|KOS"));
    QCOMPARE(b.event_key, QStringLiteral("giải chấp|KOS"));
    QCOMPARE(a.tickers, QStringList({QStringLiteral("KOS"), QStringLiteral("PNJ")}));
}

void TstViClassifier::fed_rate_change_is_urgent() {
    const auto r = vi(QStringLiteral("Fed giảm lãi suất 0,25 điểm phần trăm"));
    QCOMPARE(r.priority, Priority::Urgent);
    QCOMPARE(r.impact, Impact::Medium);
}

void TstViClassifier::sell_side_capped_at_breaking() {
    QCOMPARE(vi(QStringLiteral("Khởi tố lãnh đạo HPG · SS-T3"), QStringLiteral("HSC·RESEARCH")).priority,
             Priority::Breaking);
}

void TstViClassifier::artifact_source_is_not_classified() {
    QCOMPARE(vi(QStringLiteral("[FFT] Bộ Công an khởi tố nguyên Chủ tịch HĐQT"), QStringLiteral("HDCV ARTIFACT"))
                 .priority,
             Priority::Routine);
}

// ── Tin tiếng Anh ───────────────────────────────────────────────────────────

void TstViClassifier::english_boilerplate_is_not_flash() {
    // Guardian dán câu đóng khung liền vào chữ trước: "authorisationGet our breaking news email…".
    QCOMPARE(vinews::english_priority(QStringLiteral("OpenAI says its review into hacks is complete"),
                                      QStringLiteral("accessing Medicare without authorisationGet our breaking news "
                                                     "email, free app or daily news podcast")),
             Priority::Routine);
    QCOMPARE(vinews::english_priority(QStringLiteral("Trump threatens tariffs"),
                                      QStringLiteral("This live blog is now closed.Sign up for the breaking news US "
                                                     "email")),
             Priority::Routine);
    QCOMPARE(vinews::english_priority(QStringLiteral("Breaking: Fed cuts rates"), QString()), Priority::Flash);
    const auto r = vinews::classify(QStringLiteral("Bruce Baird dies aged 84"),
                                    QStringLiteral("…for SydneyGet our breaking news email, free app or daily news "
                                                   "podcast"),
                                    QStringLiteral("GUARDIAN"), QStringLiteral("GEOPOLITICS"), QStringLiteral("AU"));
    QCOMPARE(r.priority, Priority::Routine);
}

void TstViClassifier::english_uses_word_boundaries() {
    QCOMPARE(vinews::english_priority(QStringLiteral("Company reported earnings"), QString()), Priority::Routine);
    QCOMPARE(vinews::english_priority(QStringLiteral("New report on jobs"), QString()), Priority::Breaking);
    QCOMPARE(vinews::english_priority(QStringLiteral("Air raid alert sounded"), QString()), Priority::Flash);
    QCOMPARE(vinews::english_priority(QStringLiteral("Emergency oil reserves released"), QString()), Priority::Urgent);
}

// ── Khoá câu chuyện ─────────────────────────────────────────────────────────

void TstViClassifier::story_key_ignores_bridge_labels() {
    // Cùng một tin qua Vietstock và Vietcap AI (đo được 37 nhóm / 74 bài trùng trên 1.300 bài).
    const QString a = vinews::story_key(QStringLiteral("[Vietcap AI·Doanh nghiệp] CTB bị xử phạt ") + kEmDash +
                                        QStringLiteral(" Vietstock · NEWS"));
    const QString b = vinews::story_key(QStringLiteral("CTB bị xử phạt · FACT-T2"));
    QCOMPARE(a, b);
    QCOMPARE(a.size(), 16);
    QVERIFY(a != vinews::story_key(QStringLiteral("CTB bị cưỡng chế thuế")));
}

void TstViClassifier::runs_without_ticker_whitelist() {
    // Thiếu tệp: giữ bộ đang dùng, không văng.
    QVERIFY(!vitext::load_ticker_file(QStringLiteral("/nonexistent/fincept/vn_ma.json")));
    QVERIFY(vitext::tickers_available());

    // Không có whitelist nào: chỉ mất nhận diện mã, luật theo cơ quan VN vẫn chạy.
    vitext::set_ticker_data({});
    QVERIFY(!vitext::tickers_available());
    QVERIFY(vitext::extract_tickers(QStringLiteral("Hòa Phát (HOSE: HPG)")).isEmpty());
    QCOMPARE(vi(QStringLiteral("Bộ Công an khởi tố nguyên Chủ tịch HĐQT")).priority, Priority::Flash);
    QCOMPARE(vi(QStringLiteral("Khởi tố lãnh đạo HPG")).priority, Priority::Urgent);
}

QTEST_GUILESS_MAIN(TstViClassifier)
#include "tst_vi_classifier.moc"
