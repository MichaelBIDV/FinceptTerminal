// src/screens/langkinh/LkChips.cpp
// Lăng Kính FFT — phần dùng chung của block hồ sơ (html-lite, nhãn, pill/tag, bố cục chảy/lưới) + block "chips"
// (LK_HOSO_SPEC §6). Xem LkChips.h.
#include "screens/langkinh/LkChips.h"

#include "screens/langkinh/LkWidgets.h"

#include <QFontMetricsF>
#include <QFrame>
#include <QHBoxLayout>
#include <QJsonArray>
#include <QJsonValue>
#include <QLabel>
#include <QPainter>
#include <QPen>
#include <QRegularExpression>
#include <QResizeEvent>
#include <QSizePolicy>
#include <QStringList>
#include <QVBoxLayout>

#include <algorithm>
#include <cmath>
#include <utility>

namespace fincept::screens::langkinh {

// Helper tự do: namespace có tên riêng (quy ước của module, không dùng namespace ẩn danh).
namespace lkchips {

using lkview::lk_col;
using lkview::LkRole;

constexpr double kPillPadX = 9.0;
constexpr double kPillPadY = 2.0;
constexpr double kTagPadX = 5.0;
constexpr double kTagPadY = 1.0;
constexpr double kTagRadius = 4.0;
constexpr int kTagPx = 10;

constexpr int kChipPx = 12;
constexpr double kChipPadX = 9.0;
constexpr double kChipPadY = 5.0;
constexpr double kChipGap = 6.0;
constexpr double kChipRadius = 6.0;
constexpr int kChipMinW = 140;

QFont pill_font(int px, bool tracked) {
    QFont f = lkview::lk_font_mono(px, 600);
    if (tracked)
        f.setLetterSpacing(QFont::AbsoluteSpacing, px * 0.08);
    return f;
}

QFont tag_font() {
    QFont f = lkview::lk_font_mono(kTagPx, 600);
    f.setLetterSpacing(QFont::AbsoluteSpacing, kTagPx * 0.04);
    return f;
}

int ceil_i(double v) {
    return static_cast<int>(std::ceil(v - 1e-6));
}

// ── html-lite ─────────────────────────────────────────────────────────────────

/// Độ dài tham chiếu thực thể HTML hợp lệ bắt đầu tại i ("&amp;", "&#8722;", "&#x2212;"); 0 nếu không phải.
int entity_len(const QString& s, int i) {
    static const QRegularExpression re(
        QStringLiteral("&(?:#[0-9]{1,7}|#[xX][0-9a-fA-F]{1,6}|[A-Za-z][A-Za-z0-9]{1,31});"));
    const QRegularExpressionMatch m =
        re.match(s, i, QRegularExpression::NormalMatch, QRegularExpression::AnchorAtOffsetMatchOption);
    return m.hasMatch() ? static_cast<int>(m.capturedLength()) : 0;
}

/// Escape chữ thường: < > và & không thuộc thực thể hợp lệ; "\n" → <br>, bỏ "\r".
QString esc_text(const QString& s) {
    QString o;
    o.reserve(s.size() + 16);
    for (int i = 0; i < s.size(); ++i) {
        const QChar c = s.at(i);
        if (c == QLatin1Char('&')) {
            const int len = entity_len(s, i);
            if (len > 0) {
                o += s.mid(i, len);
                i += len - 1;
            } else {
                o += QStringLiteral("&amp;");
            }
        } else if (c == QLatin1Char('<')) {
            o += QStringLiteral("&lt;");
        } else if (c == QLatin1Char('>')) {
            o += QStringLiteral("&gt;");
        } else if (c == QLatin1Char('\n')) {
            o += QStringLiteral("<br>");
        } else if (c != QLatin1Char('\r')) {
            o += c;
        }
    }
    return o;
}

/// Một thẻ mở/đóng kiểu <b>, </b>, <br/>, <tag b="FACT-T2">. Như HTML, tên thẻ phải liền sau "<" / "</" —
/// "a < b > c" trong câu văn là chữ, không phải thẻ <b>.
const QRegularExpression& tag_re() {
    static const QRegularExpression re(QStringLiteral(R"(<(/?)([A-Za-z][A-Za-z0-9]*)((?:\s[^<>]*)?)\s*/?\s*>)"));
    return re;
}

QString strip_tags(QString s) {
    s.remove(tag_re());
    return s;
}

/// <tag b="X">nhãn</tag> → span mono màu bậc X trên nền soft (đã phủ lên surface → màu đục). Dấu cách trong nhãn
/// thành &nbsp; để tag không bị bẻ giữa hai dòng (Artifact .tag{white-space:nowrap}).
QString tag_span(const QString& b, const QString& label) {
    const QColor fg = lkview::lk_tier(b);
    const QColor bg = lkview::lk_over(lkview::lk_tier_soft(b), lk_col(LkRole::Surface));
    return QStringLiteral("<span style=\"font-family:'Menlo','SF Mono',monospace; font-size:10px; font-weight:600;"
                          " color:%1; background-color:%2;\">&nbsp;%3&nbsp;</span>")
        .arg(fg.name(), bg.name(), esc_text(label).replace(QLatin1Char(' '), QStringLiteral("&nbsp;")));
}

/// Thẻ được giữ (ngoài br/tag xử lý riêng) → HTML mở/đóng tương ứng; rỗng = thẻ lạ (bỏ markup, giữ chữ).
struct Emitter {
    QColor strong;

