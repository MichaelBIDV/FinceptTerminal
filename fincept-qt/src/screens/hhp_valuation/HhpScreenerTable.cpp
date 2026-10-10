// src/screens/hhp_valuation/HhpScreenerTable.cpp — port of the screener in
// hhp_vn100_valuation.html (render() / gauge() / sortBy()). See HhpScreenerTable.h.
#include "screens/hhp_valuation/HhpScreenerTable.h"

#include "screens/hhp_valuation/HhpCommon.h"

#include <QAction>
#include <QDate>
#include <QDateTime>
#include <QDesktopServices>
#include <QHeaderView>
#include <QKeyEvent>
#include <QLinearGradient>
#include <QMap>
#include <QMenu>
#include <QPainter>
#include <QPainterPath>
#include <QStyledItemDelegate>
#include <QTextDocument>
#include <QUrl>

#include <algorithm>
#include <array>
#include <cmath>
#include <cstdlib>
#include <utility>

namespace fincept::screens::hhp {

namespace {

// Gauge numbers live on the gauge cell; all in đồng, like the page's gauge(b).
constexpr int kRoleCheap2 = Qt::UserRole + 1;
constexpr int kRoleCheap1 = Qt::UserRole + 2;
constexpr int kRoleRich1 = Qt::UserRole + 3;
constexpr int kRoleRich2 = Qt::UserRole + 4;
constexpr int kRolePrice = Qt::UserRole + 5;
constexpr int kRoleHtml = Qt::UserRole + 6; // rich-text cell content (RichTextDelegate)

constexpr int kRowHeight = 30;
constexpr int kCellPad = 6;      // same as "::item { padding: 0 6px }"
constexpr int kGaugeW = 170;
constexpr int kGaugeH = 12;
constexpr int kTitleChars = 48;  // catalyst title shown before "…"

QColor selected_bg() { return QColor(0x1c, 0x20, 0x27); }

QString metric_label(const QString& metric) {
    return metric == QLatin1String("pb") ? QStringLiteral("P/B") : QStringLiteral("P/E");
}

/// Escaped `text` in colour `c` (optional pixel size) — building block of the rich-text cells.
QString html_span(const QString& text, const QColor& c, int px = 0) {
    const QString size = px > 0 ? QStringLiteral(" font-size:%1px;").arg(px) : QString();
    return QStringLiteral("<span style=\"color:%1;%2\">%3</span>").arg(css(c), size, text.toHtmlEscaped());
}

/// "2021-11-30" → "30/11/2021"; anything else unchanged.
QString vi_date(const QString& iso) {
    const QDate d = QDate::fromString(iso, Qt::ISODate);
    return d.isValid() ? d.toString(QStringLiteral("dd/MM/yyyy")) : iso;
}

/// "2026-09-23T15:14:27+07:00" → "23/09/2026 15:14" (in the stamp's own offset); no valid time → vi_date(date).
QString vi_stamp(const QString& iso_time, const QString& iso_date) {
    const QDateTime t = QDateTime::fromString(iso_time, Qt::ISODate);
    return t.isValid() ? t.toString(QStringLiteral("dd/MM/yyyy HH:mm")) : vi_date(iso_date);
}

/// Tooltip of the Giá cell: where row.price_now comes from (price_src / price_date / price_time, fixed upstream).
QString price_tip(const QJsonObject& row) {
    const QString src = row.value(QStringLiteral("price_src")).toString();
    QString when = vi_stamp(row.value(QStringLiteral("price_time")).toString(),
                            row.value(QStringLiteral("price_date")).toString());
    if (!when.isEmpty())
        when += QLatin1Char(' ');
    if (src == QLatin1String("vietcap_board"))
        return QStringLiteral("Giá Vietcap %1(bảng giá)").arg(when);
    if (src == QLatin1String("vietcap_history"))
        return QStringLiteral("Giá Vietcap %1(lịch sử)").arg(when);
    if (src == QLatin1String("vnd_dchart"))
        return QStringLiteral("Giá VnDirect DCHART %1(dự phòng — không có dữ liệu Vietcap)").arg(when);
    if (src == QLatin1String("simplize_stale"))
        return QStringLiteral("⚠ giá Simplize cũ — không có dữ liệu Vietcap");
    return src.isEmpty() ? QString() : QStringLiteral("Nguồn giá: ") + src;
}

/// Short name of the price feed behind row.price_now, for "upside so với giá …".
QString price_src_name(const QString& src) {
    if (src.startsWith(QLatin1String("vietcap")))
        return QStringLiteral("Vietcap");
    if (src == QLatin1String("vnd_dchart"))
        return QStringLiteral("VnDirect");
    if (src == QLatin1String("simplize_stale"))
        return QStringLiteral("Simplize cũ");
    return {};
}

/// CapIQ's average broker rec is English ("Buy", "Outperform", "Hold", "Underperform", "No Opinion").
/// rec_color() knows BUY/SELL but not the out/under-perform grades, which it would leave grey.
QColor ciq_rec_color(const QString& rec) {
    const QString u = rec.toUpper();
    if (u.contains(QLatin1String("UNDERPERFORM")))
        return c_rich();
    if (u.contains(QLatin1String("OUTPERFORM")))
        return c_cheap();
    return rec_color(rec);
}

/// Every cell paints the selected-row colour itself and then drops State_Selected, so the
/// per-cell colours (zone, recommendation, upside) survive on the selected row instead of
/// turning into the palette's HighlightedText.
class RowDelegate : public QStyledItemDelegate {
  public:
    using QStyledItemDelegate::QStyledItemDelegate;

