// src/screens/langkinh/LkKpiStrip.cpp
// Lăng Kính FFT — block "kpis" (dải ô số nối liền, LK_HOSO_SPEC §6). Xem LkKpiStrip.h.
#include "screens/langkinh/LkKpiStrip.h"

#include "screens/langkinh/LkChips.h"
#include "screens/langkinh/LkTheme.h"
#include "screens/langkinh/LkWidgets.h"

#include <QEvent>
#include <QFontMetricsF>
#include <QHelpEvent>
#include <QJsonArray>
#include <QJsonValue>
#include <QPainter>
#include <QPainterPath>
#include <QResizeEvent>
#include <QSizePolicy>
#include <QStringList>
#include <QToolTip>
#include <QVBoxLayout>

#include <algorithm>
#include <cmath>
#include <utility>

namespace fincept::screens::langkinh {

// Helper tự do: namespace có tên riêng (quy ước của module, không dùng namespace ẩn danh).
namespace lkkpi {

using namespace lkview;

constexpr int kMinCell = 142;   // CSS minmax(142px, 1fr)
constexpr double kPadX = 12.0;  // .kpi padding 11px 12px
constexpr double kPadY = 11.0;
constexpr double kRadius = 10.0;
constexpr double kVGap = 2.0;   // k → v (.v margin-top:2px)
constexpr double kSGap = 1.0;   // v → s
constexpr double kTagGap = 6.0; // giá trị v ↔ tag bậc
constexpr int kKPx = 11;
constexpr int kVPx = 16;
constexpr int kSPx = 11;

struct Kpi {
    QString k;
    QString v;
    QString s;
    QString b;
    QString tip;
    LkRole role = LkRole::Ink;
};

QFont k_font() {
    return lk_font_sans(kKPx);
}
QFont v_font() {
    return lk_font_mono(kVPx, 600);
}
QFont s_font() {
    return lk_font_mono(kSPx);
}

double text_h(const QFont& f, const QString& t, double w) {
    if (t.isEmpty())
        return 0.0;
    const QFontMetricsF fm(f);
    const QRectF br = fm.boundingRect(QRectF(0, 0, std::max(1.0, w), 1.0e6), Qt::TextWordWrap, t);
    return std::max(fm.height(), br.height());
}

/// Vị trí các phần của một ô (dùng chung cho đo chiều cao và vẽ → hai bên luôn khớp).
struct Parts {
    QRectF tag;
    QRectF k;
    QRectF v;
    QRectF s;
    double h = 0.0; // chiều cao ô cần có
};

/// Tag bậc đặt bên phải DÒNG SỐ khi số + tag vừa một dòng (nhãn k dùng đủ bề rộng, không bị gói vì tag); không vừa
/// → bên phải nhãn k như cũ (số không bao giờ bị gói dòng vì tag).
Parts layout_cell(const Kpi& it, const QRectF& cell) {
    Parts pt;
    const double x = cell.left() + kPadX;
    const double w = std::max(8.0, cell.width() - 2.0 * kPadX);
    double y = cell.top() + kPadY;
    QSizeF ts;
    bool on_v = false;
    if (!it.b.isEmpty()) {
        ts = lk_tag_size(it.b);
        ts.setWidth(std::min(ts.width(), w * 0.55));
        on_v = QFontMetricsF(v_font()).horizontalAdvance(it.v) + ts.width() + kTagGap <= w;
    }
    const double kw = !it.b.isEmpty() && !on_v ? std::max(8.0, w - ts.width() - kTagGap) : w;
    const double kh = text_h(k_font(), it.k, kw);
    pt.k = QRectF(x, y, kw, kh);
    if (!it.b.isEmpty() && !on_v)
        pt.tag = QRectF(x + w - ts.width(), y, ts.width(), ts.height());
    y += std::max(kh, !it.b.isEmpty() && !on_v ? ts.height() : 0.0) + kVGap;
    const double vw = on_v ? std::max(8.0, w - ts.width() - kTagGap) : w;
    const double vh = text_h(v_font(), it.v, vw);
    pt.v = QRectF(x, y, vw, vh);
    if (on_v) {
        const double line = QFontMetricsF(v_font()).height();
        pt.tag = QRectF(x + w - ts.width(), y + std::max(0.0, (line - ts.height()) / 2.0), ts.width(), ts.height());
    }
    y += vh;
    if (!it.s.isEmpty()) {
        y += kSGap;
        const double sh = text_h(s_font(), it.s, w);
        pt.s = QRectF(x, y, w, sh);
        y += sh;
    }
    pt.h = y + kPadY - cell.top();
    return pt;
}

QString tip_for(const Kpi& it) {
    QStringList out;
    if (!it.k.isEmpty())
        out << QStringLiteral("<b>") + it.k.toHtmlEscaped() + QStringLiteral("</b>");
    QString line = it.v.toHtmlEscaped();
    if (!it.s.isEmpty())
        line += QStringLiteral(" · ") + it.s.toHtmlEscaped();
    out << line;
    if (!it.b.isEmpty())
        out << lk_tier_desc(it.b).toHtmlEscaped();
    if (!it.tip.isEmpty())
        out << it.tip.toHtmlEscaped().replace(QLatin1Char('\n'), QStringLiteral("<br>"));
    return QStringLiteral("<qt>") + out.join(QStringLiteral("<br>")) + QStringLiteral("</qt>");
}

// ── Dải ô: nền = màu line, ô = surface cách nhau 1px → hairline như CSS gap:1px trên nền --line ──────

class KpiStrip : public QWidget {
  public:
    KpiStrip(QList<Kpi> items, QWidget* parent) : QWidget(parent), items_(std::move(items)) {
        QSizePolicy sp(QSizePolicy::Expanding, QSizePolicy::Preferred);
        sp.setHeightForWidth(true);
        setSizePolicy(sp);
        lk_transparent(this); // góc ngoài khung bo để lộ nền trang, không phải ô BG_BASE của QSS toàn cục
    }

