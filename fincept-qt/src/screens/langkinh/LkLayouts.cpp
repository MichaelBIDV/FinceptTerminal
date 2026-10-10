// src/screens/langkinh/LkLayouts.cpp
// Lăng Kính FFT — QLayout tự viết của trang hồ sơ. Xem LkLayouts.h.
// LkWrapLayout / LkAutoGridLayout chuyển nguyên văn từ LkChips.cpp (giữ hành vi cũ).
#include "screens/langkinh/LkLayouts.h"

#include <QLayoutItem>
#include <QString>
#include <QVariant>
#include <QWidget>

#include <algorithm>
#include <cmath>
#include <limits>
#include <utility>

// Helper tự do: namespace có tên riêng (quy ước của module, không dùng namespace ẩn danh).
namespace fincept::screens::langkinh::lklayouts {

/// Cao của mục tại bề rộng w (heightForWidth nếu có), không thấp hơn minimum.
int item_h(QLayoutItem* it, int w) {
    const int h = it->hasHeightForWidth() ? it->heightForWidth(w) : it->sizeHint().height();
    return std::max(h, it->minimumSize().height());
}

constexpr int kNoCap = std::numeric_limits<int>::max();

/// Bề rộng tối đa KHAI RÕ của một mục "row": maximumWidth đặt tay trên widget, hoặc property kRowMaxWProp (px > 0).
/// Không dùng QLayoutItem::maximumSize() — nó tự suy từ size policy, sẽ đổi bố cục của các hàng cũ.
int row_cap(QLayoutItem* it) {
    int cap = kNoCap;
    if (const QWidget* w = it->widget()) {
        if (w->maximumWidth() < QWIDGETSIZE_MAX)
            cap = w->maximumWidth();
        bool ok = false;
        const int p = w->property(lkview::kRowMaxWProp).toInt(&ok);
        if (ok && p > 0)
            cap = std::min(cap, p);
    }
    return cap;
}

} // namespace fincept::screens::langkinh::lklayouts

