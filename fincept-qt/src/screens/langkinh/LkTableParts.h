// src/screens/langkinh/LkTableParts.h
// Lăng Kính FFT — phần riêng của block "table" (chỉ LkTableBlock.cpp include), tách ra để tệp .cpp ≤ 800 dòng:
//   · CellGeo / cell_geo, wrap_head, tag_color, vai dữ liệu ô, LkCellDelegate (bar · tag · _tag · _vien) — chuyển
//     nguyên văn từ LkTableBlock.cpp; delegate thêm nhánh hàng nhóm.
//   · Hàng đầu nhóm (hợp đồng block v2, khoá hàng "_nhom"): nhận diện, chữ, phông, bố cục (dùng chung cho delegate
//     vẽ ô và phép đo cao hàng — hai bên phải ra cùng một số) và bộ vẽ.
//     "_nhom": true  → nhãn = chữ cột 1; chữ các cột còn lại (bỏ ô trống) nối " · " thành dòng phụ.
//     "_nhom": "…"  → nhãn = chuỗi đó; chữ mọi cột nối thành dòng phụ.
//     Hàng nhóm gộp hết các cột, nền surface-2, vạch trái + nhãn mono màu nhóm (`_vien`, không có thì `_mau` của
//     cột 1, mặc định amber), dòng phụ muted cùng dòng khi vừa, không thì xuống dòng dưới nhãn (bảng "wrap").
#pragma once

#include "screens/langkinh/LkChips.h"
#include "screens/langkinh/LkTheme.h"
#include "screens/langkinh/LkWidgets.h"
#include "ui/theme/Theme.h"

#include <QAbstractItemView>
#include <QApplication>
#include <QBrush>
#include <QColor>
#include <QFont>
#include <QFontMetrics>
#include <QHelpEvent>
#include <QJsonObject>
#include <QJsonValue>
#include <QModelIndex>
#include <QPainter>
#include <QPen>
#include <QRect>
#include <QString>
#include <QStringList>
#include <QStyle>
#include <QStyleOptionViewItem>
#include <QStyledItemDelegate>
#include <QToolTip>
#include <QVariant>

#include <algorithm>
#include <cmath>

