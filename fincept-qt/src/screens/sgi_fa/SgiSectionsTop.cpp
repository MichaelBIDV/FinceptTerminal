// src/screens/sgi_fa/SgiSectionsTop.cpp
// Top half of the SGI FA page: CỔNG strip · VERDICT · I chu kỳ · II cỗ máy · III điều kiện đáy ·
// IV tám khối · đối chiếu HHP. Engine values arrive pre-formatted from scripts/sgi_fa.py; the few raw
// issue numbers shown here (cash %, the 4-phase table, block scores) are formatted the Vietnamese way
// (decimal comma, U+2212 minus). Missing slices render a muted "[CẦN DATA] …" line so gaps stay
// visible, and every data string is escaped before it reaches a rich-text QLabel.
#include "screens/sgi_fa/SgiCommon.h"
#include "screens/sgi_fa/SgiSections.h"

#include <QDate>
#include <QFrame>
#include <QGridLayout>
#include <QHBoxLayout>
#include <QHash>
#include <QJsonArray>
#include <QJsonObject>
#include <QLabel>
#include <QRegularExpression>
#include <QStringList>
#include <QVBoxLayout>

#include <algorithm>
#include <cmath>

namespace fincept::screens::sgi {

namespace {

// Private helpers carry the "top_" prefix: the unity build may merge this TU with SgiSectionsBottom.cpp.

const QString top_kNeed = QStringLiteral("[CẦN DATA]");

// ── Formatting ───────────────────────────────────────────────────────────────

/// Vietnamese number: decimal comma, thousands dot, U+2212 minus, optional explicit "+".
QString top_num(double v, int max_dec = 2, bool plus = false) {
    if (!std::isfinite(v))
        return {};
    QString s = QString::number(std::abs(v), 'f', max_dec);
    if (s.contains(QLatin1Char('.'))) {
        while (s.endsWith(QLatin1Char('0')))
            s.chop(1);
        if (s.endsWith(QLatin1Char('.')))
            s.chop(1);
    }
    const qsizetype dot = s.indexOf(QLatin1Char('.'));
    QString ip = dot < 0 ? s : s.left(dot);
    const QString fp = dot < 0 ? QString() : s.mid(dot + 1);
    for (qsizetype i = ip.size() - 3; i > 0; i -= 3)
        ip.insert(i, QLatin1Char('.'));
    QString out = fp.isEmpty() ? ip : ip + QLatin1Char(',') + fp;
    if (out == QLatin1String("0"))
        return out;
    if (v < 0)
        out.prepend(QChar(0x2212));
    else if (plus)
        out.prepend(QLatin1Char('+'));
    return out;
}

/// Number or string value of `key` as display text; absent / null → empty.
QString top_val(const QJsonObject& o, const char* key, int max_dec = 2, bool plus = false) {
    const QJsonValue v = o.value(QLatin1String(key));
    if (v.isDouble())
        return top_num(v.toDouble(), max_dec, plus);
    if (v.isString())
        return v.toString().trimmed();
    return {};
}

QString top_or_need(const QString& s) {
    return s.trimmed().isEmpty() ? top_kNeed : s;
}

/// "2026-09-14" → "14/09"; anything unparsable passes through.
QString top_ddmm(const QString& iso) {
    const QDate d = QDate::fromString(iso.left(10), Qt::ISODate);
    return d.isValid() ? d.toString(QStringLiteral("dd/MM")) : iso;
}

/// Block id → circled digit (① … ⑳).
QString top_circled(int id) {
    if (id >= 1 && id <= 20)
        return QString(QChar(0x2460 + id - 1));
    return QStringLiteral("(%1)").arg(id);
}

/// Mono span around already-escaped html. Single-quoted style: the font CSS carries double quotes.
QString top_mono(const QString& html, int px, const QColor& c, int weight = 500) {
    return QStringLiteral("<span style='color:%1; %2'>%3</span>").arg(css(c), mono_css(px, weight), html);
}

QString top_small(const QString& html, int px, const QColor& c, bool bold = false) {
    return QStringLiteral("<span style='color:%1; font-size:%2px;%3'>%4</span>")
        .arg(css(c), QString::number(px), bold ? QStringLiteral(" font-weight:600;") : QString(), html);
}

/// ▲ = up, ▼ = down, anything else muted.
QColor top_delta_color(const QString& d) {
    if (d.startsWith(QChar(0x25B2)))
        return col(Role::Up);
    if (d.startsWith(QChar(0x25BC)))
        return col(Role::Down);
    return col(Role::Muted);
}

// ── Widgets ──────────────────────────────────────────────────────────────────

QLabel* top_plain(QWidget* parent, const QColor& c, int px, const QString& text, bool bold = false,
                  bool mono = false) {
    auto* l = make_label(parent, c, px, Qt::PlainText, bold, mono);
    l->setText(text);
    return l;
}

QLabel* top_rich(QWidget* parent, const QColor& c, int px, const QString& html, bool bold = false,
                 bool mono = false) {
    auto* l = make_label(parent, c, px, Qt::RichText, bold, mono);
    l->setText(html);
    return l;
}

/// Muted "[CẦN DATA] what" line.
QLabel* top_need(QWidget* parent, const QString& what) {
    return top_plain(parent, col(Role::Muted), 12, top_kNeed + QStringLiteral(" ") + what);
}

/// Small uppercase caption above a value (artifact .eyebrow).
QLabel* top_eyebrow(QWidget* parent, const QString& text) {
    auto* l = top_plain(parent, col(Role::Muted), 11, text.toUpper(), true);
    l->setWordWrap(false);
    return l;
}

/// Note card (artifact .note): coloured left edge, bold title, body paragraph; empty body → [CẦN DATA].
QFrame* top_note(QWidget* parent, const QColor& accent, const QString& title, const QString& body) {
    QVBoxLayout* lay = nullptr;
    QFrame* card = make_card(parent, lay, accent);
    lay->addWidget(top_plain(card, col(Role::Ink), 13, title, true));
    if (body.trimmed().isEmpty())
        lay->addWidget(top_need(card, QStringLiteral("bản tuần chưa ghi mục này")));
    else
        lay->addWidget(top_plain(card, col(Role::Ink2), 13, body));
    lay->addStretch(1);
    return card;
}

/// Thin horizontal rule in the Line colour.
QFrame* top_rule(QWidget* parent) {
    auto* r = new QFrame(parent);
    r->setFixedHeight(1);
    r->setStyleSheet(QStringLiteral("QFrame { background:%1; border:none; }").arg(css(col(Role::Line))));
    return r;
}

QGridLayout* top_grid(QVBoxLayout* body, int cols, int spacing = 12) {
    auto* g = new QGridLayout;
    g->setContentsMargins(0, 0, 0, 0);
    g->setHorizontalSpacing(spacing);
    g->setVerticalSpacing(spacing);
    for (int c = 0; c < cols; ++c)
        g->setColumnStretch(c, 1);
    body->addLayout(g);
    return g;
}

// ── VERDICT pieces ───────────────────────────────────────────────────────────

/// Column cell with the artifact's 1px left rule (.vcell).
QWidget* top_vcell(QWidget* parent, QVBoxLayout*& lay, bool rule_left) {
    auto* w = new QWidget(parent);
    w->setObjectName(QStringLiteral("sgiVCell"));
    w->setAttribute(Qt::WA_StyledBackground, true);
    w->setStyleSheet(QStringLiteral("QWidget#sgiVCell { background:transparent; %1 }")
                         .arg(rule_left ? QStringLiteral("border-left:1px solid %1;").arg(css(col(Role::Line)))
                                        : QString()));
    lay = new QVBoxLayout(w);
    lay->setContentsMargins(rule_left ? 18 : 0, 0, 0, 0);
    lay->setSpacing(4);
    return w;
}

QWidget* top_verdict_regime(const QJsonObject& verdict, const QJsonObject& engine, const QString& regime,
                            QWidget* parent) {
    QVBoxLayout* lay = nullptr;
    QWidget* cell = top_vcell(parent, lay, false);
    lay->addWidget(top_eyebrow(cell, QStringLiteral("Chế độ")));

    auto* word = new QLabel(cell);
    word->setTextFormat(Qt::PlainText);
    word->setText(regime);
    word->setWordWrap(true);
    word->setStyleSheet(QStringLiteral("QLabel { color:%1; %2 background:transparent; }")
                            .arg(css(regime_color(regime)), lk::lk_font_css(lk::lk_font_serif(44, 600))));
    lay->addWidget(word);

    const QString chot = str(verdict, "chot");
    if (chot.isEmpty())
        lay->addWidget(top_need(cell, QStringLiteral("bản tuần chưa có câu chốt")));
    else
        lay->addWidget(top_plain(cell, col(Role::Ink), 15, chot));
    const QString ghi = str(verdict, "ghi_chu");
    if (!ghi.isEmpty())
        lay->addWidget(top_plain(cell, col(Role::Muted), 12, ghi));

    // Engine disagreement stays visible next to the issue's own regime word.
    const QJsonObject cd = engine.value(QStringLiteral("che_do")).toObject();
    const QString eng = str(cd, "ten");
    if (!eng.isEmpty() && engine.contains(QStringLiteral("khop")) && !engine.value(QStringLiteral("khop")).toBool(true)) {
        QString t = QStringLiteral("Engine §7 cho %1").arg(eng);
        if (!str(cd, "dai_txt").isEmpty())
            t += QStringLiteral(" (%1)").arg(str(cd, "dai_txt"));
        lay->addWidget(top_plain(cell, col(Role::Amber), 12, QStringLiteral("⚠ ") + t + QStringLiteral(" — không khớp bản tuần"),
                                 true));
    }
    lay->addStretch(1);
    return cell;
}

QWidget* top_verdict_action(const QJsonObject& verdict, const QJsonObject& engine, QWidget* parent) {
    QVBoxLayout* lay = nullptr;
    QWidget* cell = top_vcell(parent, lay, true);
    lay->addWidget(top_eyebrow(cell, QStringLiteral("Hành động chính")));

    const QJsonObject hd = verdict.value(QStringLiteral("hanh_dong")).toObject();
    const QString tieu_de = str(hd, "tieu_de");
    auto* big = top_plain(cell, col(tieu_de.isEmpty() ? Role::Muted : Role::Ink), tieu_de.isEmpty() ? 16 : 34,
                          top_or_need(tieu_de), false, true);
    lay->addWidget(big);
    const QString mo_ta = str(hd, "mo_ta");
    if (!mo_ta.isEmpty())
        lay->addWidget(top_plain(cell, col(Role::Down), 13, mo_ta, true));

    const QJsonObject tm = verdict.value(QStringLiteral("tien_mat")).toObject();
    const auto pct = [](const QString& v) { return v.isEmpty() ? top_kNeed : v + QStringLiteral("%"); };
    const QString ink = css(col(Role::Ink));
    const QString san = top_val(verdict, "san_co_phieu");
    const QString line =
        QStringLiteral("Tiền mặt %1 → <b style='color:%2'>%3</b> · Cổ phiếu <b style='color:%2'>%4</b> NAV (sàn %5)")
            .arg(esc(pct(top_val(tm, "hien_tai"))), ink, esc(pct(top_val(tm, "de_xuat"))),
                 esc(pct(top_val(verdict, "co_phieu"))), esc(pct(san)));
    auto* cash = top_rich(cell, col(Role::Ink2), 13, line);
    cash->setContentsMargins(0, 6, 0, 0);
    lay->addWidget(cash);

    // Regime cash band from the engine, and how far the proposal sits from it.
    const QJsonObject cd = engine.value(QStringLiteral("che_do")).toObject();
    const QString dai = str(cd, "dai_txt");
    if (!dai.isEmpty()) {
        QString band = esc(QStringLiteral("Khoảng tiền mặt §7 (%1): %2").arg(str(cd, "ten"), dai));
        const QJsonObject etm = engine.value(QStringLiteral("tien_mat")).toObject();
        if (etm.contains(QStringLiteral("trong_dai")) && !etm.value(QStringLiteral("trong_dai")).toBool(true) &&
            !str(etm, "lech_txt").isEmpty())
            band += QStringLiteral(" · ") + span(esc(str(etm, "lech_txt")), col(Role::Amber), true);
        lay->addWidget(top_rich(cell, col(Role::Muted), 12, band));
    }
    lay->addStretch(1);
    return cell;
}

/// One "name ……… value / bound ▲Δ" row of the score column (artifact .scorerow).
QWidget* top_score_row(QWidget* parent, const QString& name_html, const QString& value_html, bool top_rule) {
    auto* row = new QWidget(parent);
    row->setObjectName(QStringLiteral("sgiScoreRow"));
    row->setAttribute(Qt::WA_StyledBackground, true);
    row->setStyleSheet(QStringLiteral("QWidget#sgiScoreRow { background:transparent; %1 }")
                           .arg(top_rule ? QStringLiteral("border-top:1px solid %1;").arg(css(col(Role::Line2)))
                                         : QStringLiteral("border-bottom:1px dotted %1;").arg(css(col(Role::Line)))));
    auto* hl = new QHBoxLayout(row);
    hl->setContentsMargins(0, top_rule ? 7 : 4, 0, 4);
    hl->setSpacing(10);
    auto* name = top_rich(row, col(Role::Ink), 13, name_html, top_rule);
    auto* val = top_rich(row, col(Role::Ink), 13, value_html);
    val->setWordWrap(false);
    val->setAlignment(Qt::AlignRight | Qt::AlignVCenter);
    hl->addWidget(name, 1);
    hl->addWidget(val, 0);
    return row;
}

QWidget* top_verdict_scores(const QJsonObject& engine, QWidget* parent) {
    QVBoxLayout* lay = nullptr;
    QWidget* cell = top_vcell(parent, lay, true);
    lay->setSpacing(0);
    auto* eb = top_eyebrow(cell, QStringLiteral("Điểm thành phần"));
    eb->setContentsMargins(0, 0, 0, 5);
    lay->addWidget(eb);

    const QJsonArray to_hop = engine.value(QStringLiteral("to_hop")).toArray();
    if (to_hop.isEmpty())
        lay->addWidget(top_need(cell, QStringLiteral("engine §7 chưa tính điểm tổ hợp")));
    for (const QJsonValue& v : to_hop) {
        const QJsonObject t = v.toObject();
        QString name = esc(str(t, "ten"));
        if (t.value(QStringLiteral("mo_rong")).toBool())
            name += QStringLiteral(" ") + pill_html(QStringLiteral("mở rộng"), col(Role::Violet), 10);
        const QString gt = str(t, "gia_tri_txt");
        QString value;
        if (gt.isEmpty())
            value = top_mono(esc(top_kNeed), 12, col(Role::Muted));
        else
            value = top_mono(esc(gt + QStringLiteral(" / ") + str(t, "bien_txt")), 13, light_color(str(t, "mau")));
        const QString d = str(t, "delta_txt");
        if (!d.isEmpty())
            value += QStringLiteral(" ") + top_small(esc(d), 11, top_delta_color(d), true);
        lay->addWidget(top_score_row(cell, name, value, false));
    }

    const QJsonObject day = engine.value(QStringLiteral("day")).toObject();
    QString dv;
    if (str(day, "txt").isEmpty()) {
        dv = top_mono(esc(top_kNeed), 12, col(Role::Muted));
    } else {
        const int dat = day.value(QStringLiteral("dat")).toInt();
        const QColor c = dat >= 3 ? col(Role::Up) : (dat == 2 ? col(Role::Amber) : col(Role::Down));
        dv = top_mono(esc(str(day, "txt")), 13, c, 600);
        if (day.contains(QStringLiteral("nhat_quan")) && !day.value(QStringLiteral("nhat_quan")).toBool(true) &&
            !str(day, "ban_tuan_ghi").isEmpty())
            dv += QStringLiteral("<br>") +
                  top_small(esc(QStringLiteral("bản tuần ghi %1").arg(str(day, "ban_tuan_ghi"))), 11, col(Role::Amber));
    }
    lay->addWidget(top_score_row(cell, esc(QStringLiteral("Điều kiện đáy")), dv, true));
    lay->addStretch(1);
    return cell;
}

/// Engine §7 audit lines (✓ / ⚠) and the override list under the three columns.
void top_verdict_audit(const QJsonObject& engine, QWidget* card, QVBoxLayout* lay) {
    lay->addWidget(top_eyebrow(card, QStringLiteral("Kiểm engine §7")));
    const QJsonArray kiem = engine.value(QStringLiteral("kiem")).toArray();
    if (kiem.isEmpty())
        lay->addWidget(top_need(card, QStringLiteral("engine §7 chưa chạy — cần bản tuần hợp lệ")));
    for (const QJsonValue& v : kiem) {
        const QJsonObject k = v.toObject();
        QString icon = span(QStringLiteral("•"), col(Role::Muted), true);
        if (k.value(QStringLiteral("ok")).isBool())
            icon = k.value(QStringLiteral("ok")).toBool() ? span(QStringLiteral("✓"), col(Role::Up), true)
                                                          : span(QStringLiteral("⚠"), col(Role::Amber), true);
        QString html = icon + QStringLiteral("&nbsp; ");
        if (!str(k, "muc").isEmpty())
            html += QStringLiteral("<b>%1</b> — ").arg(esc(str(k, "muc")));
        html += esc(top_or_need(str(k, "text")));
        lay->addWidget(top_rich(card, col(Role::Ink2), 12, html));
    }

    const QJsonArray ov = engine.value(QStringLiteral("override")).toArray();
    if (ov.isEmpty())
        return;
    auto* eb = top_eyebrow(card, QStringLiteral("Override §7"));
    eb->setContentsMargins(0, 8, 0, 0);
    lay->addWidget(eb);
    QStringList khong;
    for (const QJsonValue& v : ov) {
        const QJsonObject o = v.toObject();
        const QString id = QStringLiteral("#") + top_val(o, "id");
        const QString tt = str(o, "trang_thai").trimmed();
        if (tt == QStringLiteral("KHÔNG")) {
            khong << id;
            continue;
        }
        const bool active = tt == QStringLiteral("KÍCH HOẠT");
        QString text = id + QStringLiteral(" ") + str(o, "ten");
        if (!str(o, "hieu_luc").isEmpty())
            text += QStringLiteral(" → ") + str(o, "hieu_luc");
        text += QStringLiteral(" · ") + top_or_need(tt);
        if (!str(o, "co_so").isEmpty())
            text += QStringLiteral(" · ") + str(o, "co_so");
        lay->addWidget(top_plain(card, col(active ? Role::Down : Role::Muted), 12, text, active));
    }
    if (!khong.isEmpty())
        lay->addWidget(top_plain(card, col(Role::Muted), 11,
                                 QStringLiteral("Không kích hoạt: ") + khong.join(QStringLiteral(" · "))));
}

// ── I · cycles pieces ────────────────────────────────────────────────────────

int top_year(const QJsonValue& v) {
    if (v.isDouble())
        return static_cast<int>(std::lround(v.toDouble()));
    return v.toString().trimmed().left(4).toInt();
}

/// 18,6-year phase name → colour (keyword match; unknown phases stay grey).
QColor top_phase_color(const QString& pha) {
    const QString p = pha.toLower();
    if (p.contains(QStringLiteral("khủng hoảng")))
        return col(Role::Down);
    if (p.contains(QStringLiteral("suy thoái")))
        return col(Role::Amber);
    if (p.contains(QStringLiteral("bong bóng")) || p.contains(QStringLiteral("đầu cơ")))
        return col(Role::Violet);
    if (p.contains(QStringLiteral("tăng trưởng")) || p.contains(QStringLiteral("phục hồi")) ||
        p.contains(QStringLiteral("mở rộng")))
        return col(Role::Up);
    return col(Role::Grey);
}

QFrame* top_four_phase_card(const QJsonObject& chu_ky, QWidget* parent) {
    QVBoxLayout* lay = nullptr;
    QFrame* card = make_card(parent, lay);
    lay->addWidget(top_eyebrow(card, QStringLiteral("Bốn pha thị trường")));

    const QJsonArray rows = chu_ky.value(QStringLiteral("bon_pha")).toArray();
    if (rows.isEmpty()) {
        lay->addWidget(top_need(card, QStringLiteral("bảng bốn pha")));
    } else {
        auto* g = new QGridLayout;
        g->setContentsMargins(0, 2, 0, 2);
        g->setHorizontalSpacing(14);
        g->setVerticalSpacing(4);
        g->setColumnStretch(0, 1);
        const QStringList heads = {QStringLiteral("Pha"), QStringLiteral("Tháng"), QStringLiteral("Tổng"),
                                   QStringLiteral("EPS"), QStringLiteral("P/E")};
        for (int c = 0; c < heads.size(); ++c) {
            auto* h = top_plain(card, col(Role::Muted), 11, heads.at(c).toUpper(), true);
            h->setWordWrap(false);
            g->addWidget(h, 0, c, c == 0 ? Qt::AlignLeft : Qt::AlignRight);
        }
        int r = 1;
        for (const QJsonValue& v : rows) {
            const QJsonObject o = v.toObject();
            const QString pha = str(o, "pha");
            // The Tuyệt vọng row carries the chart's point: nearly all of its loss is P/E, not EPS.
            const bool key_row = pha.trimmed().compare(QStringLiteral("Tuyệt vọng"), Qt::CaseInsensitive) == 0;
            g->addWidget(top_plain(card, col(Role::Ink), 13, top_or_need(pha)), r, 0);
            const auto cell = [&](const char* k, bool pct, bool bold) {
                QString t = top_val(o, k, 1, pct);
                const bool miss = t.isEmpty();
                if (!miss && pct)
                    t += QStringLiteral("%");
                auto* l = top_plain(card, col(miss ? Role::Muted : Role::Ink), miss ? 11 : 13, miss ? top_kNeed : t,
                                    bold, true);
                l->setWordWrap(false);
                return l;
            };
            g->addWidget(cell("thang", false, false), r, 1, Qt::AlignRight);
            g->addWidget(cell("tong", true, false), r, 2, Qt::AlignRight);
            g->addWidget(cell("eps", true, false), r, 3, Qt::AlignRight);
            g->addWidget(cell("pe", true, key_row), r, 4, Qt::AlignRight);
            ++r;
        }
        lay->addLayout(g);
    }
    const QString vt = str(chu_ky, "vi_tri_4pha");
    if (!vt.isEmpty())
        lay->addWidget(top_rich(card, col(Role::Ink2), 13,
                                QStringLiteral("<b style='color:%1'>Vị trí:</b> %2").arg(css(col(Role::Ink)), esc(vt))));
    lay->addStretch(1);
    return card;
}

QFrame* top_psychology_card(const QJsonObject& chu_ky, QWidget* parent) {
    QVBoxLayout* lay = nullptr;
    QFrame* card = make_card(parent, lay);
    lay->addWidget(top_eyebrow(card, QStringLiteral("Thang tâm lý")));

    const QJsonArray thang = chu_ky.value(QStringLiteral("thang_tam_ly")).toArray();
    const QString cur = str(chu_ky, "vi_tri_tam_ly").trimmed();
    if (thang.isEmpty()) {
        lay->addWidget(top_need(card, QStringLiteral("thang tâm lý")));
    } else {
        QStringList parts;
        bool found = false;
        for (const QJsonValue& v : thang) {
            const QString s = v.toString().trimmed();
            const bool here = !cur.isEmpty() && s.compare(cur, Qt::CaseInsensitive) == 0;
            found = found || here;
            parts << (here ? pill_html(s, col(Role::Down), 13) : pill_html(s, col(Role::Grey), 11));
        }
        auto* ladder = top_rich(card, col(Role::Ink2), 12, parts.join(span(QStringLiteral(" → "), col(Role::Muted))));
        ladder->setContentsMargins(0, 4, 0, 4);
        lay->addWidget(ladder);
        if (found)
            lay->addWidget(top_rich(card, col(Role::Ink2), 13,
                                    QStringLiteral("Hiện tại: ") + span(esc(cur), col(Role::Down), true)));
        else
            lay->addWidget(top_need(card, QStringLiteral("vị trí hiện tại trên thang")));
    }
    const QString ng = str(chu_ky, "nguong_tam_ly");
    if (!ng.isEmpty())
        lay->addWidget(top_rich(card, col(Role::Ink2), 12,
                                QStringLiteral("<b style='color:%1'>Ngưỡng kích hoạt:</b> %2").arg(css(col(Role::Ink)), esc(ng))));
    lay->addStretch(1);
    return card;
}

/// Index of the current 18,6-year segment: the phase named EARLIEST in vi_tri_18_6 (the text may name
/// other phases further on, e.g. "…còn 49 tháng Tăng trưởng phía trước"), else the year it mentions,
/// else today's year. Segment years are inclusive ("2020–2022"). -1 when nothing matches.
int top_current_segment(const QJsonArray& segs, const QString& vi_tri) {
    const QString vt = vi_tri.toLower();
    int best = -1;
    qsizetype best_pos = -1;
    for (int i = 0; i < segs.size(); ++i) {
        const QString pha = str(segs.at(i).toObject(), "pha").trimmed().toLower();
        const qsizetype pos = pha.isEmpty() ? -1 : vt.indexOf(pha);
        if (pos >= 0 && (best_pos < 0 || pos < best_pos)) {
            best = i;
            best_pos = pos;
        }
    }
    if (best >= 0)
        return best;
    static const QRegularExpression kYear(QStringLiteral("\\b(19|20)\\d{2}\\b"));
    const QRegularExpressionMatch m = kYear.match(vi_tri);
    const int year = m.hasMatch() ? m.captured(0).toInt() : QDate::currentDate().year();
    for (int i = 0; i < segs.size(); ++i) {
        const QJsonObject o = segs.at(i).toObject();
        const int tu = top_year(o.value(QStringLiteral("tu")));
        const int den = top_year(o.value(QStringLiteral("den")));
        if (tu > 0 && year >= tu && year <= std::max(tu, den))
            return i;
    }
    return -1;
}

QFrame* top_map_card(const QJsonObject& chu_ky, QWidget* parent) {
    QVBoxLayout* lay = nullptr;
    QFrame* card = make_card(parent, lay);
    lay->addWidget(top_eyebrow(card, QStringLiteral("Chu kỳ đất – tín dụng 18,6 năm")));

    QJsonArray segs = chu_ky.value(QStringLiteral("ban_do_18_6")).toArray();
    const QString vi_tri = str(chu_ky, "vi_tri_18_6");
    if (segs.isEmpty()) {
        lay->addWidget(top_need(card, QStringLiteral("bản đồ pha 18,6 năm")));
    } else {
        QList<QJsonValue> sorted(segs.begin(), segs.end());
        std::stable_sort(sorted.begin(), sorted.end(), [](const QJsonValue& a, const QJsonValue& b) {
            return top_year(a.toObject().value(QStringLiteral("tu"))) < top_year(b.toObject().value(QStringLiteral("tu")));
        });
        segs = QJsonArray();
        for (const QJsonValue& v : sorted)
            segs.append(v);
        const int cur = top_current_segment(segs, vi_tri);

        auto* bar = new QHBoxLayout;
        bar->setContentsMargins(0, 4, 0, 0);
        bar->setSpacing(2);
        auto* marks = new QHBoxLayout;
        marks->setContentsMargins(0, 0, 0, 0);
        marks->setSpacing(2);
        for (int i = 0; i < segs.size(); ++i) {
            const QJsonObject o = segs.at(i).toObject();
            const int tu = top_year(o.value(QStringLiteral("tu")));
            const int den = top_year(o.value(QStringLiteral("den")));
            const int stretch = std::max(1, den - tu + 1); // width ∝ duration in years (inclusive)
            const QString pha = str(o, "pha");
            const QColor pc = top_phase_color(pha);
            auto* seg = new QLabel(card);
            seg->setTextFormat(Qt::RichText);
            seg->setWordWrap(true);
            seg->setAlignment(Qt::AlignCenter);
            seg->setMinimumHeight(44);
            const QString y0 = tu > 0 ? QString::number(tu) : QStringLiteral("?");
            const QString y1 = den > 0 ? QString::number(den) : QStringLiteral("?");
            seg->setText(QStringLiteral("<b>%1</b><br>%2")
                             .arg(esc(top_or_need(pha).toUpper()),
                                  top_mono(esc(y0 == y1 ? y0 : QStringLiteral("%1–%2").arg(y0, y1)), 11, pc)));
            seg->setStyleSheet(QStringLiteral("QLabel { color:%1; background:%2; border:%3; border-radius:2px; %4 padding:4px; }")
                                   .arg(css(pc), css(soft_on_surface(pc, 0.22)),
                                        i == cur ? QStringLiteral("2px solid %1").arg(css(col(Role::Down)))
                                                 : QStringLiteral("1px solid transparent"),
                                        lk::lk_font_css(lk::lk_font_sans(11, 400))));
            bar->addWidget(seg, stretch);
            auto* mk = top_plain(card, col(Role::Down), 11, i == cur ? QStringLiteral("▲ đang ở đây") : QString(), true);
            mk->setAlignment(Qt::AlignHCenter | Qt::AlignTop);
            marks->addWidget(mk, stretch);
        }
        lay->addLayout(bar);
        lay->addLayout(marks);
        if (cur < 0)
            lay->addWidget(top_need(card, QStringLiteral("không xác định được pha hiện tại trên bản đồ")));
    }
    if (!vi_tri.isEmpty())
        lay->addWidget(top_rich(card, col(Role::Ink2), 13,
                                QStringLiteral("<b style='color:%1'>Vị trí:</b> %2").arg(css(col(Role::Ink)), esc(vi_tri))));
    return card;
}

QFrame* top_test_card(const QJsonObject& kd, QWidget* parent) {
    QVBoxLayout* lay = nullptr;
    QFrame* card = make_card(parent, lay, col(Role::Amber));
    lay->addWidget(top_plain(card, col(Role::Ink), 13, QStringLiteral("Kiểm định khung 4 pha trên dữ liệu thật"), true));
    if (kd.isEmpty()) {
        lay->addWidget(top_need(card, QStringLiteral("bản tuần chưa có kết quả kiểm định")));
        return card;
    }
    const QString kl = str(kd, "ket_luan");
    lay->addWidget(kl.isEmpty() ? static_cast<QWidget*>(top_need(card, QStringLiteral("kết luận kiểm định")))
                                : top_plain(card, col(Role::Ink), 13, kl));
    const QString fft = str(kd, "fft");
    if (!fft.isEmpty())
        lay->addWidget(top_rich(card, col(Role::Ink2), 12,
                                span(QStringLiteral("⚠ FFT:"), col(Role::Amber), true) + QStringLiteral(" ") + esc(fft)));
    const QString dr = str(kd, "do_rong");
    if (!dr.isEmpty())
        lay->addWidget(top_rich(card, col(Role::Ink2), 12,
                                QStringLiteral("<b style='color:%1'>Độ rộng:</b> %2").arg(css(col(Role::Ink)), esc(dr))));
    return card;
}

// ── II · machine pieces ──────────────────────────────────────────────────────

/// One numbered step of the vertical flow: circle + rail on the left, title/description on the right.
QWidget* top_flow_step(QWidget* parent, int n, const QJsonObject& step, bool last) {
    const bool hot = step.value(QStringLiteral("hien_tai")).toBool();
    auto* row = make_box(parent);
    auto* hl = new QHBoxLayout(row);
    hl->setContentsMargins(0, 0, 0, 0);
    hl->setSpacing(12);

    auto* rail = make_box(row);
    rail->setFixedWidth(26);
    auto* rl = new QVBoxLayout(rail);
    rl->setContentsMargins(0, 0, 0, 0);
    rl->setSpacing(0);
    auto* circle = new QLabel(QString::number(n), rail);
    circle->setFixedSize(24, 24);
    circle->setAlignment(Qt::AlignCenter);
    const QColor accent = hot ? col(Role::Down) : col(Role::Amber);
    circle->setStyleSheet(QStringLiteral("QLabel { color:%1; background:%2; border:2px solid %3; border-radius:12px; %4 }")
                              .arg(css(hot ? col(Role::Surface) : accent), css(hot ? accent : col(Role::Surface)),
                                   css(accent), lk::lk_font_css(lk::lk_font_mono(11, 600))));
    rl->addWidget(circle, 0, Qt::AlignHCenter);
    auto* line = new QFrame(rail);
    line->setFixedWidth(2);
    line->setStyleSheet(QStringLiteral("QFrame { background:%1; border:none; }")
                            .arg(last ? QStringLiteral("transparent") : css(col(Role::Line2))));
    rl->addWidget(line, 1, Qt::AlignHCenter);
    hl->addWidget(rail, 0);

    auto* text = make_box(row);
    auto* tl = new QVBoxLayout(text);
    tl->setContentsMargins(0, 2, 0, last ? 0 : 12); // bottom gap sits beside the rail so the line stays continuous
    tl->setSpacing(2);
    QString title = esc(top_or_need(str(step, "buoc")));
    if (hot)
        title += QStringLiteral("&nbsp; ") + pill_html(QStringLiteral("ĐANG Ở ĐÂY"), col(Role::Down), 10);
    tl->addWidget(top_rich(text, col(hot ? Role::Down : Role::Ink), 14, title, true));
    const QString mo_ta = str(step, "mo_ta");
    if (!mo_ta.isEmpty())
        tl->addWidget(top_plain(text, col(Role::Ink2), 12, mo_ta));
    hl->addWidget(text, 1);
    return row;
}

// ── IV · block pieces ────────────────────────────────────────────────────────

/// Five-cell gauge −2 … +2; the cell at the (rounded) score is filled in its sign colour.
QWidget* top_gauge(QWidget* parent, bool has_score, double score) {
    auto* w = make_box(parent);
    auto* hl = new QHBoxLayout(w);
    hl->setContentsMargins(0, 0, 0, 0);
    hl->setSpacing(2);
    const int idx = has_score ? static_cast<int>(std::clamp<long>(std::lround(score), -2, 2)) + 2 : -1;
    for (int i = 0; i < 5; ++i) {
        auto* cell = new QFrame(w);
        cell->setFixedSize(14, 8);
        QColor bg = col(Role::Surface2);
        if (i == idx)
            bg = score == 0.0 ? col(Role::Ink2) : sign_color(score);
        cell->setStyleSheet(QStringLiteral("QFrame { background:%1; border:1px solid %2; border-radius:1px; }")
                                .arg(css(bg), css(i == 2 ? col(Role::Line2) : col(Role::Line))));
        hl->addWidget(cell);
    }
    return w;
}

QFrame* top_block_card(const QJsonObject& blk, const QJsonObject& eng_blk, const QHash<QString, double>& he_so,
                       QWidget* parent) {
    // Score: engine pre-formatted text first, raw issue number as fallback.
    const QJsonValue dv = blk.contains(QStringLiteral("diem")) ? blk.value(QStringLiteral("diem"))
                                                               : eng_blk.value(QStringLiteral("diem"));
    const bool has = dv.isDouble();
    const double score = has ? dv.toDouble() : 0.0;
    QString score_txt = str(eng_blk, "diem_txt");
    if (score_txt.isEmpty() && has)
        score_txt = top_num(score, 1, true);
    const QColor edge = !has ? col(Role::Muted) : (score < 0 ? col(Role::Down) : (score > 0 ? col(Role::Up) : col(Role::Amber)));

    QVBoxLayout* lay = nullptr;
    QFrame* card = make_card(parent, lay, edge);

    auto* head = new QHBoxLayout;
    head->setContentsMargins(0, 0, 0, 0);
    head->setSpacing(10);
    auto* left = new QVBoxLayout;
    left->setSpacing(2);
    const int id = blk.contains(QStringLiteral("id")) ? blk.value(QStringLiteral("id")).toInt()
                                                      : eng_blk.value(QStringLiteral("id")).toInt();
    QString ten = str(blk, "ten");
    if (ten.isEmpty())
        ten = str(eng_blk, "ten");
    auto* title = new QLabel(card);
    title->setTextFormat(Qt::PlainText);
    title->setWordWrap(true);
    title->setText(top_circled(id) + QStringLiteral(" ") + top_or_need(ten));
    title->setStyleSheet(QStringLiteral("QLabel { color:%1; %2 background:transparent; }")
                             .arg(css(col(Role::Ink)), lk::lk_font_css(lk::lk_font_serif(15, 600))));
    left->addWidget(title);

    QString tag;
    const QString th = str(eng_blk, "to_hop");
    if (!th.isEmpty()) {
        const double k = he_so.value(th, 0.0);
        tag = top_mono(esc((k > 0.0 ? QStringLiteral("×") + top_num(k) + QStringLiteral(" ") : QString()) +
                           QStringLiteral("→ ") + th),
                       11, col(Role::Muted));
    }
    const bool mo_rong = blk.value(QStringLiteral("mo_rong")).toBool() || eng_blk.value(QStringLiteral("mo_rong")).toBool();
    if (mo_rong)
        tag += (tag.isEmpty() ? QString() : QStringLiteral("&nbsp; ")) +
               pill_html(QStringLiteral("mở rộng của bản tuần — không có trong SKILL §7"), col(Role::Violet), 10);
    if (!tag.isEmpty())
        left->addWidget(top_rich(card, col(Role::Muted), 11, tag));
    head->addLayout(left, 1);

    auto* right = new QVBoxLayout;
    right->setSpacing(4);
    auto* sc = top_plain(card, has ? sign_color(score) : col(Role::Muted), has ? 18 : 12, top_or_need(score_txt), true, true);
    sc->setWordWrap(false);
    sc->setAlignment(Qt::AlignRight | Qt::AlignVCenter);
    right->addWidget(sc, 0, Qt::AlignRight);
    right->addWidget(top_gauge(card, has, score), 0, Qt::AlignRight);
    head->addLayout(right, 0);
    lay->addLayout(head);

    // What moved this week (amber); without a stated change only the previous score, muted.
    const QString moved = str(blk, "doi_ky_nay").trimmed();
    const QJsonValue prev = blk.value(QStringLiteral("diem_truoc"));
    const QString prev_txt = prev.isDouble() ? QStringLiteral("kỳ trước ") + top_num(prev.toDouble(), 1, true) : QString();
    if (!moved.isEmpty())
        lay->addWidget(top_plain(card, col(Role::Amber), 12,
                                 QStringLiteral("Đổi kỳ này: ") + moved +
                                     (prev_txt.isEmpty() ? QString() : QStringLiteral(" · ") + prev_txt)));
    else if (!prev_txt.isEmpty())
        lay->addWidget(top_plain(card, col(Role::Muted), 12,
                                 prev_txt + (has && prev.toDouble() == score ? QStringLiteral(" · không đổi") : QString())));

    const QJsonArray den = blk.value(QStringLiteral("den")).toArray();
    if (den.isEmpty())
        lay->addWidget(top_need(card, QStringLiteral("khối này chưa có đèn")));
    for (const QJsonValue& v : den) {
        const QJsonObject d = v.toObject();
        auto* row = new QHBoxLayout;
        row->setContentsMargins(0, 0, 0, 0);
        row->setSpacing(7);
        auto* dot = top_plain(card, light_color(str(d, "mau")), 11, QStringLiteral("●"));
        dot->setWordWrap(false);
        row->addWidget(dot, 0, Qt::AlignTop);
        row->addWidget(top_plain(card, col(Role::Ink2), 12, top_or_need(str(d, "text"))), 1);
        lay->addLayout(row);
    }
    lay->addStretch(1);
    return card;
}

} // namespace

// ── CỔNG ─────────────────────────────────────────────────────────────────────

QWidget* build_gate(const QJsonObject& gate, QWidget* parent) {
    const QString gia = str(gate, "gia_tien").trimmed();
    QColor edge = col(Role::Muted);
    if (gia == QStringLiteral("tiền đắt"))
        edge = col(Role::Down);
    else if (gia == QStringLiteral("tiền rẻ"))
        edge = col(Role::Up);
    else if (!gia.isEmpty() && gia != top_kNeed)
        edge = col(Role::Amber);

    auto* strip = new QFrame(parent);
    strip->setObjectName(QStringLiteral("sgiGate"));
    strip->setAttribute(Qt::WA_StyledBackground, true);
    strip->setStyleSheet(QStringLiteral("QFrame#sgiGate { background:%1; border:1px solid %2; border-left:3px solid %3; "
                                        "border-radius:3px; }")
                             .arg(css(col(Role::Surface)), css(col(Role::AmberLine)), css(edge)));
    auto* hl = new QHBoxLayout(strip);
    hl->setContentsMargins(12, 8, 12, 8);

    QString text = str(gate, "text");
    if (text.isEmpty() && !gate.isEmpty())
        text = QStringLiteral("CỔNG: %1 · chủ thể %2 · playbook %3")
                   .arg(top_or_need(gia), top_or_need(str(gate, "chu_the")), top_or_need(str(gate, "playbook")));
    if (text.isEmpty())
        text = QStringLiteral("CỔNG: %1 — engine chưa chạy (thiếu bản tuần)").arg(top_kNeed);

    QString html = top_mono(esc(text), 12, col(Role::Ink), 600);
    const QString tier = tier_html(str(gate, "tier"));
    if (!tier.isEmpty())
        html += QStringLiteral("&nbsp; ") + tier;
    const QString co_so = str(gate, "co_so");
    if (!co_so.isEmpty())
        html += QStringLiteral("&nbsp; ") + top_small(esc(co_so), 11, col(Role::Muted));
    hl->addWidget(top_rich(strip, col(Role::Ink), 12, html), 1);
    return strip;
}

// ── VERDICT ──────────────────────────────────────────────────────────────────

QWidget* build_verdict(const QJsonObject& issue, const QJsonObject& engine, QWidget* parent) {
    const QJsonObject verdict = issue.value(QStringLiteral("verdict")).toObject();
    // The verdict is the issue's own call; the engine regime only fills in when no issue is loaded.
    QString regime = str(verdict, "che_do").trimmed();
    if (regime.isEmpty())
        regime = str(engine.value(QStringLiteral("che_do")).toObject(), "ten").trimmed();
    regime = top_or_need(regime);

    auto* card = new QFrame(parent);
    card->setObjectName(QStringLiteral("sgiVerdict"));
    card->setAttribute(Qt::WA_StyledBackground, true);
    card->setStyleSheet(QStringLiteral("QFrame#sgiVerdict { background:%1; border:1px solid %2; border-top:4px solid %3; "
                                       "border-radius:4px; }")
                            .arg(css(col(Role::Surface)), css(col(Role::Line)), css(regime_color(regime))));
    auto* lay = new QVBoxLayout(card);
    lay->setContentsMargins(22, 18, 22, 16);
    lay->setSpacing(6);

    if (issue.isEmpty())
        lay->addWidget(top_need(card, QStringLiteral("chưa có bản tuần — chế độ dưới đây là của engine, không phải bản tuần")));

    auto* grid = new QGridLayout;
    grid->setContentsMargins(0, 0, 0, 0);
    grid->setHorizontalSpacing(18);
    grid->addWidget(top_verdict_regime(verdict, engine, regime, card), 0, 0);
    grid->addWidget(top_verdict_action(verdict, engine, card), 0, 1);
    grid->addWidget(top_verdict_scores(engine, card), 0, 2);
    grid->setColumnStretch(0, 5);
    grid->setColumnStretch(1, 4);
    grid->setColumnStretch(2, 4);
    lay->addLayout(grid);

    lay->addSpacing(6);
    lay->addWidget(top_rule(card));
    lay->addSpacing(2);
    top_verdict_audit(engine, card, lay);
    return card;
}

// ── I · Ba khung chu kỳ ──────────────────────────────────────────────────────

QWidget* build_cycles(const QJsonObject& chu_ky, QWidget* parent) {
    QVBoxLayout* body = nullptr;
    QWidget* sec = make_section(parent, QStringLiteral("I"), QStringLiteral("Ba khung chu kỳ"), QString(), body);
    if (chu_ky.isEmpty()) {
        body->addWidget(top_need(sec, QStringLiteral("bản tuần chưa có mục chu kỳ")));
        return sec;
    }

    QGridLayout* g = top_grid(body, 2);
    g->addWidget(top_four_phase_card(chu_ky, sec), 0, 0);
    g->addWidget(top_psychology_card(chu_ky, sec), 0, 1);

    // The issue's own warning against using the 4-phase month counts: kept loud, directly under the table.
    const QString cb = str(chu_ky, "canh_bao_4pha");
    if (!cb.isEmpty()) {
        QVBoxLayout* cl = nullptr;
        QFrame* warn = make_card(sec, cl, col(Role::Amber));
        cl->addWidget(top_plain(warn, col(Role::Amber), 13, QStringLiteral("⚠ ") + cb, true));
        body->addWidget(warn);
    }

    body->addWidget(top_map_card(chu_ky, sec));
    body->addWidget(top_note(sec, col(Role::Down), QStringLiteral("Phân xử mâu thuẫn — khung nào có quyền quyết định"),
                             str(chu_ky, "phan_xu")));
    body->addWidget(top_test_card(chu_ky.value(QStringLiteral("kiem_dinh")).toObject(), sec));
    return sec;
}

// ── II · Cỗ máy Tiền ↔ Hàng ──────────────────────────────────────────────────

QWidget* build_machine(const QJsonObject& issue, QWidget* parent) {
    QVBoxLayout* body = nullptr;
    QWidget* sec = make_section(parent, QStringLiteral("II"), QStringLiteral("Cỗ máy Tiền ↔ Hàng"), QString(), body);

    const QJsonArray steps = issue.value(QStringLiteral("co_may")).toArray();
    if (steps.isEmpty()) {
        body->addWidget(top_need(sec, QStringLiteral("bản tuần chưa có chuỗi cỗ máy")));
    } else {
        QVBoxLayout* fl = nullptr;
        QFrame* flow = make_card(sec, fl);
        fl->setSpacing(0);
        bool any_hot = false;
        for (int i = 0; i < steps.size(); ++i) {
            const QJsonObject s = steps.at(i).toObject();
            any_hot = any_hot || s.value(QStringLiteral("hien_tai")).toBool();
            fl->addWidget(top_flow_step(flow, i + 1, s, i == steps.size() - 1));
        }
        if (!any_hot)
            fl->addWidget(top_need(flow, QStringLiteral("bản tuần không đánh dấu bước hiện tại")));
        body->addWidget(flow);
    }

    QGridLayout* g = top_grid(body, 2);
    g->addWidget(top_note(sec, col(Role::Amber), QStringLiteral("Thứ tự vỡ và độ trễ"), str(issue, "thu_tu_vo")), 0, 0);
    g->addWidget(top_note(sec, col(Role::Amber), QStringLiteral("Hệ số truyền dẫn"), str(issue, "he_so_truyen_dan")), 0, 1);
    return sec;
}

// ── III · Bốn điều kiện xác nhận đáy ─────────────────────────────────────────

QWidget* build_conditions(const QJsonArray& dieu_kien_day, const QJsonObject& engine_day, QWidget* parent) {
    QStringList lede;
    if (!str(engine_day, "txt").isEmpty())
        lede << QStringLiteral("Hiện tại %1.").arg(str(engine_day, "txt"));
    if (!str(engine_day, "luat").isEmpty())
        lede << str(engine_day, "luat");
    if (lede.isEmpty())
        lede << top_kNeed + QStringLiteral(" engine chưa đếm điều kiện đáy.");
    lede << QStringLiteral("§5 chỉ đếm ĐẠT; định giá rẻ không nằm trong bốn điều kiện.");

    QVBoxLayout* body = nullptr;
    QWidget* sec = make_section(parent, QStringLiteral("III"), QStringLiteral("Bốn điều kiện xác nhận đáy"),
                                lede.join(QStringLiteral(" ")), body);

    // The issue's printed count vs the engine's §5 count.
    if (engine_day.contains(QStringLiteral("nhat_quan")) && !engine_day.value(QStringLiteral("nhat_quan")).toBool(true)) {
        QString t = str(engine_day, "ghi_chu");
        if (t.isEmpty())
            t = QStringLiteral("Bản tuần ghi %1 nhưng engine đếm %2.")
                    .arg(top_or_need(str(engine_day, "ban_tuan_ghi")), top_or_need(str(engine_day, "txt")));
        QVBoxLayout* nl = nullptr;
        QFrame* note = make_card(sec, nl, col(Role::Amber));
        nl->addWidget(top_plain(note, col(Role::Amber), 13, QStringLiteral("⚠ ") + t, true));
        body->addWidget(note);
    }

    if (dieu_kien_day.isEmpty()) {
        body->addWidget(top_need(sec, QStringLiteral("bản tuần chưa có bốn điều kiện đáy")));
        return sec;
    }
    QGridLayout* g = top_grid(body, 4, 10);
    for (int i = 0; i < dieu_kien_day.size(); ++i) {
        const QJsonObject c = dieu_kien_day.at(i).toObject();
        const QString st = top_or_need(str(c, "trang_thai").trimmed());
        QVBoxLayout* cl = nullptr;
        QFrame* card = make_card(sec, cl, status_color(st));
        const int id = c.value(QStringLiteral("id")).isDouble() ? c.value(QStringLiteral("id")).toInt() : i + 1;
        cl->addWidget(top_plain(card, col(Role::Muted), 12, QStringLiteral("%1").arg(id, 2, 10, QLatin1Char('0')), false, true));
        cl->addWidget(top_plain(card, col(Role::Ink), 14, top_or_need(str(c, "ten")), true));
        cl->addWidget(top_rich(card, col(Role::Ink), 12, pill_html(st, status_color(st), 11)));
        const QString bc = str(c, "bang_chung");
        if (bc.isEmpty())
            cl->addWidget(top_need(card, QStringLiteral("bằng chứng")));
        else
            cl->addWidget(top_plain(card, col(Role::Ink2), 12, bc));
        const QString ket = str(c, "ket");
        if (!ket.isEmpty())
            cl->addWidget(top_plain(card, col(Role::Ink), 13, ket, true));
        cl->addStretch(1);
        g->addWidget(card, i / 4, i % 4);
    }
    return sec;
}

// ── IV · Tám khối chỉ báo ────────────────────────────────────────────────────

QWidget* build_blocks(const QJsonObject& issue, const QJsonObject& engine, QWidget* parent) {
    QVBoxLayout* body = nullptr;
    QWidget* sec = make_section(parent, QStringLiteral("IV"), QStringLiteral("Tám khối chỉ báo"), str(issue, "khoi_ghi_chu"),
                                body);

    // Engine rows by block id, composite weights by composite name.
    QHash<int, QJsonObject> eng_by_id;
    const QJsonArray ek = engine.value(QStringLiteral("khoi")).toArray();
    for (const QJsonValue& v : ek)
        eng_by_id.insert(v.toObject().value(QStringLiteral("id")).toInt(), v.toObject());
    QHash<QString, double> he_so;
    const QJsonArray th = engine.value(QStringLiteral("to_hop")).toArray();
    for (const QJsonValue& v : th) {
        const QJsonObject t = v.toObject();
        if (t.value(QStringLiteral("he_so")).isDouble())
            he_so.insert(str(t, "ten"), t.value(QStringLiteral("he_so")).toDouble());
    }

    QJsonArray blocks = issue.value(QStringLiteral("khoi")).toArray();
    if (blocks.isEmpty())
        blocks = ek; // no issue: the engine's block list still names and scores the blocks
    if (blocks.isEmpty()) {
        body->addWidget(top_need(sec, QStringLiteral("bản tuần chưa có tám khối chỉ báo")));
    } else {
        QGridLayout* g = top_grid(body, 2);
        for (int i = 0; i < blocks.size(); ++i) {
            const QJsonObject b = blocks.at(i).toObject();
            const QJsonObject e = eng_by_id.value(b.value(QStringLiteral("id")).toInt());
            g->addWidget(top_block_card(b, e, he_so, sec), i / 2, i % 2);
        }
    }

    // How the blocks add up to the regime: formulas, then the engine's reading of the §7 table.
    QVBoxLayout* fl = nullptr;
    QFrame* f = make_card(sec, fl, col(Role::Line2));
    fl->addWidget(top_plain(f, col(Role::Ink), 13, QStringLiteral("Cách các khối cộng thành chế độ"), true));
    QStringList lines;
    for (const QJsonValue& v : th) {
        const QJsonObject t = v.toObject();
        const QString ten = str(t, "ten");
        QString cf = str(t, "cong_thuc");
        if (cf.isEmpty())
            cf = top_kNeed;
        QString line = cf.startsWith(ten) ? cf : ten + QStringLiteral(" = ") + cf;
        if (!str(t, "bien_txt").isEmpty())
            line += QStringLiteral("   [biên %1]").arg(str(t, "bien_txt"));
        if (t.value(QStringLiteral("mo_rong")).toBool())
            line += QStringLiteral("   (mở rộng — không dùng cho chế độ)");
        lines << line;
    }
    const QJsonObject cd = engine.value(QStringLiteral("che_do")).toObject();
    if (!str(cd, "ly_giai").isEmpty())
        lines << str(cd, "ly_giai");
    if (!str(cd, "ghi_chu_bien").isEmpty())
        lines << str(cd, "ghi_chu_bien");
    if (lines.isEmpty())
        fl->addWidget(top_need(f, QStringLiteral("engine §7 chưa chạy")));
    else
        fl->addWidget(top_plain(f, col(Role::Muted), 12, lines.join(QLatin1Char('\n')), false, true));
    body->addWidget(f);
    return sec;
}

// ── Đối chiếu HHP ────────────────────────────────────────────────────────────

QWidget* build_hhp_crosscheck(const QJsonObject& doi_chieu_hhp, QWidget* parent) {
    QVBoxLayout* lay = nullptr;
    QFrame* card = make_card(parent, lay, col(Role::Blue));
    const QString ky = str(doi_chieu_hhp, "ky");
    lay->addWidget(top_plain(card, col(Role::Ink), 13,
                             QStringLiteral("Đối chiếu khung HHP — ba chiếc đồng hồ (bản tuần HHP kỳ %1)")
                                 .arg(ky.isEmpty() ? top_kNeed : top_ddmm(ky)),
                             true));

    const QJsonArray dong_ho = doi_chieu_hhp.value(QStringLiteral("dong_ho")).toArray();
    if (dong_ho.isEmpty()) {
        lay->addWidget(top_need(card, QStringLiteral("bản tuần chưa đối chiếu với khung HHP")));
    } else {
        auto* g = new QGridLayout;
        g->setContentsMargins(0, 2, 0, 2);
        g->setHorizontalSpacing(16);
        g->setVerticalSpacing(4);
        const int cols = std::min<int>(3, static_cast<int>(dong_ho.size()));
        for (int c = 0; c < cols; ++c)
            g->setColumnStretch(c, 1);
        for (int i = 0; i < dong_ho.size(); ++i) {
            const QJsonObject d = dong_ho.at(i).toObject();
            const QString st = top_or_need(str(d, "trang_thai").trimmed());
            auto* cell = make_box(card);
            auto* cl = new QVBoxLayout(cell);
            cl->setContentsMargins(0, 0, 0, 0);
            cl->setSpacing(3);
            cl->addWidget(top_rich(cell, col(Role::Ink), 12,
                                   pill_html(top_or_need(str(d, "ten")) + QStringLiteral(" · ") + st, status_color(st), 12)));
            const QString gc = str(d, "ghi_chu");
            if (!gc.isEmpty())
                cl->addWidget(top_plain(cell, col(Role::Ink2), 12, gc));
            cl->addStretch(1);
            g->addWidget(cell, i / 3, i % 3);
        }
        lay->addLayout(g);
    }
    const QString gc = str(doi_chieu_hhp, "ghi_chu");
    if (!gc.isEmpty())
        lay->addWidget(top_plain(card, col(Role::Ink2), 12, gc));
    const QString nguon = str(doi_chieu_hhp, "nguon");
    lay->addWidget(top_plain(card, col(Role::Muted), 11, QStringLiteral("Nguồn: ") + top_or_need(nguon)));
    return card;
}

} // namespace fincept::screens::sgi