    bool hasHeightForWidth() const override { return true; }
    int heightForWidth(int w) const override {
        int h = 0;
        cells(w, &h);
        return h;
    }
    QSize sizeHint() const override {
        const int n = static_cast<int>(items_.size());
        const int w = std::clamp(n, 1, 6) * (kMinCell + 1) + 1;
        return {w, heightForWidth(w)};
    }
    QSize minimumSizeHint() const override { // cao một hàng; heightForWidth lo khi xuống hàng
        const int wide = static_cast<int>(items_.size()) * (kMinCell + 1) + 1;
        return {std::min(kMinCell, wide), heightForWidth(wide)};
    }

  protected:
    void paintEvent(QPaintEvent*) override {
        int total = 0;
        const QList<Cell> cs = cells(width(), &total);
        if (cs.isEmpty())
            return;
        QPainter p(this);
        p.setRenderHint(QPainter::Antialiasing, true);
        p.setRenderHint(QPainter::TextAntialiasing, true);
        const QRectF outer(0.0, 0.0, width(), total);
        const QColor surface = lk_col(LkRole::Surface);
        QPainterPath outer_path;
        outer_path.addRoundedRect(outer, kRadius, kRadius);
        p.fillPath(outer_path, lk_col(LkRole::Line));
        QPainterPath inner;
        inner.addRoundedRect(outer.adjusted(1.0, 1.0, -1.0, -1.0), kRadius - 1.0, kRadius - 1.0);
        // Ô đặt ở toạ độ nguyên → cạnh ô (và vạch 1px giữa các ô) sắc ở mọi DPR nguyên; góc bo theo khung trong.
        const auto fill = [&](const QRectF& r) {
            QPainterPath cp;
            cp.addRect(r);
            p.fillPath(cp.intersected(inner), surface);
        };
        for (const Cell& c : cs)
            fill(QRectF(c.r));
        const QRect& last = cs.last().r; // phần trống cuối hàng chót: một khoảng surface liền
        const int bx = last.x() + last.width() + 1;
        if (bx < width() - 1)
            fill(QRectF(bx, last.y(), width() - 1 - bx, last.height()));
        for (const Cell& c : cs)
            paint_cell(p, c);
    }

    void resizeEvent(QResizeEvent* e) override {
        QWidget::resizeEvent(e);
        if (heightForWidth(width()) != height())
            updateGeometry();
        update();
    }

    bool event(QEvent* e) override {
        if (e->type() != QEvent::ToolTip)
            return QWidget::event(e);
        const auto* he = static_cast<QHelpEvent*>(e);
        int total = 0;
        for (const Cell& c : cells(width(), &total))
            if (c.r.contains(he->pos())) {
                QToolTip::showText(he->globalPos(), tip_for(items_.at(c.idx)), this, c.r);
                return true;
            }
        QToolTip::hideText();
        e->ignore();
        return true;
    }

  private:
    struct Cell {
        QRect r;
        int idx;
    };

    /// Số cột vừa bề rộng w: c·142 + (c−1) vạch + 2 viền ≤ w; không quá số ô. Không để một ô mồ côi ở hàng cuối:
    /// còn chia không hết và c > nửa số ô thì bớt cột (6 ô → 6, rồi 3, rồi 2 cột — như các nấc .tiles của Artifact).
    int cols_for(int w) const {
        const int n = static_cast<int>(items_.size());
        int c = std::clamp((w - 1) / (kMinCell + 1), 1, std::max(1, n));
        while (c > 1 && n % c != 0 && c > (n + 1) / 2)
            --c;
        return c;
    }

