// src/screens/langkinh/LkTableBlock.cpp
// Lăng Kính FFT — block "table": bảng sắp theo _sort (delegate bar · tag · _tag · _vien · hàng nhóm "_nhom" ở
// LkTableParts.h). Xem LkTableBlock.h.
// Hợp đồng block v2: "wrap":true → ô chữ xuống dòng (không "…"), hàng cao theo nội dung, cột chữ dài nhất giãn;
// khoá nội bộ "_hoso" (trang layout hoso) → thẻ .fig, ô sans 13 đệm 9/12, tiêu đề cột mono chữ hoa, kind tag = pill.
#include "screens/langkinh/LkTableBlock.h"

#include "screens/langkinh/LkBlockView.h"
#include "screens/langkinh/LkChips.h"
#include "screens/langkinh/LkPage.h"
#include "screens/langkinh/LkTableParts.h"
#include "screens/langkinh/LkTheme.h"
#include "ui/theme/Theme.h"

#include <QAbstractItemView>
#include <QFont>
#include <QFontMetrics>
#include <QFrame>
#include <QHeaderView>
#include <QJsonArray>
#include <QLabel>
#include <QPushButton>
#include <QRegularExpression>
#include <QResizeEvent>
#include <QScrollBar>
#include <QShowEvent>
#include <QSizePolicy>
#include <QTableWidget>
#include <QTableWidgetItem>
#include <QVBoxLayout>
#include <QWheelEvent>

#include <algorithm>
#include <cmath>
#include <numeric>
#include <utility>