    void paint(QPainter* p, const QStyleOptionViewItem& option, const QModelIndex& index) const override {
        QStyleOptionViewItem opt(option);
        if (opt.state & QStyle::State_Selected) {
            p->fillRect(opt.rect, selected_bg());
            opt.state &= ~QStyle::State_Selected;
        }
        opt.state &= ~QStyle::State_HasFocus;
        QStyledItemDelegate::paint(p, opt, index);
    }
};

/// Cell whose kRoleHtml holds rich text: one cell, several colours (the page colours the catalyst's
/// recommendation, upside, revisions and title separately, and draws the "unreliable" ⚠ in red next to
/// a zone-coloured σ). Cells without kRoleHtml paint as plain items.
class RichTextDelegate : public RowDelegate {
  public:
    using RowDelegate::RowDelegate;

    void paint(QPainter* p, const QStyleOptionViewItem& option, const QModelIndex& index) const override {
        RowDelegate::paint(p, option, index); // row background + bottom border (the item text is empty)
        const QString html = index.data(kRoleHtml).toString();
        if (html.isEmpty())
            return;
        QStyleOptionViewItem opt(option);
        initStyleOption(&opt, index); // item font (bold σ) + alignment
        QTextDocument doc;
        doc.setDocumentMargin(0);
        doc.setDefaultFont(opt.font);
        doc.setHtml(html); // every span carries its own colour: the document palette is not the table's
        const QRectF area = QRectF(option.rect).adjusted(kCellPad, 0, -kCellPad, 0);
        const qreal x = (opt.displayAlignment & Qt::AlignRight) ? area.right() - doc.idealWidth() : area.left();
        const qreal y = area.top() + (area.height() - doc.size().height()) / 2.0;
        p->save();
        p->setClipRect(area);
        p->translate(x, y);
        doc.drawContents(p);
        p->restore();
    }
};

/// gauge(b): cheap2…cheap1 green, cheap1…rich1 neutral, rich1…rich2 red, gold marker at the price.
class GaugeDelegate : public RowDelegate {
  public:
    using RowDelegate::RowDelegate;

