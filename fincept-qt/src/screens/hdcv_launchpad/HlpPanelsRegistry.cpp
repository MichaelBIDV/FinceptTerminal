// src/screens/hdcv_launchpad/HlpPanelsRegistry.cpp
// HĐCV LAUNCHPAD — the component registry (panels.js `PANELS`): all 24 entries in panels.js order, so
// the "+ Component" sheet lists the same cards as the web. name / desc / w / h / linked / title are
// copied verbatim from panels.js (they show in the sheet and the panel headers). Every component
// renders its web template (HlpPanels_*.cpp): the 16 the three Fincept dashboards use (ck · vimo ·
// widata) and the 8 only the sheet offers here (sector, bidv, flash, reports, prov in
// HlpPanels_Extra.cpp; vietcapma, vietcaptin, xanhvo in HlpPanels_Vietcap.cpp).
//
// One deliberate deviation: `sgitin`. The owner (27/09/2026) replaced its source — the web reads SGI
// Capital posts relayed by a Facebook KOL; here it reads the weekly "Trạm Quan Trắc Vĩ Mô" issue
// (SPEC §8). The title stays "SGI CAPITAL" as instructed, but the sheet card's name/desc describe the
// new source instead of claiming "qua kênh KOL", which would now be false.
#include "screens/hdcv_launchpad/HlpPanels.h"