namespace fincept::screens::langkinh::lkview {

constexpr int kMaxColWidth = 340; // bề rộng tự nhiên tối đa của một cột (chữ dài hơn → "…" + tooltip)
constexpr int kFlexFloor = 120;   // bảng rộng hơn khung: cột chữ rộng được co dần tới mức này (không hẹp hơn tiêu đề)
constexpr int kWordCap = 180;     // wrap: từ dài hơn không được đẩy bề rộng tối thiểu của cột quá mức này
// Vai dữ liệu ô, CellGeo/cell_geo, wrap_head, tag_color, hàng nhóm "_nhom" và LkCellDelegate: LkTableParts.h

// ── Bảng: sắp theo _sort khi bấm tiêu đề, cao vừa đủ số hàng ──────────────────

class LkTable : public QTableWidget {
  public:
    LkTable(const QJsonArray& cols, const QJsonArray& rows, bool links, TickerFn on_link, bool hoso, bool wrap,
            int max_rows, QWidget* parent)
        : QTableWidget(parent), max_rows_(std::max(0, max_rows)), links_(links), hoso_(hoso), wrap_(wrap),
          g_(cell_geo(hoso)), on_link_(std::move(on_link)) {
        if (hoso_)
            ensurePolished(); // phông QSS (sans 13) có hiệu lực trước khi đo cột và lấy phông đậm của cột đầu
        for (const auto& cv : cols) {
            const QJsonObject co = cv.toObject();
            Col c;
            c.key = co.value(QStringLiteral("key")).toString();
            if (c.key.isEmpty())
                continue;
            c.label = co.value(QStringLiteral("label")).toString().trimmed();
            if (c.label.isEmpty())
                c.label = c.key;
            if (hoso_) // th{text-transform:uppercase} — QSS không có text-transform
                c.label = c.label.toUpper();
            const QString k = co.value(QStringLiteral("kind")).toString();
            c.kind = k == QLatin1String("bar") ? KindBar : (k == QLatin1String("tag") ? KindTag : KindText);
            const QString al = co.value(QStringLiteral("align")).toString();
            if (al == QLatin1String("right"))
                c.align = Qt::AlignRight | Qt::AlignVCenter;
            else if (al == QLatin1String("center"))
                c.align = Qt::AlignHCenter | Qt::AlignVCenter;
            else
                c.align = Qt::AlignLeft | Qt::AlignVCenter;
            cols_.append(c);
        }
        for (const auto& rv : rows)
            if (rv.isObject())
                rows_.append(rv.toObject());
        order_.resize(rows_.size());
        std::iota(order_.begin(), order_.end(), 0);

        setItemDelegate(new LkCellDelegate(this, hoso_, wrap_));
        setEditTriggers(QAbstractItemView::NoEditTriggers);
        setSelectionBehavior(QAbstractItemView::SelectRows);
        setSelectionMode(QAbstractItemView::SingleSelection);
        setAlternatingRowColors(!hoso_); // hồ sơ: hàng phân bằng vạch line như Artifact, không sọc
        setShowGrid(false);
        setWordWrap(wrap_);
        setTextElideMode(wrap_ ? Qt::ElideNone : Qt::ElideRight);
        setVerticalScrollBarPolicy(Qt::ScrollBarAlwaysOff);
        setHorizontalScrollBarPolicy(Qt::ScrollBarAsNeeded);
        setSizePolicy(QSizePolicy::Expanding, QSizePolicy::Fixed);
        verticalHeader()->setVisible(false);
        verticalHeader()->setSectionResizeMode(QHeaderView::Fixed);
        verticalHeader()->setDefaultSectionSize(g_.row_h);

        QHeaderView* hh = horizontalHeader();
        hh->setSectionsClickable(true);
        hh->setSortIndicatorShown(false);
        hh->setHighlightSections(false);
        hh->setStretchLastSection(false);
        hh->setMinimumSectionSize(36);
        hh->setTextElideMode(Qt::ElideNone); // nhãn có thể 2 dòng; cột không bao giờ hẹp hơn nhãn (apply_widths)
        // Cùng font với "QHeaderView::section" trong LkBlockView::table_qss (10px, đậm, giãn chữ 0,5px)
        // hoặc hoso_table_qss (mono 11/600).
        QFont head_font = hh->font();
        head_font.setPixelSize(10);
        head_font.setBold(true);
        head_font.setLetterSpacing(QFont::AbsoluteSpacing, 0.5);
        if (hoso_)
            head_font = lk_font_mono(11, 600);
        const QFontMetrics head_fm(head_font);
        setColumnCount(static_cast<int>(cols_.size()));
        const int head_pad = hoso_ ? 28 : 20; // QSS padding ngang của tiêu đề cột (12/8 mỗi bên) + dư
        for (int c = 0; c < cols_.size(); ++c) {
            cols_[c].head2 = wrap_head(cols_[c].label, head_fm);
            cols_[c].head1_px = head_fm.horizontalAdvance(cols_[c].label) + head_pad;
            for (const QString& ln : cols_[c].head2.split(QLatin1Char('\n')))
                cols_[c].head2_px = std::max(cols_[c].head2_px, head_fm.horizontalAdvance(ln) + head_pad);
            auto* hi = new QTableWidgetItem(cols_[c].label);
            hi->setTextAlignment(cols_[c].align);
            hi->setToolTip(lk_tr("%1 — bấm để sắp xếp").arg(cols_[c].label));
            setHorizontalHeaderItem(c, hi);
        }
        connect(hh, &QHeaderView::sectionClicked, this, [this](int c) { sort_by(c); });
        connect(this, &QTableWidget::cellDoubleClicked, this, [this](int r, int) {
            if (!links_ || !on_link_ || r < 0 || r >= order_.size())
                return;
            const QString link = rows_[order_[r]].value(QStringLiteral("_link")).toString().trimmed();
            if (!link.isEmpty())
                on_link_(link);
        });
        populate();
    }

    /// "max_rows": số hàng đang ẩn (0 khi không giới hạn hoặc đã mở hết).
    int hidden_rows() const {
        return expanded_ || max_rows_ <= 0 ? 0 : std::max(0, static_cast<int>(order_.size()) - max_rows_);
    }
    int max_rows() const { return max_rows_; }
    bool expanded() const { return expanded_; }
    /// Mở hết / thu về max_rows hàng đầu — giữ thứ tự sắp hiện tại.
    void set_expanded(bool on) {
        if (on == expanded_)
            return;
        expanded_ = on;
        populate();
    }

  protected:
    void resizeEvent(QResizeEvent* e) override {
        QTableWidget::resizeEvent(e);
        apply_widths();
        fit_height();
    }

