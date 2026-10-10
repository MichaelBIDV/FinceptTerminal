// src/screens/langkinh/LangKinhPanel.cpp
// Lăng Kính cấu trúc cổ đông & FFT (VN30 · VN100) — xem LangKinhPanel.h.
#include "screens/langkinh/LangKinhPanel.h"

#include "core/logging/Logger.h"
#include "screens/langkinh/LkBlockView.h"
#include "services/economics/EconomicsService.h"
#include "ui/theme/Theme.h"

#include <QAbstractItemView>
#include <QCompleter>
#include <QHBoxLayout>
#include <QJsonObject>
#include <QKeyEvent>
#include <QLineEdit>
#include <QRegularExpression>
#include <QSignalBlocker>
#include <QStandardItem>
#include <QStandardItemModel>
#include <QStringList>
#include <QTimer>
#include <QValidator>

#include <algorithm>
#include <functional>
#include <utility>

namespace fincept::screens {

// Hằng + helper tự do: namespace có tên riêng, không đụng tên tệp khác.
namespace langkinh_panel {

constexpr const char* kSourceId = "langkinh";
constexpr const char* kScript = "fincept_langkinh.py";
constexpr const char* kColor = "#d97706";
// Gom các lần đổi combo/rổ liên tiếp (giữ phím, gõ tìm) thành một lần chạy script.
constexpr int kDebounceMs = 250;
// Ô gõ mã (V3.1): vai trò hoàn thành = mã trần; dòng popup = "VCB · <tên ≤40 ký tự>".
constexpr int kMaRole = Qt::UserRole + 1;
constexpr int kTenMax = 40;
constexpr int kPopupRows = 14;
// Popup mặc định rộng bằng ô (110px) → tên công ty chỉ còn vài ký tự; đặt rộng tối thiểu đủ "VCB · " + tên ~40 ký tự.
constexpr int kPopupMinW = 340;

struct ViewItem {
    const char* key;
    const char* label;
};

// Thứ tự = CONTRACT §3 + DELTA D6.1/D7.1 + V4.5 + LK_HOSO_SPEC (17 view; hoso · matran5 · sigma · rrg · mauhinh ngay
// sau chuoi; chuthe sau codong, cauchuyen sau chuthe); mục đầu (tongquan) là mặc định.
const ViewItem kViews[] = {
    {"tongquan", QT_TRANSLATE_NOOP("fincept::screens::LangKinhPanel", "Tổng quan phiên")},
    {"bangquet", QT_TRANSLATE_NOOP("fincept::screens::LangKinhPanel", "Bảng quét FFT")},
    {"matran", QT_TRANSLATE_NOOP("fincept::screens::LangKinhPanel", "Ma trận FFT × Giá (8 tuần)")},
    {"bocung", QT_TRANSLATE_NOOP("fincept::screens::LangKinhPanel", "Bo cung 2 năm")},
    {"xephang", QT_TRANSLATE_NOOP("fincept::screens::LangKinhPanel", "Xếp hạng & đổi trạng thái")},
    {"thitruong", QT_TRANSLATE_NOOP("fincept::screens::LangKinhPanel", "Market FFT VN30 · VN100")},
    {"chuoi", QT_TRANSLATE_NOOP("fincept::screens::LangKinhPanel", "Chuỗi FFT × Giá theo mã")},
    {"hoso", QT_TRANSLATE_NOOP("fincept::screens::LangKinhPanel", "Hồ sơ mã (tầm Artifact)")},
    {"matran5", QT_TRANSLATE_NOOP("fincept::screens::LangKinhPanel", "Ma trận 5 pillar")},
    {"sigma", QT_TRANSLATE_NOOP("fincept::screens::LangKinhPanel", "Vùng giá σ")},
    {"rrg", QT_TRANSLATE_NOOP("fincept::screens::LangKinhPanel", "RRG vs VN-Index")},
    {"mauhinh", QT_TRANSLATE_NOOP("fincept::screens::LangKinhPanel", "Mẫu hình NTH (hình giá)")},
    {"codong", QT_TRANSLATE_NOOP("fincept::screens::LangKinhPanel", "Cổ đông (Pillar I · Toàn Vũ)")},
    {"chuthe", QT_TRANSLATE_NOOP("fincept::screens::LangKinhPanel", "🧭 Ý đồ chủ thể (Pillar III)")},
    {"cauchuyen", QT_TRANSLATE_NOOP("fincept::screens::LangKinhPanel", "📖 Câu chuyện chủ thể")},
    {"phuongphap", QT_TRANSLATE_NOOP("fincept::screens::LangKinhPanel", "Phương pháp luận (§1)")},
    {"nguon", QT_TRANSLATE_NOOP("fincept::screens::LangKinhPanel", "Nguồn & giới hạn")},
};

// Mã của view theo mã khi chưa có mã nào (ma_ khởi tạo cũng là mã này).
constexpr const char* kMaMacDinh = "FPT";

/// View nhận MÃ làm đối số CLI (chuoi, hoso); các view khác nhận rổ (VN30/VN100/VN200).
bool is_ticker_view(const QString& view) {
    return view == QLatin1String("chuoi") || view == QLatin1String("hoso");
}

/// View đích khi người dùng chọn một mã (bấm/nhấp đúp mã trên trang, Enter ở ô MÃ): các view họ hồ sơ
/// (hoso · matran5 · sigma · rrg) mở hồ sơ mã; mauhinh mở trang mẫu hình của mã; mọi view khác giữ hành vi cũ —
/// chuỗi FFT × Giá.
QString ticker_target_view(const QString& view) {
    if (view == QLatin1String("mauhinh"))
        return QStringLiteral("mauhinh");
    const bool hoso_family = view == QLatin1String("hoso") || view == QLatin1String("matran5") ||
                             view == QLatin1String("sigma") || view == QLatin1String("rrg");
    return hoso_family ? QStringLiteral("hoso") : QStringLiteral("chuoi");
}

/// Đối số CLI của view: mã (view theo mã; rỗng → kMaMacDinh) hoặc rổ. mauhinh nhận cả hai: mh_theo_ma = true
/// (người dùng vừa chọn một mã) → trang mã; ngược lại → trang vũ trụ theo rổ.
QString view_arg(const QString& view, const QString& ma, const QString& scope, bool mh_theo_ma = false) {
    const bool theo_ma = is_ticker_view(view) || (mh_theo_ma && view == QLatin1String("mauhinh"));
    if (!theo_ma)
        return scope;
    return ma.isEmpty() ? QString::fromLatin1(kMaMacDinh) : ma;
}

/// Mã hợp lệ: 1–10 ký tự chữ/số ASCII (dùng làm đối số CLI và request_id).
bool valid_ticker(const QString& s) {
    if (s.isEmpty() || s.size() > 10)
        return false;
    for (const QChar c : s)
        if (c.unicode() >= 128 || !c.isLetterOrNumber())
            return false;
    return true;
}

/// Tự viết HOA khi gõ (không từ chối ký tự nào — kiểm hợp lệ lúc Enter).
class UpperValidator : public QValidator {
  public:
    using QValidator::QValidator;
    State validate(QString& input, int& /*pos*/) const override {
        input = input.toUpper();
        return Acceptable;
    }
};

/// Popup completer đang mở mà chưa chọn dòng: QCompleter nuốt Enter (chỉ ẩn popup) → gọi `on_enter` để Enter vẫn
/// mở mã đã gõ. Có dòng đang chọn thì để QCompleter phát activated như thường.
class PopupEnter : public QObject {
  public:
    PopupEnter(QAbstractItemView* popup, std::function<void()> on_enter, QObject* parent)
        : QObject(parent), popup_(popup), on_enter_(std::move(on_enter)) {}
    bool eventFilter(QObject* obj, QEvent* e) override {
        if (e->type() == QEvent::KeyPress) {
            const int k = static_cast<QKeyEvent*>(e)->key();
            if ((k == Qt::Key_Return || k == Qt::Key_Enter) && !popup_->currentIndex().isValid())
                on_enter_();
        }
        return QObject::eventFilter(obj, e);
    }