namespace fincept::screens::hlp {

namespace {

using hlpreg_Title = std::function<QString(const QString&)>;

/// `title: () => '…'` — a title that ignores the linked ticker.
hlpreg_Title hlpreg_fixed(const QString& s) {
    return [s](const QString&) { return s; };
}

PanelDef hlpreg_def(const char* id, const QString& name, int w, int h, bool linked, const QString& desc,
                    hlpreg_Title title, std::function<NodeP(RenderCtx&)> render) {
    PanelDef d;
    d.id = QString::fromLatin1(id);
    d.name = name;
    d.desc = desc;
    d.w = w;
    d.h = h;
    d.linked = linked;
    d.title = std::move(title);
    d.render = std::move(render);
    return d;
}

QVector<PanelDef> hlpreg_build() {
    QVector<PanelDef> v;
    v.reserve(24);
    v << hlpreg_def("cong", QStringLiteral("CỔNG · Chế độ thị trường"), 3, 300, false,
                    QStringLiteral("Tiền đắt/rẻ, trend–breadth–rotation–macro, hệ số size. Bắt buộc đọc trước mọi "
                                   "nhận định."),
                    hlpreg_fixed(QStringLiteral("CỔNG · Market Regime")), render_cong);
    v << hlpreg_def("idx", QStringLiteral("VN-Index · P/E và ex-Vin"), 5, 264, false,
                    QStringLiteral("P/E toàn phần so với P/E đã tách VIC+VHM+VRE — chỉ số toàn phần bị họ Vin bóp "
                                   "méo."),
                    hlpreg_fixed(QStringLiteral("VN-INDEX · P/E · EX-VIN")), render_idx);
    v << hlpreg_def("monitor", QStringLiteral("Monitor · Bảng theo dõi"), 5, 360, true,
                    QStringLiteral("Lưới mã: giá, P/E σ, P/B σ, conviction, RRG. Bấm một dòng để đổi mã liên kết."),
                    hlpreg_fixed(QStringLiteral("MONITOR · VN200")), render_monitor);
    v << hlpreg_def("desc", QStringLiteral("Mô tả mã · Security Description"), 4, 264, true,
                    QStringLiteral("Hồ sơ một mã: định giá σ, forward, conviction, điểm gãy thesis, link nguồn."),
                    [](const QString& c) { return c + QStringLiteral(" · MÔ TẢ"); }, render_desc);
    v << hlpreg_def("chart", QStringLiteral("Vùng giá σ · HHP"), 5, 290, true,
                    QStringLiteral("Vị trí mã trên trục σ của chính chuỗi P/E và P/B lịch sử, kèm mức P/E theo "
                                   "μ±1σ/±2σ."),
                    [](const QString& c) { return c + QStringLiteral(" · VÙNG GIÁ σ"); }, render_chart);
    v << hlpreg_def("sigma", QStringLiteral("Thước σ · Toàn universe"), 7, 360, true,
                    QStringLiteral("Toàn bộ 194 mã trên một trục σ. Thấy ngay độ rộng định giá và mã đang lệch."),
                    [](const QString& c) { return QStringLiteral("THƯỚC σ · ") + c + QStringLiteral(" trên trục"); },
                    render_sigma);
    v << hlpreg_def("sector", QStringLiteral("Chuyển động ngành · giá"), 5, 300, false,
                    QStringLiteral("Biến động 1 phiên và 5 phiên theo nhóm ngành, từ Sector Analyzer."),
                    hlpreg_fixed(QStringLiteral("CHUYỂN ĐỘNG NGÀNH")), render_sector);
    v << hlpreg_def("bidv", QStringLiteral("Điểm ngành + GHTD (nội bộ)"), 4, 300, false,
                    QStringLiteral("Đổi BẬC theo QĐ 1106 và ngành vượt giới hạn tín dụng. Dữ liệu nội bộ — không đưa "
                                   "ra ngoài."),
                    hlpreg_fixed(QStringLiteral("ĐIỂM NGÀNH · GHTD ⚠ NỘI BỘ")), render_bidv);
    v << hlpreg_def("news", QStringLiteral("Dòng tin theo chủ đề"), 5, 340, true,
                    QStringLiteral("Tin ngành, chính sách, thị trường. Lọc theo chủ đề hoặc theo mã đang liên kết."),
                    hlpreg_fixed(QStringLiteral("TIN · THEO CHỦ ĐỀ")), render_news);
    v << hlpreg_def("rasoat", QStringLiteral("Rà soát · việc cần làm"), 3, 340, false,
                    QStringLiteral("Phát hiện tự động mỗi sáng: nguồn hỏng, số lệch, việc treo."),
                    hlpreg_fixed(QStringLiteral("RÀ SOÁT HẰNG NGÀY")), render_rasoat);
    v << hlpreg_def("flash", QStringLiteral("Ứng viên Flashnote"), 4, 340, false,
                    QStringLiteral("Sự kiện đủ sức thành báo cáo nhanh. Bản DRAFT — phải có analyst điền tác động "
                                   "thật."),
                    hlpreg_fixed(QStringLiteral("ỨNG VIÊN FLASHNOTE")), render_flash);
    v << hlpreg_def("reports", QStringLiteral("Thư viện báo cáo PDF"), 7, 280, false,
                    QStringLiteral("Báo cáo ngành/vĩ mô/chiến lược đã tải về từ Simplize, Vietcap, HSC RS."),
                    hlpreg_fixed(QStringLiteral("THƯ VIỆN BÁO CÁO")), render_reports);
    v << hlpreg_def("prov", QStringLiteral("Nguồn & độ tươi"), 5, 280, false,
                    QStringLiteral("Mỗi panel lấy số từ đâu, tệp cập nhật lúc nào, nguồn nào hỏng."),
                    hlpreg_fixed(QStringLiteral("NGUỒN · ĐỘ TƯƠI")), render_prov);
    v << hlpreg_def("cpicanh", QStringLiteral("CPI · cảnh báo định nghĩa"), 6, 380, false,
                    QStringLiteral("Chuỗi CPI đang nuôi lãi suất thực Fisher có dấu hiệu trộn hai định nghĩa. Đo "
                                   "dáng theo từng năm."),
                    hlpreg_fixed(QStringLiteral("⚠ CPI · TRỘN ĐỊNH NGHĨA")), render_cpicanh);
    v << hlpreg_def("vietcapma", QStringLiteral("Vietcap IQ · room ngoại & sở hữu"), 7, 400, true,
                    QStringLiteral("85 mã: giá mục tiêu, upside, room ngoại, khối ngoại đang giữ, sở hữu nhà nước."),
                    [](const QString& c) { return QStringLiteral("VIETCAP IQ · ") + c + QStringLiteral(" trong bảng"); },
                    render_vietcapma);
    v << hlpreg_def("vietcaptin", QStringLiteral("Vietcap IQ · tin CBTT theo mã"), 5, 400, true,
                    QStringLiteral("Công bố thông tin gốc theo từng mã: nghị quyết HĐQT, ĐHĐCĐ, giao dịch cổ đông "
                                   "lớn."),
                    [](const QString& c) { return QStringLiteral("CBTT · lọc ") + c; }, render_vietcaptin);
    v << hlpreg_def("xanhvo", QStringLiteral("Xanh vỏ đỏ lòng · tuổi NỘI DUNG"), 5, 300, false,
                    QStringLiteral("Tệp được ghi lại mỗi ngày nhưng ruột đã đóng băng. Đo mốc thời gian BÊN TRONG "
                                   "tệp, không đo mtime."),
                    hlpreg_fixed(QStringLiteral("⚠ XANH VỎ ĐỎ LÒNG")), render_xanhvo);
    v << hlpreg_def("songuon", QStringLiteral("Sổ nguồn · BERI và Chứng khoán"), 7, 400, false,
                    QStringLiteral("Đăng ký từng nguồn: cấp bằng chứng, cơ quan công bố gốc, kênh lấy, độ tươi đo "
                                   "từ tệp thật."),
                    hlpreg_fixed(QStringLiteral("SỔ NGUỒN")), render_songuon);
    v << hlpreg_def("alerts", QStringLiteral("Cảnh báo đang bật"), 4, 280, false,
                    QStringLiteral("Các luật cảnh báo và lần bắn gần nhất. Tin đi qua cổng tg_gate về Telegram."),
                    hlpreg_fixed(QStringLiteral("CẢNH BÁO")), render_alerts);
    v << hlpreg_def("dongho", QStringLiteral("Ba chiếc đồng hồ + CỔNG tiền"), 5, 400, false,
                    QStringLiteral("Khung xác nhận đáy của HHP: thời gian · định giá · dòng tiền. Kèm dòng CỔNG chu "
                                   "kỳ tiền lấy từ Lăng Kính FFT, đối chiếu với market_regime."),
                    hlpreg_fixed(QStringLiteral("CỔNG TIỀN · BA CHIẾC ĐỒNG HỒ")), render_dongho);
    v << hlpreg_def("chinhphu", QStringLiteral("ChínhPhủ Daily · KPI & tâm điểm"), 7, 400, false,
                    QStringLiteral("Bảng KPI vĩ mô và các mục của artifact ChínhPhủ Daily, kèm nhãn bằng chứng từng "
                                   "dòng và cảnh báo pipeline đã ngừng."),
                    hlpreg_fixed(QStringLiteral("CHÍNH PHỦ · KPI VĨ MÔ")), render_chinhphu);
    v << hlpreg_def("fftma", QStringLiteral("FFT · thanh khoản trên free float"), 6, 380, false,
                    QStringLiteral("Pillar V của Lăng Kính: Market FFT VN100/VN30 theo percentile 3 năm, đếm mã cạn "
                                   "cung và phân phối, FFT từng mã."),
                    hlpreg_fixed(QStringLiteral("FFT · PILLAR V")), render_fftma);
    // Title, w and h as panels.js; name/desc re-worded for the new source (see file header), the desc
    // kept to the card height of its row so the sheet box keeps the web's size and position.
    v << hlpreg_def("sgitin", QStringLiteral("SGI Capital · Trạm Quan Trắc Vĩ Mô"), 5, 340, false,
                    QStringLiteral("Bản tuần routine Cowork thứ Bảy: chế độ, tiền mặt, điểm thành phần, tám khối, "
                                   "điều kiện đáy, ngưỡng đảo chiều."),
                    hlpreg_fixed(QStringLiteral("SGI CAPITAL")), render_sgitin);
    v << hlpreg_def("wdsignal", QStringLiteral("WiData · Market Signals"), 12, 600, false,
                    QStringLiteral("Tín hiệu vĩ mô VN/Mỹ/TQ/châu Âu, hàng hoá, thị trường của WiData. Bấm một tín "
                                   "hiệu để xem biểu đồ chỉ tiêu; chọn bất kỳ chỉ tiêu nào trong danh mục."),
                    hlpreg_fixed(QStringLiteral("WIDATA · MARKET SIGNALS")), render_wdsignal);
    return v;
}

} // namespace

const QVector<PanelDef>& panel_defs() {
    static const QVector<PanelDef> defs = hlpreg_build();
    return defs;
}

const PanelDef* panel_def(const QString& id) {
    for (const PanelDef& d : panel_defs())
        if (d.id == id)
            return &d;
    return nullptr;
}

} // namespace fincept::screens::hlp