    void showEvent(QShowEvent* e) override {
        QTableWidget::showEvent(e);
        if (!shown_once_) {
            // Lần hiện đầu tiên QSS của trang đã áp (font 11px) → đo lại cột cho đúng.
            shown_once_ = true;
            size_columns();
        }
        fit_height();
    }

    void wheelEvent(QWheelEvent* e) override {
        // Bảng không cuộn dọc (cao vừa đủ hàng): nhường bánh xe dọc cho trang ngoài.
        const QPoint d = e->angleDelta();
        if (std::abs(d.y()) >= std::abs(d.x())) {
            e->ignore();
            return;
        }
        QTableWidget::wheelEvent(e);
    }

  private:
    struct Col {
        QString key;
        QString label;
        QString head2; // nhãn tách 2 dòng (dùng khi bảng rộng hơn khung)
        int head1_px = 0; // bề rộng nhãn 1 dòng / 2 dòng (kể cả đệm) — wrap: sàn của cột
        int head2_px = 0;
        int kind = KindText;
        Qt::Alignment align = Qt::AlignLeft | Qt::AlignVCenter;
    };

    void populate() {
        setUpdatesEnabled(false);
        clearContents();
        clearSpans();
        const int shown = static_cast<int>(order_.size()) - hidden_rows(); // "max_rows": chỉ N hàng đầu theo thứ tự sắp
        setRowCount(shown);
        QFont bold = font();
        bold.setBold(true);
        for (int r = 0; r < shown; ++r) {
            const QJsonObject& row = rows_[order_[r]];
            if (is_group_row(row)) {
                put_group(r, row);
                continue;
            }
            const QJsonObject mau = row.value(QStringLiteral("_mau")).toObject();
            const QJsonObject tag = row.value(QStringLiteral("_tag")).toObject();
            const QJsonObject bar = row.value(QStringLiteral("_bar")).toObject();
            const QJsonObject tip = row.value(QStringLiteral("_tip")).toObject();
            const QString vien = row.value(QStringLiteral("_vien")).toString().trimmed();
            const QString link = row.value(QStringLiteral("_link")).toString().trimmed();
            for (int c = 0; c < cols_.size(); ++c) {
                const Col& col = cols_[c];
                auto* it = new QTableWidgetItem(text_of(row.value(col.key)));
                it->setFlags(Qt::ItemIsEnabled | Qt::ItemIsSelectable);
                it->setTextAlignment(col.align);
                it->setData(kRoleKind, col.kind);
                const QString m = mau.value(col.key).toString().trimmed();
                if (!m.isEmpty()) {
                    it->setForeground(hoso_ ? lk_col(lk_role(m, LkRole::Ink)) : lk_color(m));
                    it->setData(kRoleMau, m);
                }
                if (col.kind == KindBar) {
                    const QJsonObject bo = bar.value(col.key).toObject();
                    double f = 0.0;
                    if (num_of(bo.value(QStringLiteral("frac")), &f)) {
                        it->setData(kRoleBarFrac, std::clamp(f, 0.0, 1.0));
                        const QString bm = bo.value(QStringLiteral("mau")).toString().trimmed();
                        it->setData(kRoleBarColor, bm.isEmpty() ? QColor(ui::colors::AMBER()) : lk_color(bm));
                    }
                }
                const QString t = tag.value(col.key).toString().trimmed();
                if (!t.isEmpty()) {
                    it->setData(kRoleTag, t);
                    it->setData(kRoleTagColor, tag_color(t));
                }
                const QString tp = tip.value(col.key).toString().trimmed();
                if (!tp.isEmpty())
                    it->setData(kRoleTip, tp);
                if (c == 0) {
                    if (!vien.isEmpty())
                        it->setData(kRoleVien, lk_color(vien));
                    it->setFont(bold);
                    if (links_ && !link.isEmpty())
                        it->setToolTip(lk_tr("Nhấp đúp để mở chuỗi FFT × Giá của %1").arg(link));
                }
                setItem(r, c, it);
            }
        }
        size_columns();
        setUpdatesEnabled(true);
        fit_height();
    }