    void paint(QPainter* p, const QStyleOptionViewItem& option, const QModelIndex& index) const override {
        RowDelegate::paint(p, option, index); // row background + bottom border (+ "—" when no gauge)
        if (!index.data(kRoleCheap2).isValid())
            return;
        const double lo = index.data(kRoleCheap2).toDouble();
        const double hi = index.data(kRoleRich2).toDouble();
        const double span = hi - lo;
        const auto frac = [lo, span](double x) { return std::clamp((x - lo) / span, 0.0, 1.0); };

        const int w = std::min(kGaugeW, option.rect.width() - 2 * kCellPad);
        if (w <= 0)
            return;
        const QRectF bar(option.rect.left() + kCellPad, option.rect.center().y() - kGaugeH / 2 + 1, w, kGaugeH);
        const double g_end = bar.left() + bar.width() * frac(index.data(kRoleCheap1).toDouble());
        const double r_start = bar.left() + bar.width() * frac(index.data(kRoleRich1).toDouble());

        p->save();
        p->setRenderHint(QPainter::Antialiasing, true);
        QPainterPath clip;
        clip.addRoundedRect(bar, 3, 3);
        p->setClipPath(clip, Qt::IntersectClip);
        p->fillRect(bar, c_neutral());
        const QRectF g(bar.left(), bar.top(), g_end - bar.left(), bar.height());
        QLinearGradient gg(g.topLeft(), g.topRight());
        gg.setColorAt(0, c_cheap2());
        gg.setColorAt(1, c_cheap());
        p->fillRect(g, gg);
        const QRectF r(r_start, bar.top(), bar.right() - r_start, bar.height());
        QLinearGradient rg(r.topLeft(), r.topRight());
        rg.setColorAt(0, c_rich());
        rg.setColorAt(1, c_rich2());
        p->fillRect(r, rg);
        p->restore();

        // Marker: 2px gold line reaching 3px past the bar, with a soft glow like the page's box-shadow.
        const double mx = std::round(bar.left() + bar.width() * frac(index.data(kRolePrice).toDouble()));
        const QPointF top(mx, bar.top() - 3), bottom(mx, bar.bottom() + 3);
        p->save();
        p->setRenderHint(QPainter::Antialiasing, true);
        QColor glow = c_idx();
        glow.setAlphaF(0.35f);
        p->setPen(QPen(glow, 4.0, Qt::SolidLine, Qt::FlatCap));
        p->drawLine(top, bottom);
        p->setPen(QPen(c_idx(), 2.0, Qt::SolidLine, Qt::FlatCap));
        p->drawLine(top, bottom);
        p->restore();
    }
};

QTableWidgetItem* make_item(const QString& text, const QColor& color, Qt::Alignment align = Qt::AlignLeft) {
    auto* it = new QTableWidgetItem(text);
    it->setFlags(Qt::ItemIsSelectable | Qt::ItemIsEnabled);
    it->setForeground(color);
    it->setTextAlignment(align | Qt::AlignVCenter);
    return it;
}

QTableWidgetItem* make_gauge_item(const QJsonObject& b, double price) {
    const double lo = num(b.value(QStringLiteral("band_cheap2")));
    const double c1 = num(b.value(QStringLiteral("band_cheap1")));
    const double fair = num(b.value(QStringLiteral("band_fair")));
    const double r1 = num(b.value(QStringLiteral("band_rich1")));
    const double hi = num(b.value(QStringLiteral("band_rich2")));
    if (!has(lo) || !has(hi) || hi <= lo || !has(price))
        return make_item(QStringLiteral("—"), c_muted());

    auto* it = make_item(QString(), c_text());
    it->setData(kRoleCheap2, lo);
    it->setData(kRoleCheap1, has(c1) ? c1 : lo);
    it->setData(kRoleRich1, has(r1) ? r1 : hi);
    it->setData(kRoleRich2, hi);
    it->setData(kRolePrice, price);
    it->setToolTip(QStringLiteral("rẻ %1–%2 · TB %3 · đắt %4–%5")
                       .arg(fmt_vi(lo), fmt_vi(c1), fmt_vi(fair), fmt_vi(r1), fmt_vi(hi)));
    return it;
}

/// Fwd 26F: forward P/E or P/B, green when it is below today's ratio (earnings/book catching up).
QTableWidgetItem* make_fwd_item(const QJsonObject& row, const QString& metric, double now, const QFont& font) {
    const QJsonValue fv = row.value(QStringLiteral("forward"));
    if (!fv.isObject()) {
        auto* it = make_item(QStringLiteral("—"), c_muted(), Qt::AlignRight);
        it->setToolTip(QStringLiteral("Chưa có dự phóng"));
        return it;
    }
    const QJsonObject fw = fv.toObject();
    const double v = num(fw.value(metric));

    QString tip = QStringLiteral("Forward 2026F");
    const QString rating = fw.value(QStringLiteral("rating")).toString();
    const QString analyst = fw.value(QStringLiteral("analyst")).toString();
    const double tp = num(fw.value(QStringLiteral("tp")));
    const double up = num(fw.value(QStringLiteral("upside_pct")));
    const double roe = num(fw.value(QStringLiteral("roe")));
    if (!rating.isEmpty())
        tip += QStringLiteral(" · ") + rating;
    if (!analyst.isEmpty())
        tip += QStringLiteral(" · ") + analyst;
    if (has(tp))
        tip += QStringLiteral(" · TP ") + fmt_vi(tp);
    if (has(up))
        tip += QStringLiteral(" · upside ") + fmt_pct(up);
    if (has(roe))
        tip += QStringLiteral(" · ROE ") + fmt_ratio(roe) + QLatin1Char('%');

    if (!has(v)) {
        auto* it = make_item(QStringLiteral("—"), c_muted(), Qt::AlignRight);
        it->setToolTip(tip);
        return it;
    }
    const QString src = fw.value(QStringLiteral("src")).toString();
    QString text = fmt_ratio(v);
    if (src == QLatin1String("vietcap"))
        text += QStringLiteral(" ·V");
    else if (src == QLatin1String("spg"))
        text += QStringLiteral(" ·S");
    auto* it = make_item(text, has(now) ? (v < now ? c_cheap() : c_rich()) : c_muted(), Qt::AlignRight);
    QFont f = font;
    f.setWeight(QFont::DemiBold);
    it->setFont(f);
    it->setToolTip(tip);
    return it;
}

/// capiq.ttm.asof {screen slug: ISO day} → "22/09/2026: fundamental; 23/09/2026: estimates, key_stats".
QString ciq_asof_text(const QJsonObject& asof) {
    QMap<QString, QStringList> by_day; // ISO day → slugs; QMap keeps the days in order
    for (auto it = asof.begin(); it != asof.end(); ++it) {
        const QString day = it.value().toString();
        by_day[day.isEmpty() ? QStringLiteral("?") : day] << it.key();
    }
    QStringList parts;
    for (auto it = by_day.cbegin(); it != by_day.cend(); ++it)
        parts << vi_date(it.key()) + QStringLiteral(": ") + it.value().join(QStringLiteral(", "));
    return parts.join(QStringLiteral("; "));
}

/// "CIQ hiện tại" lines of the CapIQ tooltip, from capiq.ttm (plain text): CapIQ's own current multiples,
/// then the [EST] ratios derived upstream (not CapIQ figures), LTM figures and each screen's export day.
/// {} when ttm carries no value.
QStringList ciq_now_lines(const QJsonObject& t) {
    const auto val = [&t](const char* key) { return num(t.value(QLatin1String(key))); };
    const auto ratio = [&val](const char* key) { return has(val(key)) ? fmt_ratio(val(key)) : QString(); };
    const auto pct = [&val](const char* key) {
        return has(val(key)) ? fmt_ratio(val(key), 1) + QLatin1Char('%') : QString();
    };
    const auto dong = [&val](const char* key) {
        return has(val(key)) ? fmt_vi(val(key)) + QStringLiteral(" đ") : QString();
    };
    const auto part = [](const char* label, const QString& value) {
        return value.isEmpty() ? QString() : QString::fromUtf8(label) + QLatin1Char(' ') + value;
    };
    QStringList lines;
    const auto line = [&lines](const QStringList& parts, const QString& suffix = QString()) {
        QStringList kept;
        for (const QString& p : parts) {
            if (!p.isEmpty())
                kept << p;
        }
        if (!kept.isEmpty())
            lines << kept.join(QStringLiteral(" · ")) + suffix;
    };
    const double mcap_b = val("mcap_b"); // tỷ đồng
    line({part("P/E", ratio("pe")), part("P/B", ratio("pb"))}, QStringLiteral(" (CIQ)"));
    line({part("P/E TTM", ratio("pe_ttm_est")), part("P/B BV FY0", ratio("pb_fy0bv_est"))},
         QStringLiteral(" [EST]"));
    line({part("EPS LTM", dong("eps_ltm")), part("BVPS LTM", dong("bvps_ltm")), part("ROE FY0", pct("roe_fy0"))});
    line({part("Cổ tức", pct("div_yield")),
          part("Vốn hoá", has(mcap_b) ? fmt_vi(mcap_b / 1000.0, 1) + QStringLiteral(" nghìn tỷ đ") : QString()),
          part("EV/EBITDA fwd", ratio("ev_ebitda_fwd"))});
    line({part("Tăng trưởng DT LTM", has(val("rev_g_ltm")) ? fmt_pct(val("rev_g_ltm")) : QString()),
          part("biên LN ròng", pct("npm_ltm"))});
    if (lines.isEmpty())
        return lines;
    const QString asof = ciq_asof_text(t.value(QStringLiteral("asof")).toObject());
    if (!asof.isEmpty())
        lines << QStringLiteral("CIQ xuất ") + asof;
    return lines;
}

/// CapIQ: "73.554 · Buy" = CIQ Target Price + average broker rec, coloured by the rec; row.capiq in the tooltip.
QTableWidgetItem* make_capiq_item(const QJsonObject& row) {
    const QJsonValue qv = row.value(QStringLiteral("capiq"));
    if (!qv.isObject()) {
        auto* it = make_item(QStringLiteral("—"), c_muted());
        it->setToolTip(QStringLiteral("Không có dữ liệu S&P CapIQ cho mã này"));
        return it;
    }
    const QJsonObject q = qv.toObject();
    const auto val = [&q](const char* key) { return num(q.value(QLatin1String(key))); };
    const double tp = val("tp");
    const QString rec = q.value(QStringLiteral("rec")).toString();

    QStringList head;
    if (has(tp))
        head << fmt_vi(tp);
    if (!rec.isEmpty())
        head << rec;

    QStringList tip = {QStringLiteral("S&P Capital IQ — đồng thuận")};
    QStringList mult;
    if (has(val("pe")))
        mult << QStringLiteral("P/E fwd 26F %1").arg(fmt_ratio(val("pe")));
    if (has(val("pb")))
        mult << QStringLiteral("P/B fwd 26F %1").arg(fmt_ratio(val("pb")));
    if (!mult.isEmpty())
        tip << mult.join(QStringLiteral(" · "));
    if (has(tp)) {
        QStringList detail;
        if (has(val("tp_med")))
            detail << QStringLiteral("TV ") + fmt_vi(val("tp_med"));
        if (has(val("tp_high")))
            detail << QStringLiteral("cao ") + fmt_vi(val("tp_high"));
        if (has(val("tp_low")))
            detail << QStringLiteral("thấp ") + fmt_vi(val("tp_low"));
        if (has(val("n_tp")))
            detail << QStringLiteral("%1 TP").arg(qRound(val("n_tp")));
        const QString tp_date = q.value(QStringLiteral("tp_date")).toString();
        if (!tp_date.isEmpty())
            detail << vi_date(tp_date);
        tip << QStringLiteral("TP %1 đ").arg(fmt_vi(tp)) +
                   (detail.isEmpty() ? QString() : QStringLiteral(" (") + detail.join(QStringLiteral(" · ")) +
                                                       QLatin1Char(')'));
    }
    if (has(val("upside_pct"))) {
        const QString src = price_src_name(row.value(QStringLiteral("price_src")).toString());
        tip << QStringLiteral("Upside %1 so với giá %2%3 đ")
                   .arg(fmt_pct(val("upside_pct")), src.isEmpty() ? QString() : src + QLatin1Char(' '),
                        fmt_vi(num(row.value(QStringLiteral("price_now")))));
    }
    QStringList est;
    if (has(val("eps_est")))
        est << QStringLiteral("EPS dự phóng %1 đ").arg(fmt_vi(val("eps_est")));
    if (has(val("bvps_est")))
        est << QStringLiteral("BVPS dự phóng %1 đ").arg(fmt_vi(val("bvps_est")));
    if (has(val("roe_est")))
        est << QStringLiteral("ROE dự phóng %1%").arg(fmt_ratio(val("roe_est")));
    if (!est.isEmpty())
        tip << est.join(QStringLiteral(" · "));
    if (!rec.isEmpty() || has(val("n_rec")))
        tip << (rec.isEmpty() ? QStringLiteral("—") : rec) +
                   (has(val("n_rec")) ? QStringLiteral(" · %1 khuyến nghị").arg(qRound(val("n_rec"))) : QString());
    const QString exported = q.value(QStringLiteral("exported")).toString();
    if (!exported.isEmpty())
        tip << QStringLiteral("CapIQ xuất ") + vi_date(exported);
    // Plain-text tooltip (its first line is fixed, so Qt never reads it as rich text): data shows verbatim.
    const QStringList now = ciq_now_lines(q.value(QStringLiteral("ttm")).toObject());
    if (!now.isEmpty())
        tip << QString() << QStringLiteral("CIQ hiện tại") << now;

    auto* it = make_item(head.isEmpty() ? QStringLiteral("—") : head.join(QStringLiteral(" · ")),
                         head.isEmpty() ? c_muted() : ciq_rec_color(rec));
    it->setToolTip(tip.join(QLatin1Char('\n')));
    return it;
}

/// Catalyst (broker): "<rec> <upside> ↑n  <title…>" — rec by recommendation, upside and revisions by
/// sign, title muted, like the page's catCell (a "KHẢ QUAN -3%" must not read as all-green).
QTableWidgetItem* make_catalyst_item(const QJsonObject& row) {
    const QJsonValue cv = row.value(QStringLiteral("fa_catalyst"));
    if (!cv.isObject())
        return make_item(QStringLiteral("—"), c_muted());
    const QJsonObject c = cv.toObject();
    const QJsonObject latest = c.value(QStringLiteral("latest")).toObject();
    const QString rec = c.value(QStringLiteral("rec")).toString();
    const double up = num(c.value(QStringLiteral("upside")));
    const int revisions = c.value(QStringLiteral("net_revisions")).toInt();
    const QString title = latest.value(QStringLiteral("title")).toString();

    QStringList head;
    if (!rec.isEmpty())
        head << QStringLiteral("<b>") + html_span(rec_display(rec), rec_color(rec), 11) + QStringLiteral("</b>");
    if (has(up))
        head << html_span(fmt_pct(up), up >= 0 ? c_cheap() : c_rich());
    if (revisions != 0)
        head << html_span((revisions > 0 ? QStringLiteral("↑") : QStringLiteral("↓")) +
                              QString::number(std::abs(revisions)),
                          revisions > 0 ? c_cheap() : c_rich(), 11);
    QString html = head.join(QLatin1Char(' '));
    if (!title.isEmpty()) {
        QString t = title.left(kTitleChars);
        if (title.size() > kTitleChars)
            t += QStringLiteral("…");
        html += (html.isEmpty() ? QString() : QStringLiteral("&nbsp;&nbsp;")) + html_span(t, c_muted(), 11);
    }
    if (html.isEmpty())
        return make_item(QStringLiteral("—"), c_muted());

    QStringList tip;
    if (!title.isEmpty())
        tip << title;
    for (const char* key : {"source", "date"}) {
        const QString s = latest.value(QLatin1String(key)).toString();
        if (!s.isEmpty())
            tip << s;
    }
    const double n_reports = num(c.value(QStringLiteral("n_reports")));
    if (has(n_reports))
        tip << QStringLiteral("%1 báo cáo").arg(static_cast<int>(n_reports));

    auto* it = make_item(QString(), c_text());
    it->setData(kRoleHtml, html);
    it->setToolTip(tip.join(QStringLiteral(" · ")));
    return it;
}

// ── Sorting ──────────────────────────────────────────────────────────────────
// Keys follow the page's sortBy(): gauge / σ / Vùng all sort by sigma.
QString key_for_column(int column) {
    switch (column) {
    case HhpScreenerTable::ColTicker:
        return QStringLiteral("tk");
    case HhpScreenerTable::ColNow:
        return QStringLiteral("now");
    case HhpScreenerTable::ColMean:
        return QStringLiteral("mean");
    case HhpScreenerTable::ColPrice:
        return QStringLiteral("price_now");
    case HhpScreenerTable::ColFair:
        return QStringLiteral("band_fair");
    case HhpScreenerTable::ColUpside:
        return QStringLiteral("upside_to_fair_pct");
    case HhpScreenerTable::ColRec:
        return QStringLiteral("fa_rec");
    case HhpScreenerTable::ColFwd:
        return QStringLiteral("fwd");
    case HhpScreenerTable::ColCapiq:
        return QStringLiteral("capiq_upside");
    case HhpScreenerTable::ColCatalyst:
        return QStringLiteral("cat_upside");
    default:
        return QStringLiteral("sigma"); // ColGauge, ColSigma, ColZone
    }
}

bool is_text_key(const QString& key) { return key == QLatin1String("tk") || key == QLatin1String("fa_rec"); }

double sort_number(const QJsonObject& row, const QString& metric, const QString& key) {
    if (key == QLatin1String("price_now"))
        return num(row.value(key));
    if (key == QLatin1String("fwd"))
        return num(row.value(QStringLiteral("forward")).toObject().value(metric));
    if (key == QLatin1String("cat_upside"))
        return num(row.value(QStringLiteral("fa_catalyst")).toObject().value(QStringLiteral("upside")));
    if (key == QLatin1String("capiq_upside"))
        return num(row.value(QStringLiteral("capiq")).toObject().value(QStringLiteral("upside_pct")));
    return num(row.value(metric).toObject().value(key));
}

/// Nulls go last whichever way the column is sorted.
void sort_rows(QVector<QJsonObject>& rows, const QString& metric, const QString& key, bool asc) {
    if (is_text_key(key)) {
        std::stable_sort(rows.begin(), rows.end(), [&](const QJsonObject& a, const QJsonObject& b) {
            const QString x = a.value(key).toString(), y = b.value(key).toString();
            if (x.isEmpty() || y.isEmpty())
                return !x.isEmpty() && y.isEmpty();
            const int c = QString::compare(x, y, Qt::CaseInsensitive);
            return asc ? c < 0 : c > 0;
        });
        return;
    }
    std::stable_sort(rows.begin(), rows.end(), [&](const QJsonObject& a, const QJsonObject& b) {
        const double x = sort_number(a, metric, key), y = sort_number(b, metric, key);
        if (!has(x) || !has(y))
            return has(x) && !has(y);
        return asc ? x < y : x > y;
    });
}

} // namespace

HhpScreenerTable::HhpScreenerTable(QWidget* parent) : QTableWidget(parent) {
    setColumnCount(ColCount);
    for (int c = 0; c < ColCount; ++c)
        setHorizontalHeaderItem(c, new QTableWidgetItem);
    horizontalHeaderItem(ColSigma)->setToolTip(
        QStringLiteral("Số độ lệch chuẩn so với trung bình lịch sử của CHÍNH mã"));
    horizontalHeaderItem(ColFwd)->setToolTip(
        QStringLiteral("P/E hoặc P/B dự phóng 2026 — V = Vietcap IQ (live), S = S&P CapIQ snapshot (bù)"));
    horizontalHeaderItem(ColCapiq)->setToolTip(
        QStringLiteral("S&P Capital IQ: Target Price đồng thuận · khuyến nghị TB của broker (bản xuất mới nhất). "
                       "Sắp xếp theo upside của TP so với giá Vietcap"));
    horizontalHeaderItem(ColCatalyst)->setToolTip(
        QStringLiteral("Catalyst FA mới nhất từ mining broker: khuyến nghị · upside · số lần nâng/hạ · tiêu đề"));
    // Numeric headers sit right-aligned over their right-aligned numbers, as on the page (th.num).
    for (int c : {ColNow, ColMean, ColSigma, ColPrice, ColFair, ColUpside, ColFwd})
        horizontalHeaderItem(c)->setTextAlignment(Qt::AlignRight | Qt::AlignVCenter);

    setSortingEnabled(false);
    setEditTriggers(QAbstractItemView::NoEditTriggers);
    setSelectionBehavior(QAbstractItemView::SelectRows);
    setSelectionMode(QAbstractItemView::SingleSelection);
    setShowGrid(false);
    setWordWrap(false);
    setCornerButtonEnabled(false);
    setTextElideMode(Qt::ElideRight);
    setHorizontalScrollBarPolicy(Qt::ScrollBarAsNeeded);
    setHorizontalScrollMode(QAbstractItemView::ScrollPerPixel);
    setVerticalScrollMode(QAbstractItemView::ScrollPerPixel);
    setContextMenuPolicy(Qt::CustomContextMenu);
    setMouseTracking(true);
    viewport()->setMouseTracking(true);

    QFont f = font();
    f.setPixelSize(13);
    setFont(f);

    verticalHeader()->setVisible(false);
    verticalHeader()->setSectionResizeMode(QHeaderView::Fixed);
    verticalHeader()->setDefaultSectionSize(kRowHeight);

    QHeaderView* hh = horizontalHeader();
    hh->setDefaultAlignment(Qt::AlignLeft | Qt::AlignVCenter);
    hh->setSectionsClickable(true);
    hh->setHighlightSections(false);
    hh->setSortIndicatorShown(false); // direction is drawn as ▲/▼ in the label: consistent under any style
    hh->setStretchLastSection(true);
    hh->setMinimumSectionSize(40);
    // Mã fits the widest mark "◆ XXX ·30" (portfolio ticker that is also VN30, in the VN100 view).
    // CapIQ fits "105.528 · Outperform".
    const std::array<int, ColCount> widths = {104, 62, 72, 186, 72, 92, 86, 86, 84, 100, 84, 150, 320};
    for (int c = 0; c < ColCount; ++c)
        hh->resizeSection(c, widths[static_cast<size_t>(c)]);

    setItemDelegate(new RowDelegate(this));
    setItemDelegateForColumn(ColGauge, new GaugeDelegate(this));
    setItemDelegateForColumn(ColSigma, new RichTextDelegate(this));
    setItemDelegateForColumn(ColCatalyst, new RichTextDelegate(this));

    // font-size here, not only setFont(): the EconPanelBase container sheet sets QTableWidget to 11px,
    // and an inherited style-sheet font beats setFont().
    setStyleSheet(QStringLiteral("QTableWidget { background:%1; color:%2; border:none; outline:0; font-size:13px; }"
                                 "QTableWidget::item { border-bottom: 1px solid %3; padding: 0 6px; }"
                                 "QHeaderView { background:%1; border:none; }"
                                 "QHeaderView::section { background:%1; color:%4; font-size:10px; font-weight:700;"
                                 " border:none; border-bottom:1px solid %3; padding:6px 6px; }"
                                 "QHeaderView::section:hover { color:%5; }"
                                 "QScrollBar:horizontal { background:%1; height:10px; margin:0; }"
                                 "QScrollBar::handle:horizontal { background:%3; border-radius:4px; min-width:40px; }"
                                 "QScrollBar:vertical { background:%1; width:10px; margin:0; }"
                                 "QScrollBar::handle:vertical { background:%3; border-radius:4px; min-height:40px; }"
                                 "QScrollBar::add-line, QScrollBar::sub-line { width:0; height:0; }"
                                 "QScrollBar::add-page, QScrollBar::sub-page { background:none; }")
                      .arg(css(c_bg()), css(c_text()), css(c_line()), css(c_muted()), css(c_gold())));

    connect(hh, &QHeaderView::sectionClicked, this, &HhpScreenerTable::sort_by_column);
    connect(this, &QTableWidget::cellClicked, this, [this](int row, int column) {
        if (column == ColTicker)
            activate_row(row);
    });
    // A double-click on the ticker cell already fired on the first click.
    connect(this, &QTableWidget::cellDoubleClicked, this, [this](int row, int column) {
        if (column != ColTicker)
            activate_row(row);
    });
    connect(this, &QWidget::customContextMenuRequested, this, &HhpScreenerTable::open_links_menu);
    connect(this, &QAbstractItemView::entered, this, [this](const QModelIndex& idx) {
        const bool link = idx.column() == ColTicker && idx.row() < shown_.size();
        viewport()->setCursor(link ? Qt::PointingHandCursor : Qt::ArrowCursor);
    });
    connect(this, &QAbstractItemView::viewportEntered, this, [this]() { viewport()->unsetCursor(); });

    update_headers();
}

void HhpScreenerTable::set_rows(const QJsonArray& rows) {
    rows_ = rows;
}

void HhpScreenerTable::set_marks(const QSet<QString>& mine, const QSet<QString>& avoid,
                                 const QHash<QString, QString>& notes, const QString& source) {
    mark_mine_ = mine;
    mark_avoid_ = avoid;
    mark_notes_ = notes;
    mark_source_ = source;
    rebuild();
}

void HhpScreenerTable::apply(const QString& universe, const QString& metric, const QString& zone_key,
                             const QString& search, bool reliable_only) {
    universe_ = universe;
    metric_ = metric == QLatin1String("pb") ? QStringLiteral("pb") : QStringLiteral("pe");
    zone_key_ = zone_key;
    search_ = search.trimmed();
    reliable_only_ = reliable_only;
    rebuild();
    emit count_changed(visible_count_);
}

QJsonArray HhpScreenerTable::visible_rows() const {
    QJsonArray out;
    for (const QJsonObject& r : shown_)
        out.append(r);
    return out;
}

void HhpScreenerTable::rebuild() {
    const int cur = currentRow();
    const QString keep_tk = (cur >= 0 && cur < shown_.size()) ? shown_.at(cur).value(QStringLiteral("tk")).toString()
                                                               : QString();

    const QString flag = universe_ == QLatin1String("VN100") ? QStringLiteral("in_vn100") : QStringLiteral("in_vn30");
    QVector<QJsonObject> rows;
    rows.reserve(rows_.size());
    for (const QJsonValue& v : rows_) {
        const QJsonObject r = v.toObject();
        const QJsonObject b = r.value(metric_).toObject();
        if (!r.value(flag).toBool() || !r.value(metric_).isObject())
            continue;
        // A stale ratio (stopped updating upstream) sits in no zone — same rule as zone_counts.
        if (!zone_key_.isEmpty() &&
            (b.value(QStringLiteral("stale")).toBool() || b.value(QStringLiteral("zone_key")).toString() != zone_key_))
            continue;
        if (reliable_only_ && !b.value(QStringLiteral("reliable")).toBool())
            continue;
        if (!search_.isEmpty() && !r.value(QStringLiteral("tk")).toString().contains(search_, Qt::CaseInsensitive))
            continue;
        rows.append(r);
    }
    sort_rows(rows, metric_, sort_key_, sort_asc_);
    shown_ = rows;
    visible_count_ = static_cast<int>(rows.size());
    update_headers();

    setUpdatesEnabled(false);
    selectionModel()->clear(); // also drops the current row: Enter must not open a ticker nobody picked
    clearContents();
    clearSpans();
    if (shown_.isEmpty()) {
        setRowCount(1);
        setSpan(0, 0, 1, ColCount);
        auto* it = make_item(QStringLiteral("Không có mã khớp bộ lọc (%1).").arg(metric_label(metric_)), c_muted());
        it->setFlags(Qt::ItemIsEnabled);
        setItem(0, 0, it);
    } else {
        setRowCount(static_cast<int>(shown_.size()));
        for (int i = 0; i < shown_.size(); ++i)
            fill_row(i, shown_.at(i));
    }
    setUpdatesEnabled(true);

    if (!keep_tk.isEmpty()) {
        for (int i = 0; i < shown_.size(); ++i) {
            if (shown_.at(i).value(QStringLiteral("tk")).toString() == keep_tk) {
                selectRow(i);
                break;
            }
        }
    }
}

void HhpScreenerTable::fill_row(int row, const QJsonObject& r) {
    const QJsonObject b = r.value(metric_).toObject();
    // Stale = the ratio stopped updating upstream (KOS P/E ends 2021): shown, but muted and zone-less.
    const bool stale = b.value(QStringLiteral("stale")).toBool();
    const QString as_of = vi_date(b.value(QStringLiteral("as_of")).toString());
    const QString stale_tip = stale ? QStringLiteral("%1 dừng cập nhật từ %2 — ratio cũ, không xếp vùng rẻ/đắt")
                                          .arg(metric_label(metric_), as_of)
                                    : QString();
    const QColor zcol = stale ? c_muted() : zone_color(b.value(QStringLiteral("zone_key")).toString());
    QFont bold = font();
    bold.setBold(true);
    QFont small_bold = bold;
    small_bold.setPixelSize(11);

    const QString tk = r.value(QStringLiteral("tk")).toString();
    const bool mark30 = universe_ == QLatin1String("VN100") && r.value(QStringLiteral("in_vn30")).toBool();
    const bool mine = mark_mine_.contains(tk);
    const bool avoid = !mine && mark_avoid_.contains(tk);
    QString tk_text = mark30 ? tk + QStringLiteral(" ·30") : tk;
    if (mine)
        tk_text = QStringLiteral("◆ ") + tk_text;
    auto* tk_item = make_item(tk_text, avoid ? c_rich() : c_gold()); // gold = clickable, as .tklink
    QFont tk_font = bold;
    tk_font.setStrikeOut(avoid);
    tk_item->setFont(tk_font);
    QString mark_tip;
    if (mine)
        mark_tip = QStringLiteral("◆ Danh mục (%1)").arg(mark_source_);
    else if (avoid)
        mark_tip = QStringLiteral("⊘ Danh sách tránh (%1)").arg(mark_source_);
    const QString note = mark_notes_.value(tk);
    if (!note.isEmpty())
        mark_tip += (mark_tip.isEmpty() ? QString() : QStringLiteral(" · ")) + note;
    tk_item->setToolTip((mark30 ? QStringLiteral("Thuộc VN30\n") : QString()) +
                        (mark_tip.isEmpty() ? QString() : mark_tip + QLatin1Char('\n')) +
                        QStringLiteral("Bấm để xem chart vùng định giá P/E · P/B (lịch sử + forward)"));
    setItem(row, ColTicker, tk_item);

    const double now = num(b.value(QStringLiteral("now")));
    auto* now_item = make_item(fmt_ratio(now), stale ? c_muted() : c_text(), Qt::AlignRight);
    now_item->setToolTip(stale_tip);
    setItem(row, ColNow, now_item);
    setItem(row, ColMean, make_item(fmt_ratio(num(b.value(QStringLiteral("mean")))), c_muted(), Qt::AlignRight));
    if (stale) {
        auto* gauge = make_item(QStringLiteral("—"), c_muted());
        gauge->setToolTip(stale_tip);
        setItem(row, ColGauge, gauge);
    } else {
        setItem(row, ColGauge, make_gauge_item(b, num(r.value(QStringLiteral("price_now")))));
    }

    // σ in the zone colour, the "unreliable" ⚠ in red beside it (page: .unrel).
    const bool reliable = b.value(QStringLiteral("reliable")).toBool();
    QString sig_html = html_span(fmt_sigma(num(b.value(QStringLiteral("sigma")))), zcol);
    QStringList sig_tip;
    if (!reliable) {
        sig_html += QStringLiteral(" ") + html_span(QStringLiteral("⚠"), c_rich(), 10);
        sig_tip << QStringLiteral("Ratio biến động lớn → band kém tin, đổi sang metric kia");
    }
    if (stale)
        sig_tip << stale_tip;
    auto* sig = make_item(QString(), zcol, Qt::AlignRight);
    sig->setData(kRoleHtml, sig_html);
    sig->setFont(bold);
    sig->setToolTip(sig_tip.join(QLatin1Char('\n')));
    setItem(row, ColSigma, sig);

    auto* zone = make_item(stale ? QStringLiteral("CŨ") : zone_short(b.value(QStringLiteral("zone_key")).toString()),
                           zcol);
    zone->setFont(small_bold);
    zone->setToolTip(stale ? stale_tip : b.value(QStringLiteral("zone")).toString());
    setItem(row, ColZone, zone);

    // Red = no Vietcap price upstream, the row still carries the old Simplize quote.
    const bool price_stale = r.value(QStringLiteral("price_src")).toString() == QLatin1String("simplize_stale");
    auto* price_item = make_item(fmt_vi(num(r.value(QStringLiteral("price_now")))), price_stale ? c_rich() : c_text(),
                                 Qt::AlignRight);
    price_item->setToolTip(price_tip(r));
    setItem(row, ColPrice, price_item);
    setItem(row, ColFair, make_item(fmt_vi(num(b.value(QStringLiteral("band_fair")))), c_muted(), Qt::AlignRight));

    const double up = num(b.value(QStringLiteral("upside_to_fair_pct")));
    auto* up_item =
        make_item(fmt_pct(up), (has(up) && !stale) ? (up >= 0 ? c_cheap() : c_rich()) : c_muted(), Qt::AlignRight);
    up_item->setToolTip(stale_tip);
    setItem(row, ColUpside, up_item);

    const QString rec = r.value(QStringLiteral("fa_rec")).toString();
    auto* rec_item = make_item(rec.isEmpty() ? QStringLiteral("—") : rec_display(rec), rec_color(rec));
    rec_item->setFont(small_bold);
    setItem(row, ColRec, rec_item);

    setItem(row, ColFwd, make_fwd_item(r, metric_, now, font()));
    setItem(row, ColCapiq, make_capiq_item(r));
    setItem(row, ColCatalyst, make_catalyst_item(r));
}

void HhpScreenerTable::update_headers() {
    const QString m = metric_label(metric_);
    const QStringList labels = {QStringLiteral("Mã"),
                                m,
                                m + QStringLiteral(" TB"),
                                QStringLiteral("Vị thế (rẻ ◄ ► đắt)"),
                                QStringLiteral("σ"),
                                QStringLiteral("Vùng"),
                                QStringLiteral("Giá"),
                                QStringLiteral("Giá TB"),
                                QStringLiteral("→TB"),
                                QStringLiteral("HSC"),
                                QStringLiteral("Fwd 26F"),
                                QStringLiteral("CapIQ"),
                                QStringLiteral("Catalyst (broker)")};
    for (int c = 0; c < ColCount; ++c) {
        // Uppercase like the page's th, except σ (it would become Σ).
        QString text = c == ColSigma ? labels.at(c) : labels.at(c).toUpper();
        if (c == sort_col_)
            text += sort_asc_ ? QStringLiteral(" ▲") : QStringLiteral(" ▼");
        horizontalHeaderItem(c)->setText(text);
    }
}

void HhpScreenerTable::sort_by_column(int column) {
    if (column < 0 || column >= ColCount)
        return;
    const QString key = key_for_column(column);
    if (key == sort_key_) {
        sort_asc_ = !sort_asc_;
    } else {
        sort_key_ = key;
        sort_asc_ = key == QLatin1String("tk") || key == QLatin1String("now") || key == QLatin1String("sigma");
    }
    sort_col_ = column;
    rebuild();
}

void HhpScreenerTable::activate_row(int row) {
    if (row < 0 || row >= shown_.size())
        return; // also covers the "no match" placeholder row
    const QString tk = shown_.at(row).value(QStringLiteral("tk")).toString();
    if (!tk.isEmpty())
        emit ticker_activated(tk);
}

void HhpScreenerTable::keyPressEvent(QKeyEvent* event) {
    if ((event->key() == Qt::Key_Return || event->key() == Qt::Key_Enter) && currentRow() >= 0 &&
        currentRow() < shown_.size()) {
        activate_row(currentRow());
        event->accept();
        return;
    }
    QTableWidget::keyPressEvent(event);
}

void HhpScreenerTable::open_links_menu(const QPoint& pos) {
    const int row = rowAt(pos.y());
    if (row < 0 || row >= shown_.size())
        return;
    const QJsonObject links = shown_.at(row).value(QStringLiteral("links")).toObject();
    selectRow(row);

    QMenu menu(this);
    menu.setStyleSheet(QStringLiteral("QMenu { background:%1; color:%2; border:1px solid %3; padding:4px; }"
                                      "QMenu::item { padding:5px 18px; }"
                                      "QMenu::item:selected { background:%4; color:%5; }")
                           .arg(css(c_card()), css(c_text()), css(c_line()), css(selected_bg()), css(c_gold())));
    const std::array<std::pair<const char*, QString>, 3> entries = {{
        {"vietcap_iq", QStringLiteral("Mở VietCap IQ")},
        {"miquant", QStringLiteral("Mở MiQuant")},
        {"simplize", QStringLiteral("Mở Simplize")},
    }};
    for (const auto& [key, label] : entries) {
        const QUrl url(links.value(QLatin1String(key)).toString());
        // Links come from the pipeline JSON: only ever hand web URLs to the OS.
        if (!url.isValid() || (url.scheme() != QLatin1String("https") && url.scheme() != QLatin1String("http")))
            continue;
        QAction* act = menu.addAction(label);
        connect(act, &QAction::triggered, this, [url]() { QDesktopServices::openUrl(url); });
    }
    if (menu.isEmpty())
        return;
    menu.exec(viewport()->mapToGlobal(pos));
}

} // namespace fincept::screens::hhp