namespace fincept::screens::langkinh::lkview {

using lklayouts::item_h;
using lklayouts::kNoCap;

// ── LkWrapLayout ──────────────────────────────────────────────────────────────

LkWrapLayout::LkWrapLayout(QWidget* parent, int hspace, int vspace, bool center)
    : QLayout(parent), h_(std::max(0, hspace)), v_(std::max(0, vspace)), center_(center) {
    setContentsMargins(0, 0, 0, 0);
}

LkWrapLayout::~LkWrapLayout() {
    while (QLayoutItem* it = takeAt(0))
        delete it;
}

QSize LkWrapLayout::sizeHint() const {
    int w = 0;
    int n = 0;
    for (QLayoutItem* it : items_) {
        if (it->isEmpty())
            continue;
        w += it->sizeHint().width();
        ++n;
    }
    const QMargins m = contentsMargins();
    w = std::min(w + std::max(0, n - 1) * h_, 900) + m.left() + m.right();
    return {w, heightForWidth(w)};
}

QSize LkWrapLayout::minimumSize() const {
    QSize s(0, 0);
    for (QLayoutItem* it : items_)
        if (!it->isEmpty())
            s = s.expandedTo(it->minimumSize());
    const QMargins m = contentsMargins();
    return s + QSize(m.left() + m.right(), m.top() + m.bottom());
}

int LkWrapLayout::do_layout(const QRect& rect, bool test_only) const {
    const QMargins m = contentsMargins();
    const QRect r = rect.adjusted(m.left(), m.top(), -m.right(), -m.bottom());
    const int avail = std::max(1, r.width());
    struct Placed {
        QLayoutItem* it;
        int w;
        int h;
    };
    QList<QList<Placed>> lines;
    QList<int> line_h;
    int x = 0;
    for (QLayoutItem* it : items_) {
        if (it->isEmpty())
            continue;
        const QSize sh = it->sizeHint();
        const int w = std::max(1, std::min(sh.width(), avail));
        const int h = it->hasHeightForWidth() ? it->heightForWidth(w) : sh.height();
        if (lines.isEmpty() || (x > 0 && x + w > avail)) {
            lines.append(QList<Placed>());
            line_h.append(0);
            x = 0;
        }
        lines.last().append(Placed{it, w, h});
        line_h.last() = std::max(line_h.last(), h);
        x += w + h_;
    }
    int y = r.y();
    for (int li = 0; li < lines.size(); ++li) {
        if (!test_only) {
            int xx = r.x();
            for (const Placed& pl : std::as_const(lines[li])) {
                const int dy = center_ ? (line_h[li] - pl.h) / 2 : 0;
                pl.it->setGeometry(QRect(xx, y + dy, pl.w, pl.h));
                xx += pl.w + h_;
            }
        }
        y += line_h[li] + (li + 1 < lines.size() ? v_ : 0);
    }
    return y - r.y() + m.top() + m.bottom();
}

// ── LkAutoGridLayout ──────────────────────────────────────────────────────────

LkAutoGridLayout::LkAutoGridLayout(QWidget* parent, int min_col_w, int max_cols, int gap)
    : QLayout(parent), min_w_(std::max(1, min_col_w)), max_cols_(max_cols), gap_(std::max(0, gap)) {
    setContentsMargins(0, 0, 0, 0);
}

LkAutoGridLayout::~LkAutoGridLayout() {
    while (QLayoutItem* it = takeAt(0))
        delete it;
}

int LkAutoGridLayout::columns_for(int w) const {
    const int n = static_cast<int>(std::count_if(items_.cbegin(), items_.cend(), [](QLayoutItem* it) {
        return !it->isEmpty();
    }));
    if (n == 0)
        return 1;
    int cols = std::max(1, (w + gap_) / (min_w_ + gap_));
    if (max_cols_ > 0)
        cols = std::min(cols, max_cols_);
    return keep_tracks_ ? cols : std::max(1, std::min(cols, n));
}

QSize LkAutoGridLayout::sizeHint() const {
    const int n = static_cast<int>(std::count_if(items_.cbegin(), items_.cend(), [](QLayoutItem* it) {
        return !it->isEmpty();
    }));
    int cols = std::max(1, std::min(n, 4));
    if (max_cols_ > 0)
        cols = std::min(cols, max_cols_);
    const QMargins m = contentsMargins();
    const int w = cols * min_w_ + (cols - 1) * gap_ + m.left() + m.right();
    return {w, heightForWidth(w)};
}

QSize LkAutoGridLayout::minimumSize() const {
    QSize s(0, 0);
    for (QLayoutItem* it : items_)
        if (!it->isEmpty())
            s = s.expandedTo(it->minimumSize());
    s.setWidth(std::min(s.width(), min_w_)); // hẹp hơn một cột tối thiểu thì co mục, không đẩy trang cuộn ngang
    const QMargins m = contentsMargins();
    return s + QSize(m.left() + m.right(), m.top() + m.bottom());
}

int LkAutoGridLayout::do_layout(const QRect& rect, bool test_only) const {
    const QMargins m = contentsMargins();
    const QRect r = rect.adjusted(m.left(), m.top(), -m.right(), -m.bottom());
    QList<QLayoutItem*> vis;
    for (QLayoutItem* it : items_)
        if (!it->isEmpty())
            vis << it;
    const int n = static_cast<int>(vis.size());
    if (n == 0 || r.width() <= 0)
        return m.top() + m.bottom();
    const int cols = columns_for(r.width());
    const int avail = std::max(cols, r.width() - (cols - 1) * gap_);
    const auto col_w = [avail, cols](int j) { return avail / cols + (j < avail % cols ? 1 : 0); };
    int y = r.y();
    for (int first = 0; first < n; first += cols) {
        const int last = std::min(n, first + cols);
        int rh = 0;
        for (int i = first; i < last; ++i)
            rh = std::max(rh, item_h(vis[i], col_w(i - first)));
        if (!test_only) {
            int x = r.x();
            for (int i = first; i < last; ++i) {
                const int cw = col_w(i - first);
                vis[i]->setGeometry(QRect(x, y, cw, rh));
                x += cw + gap_;
            }
        }
        y += rh + (last < n ? gap_ : 0);
    }
    return y - r.y() + m.top() + m.bottom();
}

// ── Bề rộng cột bảng wrap ─────────────────────────────────────────────────────

QVector<int> lk_auto_col_widths(const QVector<int>& mn, const QVector<int>& mx, int avail, int stretch) {
    const int n = static_cast<int>(std::min(mn.size(), mx.size()));
    QVector<int> w(n);
    int smin = 0;
    int smax = 0;
    for (int c = 0; c < n; ++c) {
        smin += mn[c];
        smax += std::max(mn[c], mx[c]);
    }
    for (int c = 0; c < n; ++c) {
        const int hi = std::max(mn[c], mx[c]);
        if (smax <= avail || smax == smin)
            w[c] = hi;
        else if (smin >= avail)
            w[c] = mn[c];
        else
            w[c] = mn[c] + static_cast<int>((hi - mn[c]) * (static_cast<double>(avail - smin) / (smax - smin)));
    }
    int used = 0;
    for (const int v : std::as_const(w))
        used += v;
    if (stretch >= 0 && stretch < n && used < avail) // dư (bảng hẹp hơn khung, hoặc phần lẻ khi chia) → cột giãn
        w[stretch] += avail - used;
    return w;
}

// ── LkColumnLayout ────────────────────────────────────────────────────────────

LkColumnLayout::LkColumnLayout(QWidget* parent, int max_w, Qt::Alignment align)
    : QLayout(parent), max_w_(std::max(1, max_w)), align_(align) {
    setContentsMargins(0, 0, 0, 0);
}

LkColumnLayout::~LkColumnLayout() {
    while (QLayoutItem* it = takeAt(0))
        delete it;
}

QSize LkColumnLayout::sizeHint() const {
    int w = 0;
    for (QLayoutItem* it : items_)
        if (!it->isEmpty())
            w = std::max(w, it->sizeHint().width());
    const QMargins m = contentsMargins();
    w = std::min(w, max_w_) + m.left() + m.right();
    return {w, heightForWidth(w)};
}

QSize LkColumnLayout::minimumSize() const {
    QSize s(0, 0);
    for (QLayoutItem* it : items_)
        if (!it->isEmpty())
            s = s.expandedTo(it->minimumSize());
    s.setWidth(std::min(s.width(), max_w_));
    const QMargins m = contentsMargins();
    return s + QSize(m.left() + m.right(), m.top() + m.bottom());
}

int LkColumnLayout::do_layout(const QRect& rect, bool test_only) const {
    const QMargins m = contentsMargins();
    const QRect r = rect.adjusted(m.left(), m.top(), -m.right(), -m.bottom());
    const int w = std::max(0, std::min(r.width(), max_w_));
    int x = r.x();
    if (align_.testFlag(Qt::AlignHCenter))
        x += (r.width() - w) / 2;
    else if (align_.testFlag(Qt::AlignRight))
        x += r.width() - w;
    int last = -1;
    for (int i = 0; i < items_.size(); ++i)
        if (!items_.at(i)->isEmpty())
            last = i;
    int y = r.y();
    for (int i = 0; i <= last; ++i) {
        QLayoutItem* it = items_.at(i);
        if (it->isEmpty())
            continue;
        const int h = item_h(it, w);
        if (!test_only) {
            // Mục cuối lấp phần cao còn lại (trang: khoảng giãn cuối cột hút phần thừa của viewport).
            const int gh = (i == last) ? std::max(h, r.bottom() + 1 - y) : h;
            it->setGeometry(QRect(x, y, w, gh));
        }
        y += h;
    }
    return y - r.y() + m.top() + m.bottom();
}

// ── LkRowLayout ───────────────────────────────────────────────────────────────

LkRowLayout::LkRowLayout(QWidget* parent, int gap, int stack_below)
    : QLayout(parent), gap_(std::max(0, gap)), stack_below_(std::max(0, stack_below)) {
    setContentsMargins(0, 0, 0, 0);
}

LkRowLayout::~LkRowLayout() {
    while (QLayoutItem* it = takeAt(0))
        delete it;
}

QSize LkRowLayout::sizeHint() const {
    int w = 0;
    int n = 0;
    for (QLayoutItem* it : items_) {
        if (it->isEmpty())
            continue;
        w += it->sizeHint().width();
        ++n;
    }
    const QMargins m = contentsMargins();
    w = std::max(w + std::max(0, n - 1) * gap_, stack_below_) + m.left() + m.right();
    return {w, heightForWidth(w)};
}

QSize LkRowLayout::minimumSize() const {
    QSize s(0, 0); // hẹp thì xếp dọc → tối thiểu là mục rộng nhất, không phải tổng các mục
    for (QLayoutItem* it : items_)
        if (!it->isEmpty())
            s = s.expandedTo(it->minimumSize());
    const QMargins m = contentsMargins();
    return s + QSize(m.left() + m.right(), m.top() + m.bottom());
}

QVector<int> LkRowLayout::side_widths(const QList<QLayoutItem*>& vis, int width) const {
    const int n = static_cast<int>(vis.size());
    const int avail = std::max(n, width - (n - 1) * gap_);
    QVector<int> cap(n);
    int n_free = 0;
    int fixed = 0;
    for (int i = 0; i < n; ++i) {
        cap[i] = lklayouts::row_cap(vis[i]);
        if (cap[i] < kNoCap)
            fixed += cap[i];
        else
            ++n_free;
    }
    if (width < stack_below_) { // hẹp: chỉ đứng cạnh nhau khi mục cố định hẹp vẫn chừa đủ chỗ cho mục còn lại
        const int rest = avail - fixed;
        if (n_free == n || (n_free > 0 ? rest < n_free * (stack_below_ / 2) : rest < 0))
            return {};
    }
    QVector<double> wt(n, 1.0);
    if (flex_.size() == n && std::all_of(flex_.cbegin(), flex_.cend(), [](double f) { return f > 0.0; }))
        wt = flex_;
    QVector<int> out(n, 0);
    QVector<int> free;
    for (int i = 0; i < n; ++i)
        free << i;
    int remaining = avail;
    const auto weight = [&wt](const QVector<int>& ids) {
        double s = 0.0;
        for (const int j : ids)
            s += wt[j];
        return s;
    };
    for (bool capped = true; capped && !free.isEmpty();) { // chia theo trọng số; mục vượt mức tối đa nhận đúng mức
        capped = false;
        const double W = weight(free);
        QVector<int> keep;
        for (const int j : std::as_const(free)) {
            if (cap[j] < remaining * wt[j] / W) {
                out[j] = cap[j];
                capped = true;
            } else {
                keep << j;
            }
        }
        for (const int j : std::as_const(free))
            if (!keep.contains(j))
                remaining -= cap[j];
        free = keep;
    }
    if (!free.isEmpty()) { // phần còn lại theo trọng số, phần lẻ cho các mục đầu (chia đều = avail/n như trước)
        const double W = weight(free);
        int used = 0;
        for (const int j : std::as_const(free)) {
            out[j] = static_cast<int>(std::floor(remaining * wt[j] / W));
            used += out[j];
        }
        for (int k = 0, left = remaining - used; k < free.size() && left > 0; ++k, --left)
            ++out[free[k]];
    }
    return out;
}

int LkRowLayout::do_layout(const QRect& rect, bool test_only) const {
    const QMargins m = contentsMargins();
    const QRect r = rect.adjusted(m.left(), m.top(), -m.right(), -m.bottom());
    QList<QLayoutItem*> vis;
    for (QLayoutItem* it : items_)
        if (!it->isEmpty())
            vis << it;
    const int n = static_cast<int>(vis.size());
    if (n == 0 || r.width() <= 0)
        return m.top() + m.bottom();
    const QVector<int> cw = n > 1 ? side_widths(vis, r.width()) : QVector<int>();
    if (!cw.isEmpty()) {
        int rh = 0;
        for (int i = 0; i < n; ++i)
            rh = std::max(rh, item_h(vis[i], cw[i]));
        if (!test_only) {
            int x = r.x();
            for (int i = 0; i < n; ++i) {
                vis[i]->setGeometry(QRect(x, r.y(), cw[i], rh));
                x += cw[i] + gap_;
            }
        }
        return rh + m.top() + m.bottom();
    }
    int y = r.y();
    for (int i = 0; i < n; ++i) {
        const int h = item_h(vis[i], r.width());
        if (!test_only)
            vis[i]->setGeometry(QRect(r.x(), y, r.width(), h));
        y += h + (i + 1 < n ? gap_ : 0);
    }
    return y - r.y() + m.top() + m.bottom();
}

// ── lk_measure ────────────────────────────────────────────────────────────────

QWidget* lk_measure(QWidget* child, int max_w, QWidget* parent) {
    auto* box = new QWidget(parent);
    box->setObjectName(QStringLiteral("lkMeasure"));
    auto* col = new LkColumnLayout(box, max_w, Qt::AlignLeft);
    if (child) {
        child->setParent(box);
        col->addWidget(child);
    }
    return box;
}

} // namespace fincept::screens::langkinh::lkview