    /// Hàng đầu nhóm "_nhom": một ô gộp mọi cột, không chọn được; màu nhóm = _vien, không có thì _mau của cột 1.
    void put_group(int r, const QJsonObject& row) {
        QStringList keys;
        for (const Col& c : std::as_const(cols_))
            keys << c.key;
        const GroupText t = group_text(row, keys);
        auto* it = new QTableWidgetItem(t.label);
        it->setFlags(Qt::ItemIsEnabled);
        it->setData(kRoleNhom, t.rest);
        QString m = row.value(QStringLiteral("_vien")).toString().trimmed();
        if (m.isEmpty() && !keys.isEmpty())
            m = row.value(QStringLiteral("_mau")).toObject().value(keys.first()).toString().trimmed();
        it->setData(kRoleVien, hoso_ ? lk_col(lk_role(m, LkRole::Amber))
                                     : (m.isEmpty() ? QColor(ui::colors::AMBER()) : lk_color(m)));
        setItem(r, 0, it);
        if (cols_.size() > 1)
            setSpan(r, 0, 1, static_cast<int>(cols_.size()));
    }

    /// Nhãn cột 1 dòng (bảng vừa khung) hoặc 2 dòng (bảng rộng hơn khung).
    void set_two_line_head(bool two) {
        if (two == two_line_head_)
            return;
        two_line_head_ = two;
        for (int c = 0; c < cols_.size() && c < columnCount(); ++c)
            if (QTableWidgetItem* hi = horizontalHeaderItem(c))
                hi->setText(two ? cols_[c].head2 : cols_[c].label);
        updateGeometries(); // chiều cao tiêu đề đổi theo số dòng nhãn
    }

    /// Đo bề rộng tự nhiên (chặn kMaxColWidth) với kiểu nhãn cho trước; floor = mức co tối thiểu
    /// (không hẹp hơn nhãn cột, không dưới kFlexFloor trừ khi tự nhiên đã hẹp hơn).
    void measure(bool two, QVector<int>& natural, QVector<int>* floor, QVector<int>* raw = nullptr) {
        set_two_line_head(two);
        resizeColumnsToContents();
        const int n = columnCount();
        natural.resize(n);
        if (floor)
            floor->resize(n);
        if (raw)
            raw->resize(n);
        for (int c = 0; c < n; ++c) {
            if (raw)
                (*raw)[c] = columnWidth(c); // chưa chặn — để tìm cột chữ dài nhất (wrap)
            natural[c] = std::min(columnWidth(c), kMaxColWidth);
            if (floor)
                (*floor)[c] = std::min(natural[c], std::max(kFlexFloor, horizontalHeader()->sectionSizeHint(c)));
        }
    }

    void size_columns() {
        measure(true, natural2_, &floor2_);
        measure(false, natural1_, nullptr, &raw1_);
        if (wrap_)
            minc_ = min_content();
        apply_widths();
    }

    /// wrap: bề rộng tối thiểu theo nội dung của mỗi cột = từ dài nhất (chặn kWordCap) + đệm ô.
    QVector<int> min_content() const {
        static const QRegularExpression ws(QStringLiteral("\\s+"));
        QVector<int> out(columnCount(), 0);
        for (int r = 0; r < rowCount(); ++r)
            for (int c = 0; c < columnCount(); ++c) {
                const QTableWidgetItem* it = item(r, c);
                if (!it || it->data(kRoleNhom).isValid()) // hàng nhóm gộp cột: không đặt sàn cho cột nào
                    continue;
                const QVariant fv = it->data(Qt::FontRole);
                const QFontMetrics fm(fv.isValid() ? fv.value<QFont>() : font());
                for (const QString& wd : it->text().split(ws, Qt::SkipEmptyParts))
                    out[c] = std::max(out[c], std::min(kWordCap, fm.horizontalAdvance(wd)) + 2 * g_.pad_x + 2);
            }
        return out;
    }