namespace fincept::screens::langkinh::lkview {

constexpr int kRowHeight = 26;
constexpr int kCellPad = 8;
constexpr int kHeadWrapPx = 72; // bảng rộng hơn khung: nhãn cột dài hơn → 2 dòng, trả bề rộng cho cột chữ

/// Kích thước ô theo kiểu trang: cũ (26px, đệm 8/5) · hồ sơ (36px, đệm 12/9 như Artifact td{padding:9px 12px}).
struct CellGeo {
    int row_h;
    int pad_x;
    int pad_y;
};
inline CellGeo cell_geo(bool hoso) {
    return hoso ? CellGeo{36, 12, 9} : CellGeo{kRowHeight, kCellPad, 5};
}

/// Nhãn cột dài: tách 2 dòng tại dấu cách cho dòng dài nhất ngắn nhất; nhãn ngắn/không có dấu cách giữ nguyên.
inline QString wrap_head(const QString& label, const QFontMetrics& fm) {
    if (fm.horizontalAdvance(label) <= kHeadWrapPx)
        return label;
    int best = -1;
    int best_w = 0;
    for (int i = label.indexOf(QLatin1Char(' ')); i > 0; i = label.indexOf(QLatin1Char(' '), i + 1)) {
        const int w = std::max(fm.horizontalAdvance(label.left(i)), fm.horizontalAdvance(label.mid(i + 1)));
        if (best < 0 || w < best_w) {
            best = i;
            best_w = w;
        }
    }
    return best < 0 ? label : label.left(best) + QLatin1Char('\n') + label.mid(best + 1);
}

/// Màu nhãn nhỏ _tag: "x%" (tỷ trọng danh mục) → AMBER · "watch…" → INFO · "avoid…" (kể cả "avoid*") → NEGATIVE.
inline QColor tag_color(const QString& tag) {
    using namespace ui::colors;
    const QString t = tag.trimmed().toLower();
    if (t.endsWith(QLatin1Char('%')))
        return QColor(AMBER());
    if (t.startsWith(QLatin1String("watch")))
        return QColor(INFO());
    if (t.startsWith(QLatin1String("avoid")))
        return QColor(NEGATIVE());
    return QColor(TEXT_SECONDARY());
}

// ── Hàng đầu nhóm "_nhom" ─────────────────────────────────────────────────────

inline bool is_group_row(const QJsonObject& row) {
    const QJsonValue v = row.value(QStringLiteral("_nhom"));
    return v.toBool(false) || (v.isString() && !v.toString().trimmed().isEmpty());
}

struct GroupText {
    QString label;
    QString rest; // dòng phụ (có thể rỗng)
};

inline GroupText group_text(const QJsonObject& row, const QStringList& keys) {
    GroupText g;
    const QJsonValue nv = row.value(QStringLiteral("_nhom"));
    int from = 0;
    if (nv.isString() && !nv.toString().trimmed().isEmpty()) {
        g.label = nv.toString().trimmed();
    } else if (!keys.isEmpty()) {
        g.label = text_opt(row.value(keys.first()));
        from = 1;
    }
    QStringList rest;
    for (int i = from; i < keys.size(); ++i)
        if (const QString t = text_opt(row.value(keys.at(i))); !t.isEmpty())
            rest << t;
    if (g.label.isEmpty() && !rest.isEmpty()) // cột 1 trống: phần đầu của dòng phụ làm nhãn
        g.label = rest.takeFirst();
    g.rest = rest.join(QStringLiteral(" · "));
    return g;
}

struct GroupFonts {
    QFont label;
    QFont rest;
};

/// Hồ sơ: nhãn mono 11/600 giãn 0,06em, dòng phụ sans 12. Trang cũ: phông bảng, nhãn đậm.
inline GroupFonts group_fonts(bool hoso, const QFont& base) {
    if (hoso) {
        QFont l = lk_font_mono(11, 600);
        l.setLetterSpacing(QFont::AbsoluteSpacing, 0.06 * 11);
        return {l, lk_font_sans(12)};
    }
    QFont l = base;
    l.setBold(true);
    return {l, base};
}

struct GroupGeo {
    QRect label; // toạ độ trong ô (gốc 0,0)
    QRect rest;
    int h = 0;
};

/// Bố cục hàng nhóm trong ô rộng w. wrap: nhãn gói chữ (không cắt), dòng phụ cùng dòng khi vừa, không thì xuống
/// dưới nhãn và gói chữ; h = cao cần. Không wrap: một dòng cao row_h, canh giữa dọc (dòng phụ cắt "…" khi vẽ).
inline GroupGeo group_geo(const GroupText& t, const GroupFonts& f, int w, int pad_x, int pad_y, int row_h,
                          bool wrap) {
    GroupGeo g;
    const QFontMetrics fl(f.label);
    const QFontMetrics fr(f.rest);
    const int x = pad_x + 2; // chừa vạch trái 3px
    const int iw = std::max(1, w - x - pad_x);
    constexpr int kGapX = 10;
    constexpr int kBig = 100000;
    if (!wrap) {
        const int lw = std::min(iw, fl.horizontalAdvance(t.label));
        const int lh = fl.height();
        g.label = QRect(x, (row_h - lh) / 2, lw, lh);
        const int top = g.label.top() + fl.ascent() - fr.ascent(); // chung đường chân chữ với nhãn
        g.rest = QRect(x + lw + kGapX, top, std::max(0, iw - lw - kGapX), fr.height());
        g.h = row_h;
        return g;
    }
    const QRect lb = fl.boundingRect(QRect(0, 0, iw, kBig), Qt::TextWordWrap, t.label);
    g.label = QRect(x, pad_y, std::min(iw, lb.width() + 1), lb.height());
    int bottom = g.label.bottom() + 1;
    if (!t.rest.isEmpty()) {
        const int rw = fr.horizontalAdvance(t.rest);
        if (lb.height() <= fl.height() && g.label.width() + kGapX + rw <= iw) {
            const int top = pad_y + fl.ascent() - fr.ascent();
            g.rest = QRect(x + g.label.width() + kGapX, top, rw + 1, fr.height());
            bottom = std::max(bottom, g.rest.bottom() + 1);
        } else {
            const QRect rb = fr.boundingRect(QRect(0, 0, iw, kBig), Qt::TextWordWrap, t.rest);
            g.rest = QRect(x, bottom + 3, iw, rb.height());
            bottom = g.rest.bottom() + 1;
        }
    }
    g.h = std::max(row_h, bottom + pad_y);
    return g;
}

/// Vẽ nội dung hàng nhóm trong `cell` (nền + chữ; viền dưới do style của bảng, vạch trái do người gọi).
inline void paint_group(QPainter* p, const QRect& cell, const GroupText& t, const GroupFonts& f, const GroupGeo& g,
                        const QColor& bg, const QColor& label_c, const QColor& rest_c, bool wrap) {
    p->fillRect(cell.adjusted(0, 0, 0, -1), bg);
    p->setFont(f.label);
    p->setPen(label_c);
    p->drawText(g.label.translated(cell.topLeft()), Qt::AlignLeft | Qt::AlignTop | Qt::TextWordWrap, t.label);
    if (t.rest.isEmpty() || g.rest.width() <= 0)
        return;
    p->setFont(f.rest);
    p->setPen(rest_c);
    const QRect rr = g.rest.translated(cell.topLeft());
    if (wrap)
        p->drawText(rr, Qt::AlignLeft | Qt::AlignTop | Qt::TextWordWrap, t.rest);
    else
        p->drawText(rr, Qt::AlignLeft | Qt::AlignTop,
                    QFontMetrics(f.rest).elidedText(t.rest, Qt::ElideRight, rr.width()));
}

// ── Vai dữ liệu ô ──────────────────────────────────────────────────────────────

constexpr int kRoleKind = Qt::UserRole + 1;
constexpr int kRoleBarFrac = Qt::UserRole + 2;
constexpr int kRoleBarColor = Qt::UserRole + 3;
constexpr int kRoleTag = Qt::UserRole + 4;
constexpr int kRoleTagColor = Qt::UserRole + 5;
constexpr int kRoleVien = Qt::UserRole + 6;
constexpr int kRoleTip = Qt::UserRole + 7;
constexpr int kRoleMau = Qt::UserRole + 8; // chuỗi _mau gốc của ô (pill ở trang hồ sơ)
constexpr int kRoleNhom = Qt::UserRole + 9; // hàng đầu nhóm "_nhom": dòng phụ (QString, có thể rỗng); vắng = hàng thường

enum CellKind { KindText = 0, KindBar = 1, KindTag = 2 };

constexpr int kBarWidth = 56;

// ── Delegate ô bảng: bar · tag · _tag · _vien ─────────────────────────────────

class LkCellDelegate : public QStyledItemDelegate {
  public:
    LkCellDelegate(QObject* parent, bool hoso, bool wrap)
        : QStyledItemDelegate(parent), hoso_(hoso), wrap_(wrap), g_(cell_geo(hoso)) {}