    QList<Cell> cells(int w, int* total_h) const {
        QList<Cell> out;
        *total_h = 0;
        const int n = static_cast<int>(items_.size());
        if (n == 0 || w <= 2)
            return out;
        const int cols = cols_for(w);
        const int avail = std::max(cols, w - 2 - (cols - 1));
        const auto col_w = [avail, cols](int j) { return avail / cols + (j < avail % cols ? 1 : 0); };
        int y = 1;
        for (int first = 0; first < n; first += cols) {
            const int last = std::min(n, first + cols);
            int rh = 0;
            for (int i = first; i < last; ++i) {
                const double h = layout_cell(items_.at(i), QRectF(0.0, 0.0, col_w(i - first), 0.0)).h;
                rh = std::max(rh, static_cast<int>(std::ceil(h)));
            }
            int x = 1;
            for (int i = first; i < last; ++i) {
                const int cw = col_w(i - first);
                out.append(Cell{QRect(x, y, cw, rh), i});
                x += cw + 1;
            }
            y += rh + 1; // vạch giữa hàng; sau hàng chót chính là viền dưới
        }
        *total_h = y;
        return out;
    }

    void paint_cell(QPainter& p, const Cell& c) const {
        const Kpi& it = items_.at(c.idx);
        const Parts pt = layout_cell(it, QRectF(c.r));
        p.save();
        p.setClipRect(c.r);
        if (!it.b.isEmpty())
            lk_paint_tag(p, pt.tag, it.b);
        constexpr int flags = Qt::TextWordWrap | Qt::AlignLeft | Qt::AlignTop;
        if (!it.k.isEmpty()) {
            p.setFont(k_font());
            p.setPen(lk_col(LkRole::Muted));
            p.drawText(pt.k, flags, it.k);
        }
        p.setFont(v_font());
        p.setPen(lk_col(it.role));
        p.drawText(pt.v, flags, it.v);
        if (!it.s.isEmpty()) {
            p.setFont(s_font());
            p.setPen(lk_col(LkRole::Ink2));
            p.drawText(pt.s, flags, it.s);
        }
        p.restore();
    }

    QList<Kpi> items_;
};

} // namespace lkkpi

namespace lkview {

QWidget* make_kpis(const QJsonObject& b, QWidget* parent) {
    const QString phrase = lk_tr("không dùng cho quyết định");
    QList<lkkpi::Kpi> items;
    for (const auto& iv : b.value(QStringLiteral("items")).toArray()) {
        if (!iv.isObject())
            continue;
        const QJsonObject o = iv.toObject();
        lkkpi::Kpi k;
        k.k = text_opt(o.value(QStringLiteral("k")));
        const QJsonValue v = o.value(QStringLiteral("v"));
        k.v = text_of(v); // thiếu/sai kiểu → "—"
        k.s = text_opt(o.value(QStringLiteral("s")));
        k.b = text_opt(o.value(QStringLiteral("b")));
        k.tip = text_opt(o.value(QStringLiteral("tip")));
        k.role = lk_role(o.value(QStringLiteral("mau")).toString(), LkRole::Ink);
        if (k.k.isEmpty() && k.v == dash() && k.s.isEmpty())
            continue;
        if (v.isNull() && k.b.isEmpty()) // null tường minh = thiếu nguồn (§0.1), không phải số 0
            k.b = QStringLiteral("CẦN DATA");
        if (lk_tier_unverified(k.b) && !k.s.contains(phrase, Qt::CaseInsensitive))
            k.s = k.s.isEmpty() ? phrase : k.s + QStringLiteral(" · ") + phrase;
        items << k;
    }
    if (items.isEmpty())
        return nullptr;

    const QString title = b.value(QStringLiteral("title")).toString().trimmed();
    const QString sub = b.value(QStringLiteral("sub")).toString().trimmed();
    if (title.isEmpty() && sub.isEmpty())
        return new lkkpi::KpiStrip(std::move(items), parent);
    auto* w = new QWidget(parent);
    lk_transparent(w);
    auto* vl = new QVBoxLayout(w);
    vl->setContentsMargins(0, 0, 0, 0);
    vl->setSpacing(8);
    lk_add_head(vl, b, w);
    vl->addWidget(new lkkpi::KpiStrip(std::move(items), w));
    return w;
}

} // namespace lkview

} // namespace fincept::screens::langkinh