    /// Vừa khung với nhãn 1 dòng: nới đều các cột theo tỉ lệ (tối đa ×1,8) thay vì kéo giãn một cột cuối.
    /// Rộng hơn khung: nhãn dài xuống 2 dòng; còn rộng thì co các cột chữ rộng (theo phần vượt floor) cho
    /// vừa khung — chữ bị cắt "…" vẫn xem đủ qua tooltip; co hết mức mà vẫn rộng hơn thì cuộn ngang.
    void apply_widths() {
        if (wrap_) {
            apply_widths_wrap();
            return;
        }
        const int avail = viewport()->width();
        if (natural1_.isEmpty() || avail <= 0)
            return;
        const auto sum = [](const QVector<int>& v) { return std::accumulate(v.begin(), v.end(), 0); };
        const int total1 = sum(natural1_);
        const bool two = total1 > avail;
        set_two_line_head(two);
        const QVector<int>& nat = two ? natural2_ : natural1_;
        const int total = two ? sum(natural2_) : total1;
        if (total <= avail) {
            const double scale = total > 0 ? std::min(1.8, static_cast<double>(avail) / total) : 1.0;
            for (int c = 0; c < nat.size() && c < columnCount(); ++c)
                setColumnWidth(c, static_cast<int>(nat[c] * scale));
            return;
        }
        int flex = 0;
        for (int c = 0; c < nat.size(); ++c)
            flex += nat[c] - floor2_[c];
        const double ratio = flex > 0 ? std::min(1.0, static_cast<double>(total - avail) / flex) : 0.0;
        for (int c = 0; c < nat.size() && c < columnCount(); ++c)
            setColumnWidth(c, nat[c] - static_cast<int>(std::ceil((nat[c] - floor2_[c]) * ratio)));
    }

    /// wrap: bảng tự động kiểu CSS (lk_auto_col_widths) — cột chữ: min = max(từ dài nhất, nhãn 2 dòng), max = chữ một
    /// dòng; bar/tag giữ bề rộng tự nhiên; chỉ cuộn ngang khi Σmin > khung. Cột hẹp hơn nhãn 1 dòng → nhãn 2 dòng.
    void apply_widths_wrap() {
        const int avail = viewport()->width();
        const int n = std::min(static_cast<int>(natural1_.size()), columnCount());
        if (n == 0 || avail <= 0 || raw1_.size() < n || minc_.size() < n)
            return;
        QVector<int> mn(n);
        QVector<int> mx(n);
        int longest = -1;
        for (int c = 0; c < n; ++c) {
            if (cols_[c].kind != KindText) {
                mn[c] = mx[c] = natural1_[c];
                continue;
            }
            mx[c] = std::max(raw1_[c], cols_[c].head1_px);
            mn[c] = std::min(mx[c], std::max(minc_[c], cols_[c].head2_px));
            if (longest < 0 || raw1_[c] > raw1_[longest])
                longest = c;
        }
        const QVector<int> w = lk_auto_col_widths(mn, mx, avail, longest);
        bool two = false;
        for (int c = 0; c < n; ++c)
            two = two || w[c] < cols_[c].head1_px;
        set_two_line_head(two);
        for (int c = 0; c < n; ++c)
            setColumnWidth(c, w[c]);
        fit_rows();
    }

    /// wrap: hàng cao = max(một dòng, chữ gói trong bề rộng cột + đệm trên/dưới) — cùng phép đo với delegate.
    void fit_rows() {
        for (int r = 0; r < rowCount(); ++r) {
            int h = g_.row_h;
            if (const QTableWidgetItem* gi = item(r, 0); gi && gi->data(kRoleNhom).isValid()) { // hàng nhóm gộp cột
                int w = 0;
                for (int c = 0; c < columnCount(); ++c)
                    w += columnWidth(c);
                const GroupText t{gi->text(), gi->data(kRoleNhom).toString()};
                h = group_geo(t, group_fonts(hoso_, font()), w, g_.pad_x, g_.pad_y, g_.row_h, true).h;
                if (rowHeight(r) != h)
                    setRowHeight(r, h);
                continue;
            }
            for (int c = 0; c < columnCount() && c < cols_.size(); ++c) {
                const QTableWidgetItem* it = item(r, c);
                if (!it || cols_[c].kind != KindText || !it->data(kRoleTag).toString().isEmpty())
                    continue;
                const QString t = it->text();
                if (t.isEmpty())
                    continue;
                const QVariant fv = it->data(Qt::FontRole);
                const QFont f = fv.isValid() ? fv.value<QFont>() : font();
                const int tw = std::max(1, columnWidth(c) - 2 * g_.pad_x);
                const int th = QFontMetrics(f).boundingRect(QRect(0, 0, tw, 100000), Qt::TextWordWrap, t).height();
                h = std::max(h, th + 2 * g_.pad_y);
            }
            if (rowHeight(r) != h)
                setRowHeight(r, h);
        }
    }