    static bool is_bold(const QString& n) { return n == QLatin1String("b") || n == QLatin1String("strong"); }
    static bool is_ital(const QString& n) { return n == QLatin1String("i") || n == QLatin1String("em"); }

    QString open(const QString& n) const {
        if (is_bold(n))
            return strong.isValid()
                       ? QStringLiteral("<span style=\"font-weight:600; color:%1;\">").arg(strong.name())
                       : QStringLiteral("<b>");
        if (is_ital(n))
            return QStringLiteral("<i>");
        if (n == QLatin1String("code"))
            return QStringLiteral("<span style=\"font-family:'Menlo','SF Mono',monospace;\">");
        return {};
    }
    QString close(const QString& n) const {
        if (is_bold(n))
            return strong.isValid() ? QStringLiteral("</span>") : QStringLiteral("</b>");
        if (is_ital(n))
            return QStringLiteral("</i>");
        if (n == QLatin1String("code"))
            return QStringLiteral("</span>");
        return {};
    }
};

/// Giá trị thuộc tính b="…" (nháy kép, nháy đơn hoặc không nháy) trong phần thuộc tính của thẻ.
QString attr_b(const QString& attrs) {
    // Dấu phân cách "re" vì mẫu chứa `)"` (sẽ kết thúc sớm một raw string R"(…)").
    static const QRegularExpression re(QStringLiteral(R"re((?:^|\s)b\s*=\s*(?:"([^"]*)"|'([^']*)'|([^\s"'>/]+)))re"));
    const QRegularExpressionMatch m = re.match(attrs);
    if (!m.hasMatch())
        return {};
    for (int g = 1; g <= 3; ++g)
        if (m.capturedStart(g) >= 0)
            return m.captured(g).trimmed();
    return {};
}

// ── Chip khai nguồn: tag bậc + chữ gói dòng, viền mảnh bo 6px ─────────────────

class ChipItem : public QWidget {
  public:
    ChipItem(const QString& b, const QString& text, QWidget* parent)
        : QWidget(parent), b_(b.trimmed()), text_(text.trimmed()) {
        QSizePolicy sp(QSizePolicy::Preferred, QSizePolicy::Preferred);
        sp.setHeightForWidth(true);
        setSizePolicy(sp);
        lkview::lk_transparent(this);
        QStringList tip;
        if (!b_.isEmpty())
            tip << lkview::lk_tier_desc(b_);
        if (!text_.isEmpty())
            tip << text_;
        setToolTip(tip.join(QLatin1Char('\n')));
    }

    bool hasHeightForWidth() const override { return true; }
    int heightForWidth(int w) const override { return ceil_i(geo(w).h); }
    QSize sizeHint() const override {
        const QFontMetricsF fm(text_font());
        double w = 2.0 * (1.0 + kChipPadX) + fm.horizontalAdvance(text_) + 1.0;
        if (!b_.isEmpty())
            w += lkview::lk_tag_size(b_).width() + (text_.isEmpty() ? 0.0 : kChipGap);
        const int wi = ceil_i(w);
        return {wi, heightForWidth(wi)};
    }
    QSize minimumSizeHint() const override { // cao một dòng: hfw lo phần gói chữ
        return {std::min(kChipMinW, sizeHint().width()), ceil_i(geo(1.0e5).h)};
    }