    void paint(QPainter* p, const QStyleOptionViewItem& option, const QModelIndex& index) const override {
        const int kind = index.data(kRoleKind).toInt();
        const QString tag = index.data(kRoleTag).toString();
        const QVariant vien = index.data(kRoleVien);
        QStyleOptionViewItem plain(option);
        plain.state &= ~QStyle::State_HasFocus; // bảng chỉ đọc: không vẽ khung focus quanh ô hiện hành
        if (index.data(kRoleNhom).isValid()) {
            paint_group_cell(p, plain, index);
            paint_vien(p, option, vien);
            return;
        }
        if (kind == KindText && tag.isEmpty() && !wrap_) {
            QStyledItemDelegate::paint(p, plain, index); // chữ dài: style tự cắt "…" (ElideRight)
            paint_vien(p, option, vien);
            return;
        }

        QStyleOptionViewItem opt(plain);
        initStyleOption(&opt, index);
        const QString text = opt.text;
        opt.text.clear();
        const QWidget* w = opt.widget;
        QStyle* st = w ? w->style() : QApplication::style();
        st->drawControl(QStyle::CE_ItemViewItem, &opt, p, w); // nền, chọn dòng, viền theo QSS

        p->save();
        p->setRenderHint(QPainter::Antialiasing, true);
        p->setFont(opt.font);
        const QFontMetrics fm(opt.font);
        QColor fg(ui::colors::TEXT_PRIMARY());
        const QVariant fgv = index.data(Qt::ForegroundRole);
        if (fgv.canConvert<QBrush>()) {
            const QBrush b = fgv.value<QBrush>();
            if (b.style() != Qt::NoBrush)
                fg = b.color();
        }
        const Qt::Alignment align =
            qvariant_cast<Qt::Alignment>(index.data(Qt::TextAlignmentRole)) & Qt::AlignHorizontal_Mask;
        if (kind == KindText && tag.isEmpty()) { // wrap: chữ xuống dòng, canh trên (td{vertical-align:top})
            int flags = Qt::TextWordWrap | Qt::AlignTop;
            flags |= align.testFlag(Qt::AlignRight)     ? Qt::AlignRight
                     : align.testFlag(Qt::AlignHCenter) ? Qt::AlignHCenter
                                                        : Qt::AlignLeft;
            p->setPen(fg);
            p->drawText(opt.rect.adjusted(g_.pad_x, g_.pad_y, -g_.pad_x, -g_.pad_y), flags, text);
            p->restore();
            paint_vien(p, option, vien);
            return;
        }
        // wrap: bar/tag/_tag nằm ở dải một dòng trên cùng của ô cao.
        QRect cell = opt.rect;
        if (wrap_)
            cell.setHeight(std::min(cell.height(), g_.row_h));
        const QRect r = cell.adjusted(g_.pad_x, 0, -g_.pad_x, 0);
        auto start_x = [&](int total) {
            int x = r.left();
            if (align & Qt::AlignRight)
                x = r.right() - total + 1;
            else if (align & Qt::AlignHCenter)
                x = r.left() + (r.width() - total) / 2;
            return std::max(x, r.left());
        };

        if (kind == KindBar) {
            const int text_w = fm.horizontalAdvance(text);
            const int bw = bar_width(r.width(), text_w);
            const int x = start_x(bw + 6 + text_w);
            // Không có frac → KHÔNG vẽ rãnh: rãnh rỗng dễ bị đọc thành "P0 / cạn cung".
            const QVariant fv = index.data(kRoleBarFrac);
            if (fv.isValid()) {
                const QRectF track(x, r.center().y() - 3.0, bw, 7.0);
                p->setPen(Qt::NoPen);
                p->setBrush(QColor(ui::colors::BORDER_MED()));
                p->drawRoundedRect(track, 2.0, 2.0);
                const double frac = std::clamp(fv.toDouble(), 0.0, 1.0);
                QColor bc = index.data(kRoleBarColor).value<QColor>();
                if (!bc.isValid())
                    bc = QColor(ui::colors::AMBER());
                if (frac > 0.0) {
                    QRectF fill = track;
                    fill.setWidth(std::max(2.0, bw * frac));
                    p->setBrush(bc);
                    p->drawRoundedRect(fill, 2.0, 2.0);
                }
            }
            const int tx = x + bw + 6;
            const QRect tr(tx, r.top(), std::max(0, r.right() - tx + 1), r.height());
            p->setPen(fg);
            p->drawText(tr, Qt::AlignLeft | Qt::AlignVCenter, fm.elidedText(text, Qt::ElideRight, tr.width()));
        } else if (kind == KindTag && (text.isEmpty() || text == dash())) {
            p->setPen(QColor(ui::colors::TEXT_TERTIARY()));
            p->drawText(QRect(start_x(fm.horizontalAdvance(dash())), r.top(), r.width(), r.height()),
                        Qt::AlignLeft | Qt::AlignVCenter, dash());
        } else if (kind == KindTag && hoso_) { // pill bo tròn hẳn, không viền (Artifact .pill)
            const QSizeF ps = lk_pill_size(text, 11);
            const double pw = std::min(ps.width(), static_cast<double>(r.width()));
            const QRectF chip(start_x(static_cast<int>(std::ceil(pw))), r.center().y() + 0.5 - ps.height() / 2.0, pw,
                              ps.height());
            lk_paint_pill(*p, chip, text, lk_pill_role(index.data(kRoleMau).toString()), 11);
        } else if (kind == KindTag) {
            const QString shown = fm.elidedText(text, Qt::ElideRight, std::max(0, r.width() - 12));
            const int cw = fm.horizontalAdvance(shown) + 12;
            const int ch = std::min(r.height() - 6, fm.height() + 4);
            const QRectF chip(start_x(cw), r.center().y() - ch / 2.0, cw, ch);
            QColor bg = fg;
            bg.setAlpha(40);
            QColor border = fg;
            border.setAlpha(160);
            p->setPen(QPen(border, 1.0));
            p->setBrush(bg);
            p->drawRoundedRect(chip, 3.0, 3.0);
            p->setPen(fg);
            p->drawText(chip, Qt::AlignCenter, shown);
        } else {
            // Chữ + nhãn nhỏ phía sau (vd "FPT [12%]", "MBB [watch]").
            const QFont tf = tag_font(opt.font);
            const QFontMetrics tfm(tf);
            const int tag_w = tfm.horizontalAdvance(tag) + 8;
            const int avail = std::max(0, r.width() - 6 - tag_w);
            const QString shown = fm.elidedText(text, Qt::ElideRight, avail);
            const int text_w = fm.horizontalAdvance(shown);
            const int x = start_x(text_w + 6 + tag_w);
            p->setPen(fg);
            p->drawText(QRect(x, r.top(), text_w + 2, r.height()), Qt::AlignLeft | Qt::AlignVCenter, shown);
            QColor tc = index.data(kRoleTagColor).value<QColor>();
            if (!tc.isValid())
                tc = QColor(ui::colors::TEXT_SECONDARY());
            const qreal th = tfm.height() + 2.0;
            const QRectF chip(x + text_w + 6, r.center().y() - th / 2.0, tag_w, th);
            p->setPen(QPen(tc, 1.0));
            p->setBrush(Qt::NoBrush);
            p->drawRoundedRect(chip, 2.0, 2.0);
            p->setFont(tf);
            p->drawText(chip, Qt::AlignCenter, tag);
        }
        p->restore();
        paint_vien(p, option, vien);
    }

