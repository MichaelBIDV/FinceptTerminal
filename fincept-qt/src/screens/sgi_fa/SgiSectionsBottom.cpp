// src/screens/sgi_fa/SgiSectionsBottom.cpp
// SGI FA — bottom half of the page: V bằng chứng · VI neo lịch sử · VII ngưỡng đảo chiều ·
// VIII hàm ý danh mục · IX track record · X nghịch đảo · footer (nguồn, cảnh báo, kiểm kỳ sau).
//
// Layout only: numbers arrive pre-formatted from scripts/sgi_fa.py, except the few raw numbers the
// issue JSON carries verbatim (portfolio %, track-record returns), which get the Vietnamese number
// format here (decimal comma, thousands dot, U+2212 minus). Nothing is computed that the payload does
// not state; a missing value renders as "[CẦN DATA]" so the gap stays visible.
//
// Tables are QGridLayout-of-QLabel grids (all short, ≤ ~25 rows): every cell word-wraps and the page
// scrolls as one. Charts reuse langkinh::LkLineChart exactly as LkBlockView embeds it (fixed height,
// QtCharts legend when the block has no "legend" key).
// Private helpers live in an anonymous namespace with a "bot_" prefix (unity-build safety).
#include "screens/sgi_fa/SgiCommon.h"
#include "screens/sgi_fa/SgiSections.h"

#include "screens/langkinh/LkChart.h"

#include <QDate>
#include <QGridLayout>
#include <QHBoxLayout>
#include <QJsonArray>
#include <QJsonObject>
#include <QLabel>
#include <QList>
#include <QPair>
#include <QSizePolicy>
#include <QStringList>

#include <algorithm>
#include <cmath>
#include <iterator>
#include <utility>