  protected:
    void paintEvent(QPaintEvent*) override {
        QPainter p(this);
        p.setRenderHint(QPainter::Antialiasing, true);
        p.setRenderHint(QPainter::TextAntialiasing, true);
        const Geo g = geo(width());
        p.setPen(QPen(lk_col(LkRole::Line), 1.0));
        p.setBrush(lk_col(LkRole::Surface));
        p.drawRoundedRect(QRectF(rect()).adjusted(0.5, 0.5, -0.5, -0.5), kChipRadius, kChipRadius);
        if (!b_.isEmpty())
            lkview::lk_paint_tag(p, g.tag, b_);
        if (!text_.isEmpty()) {
            p.setFont(text_font());
            p.setPen(lk_col(LkRole::Ink2));
            p.drawText(g.text, Qt::TextWordWrap | Qt::AlignLeft | Qt::AlignTop, text_);
        }
    }

  private:
    struct Geo {
        QRectF tag;
        QRectF text;
        double h = 0.0;
    };

    static QFont text_font() { return lkview::lk_font_sans(kChipPx); }

    /// Hình học tại bề rộng w: tag bên trái, chữ gói dòng bên phải; đường chân chữ tag = đường chân dòng đầu.
    Geo geo(double w) const {
        Geo g;
        const QFontMetricsF fm(text_font());
        const bool has_tag = !b_.isEmpty();
        const double x0 = 1.0 + kChipPadX;
        const double top = 1.0 + kChipPadY;
        const double right = std::max(x0 + 24.0, w - 1.0 - kChipPadX);
        QSizeF ts;
        if (has_tag) {
            ts = lkview::lk_tag_size(b_);
            ts.setWidth(std::min(ts.width(), text_.isEmpty() ? right - x0 : (right - x0) * 0.6));
        }
        const double tx = has_tag && !text_.isEmpty() ? x0 + ts.width() + kChipGap : x0;
        const double tw = std::max(24.0, right - tx);
        double th = 0.0;
        if (!text_.isEmpty())
            th = std::max(fm.height(), fm.boundingRect(QRectF(0, 0, tw, 1.0e6), Qt::TextWordWrap, text_).height());
        double bottom = top + th;
        if (has_tag) {
            const QFontMetricsF tfm(tag_font());
            const double ty = text_.isEmpty() ? top : std::max(2.0, top + fm.ascent() - tfm.ascent() - kTagPadY);
            g.tag = QRectF(x0, ty, ts.width(), ts.height());
            bottom = std::max(bottom, g.tag.bottom());
        }
        g.text = QRectF(tx, top, tw, th);
        g.h = bottom + kChipPadY + 1.0;
        return g;
    }

    QString b_;
    QString text_;
};

/// Tiêu đề + tag bậc bên phải (khoá `b`) trên một hàng; không có tag → chỉ nhãn tiêu đề.
void add_title_row(QVBoxLayout* vl, QLabel* title, const QString& tier, QWidget* parent) {
    if (tier.isEmpty()) {
        if (title)
            vl->addWidget(title);
        return;
    }
    auto* hl = new QHBoxLayout;
    hl->setContentsMargins(0, 0, 0, 0);
    hl->setSpacing(10);
    if (title)
        hl->addWidget(title, 1);
    hl->addWidget(new lkview::LkTag(tier, parent), 0, Qt::AlignTop | (title ? Qt::AlignRight : Qt::AlignLeft));
    if (!title)
        hl->addStretch(1);
    vl->addLayout(hl);
}

} // namespace lkchips

