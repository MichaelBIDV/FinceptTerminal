// src/screens/deepfa/DeepFaSectionsTop.cpp
// Top half of the DEEP FA ticker page: CỔNG · header band · §1 thesis + điểm gãy · §7 checklist sống ·
// §2 TENSION (memo ⚔ live) · chủ thể & dòng tiền. Values arrive pre-formatted from scripts/deepfa.py
// (number objects {v,u,t,b,n,g,txt}); this file only lays them out. Missing slices render a muted
// "[CẦN DATA] …" line so gaps stay visible, and every data string is escaped before rich text.
#include "screens/deepfa/DeepFaCommon.h"
#include "screens/deepfa/DeepFaSections.h"

#include <QFrame>
#include <QGridLayout>
#include <QHBoxLayout>
#include <QJsonArray>
#include <QJsonObject>
#include <QJsonValue>
#include <QLabel>
#include <QStringList>
#include <QToolButton>
#include <QVBoxLayout>

namespace fincept::screens::deepfa {

namespace {

// Private helpers carry the "dt_" prefix: the unity build may merge this TU with the bottom half.

const QString dt_kNeed = QStringLiteral("[CẦN DATA]");

QLabel* dt_plain(QWidget* parent, const QColor& c, int px, const QString& text, bool bold = false, bool mono = false) {
    auto* l = make_label(parent, c, px, Qt::PlainText, bold, mono);
    l->setText(text);
    return l;
}

QLabel* dt_rich(QWidget* parent, const QColor& c, int px, const QString& html, bool bold = false) {
    auto* l = make_label(parent, c, px, Qt::RichText, bold);
    l->setText(html);
    return l;
}

/// Small uppercase caption above a value.
QLabel* dt_eyebrow(QWidget* parent, const QString& text) {
    auto* l = dt_plain(parent, col(Role::Muted), 10, text.toUpper(), true);
    l->setWordWrap(false);
    return l;
}

/// "value (txt) + provenance" tile for a number object.
QWidget* dt_tile(QWidget* parent, const QString& caption, const QJsonObject& num, const QColor& value_color = QColor()) {
    QVBoxLayout* lay = nullptr;
    QFrame* card = make_card(parent, lay);
    lay->setContentsMargins(10, 8, 10, 8);
    lay->setSpacing(2);
    lay->addWidget(dt_eyebrow(card, caption));
    const QColor vc = value_color.isValid() ? value_color : col(Role::Ink);
    auto* v = dt_plain(card, vc, 17, num_txt(num), true, true);
    v->setWordWrap(false);
    lay->addWidget(v);
    const QString g = num.value(QLatin1String("g")).toString().trimmed();
    QString prov = prov_html(num, 9);
    if (!g.isEmpty())
        prov += QStringLiteral("<br>") + span(esc(g), col(Role::Muted));
    if (!prov.isEmpty())
        lay->addWidget(dt_rich(card, col(Role::Muted), 9, prov));
    return card;
}

/// Row of tiles with equal stretch.
QWidget* dt_tile_row(QWidget* parent, const QList<QWidget*>& tiles) {
    auto* w = new QWidget(parent);
    auto* hl = new QHBoxLayout(w);
    hl->setContentsMargins(0, 0, 0, 0);
    hl->setSpacing(8);
    for (QWidget* t : tiles) {
        t->setParent(w);
        hl->addWidget(t, 1);
    }
    return w;
}

/// Collapsible prose block (memo sections are long): a toggle button + a rich label.
QWidget* dt_collapsible(QWidget* parent, const QString& title, const QString& html, bool open) {
    auto* w = new QWidget(parent);
    auto* vl = new QVBoxLayout(w);
    vl->setContentsMargins(0, 0, 0, 0);
    vl->setSpacing(4);
    auto* btn = new QToolButton(w);
    btn->setText(title);
    btn->setCheckable(true);
    btn->setChecked(open);
    btn->setArrowType(open ? Qt::DownArrow : Qt::RightArrow);
    btn->setToolButtonStyle(Qt::ToolButtonTextBesideIcon);
    btn->setCursor(Qt::PointingHandCursor);
    btn->setStyleSheet(QStringLiteral("QToolButton { color:%1; background:transparent; border:none; font-weight:bold; }")
                           .arg(css(col(Role::Ink2))));
    vl->addWidget(btn);
    auto* body = dt_rich(w, col(Role::Ink), 13, html.isEmpty() ? span(esc(dt_kNeed), col(Role::Muted)) : html);
    body->setVisible(open);
    vl->addWidget(body);
    QObject::connect(btn, &QToolButton::toggled, body, [btn, body](bool on) {
        body->setVisible(on);
        btn->setArrowType(on ? Qt::DownArrow : Qt::RightArrow);
    });
    return w;
}

/// Grid table of plain strings: `cols` captions, `rows` cells (already escaped html allowed).
QWidget* dt_grid(QWidget* parent, const QStringList& cols, const QList<QStringList>& rows, const QList<int>& stretch = {}) {
    auto* w = new QWidget(parent);
    auto* g = new QGridLayout(w);
    g->setContentsMargins(0, 0, 0, 0);
    g->setHorizontalSpacing(12);
    g->setVerticalSpacing(4);
    for (int c = 0; c < cols.size(); ++c) {
        auto* h = dt_eyebrow(w, cols.at(c));
        g->addWidget(h, 0, c);
        g->setColumnStretch(c, c < stretch.size() ? stretch.at(c) : 1);
    }
    for (int r = 0; r < rows.size(); ++r) {
        const QStringList& cells = rows.at(r);
        for (int c = 0; c < cells.size() && c < cols.size(); ++c) {
            auto* l = dt_rich(w, col(Role::Ink), 12, cells.at(c));
            g->addWidget(l, r + 1, c, Qt::AlignTop);
        }
    }
    return w;
}

QString dt_pill(const QString& text, const QColor& c) {
    return pill_html(text, c, 10);
}

QString dt_status_pill(const QString& st) {
    const QString u = st.toLower();
    QColor c = col(Role::Muted);
    if (u == QLatin1String("ok"))
        c = col(Role::Up);
    else if (u == QLatin1String("warn"))
        c = col(Role::Amber);
    else if (u == QLatin1String("stale") || u == QLatin1String("missing"))
        c = col(Role::Down);
    return dt_pill(st, c);
}

QColor dt_pha_color(const QString& pha) {
    if (pha == QStringLiteral("khép") || pha == QStringLiteral("giữ") || pha == QStringLiteral("vẫn đồng pha"))
        return col(Role::Up);
    if (pha == QStringLiteral("mở") || pha == QStringLiteral("đổi chiều") || pha == QStringLiteral("vẫn lệch pha"))
        return col(Role::Down);
    if (pha == QStringLiteral("dịch nhẹ"))
        return col(Role::Amber);
    return col(Role::Muted);
}

QString dt_dir_glyph(const QJsonValue& v) {
    if (!v.isDouble())
        return QStringLiteral("—");
    const double d = v.toDouble();
    return d > 0 ? QStringLiteral("▲") : (d < 0 ? QStringLiteral("▼") : QStringLiteral("●"));
}

} // namespace

// ── CỔNG ─────────────────────────────────────────────────────────────────────

QWidget* build_cong(const QJsonObject& cong, QWidget* parent) {
    const bool dung = cong.value(QLatin1String("dung")).toBool(true);
    const QString dong = str(cong, "dong").trimmed();
    QVBoxLayout* lay = nullptr;
    QFrame* card = make_card(parent, lay, dung ? col(Role::Amber) : col(Role::Up));
    card->setObjectName(QStringLiteral("deepfaCong"));
    QString html = span(esc(dong.isEmpty() ? QStringLiteral("CỔNG: [CẦN DATA]") : dong), dung ? col(Role::Amber) : col(Role::Up), true);
    if (dung)
        html += QStringLiteral("<br>") + span(esc(QStringLiteral("CỔNG đang DỪNG — mọi nhận định dưới đây là nghiên cứu, không phải verdict risk/reward.")), col(Role::Muted));
    const QString t = str(cong, "t");
    if (!t.isEmpty())
        html += QStringLiteral(" ") + span(esc(t + QStringLiteral(" · ") + str(cong, "n")), col(Role::Muted));
    lay->addWidget(dt_rich(card, col(Role::Ink), 13, html));
    return card;
}

// ── Header band ──────────────────────────────────────────────────────────────

QWidget* build_header(const QJsonObject& meta, const QJsonObject& header, QWidget* parent) {
    auto* w = new QWidget(parent);
    auto* vl = new QVBoxLayout(w);
    vl->setContentsMargins(0, 6, 0, 0);
    vl->setSpacing(8);

    // line 1: ticker · name · baskets · DM · memo status · engine · regen
    const QJsonObject memo = meta.value(QLatin1String("memo")).toObject();
    QStringList parts;
    parts << QStringLiteral("<span style=\"font-size:22px; font-weight:bold; color:%1;\">%2</span>").arg(css(col(Role::Amber)), esc(str(meta, "tk")));
    parts << span(esc(str(meta, "ten")), col(Role::Ink), true);
    QStringList ro;
    for (const QJsonValue& v : meta.value(QLatin1String("ro")).toArray())
        ro << v.toString();
    if (!ro.isEmpty())
        parts << span(esc(ro.join(QStringLiteral(" · "))), col(Role::Muted));
    const QString dm = str(meta, "dm");
    if (dm == QLatin1String("NAV")) {
        const QJsonValue nav = meta.value(QLatin1String("nav_pct"));
        parts << dt_pill(nav.isDouble() ? QStringLiteral("NAV %1%").arg(QString::number(nav.toDouble(), 'f', 0)) : QStringLiteral("NAV"), col(Role::Up));
    } else if (dm == QLatin1String("WATCH")) {
        parts << dt_pill(QStringLiteral("WATCH"), col(Role::Blue));
    } else if (dm == QLatin1String("AVOID")) {
        parts << dt_pill(QStringLiteral("AVOID"), col(Role::Down));
    }
    if (memo.isEmpty()) {
        parts << dt_pill(QStringLiteral("chưa có memo"), col(Role::Down));
    } else {
        const QString st = str(memo, "state");
        parts << dt_pill(QStringLiteral("State %1").arg(st.isEmpty() ? QStringLiteral("—") : st), state_color(st));
        parts << dt_status_pill(QStringLiteral("memo %1 · %2").arg(str(memo, "date"), str(memo, "age_txt")));
        if (str(memo, "tier_hieu_luc") == QLatin1String("UNVERIFIED"))
            parts << dt_pill(QStringLiteral("UNVERIFIED"), col(Role::Down));
        if (!str(memo, "engine").isEmpty())
            parts << span(esc(QStringLiteral("engine ") + str(memo, "engine")), col(Role::Muted));
        if (memo.value(QLatin1String("deep")).toBool())
            parts << dt_pill(QStringLiteral("deep"), col(Role::Blue));
    }
    const QJsonObject regen = meta.value(QLatin1String("regen")).toObject();
    if (regen.value(QLatin1String("can")).toBool()) {
        QStringList why;
        for (const QJsonValue& v : regen.value(QLatin1String("ly_do")).toArray())
            why << v.toString();
        parts << dt_pill(QStringLiteral("↻ cần regen"), col(Role::Amber)) + QStringLiteral(" ") + span(esc(why.join(QStringLiteral("; "))), col(Role::Muted));
    }
    vl->addWidget(dt_rich(w, col(Role::Ink), 13, parts.join(QStringLiteral(" &nbsp; "))));

    // line 2: tiles
    const QJsonObject gia = header.value(QLatin1String("gia")).toObject();
    const QJsonObject delta = header.value(QLatin1String("delta_pct")).toObject();
    const QJsonObject sigma = header.value(QLatin1String("sigma_pe")).toObject();
    const QJsonObject edi = header.value(QLatin1String("edi")).toObject();
    const QJsonObject tp = header.value(QLatin1String("tp")).toObject();
    QList<QWidget*> tiles;
    tiles << dt_tile(w, QStringLiteral("Giá bảng"), gia);
    QJsonObject dl = delta;
    dl.insert(QLatin1String("g"), str(header, "ca_note"));
    tiles << dt_tile(w, QStringLiteral("Δ từ ngày memo"), dl, dir_color(delta.value(QLatin1String("v"))));
    QJsonObject sg = sigma;
    if (!str(header, "zone_pe").isEmpty())
        sg.insert(QLatin1String("g"), str(header, "zone_pe"));
    const double sv = sigma.value(QLatin1String("v")).toDouble(0.0);
    tiles << dt_tile(w, QStringLiteral("σ P/E (HHP)"), sg, sigma.value(QLatin1String("v")).isDouble() ? (sv < -1 ? col(Role::Up) : (sv > 1 ? col(Role::Down) : col(Role::Ink))) : col(Role::Muted));
    QJsonObject ed;
    ed.insert(QLatin1String("txt"), str(edi, "txt") + (str(edi, "stage").isEmpty() ? QString() : QStringLiteral(" · ") + str(edi, "stage")));
    ed.insert(QLatin1String("t"), edi.value(QLatin1String("t")));
    ed.insert(QLatin1String("b"), edi.value(QLatin1String("b")));
    ed.insert(QLatin1String("n"), QStringLiteral("edi_index.by_ticker"));
    if (edi.value(QLatin1String("late")).toBool())
        ed.insert(QLatin1String("g"), QStringLiteral("LATE — edge đã migrate sang FA/TA"));
    tiles << dt_tile(w, QStringLiteral("EDI leading"), ed, edi.value(QLatin1String("late")).toBool() ? col(Role::Amber) : col(Role::Ink));
    QJsonObject tpn;
    if (!tp.isEmpty() && tp.value(QLatin1String("target_price")).isDouble()) {
        tpn.insert(QLatin1String("txt"), str(tp, "target_price_txt") + QStringLiteral(" · ") + str(tp, "rating"));
        tpn.insert(QLatin1String("t"), tp.value(QLatin1String("tp_date")));
        tpn.insert(QLatin1String("b"), QStringLiteral("SS-T3"));
        tpn.insert(QLatin1String("n"), QStringLiteral("Vietcap coverage"));
        if (tp.value(QLatin1String("tp_stale")).toBool())
            tpn.insert(QLatin1String("g"), str(tp, "tp_flag_txt"));
    } else {
        tpn.insert(QLatin1String("txt"), dt_kNeed);
    }
    tiles << dt_tile(w, QStringLiteral("TP Vietcap (SS-T3)"), tpn, tp.value(QLatin1String("tp_stale")).toBool() ? col(Role::Amber) : col(Role::Violet));
    QJsonObject fg;
    const QString gate = str(header, "fund_gate");
    fg.insert(QLatin1String("txt"), gate.isEmpty() ? dt_kNeed : gate);
    fg.insert(QLatin1String("n"), QStringLiteral("fund_intent + GATE LVF"));
    tiles << dt_tile(w, QStringLiteral("Fund gate"), fg,
                     gate == QLatin1String("GATE-BLIND") ? col(Role::Down) : (gate == QStringLiteral("CHƯA LỌC") ? col(Role::Amber) : col(Role::Ink)));
    vl->addWidget(dt_tile_row(w, tiles));

    // line 3: secondary numbers + KG chip
    QStringList l3;
    for (const char* key : {"pe", "pb", "foreign_pct", "market_cap"}) {
        const QJsonObject n = header.value(QLatin1String(key)).toObject();
        const QString cap = key == QLatin1String("pe") ? QStringLiteral("P/E") : key == QLatin1String("pb") ? QStringLiteral("P/B")
                            : key == QLatin1String("foreign_pct") ? QStringLiteral("NN sở hữu") : QStringLiteral("Vốn hoá");
        l3 << span(esc(cap + QStringLiteral(" ")), col(Role::Muted)) + span(esc(num_txt(n)), col(Role::Ink), true) + QStringLiteral(" ") + prov_html(n, 9);
    }
    const QJsonObject kgc = header.value(QLatin1String("kg_chip")).toObject();
    if (kgc.value(QLatin1String("co")).toBool())
        l3 << span(esc(QStringLiteral("KG bậc %1 · built %2").arg(QString::number(kgc.value(QLatin1String("degree")).toInt()), str(kgc, "built_at").left(16))), col(Role::Muted));
    vl->addWidget(dt_rich(w, col(Role::Ink), 12, l3.join(QStringLiteral(" &nbsp;·&nbsp; "))));

    // warnings
    const QJsonArray warns = meta.value(QLatin1String("warnings")).toArray();
    if (!warns.isEmpty()) {
        QStringList ws;
        for (const QJsonValue& v : warns)
            ws << esc(QStringLiteral("⚠ ") + v.toString());
        vl->addWidget(dt_rich(w, col(Role::Amber), 11, ws.join(QStringLiteral("<br>"))));
    }
    return w;
}

// ── §1 Thesis + điểm gãy ─────────────────────────────────────────────────────

QWidget* build_thesis(const QJsonObject& thesis, QWidget* parent) {
    QVBoxLayout* body = nullptr;
    QWidget* sec = make_section(parent, QStringLiteral("§1"), QStringLiteral("THESIS · điểm gãy của thesis"), QString(), body);
    const QJsonObject bp = thesis.value(QLatin1String("break_point")).toObject();
    QVBoxLayout* lay = nullptr;
    QFrame* card = make_card(sec, lay, thesis.value(QLatin1String("thieu_diem_gay")).toBool() ? col(Role::Down) : col(Role::Amber));
    lay->addWidget(dt_eyebrow(card, QStringLiteral("Điểm gãy của thesis")));
    const QString bpt = str(bp, "text").trimmed();
    if (bpt.isEmpty()) {
        lay->addWidget(dt_plain(card, col(Role::Down), 13,
                                thesis.value(QLatin1String("memo_co")).toBool() ? QStringLiteral("Memo không nêu điểm gãy — theo luật DeepFA đây là memo hỏng (cờ rigor).")
                                                                                 : QStringLiteral("[CẦN DATA] chưa có memo cho mã này."), true));
    } else {
        lay->addWidget(dt_rich(card, col(Role::Ink), 13, esc(bpt).replace(QStringLiteral("**"), QString())));
        QStringList tail;
        tail << span(esc(QStringLiteral("nguồn: ") + str(bp, "src")), col(Role::Muted));
        for (const QJsonValue& v : bp.value(QLatin1String("muc_gia")).toArray()) {
            const QJsonObject m = v.toObject();
            const QJsonValue adj = m.value(QLatin1String("adj_lvl"));
            tail << span(esc(QStringLiteral("mốc %1 → %2 trên cơ sở hôm nay (CA ×%3)")
                                 .arg(QString::number(m.value(QLatin1String("memo_lvl")).toDouble(), 'f', 1),
                                      adj.isDouble() ? QString::number(adj.toDouble(), 'f', 1) : QStringLiteral("?"),
                                      QString::number(m.value(QLatin1String("ca_factor")).toDouble(1.0), 'f', 4))),
                         col(Role::Blue));
        }
        lay->addWidget(dt_rich(card, col(Role::Muted), 11, tail.join(QStringLiteral(" · "))));
    }
    body->addWidget(card);
    body->addWidget(dt_collapsible(sec, QStringLiteral("§1 Thesis (memo, nguyên văn)"), str(thesis, "memo_html"), true));
    return sec;
}

// ── §7 Checklist sống ────────────────────────────────────────────────────────

QWidget* build_conditions(const QJsonObject& dk, QWidget* parent) {
    const QJsonObject tt = dk.value(QLatin1String("tom_tat")).toObject();
    const QString lede = tt.value(QLatin1String("n")).toInt() == 0
        ? QString()
        : QStringLiteral("%1 điều kiện · máy kiểm được %2 · đến hạn %3 · quá hạn %4 · gãy %5 — hạn ±7 ngày; loại ngoài whitelist hiện nguyên văn.")
              .arg(tt.value(QLatin1String("n")).toInt()).arg(tt.value(QLatin1String("n_kiem_duoc")).toInt())
              .arg(tt.value(QLatin1String("n_den_han")).toInt()).arg(tt.value(QLatin1String("n_qua_han")).toInt()).arg(tt.value(QLatin1String("n_gay")).toInt());
    QVBoxLayout* body = nullptr;
    QWidget* sec = make_section(parent, QStringLiteral("§7"), QStringLiteral("ĐIỀU KIỆN FALSIFIABLE — checklist sống"), lede, body);
    struct Group { const char* key; const char* title; };
    const Group groups[] = {{"dung", "Thesis đúng nếu"}, {"gay", "Thesis gãy nếu"}, {"lich", "Lịch theo dõi"}};
    bool any = false;
    for (const Group& g : groups) {
        const QJsonArray items = dk.value(QLatin1String(g.key)).toArray();
        if (items.isEmpty())
            continue;
        any = true;
        body->addWidget(dt_plain(sec, col(Role::Ink2), 12, QString::fromUtf8(g.title), true));
        QList<QStringList> rows;
        for (const QJsonValue& v : items) {
            const QJsonObject it = v.toObject();
            const QString st = str(it, "trang_thai");
            const QString kq = str(it, "ket_qua");
            QColor stc = col(Role::Muted);
            if (st == QStringLiteral("quá hạn") || st == QStringLiteral("đến hạn"))
                stc = col(Role::Amber);
            else if (st == QStringLiteral("sắp đến hạn"))
                stc = col(Role::Blue);
            QColor kqc = col(Role::Muted);
            if (kq == QStringLiteral("gãy"))
                kqc = col(Role::Down);
            else if (kq == QStringLiteral("đạt"))
                kqc = col(Role::Up);
            else if (kq == QStringLiteral("chưa"))
                kqc = col(Role::Ink2);
            const QString so = str(it, "so_song");
            const QString ly = str(it, "ly_do");
            rows << (QStringList() << esc(str(it, "text"))
                                   << span(esc(str(it, "loai").isEmpty() ? QStringLiteral("—") : str(it, "loai")), col(Role::Ink2))
                                   << esc(str(it, "date_hint").isEmpty() ? (str(it, "due").isEmpty() ? QStringLiteral("—") : str(it, "due")) : str(it, "date_hint"))
                                   << dt_pill(st.isEmpty() ? QStringLiteral("—") : st, stc)
                                   << (so.isEmpty() ? span(esc(dt_kNeed), col(Role::Muted)) : esc(so)) + (ly.isEmpty() ? QString() : QStringLiteral("<br>") + span(esc(ly), col(Role::Muted)))
                                   << (kq.isEmpty() ? span(QStringLiteral("—"), col(Role::Muted)) : dt_pill(kq, kqc)));
        }
        body->addWidget(dt_grid(sec, QStringList() << QStringLiteral("Điều kiện") << QStringLiteral("Loại") << QStringLiteral("Hạn") << QStringLiteral("Trạng thái")
                                                    << QStringLiteral("Số sống") << QStringLiteral("Kết quả"),
                                rows, QList<int>() << 6 << 2 << 1 << 1 << 4 << 1));
    }
    if (!any)
        body->addWidget(make_need(sec, tt.value(QLatin1String("memo_co")).toBool() ? QStringLiteral("§7 của memo không có mục đúng/gãy/lịch nhận diện được — đọc nguyên văn bên dưới.")
                                                                                     : QStringLiteral("chưa có §7 (memo thiếu hoặc chưa có memo).")));
    if (!str(tt, "memo_html").isEmpty())
        body->addWidget(dt_collapsible(sec, QStringLiteral("§7 nguyên văn"), str(tt, "memo_html"), !any));
    return sec;
}

// ── §2 TENSION ───────────────────────────────────────────────────────────────

QWidget* build_tension(const QJsonObject& tension, QWidget* parent) {
    const QJsonObject live = tension.value(QLatin1String("live")).toObject();
    const QJsonObject drift = tension.value(QLatin1String("drift")).toObject();
    const QString tong = str(drift, "tong");
    QVBoxLayout* body = nullptr;
    QWidget* sec = make_section(parent, QStringLiteral("§2"), QStringLiteral("TENSION GIỮA CÁC DÒNG PHIẾU — memo ⚔ hôm nay"),
                                QStringLiteral("Giá trị nằm ở giao/lệch pha giữa ≥3 dòng phiếu độc lập; lệch pha là cờ đỏ, không phải nhiễu."), body);

    // verdict line
    QString vh = span(esc(QStringLiteral("Sống: ")), col(Role::Muted)) + span(esc(str(live, "alignment")), col(Role::Ink), true);
    vh += QStringLiteral(" &nbsp;·&nbsp; ") + span(esc(QStringLiteral("Drift so memo: ")), col(Role::Muted)) + dt_pill(tong.isEmpty() ? dt_kNeed : tong, dt_pha_color(tong));
    body->addWidget(dt_rich(sec, col(Role::Ink), 13, vh));

    // matrix memo ⚔ live
    QList<QStringList> rows;
    const QJsonArray cap = drift.value(QLatin1String("cap")).toArray();
    QJsonArray liveRows = live.value(QLatin1String("dong")).toArray();
    // map live rows by first word for the flow row (memo has no flow stream)
    for (int i = 0; i < liveRows.size(); ++i) {
        const QJsonObject l = liveRows.at(i).toObject();
        const QString name = str(l, "dong");
        QJsonObject m;
        QString pha;
        for (const QJsonValue& cv : cap) {
            const QJsonObject c = cv.toObject();
            if (name.startsWith(str(c, "dong").left(4), Qt::CaseInsensitive)) {
                m = c.value(QLatin1String("memo")).toObject();
                pha = str(c, "pha");
                break;
            }
        }
        QString memo_txt = QStringLiteral("—");
        if (!m.isEmpty()) {
            QStringList mp;
            for (const char* k : {"tone", "up", "down", "net", "net_1m_M", "score", "stage"}) {
                const QJsonValue v = m.value(QLatin1String(k));
                if (v.isDouble())
                    mp << QStringLiteral("%1 %2").arg(QLatin1String(k), QString::number(v.toDouble()));
                else if (v.isString() && !v.toString().isEmpty())
                    mp << v.toString();
            }
            memo_txt = dt_dir_glyph(m.value(QLatin1String("huong"))) + QStringLiteral(" ") + mp.join(QStringLiteral(" · "));
            if (!str(m, "t").isEmpty())
                memo_txt += QStringLiteral(" ") + span(esc(str(m, "t")), col(Role::Muted));
        }
        QString live_txt = span(dt_dir_glyph(l.value(QLatin1String("huong"))), dir_color(l.value(QLatin1String("huong"))), true) + QStringLiteral(" ") + esc(str(l, "txt"));
        live_txt += QStringLiteral(" ") + prov_html(l, 9);
        const QString g = str(l, "g");
        if (!g.isEmpty())
            live_txt += QStringLiteral("<br>") + span(esc(g), col(Role::Muted));
        rows << (QStringList() << span(esc(name), col(Role::Ink2), true) << memo_txt << live_txt << (pha.isEmpty() ? span(QStringLiteral("—"), col(Role::Muted)) : dt_pill(pha, dt_pha_color(pha))));
    }
    if (rows.isEmpty())
        body->addWidget(make_need(sec, QStringLiteral("không có dòng phiếu sống nào (lớp mgmt_view/source_map/vietcap_fundamentals/vc_lk thiếu)")));
    else
        body->addWidget(dt_grid(sec, QStringList() << QStringLiteral("Dòng phiếu") << QStringLiteral("Memo (ngày json)") << QStringLiteral("Hôm nay") << QStringLiteral("Pha"),
                                rows, QList<int>() << 2 << 3 << 5 << 1));
    const QString dg = str(drift, "g");
    if (!dg.isEmpty())
        body->addWidget(dt_plain(sec, col(Role::Muted), 11, dg));

    // street votes + BLĐ gate
    const QJsonObject sv = tension.value(QLatin1String("street_votes")).toObject();
    const QJsonObject bld = tension.value(QLatin1String("bld")).toObject();
    QStringList notes;
    if (!sv.isEmpty()) {
        QStringList cl;
        for (const QJsonValue& v : sv.value(QLatin1String("clusters")).toArray()) {
            const QJsonObject c = v.toObject();
            cl << QStringLiteral("%1 (%2)").arg(str(c, "terminal"), QString::number(c.value(QLatin1String("brokers")).toArray().size()));
        }
        notes << span(esc(QStringLiteral("Street: %1 broker = %2 phiếu độc lập theo fingerprint terminal [%3]; ▲%4/▼%5 (regex)%6")
                              .arg(QString::number(sv.value(QLatin1String("n_brokers")).toInt()), QString::number(sv.value(QLatin1String("n_independent")).toInt()),
                                   cl.join(QStringLiteral(", ")), QString::number(sv.value(QLatin1String("up")).toDouble()), QString::number(sv.value(QLatin1String("down")).toDouble()),
                                   sv.value(QLatin1String("minority_first")).toBool() ? QStringLiteral(" — phe ▼ thiểu số: đọc variant trước") : QString())),
                      col(Role::Ink2)) + QStringLiteral(" ") + tier_html(QStringLiteral("EST"));
    }
    if (!bld.isEmpty()) {
        notes << span(esc(QStringLiteral("BLĐ: tone %1 (%2 thuận/%3 khó)%4 · %5")
                              .arg(str(bld, "tone").isEmpty() ? dt_kNeed : str(bld, "tone"), QString::number(bld.value(QLatin1String("n_tail")).toDouble()),
                                   QString::number(bld.value(QLatin1String("n_head")).toDouble()), bld.value(QLatin1String("cap")).toBool() ? QStringLiteral(" ⚠cap 16/16") : QString(),
                                   str(bld, "g"))),
                      col(Role::Ink2)) + QStringLiteral(" ") + tier_html(QStringLiteral("EST"));
    }
    if (!notes.isEmpty())
        body->addWidget(dt_rich(sec, col(Role::Ink2), 11, notes.join(QStringLiteral("<br>"))));
    body->addWidget(dt_collapsible(sec, QStringLiteral("§2 TENSION (memo, nguyên văn — số của memo tại ngày memo)"), str(tension, "memo_html"), false));
    return sec;
}

// ── Chủ thể & dòng tiền ──────────────────────────────────────────────────────

QWidget* build_chu_the(const QJsonObject& ct, QWidget* parent) {
    QVBoxLayout* body = nullptr;
    QWidget* sec = make_section(parent, QStringLiteral("CT"), QStringLiteral("CHỦ THỂ & DÒNG TIỀN — chủ thể có đang cần thị trường không?"),
                                QStringLiteral("Câu hỏi này đứng TRƯỚC quality/định giá (luật §6.5). Δ cổ đông thật > hệ số k > proxy giá/KL."), body);
    const QJsonObject flow = ct.value(QLatin1String("flow")).toObject();
    const QJsonObject nhan = ct.value(QLatin1String("nhan")).toObject();
    QList<QWidget*> tiles;
    QJsonObject nh;
    nh.insert(QLatin1String("txt"), str(nhan, "v").isEmpty() ? dt_kNeed : str(nhan, "v"));
    nh.insert(QLatin1String("t"), nhan.value(QLatin1String("t")));
    nh.insert(QLatin1String("b"), nhan.value(QLatin1String("b")));
    nh.insert(QLatin1String("n"), nhan.value(QLatin1String("n")));
    if (!str(nhan, "g").isEmpty())
        nh.insert(QLatin1String("g"), str(nhan, "g"));
    const QString nv = str(nhan, "v");
    tiles << dt_tile(sec, QStringLiteral("Chủ thể cần thị trường?"), nh, nv == QStringLiteral("cần") ? col(Role::Amber) : (nv == QStringLiteral("không cần") ? col(Role::Up) : col(Role::Ink)));
    tiles << dt_tile(sec, QStringLiteral("NN ròng 20 phiên"), flow.value(QLatin1String("foreign_net_20")).toObject(), dir_color(flow.value(QLatin1String("foreign_net_20")).toObject().value(QLatin1String("v"))));
    tiles << dt_tile(sec, QStringLiteral("Tự doanh ròng 20 phiên"), flow.value(QLatin1String("prop_net_20")).toObject(), dir_color(flow.value(QLatin1String("prop_net_20")).toObject().value(QLatin1String("v"))));
    tiles << dt_tile(sec, QStringLiteral("NN sở hữu"), flow.value(QLatin1String("foreign_pct")).toObject());
    const QJsonObject nqs = ct.value(QLatin1String("nqs_doi_chieu")).toObject();
    if (!nqs.isEmpty())
        tiles << dt_tile(sec, QStringLiteral("Đối chiếu NQS 20 phiên"), nqs, dir_color(nqs.value(QLatin1String("v"))));
    body->addWidget(dt_tile_row(sec, tiles));

    if (!ct.value(QLatin1String("co")).toBool()) {
        body->addWidget(make_need(sec, str(ct, "ly_do")));
    } else {
        // fund gate
        const QJsonObject fund = ct.value(QLatin1String("fund")).toObject();
        QString fh;
        if (str(fund, "trang_thai") == QLatin1String("GATE-BLIND"))
            fh = span(esc(QStringLiteral("Fund intent: GATE-BLIND — ") + str(fund, "ly_do")), col(Role::Down), true);
        else if (str(fund, "trang_thai") == QStringLiteral("CHƯA LỌC"))   // fresh universe export, no per-fund rows: gate could not run
            fh = span(esc(QStringLiteral("Fund intent: ") + str(fund, "ly_do")), col(Role::Amber), true);
        else if (str(fund, "trang_thai") == QLatin1String("ok"))
            fh = span(esc(QStringLiteral("Fund intent sau GATE LVF: %1 (thô: %2; cơ học loại %3 cp)")
                              .arg(str(fund, "nhan_sau_gate"), str(fund, "nhan_tho"), QString::number(fund.value(QLatin1String("co_hoc_cp")).toDouble(), 'f', 0))),
                      col(Role::Ink2));
        else
            fh = span(esc(QStringLiteral("Fund intent: ") + str(fund, "ly_do")), col(Role::Muted));
        body->addWidget(dt_rich(sec, col(Role::Ink), 12, fh));

        // insider table
        const QJsonArray nb = ct.value(QLatin1String("noi_bo")).toArray();
        if (!nb.isEmpty()) {
            body->addWidget(dt_plain(sec, col(Role::Ink2), 12, QStringLiteral("Giao dịch nội bộ (lk_hoso, Vietcap IQ)"), true));
            QList<QStringList> rows;
            for (const QJsonValue& v : nb) {
                const QJsonObject r = v.toObject();
                rows << (QStringList() << esc(str(r, "ngay")) << esc(str(r, "nguoi")) << esc(str(r, "chuc_vu")) << esc(str(r, "hanh_dong"))
                                       << esc(str(r, "so_luong")) << esc(str(r, "trang_thai")) << tier_html(str(r, "bac")));
            }
            body->addWidget(dt_grid(sec, QStringList() << QStringLiteral("Ngày") << QStringLiteral("Người") << QStringLiteral("Chức vụ") << QStringLiteral("Hành động")
                                                        << QStringLiteral("KL") << QStringLiteral("Trạng thái") << QStringLiteral("Bậc"),
                                    rows, QList<int>() << 1 << 3 << 2 << 2 << 1 << 1 << 1));
        }
        // shareholder milestones
        const QJsonObject cd = ct.value(QLatin1String("codong")).toObject();
        const QJsonArray moc = cd.value(QLatin1String("moc")).toArray();
        QStringList mline;
        for (const QJsonValue& v : moc) {
            const QJsonObject m = v.toObject();
            const QJsonValue val = m.value(QLatin1String("v"));
            mline << QStringLiteral("%1: %2%3").arg(str(m, "ky"), val.isDouble() ? QString::number(val.toDouble(), 'f', 0) : QStringLiteral("—"),
                                                     m.value(QLatin1String("cf")).toBool() ? QStringLiteral(" (CF)") : QString());
        }
        body->addWidget(dt_rich(sec, col(Role::Ink2), 11,
                                span(esc(QStringLiteral("Số cổ đông (mốc): ")), col(Role::Muted)) +
                                    (mline.isEmpty() ? span(esc(dt_kNeed + QStringLiteral(" ") + str(cd, "trang_thai")), col(Role::Muted)) : esc(mline.join(QStringLiteral(" · ")))) +
                                    QStringLiteral(" ") + span(esc(str(cd, "nguon_moc")), col(Role::Muted))));
        const QJsonValue pha = ct.value(QLatin1String("pha"));
        if (pha.isObject())
            body->addWidget(dt_rich(sec, col(Role::Ink2), 11, span(esc(QStringLiteral("Pha lăng kính: ")), col(Role::Muted)) + esc(str(pha.toObject(), "nhan")) +
                                                                QStringLiteral(" ") + span(esc(str(pha.toObject(), "phu")), col(Role::Muted)) + QStringLiteral(" ") + tier_html(QStringLiteral("EST"))));
        // triggers
        const QJsonArray trig = ct.value(QLatin1String("trigger")).toArray();
        if (!trig.isEmpty()) {
            QStringList tl;
            for (const QJsonValue& v : trig) {
                const QJsonObject t = v.toObject();
                tl << QStringLiteral("• ") + esc(str(t, "loai")) + (str(t, "trang_thai").isEmpty() ? QString() : QStringLiteral(" — ") + span(esc(str(t, "trang_thai")), col(Role::Ink2)));
            }
            body->addWidget(dt_rich(sec, col(Role::Ink2), 11, span(esc(QStringLiteral("Trigger dữ liệu (lk_hoso, trung tính): ")), col(Role::Muted)) + QStringLiteral("<br>") + tl.join(QStringLiteral("<br>"))));
        }
        // owner intent events
        const QJsonArray yd = ct.value(QLatin1String("y_do_chu_the")).toArray();
        if (!yd.isEmpty()) {
            QStringList el;
            for (const QJsonValue& v : yd) {
                const QJsonObject e = v.toObject();
                el << QStringLiteral("%1 · %2 · %3%4").arg(esc(str(e, "date")), esc(str(e, "type")), esc(str(e, "title")),
                                                            e.value(QLatin1String("auto")).toBool() ? QString() : QStringLiteral(" ") + dt_pill(QStringLiteral("curated"), col(Role::Amber)));
            }
            body->addWidget(dt_rich(sec, col(Role::Ink2), 11, span(esc(QStringLiteral("Ý đồ chủ thể (owner_intent): ")), col(Role::Muted)) + QStringLiteral("<br>") + el.join(QStringLiteral("<br>"))));
        }
        const QJsonArray cdta = ct.value(QLatin1String("can_data")).toArray();
        if (!cdta.isEmpty()) {
            QStringList cl;
            for (const QJsonValue& v : cdta) {
                const QJsonObject c = v.toObject();
                cl << esc(str(c, "khoa") + QStringLiteral(": ") + str(c, "ly_do"));
            }
            body->addWidget(dt_rich(sec, col(Role::Muted), 10, cl.join(QStringLiteral("<br>"))));
        }
    }
    return sec;
}

} // namespace fincept::screens::deepfa