namespace fincept::screens::sgi {

namespace {

constexpr int kBotChartH = 300;    ///< chart height inside a figure card (LkBlockView uses 320 for full-width)
constexpr int kBotBarScale = 1000; ///< stretch units of a track-record half bar
const QString kBotNeed = QStringLiteral("[CẦN DATA]");

// ── Number / text formatting ─────────────────────────────────────────────────

/// Vietnamese number: decimal comma, thousands dot, U+2212 minus, trailing zeros trimmed.
QString bot_fmt(double v, int dec = 2, bool plus = false) {
    if (!std::isfinite(v))
        return {};
    QString s = QString::number(std::abs(v), 'f', dec);
    if (s.contains(QLatin1Char('.'))) {
        while (s.endsWith(QLatin1Char('0')))
            s.chop(1);
        if (s.endsWith(QLatin1Char('.')))
            s.chop(1);
    }
    QString int_part = s.section(QLatin1Char('.'), 0, 0);
    const QString frac = s.section(QLatin1Char('.'), 1);
    for (int i = int_part.size() - 3; i > 0; i -= 3)
        int_part.insert(i, QLatin1Char('.'));
    QString out = frac.isEmpty() ? int_part : int_part + QLatin1Char(',') + frac;
    if (out == QLatin1String("0"))
        return out;
    if (v < 0.0)
        out.prepend(QChar(0x2212));
    else if (plus)
        out.prepend(QLatin1Char('+'));
    return out;
}

/// Display text of a JSON value: strings verbatim (trimmed), numbers Vietnamese-formatted + unit.
QString bot_num(const QJsonValue& v, const QString& unit = {}, bool plus = false) {
    if (v.isString())
        return v.toString().trimmed();
    if (v.isDouble()) {
        const QString n = bot_fmt(v.toDouble(), 2, plus);
        return n.isEmpty() ? QString() : n + unit;
    }
    return {};
}

/// o[key] as display text, preferring a pre-formatted o[key + "_txt"] from the engine.
QString bot_txt(const QJsonObject& o, const char* key, const QString& unit = {}) {
    const QString k = QLatin1String(key);
    const QJsonValue t = o.value(k + QStringLiteral("_txt"));
    if (t.isString() && !t.toString().trimmed().isEmpty())
        return t.toString().trimmed();
    return bot_num(o.value(k), unit);
}

/// ISO date "YYYY-MM-DD" → "dd/MM/yyyy"; anything else verbatim.
QString bot_date(const QString& iso) {
    const QDate d = QDate::fromString(iso.trimmed(), Qt::ISODate);
    return d.isValid() ? d.toString(QStringLiteral("dd/MM/yyyy")) : iso.trimmed();
}

bool bot_is_need(const QString& s) {
    return s.trimmed().isEmpty() || s.trimmed().startsWith(QStringLiteral("[CẦN DATA"));
}

/// Escaped value, or a red "[CẦN DATA]" when empty.
QString bot_or_need_html(const QString& s) {
    if (s.trimmed().isEmpty())
        return span(esc(kBotNeed), col(Role::Down));
    return esc(s);
}

// ── Small widgets ────────────────────────────────────────────────────────────

QLabel* bot_label(QWidget* parent, const QString& html, const QColor& c, int px, bool mono = false,
                  bool bold = false) {
    auto* l = make_label(parent, c, px, Qt::RichText, bold, mono);
    l->setText(html);
    return l;
}

QLabel* bot_plain(QWidget* parent, const QString& text, const QColor& c, int px) {
    auto* l = make_label(parent, c, px, Qt::PlainText);
    l->setText(text);
    return l;
}

/// Uppercase small caption (the artifact's .lbl / eyebrow).
QLabel* bot_eyebrow(QWidget* parent, const QString& text, const QColor& c = QColor()) {
    auto* l = make_label(parent, c.isValid() ? c : col(Role::Muted), 11, Qt::PlainText, true);
    l->setText(text.toUpper());
    return l;
}

/// Muted "[CẦN DATA] <what>" note — a gap that must stay visible.
QLabel* bot_need(QWidget* parent, const QString& what) {
    return bot_label(parent, span(esc(kBotNeed), col(Role::Down), true) + QStringLiteral(" ") + esc(what),
                     col(Role::Muted), 12);
}

/// Grid container with `cols` equal columns.
QGridLayout* bot_grid(QWidget* parent, QWidget*& holder, int cols, int spacing = 12) {
    holder = make_box(parent);
    auto* g = new QGridLayout(holder);
    g->setContentsMargins(0, 0, 0, 0);
    g->setHorizontalSpacing(spacing);
    g->setVerticalSpacing(spacing);
    for (int c = 0; c < cols; ++c)
        g->setColumnStretch(c, 1);
    return g;
}

/// Place `w` at flat index `i`; the last item of an odd row spans the rest when `span_last`.
void bot_place(QGridLayout* g, int cols, int i, int n, QWidget* w, bool span_last = false) {
    const int r = i / cols;
    const int c = i % cols;
    if (span_last && i == n - 1 && c < cols - 1)
        g->addWidget(w, r, c, 1, cols - c);
    else
        g->addWidget(w, r, c);
}

/// Card with a serif title and a plain-text body ("[CẦN DATA]" when the body is empty).
QFrame* bot_text_card(QWidget* parent, const QString& title, const QString& body, const QColor& accent = QColor()) {
    QVBoxLayout* lay = nullptr;
    QFrame* card = make_card(parent, lay, accent);
    auto* t = bot_plain(card, title, col(Role::Ink), 15);
    t->setStyleSheet(QStringLiteral("QLabel { color:%1; %2 background:transparent; }")
                         .arg(css(col(Role::Ink)), lk::lk_font_css(lk::lk_font_serif(15, 600))));
    lay->addWidget(t);
    if (body.trimmed().isEmpty())
        lay->addWidget(bot_need(card, QStringLiteral("bản tuần không ghi mục này")));
    else
        lay->addWidget(bot_plain(card, body.trimmed(), col(Role::Ink2), 13));
    lay->addStretch(1);
    return card;
}

// ── Tables (QGridLayout of labels) ───────────────────────────────────────────

struct BotTable {
    QFrame* frame = nullptr;
    QGridLayout* grid = nullptr;
    int cols = 0;
    int row = 0; ///< next free grid row
};

QString bot_cell_css(const QColor& c, const QFont& f, const QColor& bg = QColor()) {
    return QStringLiteral("QLabel { color:%1; %2 background:%3; padding:7px 10px; border:none;"
                          " border-bottom:1px solid %4; }")
        .arg(css(c), lk::lk_font_css(f), bg.isValid() ? css(bg) : QStringLiteral("transparent"),
             css(col(Role::Line)));
}

BotTable bot_table(QWidget* parent, const QStringList& heads, const QList<int>& stretch) {
    BotTable t;
    t.frame = new QFrame(parent);
    t.frame->setObjectName(QStringLiteral("sgiTable"));
    t.frame->setAttribute(Qt::WA_StyledBackground, true);
    t.frame->setStyleSheet(QStringLiteral("QFrame#sgiTable { background:%1; border:1px solid %2; border-radius:4px; }")
                               .arg(css(col(Role::Surface)), css(col(Role::Line))));
    t.grid = new QGridLayout(t.frame);
    t.grid->setContentsMargins(1, 1, 1, 1);
    t.grid->setSpacing(0);
    t.cols = static_cast<int>(heads.size());
    for (int c = 0; c < t.cols; ++c) {
        auto* h = new QLabel(t.frame);
        h->setTextFormat(Qt::PlainText);
        h->setWordWrap(true);
        h->setText(heads.at(c).toUpper());
        h->setAlignment(Qt::AlignLeft | Qt::AlignBottom);
        h->setStyleSheet(bot_cell_css(col(Role::Muted), lk::lk_font_sans(11, 600), col(Role::Surface2)));
        t.grid->addWidget(h, 0, c);
        t.grid->setColumnStretch(c, stretch.value(c, 1));
    }
    t.row = 1;
    return t;
}

/// One rich-text cell of the current row. `html` must already be escaped.
QLabel* bot_cell(BotTable& t, int c, const QString& html, const QColor& color, int px = 13, bool mono = false,
                 bool wrap = true) {
    auto* l = new QLabel(t.frame);
    l->setTextFormat(Qt::RichText);
    l->setWordWrap(wrap);
    l->setTextInteractionFlags(Qt::TextSelectableByMouse);
    l->setAlignment(Qt::AlignLeft | Qt::AlignTop);
    l->setStyleSheet(bot_cell_css(color, mono ? lk::lk_font_mono(px, 500) : lk::lk_font_sans(px, 400)));
    l->setText(html);
    t.grid->addWidget(l, t.row, c);
    return l;
}

/// Full-width group row inside a table (e.g. "NEO BÊN NGOÀI").
void bot_subhead(BotTable& t, const QString& text) {
    auto* l = new QLabel(t.frame);
    l->setTextFormat(Qt::PlainText);
    l->setWordWrap(true);
    l->setText(text.toUpper());
    l->setStyleSheet(bot_cell_css(col(Role::Amber), lk::lk_font_sans(11, 700), col(Role::Surface2)));
    t.grid->addWidget(l, t.row, 0, 1, t.cols);
    ++t.row;
}

// ── Shared pieces ────────────────────────────────────────────────────────────

/// "● Đỏ" style light cell from a data colour key.
QString bot_den_html(const QString& den) {
    const QString k = den.trimmed().toLower();
    QString name;
    if (k == QLatin1String("xanh"))
        name = QStringLiteral("Xanh");
    else if (k == QLatin1String("vang"))
        name = QStringLiteral("Vàng");
    else if (k == QLatin1String("do"))
        name = QStringLiteral("Đỏ");
    else if (k == QLatin1String("xam"))
        name = QStringLiteral("Xám");
    if (name.isEmpty())
        return k.isEmpty() ? span(QStringLiteral("—"), col(Role::Muted)) : span(esc(den.trimmed()), col(Role::Muted));
    const QColor c = light_color(k);
    return span(QStringLiteral("●"), c) + QStringLiteral("&nbsp;") + span(esc(name), c, true);
}

/// Value colour of a tile: the light colour, or ink when the tile carries no meaningful light.
QColor bot_value_color(const QString& mau) {
    const QString k = mau.trimmed().toLower();
    if (k == QLatin1String("xanh") || k == QLatin1String("vang") || k == QLatin1String("do"))
        return light_color(k);
    return col(Role::Ink);
}

/// One evidence tile (issue tile or live tile — live tiles get a dashed blue edge and a LIVE pill).
QFrame* bot_tile(QWidget* parent, const QJsonObject& t, bool live) {
    auto* card = new QFrame(parent);
    card->setObjectName(QStringLiteral("sgiTile"));
    card->setAttribute(Qt::WA_StyledBackground, true);
    const QColor edge = live ? soft_on_surface(col(Role::Blue), 0.7) : col(Role::Line);
    card->setStyleSheet(QStringLiteral("QFrame#sgiTile { background:%1; border:1px %2 %3; border-radius:4px; }")
                            .arg(css(col(Role::Surface)), live ? QStringLiteral("dashed") : QStringLiteral("solid"),
                                 css(edge)));
    auto* lay = new QVBoxLayout(card);
    lay->setContentsMargins(14, 12, 14, 12);
    lay->setSpacing(5);

    const QString nhan = str(t, "nhan");
    QString head = esc((nhan.isEmpty() ? QStringLiteral("—") : nhan).toUpper());
    if (live)
        head = pill_html(QStringLiteral("LIVE"), col(Role::Blue), 10) + QStringLiteral("&nbsp; ") + head;
    lay->addWidget(bot_label(card, head, col(Role::Muted), 11, false, true));

    const QString val = bot_txt(t, "gia_tri");
    if (bot_is_need(val))
        lay->addWidget(bot_label(card, span(esc(kBotNeed), col(Role::Down), true), col(Role::Down), 18, true));
    else // long values ("+0,76 điểm %", "−3.115,5 tỷ đ") step down so a narrow 4-column tile does not orphan the unit
        lay->addWidget(bot_label(card, esc(val), bot_value_color(str(t, "mau")),
                                 val.size() <= 7 ? 26 : (val.size() <= 10 ? 22 : 18), true));

    const QString note = str(t, "ghi_chu");
    if (!note.trimmed().isEmpty())
        lay->addWidget(bot_plain(card, note.trimmed(), col(Role::Ink2), 12));

    QStringList meta;
    const QString tier = tier_html(str(t, "tier"));
    if (!tier.isEmpty())
        meta << tier;
    const QString ky = str(t, "ky");
    if (!ky.trimmed().isEmpty())
        meta << esc(bot_date(ky));
    const QString nguon = str(t, "nguon");
    if (live && !nguon.trimmed().isEmpty())
        meta << esc(nguon.trimmed());
    lay->addStretch(1);
    if (!meta.isEmpty())
        lay->addWidget(bot_label(card, meta.join(QStringLiteral(" · ")), col(Role::Muted), 11));
    return card;
}

/// Tile grid, 4 columns.
QWidget* bot_tile_grid(QWidget* parent, const QJsonArray& tiles, bool live) {
    QWidget* holder = nullptr;
    QGridLayout* g = bot_grid(parent, holder, 4);
    int i = 0;
    for (const QJsonValue& v : tiles) {
        if (!v.isObject())
            continue;
        bot_place(g, 4, i++, 0, bot_tile(holder, v.toObject(), live));
    }
    return holder;
}

/// Live breadth card (live.do_rong): engine value next to the issue's own figure.
QFrame* bot_breadth_card(QWidget* parent, const QJsonObject& dr) {
    QVBoxLayout* lay = nullptr;
    QFrame* card = make_card(parent, lay, col(Role::Blue));
    const QString tier = str(dr, "tier").trimmed().isEmpty() ? QStringLiteral("EST") : str(dr, "tier");
    auto* title = bot_label(card,
                            esc(QStringLiteral("Độ rộng thị trường — máy tự tính trên kho giá")) +
                                QStringLiteral("&nbsp;&nbsp;") + pill_html(QStringLiteral("LIVE"), col(Role::Blue), 10) +
                                QStringLiteral("&nbsp;") + tier_html(tier),
                            col(Role::Ink), 15);
    title->setStyleSheet(QStringLiteral("QLabel { color:%1; %2 background:transparent; }")
                             .arg(css(col(Role::Ink)), lk::lk_font_css(lk::lk_font_serif(15, 600))));
    lay->addWidget(title);

    QStringList sub;
    const QString uni = bot_txt(dr, "universe");
    sub << (uni.isEmpty() ? span(esc(kBotNeed), col(Role::Down)) : esc(uni));
    const QString ngay = str(dr, "ngay");
    if (!ngay.isEmpty())
        sub << esc(QStringLiteral("phiên ") + bot_date(ngay));
    const QJsonValue drop = dr.value(QStringLiteral("loai_bo"));
    if (drop.isDouble() && drop.toDouble() > 0.0)
        sub << esc(QStringLiteral("đã loại %1 mã/cửa sổ có phiên biến động > 35% (nghi chưa điều chỉnh giá)")
                       .arg(bot_fmt(drop.toDouble(), 0)));
    lay->addWidget(bot_label(card, sub.join(QStringLiteral(" · ")), col(Role::Muted), 12));

    const QJsonObject bt = dr.value(QStringLiteral("ban_tuan")).toObject();
    struct Row {
        const char* key;
        const char* label;
        const char* unit; ///< appended only when the engine sent a raw number instead of "<key>_txt"
    };
    static const Row kRows[] = {
        {"tren_ma200", "% mã trên MA200", "%"},
        {"tren_ma50", "% mã trên MA50", "%"},
        {"vni_ytd", "VN-Index từ đầu năm", "%"},
        {"trung_vi_ytd", "Trung vị cổ phiếu từ đầu năm", "%"},
        {"chenh_dpt", "Chênh chỉ số − trung vị", " đpt"},
        {"danh_bai_250", "% mã đánh bại chỉ số 250 phiên", "%"},
        {"deu_vs_vni_12t", "Bình quân đều vs VN-Index 12 tháng", "%"},
        {"universe", "Rổ tính", ""},
    };
    BotTable t = bot_table(card, {QStringLiteral("Chỉ báo"), QStringLiteral("Máy · live"), QStringLiteral("Bản tuần")},
                           {3, 2, 2});
    for (const Row& r : kRows) {
        const QString live_v = bot_txt(dr, r.key, QString::fromUtf8(r.unit));
        const QString issue_v = bot_txt(bt, r.key);
        bot_cell(t, 0, esc(QString::fromUtf8(r.label)), col(Role::Ink2), 12);
        bot_cell(t, 1, bot_or_need_html(live_v), col(Role::Blue), 13, true);
        bot_cell(t, 2, issue_v.isEmpty() ? span(QStringLiteral("—"), col(Role::Muted)) : esc(issue_v), col(Role::Ink),
                 13, true);
        ++t.row;
    }
    lay->addWidget(t.frame);

    const QString note = str(dr, "ghi_chu");
    if (!note.trimmed().isEmpty())
        lay->addWidget(bot_plain(card, note.trimmed(), col(Role::Muted), 12));
    return card;
}

/// Figure card: serif title, caption, chart (or a [CẦN DATA] note), source line + tier.
QFrame* bot_chart_card(QWidget* parent, const QJsonObject& ch) {
    QVBoxLayout* lay = nullptr;
    QFrame* card = make_card(parent, lay);
    const QString title = str(ch, "tieu_de").trimmed().isEmpty() ? str(ch, "id") : str(ch, "tieu_de");
    auto* t = bot_plain(card, title.trimmed().isEmpty() ? QStringLiteral("—") : title.trimmed(), col(Role::Ink), 15);
    t->setStyleSheet(QStringLiteral("QLabel { color:%1; %2 background:transparent; }")
                         .arg(css(col(Role::Ink)), lk::lk_font_css(lk::lk_font_serif(15, 600))));
    lay->addWidget(t);
    const QString cap = str(ch, "chu_thich");
    if (!cap.trimmed().isEmpty())
        lay->addWidget(bot_plain(card, cap.trimmed(), col(Role::Muted), 12));

    const QJsonObject block = ch.value(QStringLiteral("block")).toObject();
    bool drawn = false;
    if (!block.isEmpty()) {
        auto* chart = new fincept::screens::langkinh::LkLineChart(block, card);
        if (chart->has_data()) {
            chart->setFixedHeight(kBotChartH);
            lay->addWidget(chart);
            drawn = true;
        } else {
            delete chart;
        }
    }
    if (!drawn)
        lay->addWidget(bot_need(card, QStringLiteral("không có điểm dữ liệu hợp lệ để vẽ biểu đồ này")));

    QString src;
    const QString nguon = str(ch, "nguon");
    src = esc(QStringLiteral("Nguồn: ")) + (nguon.trimmed().isEmpty() ? span(esc(kBotNeed), col(Role::Down))
                                                                       : esc(nguon.trimmed()));
    const QString tier = tier_html(str(ch, "tier"));
    if (!tier.isEmpty())
        src += QStringLiteral("&nbsp;&nbsp;") + tier;
    lay->addWidget(bot_label(card, src, col(Role::Muted), 11));
    lay->addStretch(1);
    return card;
}

/// Small horizontal half bar for the track-record strip: `w` in [0, kBotBarScale], anchored to the
/// centre axis (left half grows leftwards).
QWidget* bot_half_bar(QWidget* parent, int w, const QColor& c, bool left_half) {
    auto* half = make_box(parent);
    auto* hl = new QHBoxLayout(half);
    hl->setContentsMargins(0, 0, 0, 0);
    hl->setSpacing(0);
    auto* pad = make_box(half);
    pad->setSizePolicy(QSizePolicy::Expanding, QSizePolicy::Fixed);
    if (w <= 0) {
        hl->addWidget(pad, 1);
        return half;
    }
    auto* bar = new QFrame(half);
    bar->setObjectName(QStringLiteral("sgiBar"));
    bar->setAttribute(Qt::WA_StyledBackground, true);
    bar->setFixedHeight(10);
    bar->setSizePolicy(QSizePolicy::Expanding, QSizePolicy::Fixed);
    bar->setStyleSheet(QStringLiteral("QFrame#sgiBar { background:%1; border:none; }").arg(css(c)));
    const int rest = kBotBarScale - w;
    if (left_half) {
        hl->addWidget(pad, rest);
        hl->addWidget(bar, w);
    } else {
        hl->addWidget(bar, w);
        hl->addWidget(pad, rest);
    }
    return half;
}

/// Action pill colour of the portfolio table.
QColor bot_action_color(const QString& act) {
    const QString u = act.trimmed().toUpper();
    if (u == QStringLiteral("THOÁT"))
        return col(Role::Down);
    if (u == QStringLiteral("GIẢM"))
        return col(Role::Amber);
    if (u == QStringLiteral("THÊM") || u == QStringLiteral("TĂNG"))
        return col(Role::Up);
    return col(Role::Muted); // GIỮ and anything else
}

/// Direction chip of a reversal threshold.
QString bot_huong_html(const QString& huong) {
    const QString h = huong.trimmed().toLower();
    if (h == QLatin1String("dung"))
        return pill_html(QStringLiteral("▲ đúng hướng"), col(Role::Up), 10);
    if (h == QLatin1String("nguoc"))
        return pill_html(QStringLiteral("▼ đi ngược"), col(Role::Down), 10);
    if (h == QLatin1String("xa"))
        return pill_html(QStringLiteral("xa"), col(Role::Muted), 10);
    if (h.isEmpty() || h == QLatin1String("chua_ro"))
        return pill_html(QStringLiteral("chưa rõ hướng"), col(Role::Muted), 10);
    return pill_html(huong.trimmed(), col(Role::Muted), 10);
}

QColor bot_huong_color(const QString& huong) {
    const QString h = huong.trimmed().toLower();
    if (h == QLatin1String("dung"))
        return col(Role::Up);
    if (h == QLatin1String("nguoc"))
        return col(Role::Down);
    return QColor(); // no edge: direction carries no signal
}

/// True when an anchor row is the NEO_NGOAI separator itself ("— NEO BÊN NGOÀI —").
bool bot_is_ext_separator(const QJsonObject& r) {
    const QString name = str(r, "chi_bao").trimmed();
    const QString up = name.toUpper();
    return up.contains(QStringLiteral("NEO BÊN NGOÀI")) ||
           (name.startsWith(QChar(0x2014)) && up.contains(QStringLiteral("NGOÀI")));
}

/// True when an anchor row is marked external by a field ("ngoai": true, or nhom naming NEO_NGOAI).
bool bot_is_ext_row(const QJsonObject& r) {
    if (r.value(QStringLiteral("ngoai")).toBool(false))
        return true;
    const QString nhom = str(r, "nhom").toUpper();
    return nhom.contains(QStringLiteral("NGOAI")) || nhom.contains(QStringLiteral("NGOÀI"));
}

} // namespace

// ── V · Bằng chứng ───────────────────────────────────────────────────────────

QWidget* build_evidence(const QJsonObject& issue, const QJsonObject& live, const QJsonArray& charts, QWidget* parent) {
    QVBoxLayout* body = nullptr;
    QWidget* sec = make_section(parent, QStringLiteral("V"), QStringLiteral("Bằng chứng"),
                                QStringLiteral("Số của bản tuần giữ nguyên nhãn bậc bằng chứng của nó. Số live đọc từ kho "
                                               "máy cục bộ, mang ngày và nguồn riêng — lệch nhau thì hiện cả hai."),
                                body);

    // 1. Issue tiles.
    const QJsonArray tiles = issue.value(QStringLiteral("tiles")).toArray();
    body->addWidget(bot_eyebrow(sec, QStringLiteral("Số của bản tuần")));
    if (tiles.isEmpty())
        body->addWidget(bot_need(sec, QStringLiteral("bản tuần không có ô số nào (issue.tiles)")));
    else
        body->addWidget(bot_tile_grid(sec, tiles, false));

    // 2. Live tiles.
    const QJsonArray ltiles = live.value(QStringLiteral("tiles")).toArray();
    body->addSpacing(6);
    body->addWidget(bot_label(sec,
                              pill_html(QStringLiteral("LIVE"), col(Role::Blue), 10) + QStringLiteral("&nbsp; ") +
                                  esc(QStringLiteral("SỐ LIVE TỪ KHO MÁY")) +
                                  span(esc(QStringLiteral(" · đọc kho cục bộ, không gọi mạng")), col(Role::Muted)),
                              col(Role::Muted), 11, false, true));
    if (ltiles.isEmpty())
        body->addWidget(bot_need(sec, QStringLiteral("không đọc được số live nào từ kho máy (live.tiles)")));
    else
        body->addWidget(bot_tile_grid(sec, ltiles, true));

    // 3. Breadth summary.
    const QJsonObject dr = live.value(QStringLiteral("do_rong")).toObject();
    if (dr.isEmpty())
        body->addWidget(bot_need(sec, QStringLiteral("độ rộng live chưa tính được (live.do_rong) — kho giá vnstore thiếu "
                                                     "hoặc không mở được")));
    else
        body->addWidget(bot_breadth_card(sec, dr));

    // 4. Charts, 2 columns.
    body->addSpacing(6);
    body->addWidget(bot_eyebrow(sec, QStringLiteral("Biểu đồ")));
    QList<QJsonObject> figs;
    for (const QJsonValue& v : charts)
        if (v.isObject())
            figs << v.toObject();
    if (figs.isEmpty()) {
        body->addWidget(bot_need(sec, QStringLiteral("chưa có biểu đồ nào — dữ liệu chuỗi live thiếu (xem cảnh báo ở cuối trang)")));
    } else {
        QWidget* holder = nullptr;
        QGridLayout* g = bot_grid(sec, holder, 2, 16);
        const int n = static_cast<int>(figs.size());
        for (int i = 0; i < n; ++i)
            bot_place(g, 2, i, n, bot_chart_card(holder, figs.at(i)), true);
        body->addWidget(holder);
    }
    return sec;
}

// ── VI · Neo lịch sử ─────────────────────────────────────────────────────────

QWidget* build_anchors(const QJsonArray& neo, QWidget* parent) {
    QVBoxLayout* body = nullptr;
    QWidget* sec = make_section(parent, QStringLiteral("VI"), QStringLiteral("Neo lịch sử — số hôm nay đứng ở đâu"),
                                QString(), body);
    body->addWidget(bot_label(sec,
                              tier_html(QStringLiteral("SS-T3")) + QStringLiteral("&nbsp; ") +
                                  esc(QStringLiteral("Ba cột neo là SS-T3 chép từ báo cáo SGI gốc — không phải dữ liệu "
                                                     "hiện hành.")),
                              col(Role::Muted), 12));
    if (neo.isEmpty()) {
        body->addWidget(bot_need(sec, QStringLiteral("bảng neo trống (payload neo)")));
        return sec;
    }

    BotTable t = bot_table(sec,
                           {QStringLiteral("Chỉ báo"), QStringLiteral("Hiện tại · kỳ"), QStringLiteral("Đèn"),
                            QStringLiteral("Nhãn"), QStringLiteral("Lành mạnh"), QStringLiteral("Cảnh báo"),
                            QStringLiteral("Đỉnh chu kỳ / tiền lệ")},
                           {4, 3, 2, 2, 2, 2, 4});
    bool ext_open = false;
    int n_rows = 0;
    int n_have = 0;
    for (const QJsonValue& v : neo) {
        if (!v.isObject())
            continue;
        const QJsonObject r = v.toObject();
        if (bot_is_ext_separator(r)) {
            if (!ext_open)
                bot_subhead(t, QStringLiteral("Neo bên ngoài"));
            ext_open = true;
            continue;
        }
        if (!ext_open && bot_is_ext_row(r)) {
            bot_subhead(t, QStringLiteral("Neo bên ngoài"));
            ext_open = true;
        }
        ++n_rows;

        const QString name = str(r, "chi_bao");
        bot_cell(t, 0, name.trimmed().isEmpty() ? span(QStringLiteral("—"), col(Role::Muted)) : esc(name.trimmed()),
                 col(Role::Ink), 13, false);

        const QString now = bot_txt(r, "hien_tai");
        QString now_html;
        if (bot_is_need(now)) {
            now_html = span(esc(kBotNeed), col(Role::Down), true);
        } else {
            ++n_have;
            now_html = span(esc(now), col(Role::Ink), true);
        }
        QStringList sub;
        const QString ky = str(r, "ky");
        if (!ky.trimmed().isEmpty())
            sub << esc(bot_date(ky));
        const QString src = str(r, "nguon_hien_tai").trimmed();
        if (src == QLatin1String("live"))
            sub << span(QStringLiteral("LIVE"), col(Role::Blue), true);
        else if (!src.isEmpty())
            sub << esc(src);
        if (!sub.isEmpty())
            now_html += QStringLiteral("<br><span style=\"font-size:11px; color:%1;\">%2</span>")
                            .arg(css(col(Role::Muted)), sub.join(QStringLiteral(" · ")));
        bot_cell(t, 1, now_html, col(Role::Ink), 13, true);

        bot_cell(t, 2, bot_den_html(str(r, "den")), col(Role::Ink), 12, false, false);
        const QString tier = tier_html(str(r, "tier"));
        bot_cell(t, 3, tier.isEmpty() ? span(QStringLiteral("—"), col(Role::Muted)) : tier, col(Role::Ink), 12, false,
                 false);

        const auto anchor = [&r](const char* key) {
            const QString s = str(r, key).trimmed();
            return s.isEmpty() ? QStringLiteral("—") : esc(s);
        };
        bot_cell(t, 4, anchor("lanh_manh"), col(Role::Muted), 12);
        bot_cell(t, 5, anchor("canh_bao"), col(Role::Muted), 12);
        bot_cell(t, 6, anchor("dinh"), col(Role::Muted), 12);
        ++t.row;
    }
    body->addWidget(t.frame);
    body->addWidget(bot_label(sec,
                              esc(QStringLiteral("%1/%2 neo có số hiện tại; phần còn lại là [CẦN DATA].")
                                      .arg(n_have)
                                      .arg(n_rows)),
                              col(Role::Muted), 11));
    return sec;
}

// ── VII · Ngưỡng đảo chiều ───────────────────────────────────────────────────

QWidget* build_thresholds(const QJsonArray& nguong, QWidget* parent) {
    QVBoxLayout* body = nullptr;
    QWidget* sec = make_section(parent, QStringLiteral("VII"), QStringLiteral("Ngưỡng đảo chiều"),
                                QStringLiteral("Ngưỡng, trạng thái và hướng là của bản tuần. Ô LIVE là số kho máy đo lại, "
                                               "mang ngày và nguồn riêng."),
                                body);
    QList<QJsonObject> rows;
    for (const QJsonValue& v : nguong)
        if (v.isObject())
            rows << v.toObject();
    if (rows.isEmpty()) {
        body->addWidget(bot_need(sec, QStringLiteral("bản tuần không có ngưỡng đảo chiều nào (nguong_dao_chieu)")));
        return sec;
    }

    QWidget* holder = nullptr;
    QGridLayout* g = bot_grid(sec, holder, 3);
    const int n = static_cast<int>(rows.size());
    for (int i = 0; i < n; ++i) {
        const QJsonObject& r = rows.at(i);
        QVBoxLayout* lay = nullptr;
        QFrame* card = make_card(holder, lay, bot_huong_color(str(r, "huong")));

        const QString nhom = str(r, "nhom");
        if (!nhom.trimmed().isEmpty())
            lay->addWidget(bot_eyebrow(card, nhom.trimmed()));
        const QString ten = str(r, "ten");
        lay->addWidget(bot_label(card, ten.trimmed().isEmpty() ? span(esc(kBotNeed), col(Role::Down)) : esc(ten.trimmed()),
                                 col(Role::Amber), 18, true));

        const QString st = str(r, "trang_thai").trimmed();
        lay->addWidget(bot_label(card,
                                 pill_html(st.isEmpty() ? kBotNeed : st, status_color(st), 10) + QStringLiteral("&nbsp;") +
                                     bot_huong_html(str(r, "huong")),
                                 col(Role::Ink), 12));

        const QString now = str(r, "hien_tai");
        QString now_html = esc(QStringLiteral("Hiện tại: ")) +
                           (now.trimmed().isEmpty() ? span(esc(kBotNeed), col(Role::Down), true)
                                                    : QStringLiteral("<span style='%1'>%2</span>")
                                                          .arg(mono_css(13, 600), esc(now.trimmed())));
        const QString keo = str(r, "keo_dai");
        if (!keo.trimmed().isEmpty())
            now_html += span(esc(QStringLiteral(" · duy trì ") + keo.trimmed()), col(Role::Muted));
        lay->addWidget(bot_label(card, now_html, col(Role::Ink), 12));

        const QString note = str(r, "ghi_chu");
        if (!note.trimmed().isEmpty()) {
            // 12.5px in the artifact; lk fonts take whole pixels, so 13px keeps the sans family.
            lay->addWidget(bot_plain(card, note.trimmed(), col(Role::Ink2), 13));
        }

        // LIVE box — only when the engine merged a live check into this row.
        const bool has_live = r.contains(QStringLiteral("live_txt")) || r.contains(QStringLiteral("live_trang_thai")) ||
                              r.contains(QStringLiteral("live_v"));
        const QString live_key = str(r, "live").trimmed();
        if (has_live) {
            auto* box = new QFrame(card);
            box->setObjectName(QStringLiteral("sgiLiveBox"));
            box->setAttribute(Qt::WA_StyledBackground, true);
            box->setStyleSheet(
                QStringLiteral("QFrame#sgiLiveBox { background:%1; border:1px dashed %2; border-radius:3px; }")
                    .arg(css(soft_on_surface(col(Role::Blue), 0.08)), css(soft_on_surface(col(Role::Blue), 0.7))));
            auto* bl = new QVBoxLayout(box);
            bl->setContentsMargins(8, 6, 8, 6);
            bl->setSpacing(3);
            QStringList parts;
            parts << pill_html(QStringLiteral("LIVE"), col(Role::Blue), 10);
            const QString lv = str(r, "live_txt").trimmed().isEmpty() ? bot_num(r.value(QStringLiteral("live_v")))
                                                                       : str(r, "live_txt").trimmed();
            parts << (lv.isEmpty() ? span(esc(kBotNeed), col(Role::Down), true)
                                   : QStringLiteral("<span style='%1 color:%2;'>%3</span>")
                                         .arg(mono_css(13, 600), css(col(Role::Ink)), esc(lv)));
            const QString lst = str(r, "live_trang_thai").trimmed();
            if (!lst.isEmpty())
                parts << pill_html(lst, status_color(lst), 10);
            const QString lsrc = str(r, "live_nguon").trimmed();
            if (!lsrc.isEmpty())
                parts << span(esc(lsrc), col(Role::Muted));
            const QString ltier = tier_html(str(r, "live_tier"));
            if (!ltier.isEmpty())
                parts << ltier;
            bl->addWidget(bot_label(box, parts.join(QStringLiteral(" · ")), col(Role::Ink), 12));
            const QString lnote = str(r, "live_ghi_chu");
            if (!lnote.trimmed().isEmpty())
                bl->addWidget(bot_plain(box, lnote.trimmed(), col(Role::Muted), 11));
            lay->addWidget(box);
        } else if (!live_key.isEmpty() && live_key != QLatin1String("null")) {
            lay->addWidget(bot_need(card, QStringLiteral("kho máy chưa có số live cho ngưỡng này (%1)").arg(live_key)));
        }
        lay->addStretch(1);
        bot_place(g, 3, i, n, card);
    }
    body->addWidget(holder);
    return sec;
}

// ── VIII · Hàm ý danh mục ────────────────────────────────────────────────────

QWidget* build_portfolio(const QJsonObject& danh_muc, QWidget* parent) {
    QVBoxLayout* body = nullptr;
    QWidget* sec = make_section(parent, QStringLiteral("VIII"), QStringLiteral("Hàm ý danh mục"), QString(), body);

    // Always visible, whatever the payload holds.
    auto* warn = bot_label(sec,
                           span(esc(QStringLiteral("Bản tuần của chủ hệ — tham khảo, KHÔNG phải khuyến nghị mua/bán.")),
                                col(Role::Amber), true),
                           col(Role::Amber), 13);
    body->addWidget(warn);

    const QString tieu_de = str(danh_muc, "tieu_de");
    if (!tieu_de.trimmed().isEmpty()) {
        auto* t = bot_plain(sec, tieu_de.trimmed(), col(Role::Ink), 16);
        t->setStyleSheet(QStringLiteral("QLabel { color:%1; %2 background:transparent; }")
                             .arg(css(col(Role::Ink)), lk::lk_font_css(lk::lk_font_serif(16, 600))));
        body->addWidget(t);
    }
    const QString tom_tat = str(danh_muc, "tom_tat");
    if (!tom_tat.trimmed().isEmpty())
        body->addWidget(bot_plain(sec, tom_tat.trimmed(), col(Role::Ink2), 13));

    const QJsonArray dong = danh_muc.value(QStringLiteral("dong")).toArray();
    if (dong.isEmpty()) {
        body->addWidget(bot_need(sec, QStringLiteral("bản tuần không có bảng danh mục (danh_muc.dong)")));
    } else {
        // Headers as the issue prints them (danh_muc.cot, issue v7+: the second column became "Kỳ trước").
        QStringList heads = {QStringLiteral("Mã"), QStringLiteral("Hiện tại"), QStringLiteral("Trục vĩ mô chi phối"),
                             QStringLiteral("Hành động"), QStringLiteral("Đề xuất")};
        const QJsonArray cot = danh_muc.value(QStringLiteral("cot")).toArray();
        if (cot.size() == heads.size())
            for (int i = 0; i < heads.size(); ++i)
                if (const QString c = cot.at(i).toString().trimmed(); !c.isEmpty())
                    heads[i] = c;
        BotTable t = bot_table(sec, heads, {2, 1, 8, 1, 1});
        for (const QJsonValue& v : dong) {
            if (!v.isObject())
                continue;
            const QJsonObject r = v.toObject();
            const QString ma = str(r, "ma").trimmed();
            bot_cell(t, 0, ma.isEmpty() ? span(QStringLiteral("—"), col(Role::Muted)) : esc(ma), col(Role::Ink), 13,
                     true);
            bot_cell(t, 1, bot_or_need_html(bot_num(r.value(QStringLiteral("hien_tai")), QStringLiteral("%"))),
                     col(Role::Ink2), 13, true, false);
            const QString truc = str(r, "truc").trimmed();
            bot_cell(t, 2, truc.isEmpty() ? span(QStringLiteral("—"), col(Role::Muted)) : esc(truc), col(Role::Ink2),
                     12);
            const QString act = str(r, "hanh_dong").trimmed();
            bot_cell(t, 3, act.isEmpty() ? span(QStringLiteral("—"), col(Role::Muted)) : pill_html(act, bot_action_color(act)),
                     col(Role::Ink), 12, false, false);
            bot_cell(t, 4, bot_or_need_html(bot_num(r.value(QStringLiteral("de_xuat")), QStringLiteral("%"))),
                     col(Role::Ink), 13, true, false);
            ++t.row;
        }
        body->addWidget(t.frame);
    }

    QWidget* holder = nullptr;
    QGridLayout* g = bot_grid(sec, holder, 2);
    g->addWidget(bot_text_card(holder, QStringLiteral("Vì sao"), str(danh_muc, "vi_sao")), 0, 0);
    g->addWidget(bot_text_card(holder, QStringLiteral("Điều kiện mua lại — viết trước, không tranh luận sau"),
                               str(danh_muc, "dieu_kien_mua_lai"), col(Role::Blue)),
                 0, 1);
    body->addWidget(holder);
    return sec;
}

// ── IX · Track record ────────────────────────────────────────────────────────

QWidget* build_track_record(const QJsonObject& track_record, QWidget* parent) {
    QVBoxLayout* body = nullptr;
    QWidget* sec = make_section(parent, QStringLiteral("IX"), QStringLiteral("Track record của chính khung này"),
                                QString(), body);
    const QJsonArray dong = track_record.value(QStringLiteral("dong")).toArray();
    QList<QJsonObject> rows;
    for (const QJsonValue& v : dong)
        if (v.isObject())
            rows << v.toObject();

    if (rows.isEmpty()) {
        body->addWidget(bot_need(sec, QStringLiteral("bản tuần không có bảng hiệu suất (track_record.dong)")));
    } else {
        BotTable t = bot_table(sec,
                               {QStringLiteral("Năm"), QStringLiteral("Tiền mặt BQ"), QStringLiteral("Quỹ"),
                                QStringLiteral("VN-Index"), QStringLiteral("Chênh")},
                               {2, 2, 2, 2, 2});
        double max_abs = 0.0;
        for (const QJsonObject& r : rows) {
            const QJsonValue c = r.value(QStringLiteral("chenh"));
            if (c.isDouble() && std::isfinite(c.toDouble()))
                max_abs = std::max(max_abs, std::abs(c.toDouble()));
            bot_cell(t, 0, bot_or_need_html(bot_num(r.value(QStringLiteral("nam")))), col(Role::Ink), 13, true, false);
            bot_cell(t, 1, bot_or_need_html(bot_num(r.value(QStringLiteral("tien_mat")), QStringLiteral("%"))),
                     col(Role::Ink2), 13, true, false);
            const auto ret = [&t](int c_idx, const QJsonValue& v) {
                const QString s = bot_num(v, QStringLiteral("%"), true);
                const QColor c = v.isDouble() ? sign_color(v.toDouble()) : col(Role::Ink);
                bot_cell(t, c_idx, s.isEmpty() ? span(esc(kBotNeed), col(Role::Down)) : span(esc(s), c), col(Role::Ink),
                         13, true, false);
            };
            ret(2, r.value(QStringLiteral("quy")));
            ret(3, r.value(QStringLiteral("vni")));
            const QString cs = bot_num(c, QStringLiteral(" đpt"), true);
            bot_cell(t, 4,
                     cs.isEmpty() ? span(esc(kBotNeed), col(Role::Down))
                                  : span(esc(cs), c.isDouble() ? sign_color(c.toDouble()) : col(Role::Ink), true),
                     col(Role::Ink), 13, true, false);
            ++t.row;
        }
        body->addWidget(t.frame);

        // Bar strip: one row per year, |chênh| proportional, negative leftwards (down), positive rightwards (up).
        if (max_abs > 0.0) {
            QVBoxLayout* lay = nullptr;
            QFrame* card = make_card(sec, lay);
            lay->setSpacing(4);
            lay->addWidget(bot_eyebrow(card, QStringLiteral("Chênh hiệu suất quỹ − VN-Index (điểm phần trăm)")));
            for (const QJsonObject& r : rows) {
                const QJsonValue c = r.value(QStringLiteral("chenh"));
                auto* row = make_box(card);
                auto* hl = new QHBoxLayout(row);
                hl->setContentsMargins(0, 0, 0, 0);
                hl->setSpacing(0);
                QString yr = esc(bot_num(r.value(QStringLiteral("nam"))));
                const QString cash = bot_num(r.value(QStringLiteral("tien_mat")), QStringLiteral("%"));
                if (!cash.isEmpty())
                    yr += span(esc(QStringLiteral(" · ") + cash + QStringLiteral(" tiền")), col(Role::Muted));
                auto* yl = bot_label(row, yr, col(Role::Ink), 12, true);
                yl->setWordWrap(false);
                yl->setFixedWidth(150);
                hl->addWidget(yl);

                int w = 0;
                double val = 0.0;
                if (c.isDouble() && std::isfinite(c.toDouble())) {
                    val = c.toDouble();
                    w = static_cast<int>(std::lround(std::abs(val) / max_abs * kBotBarScale));
                    if (val != 0.0)
                        w = std::clamp(w, 8, kBotBarScale); // keep tiny gaps visible
                }
                hl->addWidget(bot_half_bar(row, val < 0.0 ? w : 0, col(Role::Down), true), 1);
                auto* axis = new QFrame(row);
                axis->setObjectName(QStringLiteral("sgiAxis"));
                axis->setAttribute(Qt::WA_StyledBackground, true);
                axis->setFixedSize(1, 16);
                axis->setStyleSheet(QStringLiteral("QFrame#sgiAxis { background:%1; border:none; }").arg(css(col(Role::Line2))));
                hl->addWidget(axis);
                hl->addWidget(bot_half_bar(row, val > 0.0 ? w : 0, col(Role::Up), false), 1);

                const QString cs = bot_num(c, QString(), true);
                auto* vl = bot_label(row,
                                     cs.isEmpty() ? span(esc(kBotNeed), col(Role::Down))
                                                  : span(esc(cs), c.isDouble() ? sign_color(val) : col(Role::Ink), true),
                                     col(Role::Ink), 12, true);
                vl->setWordWrap(false);
                vl->setFixedWidth(90);
                vl->setAlignment(Qt::AlignRight | Qt::AlignVCenter);
                hl->addWidget(vl);
                lay->addWidget(row);
            }
            body->addWidget(card);
        }
    }

    // Reading cards: the three core ones always (gaps visible), the two optional ones when stated.
    struct Card {
        const char* key;
        const char* title;
        bool core;
    };
    static const Card kCards[] = {
        {"doc", "Đọc bảng", true},
        {"gia_tri", "Nơi khung tạo giá trị", false},
        {"pha_huy", "Nơi khung phá huỷ giá trị", false},
        {"that_bai", "Chế độ thất bại lặp lại", true},
        {"he_qua", "Hệ quả cho cách dùng bản tuần", true},
    };
    QList<QFrame*> cards;
    QWidget* holder = nullptr;
    QGridLayout* g = bot_grid(sec, holder, 2);
    for (const Card& c : kCards) {
        const QString text = str(track_record, c.key);
        if (!c.core && text.trimmed().isEmpty())
            continue;
        const QColor accent = QLatin1String(c.key) == QLatin1String("that_bai") ? col(Role::Down) : QColor();
        cards << bot_text_card(holder, QString::fromUtf8(c.title), text, accent);
    }
    const int n = static_cast<int>(cards.size());
    for (int i = 0; i < n; ++i)
        bot_place(g, 2, i, n, cards.at(i), true);
    body->addWidget(holder);

    const QString nguon = str(track_record, "nguon");
    if (!nguon.trimmed().isEmpty())
        body->addWidget(bot_label(sec, esc(QStringLiteral("Nguồn: ") + nguon.trimmed()), col(Role::Muted), 11));
    return sec;
}

// ── X · Nghịch đảo ───────────────────────────────────────────────────────────

QWidget* build_inversion(const QJsonObject& nghich_dao, QWidget* parent) {
    QVBoxLayout* body = nullptr;
    QWidget* sec = make_section(parent, QStringLiteral("X"), QStringLiteral("Nghịch đảo — khung này đang sai ở đâu"),
                                QString(), body);

    // Quote card (blockquote style): accepts {"text","nguon"} or a bare string.
    const QJsonValue q = nghich_dao.value(QStringLiteral("trich_dan"));
    QString qt;
    QString qs;
    if (q.isObject()) {
        qt = str(q.toObject(), "text");
        qs = str(q.toObject(), "nguon");
    } else if (q.isString()) {
        qt = q.toString();
    }
    if (!qt.trimmed().isEmpty()) {
        auto* card = new QFrame(sec);
        card->setObjectName(QStringLiteral("sgiQuote"));
        card->setAttribute(Qt::WA_StyledBackground, true);
        card->setStyleSheet(QStringLiteral("QFrame#sgiQuote { background:%1; border:1px solid %2; border-left:3px solid %3;"
                                           " border-radius:4px; }")
                                .arg(css(col(Role::Surface2)), css(col(Role::Line2)), css(col(Role::Amber))));
        auto* lay = new QVBoxLayout(card);
        lay->setContentsMargins(18, 14, 18, 14);
        lay->setSpacing(6);
        auto* ql = bot_plain(card, QStringLiteral("“%1”").arg(qt.trimmed()), col(Role::Ink), 16);
        ql->setStyleSheet(QStringLiteral("QLabel { color:%1; %2 font-style:italic; background:transparent; }")
                              .arg(css(col(Role::Ink)), lk::lk_font_css(lk::lk_font_serif(16, 400))));
        lay->addWidget(ql);
        lay->addWidget(bot_plain(card,
                                 QStringLiteral("— ") + (qs.trimmed().isEmpty() ? kBotNeed : qs.trimmed()),
                                 col(Role::Muted), 12));
        body->addWidget(card);
    } else {
        body->addWidget(bot_need(sec, QStringLiteral("bản tuần không có trích dẫn phản biện")));
    }

    struct Card {
        const char* key;
        const char* title;
    };
    static const Card kCards[] = {
        {"chi_phi", "Chi phí đang trả"},
        {"co_che_bi_bac", "Cơ chế vừa bị bác bỏ"},
        {"tin_hieu_nguoc", "Tín hiệu ngược"},
        {"tu_nghich_dao", "Tự nghịch đảo"},
        {"pre_mortem", "Pre-mortem"},
    };
    QWidget* holder = nullptr;
    QGridLayout* g = bot_grid(sec, holder, 2);
    const int n = static_cast<int>(std::size(kCards));
    for (int i = 0; i < n; ++i) {
        const Card& c = kCards[i];
        const QColor accent = QLatin1String(c.key) == QLatin1String("pre_mortem") ? col(Role::Amber) : QColor();
        bot_place(g, 2, i, n, bot_text_card(holder, QString::fromUtf8(c.title), str(nghich_dao, c.key), accent), true);
    }
    body->addWidget(holder);

    const QString next = str(nghich_dao, "ra_soat_tiep");
    body->addWidget(bot_label(sec,
                              span(esc(QStringLiteral("Rà soát bắt buộc tiếp theo: ")), col(Role::Amber), true) +
                                  (next.trimmed().isEmpty() ? span(esc(kBotNeed), col(Role::Down), true)
                                                            : QStringLiteral("<span style='%1 color:%2;'>%3</span>")
                                                                  .arg(mono_css(14, 600), css(col(Role::Amber)),
                                                                       esc(bot_date(next)))),
                              col(Role::Amber), 14));
    return sec;
}

// ── Footer · nguồn, cảnh báo, kiểm kỳ sau ────────────────────────────────────

QWidget* build_sources(const QJsonObject& meta, const QJsonObject& issue, QWidget* parent) {
    QVBoxLayout* body = nullptr;
    QWidget* sec = make_section(parent, QString(), QStringLiteral("Nguồn · cảnh báo · kiểm kỳ sau"), QString(), body);

    // 1. Issue sources grouped by evidence tier (strongest first; unknown tiers keep their own group).
    const QJsonArray nguon = issue.value(QStringLiteral("nguon")).toArray();
    body->addWidget(bot_eyebrow(sec, QStringLiteral("Nguồn của bản tuần")));
    if (nguon.isEmpty()) {
        body->addWidget(bot_need(sec, QStringLiteral("bản tuần không liệt kê nguồn (issue.nguon)")));
    } else {
        static const char* const kOrder[] = {"FACT-T1", "FACT-T2", "SS-T3", "EST", "NEWS", "UNVERIFIED", "CẦN DATA"};
        QStringList groups;
        for (const char* k : kOrder)
            groups << QString::fromUtf8(k);
        QList<QPair<QString, QStringList>> other; // raw tier text → items (order of first appearance)
        QList<QStringList> known(groups.size());
        for (const QJsonValue& v : nguon) {
            QString tier;
            QString text;
            if (v.isObject()) {
                tier = str(v.toObject(), "tier").trimmed();
                text = str(v.toObject(), "mo_ta").trimmed();
            } else if (v.isString()) {
                text = v.toString().trimmed();
            }
            if (text.isEmpty())
                continue;
            const int gi = static_cast<int>(groups.indexOf(lk::lk_tier_key(tier)));
            if (gi >= 0) {
                known[gi] << text;
                continue;
            }
            const QString key = tier.isEmpty() ? QStringLiteral("—") : tier;
            auto it = std::find_if(other.begin(), other.end(), [&key](const auto& p) { return p.first == key; });
            if (it == other.end())
                other.append({key, {text}});
            else
                it->second << text;
        }
        const auto add_group = [&](const QString& tier, const QStringList& items) {
            if (items.isEmpty())
                return;
            QVBoxLayout* lay = nullptr;
            QFrame* card = make_card(sec, lay, tier_color(tier));
            lay->addWidget(bot_label(card, tier == QStringLiteral("—") ? pill_html(QStringLiteral("CHƯA GẮN BẬC"), col(Role::Down))
                                                                         : tier_html(tier, 11),
                                     col(Role::Ink), 12));
            for (const QString& it : items)
                lay->addWidget(bot_plain(card, it, col(Role::Ink2), 12));
            body->addWidget(card);
        };
        for (int i = 0; i < groups.size(); ++i)
            add_group(groups.at(i), known.at(i));
        for (const auto& p : std::as_const(other))
            add_group(p.first, p.second);
    }

    // 2. Live sources of this run.
    const QJsonArray live = meta.value(QStringLiteral("sources_live")).toArray();
    body->addWidget(bot_eyebrow(sec, QStringLiteral("Nguồn live của lần chạy này (kho cục bộ, không gọi mạng)")));
    if (live.isEmpty()) {
        body->addWidget(bot_need(sec, QStringLiteral("không có nguồn live nào được ghi nhận (meta.sources_live)")));
    } else {
        QVBoxLayout* lay = nullptr;
        QFrame* card = make_card(sec, lay);
        for (const QJsonValue& v : live) {
            if (!v.isObject())
                continue;
            const QJsonObject s = v.toObject();
            const bool ok = s.value(QStringLiteral("ok")).toBool(false);
            QString html = span(ok ? QStringLiteral("✓") : QStringLiteral("✗"), ok ? col(Role::Up) : col(Role::Down), true) +
                           QStringLiteral("&nbsp; ") + span(esc(str(s, "ten").trimmed()), col(Role::Ink), true);
            const QString as_of = str(s, "as_of").trimmed();
            html += span(esc(QStringLiteral(" · đến ") + (as_of.isEmpty() ? kBotNeed : bot_date(as_of))),
                         as_of.isEmpty() ? col(Role::Down) : col(Role::Ink2));
            const QString tier = tier_html(str(s, "tier"));
            if (!tier.isEmpty())
                html += QStringLiteral("&nbsp; ") + tier;
            const QString path = str(s, "duong_dan").trimmed();
            if (!path.isEmpty())
                html += QStringLiteral("<br><span style='%1 color:%2;'>%3</span>")
                            .arg(mono_css(11, 400), css(col(Role::Muted)), esc(path));
            const QString note = str(s, "ghi_chu").trimmed();
            if (!note.isEmpty())
                html += QStringLiteral("<br>") + span(esc(note), ok ? col(Role::Muted) : col(Role::Down));
            lay->addWidget(bot_label(card, html, col(Role::Ink), 12));
        }
        body->addWidget(card);
    }

    // 3. Warnings: the issue's own + the engine's (missing sources, data traps hit).
    const QJsonArray w_issue = issue.value(QStringLiteral("canh_bao")).toArray();
    const QJsonArray w_meta = meta.value(QStringLiteral("warnings")).toArray();
    if (!w_issue.isEmpty() || !w_meta.isEmpty()) {
        QVBoxLayout* lay = nullptr;
        QFrame* card = make_card(sec, lay, col(Role::Amber));
        lay->addWidget(bot_eyebrow(card, QStringLiteral("Cảnh báo"), col(Role::Amber)));
        const auto add_list = [&](const QString& head, const QJsonArray& items) {
            if (items.isEmpty())
                return;
            lay->addWidget(bot_label(card, esc(head), col(Role::Muted), 11, false, true));
            for (const QJsonValue& v : items) {
                const QString s = v.isString() ? v.toString().trimmed() : bot_num(v);
                if (!s.isEmpty())
                    lay->addWidget(bot_label(card, span(QStringLiteral("▲&nbsp;"), col(Role::Amber)) + esc(s),
                                             col(Role::Ink2), 12));
            }
        };
        add_list(QStringLiteral("Bản tuần"), w_issue);
        add_list(QStringLiteral("Máy · sgi_fa.py"), w_meta);
        body->addWidget(card);
    }

    // 4. Next-issue checklist.
    const QJsonArray todo = issue.value(QStringLiteral("can_kiem_ky_sau")).toArray();
    body->addWidget(bot_eyebrow(sec, QStringLiteral("Cần kiểm kỳ sau")));
    if (todo.isEmpty()) {
        body->addWidget(bot_need(sec, QStringLiteral("bản tuần không ghi danh sách cần kiểm (can_kiem_ky_sau)")));
    } else {
        QVBoxLayout* lay = nullptr;
        QFrame* card = make_card(sec, lay);
        for (const QJsonValue& v : todo) {
            const QString s = v.isString() ? v.toString().trimmed() : bot_num(v);
            if (!s.isEmpty())
                lay->addWidget(bot_label(card, span(QStringLiteral("☐&nbsp;"), col(Role::Muted)) + esc(s), col(Role::Ink2),
                                         12));
        }
        body->addWidget(card);
    }

    // 5. Disclaimer + run stamp.
    const QString tuyen_bo = str(issue, "tuyen_bo");
    if (!tuyen_bo.trimmed().isEmpty()) {
        auto* l = bot_plain(sec, tuyen_bo.trimmed(), col(Role::Muted), 12);
        l->setStyleSheet(QStringLiteral("QLabel { color:%1; %2 background:transparent; border-top:1px solid %3;"
                                        " padding-top:10px; margin-top:6px; }")
                             .arg(css(col(Role::Muted)), lk::lk_font_css(lk::lk_font_sans(12, 400)),
                                  css(col(Role::Line))));
        body->addWidget(l);
    }
    QStringList stamp;
    const QString gen = str(meta, "generated").trimmed();
    if (!gen.isEmpty())
        stamp << QStringLiteral("sinh lúc ") + gen;
    const QString ver = str(meta, "script_version").trimmed();
    if (!ver.isEmpty())
        stamp << QStringLiteral("sgi_fa.py ") + ver;
    const QString file = str(meta, "issue_file").trimmed();
    if (!file.isEmpty())
        stamp << file;
    if (!stamp.isEmpty())
        body->addWidget(bot_label(sec, esc(stamp.join(QStringLiteral(" · "))), col(Role::Muted), 11, true));
    return sec;
}

} // namespace fincept::screens::sgi
