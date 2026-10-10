// src/screens/beri/BeriSectionsLive.cpp
// Live half of the BERI page: masthead · alert · I lịch · II sổ lệch · III cam kết & mốc neo ·
// IV việc đang mở · V sổ nguồn · VI kho & pipeline. Every value arrives pre-computed from
// scripts/beri.py (countdowns, ledger states, file ages); this file only lays it out. Missing slices
// render a muted "[CẦN DATA] …" line, and every data string is escaped before it reaches a rich-text QLabel.
#include "screens/beri/BeriCommon.h"
#include "screens/beri/BeriSections.h"

#include <QDate>
#include <QDateTime>
#include <QFrame>
#include <QHBoxLayout>
#include <QJsonArray>
#include <QJsonObject>
#include <QLabel>
#include <QList>
#include <QPair>
#include <QStringList>
#include <QVBoxLayout>

namespace fincept::screens::beri {

namespace {

// Private helpers carry the "live_" prefix: the unity build may merge this TU with BeriSectionsCharter.cpp.

QString live_small(const QString& html, const QColor& c, int px = 11, bool bold = false) {
    return QStringLiteral("<span style='color:%1; font-size:%2px;%3'>%4</span>")
        .arg(css(c), QString::number(px), bold ? QStringLiteral(" font-weight:600;") : QString(), html);
}

/// Sub-heading inside a section (group name + optional muted source note).
QLabel* live_subhead(QWidget* parent, const QString& title, const QString& note = {}) {
    QString html = span(esc(title), col(Role::Ink), true);
    if (!note.trimmed().isEmpty())
        html += QStringLiteral("&nbsp;&nbsp;") + live_small(esc(note), col(Role::Muted));
    auto* l = rich(parent, col(Role::Ink), 13, html);
    l->setContentsMargins(0, 6, 0, 0);
    return l;
}

/// Row of pills (already-built html fragments) on one wrapped line.
QLabel* live_pills(QWidget* parent, const QStringList& pills) {
    return rich(parent, col(Role::Ink2), 12, pills.join(QStringLiteral("&nbsp;&nbsp;")));
}

/// Ledger state text → colour: open-priority crit, open gold, explained blue, closed teal.
QColor live_state_color(const QJsonObject& r) {
    const QString tt = str(r, "trang_thai").toUpper();
    if (tt.contains(QStringLiteral("GIẢI THÍCH")))
        return col(Role::Blue);
    if (!r.value("mo").toBool())
        return teal();
    return tt.contains(QStringLiteral("ƯU TIÊN")) ? crit() : gold();
}

/// Problem cell of a ledger row: text + the cross-ledger reference when the engine found one.
QString live_problem_cell(const QJsonObject& r) {
    QString html = esc(str(r, "van_de"));
    const QString link = str(r, "trung_voi");
    if (!link.isEmpty())
        html += QStringLiteral("<br>") + live_small(QStringLiteral("↔ ") + esc(link), teal(), 11, true);
    return html;
}

QList<QStringList> live_ledger_rows(const QJsonArray& rows, bool with_ab) {
    QList<QStringList> out;
    for (const QJsonValue& v : rows) {
        const QJsonObject r = v.toObject();
        QStringList cells{mono(esc(str(r, "so")), 12, col(Role::Muted)), live_problem_cell(r)};
        if (with_ab)
            cells << esc(str(r, "a")) << esc(str(r, "b"));
        cells << esc(str(r, "xu_ly")) << pill(str(r, "trang_thai"), live_state_color(r), 10);
        out << cells;
    }
    return out;
}

QString live_ddmmyyyy(const QString& iso) {
    const QDate d = QDate::fromString(iso.left(10), Qt::ISODate);
    return d.isValid() ? d.toString(QStringLiteral("dd/MM/yyyy")) : iso;
}

} // namespace

// ── Masthead / alert ─────────────────────────────────────────────────────────

QWidget* build_masthead(const QJsonObject& mandate, const QJsonObject& meta, QWidget* parent) {
    auto* box = make_box(parent);
    auto* vl = new QVBoxLayout(box);
    vl->setContentsMargins(0, 0, 0, 0);
    vl->setSpacing(4);

    auto* eyebrow = plain(box, teal(), 11, QStringLiteral("BERI · HỘI ĐỒNG CỐ VẤN AI · VIỆN NGHIÊN CỨU KINH TẾ BIDV"), true);
    vl->addWidget(eyebrow);

    auto* title = new QLabel(box);
    title->setTextFormat(Qt::PlainText);
    title->setWordWrap(true);
    title->setText(QStringLiteral("Bàn điều hành Hội đồng — lịch, sổ lệch, sổ nguồn, bộ máy"));
    title->setStyleSheet(QStringLiteral("QLabel { color:%1; %2 background:transparent; }")
                             .arg(css(col(Role::Ink)), lk::lk_font_css(lk::lk_font_serif(24, 600))));
    vl->addWidget(title);

    const QString ten = str(mandate, "ten");
    QString who = span(esc(ten.isEmpty() ? QStringLiteral("[CẦN DATA]") : ten), col(Role::Ink), true);
    const QString vai = str(mandate, "vai");
    if (!vai.isEmpty())
        who += QStringLiteral(" — ") + esc(vai);
    vl->addWidget(rich(box, col(Role::Ink2), 13, who));

    QStringList facts;
    const QString hl = str(mandate, "hieu_luc");
    if (!hl.isEmpty())
        facts << esc(QStringLiteral("Hiệu lực %1").arg(hl));
    QStringList docs;
    for (const QJsonValue& d : mandate.value("van_ban").toArray())
        docs << d.toString();
    if (!docs.isEmpty())
        facts << esc(QStringLiteral("Văn bản: %1").arg(docs.join(QStringLiteral(" · "))));
    const QString today = live_ddmmyyyy(str(meta, "today"));
    if (!today.isEmpty())
        facts << esc(QStringLiteral("Hôm nay %1").arg(today));
    const QDateTime gen = QDateTime::fromString(str(meta, "generated"), Qt::ISODate);
    if (gen.isValid())
        facts << esc(QStringLiteral("đọc tệp lúc %1").arg(gen.toString(QStringLiteral("HH:mm"))));
    const QString src = str(mandate, "nguon");
    if (!src.isEmpty())
        facts << live_small(esc(src), col(Role::Muted));
    vl->addWidget(rich(box, col(Role::Muted), 12, facts.join(QStringLiteral(" · "))));

    const QString local = str(meta, "local_only");
    if (!local.isEmpty())
        vl->addWidget(rich(box, gold(), 12, span(esc(QStringLiteral("● ") + local), gold(), true)));

    for (const QJsonValue& w : meta.value("warnings").toArray()) {
        const QString s = w.toString().trimmed();
        if (!s.isEmpty())
            vl->addWidget(plain(box, crit(), 12, QStringLiteral("⚠ ") + s));
    }
    return box;
}

QWidget* build_alert(const QJsonObject& alert, QWidget* parent) {
    const QColor c = level_color(str(alert, "muc"));
    QVBoxLayout* lay = nullptr;
    QFrame* card = make_card(parent, lay, c);
    lay->addWidget(plain(card, c, 11, str(alert, "tieu_de").toUpper(), true));
    const QString body = str(alert, "noi_dung");
    lay->addWidget(body.isEmpty() ? need(card, QStringLiteral("chưa tính được mốc gần nhất"))
                                  : plain(card, col(Role::Ink), 14, body, true));
    return card;
}

// ── I · Lịch ─────────────────────────────────────────────────────────────────

QWidget* build_calendar(const QJsonObject& lich, QWidget* parent) {
    QVBoxLayout* body = nullptr;
    QWidget* sec = make_section(parent, QStringLiteral("I"), QStringLiteral("Lịch sản phẩm — đếm ngược tới hôm nay"),
                                str(lich, "nguon"), body);
    if (lich.isEmpty()) {
        body->addWidget(need(sec, QStringLiteral("không đọc được beri-workspace §6 — không có lịch để tính")));
        return sec;
    }
    const QJsonObject dem = lich.value("dem").toObject();
    body->addWidget(live_pills(sec, {pill(QStringLiteral("≤ 7 ngày: %1").arg(num(dem, "crit", 0)), crit()),
                                     pill(QStringLiteral("8–21 ngày: %1").arg(num(dem, "warn", 0)), gold()),
                                     pill(QStringLiteral("xa hơn: %1").arg(num(dem, "ok", 0)), teal()),
                                     pill(QStringLiteral("theo sự kiện: %1").arg(num(dem, "na", 0)), col(Role::Muted))}));
    const QString note = str(lich, "ghi_chu");
    if (!note.isEmpty())
        body->addWidget(plain(sec, col(Role::Muted), 11, note));

    const QStringList headers{QStringLiteral("Sản phẩm"), QStringLiteral("Hạn — nguyên văn"),
                              QStringLiteral("Mốc tiếp"), QStringLiteral("Còn"),
                              QStringLiteral("Kỳ vừa qua"), QStringLiteral("Tệp làm việc gần nhất")};
    const QList<int> stretch{5, 3, 2, 2, 3, 4};
    for (const QJsonValue& gv : lich.value("nhom").toArray()) {
        const QJsonObject g = gv.toObject();
        body->addWidget(live_subhead(sec, str(g, "ten")));
        QList<QStringList> rows;
        for (const QJsonValue& rv : g.value("dong").toArray()) {
            const QJsonObject r = rv.toObject();
            const QColor lc = level_color(str(r, "muc"));
            QString sp = span(esc(str(r, "san_pham")), col(Role::Ink));
            const QString dv = str(r, "don_vi");
            if (!dv.isEmpty() && dv != QLatin1String("—"))
                sp += QStringLiteral("<br>") + live_small(esc(dv), col(Role::Muted));
            for (const QJsonValue& f : r.value("co").toArray())
                sp += QStringLiteral("<br>") + live_small(esc(QStringLiteral("⚠ ") + f.toString()), crit(), 11, true);

            const QString con = str(r, "con_txt");
            const QString con_cell = r.value("con_ngay").isDouble() ? pill(con, lc, 11)
                                                                   : live_small(esc(con), col(Role::Muted));
            QString prev;
            const QJsonObject kv = r.value("ky_vua_qua").toObject();
            if (!kv.isEmpty())
                prev = esc(str(kv, "moc_txt")) + QStringLiteral("<br>") +
                       live_small(esc(QStringLiteral("qua %1 ngày — chưa xác nhận phát hành").arg(num(kv, "qua_ngay", 0))),
                                  col(Role::Muted));
            QString file;
            const QJsonObject td = r.value("tien_do").toObject();
            // File names have no spaces; a zero-width space after each "_" lets the cell wrap instead of clip.
            if (!td.isEmpty())
                file = esc(str(td, "tep")).replace(QLatin1Char('_'), QStringLiteral("_​")) + QStringLiteral("<br>") +
                       live_small(esc(str(td, "giai_doan") + QStringLiteral(" · ") + str(td, "ngay_txt")), teal());
            rows << QStringList{sp, esc(str(r, "han_goc")),
                                mono(esc(str(r, "moc_tiep_txt")), 12, r.value("moc_tiep").isString() ? lc : col(Role::Muted)),
                                con_cell, prev, file};
        }
        body->addWidget(make_table(sec, headers, rows, stretch, QStringLiteral("nhóm này không có dòng nào")));
    }
    return sec;
}

// ── II · Sổ lệch ─────────────────────────────────────────────────────────────

QWidget* build_ledgers(const QJsonObject& so_lech, QWidget* parent) {
    QVBoxLayout* body = nullptr;
    QWidget* sec = make_section(
        parent, QStringLiteral("II"), QStringLiteral("Hai sổ lệch"),
        QStringLiteral("Hai sổ, hai hệ đánh số: sổ lệch SỐ LIỆU (Kho §G) giữ con số được trích dẫn; sổ lệch VẬN HÀNH "
                       "(beri-workspace §7) giữ lịch, tên gọi, quy trình. Mục có ở cả hai sổ được đánh dấu ↔."),
        body);

    const QJsonObject sl = so_lech.value("so_lieu").toObject();
    body->addWidget(live_subhead(sec, QStringLiteral("Sổ lệch số liệu"), str(sl, "nguon")));
    if (sl.isEmpty()) {
        body->addWidget(need(sec, QStringLiteral("không đọc được Kho §G")));
    } else {
        body->addWidget(live_pills(sec, {pill(QStringLiteral("mở: %1").arg(num(sl, "mo", 0)), gold()),
                                         pill(QStringLiteral("đã giải thích: %1").arg(num(sl, "giai_thich", 0)), col(Role::Blue)),
                                         pill(QStringLiteral("đã đóng: %1").arg(num(sl, "dong_lai", 0)), teal())}));
        body->addWidget(make_table(sec,
                                   {QStringLiteral("#"), QStringLiteral("Vấn đề"), QStringLiteral("Nguồn A"),
                                    QStringLiteral("Nguồn B"), QStringLiteral("Xử lý"), QStringLiteral("Trạng thái")},
                                   live_ledger_rows(sl.value("dong").toArray(), true), {1, 5, 3, 3, 4, 2},
                                   QStringLiteral("sổ trống")));
    }

    const QJsonObject vh = so_lech.value("van_hanh").toObject();
    body->addWidget(live_subhead(sec, QStringLiteral("Sổ lệch vận hành"), str(vh, "nguon")));
    if (vh.isEmpty()) {
        body->addWidget(need(sec, QStringLiteral("không đọc được beri-workspace §7")));
        return sec;
    }
    const QJsonArray open = vh.value("dang_mo").toArray();
    const QJsonArray closed = vh.value("da_chot").toArray();
    body->addWidget(live_pills(sec, {pill(QStringLiteral("đang mở: %1").arg(open.size()), gold()),
                                     pill(QStringLiteral("đã chốt: %1").arg(closed.size()), teal())}));
    body->addWidget(make_table(sec,
                               {QStringLiteral("#"), QStringLiteral("Đang mở"), QStringLiteral("Bên A"),
                                QStringLiteral("Bên B"), QStringLiteral("Đề xuất"), QStringLiteral("Trạng thái")},
                               live_ledger_rows(open, true), {1, 4, 3, 3, 4, 2}, QStringLiteral("không có mục mở")));
    body->addWidget(make_table(sec, {QStringLiteral("#"), QStringLiteral("Đã chốt"), QStringLiteral("Kết luận"),
                                     QStringLiteral("Trạng thái")},
                               live_ledger_rows(closed, false), {1, 6, 6, 2}, QStringLiteral("chưa có mục chốt")));
    return sec;
}

// ── III · Cam kết & mốc neo ──────────────────────────────────────────────────

QWidget* build_commitments(const QJsonObject& cam_ket, const QJsonObject& moc_neo, QWidget* parent) {
    QVBoxLayout* body = nullptr;
    QWidget* sec = make_section(parent, QStringLiteral("III"), QStringLiteral("Cam kết mới và mốc neo văn bản"),
                                str(cam_ket, "nguon"), body);
    if (cam_ket.isEmpty()) {
        body->addWidget(need(sec, QStringLiteral("không đọc được beri-workspace §6b")));
    } else {
        const QJsonArray rows = cam_ket.value("dong").toArray();
        body->addWidget(live_pills(
            sec, {pill(QStringLiteral("%1 / %2 cam kết chưa có mốc").arg(num(cam_ket, "chua_moc", 0)).arg(rows.size()),
                       gold())}));
        QList<QStringList> cells;
        for (const QJsonValue& v : rows) {
            const QJsonObject r = v.toObject();
            const QString moc = str(r, "moc");
            const QColor mc = moc.startsWith(QStringLiteral("chưa")) ? gold() : teal();
            cells << QStringList{mono(esc(str(r, "so")), 12, col(Role::Muted)), esc(str(r, "viec")),
                                 span(esc(moc), mc, true), esc(str(r, "trang_thai"))};
        }
        body->addWidget(make_table(sec, {QStringLiteral("#"), QStringLiteral("Việc"), QStringLiteral("Mốc"),
                                         QStringLiteral("Ghi chú")},
                                   cells, {1, 6, 2, 5}, QStringLiteral("không có cam kết")));
    }

    body->addWidget(live_subhead(sec, QStringLiteral("Mốc neo văn bản"), str(moc_neo, "nguon")));
    if (moc_neo.isEmpty()) {
        body->addWidget(need(sec, QStringLiteral("không đọc được beri-workspace §6c")));
        return sec;
    }
    body->addWidget(live_pills(
        sec, {pill(QStringLiteral("%1 QĐ neo sản phẩm còn thiếu ngày").arg(num(moc_neo, "thieu_ngay", 0)), crit())}));
    QList<QStringList> cells;
    for (const QJsonValue& v : moc_neo.value("dong").toArray()) {
        const QJsonObject r = v.toObject();
        QString vb = span(esc(str(r, "van_ban")), col(Role::Ink), true);
        if (r.value("thieu_ngay").toBool())
            vb += QStringLiteral("<br>") + live_small(esc(QStringLiteral("⚠ thiếu ngày ban hành")), crit(), 11, true);
        cells << QStringList{vb, esc(str(r, "noi_dung")), esc(str(r, "san_pham"))};
    }
    body->addWidget(make_table(sec, {QStringLiteral("Văn bản"), QStringLiteral("Nội dung"),
                                     QStringLiteral("Sản phẩm neo")},
                               cells, {3, 4, 3}, QStringLiteral("không có mốc neo")));
    return sec;
}

// ── IV · Việc đang mở ────────────────────────────────────────────────────────

QWidget* build_open_work(const QJsonObject& viec_mo, QWidget* parent) {
    QVBoxLayout* body = nullptr;
    QWidget* sec = make_section(parent, QStringLiteral("IV"), QStringLiteral("Việc đang mở"),
                                QStringLiteral("Nguồn: beri-workspace §8."), body);
    const QJsonArray groups = viec_mo.value("nhom").toArray();
    if (groups.isEmpty()) {
        body->addWidget(need(sec, QStringLiteral("không đọc được beri-workspace §8")));
        return sec;
    }
    for (const QJsonValue& gv : groups) {
        const QJsonObject g = gv.toObject();
        QVBoxLayout* lay = nullptr;
        QFrame* card = make_card(sec, lay, teal());
        lay->addWidget(plain(card, col(Role::Ink), 13, str(g, "ten"), true));
        QStringList items;
        for (const QJsonValue& it : g.value("dong").toArray())
            items << QStringLiteral("• ") + esc(it.toString());
        lay->addWidget(items.isEmpty() ? need(card, QStringLiteral("nhóm trống"))
                                       : rich(card, col(Role::Ink2), 12, items.join(QStringLiteral("<br>"))));
        body->addWidget(card);
    }
    return sec;
}

// ── V · Sổ nguồn ─────────────────────────────────────────────────────────────

QWidget* build_registry(const QJsonObject& so_nguon, QWidget* parent) {
    QVBoxLayout* body = nullptr;
    QString lede = str(so_nguon, "nguon");
    const QString cap = str(so_nguon, "cap_nhat");
    if (!cap.isEmpty()) {
        lede += QStringLiteral(" · cập nhật %1").arg(cap);
        const int age = num(so_nguon, "tuoi_ngay");
        if (age >= 0)
            lede += QStringLiteral(" (%1 ngày trước)").arg(age);
    }
    QWidget* sec = make_section(parent, QStringLiteral("V"), QStringLiteral("Sổ nguồn BERI"), lede, body);
    if (so_nguon.isEmpty()) {
        body->addWidget(need(sec, QStringLiteral("không đọc được songuon_registry.json")));
        return sec;
    }
    const QJsonObject dem = so_nguon.value("dem").toObject();
    const QList<QPair<QString, QString>> order{{QStringLiteral("song"), QStringLiteral("sống")},
                                               {QStringLiteral("thu_cong"), QStringLiteral("thủ công")},
                                               {QStringLiteral("chap_chon"), QStringLiteral("chập chờn")},
                                               {QStringLiteral("chua_co"), QStringLiteral("chưa có")},
                                               {QStringLiteral("chan"), QStringLiteral("bị chặn")}};
    QStringList pills;
    for (const auto& [key, label] : order) {
        const int n = num(dem, key.toUtf8().constData(), 0);
        if (n > 0)
            pills << pill(QStringLiteral("%1: %2").arg(label).arg(n), source_status_color(key));
    }
    body->addWidget(live_pills(sec, pills));

    QList<QStringList> cells;
    for (const QJsonValue& v : so_nguon.value("dong").toArray()) {
        const QJsonObject r = v.toObject();
        const QString tier = str(r, "tier");
        cells << QStringList{span(esc(str(r, "ten")), col(Role::Ink)) + QStringLiteral("<br>") +
                                 live_small(esc(str(r, "id")), col(Role::Muted)),
                             esc(str(r, "nhom")), pill(tier, tier_color(tier), 10),
                             pill(str(r, "trang_thai_txt"), source_status_color(str(r, "trang_thai")), 10),
                             esc(str(r, "tan_suat")), live_small(esc(str(r, "ghi_chu")), col(Role::Ink2), 11)};
    }
    body->addWidget(make_table(sec,
                               {QStringLiteral("Nguồn"), QStringLiteral("Nhóm"), QStringLiteral("Bậc"),
                                QStringLiteral("Trạng thái"), QStringLiteral("Tần suất"), QStringLiteral("Ghi chú")},
                               cells, {4, 2, 2, 2, 2, 5}, QStringLiteral("sổ nguồn không có dòng BERI")));
    return sec;
}

// ── VI · Kho & pipeline ──────────────────────────────────────────────────────

QWidget* build_store(const QJsonObject& kho, const QJsonObject& pipeline, QWidget* parent) {
    QVBoxLayout* body = nullptr;
    QWidget* sec = make_section(parent, QStringLiteral("VI"), QStringLiteral("Tám tệp lõi, Kho số liệu và pipeline"),
                                QStringLiteral("Bản gốc ở beri_sector; bản sao ở ~/Downloads và BERI_Cowork được so md5."),
                                body);
    QList<QStringList> cells;
    for (const QJsonValue& v : kho.value("tep").toArray()) {
        const QJsonObject r = v.toObject();
        QString copies;
        if (!r.value("ton_tai").toBool()) {
            copies = span(esc(QStringLiteral("[CẦN DATA] không thấy tệp gốc")), crit(), true);
        } else if (!r.value("lech").toArray().isEmpty()) {
            QStringList paths;
            for (const QJsonValue& p : r.value("lech").toArray())
                paths << p.toString();
            copies = span(esc(QStringLiteral("LỆCH")), crit(), true) + QStringLiteral("<br>") +
                     live_small(esc(paths.join(QStringLiteral("; "))), crit());
        } else {
            const int n = num(r, "ban_sao", 0);
            copies = n > 0 ? span(esc(QStringLiteral("%1 bản sao · khớp").arg(n)), teal(), true)
                           : live_small(esc(QStringLiteral("không có bản sao")), col(Role::Muted));
        }
        const int age = num(r, "tuoi_ngay");
        QString when = mono(esc(str(r, "sua_luc")), 11, col(Role::Ink2));
        if (age >= 0)
            when += QStringLiteral("<br>") + live_small(esc(QStringLiteral("%1 ngày").arg(age)), col(Role::Muted));
        cells << QStringList{span(esc(str(r, "ten")), col(Role::Ink)), esc(str(r, "vai_tro")), when, copies};
    }
    body->addWidget(make_table(sec, {QStringLiteral("Tệp"), QStringLiteral("Vai trò"), QStringLiteral("Sửa lúc"),
                                     QStringLiteral("Bản sao")},
                               cells, {4, 4, 2, 3}, QStringLiteral("không liệt kê được tệp lõi")));

    const QJsonObject sl = kho.value("so_lieu").toObject();
    {
        const QString warn = str(sl, "canh_bao");
        QVBoxLayout* lay = nullptr;
        QFrame* card = make_card(sec, lay, warn.isEmpty() ? teal() : gold());
        lay->addWidget(plain(card, col(Role::Ink), 13,
                             QStringLiteral("Kho số liệu chuẩn — kỳ %1 · cập nhật %2")
                                 .arg(str(sl, "ky"), str(sl, "cap_nhat_txt")),
                             true));
        if (!warn.isEmpty())
            lay->addWidget(plain(card, gold(), 12, warn));
        body->addWidget(card);
    }

    const QJsonObject q = pipeline.value("quet").toObject();
    const QJsonObject rs = pipeline.value("ra_soat").toObject();
    QVBoxLayout* lay = nullptr;
    QFrame* card = make_card(sec, lay, level_color(q.isEmpty() ? QString() : str(q, "muc")));
    lay->addWidget(plain(card, col(Role::Ink), 13, QStringLiteral("Pipeline tin ngành (beri_sector)"), true));
    if (q.isEmpty()) {
        lay->addWidget(need(card, QStringLiteral("không đọc được sector_feed.json")));
    } else {
        const QString gio = q.value("cach_gio").isDouble() ? QString::number(q.value("cach_gio").toDouble(), 'f', 1)
                                                             : QStringLiteral("?");
        lay->addWidget(rich(card, col(Role::Ink2), 12,
                            span(esc(QStringLiteral("Lượt quét gần nhất %1 (cách %2 giờ)").arg(str(q, "moi_nhat_txt"), gio)),
                                 level_color(str(q, "muc")), true) +
                                esc(QStringLiteral(" · %1 lượt lưu · %2 tin · %3 văn bản chính sách")
                                        .arg(num(q, "so_luot", 0))
                                        .arg(str(q, "n_tin"), str(q, "n_chinh_sach")))));
    }
    if (rs.isEmpty()) {
        lay->addWidget(need(card, QStringLiteral("chưa có tệp rà soát")));
    } else {
        QStringList groups;
        const QJsonObject nhom = rs.value("nhom").toObject();
        for (auto it = nhom.begin(); it != nhom.end(); ++it)
            groups << QStringLiteral("%1 %2").arg(it.key()).arg(it.value().toInt());
        QStringList tasks;
        for (const QJsonValue& t : rs.value("viec").toArray())
            tasks << t.toString();
        QString html = esc(QStringLiteral("Rà soát %1: %2 phát hiện, ").arg(str(rs, "ngay_txt"), str(rs, "tong"))) +
                       span(esc(QStringLiteral("%1 nghiêm trọng").arg(str(rs, "nghiem_trong"))), crit(), true);
        if (!groups.isEmpty())
            html += esc(QStringLiteral(" · theo nhóm: ") + groups.join(QStringLiteral(", ")));
        if (!tasks.isEmpty())
            html += QStringLiteral("<br>") + esc(QStringLiteral("Việc: ") + tasks.join(QStringLiteral("; ")));
        lay->addWidget(rich(card, col(Role::Ink2), 12, html));
    }
    body->addWidget(card);
    return sec;
}

} // namespace fincept::screens::beri
