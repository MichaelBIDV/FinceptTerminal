// src/screens/beri/BeriSectionsCharter.cpp
// Charter half of the BERI page: VII hiến chương · VIII tầng E · IX bộ máy 12 ghế · X quy trình &
// kết luận · XI dòng giá trị · footer. These slices are parsed by scripts/beri.py from the core files
// (Charter, 18 ghế, Kho dữ liệu – đối tác – doanh thu) at every fetch, so an edit to those files shows
// here without a rebuild. Missing slices render "[CẦN DATA] …"; data strings are escaped.
#include "screens/beri/BeriCommon.h"
#include "screens/beri/BeriSections.h"

#include <QFrame>
#include <QGridLayout>
#include <QHBoxLayout>
#include <QJsonArray>
#include <QJsonObject>
#include <QLabel>
#include <QStringList>
#include <QVBoxLayout>

#include <algorithm>
#include <utility>

namespace fincept::screens::beri {

namespace {

// Private helpers carry the "ch_" prefix: the unity build may merge this TU with BeriSectionsLive.cpp.

QString ch_small(const QString& html, const QColor& c, int px = 11, bool bold = false) {
    return QStringLiteral("<span style='color:%1; font-size:%2px;%3'>%4</span>")
        .arg(css(c), QString::number(px), bold ? QStringLiteral(" font-weight:600;") : QString(), html);
}

/// "label: value" line, both escaped here; empty value → nothing.
QString ch_field(const QString& label, const QString& value) {
    if (value.trimmed().isEmpty())
        return {};
    return span(esc(label + QStringLiteral(": ")), col(Role::Muted), true) + esc(value);
}

QString ch_bullets(const QJsonArray& items, const QColor& c) {
    QStringList out;
    for (const QJsonValue& v : items) {
        const QString s = v.toString().trimmed();
        if (!s.isEmpty())
            out << ch_small(QStringLiteral("• ") + esc(s), c, 11);
    }
    return out.join(QStringLiteral("<br>"));
}

/// Cards laid out `cols` per row; each cell stretches equally.
QWidget* ch_grid(QWidget* parent, const QList<QWidget*>& cards, int cols) {
    auto* box = make_box(parent);
    auto* grid = new QGridLayout(box);
    grid->setContentsMargins(0, 0, 0, 0);
    grid->setHorizontalSpacing(10);
    grid->setVerticalSpacing(10);
    for (int i = 0; i < cards.size(); ++i) {
        cards.at(i)->setParent(box);
        grid->addWidget(cards.at(i), i / cols, i % cols);
    }
    for (int c = 0; c < cols; ++c)
        grid->setColumnStretch(c, 1);
    return box;
}

/// Power keyword → colour: CHẶN blocks (crit), CỜ ĐỎ flags (gold), anything else muted.
QColor ch_power_color(const QString& quyen) {
    const QString u = quyen.toUpper();
    if (u.startsWith(QStringLiteral("CHẶN")))
        return crit();
    if (u.startsWith(QStringLiteral("CỜ ĐỎ")))
        return gold();
    return col(Role::Muted);
}

} // namespace

// ── VII · Hiến chương ────────────────────────────────────────────────────────

QWidget* build_charter(const QJsonObject& hc, QWidget* parent) {
    QVBoxLayout* body = nullptr;
    QWidget* sec = make_section(parent, QStringLiteral("VII"), QStringLiteral("Hiến chương dữ liệu"),
                                str(hc, "nguon"), body);
    if (hc.isEmpty()) {
        body->addWidget(need(sec, QStringLiteral("không đọc được Hiến chương")));
        return sec;
    }
    QList<QStringList> rows;
    for (const QJsonValue& v : hc.value("bac").toArray()) {
        const QJsonObject r = v.toObject();
        const QString tag = str(r, "tag");
        rows << QStringList{pill(tag, tier_color(tag), 11), esc(str(r, "nghia")),
                            ch_small(esc(str(r, "vi_du")), col(Role::Muted), 11)};
    }
    body->addWidget(make_table(sec, {QStringLiteral("Bậc"), QStringLiteral("Nghĩa"), QStringLiteral("Ví dụ")}, rows,
                               {2, 6, 6}, QStringLiteral("chưa đọc được bảng bậc bằng chứng")));
    const QString t4 = str(hc, "quy_tac_t4");
    if (!t4.isEmpty())
        body->addWidget(rich(sec, col(Role::Ink2), 12, span(esc(QStringLiteral("Quy tắc T4: ")), gold(), true) + esc(t4)));

    const QJsonArray no = hc.value("khong").toArray();
    if (!no.isEmpty()) {
        QVBoxLayout* lay = nullptr;
        QFrame* card = make_card(sec, lay, crit());
        lay->addWidget(plain(card, crit(), 11, QStringLiteral("SÁU ĐIỀU KHÔNG"), true));
        QStringList items;
        int i = 0;
        for (const QJsonValue& v : no)
            items << span(esc(QStringLiteral("%1. ").arg(++i)), crit(), true) + esc(v.toString());
        lay->addWidget(rich(card, col(Role::Ink2), 12, items.join(QStringLiteral("<br>"))));
        body->addWidget(card);
    }
    return sec;
}

// ── VIII · Tầng E ────────────────────────────────────────────────────────────

QWidget* build_experts(const QJsonObject& tang_e, QWidget* parent) {
    QVBoxLayout* body = nullptr;
    QWidget* sec = make_section(parent, QStringLiteral("VIII"), QStringLiteral("Tầng E — mười tám ghế chuyên gia"),
                                str(tang_e, "nguyen_tac"), body);
    const QJsonArray khoi = tang_e.value("khoi").toArray();
    if (khoi.isEmpty()) {
        body->addWidget(need(sec, QStringLiteral("không đọc được BERI_HoiDongChuyenGia_18Ghe.md")));
        return sec;
    }
    for (const QJsonValue& kv : khoi) {
        const QJsonObject k = kv.toObject();
        body->addWidget(plain(sec, teal(), 12, str(k, "ten"), true));
        QList<QWidget*> cards;
        for (const QJsonValue& gv : k.value("ghe").toArray()) {
            const QJsonObject g = gv.toObject();
            const QString role = str(g, "vai_tro");
            QVBoxLayout* lay = nullptr;
            QFrame* card = make_card(sec, lay, role.isEmpty() ? QColor() : gold());
            QString head = mono(esc(str(g, "id")), 12, teal(), 700) + QStringLiteral("&nbsp;&nbsp;") +
                           span(esc(str(g, "ten")), col(Role::Ink), true);
            if (!role.isEmpty())
                head += QStringLiteral("&nbsp;&nbsp;") + pill(role, gold(), 10);
            lay->addWidget(rich(card, col(Role::Ink), 13, head));
            QStringList lines;
            for (const auto& [label, key] : {std::pair{QStringLiteral("Nguyên mẫu"), "nguyen_mau"},
                                              std::pair{QStringLiteral("Mandate"), "mandate"},
                                              std::pair{QStringLiteral("Sản phẩm"), "san_pham"}}) {
                const QString f = ch_field(label, str(g, key));
                if (!f.isEmpty())
                    lines << f;
            }
            if (!lines.isEmpty())
                lay->addWidget(rich(card, col(Role::Ink2), 12, lines.join(QStringLiteral("<br>"))));
            const QString qs = ch_bullets(g.value("cau_hoi").toArray(), col(Role::Ink2));
            if (!qs.isEmpty())
                lay->addWidget(rich(card, col(Role::Ink2), 11,
                                    span(esc(QStringLiteral("Câu hỏi lõi")), col(Role::Muted), true) +
                                        QStringLiteral("<br>") + qs));
            lay->addStretch(1);
            cards << card;
        }
        body->addWidget(ch_grid(sec, cards, 2));
    }
    return sec;
}

// ── IX · Bộ máy 12 ghế ───────────────────────────────────────────────────────

QWidget* build_operating_seats(const QJsonObject& bo_may, QWidget* parent) {
    QVBoxLayout* body = nullptr;
    QWidget* sec = make_section(parent, QStringLiteral("IX"), QStringLiteral("Bộ máy vận hành — mười hai ghế"),
                                str(bo_may, "nguon"), body);
    const QJsonArray tang = bo_may.value("tang").toArray();
    if (tang.isEmpty()) {
        body->addWidget(need(sec, QStringLiteral("không đọc được Hiến chương §2")));
        return sec;
    }
    for (const QJsonValue& tv : tang) {
        const QJsonObject t = tv.toObject();
        QString head = span(esc(str(t, "ten")), teal(), true);
        const QString role = str(t, "vai_tro");
        if (!role.isEmpty())
            head += QStringLiteral("&nbsp;&nbsp;") + ch_small(esc(role), col(Role::Muted));
        body->addWidget(rich(sec, teal(), 12, head));
        QList<QWidget*> cards;
        for (const QJsonValue& gv : t.value("ghe").toArray()) {
            const QJsonObject g = gv.toObject();
            const QString quyen = str(g, "quyen");
            QVBoxLayout* lay = nullptr;
            QFrame* card = make_card(sec, lay, quyen.isEmpty() ? QColor() : ch_power_color(quyen));
            QString h = mono(esc(str(g, "id")), 12, teal(), 700) + QStringLiteral("&nbsp;&nbsp;") +
                        span(esc(str(g, "ten")), col(Role::Ink), true);
            const QString vr = str(g, "vai_tro");
            if (!vr.isEmpty())
                h += QStringLiteral("<br>") + ch_small(esc(vr), col(Role::Muted));
            lay->addWidget(rich(card, col(Role::Ink), 13, h));
            const QString mo_ta = str(g, "mo_ta");
            if (!mo_ta.isEmpty())
                lay->addWidget(plain(card, col(Role::Ink2), 12, mo_ta));
            if (!quyen.isEmpty())
                lay->addWidget(rich(card, col(Role::Ink2), 12,
                                    span(esc(QStringLiteral("Quyền: ")), ch_power_color(quyen), true) + esc(quyen)));
            const QString qs = ch_bullets(g.value("cau_hoi").toArray(), col(Role::Ink2));
            if (!qs.isEmpty())
                lay->addWidget(rich(card, col(Role::Ink2), 11, qs));
            lay->addStretch(1);
            cards << card;
        }
        body->addWidget(ch_grid(sec, cards, cards.size() >= 4 ? 4 : 3));
    }
    return sec;
}

// ── X · Quy trình & kết luận ─────────────────────────────────────────────────

QWidget* build_process(const QJsonObject& quy_trinh, const QJsonObject& ket_luan, QWidget* parent) {
    QVBoxLayout* body = nullptr;
    QWidget* sec = make_section(parent, QStringLiteral("X"), QStringLiteral("Quy trình bảy bước và bốn trạng thái kết luận"),
                                str(quy_trinh, "nguon"), body);
    const QJsonArray steps = quy_trinh.value("buoc").toArray();
    if (steps.isEmpty()) {
        body->addWidget(need(sec, QStringLiteral("không đọc được Hiến chương §3")));
    } else {
        QList<QWidget*> cards;
        for (const QJsonValue& sv : steps) {
            const QJsonObject s = sv.toObject();
            // Step 4 (tổ kiểm chứng) is the gate: it speaks before any conclusion is locked.
            const bool gate = num(s, "so") == 4;
            QVBoxLayout* lay = nullptr;
            QFrame* card = make_card(sec, lay, gate ? crit() : teal());
            lay->addWidget(rich(card, col(Role::Ink), 13,
                                mono(esc(QStringLiteral("B%1").arg(num(s, "so"))), 12, gate ? crit() : teal(), 700) +
                                    QStringLiteral("&nbsp;&nbsp;") + span(esc(str(s, "ten")), col(Role::Ink), true) +
                                    (gate ? QStringLiteral("&nbsp;&nbsp;") + pill(QStringLiteral("CỔNG"), crit(), 10)
                                          : QString())));
            lay->addWidget(plain(card, col(Role::Ink2), 11, str(s, "mo_ta")));
            lay->addStretch(1);
            cards << card;
        }
        body->addWidget(ch_grid(sec, cards, 4));
        const QString nt = str(quy_trinh, "nguyen_tac");
        if (!nt.isEmpty())
            body->addWidget(rich(sec, col(Role::Ink2), 12,
                                 span(esc(QStringLiteral("Nguyên tắc thứ tự: ")), crit(), true) + esc(nt)));
    }

    QList<QStringList> rows;
    const QList<QColor> tone{teal(), col(Role::Blue), gold(), crit()};
    int i = 0;
    for (const QJsonValue& v : ket_luan.value("dong").toArray()) {
        const QJsonObject r = v.toObject();
        const QColor c = tone.at(std::min<int>(i++, tone.size() - 1));
        rows << QStringList{pill(str(r, "ma") + QStringLiteral(" — ") + str(r, "ten"), c, 11), esc(str(r, "nghia")),
                            esc(str(r, "xu_ly"))};
    }
    body->addWidget(make_table(sec, {QStringLiteral("Trạng thái"), QStringLiteral("Nghĩa"), QStringLiteral("Xử lý")},
                               rows, {3, 5, 5}, QStringLiteral("không đọc được Hiến chương §4")));
    return sec;
}

// ── XI · Dòng giá trị ────────────────────────────────────────────────────────

QWidget* build_value_lines(const QJsonObject& gia_tri, QWidget* parent) {
    QVBoxLayout* body = nullptr;
    QWidget* sec = make_section(parent, QStringLiteral("XI"), QStringLiteral("Bốn dòng giá trị của Viện"),
                                str(gia_tri, "nguon"), body);
    const QJsonArray lines = gia_tri.value("dong").toArray();
    if (lines.isEmpty()) {
        body->addWidget(need(sec, QStringLiteral("không đọc được BERI_KhoDuLieu_DoiTac_DoanhThu.md §3")));
        return sec;
    }
    QList<QWidget*> cards;
    for (const QJsonValue& v : lines) {
        const QJsonObject r = v.toObject();
        QVBoxLayout* lay = nullptr;
        QFrame* card = make_card(sec, lay, teal());
        QString head = mono(esc(QStringLiteral("0%1").arg(num(r, "so"))), 13, teal(), 700) +
                       QStringLiteral("&nbsp;&nbsp;") + span(esc(str(r, "ten")), col(Role::Ink), true);
        lay->addWidget(rich(card, col(Role::Ink), 14, head));
        const QString tag = str(r, "nhan");
        if (!tag.isEmpty())
            lay->addWidget(rich(card, gold(), 11, pill(tag, gold(), 10)));
        const QString mo_ta = str(r, "mo_ta");
        lay->addWidget(mo_ta.isEmpty() ? need(card, QStringLiteral("chưa có mô tả")) : plain(card, col(Role::Ink2), 12, mo_ta));
        lay->addStretch(1);
        cards << card;
    }
    body->addWidget(ch_grid(sec, cards, 2));
    return sec;
}

// ── Footer ───────────────────────────────────────────────────────────────────

QWidget* build_footer(const QJsonObject& meta, QWidget* parent) {
    QVBoxLayout* body = nullptr;
    QWidget* sec = make_section(parent, QString(), QStringLiteral("Nguồn của trang này"),
                                QStringLiteral("Trang đọc lại các tệp dưới đây mỗi lần làm mới; không có số nào gõ tay trong mã."),
                                body);
    QList<QStringList> rows;
    for (const QJsonValue& v : meta.value("sources").toArray()) {
        const QJsonObject s = v.toObject();
        const bool ok = s.value("ton_tai").toBool();
        const int age = num(s, "tuoi_ngay");
        rows << QStringList{span(esc(str(s, "ten")), col(Role::Ink), true),
                            ch_small(esc(str(s, "duong_dan")), col(Role::Muted), 11),
                            ok ? mono(esc(str(s, "sua_luc")), 11, col(Role::Ink2)) +
                                     (age >= 0 ? ch_small(esc(QStringLiteral(" · %1 ngày").arg(age)), col(Role::Muted)) : QString())
                               : span(esc(QStringLiteral("[CẦN DATA] không thấy tệp")), crit(), true)};
    }
    body->addWidget(make_table(sec, {QStringLiteral("Nguồn"), QStringLiteral("Đường dẫn"), QStringLiteral("Sửa lúc")},
                               rows, {2, 6, 3}, QStringLiteral("meta.sources trống")));
    const QString local = str(meta, "local_only");
    if (!local.isEmpty())
        body->addWidget(plain(sec, gold(), 11, local));
    body->addWidget(plain(sec, col(Role::Muted), 11,
                          QStringLiteral("Hệ BERI — Viện NCKT BIDV. Không dùng chung thang bậc hay dữ liệu với hệ HĐCV "
                                         "chứng khoán (mã / NAV / chu kỳ tiền).")));
    return sec;
}

} // namespace fincept::screens::beri