    void sort_by(int col) {
        if (col < 0 || col >= cols_.size())
            return;
        if (sort_col_ == col) {
            sort_order_ = sort_order_ == Qt::AscendingOrder ? Qt::DescendingOrder : Qt::AscendingOrder;
        } else {
            sort_col_ = col;
            sort_order_ = Qt::AscendingOrder;
        }
        const QString key = cols_[col].key;
        struct Key {
            bool has_num = false;
            double num = 0.0;
            bool empty = true;
            QString text;
        };
        QVector<Key> keys(rows_.size());
        QVector<int> grp(rows_.size()); // hàng nhóm "_nhom": sắp trong từng nhóm, đầu nhóm đứng đầu nhóm của nó
        QVector<bool> head(rows_.size());
        bool any_num = false;
        for (int i = 0, g = -1; i < rows_.size(); ++i) {
            head[i] = is_group_row(rows_[i]);
            g = head[i] ? i : g;
            grp[i] = g;
            Key& k = keys[i];
            k.has_num = num_of(rows_[i].value(QStringLiteral("_sort")).toObject().value(key), &k.num);
            k.text = text_of(rows_[i].value(key));
            k.empty = k.text == dash();
            any_num = any_num || k.has_num;
        }
        const Qt::SortOrder ord = sort_order_;
        // Có _sort số → sắp theo số; hàng thiếu số/thiếu chữ luôn nằm cuối ở cả hai chiều.
        std::stable_sort(order_.begin(), order_.end(), [&](int a, int b) {
            if (grp[a] != grp[b])
                return grp[a] < grp[b];
            if (head[a] != head[b])
                return head[a];
            const Key& ka = keys[a];
            const Key& kb = keys[b];
            const bool miss_a = any_num ? !ka.has_num : ka.empty;
            const bool miss_b = any_num ? !kb.has_num : kb.empty;
            if (miss_a != miss_b)
                return miss_b;
            if (miss_a)
                return false;
            int cmp = 0;
            if (any_num)
                cmp = ka.num < kb.num ? -1 : (ka.num > kb.num ? 1 : 0);
            else
                cmp = QString::localeAwareCompare(ka.text, kb.text);
            return ord == Qt::AscendingOrder ? cmp < 0 : cmp > 0;
        });
        horizontalHeader()->setSortIndicatorShown(true);
        horizontalHeader()->setSortIndicator(col, sort_order_);
        populate();
    }

    void fit_height() {
        int rows_h = rowCount() * kRowHeight;
        if (hoso_ || wrap_) { // hàng cao khác nhau (wrap) hoặc 36px (hồ sơ)
            rows_h = 0;
            for (int r = 0; r < rowCount(); ++r)
                rows_h += rowHeight(r);
        }
        int h = 2 * frameWidth() + horizontalHeader()->sizeHint().height() + rows_h;
        const int avail = viewport()->width() > 0 ? viewport()->width() : width();
        if (horizontalHeader()->length() > avail + 1)
            h += horizontalScrollBar()->sizeHint().height();
        if (h != height() || minimumHeight() != h)
            setFixedHeight(h);
    }

