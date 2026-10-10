// src/screens/deepfa/DeepFaSectionsBottom.cpp
// Bottom half of the DEEP FA ticker page: §6 định giá (σ dated · HHP band chart · TP strip) · §4 filing
// teardown (worksheet 10 groups · read list · doc gaps · inventory) · §3 codex + EDI + §5 board ·
// đồ thị tri thức (KG neighbourhood) · ledger (labelled by its nature) · phụ lục (catalyst/news after
// memo · sources freshness · rigor 6D proxy · registry gaps). Same rules as the top half.
#include "screens/deepfa/DeepFaCommon.h"
#include "screens/deepfa/DeepFaSections.h"
#include "screens/hhp_valuation/HhpChart.h"

#include <QDesktopServices>
#include <QFileInfo>
#include <QFrame>
#include <QGridLayout>
#include <QHBoxLayout>
#include <QJsonArray>
#include <QJsonObject>
#include <QJsonValue>
#include <QLabel>
#include <QPointF>
#include <QPushButton>
#include <QStringList>
#include <QToolButton>
#include <QUrl>
#include <QVBoxLayout>
#include <QVector>

#include <cmath>

namespace fincept::screens::deepfa {

namespace {

// Private helpers carry the "db_" prefix: the unity build may merge this TU with the top half.

const QString db_kNeed = QStringLiteral("[CẦN DATA]");

QLabel* db_plain(QWidget* parent, const QColor& c, int px, const QString& text, bool bold = false, bool mono = false) {
    auto* l = make_label(parent, c, px, Qt::PlainText, bold, mono);
    l->setText(text);
    return l;
}

QLabel* db_rich(QWidget* parent, const QColor& c, int px, const QString& html, bool bold = false) {
    auto* l = make_label(parent, c, px, Qt::RichText, bold);
    l->setText(html);
    return l;
}

QLabel* db_eyebrow(QWidget* parent, const QString& text) {
    auto* l = db_plain(parent, col(Role::Muted), 10, text.toUpper(), true);
    l->setWordWrap(false);
    return l;
}

QWidget* db_tile(QWidget* parent, const QString& caption, const QJsonObject& num, const QColor& value_color = QColor()) {
    QVBoxLayout* lay = nullptr;
    QFrame* card = make_card(parent, lay);
    lay->setContentsMargins(10, 8, 10, 8);
    lay->setSpacing(2);
    lay->addWidget(db_eyebrow(card, caption));
    auto* v = db_plain(card, value_color.isValid() ? value_color : col(Role::Ink), 17, num_txt(num), true, true);
    v->setWordWrap(false);
    lay->addWidget(v);
    QString prov = prov_html(num, 9);
    const QString g = num.value(QLatin1String("g")).toString().trimmed();
    if (!g.isEmpty())
        prov += QStringLiteral("<br>") + span(esc(g), col(Role::Muted));
    if (!prov.isEmpty())
        lay->addWidget(db_rich(card, col(Role::Muted), 9, prov));
    return card;
}

QWidget* db_tile_row(QWidget* parent, const QList<QWidget*>& tiles) {
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

QWidget* db_collapsible(QWidget* parent, const QString& title, const QString& html, bool open) {
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
    btn->setStyleSheet(QStringLiteral("QToolButton { color:%1; background:transparent; border:none; font-weight:bold; }").arg(css(col(Role::Ink2))));
    vl->addWidget(btn);
    auto* body = db_rich(w, col(Role::Ink), 13, html.isEmpty() ? span(esc(db_kNeed), col(Role::Muted)) : html);
    body->setVisible(open);
    vl->addWidget(body);
    QObject::connect(btn, &QToolButton::toggled, body, [btn, body](bool on) {
        body->setVisible(on);
        btn->setArrowType(on ? Qt::DownArrow : Qt::RightArrow);
    });
    return w;
}

QWidget* db_grid(QWidget* parent, const QStringList& cols, const QList<QStringList>& rows, const QList<int>& stretch = {}) {
    auto* w = new QWidget(parent);
    auto* g = new QGridLayout(w);
    g->setContentsMargins(0, 0, 0, 0);
    g->setHorizontalSpacing(12);
    g->setVerticalSpacing(4);
    for (int c = 0; c < cols.size(); ++c) {
        g->addWidget(db_eyebrow(w, cols.at(c)), 0, c);
        g->setColumnStretch(c, c < stretch.size() ? stretch.at(c) : 1);
    }
    for (int r = 0; r < rows.size(); ++r) {
        const QStringList& cells = rows.at(r);
        for (int c = 0; c < cells.size() && c < cols.size(); ++c)
            g->addWidget(db_rich(w, col(Role::Ink), 12, cells.at(c)), r + 1, c, Qt::AlignTop);
    }
    return w;
}

QVector<QPointF> db_points(const QJsonValue& arr) {
    QVector<QPointF> out;
    for (const QJsonValue& v : arr.toArray()) {
        const QJsonArray p = v.toArray();
        if (p.size() < 2 || !p.at(0).isDouble() || !p.at(1).isDouble())
            continue;
        out.push_back(QPointF(p.at(0).toDouble(), p.at(1).toDouble()));
    }
    return out;
}

hhp::HhpChartSeries db_series(hhp::HhpChartSeries::Kind kind, const QString& name, const QColor& c, double width, double opacity,
                              const QJsonValue& upper, const QJsonValue& lower = QJsonValue()) {
    hhp::HhpChartSeries s;
    s.kind = kind;
    s.name = name;
    s.color = c;
    s.width = width;
    s.opacity = opacity;
    s.points = db_points(upper);
    if (!lower.isUndefined() && !lower.isNull())
        s.lower = db_points(lower);
    return s;
}

QString db_num(double v, int dec = 1) {
    if (!std::isfinite(v))
        return db_kNeed;
    QString s = QString::number(std::abs(v), 'f', dec);
    s.replace(QLatin1Char('.'), QLatin1Char(','));
    return (v < 0 ? QString(QChar(0x2212)) : QString()) + s;
}

QColor db_stale_color(bool stale) {
    return stale ? col(Role::Down) : col(Role::Up);
}

} // namespace

// ── §6 Định giá ──────────────────────────────────────────────────────────────

QWidget* build_dinh_gia(const QJsonObject& dg, QWidget* parent) {
    QVBoxLayout* body = nullptr;
    QWidget* sec = make_section(parent, QStringLiteral("§6"), QStringLiteral("ĐỊNH GIÁ — σ của chính mã, kèm ngày đo"), str(dg, "gia_note"), body);
    const QJsonObject sig = dg.value(QLatin1String("sigma")).toObject();
    const QJsonObject pe = sig.value(QLatin1String("pe")).toObject();
    const QJsonObject pb = sig.value(QLatin1String("pb")).toObject();
    const QJsonObject rs = dg.value(QLatin1String("ratio_song")).toObject();
    const QJsonObject pc = dg.value(QLatin1String("pctile")).toObject();
    QList<QWidget*> tiles;
    auto sigma_tile = [&](const QJsonObject& b, const QString& cap) {
        QJsonObject n;
        n.insert(QLatin1String("txt"), str(b, "sigma_txt") + (str(b, "zone").isEmpty() ? QString() : QStringLiteral(" · ") + str(b, "zone")));
        n.insert(QLatin1String("t"), b.value(QLatin1String("t")));
        n.insert(QLatin1String("b"), b.value(QLatin1String("b")));
        n.insert(QLatin1String("n"), b.value(QLatin1String("src")));
        const QJsonValue mean = b.value(QLatin1String("mean"));
        if (mean.isDouble())
            n.insert(QLatin1String("g"), QStringLiteral("now %1 · μ %2 · σ %3 · n %4").arg(db_num(b.value(QLatin1String("now")).toDouble(), 2), db_num(mean.toDouble(), 2),
                                                                                       db_num(b.value(QLatin1String("sd")).toDouble(), 2), QString::number(b.value(QLatin1String("n")).toDouble(), 'f', 0)));
        const double sv = b.value(QLatin1String("sigma")).toDouble(0.0);
        return db_tile(sec, cap, n, b.value(QLatin1String("sigma")).isDouble() ? (sv < -1 ? col(Role::Up) : (sv > 1 ? col(Role::Down) : col(Role::Ink))) : col(Role::Muted));
    };
    tiles << sigma_tile(pe, QStringLiteral("P/E σ (HHP)"));
    tiles << sigma_tile(pb, QStringLiteral("P/B σ (HHP)"));
    tiles << db_tile(sec, QStringLiteral("P/E sống (Vietcap)"), rs.value(QLatin1String("pe")).toObject());
    tiles << db_tile(sec, QStringLiteral("P/B sống (Vietcap)"), rs.value(QLatin1String("pb")).toObject());
    QJsonObject pn;
    const QJsonValue p3 = pc.value(QLatin1String("pe_3y")), pa = pc.value(QLatin1String("pe_all"));
    pn.insert(QLatin1String("txt"), (p3.isDouble() && pa.isDouble()) ? QStringLiteral("3Y %1 · toàn dải %2").arg(db_num(p3.toDouble(), 0), db_num(pa.toDouble(), 0)) : db_kNeed);
    pn.insert(QLatin1String("t"), pc.value(QLatin1String("t")));
    pn.insert(QLatin1String("b"), pc.value(QLatin1String("b")));
    pn.insert(QLatin1String("n"), pc.value(QLatin1String("n")));
    pn.insert(QLatin1String("g"), pc.value(QLatin1String("g")));
    tiles << db_tile(sec, QStringLiteral("Percentile P/E"), pn);
    body->addWidget(db_tile_row(sec, tiles));
    if (!str(sig, "g").isEmpty())
        body->addWidget(db_plain(sec, col(Role::Muted), 11, str(sig, "g")));

    // HHP band chart
    const QJsonValue chv = dg.value(QLatin1String("hhp_chart"));
    if (chv.isObject()) {
        const QJsonObject ch = chv.toObject();
        auto* chart = new hhp::HhpChart(true, sec);
        chart->set_plot_min_height(300);
        using Kind = hhp::HhpChartSeries::Kind;
        const QVector<hhp::HhpChartSeries> series = {
            db_series(Kind::Band, QStringLiteral("Vùng rẻ P/E (−2σ…−1σ)"), col(Role::Up), 0.0, 0.30, ch.value(QLatin1String("cheap1")), ch.value(QLatin1String("cheap2"))),
            db_series(Kind::Band, QStringLiteral("Vùng mắc P/E (+1σ…+2σ)"), col(Role::Down), 0.0, 0.26, ch.value(QLatin1String("rich2")), ch.value(QLatin1String("rich1"))),
            db_series(Kind::Dashed, QStringLiteral("P/E trung bình"), col(Role::Amber), 1.2, 1.0, ch.value(QLatin1String("fair"))),
            db_series(Kind::Line, QStringLiteral("Giá (điều chỉnh)"), col(Role::Blue), 2.2, 1.0, ch.value(QLatin1String("price"))),
        };
        chart->set_series(series, QStringLiteral("Giá (%1)").arg(str(ch, "unit")), 1, true);
        chart->set_range(QStringLiteral("3Y"));
        body->addWidget(chart);
        body->addWidget(db_rich(sec, col(Role::Muted), 10, span(esc(QStringLiteral("HHP band · as_of %1 · %2 · %3").arg(str(ch, "as_of"), str(ch, "n"), str(ch, "g"))), col(Role::Muted)) + QStringLiteral(" ") + tier_html(str(ch, "b"))));
    } else {
        body->addWidget(make_need(sec, QStringLiteral("chưa có chuỗi HHP (hhp_vn100_series/<TK>.json) — không vẽ chart, không bịa số")));
    }

    // TP strip
    const QJsonArray tps = dg.value(QLatin1String("tp_strip")).toArray();
    if (!tps.isEmpty()) {
        body->addWidget(db_plain(sec, col(Role::Ink2), 12, QStringLiteral("Giá mục tiêu sell-side (SS-T3 — mọi nguồn; cũ >90 ngày gắn cờ, không xếp hạng theo upside)"), true));
        QList<QStringList> rows;
        for (const QJsonValue& v : tps) {
            const QJsonObject t = v.toObject();
            const bool stale = t.value(QLatin1String("stale")).toBool();
            const QJsonValue age = t.value(QLatin1String("age_d"));
            rows << (QStringList() << esc(str(t, "nguon")) << span(esc(str(t, "tp_txt")), stale ? col(Role::Amber) : col(Role::Ink), true) << esc(str(t, "rec"))
                                   << esc(str(t, "t")) + (age.isDouble() ? span(esc(QStringLiteral(" (%1 ngày)").arg(QString::number(age.toDouble(), 'f', 0))), col(Role::Muted)) : QString())
                                   << (stale ? pill_html(QStringLiteral("⚠ cũ"), col(Role::Amber), 10) : QString()) + QStringLiteral(" ") + tier_html(str(t, "b"))
                                   << esc(str(t, "title").isEmpty() ? str(t, "analyst") : str(t, "title")));
        }
        body->addWidget(db_grid(sec, QStringList() << QStringLiteral("Nguồn") << QStringLiteral("TP") << QStringLiteral("KN") << QStringLiteral("Ngày") << QStringLiteral("Cờ") << QStringLiteral("Ghi chú"),
                                rows, QList<int>() << 2 << 1 << 1 << 2 << 1 << 5));
    } else {
        body->addWidget(make_need(sec, QStringLiteral("không có TP sell-side nào trên đĩa cho mã này")));
    }
    body->addWidget(db_collapsible(sec, QStringLiteral("§6 Định giá — diễn giải (memo, nguyên văn)"), str(dg, "memo_html"), false));
    return sec;
}

// ── §4 Filing teardown ───────────────────────────────────────────────────────

QWidget* build_filing(const QJsonObject& fl, QWidget* parent) {
    QVBoxLayout* body = nullptr;
    QWidget* sec = make_section(parent, QStringLiteral("§4"), QStringLiteral("FILING TEARDOWN 🔬 — đọc tài liệu gốc"),
                                QStringLiteral("MOAT 1 của DeepFA: thuyết minh BCTC, tờ trình ĐHCĐ, BC quản trị. Chỉ tin governance/cash-to-parent/dilution khi engine claude-deep."), body);
    const QJsonObject ws = fl.value(QLatin1String("worksheet")).toObject();
    const QJsonObject inv = fl.value(QLatin1String("inventory")).toObject();
    // badge line
    QStringList badge;
    if (ws.value(QLatin1String("co")).toBool()) {
        const QString eng = str(ws, "engine");
        badge << pill_html(QStringLiteral("engine %1").arg(eng.isEmpty() ? QStringLiteral("?") : eng), eng == QLatin1String("claude-deep") ? col(Role::Up) : col(Role::Amber), 10);
        badge << span(esc(QStringLiteral("worksheet %1 · đã đọc %2 filing thật").arg(str(ws, "as_of"), QString::number(ws.value(QLatin1String("n_read")).toInt()))), col(Role::Ink2));
        const QJsonValue conf = ws.value(QLatin1String("confidence"));
        if (conf.isDouble())
            badge << span(esc(QStringLiteral("confidence %1 %2").arg(QString::number(conf.toDouble(), 'f', 1), str(ws, "confidence_level"))), col(Role::Muted));
    } else {
        badge << pill_html(QStringLiteral("chưa có worksheet"), col(Role::Down), 10) + QStringLiteral(" ") + span(esc(str(ws, "ly_do")), col(Role::Muted));
    }
    if (fl.value(QLatin1String("moi_hon_worksheet")).toBool())
        badge << pill_html(QStringLiteral("⚠ có filing BCTC mới hơn worksheet — cần regen"), col(Role::Amber), 10);
    body->addWidget(db_rich(sec, col(Role::Ink), 12, badge.join(QStringLiteral(" &nbsp; "))));

    if (ws.value(QLatin1String("co")).toBool()) {
        if (!str(ws, "summary_html").isEmpty())
            body->addWidget(db_rich(sec, col(Role::Ink), 13, str(ws, "summary_html")));
        // 10 groups in two columns
        auto* gridw = new QWidget(sec);
        auto* grid = new QGridLayout(gridw);
        grid->setContentsMargins(0, 0, 0, 0);
        grid->setHorizontalSpacing(8);
        grid->setVerticalSpacing(8);
        int i = 0;
        for (const QJsonValue& v : ws.value(QLatin1String("groups")).toArray()) {
            const QJsonObject g = v.toObject();
            QVBoxLayout* lay = nullptr;
            QFrame* card = make_card(gridw, lay, g.value(QLatin1String("need")).toBool() ? col(Role::Amber) : tier_color(str(g, "tier")));
            QString head = span(esc(str(g, "label")), col(Role::Ink), true) + QStringLiteral(" ") + tier_html(str(g, "tier"));
            if (g.value(QLatin1String("gated")).toBool())
                head += QStringLiteral(" ") + pill_html(QStringLiteral("chỉ tham khảo"), col(Role::Amber), 9);
            lay->addWidget(db_rich(card, col(Role::Ink), 12, head));
            lay->addWidget(db_rich(card, col(Role::Ink2), 12, str(g, "html")));
            if (!str(g, "g").isEmpty())
                lay->addWidget(db_rich(card, col(Role::Muted), 10, esc(str(g, "g"))));
            grid->addWidget(card, i / 2, i % 2);
            ++i;
        }
        grid->setColumnStretch(0, 1);
        grid->setColumnStretch(1, 1);
        body->addWidget(gridw);
        // read list
        const QJsonArray rl = ws.value(QLatin1String("read_list")).toArray();
        if (!rl.isEmpty()) {
            body->addWidget(db_plain(sec, col(Role::Ink2), 12, QStringLiteral("Filing đã đọc (tag doc·kỳ)"), true));
            for (const QJsonValue& v : rl) {
                const QJsonObject r = v.toObject();
                auto* row = new QWidget(sec);
                auto* hl = new QHBoxLayout(row);
                hl->setContentsMargins(0, 0, 0, 0);
                hl->setSpacing(8);
                const bool exists = r.value(QLatin1String("exists")).toBool();
                hl->addWidget(db_rich(row, col(Role::Ink), 12, pill_html(str(r, "tag"), col(Role::Blue), 10) + QStringLiteral(" ") + esc(str(r, "file")) + QStringLiteral(" ") +
                                                                   span(esc(str(r, "status") + QStringLiteral(" · ") + str(r, "method")), col(Role::Muted))),
                              1);
                auto* btn = new QPushButton(exists ? QStringLiteral("Mở PDF") : QStringLiteral("không có tệp"), row);
                btn->setEnabled(exists);
                btn->setFixedHeight(22);
                btn->setCursor(Qt::PointingHandCursor);
                const QString path = str(r, "path");
                QObject::connect(btn, &QPushButton::clicked, btn, [path]() {
                    if (QFileInfo::exists(path))
                        QDesktopServices::openUrl(QUrl::fromLocalFile(path));
                });
                hl->addWidget(btn, 0);
                body->addWidget(row);
            }
        }
        const QJsonArray gaps = ws.value(QLatin1String("doc_gaps")).toArray();
        if (!gaps.isEmpty()) {
            QStringList gl;
            for (const QJsonValue& v : gaps)
                gl << QStringLiteral("• ") + esc(v.toString());
            body->addWidget(db_rich(sec, col(Role::Amber), 11, span(esc(QStringLiteral("Doc gaps [CẦN BÁO CÁO GỐC] — không bịa: ")), col(Role::Amber), true) + QStringLiteral("<br>") + gl.join(QStringLiteral("<br>"))));
        }
    }
    // inventory
    if (inv.value(QLatin1String("n_filings")).isDouble()) {
        QStringList bt;
        const QJsonObject by = inv.value(QLatin1String("by_type")).toObject();
        const QJsonObject latest = inv.value(QLatin1String("latest")).toObject();
        for (const QString& k : by.keys())
            bt << QStringLiteral("%1 %2 (mới nhất %3)").arg(k, QString::number(by.value(k).toInt()), latest.value(k).toString(QStringLiteral("?")));
        body->addWidget(db_rich(sec, col(Role::Ink2), 11,
                                span(esc(QStringLiteral("Kho filing gốc: %1 tệp · ").arg(QString::number(inv.value(QLatin1String("n_filings")).toDouble(), 'f', 0))), col(Role::Muted)) +
                                    esc(bt.join(QStringLiteral(" · "))) + QStringLiteral(" ") + tier_html(str(inv, "b")) + QStringLiteral(" ") +
                                    span(esc(str(inv, "t") + QStringLiteral(" · năm thư mục = năm đăng, không phải kỳ")), col(Role::Muted))));
    }
    body->addWidget(db_collapsible(sec, QStringLiteral("§4 Filing teardown (memo, nguyên văn)"), str(fl, "memo_html"), false));
    return sec;
}

// ── §3 Codex · EDI · §5 Board ────────────────────────────────────────────────

QWidget* build_codex(const QJsonObject& cx, QWidget* parent) {
    QVBoxLayout* body = nullptr;
    QWidget* sec = make_section(parent, QStringLiteral("§3·§5"), QStringLiteral("CODEX 7 TẦNG · EDI LEADING · BOARD OF ENGINES"),
                                QStringLiteral("Module KHÔNG tính State mới — chỉ đặt State/EDI của memo cạnh EDI hôm nay."), body);
    const QJsonObject el = cx.value(QLatin1String("edi_live")).toObject();
    const QJsonObject em = cx.value(QLatin1String("edi_memo")).toObject();
    QStringList line;
    const QString st = str(cx, "state");
    line << span(esc(QStringLiteral("State memo: ")), col(Role::Muted)) + pill_html(st.isEmpty() ? QStringLiteral("—") : st, state_color(st), 11);
    line << span(esc(QStringLiteral("EDI hôm nay: ")), col(Role::Muted)) + span(esc(str(el, "txt") + QStringLiteral(" · ") + str(el, "stage")), el.value(QLatin1String("late")).toBool() ? col(Role::Amber) : col(Role::Ink), true) +
                QStringLiteral(" ") + span(esc(str(el, "t")), col(Role::Muted)) + QStringLiteral(" ") + tier_html(str(el, "b"));
    if (!em.isEmpty())
        line << span(esc(QStringLiteral("EDI lúc memo: ")), col(Role::Muted)) + esc(QStringLiteral("%1 · %2 (%3)").arg(QString::number(em.value(QLatin1String("score")).toInt()), str(em, "stage"), str(em, "t")));
    const QJsonValue doi = cx.value(QLatin1String("edi_doi"));
    if (doi.isBool())
        line << (doi.toBool() ? pill_html(QStringLiteral("stage EDI đã đổi so memo"), col(Role::Amber), 10) : span(esc(QStringLiteral("stage EDI không đổi")), col(Role::Muted)));
    body->addWidget(db_rich(sec, col(Role::Ink), 12, line.join(QStringLiteral(" &nbsp;·&nbsp; "))));
    const QJsonArray tl = cx.value(QLatin1String("timeline")).toArray();
    if (!tl.isEmpty()) {
        QStringList ts;
        for (const QJsonValue& v : tl) {
            const QJsonObject t = v.toObject();
            ts << esc(str(t, "d") + QStringLiteral(" ") + str(t, "t"));
        }
        body->addWidget(db_rich(sec, col(Role::Muted), 10, span(esc(QStringLiteral("EDI timeline: ")), col(Role::Muted)) + ts.join(QStringLiteral(" → "))));
    }
    const QJsonArray drv = el.value(QLatin1String("drivers")).toArray();
    if (!drv.isEmpty()) {
        QStringList ds;
        for (const QJsonValue& v : drv)
            ds << esc(v.toString());
        body->addWidget(db_rich(sec, col(Role::Muted), 10, span(esc(QStringLiteral("drivers: ")), col(Role::Muted)) + ds.join(QStringLiteral(" · "))));
    }
    body->addWidget(db_collapsible(sec, QStringLiteral("§3 Codex 7 tầng (memo, nguyên văn)"), str(cx, "memo_html"), false));
    body->addWidget(db_collapsible(sec, QStringLiteral("§5 Board of Engines — nơi bất đồng (memo, nguyên văn)"), str(cx, "board_html"), false));
    if (!str(cx, "engines_note").isEmpty())
        body->addWidget(db_plain(sec, col(Role::Muted), 10, str(cx, "engines_note")));
    return sec;
}

// ── Đồ thị tri thức ──────────────────────────────────────────────────────────

QWidget* build_kg(const QJsonObject& kg, QWidget* parent) {
    QVBoxLayout* body = nullptr;
    QWidget* sec = make_section(parent, QStringLiteral("KG"), QStringLiteral("ĐỒ THỊ TRI THỨC — láng giềng 1 bước"),
                                QStringLiteral("Chỉ mục nối các lớp lại với nhau; không phải nguồn sự thật. Mỗi nhóm mang mốc và bậc riêng; trùng lớp khác thì lấy nguồn gốc."), body);
    if (!kg.value(QLatin1String("co")).toBool()) {
        body->addWidget(make_need(sec, str(kg, "ly_do")));
        return sec;
    }
    body->addWidget(db_rich(sec, col(Role::Ink2), 11,
                            esc(QStringLiteral("built %1 · v%2 · bậc %3 · ").arg(str(kg, "built_at").left(16), str(kg, "version"), QString::number(kg.value(QLatin1String("degree")).toInt()))) +
                                QStringLiteral("<a href=\"%1\" style=\"color:%2\">graph viewer :8099</a>").arg(esc(str(kg, "viewer_url")), css(col(Role::Blue)))));
    auto* gridw = new QWidget(sec);
    auto* grid = new QGridLayout(gridw);
    grid->setContentsMargins(0, 0, 0, 0);
    grid->setHorizontalSpacing(8);
    grid->setVerticalSpacing(8);
    int i = 0;
    for (const QJsonValue& v : kg.value(QLatin1String("groups")).toArray()) {
        const QJsonObject g = v.toObject();
        QVBoxLayout* lay = nullptr;
        QFrame* card = make_card(gridw, lay, tier_color(str(g, "b")));
        const bool stale = g.value(QLatin1String("stale")).toBool();
        QString head = span(esc(str(g, "label")), col(Role::Ink), true) + QStringLiteral(" ") +
                       span(esc(QStringLiteral("%1 (%2 duy nhất)").arg(QString::number(g.value(QLatin1String("n")).toInt()), QString::number(g.value(QLatin1String("n_unique")).toInt()))), col(Role::Muted)) +
                       QStringLiteral(" ") + tier_html(str(g, "b"));
        if (!str(g, "t").isEmpty())
            head += QStringLiteral(" ") + span(esc(str(g, "t")), db_stale_color(stale));
        if (stale)
            head += QStringLiteral(" ") + pill_html(QStringLiteral("cũ"), col(Role::Down), 9);
        lay->addWidget(db_rich(card, col(Role::Ink), 12, head));
        QStringList items;
        for (const QJsonValue& iv : g.value(QLatin1String("items")).toArray()) {
            const QJsonObject it = iv.toObject();
            const QJsonObject x = it.value(QLatin1String("x")).toObject();
            QString extra;
            for (const QString& k : x.keys()) {
                const QJsonValue xv = x.value(k);
                if (k == QLatin1String("md_path") || k == QLatin1String("description"))
                    continue;
                extra += QStringLiteral(" %1=%2").arg(k, xv.isDouble() ? QString::number(xv.toDouble()) : xv.toString());
                if (extra.size() > 140)
                    break;
            }
            items << QStringLiteral("• ") + esc(str(it, "label")) + (str(it, "date").isEmpty() ? QString() : span(esc(QStringLiteral(" ") + str(it, "date")), col(Role::Muted))) +
                         span(esc(extra), col(Role::Muted));
        }
        lay->addWidget(db_rich(card, col(Role::Ink2), 11, items.join(QStringLiteral("<br>"))));
        grid->addWidget(card, i / 2, i % 2);
        ++i;
    }
    grid->setColumnStretch(0, 1);
    grid->setColumnStretch(1, 1);
    body->addWidget(gridw);
    const QJsonObject props = kg.value(QLatin1String("props")).toObject();
    if (!props.isEmpty()) {
        QStringList ps;
        for (const QString& k : props.keys()) {
            const QJsonValue pv = props.value(k);
            ps << esc(QStringLiteral("%1=%2").arg(k, pv.isDouble() ? QString::number(pv.toDouble()) : pv.toString()));
        }
        body->addWidget(db_rich(sec, col(Role::Muted), 10, span(esc(QStringLiteral("thuộc tính KG không có ở lớp khác (EST/SS-T3): ")), col(Role::Muted)) + ps.join(QStringLiteral(" · "))));
    }
    return sec;
}

// ── Ledger ───────────────────────────────────────────────────────────────────

QWidget* build_ledger(const QJsonObject& lg, QWidget* parent) {
    const QJsonObject honest = lg.value(QLatin1String("honest")).toObject();
    QVBoxLayout* body = nullptr;
    QWidget* sec = make_section(parent, QStringLiteral("LG"), QStringLiteral("LEDGER ALPHA SPINE — lệnh của hệ trên mã này"), str(honest, "note"), body);
    if (!str(honest, "uniform_negative").isEmpty())
        body->addWidget(db_rich(sec, col(Role::Amber), 11, esc(QStringLiteral("⚠ ") + str(honest, "uniform_negative"))));
    const QJsonArray calls = lg.value(QLatin1String("calls")).toArray();
    if (calls.isEmpty()) {
        body->addWidget(make_need(sec, QStringLiteral("hệ chưa có lệnh nào trên mã này")));
        return sec;
    }
    QList<QStringList> rows;
    for (const QJsonValue& v : calls) {
        const QJsonObject c = v.toObject();
        const QJsonValue alpha = c.value(QLatin1String("alpha"));
        rows << (QStringList() << esc(str(c, "open_date")) << esc(str(c, "signal")) << esc(QString::number(c.value(QLatin1String("entry_price")).toDouble(), 'f', 1))
                               << esc(QString::number(c.value(QLatin1String("cur_price")).toDouble(), 'f', 1))
                               << span(esc(alpha.isDouble() ? db_num(alpha.toDouble(), 1) + QStringLiteral("%") : db_kNeed), alpha.isDouble() ? (alpha.toDouble() >= 0 ? col(Role::Up) : col(Role::Down)) : col(Role::Muted), true)
                               << esc(str(c, "status") + QStringLiteral(" · ") + str(c, "last_mark")) << esc(str(c, "break_point")));
    }
    body->addWidget(db_grid(sec, QStringList() << QStringLiteral("Mở") << QStringLiteral("Tín hiệu") << QStringLiteral("Giá vào") << QStringLiteral("Giá nay") << QStringLiteral("Alpha vs VNI") << QStringLiteral("Trạng thái") << QStringLiteral("Điểm gãy (ledger)"),
                            rows, QList<int>() << 1 << 1 << 1 << 1 << 1 << 2 << 5));
    body->addWidget(db_plain(sec, col(Role::Muted), 10, QStringLiteral("benchmark: ") + str(honest, "benchmark") + QStringLiteral(" · alpha = ảnh chụp mark-to-market; không phải track record khi lệnh còn mở")));
    return sec;
}

// ── Phụ lục ──────────────────────────────────────────────────────────────────

QWidget* build_phu_luc(const QJsonObject& pl, const QJsonObject& meta, QWidget* parent) {
    QVBoxLayout* body = nullptr;
    QWidget* sec = make_section(parent, QStringLiteral("§8"), QStringLiteral("PHỤ LỤC — sự kiện sau memo · nguồn · rigor · regen"), QString(), body);
    // catalysts after memo
    const QJsonArray cat = pl.value(QLatin1String("catalyst")).toArray();
    if (!cat.isEmpty()) {
        body->addWidget(db_plain(sec, col(Role::Ink2), 12, QStringLiteral("Sự kiện (fft_tin, đã lọc UNVERIFIED) — %1 sau ngày memo").arg(QString::number(pl.value(QLatin1String("n_catalyst_sau_memo")).toInt())), true));
        QList<QStringList> rows;
        for (const QJsonValue& v : cat) {
            const QJsonObject e = v.toObject();
            rows << (QStringList() << esc(str(e, "ngay")) + (e.value(QLatin1String("sau_memo")).toBool() ? QStringLiteral(" ") + pill_html(QStringLiteral("sau memo"), col(Role::Blue), 9) : QString())
                                   << esc(str(e, "mo_ta")) << tier_html(str(e, "bac")) << esc(str(e, "nguon")));
        }
        body->addWidget(db_grid(sec, QStringList() << QStringLiteral("Ngày") << QStringLiteral("Sự kiện") << QStringLiteral("Bậc") << QStringLiteral("Nguồn"), rows, QList<int>() << 1 << 6 << 1 << 1));
    } else {
        body->addWidget(make_need(sec, QStringLiteral("fft_tin không có sự kiện cho mã này (ngoài vũ trụ VN30∪VN100∪VN200∪CHAEBOL hoặc chưa có)")));
    }
    // news after memo
    const QJsonArray news = pl.value(QLatin1String("tin_sau_memo")).toArray();
    if (!news.isEmpty()) {
        QStringList nl;
        for (const QJsonValue& v : news) {
            const QJsonObject n = v.toObject();
            const QString sent = str(n, "sentiment").toLower();
            const QColor sc = sent.startsWith(QLatin1String("pos")) ? col(Role::Up) : (sent.startsWith(QLatin1String("neg")) ? col(Role::Down) : col(Role::Muted));
            nl << esc(str(n, "date")) + QStringLiteral(" ") + span(esc(str(n, "sentiment")), sc) + QStringLiteral(" ") + esc(str(n, "title")) +
                      (n.value(QLatin1String("sau_memo")).toBool() ? QStringLiteral(" ") + pill_html(QStringLiteral("sau memo"), col(Role::Blue), 9) : QString());
        }
        body->addWidget(db_rich(sec, col(Role::Ink2), 11, span(esc(QStringLiteral("AI-news Vietcap (EST, một nguồn): ")), col(Role::Muted)) + QStringLiteral("<br>") + nl.join(QStringLiteral("<br>"))));
    }
    // rigor
    const QJsonObject rg = pl.value(QLatin1String("rigor")).toObject();
    if (!rg.isEmpty()) {
        const QJsonObject marks = rg.value(QLatin1String("marks")).toObject();
        QStringList ms;
        for (const QString& k : marks.keys()) {
            const int m = marks.value(k).toInt();
            ms << span(esc(QStringLiteral("%1 %2/5").arg(k, QString::number(m))), m <= 2 ? col(Role::Down) : col(Role::Ink2));
        }
        body->addWidget(db_rich(sec, col(Role::Ink2), 11, span(esc(QStringLiteral("Rigor 6D (proxy) TB %1: ").arg(QString::number(rg.value(QLatin1String("avg")).toDouble(), 'f', 1))), col(Role::Muted), true) +
                                                                ms.join(QStringLiteral(" · ")) + QStringLiteral("<br>") + span(esc(str(rg, "g")), col(Role::Muted))));
    }
    // sources freshness table
    const QJsonArray src = pl.value(QLatin1String("nguon")).toArray();
    if (!src.isEmpty()) {
        body->addWidget(db_plain(sec, col(Role::Ink2), 12, QStringLiteral("Nguồn đã dùng — tuổi và bậc hiệu lực"), true));
        QList<QStringList> rows;
        for (const QJsonValue& v : src) {
            const QJsonObject l = v.toObject();
            const QString st = str(l, "status");
            rows << (QStringList() << esc(str(l, "light") + QStringLiteral(" ") + str(l, "label")) << esc(str(l, "as_of_txt") + QStringLiteral(" · ") + str(l, "age_txt"))
                                   << tier_html(str(l, "tier")) + QStringLiteral("→") + tier_html(str(l, "tier_hieu_luc")) << span(esc(st), status_color(st)));
        }
        body->addWidget(db_grid(sec, QStringList() << QStringLiteral("Lớp") << QStringLiteral("Mốc") << QStringLiteral("Bậc gốc → hiệu lực") << QStringLiteral("Trạng thái"), rows, QList<int>() << 5 << 3 << 2 << 1));
    }
    const QJsonArray rgaps = pl.value(QLatin1String("registry_gaps")).toArray();
    if (!rgaps.isEmpty()) {
        QStringList gl;
        for (const QJsonValue& v : rgaps)
            gl << QStringLiteral("• ") + esc(v.toString());
        body->addWidget(db_rich(sec, col(Role::Muted), 10, span(esc(QStringLiteral("Sổ nguồn còn thiếu: ")), col(Role::Muted), true) + QStringLiteral("<br>") + gl.join(QStringLiteral("<br>"))));
    }
    const QJsonObject regen = meta.value(QLatin1String("regen")).toObject();
    if (regen.value(QLatin1String("can")).toBool()) {
        QStringList why;
        for (const QJsonValue& v : regen.value(QLatin1String("ly_do")).toArray())
            why << v.toString();
        body->addWidget(db_rich(sec, col(Role::Amber), 11, span(esc(QStringLiteral("↻ Cần regen: ") + why.join(QStringLiteral("; "))), col(Role::Amber), true) + QStringLiteral("<br>") +
                                                                 span(esc(str(regen, "lenh")), col(Role::Muted))));
    }
    body->addWidget(db_collapsible(sec, QStringLiteral("§8 Appendix (memo, nguyên văn)"), str(pl, "memo_html"), false));
    body->addWidget(db_plain(sec, col(Role::Muted), 10, QStringLiteral("Tham khảo, tự thẩm định. Không phải khuyến nghị mua/bán. Sell-side −1 conviction.")));
    return sec;
}

} // namespace fincept::screens::deepfa