    QSize sizeHint(const QStyleOptionViewItem& option, const QModelIndex& index) const override {
        if (index.data(kRoleNhom).isValid()) // hàng nhóm gộp cột: không đẩy bề rộng cột 1
            return {0, g_.row_h};
        QSize s = QStyledItemDelegate::sizeHint(option, index);
        const int kind = index.data(kRoleKind).toInt();
        const QString tag = index.data(kRoleTag).toString();
        if (kind == KindText && tag.isEmpty())
            return s;
        QStyleOptionViewItem opt(option);
        initStyleOption(&opt, index);
        const int text_w = QFontMetrics(opt.font).horizontalAdvance(opt.text);
        int need = 0;
        const int pad = g_.pad_x;
        if (kind == KindBar)
            need = 2 * pad + kBarWidth + 6 + text_w + 4;
        else if (kind == KindTag && hoso_)
            need = 2 * pad + static_cast<int>(std::ceil(lk_pill_size(opt.text, 11).width())) + 4;
        else if (kind == KindTag)
            need = 2 * pad + text_w + 12 + 4;
        else
            need = 2 * pad + text_w + 6 + QFontMetrics(tag_font(opt.font)).horizontalAdvance(tag) + 8 + 4;
        s.setWidth(std::max(s.width(), need));
        return s;
    }