namespace lkview {

// ── Rich text ─────────────────────────────────────────────────────────────────

QString lk_inline_html(const QString& src, const QColor& strong) {
    using namespace lkchips;
    static const QRegularExpression close_tag(QStringLiteral(R"(<\s*/\s*tag\s*>)"),
                                              QRegularExpression::CaseInsensitiveOption);
    static const QRegularExpression open_tag(QStringLiteral(R"(<tag(?:[\s/>]))"),
                                             QRegularExpression::CaseInsensitiveOption);
    const Emitter em{strong};
    QString out;
    QStringList stack; // thẻ đang mở (b/i/code) để đóng đúng thứ tự, bỏ thẻ đóng lẻ
    const int n = static_cast<int>(src.size());
    int text_from = 0;
    int i = 0;
    while (i < n) {
        if (src.at(i) != QLatin1Char('<')) {
            ++i;
            continue;
        }
        const QRegularExpressionMatch m =
            tag_re().match(src, i, QRegularExpression::NormalMatch, QRegularExpression::AnchorAtOffsetMatchOption);
        if (!m.hasMatch()) { // "<" lẻ (vd "k < 50 nghìn") → escape khi xả chữ
            ++i;
            continue;
        }
        out += esc_text(src.mid(text_from, i - text_from));
        i = static_cast<int>(m.capturedEnd());
        text_from = i;
        const bool closing = !m.captured(1).isEmpty();
        const QString name = m.captured(2).toLower();
        if (name == QLatin1String("br")) {
            out += QStringLiteral("<br>");
            continue;
        }
        if (name == QLatin1String("tag")) {
            if (closing) // </tag> lẻ
                continue;
            const QString b = attr_b(m.captured(3));
            QString label;
            QString whole = m.captured(0);
            whole.chop(1); // bỏ ">"
            if (!whole.trimmed().endsWith(QLatin1Char('/'))) { // <tag …/> tự đóng: không tìm </tag>, nhãn = b
                // </tag> chỉ tính khi đứng trước <tag kế tiếp: thiếu </tag> không được nuốt chip sau.
                const QRegularExpressionMatch cm = close_tag.match(src, i);
                const QRegularExpressionMatch om = open_tag.match(src, i);
                if (cm.hasMatch() && (!om.hasMatch() || om.capturedStart() > cm.capturedStart())) {
                    label = strip_tags(src.mid(i, cm.capturedStart() - i));
                    i = static_cast<int>(cm.capturedEnd());
                    text_from = i;
                }
            }
            label = label.simplified();
            if (label.isEmpty())
                label = b;
            if (!label.isEmpty())
                out += tag_span(b, label);
            continue;
        }
        const QString open = em.open(name);
        if (open.isEmpty()) // thẻ ngoài danh sách: bỏ markup, giữ chữ
            continue;
        if (!closing) {
            stack << name;
            out += open;
        } else if (stack.contains(name)) {
            while (!stack.isEmpty()) {
                const QString t = stack.takeLast();
                out += em.close(t);
                if (t == name)
                    break;
            }
        }
    }
    out += esc_text(src.mid(text_from));
    while (!stack.isEmpty())
        out += em.close(stack.takeLast());
    return out;
}

QString lk_para_html(const QString& src, const QColor& strong, int line_height_pct) {
    static const QRegularExpression para_re(QStringLiteral("\\n[ \\t]*\\n"));
    QString s = src;
    s.replace(QStringLiteral("\r\n"), QStringLiteral("\n"));
    const QStringList paras = s.split(para_re, Qt::SkipEmptyParts);
    const int lh = std::clamp(line_height_pct, 100, 220);
    QString out;
    int k = 0;
    for (const QString& para : paras) {
        const QString t = para.trimmed();
        if (t.isEmpty())
            continue;
        out += QStringLiteral("<p style=\"margin-top:%1px; margin-bottom:0px; line-height:%2%;\">")
                   .arg(k == 0 ? 0 : 8)
                   .arg(lh) +
               lk_inline_html(t, strong) + QStringLiteral("</p>");
        ++k;
    }
    return out;
}

int lk_line_pct(const QFont& f, double em) {
    const QFontMetricsF fm(f);
    const double px = f.pixelSize() > 0 ? f.pixelSize() : f.pointSizeF() * 96.0 / 72.0;
    if (!(fm.height() > 0.0) || !(px > 0.0))
        return 158;
    return std::clamp(static_cast<int>(std::lround(100.0 * em * px / fm.height())), 100, 220);
}

QString lk_tier_desc(const QString& b) {
    const QString k = lk_tier_key(b);
    QString d;
    if (k == QLatin1String("FACT-T1"))
        d = lk_tr("nguồn gốc: CBTT / BCTC / BCTN");
    else if (k == QLatin1String("FACT-T2"))
        d = lk_tr("data vendor: Vietcap, KHO vnstock");
    else if (k == QLatin1String("SS-T3"))
        d = lk_tr("sell-side / Toàn Vũ");
    else if (k == QLatin1String("NEWS"))
        d = lk_tr("tin tức");
    else if (k == QLatin1String("EST"))
        d = lk_tr("tự ước — xem logic đi kèm");
    else if (k == QLatin1String("UNVERIFIED"))
        d = lk_tr("chưa kiểm — không dùng cho quyết định");
    else if (k == QStringLiteral("CẦN DATA"))
        d = lk_tr("thiếu nguồn — không điền số");
    const QString t = b.trimmed();
    if (t.isEmpty())
        return d;
    return d.isEmpty() ? t : t + QStringLiteral(" — ") + d;
}

// ── Nhãn chữ ──────────────────────────────────────────────────────────────────

QLabel* lk_label(const QString& text, const QFont& f, const QColor& c, QWidget* parent, Qt::TextFormat fmt) {
    auto* l = new QLabel(parent);
    l->setTextFormat(fmt);
    l->setText(text);
    l->setWordWrap(true);
    l->setOpenExternalLinks(false);
    l->setTextInteractionFlags(Qt::TextSelectableByMouse);
    l->setFont(f);
    l->setStyleSheet(QStringLiteral("QLabel { %1 color:%2; background:transparent; border:none; padding:0px; }")
                         .arg(lk_font_css(f), c.name()));
    return l;
}

void lk_add_head(QVBoxLayout* vl, const QJsonObject& b, QWidget* parent, LkHead style) {
    if (!vl)
        return;
    const QString title = b.value(QStringLiteral("title")).toString().trimmed();
    const QString sub = b.value(QStringLiteral("sub")).toString().trimmed();
    const QString tier = b.value(QStringLiteral("b")).toString().trimmed();
    if (!title.isEmpty() || !tier.isEmpty()) {
        QLabel* t = title.isEmpty() ? nullptr : lk_label(title, lk_font_sans(14, 600), lk_col(LkRole::Ink), parent);
        lkchips::add_title_row(vl, t, tier, parent);
    }
    if (sub.isEmpty())
        return;
    const bool fig = style == LkHead::Fig; // .fig .cap .src: nguồn, muted
    vl->addWidget(lk_label(lk_inline_html(sub, lk_col(fig ? LkRole::Ink2 : LkRole::Ink)), lk_font_sans(12),
                           lk_col(fig ? LkRole::Muted : LkRole::Ink2), parent, Qt::RichText));
}

void lk_section_head(QVBoxLayout* vl, const QJsonObject& b, QWidget* parent) {
    if (!vl)
        return;
    const QString eyebrow = b.value(QStringLiteral("eyebrow")).toString().trimmed();
    const QString title = b.value(QStringLiteral("title")).toString().trimmed();
    const QString sub = b.value(QStringLiteral("sub")).toString().trimmed();
    const QString tier = b.value(QStringLiteral("b")).toString().trimmed();
    const QColor ink = lk_col(LkRole::Ink);
    if (!eyebrow.isEmpty())
        vl->addWidget(new LkCapsLabel(eyebrow, lk_font_mono(11), LkRole::Amber, parent, 0.14, true));
    if (!title.isEmpty() || !tier.isEmpty()) {
        vl->addSpacing(6);
        QLabel* t = title.isEmpty()
                        ? nullptr
                        : lk_label(lk_inline_html(title, ink), lk_font_serif(28, 600), ink, parent, Qt::RichText);
        lkchips::add_title_row(vl, t, tier, parent);
    }
    if (!sub.isEmpty()) {
        vl->addSpacing(8);
        vl->addWidget(lk_measure(lk_label(lk_inline_html(sub, ink), lk_font_sans(14), lk_col(LkRole::Ink2), parent,
                                          Qt::RichText),
                                 760, parent));
    }
    vl->addSpacing(12);
    auto* rule = new QFrame(parent);
    rule->setObjectName(QStringLiteral("lkSecRule"));
    rule->setFixedHeight(1);
    rule->setStyleSheet(
        QStringLiteral("QFrame#lkSecRule { background:%1; border:none; }").arg(lk_qss(lk_col(LkRole::Line))));
    vl->addWidget(rule);
    vl->addSpacing(18);
}

void lk_transparent(QWidget* w) {
    if (w)
        w->setStyleSheet(QStringLiteral("QWidget { background:transparent; }"));
}

// ── Pill & tag ────────────────────────────────────────────────────────────────

LkRole lk_pill_role(const QString& mau) {
    return lk_role(mau, LkRole::Grey);
}

QSizeF lk_pill_size(const QString& text, int px, bool tracked) {
    const QFontMetricsF fm(lkchips::pill_font(px, tracked));
    return {std::ceil(fm.horizontalAdvance(text.trimmed()) + 2.0 * lkchips::kPillPadX),
            std::ceil(fm.height() + 2.0 * lkchips::kPillPadY)};
}

void lk_paint_pill(QPainter& p, const QRectF& r, const QString& text, LkRole role, int px, bool tracked) {
    if (r.width() <= 1.0 || r.height() <= 1.0)
        return;
    p.save();
    p.setRenderHint(QPainter::Antialiasing, true);
    p.setRenderHint(QPainter::TextAntialiasing, true);
    const QColor fg = lk_col(role);
    const double rad = r.height() / 2.0;
    p.setPen(Qt::NoPen);
    p.setBrush(lk_soft(fg));
    p.drawRoundedRect(r, rad, rad);
    const QFont f = lkchips::pill_font(px, tracked);
    const QFontMetricsF fm(f);
    const QRectF tr = r.adjusted(lkchips::kPillPadX, 0.0, -lkchips::kPillPadX, 0.0);
    p.setFont(f);
    p.setPen(fg);
    p.drawText(tr, Qt::AlignCenter, fm.elidedText(text.trimmed(), Qt::ElideRight, tr.width() + 0.5));
    p.restore();
}

QSizeF lk_tag_size(const QString& b) {
    const QFontMetricsF fm(lkchips::tag_font());
    return {std::ceil(fm.horizontalAdvance(b.trimmed()) + 2.0 * lkchips::kTagPadX),
            std::ceil(fm.height() + 2.0 * lkchips::kTagPadY)};
}

void lk_paint_tag(QPainter& p, const QRectF& r, const QString& b) {
    const QString t = b.trimmed();
    if (t.isEmpty() || r.width() <= 1.0 || r.height() <= 1.0)
        return;
    p.save();
    p.setRenderHint(QPainter::Antialiasing, true);
    p.setRenderHint(QPainter::TextAntialiasing, true);
    p.setPen(Qt::NoPen);
    p.setBrush(lk_tier_soft(t));
    p.drawRoundedRect(r, lkchips::kTagRadius, lkchips::kTagRadius);
    const QFont f = lkchips::tag_font();
    const QFontMetricsF fm(f);
    const QRectF tr = r.adjusted(lkchips::kTagPadX, 0.0, -lkchips::kTagPadX, 0.0);
    p.setFont(f);
    p.setPen(lk_tier(t));
    p.drawText(tr, Qt::AlignCenter, fm.elidedText(t, Qt::ElideRight, tr.width() + 0.5));
    p.restore();
}

// ── LkPill · LkTag · LkCapsLabel ──────────────────────────────────────────────

LkPill::LkPill(const QString& text, LkRole role, QWidget* parent, int px, bool tracked)
    : QWidget(parent), text_(text.trimmed()), role_(role), px_(std::max(7, px)), tracked_(tracked) {
    setSizePolicy(QSizePolicy::Fixed, QSizePolicy::Fixed);
    lk_transparent(this);
}

QSize LkPill::sizeHint() const {
    const QSizeF s = lk_pill_size(text_, px_, tracked_);
    return {lkchips::ceil_i(s.width()), lkchips::ceil_i(s.height())};
}

void LkPill::paintEvent(QPaintEvent*) {
    QPainter p(this);
    lk_paint_pill(p, QRectF(rect()), text_, role_, px_, tracked_);
}

LkTag::LkTag(const QString& b, QWidget* parent) : QWidget(parent), b_(b.trimmed()) {
    setSizePolicy(QSizePolicy::Fixed, QSizePolicy::Fixed);
    lk_transparent(this);
    setToolTip(lk_tier_desc(b_));
}

QSize LkTag::sizeHint() const {
    if (b_.isEmpty())
        return {0, 0};
    const QSizeF s = lk_tag_size(b_);
    return {lkchips::ceil_i(s.width()), lkchips::ceil_i(s.height())};
}

void LkTag::paintEvent(QPaintEvent*) {
    QPainter p(this);
    lk_paint_tag(p, QRectF(rect()), b_);
}

LkCapsLabel::LkCapsLabel(const QString& text, const QFont& f, LkRole role, QWidget* parent, double tracking_em,
                         bool wrap)
    : QWidget(parent), text_(text.trimmed().toUpper()), font_(f), role_(role), wrap_(wrap) {
    const int px = f.pixelSize() > 0 ? f.pixelSize() : 11;
    if (tracking_em != 0.0)
        font_.setLetterSpacing(QFont::AbsoluteSpacing, px * tracking_em);
    QSizePolicy sp(QSizePolicy::Preferred, wrap ? QSizePolicy::Preferred : QSizePolicy::Fixed);
    sp.setHeightForWidth(wrap);
    setSizePolicy(sp);
    lk_transparent(this);
}

QSize LkCapsLabel::sizeHint() const {
    const QFontMetricsF fm(font_);
    const int w = lkchips::ceil_i(fm.horizontalAdvance(text_) + 1.0);
    return {w, wrap_ ? heightForWidth(w) : lkchips::ceil_i(fm.height())};
}

QSize LkCapsLabel::minimumSizeHint() const {
    const QFontMetricsF fm(font_);
    return {std::min(sizeHint().width(), 48), lkchips::ceil_i(fm.height())};
}

int LkCapsLabel::heightForWidth(int w) const {
    const QFontMetricsF fm(font_);
    if (!wrap_ || text_.isEmpty())
        return lkchips::ceil_i(fm.height());
    const QRectF br = fm.boundingRect(QRectF(0, 0, std::max(1, w), 1.0e6), Qt::TextWordWrap, text_);
    return lkchips::ceil_i(std::max(fm.height(), br.height()));
}

void LkCapsLabel::paintEvent(QPaintEvent*) {
    QPainter p(this);
    p.setRenderHint(QPainter::TextAntialiasing, true);
    p.setFont(font_);
    p.setPen(lk_col(role_));
    if (wrap_) {
        p.drawText(QRectF(rect()), Qt::TextWordWrap | Qt::AlignLeft | Qt::AlignTop, text_);
        return;
    }
    const QFontMetricsF fm(font_);
    p.drawText(QRectF(rect()), Qt::AlignLeft | Qt::AlignVCenter, fm.elidedText(text_, Qt::ElideRight, width() + 0.5));
}

void LkCapsLabel::resizeEvent(QResizeEvent* e) {
    QWidget::resizeEvent(e);
    if (wrap_) {
        if (heightForWidth(width()) != height())
            updateGeometry();
        return;
    }
    const QFontMetricsF fm(font_);
    setToolTip(fm.horizontalAdvance(text_) > width() + 0.5 ? text_ : QString());
}

// ── Block "chips" ─────────────────────────────────────────────────────────────

QWidget* make_chips(const QJsonObject& b, QWidget* parent) {
    const QJsonArray items = b.value(QStringLiteral("items")).toArray();
    auto* w = new QWidget(parent);
    lk_transparent(w);
    auto* vl = new QVBoxLayout(w);
    vl->setContentsMargins(0, 0, 0, 0);
    vl->setSpacing(8);
    lk_add_head(vl, b, w);
    auto* box = new QWidget(w);
    auto* flow = new LkWrapLayout(box, 8, 8, false);
    const QString phrase = lk_tr("không dùng cho quyết định");
    int n = 0;
    for (const auto& iv : items) {
        QString tier;
        QString text;
        if (iv.isObject()) {
            const QJsonObject it = iv.toObject();
            tier = text_opt(it.value(QStringLiteral("b")));
            text = text_opt(it.value(QStringLiteral("text")));
        } else {
            text = text_opt(iv); // mục là chuỗi trần → chip không tag
        }
        if (tier.isEmpty() && text.isEmpty())
            continue;
        if (lk_tier_unverified(tier) && !text.contains(phrase, Qt::CaseInsensitive))
            text = text.isEmpty() ? phrase : text + QStringLiteral(" · ") + phrase;
        flow->addWidget(new lkchips::ChipItem(tier, text, box));
        ++n;
    }
    if (n == 0) {
        delete w;
        return nullptr;
    }
    vl->addWidget(box);
    return w;
}

} // namespace lkview

} // namespace fincept::screens::langkinh
