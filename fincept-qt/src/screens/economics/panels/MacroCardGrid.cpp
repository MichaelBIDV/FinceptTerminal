// src/screens/economics/panels/MacroCardGrid.cpp — xem MacroCardGrid.h để biết vì sao dựng lại
// bằng widget thay vì nhúng trang HTML.
#include "screens/economics/panels/MacroCardGrid.h"

#include <QEnterEvent>
#include <QGridLayout>
#include <QHBoxLayout>
#include <QLabel>
#include <QMouseEvent>
#include <QResizeEvent>
#include <QVBoxLayout>

namespace fincept::screens {

namespace {

QString country_color(const QString& code) {
    if (code == "VN") return QStringLiteral("#f59e0b");
    if (code == "US") return QStringLiteral("#06b6d4");
    if (code == "CN") return QStringLiteral("#f43f5e");
    if (code == "EU") return QStringLiteral("#10b981");
    return QStringLiteral("#94a3b8");
}

/// Nguồn trả "TĂNG ▲" / "GIẢM ▼" / "KHÔNG ĐỔI" ở cột XU HƯỚNG.
QString trend_color(const QString& xu_huong, const QString& bien_dong) {
    const QString t = xu_huong.toUpper();
    if (t.contains(QStringLiteral("TĂNG")) || bien_dong.startsWith(QLatin1Char('+')))
        return QStringLiteral("#22c55e");
    if (t.contains(QStringLiteral("GIẢM")) || bien_dong.startsWith(QStringLiteral("−")) ||
        bien_dong.startsWith(QLatin1Char('-')))
        return QStringLiteral("#ef4444");
    return QStringLiteral("#94a3b8");
}

/// Nhãn từ leaderboard đi qua HTML nên còn thực thể ("Bán lẻ hàng hoá &amp; dịch vụ").
/// Gỡ ở đây chứ không sửa nguồn: cùng một chuỗi còn được các màn khác dùng nguyên trạng.
QString unescape(const QString& s) {
    QString t = s;
    t.replace(QStringLiteral("&amp;"), QStringLiteral("&"));
    t.replace(QStringLiteral("&lt;"), QStringLiteral("<"));
    t.replace(QStringLiteral("&gt;"), QStringLiteral(">"));
    t.replace(QStringLiteral("&quot;"), QStringLiteral("\""));
    t.replace(QStringLiteral("&#39;"), QStringLiteral("'"));
    t.replace(QStringLiteral("&nbsp;"), QStringLiteral(" "));
    return t;
}

} // namespace

// ───────────────────────────── MacroCard ─────────────────────────────

MacroCard::MacroCard(const QJsonObject& c, const QString& country_code, QWidget* parent)
    : QFrame(parent), cc_(country_code) {
    label_ = unescape(c.value(QStringLiteral("CHỈ TIÊU")).toString());
    table_id_ = c.value(QStringLiteral("MÃ BẢNG")).toString().toInt();

    const QString hint = unescape(c.value(QStringLiteral("GIẢI THÍCH")).toString());
    const QString value = c.value(QStringLiteral("GIÁ TRỊ")).toString();
    const QString unit = unescape(c.value(QStringLiteral("ĐƠN VỊ")).toString());
    const QString period = c.value(QStringLiteral("KỲ BÁO CÁO")).toString();
    const QString delta = c.value(QStringLiteral("BIẾN ĐỘNG")).toString();
    const QString so_voi = c.value(QStringLiteral("SO VỚI")).toString();
    const QString xu = c.value(QStringLiteral("XU HƯỚNG")).toString();

    setCursor(table_id_ > 0 ? Qt::PointingHandCursor : Qt::ArrowCursor);
    setMinimumHeight(146);
    apply_style(false);

    auto* v = new QVBoxLayout(this);
    v->setContentsMargins(14, 12, 14, 12);
    v->setSpacing(4);

    // Hàng đầu: tên chỉ tiêu + huy hiệu nền kinh tế
    auto* top = new QHBoxLayout;
    top->setSpacing(6);
    auto* name = new QLabel(label_, this);
    name->setWordWrap(true);
    name->setStyleSheet(QStringLiteral("color:#e2e8f0; font-size:12px; font-weight:700;"));
    top->addWidget(name, 1);
    auto* badge = new QLabel(country_code, this);
    badge->setAlignment(Qt::AlignCenter);
    badge->setFixedSize(26, 15);
    badge->setStyleSheet(QStringLiteral("color:%1; border:1px solid %1; border-radius:3px;"
                                        "font-size:9px; font-weight:700;")
                             .arg(country_color(country_code)));
    top->addWidget(badge, 0, Qt::AlignTop);
    v->addLayout(top);

    if (!hint.isEmpty() && hint != QStringLiteral("—")) {
        auto* h = new QLabel(hint, this);
        h->setWordWrap(true);
        h->setStyleSheet(QStringLiteral("color:#64748b; font-size:10px;"));
        v->addWidget(h);
    }

    v->addStretch(1);

    // Giá trị lớn + đơn vị
    auto* row = new QHBoxLayout;
    row->setSpacing(5);
    auto* val = new QLabel(value.isEmpty() ? QStringLiteral("—") : value, this);
    val->setStyleSheet(QStringLiteral("color:#f8fafc; font-size:21px; font-weight:800;"
                                      "font-family:'JetBrains Mono','SF Mono',monospace;"));
    row->addWidget(val, 0, Qt::AlignBottom);
    auto* u = new QLabel(unit, this);
    u->setStyleSheet(QStringLiteral("color:#94a3b8; font-size:11px;"));
    row->addWidget(u, 0, Qt::AlignBottom);
    row->addStretch(1);
    v->addLayout(row);

    // Chân thẻ: kỳ công bố ở trái, biến động ở phải — kỳ LUÔN hiện, vì một con số không kèm kỳ
    // là một con số không dùng được.
    auto* bot = new QHBoxLayout;
    bot->setSpacing(6);
    auto* p = new QLabel(period, this);
    p->setStyleSheet(QStringLiteral("color:#64748b; font-size:10px;"
                                    "font-family:'JetBrains Mono','SF Mono',monospace;"));
    bot->addWidget(p, 0);
    bot->addStretch(1);
    if (!delta.isEmpty()) {
        auto* d = new QLabel(delta, this);
        d->setStyleSheet(QStringLiteral("color:%1; font-size:11px; font-weight:700;")
                             .arg(trend_color(xu, delta)));
        bot->addWidget(d, 0);
    }
    if (!so_voi.isEmpty()) {
        auto* sv = new QLabel(so_voi, this);
        sv->setStyleSheet(QStringLiteral("color:#64748b; font-size:9px;"));
        bot->addWidget(sv, 0);
    }
    v->addLayout(bot);

    setToolTip(table_id_ > 0
                   ? tr("%1\n%2 %3 · kỳ %4 · %5 %6\n\nBấm để mở toàn bộ dải lịch sử (mã bảng %7)")
                         .arg(label_, value, unit, period, delta, so_voi)
                         .arg(table_id_)
                   : tr("%1\n%2 %3 · kỳ %4\n\nChỉ tiêu này chưa có mã bảng nên không mở được đồ thị")
                         .arg(label_, value, unit, period));
}

void MacroCard::apply_style(bool hover) {
    setStyleSheet(QStringLiteral("QFrame{background:%1; border:1px solid %2; border-radius:8px;}")
                      .arg(hover ? QStringLiteral("#131c2b") : QStringLiteral("#0d1420"),
                           hover ? country_color(cc_) : QStringLiteral("#1e293b")));
}

void MacroCard::enterEvent(QEnterEvent* e) {
    apply_style(true);
    QFrame::enterEvent(e);
}

void MacroCard::leaveEvent(QEvent* e) {
    apply_style(false);
    QFrame::leaveEvent(e);
}

void MacroCard::mouseReleaseEvent(QMouseEvent* e) {
    if (e->button() == Qt::LeftButton && table_id_ > 0 && rect().contains(e->pos()))
        emit activated(table_id_, label_);
    QFrame::mouseReleaseEvent(e);
}

// ─────────────────────────── MacroCardGrid ───────────────────────────

MacroCardGrid::MacroCardGrid(QWidget* parent) : QScrollArea(parent) {
    setWidgetResizable(true);
    setFrameShape(QFrame::NoFrame);
    setStyleSheet(QStringLiteral("QScrollArea{background:#080c14;border:none;}"));
    canvas_ = new QWidget;
    canvas_->setStyleSheet(QStringLiteral("background:#080c14;"));
    grid_ = new QGridLayout(canvas_);
    grid_->setContentsMargins(14, 12, 14, 18);
    grid_->setHorizontalSpacing(10);
    grid_->setVerticalSpacing(10);
    setWidget(canvas_);
}

void MacroCardGrid::set_country_cards(const QString& code, const QString& name,
                                      const QJsonArray& cards) {
    for (auto& n : nhom_) {
        if (n.code == code) {
            n.name = name;
            n.cards = cards;
            rebuild();
            return;
        }
    }
    nhom_.append({code, name, cards});
    rebuild();
}

void MacroCardGrid::set_filter(const QString& code) {
    filter_ = code;
    rebuild();
}

void MacroCardGrid::set_search(const QString& text) {
    search_ = text.trimmed();
    rebuild();
}

void MacroCardGrid::clear_all() {
    nhom_.clear();
    rebuild();
}

int MacroCardGrid::total_cards() const {
    int n = 0;
    for (const auto& g : nhom_)
        n += g.cards.size();
    return n;
}

int MacroCardGrid::columns_for_width(int w) const {
    if (w >= 1500) return 5;
    if (w >= 1200) return 4;
    if (w >= 880) return 3;
    if (w >= 600) return 2;
    return 1;
}

void MacroCardGrid::resizeEvent(QResizeEvent* e) {
    QScrollArea::resizeEvent(e);
    if (columns_for_width(viewport()->width()) != cols_)
        rebuild();
}

void MacroCardGrid::rebuild() {
    while (QLayoutItem* it = grid_->takeAt(0)) {
        if (it->widget())
            it->widget()->deleteLater();
        delete it;
    }
    cols_ = columns_for_width(viewport()->width() > 0 ? viewport()->width() : width());

    // Thứ tự cố định để mắt không phải đi tìm; nền kinh tế nào chưa về thì vắng mặt, không
    // dựng ô rỗng — ô rỗng nuôi ảo giác là "đã có dữ liệu".
    static const QStringList thu_tu = {QStringLiteral("VN"), QStringLiteral("US"),
                                       QStringLiteral("CN"), QStringLiteral("EU")};
    int row = 0;
    for (const QString& code : thu_tu) {
        if (!filter_.isEmpty() && filter_ != code)
            continue;
        const Nhom* g = nullptr;
        for (const auto& x : nhom_) {
            if (x.code == code) {
                g = &x;
                break;
            }
        }
        if (!g)
            continue;

        QVector<QJsonObject> hien;
        for (const auto& v : g->cards) {
            const QJsonObject o = v.toObject();
            if (!search_.isEmpty() &&
                !unescape(o.value(QStringLiteral("CHỈ TIÊU")).toString())
                     .contains(search_, Qt::CaseInsensitive))
                continue;
            hien.append(o);
        }
        if (hien.isEmpty())
            continue;

        auto* head = new QLabel(QStringLiteral("%1  ·  %2 chỉ tiêu").arg(g->name).arg(hien.size()),
                                canvas_);
        head->setStyleSheet(QStringLiteral("color:%1; font-size:12px; font-weight:800;"
                                           "padding:10px 2px 2px 2px;")
                                .arg(country_color(code)));
        grid_->addWidget(head, row, 0, 1, cols_);
        ++row;

        int col = 0;
        for (const auto& o : hien) {
            auto* card = new MacroCard(o, code, canvas_);
            connect(card, &MacroCard::activated, this, &MacroCardGrid::indicator_activated);
            grid_->addWidget(card, row, col);
            if (++col >= cols_) {
                col = 0;
                ++row;
            }
        }
        if (col != 0)
            ++row;
    }

    for (int c = 0; c < cols_; ++c)
        grid_->setColumnStretch(c, 1);
    grid_->setRowStretch(row, 1);
}

} // namespace fincept::screens