    /// Tooltip ô = [nguyên văn đầy đủ nếu chữ bị cắt] + [_tip của ô] + [gợi ý nhấp đúp của cột mã].
    bool helpEvent(QHelpEvent* e, QAbstractItemView* view, const QStyleOptionViewItem& option,
                   const QModelIndex& index) override {
        if (!e || !view || e->type() != QEvent::ToolTip)
            return QStyledItemDelegate::helpEvent(e, view, option, index);
        QStringList parts;
        QString text = index.data(Qt::DisplayRole).toString();
        if (const QString g = index.data(kRoleNhom).toString(); !g.isEmpty()) // hàng nhóm: nhãn · dòng phụ
            text += QStringLiteral(" · ") + g;
        if (is_elided(option, index, text))
            parts << text.toHtmlEscaped().replace(QLatin1Char('\n'), QStringLiteral("<br>"));
        const QString tip = index.data(kRoleTip).toString().trimmed();
        if (!tip.isEmpty()) // không tô màu riêng: nền tooltip do QSS chung của app quyết định
            parts << tip.toHtmlEscaped().replace(QLatin1Char('\n'), QStringLiteral("<br>"));
        const QString hint = index.data(Qt::ToolTipRole).toString().trimmed();
        if (!hint.isEmpty())
            parts << QStringLiteral("<i>%1</i>").arg(hint.toHtmlEscaped());
        if (parts.isEmpty()) {
            QToolTip::hideText();
            return true;
        }
        // Rich text ("<p>…") → QToolTip tự xuống dòng (~80 ký tự) thay vì một dòng dài hết màn hình.
        QToolTip::showText(e->globalPos(), QStringLiteral("<p>%1</p>").arg(parts.join(QStringLiteral("<br>"))),
                           view->viewport(), option.rect);
        return true;
    }