  private:
    QAbstractItemView* popup_;
    std::function<void()> on_enter_;
};

/// "vcb · Vietcombank" → "VCB" (token đầu, viết hoa).
QString first_token(const QString& text) {
    QString t = text.trimmed().toUpper();
    const int cut = static_cast<int>(t.indexOf(QRegularExpression(QStringLiteral("[\\s\\x{00B7}]"))));
    if (cut >= 0)
        t.truncate(cut);
    return t;
}

} // namespace langkinh_panel

// ── Dựng ──────────────────────────────────────────────────────────────────────

LangKinhPanel::LangKinhPanel(QWidget* parent)
    : EconPanelBase(langkinh_panel::kSourceId, langkinh_panel::kColor, parent) {
    // Tạo trước build_base_ui(): combo/nút rổ nối vào schedule_fetch() trong build_controls().
    fetch_timer_ = new QTimer(this);
    fetch_timer_->setSingleShot(true);
    fetch_timer_->setInterval(langkinh_panel::kDebounceMs);
    connect(fetch_timer_, &QTimer::timeout, this, &LangKinhPanel::fetch_if_changed);

    build_base_ui(this);
    set_stats_visible(false);
    // Thanh tiêu đề của lớp cơ sở lặp lại tiêu đề trang mà LkBlockView đã vẽ → ẩn (DELTA B7b).
    // Tìm theo objectName để không phải sửa EconPanelBase.
    if (auto* title_bar = findChild<QWidget*>(QStringLiteral("econTitleBar")))
        title_bar->hide();

    block_view_ = new langkinh::LkBlockView(this);
    page_idx_ = add_content_page(block_view_);
    // Hàng đợi: tín hiệu có thể phát từ giữa xử lý chuột của widget sắp bị thay.
    connect(block_view_, &langkinh::LkBlockView::ticker_activated, this, &LangKinhPanel::on_ticker_activated,
            Qt::QueuedConnection);

    connect(&services::EconomicsService::instance(), &services::EconomicsService::result_ready, this,
            &LangKinhPanel::on_result);

    show_empty(tr("Trang Lăng Kính FFT tự nạp khi mở tab — hoặc bấm FETCH để dựng lại từ tệp bridge."));
}

void LangKinhPanel::build_controls(QHBoxLayout* thl) {
    btn_vn30_ = new QPushButton(QStringLiteral("VN30"));
    btn_vn100_ = new QPushButton(QStringLiteral("VN100"));
    btn_vn200_ = new QPushButton(QStringLiteral("VN200"));
    for (QPushButton* b : {btn_vn30_, btn_vn100_, btn_vn200_}) {
        b->setCheckable(true);
        b->setFixedHeight(26);
        b->setCursor(Qt::PointingHandCursor);
        const QString code = b->text();
        b->setAccessibleName(tr("Rổ %1").arg(code));
        b->setToolTip(tr("Xem theo rổ %1").arg(code));
        connect(b, &QPushButton::clicked, this, [this, code]() { set_scope(code); });
        thl->addWidget(b);
    }
    thl->addSpacing(8);

    view_lbl_ = new QLabel(tr("CHẾ ĐỘ XEM"));
    view_lbl_->setObjectName(QStringLiteral("econCtrlLabel"));
    view_combo_ = new QComboBox;
    view_combo_->setFixedHeight(26);
    view_combo_->setMinimumWidth(230);
    view_combo_->setAccessibleName(tr("Chế độ xem Lăng Kính FFT"));
    for (const auto& v : langkinh_panel::kViews)
        view_combo_->addItem(tr(v.label), QString::fromLatin1(v.key));
    connect(view_combo_, &QComboBox::currentIndexChanged, this, &LangKinhPanel::on_view_changed);
    thl->addWidget(view_lbl_);
    thl->addWidget(view_combo_);
    thl->addSpacing(8);

    ma_lbl_ = new QLabel(tr("MÃ"));
    ma_lbl_->setObjectName(QStringLiteral("econCtrlLabel"));
    ma_edit_ = new QLineEdit;
    ma_edit_->setFixedHeight(26);
    ma_edit_->setFixedWidth(110);
    ma_edit_->setPlaceholderText(tr("Gõ mã… vd V"));
    ma_edit_->setAccessibleName(tr("Mã cổ phiếu"));
    ma_edit_->setValidator(new langkinh_panel::UpperValidator(ma_edit_));
    ma_model_ = new QStandardItemModel(this);
    ma_completer_ = new QCompleter(ma_model_, this);
    ma_completer_->setCompletionRole(langkinh_panel::kMaRole);
    ma_completer_->setCaseSensitivity(Qt::CaseInsensitive);
    ma_completer_->setFilterMode(Qt::MatchStartsWith);
    ma_completer_->setCompletionMode(QCompleter::PopupCompletion);
    ma_completer_->setMaxVisibleItems(langkinh_panel::kPopupRows);
    ma_completer_->popup()->setMinimumWidth(langkinh_panel::kPopupMinW);
    ma_edit_->setCompleter(ma_completer_);
    connect(ma_edit_, &QLineEdit::textEdited, this, [this](const QString&) {
        if (ma_invalid_) {
            ma_invalid_ = false;
            update_ma_style();
        }
    });
    connect(ma_edit_, &QLineEdit::returnPressed, this, [this]() { on_ma_entered(ma_edit_->text()); });
    // Lọc cài SAU QCompleter nên chạy TRƯỚC bộ lọc của nó trên popup.
    ma_completer_->popup()->installEventFilter(new langkinh_panel::PopupEnter(
        ma_completer_->popup(), [this]() { on_ma_entered(ma_edit_->text()); }, ma_completer_));
    connect(ma_completer_, QOverload<const QString&>::of(&QCompleter::activated), this,
            &LangKinhPanel::on_ma_entered);
    thl->addWidget(ma_lbl_);
    thl->addWidget(ma_edit_);
    thl->addSpacing(12);

    status_lbl_ = new QLabel;
    status_lbl_->setAccessibleName(tr("Mốc dữ liệu"));
    thl->addWidget(status_lbl_);

    update_scope_btn_styles();
    update_ma_text();
    update_ma_style();
    update_status_style();
}

// ── Nạp dữ liệu ───────────────────────────────────────────────────────────────

void LangKinhPanel::activate() {
    if (has_data_ || !pending_req_.isEmpty())
        return;
    fetch();
}

void LangKinhPanel::on_fetch() {
    // EconPanelBase nối returnPressed của MỌI QLineEdit trên thanh công cụ vào on_fetch. Enter ở ô MÃ đã được
    // on_ma_entered xử lý (mở mã / viền đỏ) → không dựng lại view hiện tại lần nữa (nạp đôi, hoặc nạp lại trang
    // khi mã không hợp lệ).
    if (sender() == ma_edit_)
        return;
    fetch(); // người dùng bấm FETCH → dựng lại từ tệp bridge
}

QString LangKinhPanel::current_view() const {
    if (!view_combo_)
        return QString::fromLatin1(langkinh_panel::kViews[0].key);
    const QString v = view_combo_->currentData().toString();
    return v.isEmpty() ? QString::fromLatin1(langkinh_panel::kViews[0].key) : v;
}

void LangKinhPanel::schedule_fetch() {
    fetch_timer_->start(); // khởi động lại: chỉ lần đổi cuối (sau kDebounceMs yên) mới nạp
}

void LangKinhPanel::fetch_if_changed() {
    // Khoá (view, rổ|mã) trùng yêu cầu đang chờ (đổi qua rồi quay lại) → không chạy thêm script.
    const QString view = current_view();
    const QString key = QStringLiteral("lk_%1_%2").arg(view, langkinh_panel::view_arg(view, ma_, scope_, mh_theo_ma_));
    if (!pending_req_.isEmpty() && pending_req_.section(QLatin1Char('#'), 0, 0) == key)
        return;
    fetch();
}

void LangKinhPanel::fetch() {
    if (!view_combo_)
        return;
    fetch_timer_->stop(); // nạp ngay (FETCH, bấm mã, activate/restore) thay luôn lần nạp đang hẹn
    const QString view = current_view();
    const QString arg = langkinh_panel::view_arg(view, ma_, scope_, mh_theo_ma_);
    // "#<seq>": hai lần nạp cùng view+đối số vẫn khác id → lần cũ về muộn (lỗi/dữ liệu cũ) bị bỏ.
    // seq quay vòng trong kSeqVong giá trị: EconomicsService giữ một dispatch record + một topic DataHub
    // cho mỗi request_id, id không lặp lại thì hai bảng đó phình theo mỗi lần nạp.
    constexpr quint64 kSeqVong = 8;
    const QString req = QStringLiteral("lk_%1_%2#%3").arg(view, arg, QString::number(++req_seq_ % kSeqVong));
    // Đặt TRƯỚC execute(): nếu kết quả phát ngay bên trong execute() thì vẫn khớp yêu cầu đang chờ.
    pending_req_ = req;
    show_loading(tr("Đang dựng trang «%1» · %2…").arg(view_combo_->currentText(), arg));
    LOG_INFO("LangKinhPanel", QStringLiteral("Nạp %1 %2").arg(view, arg));
    // Luôn force=true (DELTA I1): script chỉ đọc tệp bridge (~0,2 s); cache 10' của EconomicsService
    // làm "tuoi" và số liệu đông cứng khi đổi view/rổ/mã.
    services::EconomicsService::instance().execute(QString::fromLatin1(langkinh_panel::kSourceId),
                                                   QString::fromLatin1(langkinh_panel::kScript), view, {arg}, req,
                                                   /*force=*/true);
}

void LangKinhPanel::on_result(const QString& request_id, const services::EconomicsResult& result) {
    if (result.source_id != QLatin1String(langkinh_panel::kSourceId))
        return;
    if (pending_req_.isEmpty() || request_id != pending_req_)
        return; // kết quả của yêu cầu cũ về muộn
    pending_req_.clear();

    if (!result.success) {
        show_error(result.error.isEmpty() ? tr("fincept_langkinh.py không trả kết quả.") : result.error);
        return;
    }
    const QJsonObject& d = result.data;
    const QJsonValue ok = d.value(QStringLiteral("success"));
    if (ok.isBool() && !ok.toBool()) {
        const QString err = d.value(QStringLiteral("error")).toString().trimmed();
        show_error(err.isEmpty() ? tr("fincept_langkinh.py báo thất bại nhưng không kèm thông điệp.") : err);
        return;
    }
    if (!d.value(QStringLiteral("blocks")).isArray() && !d.value(QStringLiteral("cong")).isObject()) {
        show_error(tr("Kết quả không đúng hợp đồng (thiếu blocks và cong) — kiểm tra bản fincept_langkinh.py."));
        return;
    }

    has_data_ = true;
    fill_ds_ma(d.value(QStringLiteral("ds_ma")).toArray(), d.value(QStringLiteral("tickers")).toArray());

    const QString as_of = d.value(QStringLiteral("as_of")).toString().trimmed();
    const QString tuoi = d.value(QStringLiteral("tuoi")).toString().trimmed();
    stale_ = tuoi.contains(QStringLiteral("CŨ"));
    QStringList st;
    if (!as_of.isEmpty())
        st << as_of;
    if (!tuoi.isEmpty())
        st << tuoi;
    if (status_lbl_)
        status_lbl_->setText(st.join(QStringLiteral(" · ")));
    update_status_style();

    // Bảng phẳng cho CSV (không hiển thị — trang block nằm trên cùng).
    display(d.value(QStringLiteral("data")).toArray(), d.value(QStringLiteral("title")).toString());
    block_view_->set_payload(d);
    show_content_page(page_idx_);
}

// ── Điều khiển ────────────────────────────────────────────────────────────────

void LangKinhPanel::set_scope(const QString& scope) {
    if (scope != QLatin1String("VN30") && scope != QLatin1String("VN100") && scope != QLatin1String("VN200"))
        return;
    const bool changed = scope_ != scope;
    // mauhinh đang ở trang mã: bấm rổ (kể cả rổ đang chọn) → về trang vũ trụ của rổ.
    const bool ve_ro = mh_theo_ma_ && current_view() == QLatin1String("mauhinh");
    mh_theo_ma_ = false;
    scope_ = scope;
    update_scope_btn_styles();
    if (ve_ro)
        update_ma_text();
    if (!changed && !ve_ro)
        return;
    emit state_changed();
    if (!langkinh_panel::is_ticker_view(current_view()))
        schedule_fetch();
}

void LangKinhPanel::select_view(const QString& view) {
    if (!view_combo_)
        return;
    const int idx = view_combo_->findData(view);
    if (idx < 0)
        return;
    const QSignalBlocker block(view_combo_);
    view_combo_->setCurrentIndex(idx);
}

void LangKinhPanel::fill_ds_ma(const QJsonArray& ds_ma, const QJsonArray& tickers) {
    if (!ma_model_)
        return;
    QVector<std::pair<QString, QString>> items; // (mã, tên)
    QSet<QString> codes;
    for (const auto& v : ds_ma) {
        const QJsonObject o = v.toObject();
        const QString m = o.value(QStringLiteral("ma")).toString().trimmed().toUpper();
        if (langkinh_panel::valid_ticker(m) && !codes.contains(m)) {
            codes.insert(m);
            items.append({m, o.value(QStringLiteral("ten")).toString().simplified()});
        }
    }
    ds_ma_ = codes; // rỗng (bản script cũ chưa có ds_ma) → không chặn mã ở ô gõ, script tự kiểm
    if (items.isEmpty()) {
        for (const auto& v : tickers) {
            const QString m = v.toString().trimmed().toUpper();
            if (langkinh_panel::valid_ticker(m) && !codes.contains(m)) {
                codes.insert(m);
                items.append({m, QString()});
            }
        }
    }
    if (items.isEmpty())
        return;
    std::sort(items.begin(), items.end());
    bool same = ma_model_->rowCount() == items.size();
    for (int r = 0; same && r < items.size(); ++r)
        same = ma_model_->item(r)->data(langkinh_panel::kMaRole).toString() == items[r].first;
    if (same)
        return; // không đổi → giữ model (popup có thể đang mở)
    ma_model_->clear();
    for (const auto& [m, ten] : std::as_const(items)) {
        const QString t = ten.size() > langkinh_panel::kTenMax ? ten.left(langkinh_panel::kTenMax - 1) + QChar(0x2026)
                                                               : ten;
        auto* it = new QStandardItem(t.isEmpty() ? m : m + QStringLiteral(" · ") + t);
        it->setData(m, langkinh_panel::kMaRole);
        it->setEditable(false);
        ma_model_->appendRow(it);
    }
}

void LangKinhPanel::on_view_changed(int /*index*/) {
    mh_theo_ma_ = false; // chọn mauhinh từ combo → trang vũ trụ theo rổ
    update_ma_text();
    emit state_changed();
    schedule_fetch();
}

void LangKinhPanel::on_ma_entered(const QString& text) {
    const QString t = langkinh_panel::first_token(text);
    if (t.isEmpty())
        return;
    const bool known = ds_ma_.isEmpty() ? langkinh_panel::valid_ticker(t) : ds_ma_.contains(t);
    ma_invalid_ = !known;
    update_ma_style();
    if (!known)
        return; // mã ngoài VN100: viền đỏ + tooltip, không nạp
    // Chọn dòng popup bằng Enter phát cả activated lẫn returnPressed → lần thứ hai gặp đúng yêu cầu đang chờ.
    const QString key = QStringLiteral("lk_%1_%2").arg(langkinh_panel::ticker_target_view(current_view()), t);
    if (!pending_req_.isEmpty() && pending_req_.section(QLatin1Char('#'), 0, 0) == key)
        return;
    on_ticker_activated(t);
}

void LangKinhPanel::on_ticker_activated(const QString& ma) {
    const QString t = ma.trimmed().toUpper();
    if (!langkinh_panel::valid_ticker(t))
        return;
    ma_ = t;
    // Họ hồ sơ (hoso · matran5 · sigma · rrg) → hồ sơ mã; mauhinh → trang mẫu hình của mã; view khác → chuỗi FFT × Giá.
    const QString dich = langkinh_panel::ticker_target_view(current_view());
    mh_theo_ma_ = dich == QLatin1String("mauhinh");
    select_view(dich);
    update_ma_text();
    emit state_changed();
    fetch(); // nạp ngay, không debounce
}

// ── Trạng thái lưu ────────────────────────────────────────────────────────────

QVariantMap LangKinhPanel::save_panel_state() const {
    return {{QStringLiteral("scope"), scope_},
            {QStringLiteral("view"), current_view()},
            {QStringLiteral("ma"), ma_},
            {QStringLiteral("mh_ma"), mh_theo_ma_}};
}

void LangKinhPanel::restore_panel_state(const QVariantMap& state) {
    // Khoá yêu cầu hiệu lực (view + rổ|mã): chỉ nạp lại khi khoá này đổi.
    const auto request_key = [this]() {
        const QString v = current_view();
        return v + QLatin1Char('_') + langkinh_panel::view_arg(v, ma_, scope_, mh_theo_ma_);
    };
    const QString before = request_key();
    const QString sc = state.value(QStringLiteral("scope")).toString();
    if (sc == QLatin1String("VN30") || sc == QLatin1String("VN100") || sc == QLatin1String("VN200"))
        scope_ = sc;
    const QString m = state.value(QStringLiteral("ma")).toString().trimmed().toUpper();
    if (langkinh_panel::valid_ticker(m))
        ma_ = m;
    const QString v = state.value(QStringLiteral("view")).toString();
    if (!v.isEmpty())
        select_view(v);
    mh_theo_ma_ = state.value(QStringLiteral("mh_ma")).toBool(); // thiếu (trạng thái cũ) → false: trang vũ trụ
    update_scope_btn_styles();
    update_ma_text();
    // Đã có trang (hoặc đang nạp) mà trạng thái thực sự đổi thì dựng lại; nếu chưa có thì
    // activate() sẽ nạp đúng view này.
    if ((has_data_ || !pending_req_.isEmpty()) && request_key() != before)
        fetch();
}

// ── Giao diện ─────────────────────────────────────────────────────────────────

void LangKinhPanel::update_scope_btn_styles() {
    using namespace ui::colors;
    const QString on = QStringLiteral("QPushButton { background:%1; color:%2; border:1px solid %1;"
                                      " font-size:10px; font-weight:700; padding:2px 10px; }")
                           .arg(color_, QString(TEXT_ON_ACCENT()));
    const QString off = QStringLiteral("QPushButton { background:%1; color:%2; border:1px solid %3;"
                                       " font-size:10px; font-weight:700; padding:2px 10px; }"
                                       "QPushButton:hover { color:%4; border-color:%5; }")
                            .arg(BG_RAISED(), TEXT_SECONDARY(), BORDER_MED(), TEXT_PRIMARY(), BORDER_BRIGHT());
    const struct {
        QPushButton* btn;
        const char* code;
    } items[] = {{btn_vn30_, "VN30"}, {btn_vn100_, "VN100"}, {btn_vn200_, "VN200"}};
    for (const auto& it : items) {
        if (!it.btn)
            continue;
        const bool active = scope_ == QLatin1String(it.code);
        it.btn->setChecked(active);
        it.btn->setStyleSheet(active ? on : off);
    }
}

void LangKinhPanel::update_ma_text() {
    // Ô mã hiện ở mọi view; ở view theo mã (chuoi, hoso) hiển thị mã đang xem, view khác để trống (gõ thẳng mã mới).
    if (!ma_edit_)
        return;
    const QSignalBlocker block(ma_edit_);
    const bool theo_ma = langkinh_panel::is_ticker_view(current_view()) ||
                         (mh_theo_ma_ && current_view() == QLatin1String("mauhinh"));
    ma_edit_->setText(theo_ma ? ma_ : QString());
    if (ma_invalid_) {
        ma_invalid_ = false;
        update_ma_style();
    }
}

void LangKinhPanel::update_ma_style() {
    if (!ma_edit_)
        return;
    using namespace ui::colors;
    const QString edge = ma_invalid_ ? QString(NEGATIVE()) : QString(BORDER_MED());
    ma_edit_->setStyleSheet(QStringLiteral("QLineEdit { background:%1; color:%2; border:1px solid %3; font-size:11px;"
                                           " font-weight:700; padding:0 6px; }"
                                           "QLineEdit:focus { border-color:%4; }")
                                .arg(QString(BG_RAISED()), QString(TEXT_PRIMARY()), edge,
                                     ma_invalid_ ? QString(NEGATIVE()) : color_));
    ma_edit_->setToolTip(ma_invalid_ ? tr("Mã không thuộc vũ trụ theo dõi")
                                     : tr("Gõ mã VN100 / VN200 (vd V → các mã bắt đầu bằng V) rồi Enter để mở FFT × Giá"
                                          " (ở các view hồ sơ: mở hồ sơ mã)"));
    if (ma_completer_ && ma_completer_->popup())
        ma_completer_->popup()->setStyleSheet(
            QStringLiteral("QAbstractItemView { background:%1; color:%2; border:1px solid %3; font-size:11px;"
                           " outline:0; }"
                           "QAbstractItemView::item { padding:3px 6px; }"
                           "QAbstractItemView::item:selected { background:%4; color:%5; }")
                .arg(QString(BG_RAISED()), QString(TEXT_PRIMARY()), QString(BORDER_MED()), color_,
                     QString(TEXT_ON_ACCENT())));
}

void LangKinhPanel::update_status_style() {
    if (!status_lbl_)
        return;
    using namespace ui::colors;
    status_lbl_->setStyleSheet(QStringLiteral("QLabel { color:%1; font-size:9px; font-weight:%2; background:transparent; }")
                                   .arg(stale_ ? QString(WARNING()) : QString(TEXT_TERTIARY()),
                                        stale_ ? QStringLiteral("700") : QStringLiteral("400")));
}

void LangKinhPanel::refresh_panel_theme() {
    EconPanelBase::refresh_panel_theme();
    update_scope_btn_styles();
    update_ma_style();
    update_status_style();
}

void LangKinhPanel::retranslateUi() {
    if (view_lbl_)
        view_lbl_->setText(tr("CHẾ ĐỘ XEM"));
    if (ma_lbl_)
        ma_lbl_->setText(tr("MÃ"));
    if (ma_edit_)
        ma_edit_->setPlaceholderText(tr("Gõ mã… vd V"));
    update_ma_style();
    if (view_combo_) {
        for (int i = 0; i < view_combo_->count(); ++i) {
            const QString key = view_combo_->itemData(i).toString();
            for (const auto& v : langkinh_panel::kViews)
                if (key == QLatin1String(v.key))
                    view_combo_->setItemText(i, tr(v.label));
        }
    }
    EconPanelBase::retranslateUi();
}

} // namespace fincept::screens