    QVector<Col> cols_;
    QVector<QJsonObject> rows_;
    QVector<int> order_;
    QVector<int> natural1_; // bề rộng cột theo nội dung, nhãn 1 dòng (đã chặn kMaxColWidth)
    QVector<int> natural2_; // như trên, nhãn 2 dòng
    QVector<int> floor2_;   // bề rộng tối thiểu khi phải co cho vừa khung (nhãn 2 dòng)
    QVector<int> raw1_;     // bề rộng nội dung CHƯA chặn, nhãn 1 dòng (wrap: tìm cột chữ dài nhất)
    QVector<int> minc_;     // wrap: bề rộng tối thiểu theo từ dài nhất của mỗi cột
    bool two_line_head_ = false;
    int sort_col_ = -1;
    int max_rows_ = 0; // 0 = hiện mọi hàng
    bool expanded_ = false;
    Qt::SortOrder sort_order_ = Qt::AscendingOrder;
    bool links_ = true;
    bool hoso_ = false;
    bool wrap_ = false;
    CellGeo g_;
    bool shown_once_ = false;
    TickerFn on_link_;
};

// ── Block ─────────────────────────────────────────────────────────────────────

/// "Hiện thêm N dòng" / "Thu gọn về N dòng đầu" dưới bảng có max_rows (nút chữ, giữ thứ tự sắp hiện tại).
QPushButton* make_more_button(LkTable* table, bool hoso, QWidget* parent) {
    auto* btn = new QPushButton(parent);
    btn->setFlat(true);
    btn->setCursor(Qt::PointingHandCursor);
    const QFont f = hoso ? lk_font_mono(12, 600) : QFont();
    btn->setStyleSheet(QStringLiteral("QPushButton { background:transparent; border:none; color:%1; padding:6px 0px;"
                                      " text-align:left; %2 } QPushButton:hover { text-decoration:underline; }")
                           .arg(hoso ? lk_col(LkRole::Amber).name() : QString(ui::colors::AMBER()),
                                hoso ? lk_font_css(f) : QStringLiteral("font-size:11px; font-weight:700;")));
    const int hidden = table->hidden_rows();
    const auto label = [table, hidden]() {
        return table->expanded() ? lk_tr("Thu gọn về %1 dòng đầu").arg(table->max_rows())
                                 : lk_tr("Hiện thêm %1 dòng").arg(hidden);
    };
    btn->setText(label());
    QObject::connect(btn, &QPushButton::clicked, btn, [table, btn, label]() {
        table->set_expanded(!table->expanded());
        btn->setText(label());
    });
    return btn;
}

QWidget* make_table_block(const QJsonObject& b, QWidget* parent, const TickerFn& on_link) {
    const bool hoso = b.value(QStringLiteral("_hoso")).toBool(false);
    const bool wrap = b.value(QStringLiteral("wrap")).toBool(false);
    QFrame* card = nullptr;
    QVBoxLayout* vl = nullptr;
    if (hoso) { // thẻ .fig của trang hồ sơ
        card = make_fig(parent, &vl);
        lk_add_head(vl, b, card, LkHead::Fig);
    } else {
        card = new QFrame(parent);
        card->setObjectName(QStringLiteral("lkCard"));
        vl = new QVBoxLayout(card);
        vl->setContentsMargins(10, 8, 10, 8);
        vl->setSpacing(5);
        add_head(vl, b, card);
    }

    const QJsonArray cols = b.value(QStringLiteral("cols")).toArray();
    const QJsonArray rows = b.value(QStringLiteral("rows")).toArray();
    const bool links = b.value(QStringLiteral("row_link")).toBool(true);
    LkTable* table = nullptr;
    if (!cols.isEmpty() && !rows.isEmpty()) {
        table = new LkTable(cols, rows, links, on_link, hoso, wrap, b.value(QStringLiteral("max_rows")).toInt(0), card);
        if (table->columnCount() == 0) {
            delete table;
            table = nullptr;
        }
    }
    if (table) {
        vl->addWidget(table);
        if (table->hidden_rows() > 0)
            vl->addWidget(make_more_button(table, hoso, card));
    }
    else if (hoso)
        vl->addWidget(lk_label(lk_tr("— không có dòng nào —"), lk_font_sans(12), lk_col(LkRole::Muted), card));
    else
        vl->addWidget(make_label(lk_tr("— không có dòng nào —"), "lkCap", card));

    const QString caption = b.value(QStringLiteral("caption")).toString().trimmed();
    if (!caption.isEmpty()) {
        if (hoso)
            vl->addWidget(lk_label(lk_inline_html(caption, lk_col(LkRole::Ink2)), lk_font_sans(12),
                                   lk_col(LkRole::Muted), card, Qt::RichText));
        else
            vl->addWidget(make_label(caption, "lkCap", card, Qt::AutoText));
    }
    if (hoso) // thẻ .fig trong "row": phần cao dư dồn xuống đáy
        vl->addStretch(1);
    return card;
}

} // namespace fincept::screens::langkinh::lkview