  private:
    static int bar_width(int avail, int text_w) { return std::clamp(avail - 6 - text_w, 20, kBarWidth); }

    static QFont tag_font(const QFont& base) {
        QFont tf = base;
        tf.setBold(false);
        if (tf.pixelSize() > 0)
            tf.setPixelSize(std::max(8, tf.pixelSize() - 2));
        else
            tf.setPointSizeF(std::max(7.0, tf.pointSizeF() * 0.82));
        return tf;
    }

    /// Chữ của ô có bị cắt "…" khi vẽ không (cùng phép tính bề rộng như paint()).
    bool is_elided(const QStyleOptionViewItem& option, const QModelIndex& index, const QString& text) const {
        if (text.isEmpty() || text == dash())
            return false;
        if (index.data(kRoleNhom).isValid()) // hàng nhóm: wrap không cắt; một dòng thì tooltip luôn có đủ chữ
            return !wrap_;
        if (wrap_ && index.data(kRoleKind).toInt() == KindText && index.data(kRoleTag).toString().isEmpty())
            return false; // xuống dòng: không bao giờ cắt
        QStyleOptionViewItem opt(option);
        initStyleOption(&opt, index);
        const QFontMetrics fm(opt.font);
        const int text_w = fm.horizontalAdvance(text);
        const int inner = opt.rect.width() - 2 * g_.pad_x;
        const int kind = index.data(kRoleKind).toInt();
        const QString tag = index.data(kRoleTag).toString();
        int avail = inner - 2; // style + QSS padding 8px mỗi bên
        if (kind == KindBar)
            avail = inner - 6 - bar_width(inner, text_w);
        else if (kind == KindTag)
            avail = hoso_ ? inner - 2 * 9 : inner - 12;
        else if (!tag.isEmpty())
            avail = inner - 6 - (QFontMetrics(tag_font(opt.font)).horizontalAdvance(tag) + 8);
        return text_w > avail;
    }

    bool hoso_ = false;
    bool wrap_ = false;
    CellGeo g_;

    /// Hàng đầu nhóm (ô gộp mọi cột): viền dưới theo QSS, nền surface-2, nhãn màu nhóm + dòng phụ muted.
    void paint_group_cell(QPainter* p, const QStyleOptionViewItem& plain, const QModelIndex& index) const {
        QStyleOptionViewItem opt(plain);
        initStyleOption(&opt, index);
        const GroupText t{opt.text, index.data(kRoleNhom).toString()};
        opt.text.clear();
        const QWidget* w = opt.widget;
        (w ? w->style() : QApplication::style())->drawControl(QStyle::CE_ItemViewItem, &opt, p, w);
        const GroupFonts f = group_fonts(hoso_, opt.font);
        const GroupGeo g = group_geo(t, f, opt.rect.width(), g_.pad_x, g_.pad_y, opt.rect.height(), wrap_);
        QColor lc = index.data(kRoleVien).value<QColor>();
        if (!lc.isValid())
            lc = hoso_ ? lk_col(LkRole::Amber) : QColor(ui::colors::AMBER());
        p->save();
        p->setRenderHint(QPainter::TextAntialiasing, true);
        paint_group(p, opt.rect, t, f, g, hoso_ ? lk_col(LkRole::Surface2) : QColor(ui::colors::BG_RAISED()), lc,
                    hoso_ ? lk_col(LkRole::Muted) : QColor(ui::colors::TEXT_SECONDARY()), wrap_);
        p->restore();
    }

    static void paint_vien(QPainter* p, const QStyleOptionViewItem& o, const QVariant& v) {
        if (!v.isValid())
            return;
        const QColor c = v.value<QColor>();
        if (!c.isValid())
            return;
        p->fillRect(QRect(o.rect.left(), o.rect.top() + 1, 3, std::max(0, o.rect.height() - 2)), c);
    }
};

} // namespace fincept::screens::langkinh::lkview
