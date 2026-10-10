// WdcLegend.cpp: legend layout, swatches, legend widget and popover of the WiData clone (package D).
// Numbers: UI §3.4 (aio), §3.5 (macro), §4.5 (expanded), capture vimo (chart page), DESIGN §6.1 and §8.4.
#include "screens/widata/WdcLegend.h"

#include "screens/widata/WdcIcons_p.h"
#include "screens/widata/WdcTheme_p.h"

#include <QDateTime>
#include <QGuiApplication>
#include <QKeyEvent>
#include <QMouseEvent>
#include <QPainter>
#include <QScreen>
#include <QTimeZone>
#include <QTimer>
#include <QWheelEvent>

#include <algorithm>
#include <cmath>
#include <numeric>

namespace fincept::screens::wdc {

namespace th = theme;

namespace {

constexpr int kInfoDelayMs = 120; // hover on the info icon before the popover opens (MẶC ĐỊNH)

int wdcl_cols(LegendStyle s) {
    switch (s) {
    case LegendStyle::Expanded: return 4;
    case LegendStyle::Single: return 3;
    default: return 2;
    }
}

/// Swatch parts relative to (sx, sy) = (item.x - 1.5, row.y), DOM order (UI §3.4 table, FACT DOM).
std::vector<QRectF> wdcl_parts(SwatchKind k, qreal sx, qreal sy) {
    switch (k) {
    case SwatchKind::Line: return {QRectF(sx, sy + th::kLineY, th::kSwatchW, th::kLineH)};
    case SwatchKind::Dash: {
        const qreal y = sy + th::kLineY, x2 = sx + th::kDashShort + th::kDashGap, x3 = x2 + th::kDashLong + th::kDashGap;
        return {QRectF(sx, y, th::kSwatchW, th::kLineH), QRectF(sx, y, th::kDashShort, th::kLineH),
                QRectF(x2, y, th::kDashLong, th::kLineH), QRectF(x3, y, th::kDashShort, th::kLineH)};
    }
    case SwatchKind::LineMarker:
        return {QRectF(sx, sy + th::kLineY, th::kSwatchW, th::kLineH),
                QRectF(sx + th::kDotDx, sy + th::kLineY + th::kDotDy, th::kDotSize, th::kDotSize)};
    case SwatchKind::Column:
    case SwatchKind::Column2: return {QRectF(sx, sy + th::kBoxY, th::kSwatchW, th::kBoxH)};
    case SwatchKind::Area:
    case SwatchKind::Area2:
        return {QRectF(sx, sy + th::kBoxY, th::kSwatchW, th::kBoxH), QRectF(sx, sy + th::kBoxY, th::kSwatchW, th::kAreaBarH),
                QRectF(sx + th::kAreaBlockInset, sy + th::kBoxY + th::kAreaBarH, th::kAreaBlockW, th::kAreaBlockH)};
    }
    return {};
}

/// CSS border-radius on a small box: every radius scaled by the same factor, i.e. min(r, w/2, h/2).
QPainterPath wdcl_round(const QRectF& r, qreal radius) {
    QPainterPath p;
    const qreal rr = std::min({radius, r.width() / 2, r.height() / 2});
    if (rr > 0) p.addRoundedRect(r, rr, rr);
    else p.addRect(r);
    return p;
}

/// Lower block of the area swatch: radius "0 0 1px 1px".
QPainterPath wdcl_block(const QRectF& r) {
    QPainterPath p;
    const qreal k = 1.0;
    p.moveTo(r.topLeft());
    p.lineTo(r.topRight());
    p.lineTo(r.right(), r.bottom() - k);
    p.quadTo(r.bottomRight(), QPointF(r.right() - k, r.bottom()));
    p.lineTo(r.left() + k, r.bottom());
    p.quadTo(r.bottomLeft(), QPointF(r.left(), r.bottom() - k));
    p.closeSubpath();
    return p;
}

/// Two colours split in the middle with a 1 px light gap (DESIGN §6.1, measured on ref/user/5.webp).
void wdcl_fill2(QPainter& p, const QPainterPath& shape, const QRectF& box, const QColor& pos, const QColor& neg) {
    const qreal mid = box.x() + box.width() / 2;
    p.save();
    p.setClipPath(shape);
    p.fillRect(QRectF(box.x(), box.y(), mid - 0.5 - box.x(), box.height()), pos);
    p.fillRect(QRectF(mid + 0.5, box.y(), box.right() - mid - 0.5, box.height()), neg);
    p.restore();
}

QString wdcl_date(qint64 t) {
    return QDateTime::fromMSecsSinceEpoch(t, QTimeZone::UTC).toString(QStringLiteral("dd/MM/yyyy"));
}

} // namespace

// ---- pure layout -------------------------------------------------------------------------------------------

SwatchKind swatchKindFor(const SeriesRef& ref) {
    const bool two = ref.negativeColor.has_value();
    switch (ref.type) {
    case SeriesType::Column: return two ? SwatchKind::Column2 : SwatchKind::Column;
    case SeriesType::AreaSpline: return two ? SwatchKind::Area2 : SwatchKind::Area;
    case SeriesType::Spline: break;
    }
    if (ref.dashStyle.compare(QLatin1String("Dash"), Qt::CaseInsensitive) == 0) return SwatchKind::Dash;
    return ref.marker ? SwatchKind::LineMarker : SwatchKind::Line;
}

QString swatchKindName(SwatchKind k) {
    switch (k) {
    case SwatchKind::Line: return QStringLiteral("line");
    case SwatchKind::Dash: return QStringLiteral("dash");
    case SwatchKind::LineMarker: return QStringLiteral("line_marker");
    case SwatchKind::Column: return QStringLiteral("column");
    case SwatchKind::Area: return QStringLiteral("area");
    case SwatchKind::Column2: return QStringLiteral("column2");
    case SwatchKind::Area2: return QStringLiteral("area2");
    }
    return QString();
}

std::vector<int> legendOrder(const std::vector<SeriesRef>& refs, bool zIndexDesc) {
    std::vector<int> idx(refs.size());
    std::iota(idx.begin(), idx.end(), 0);
    if (zIndexDesc)
        std::stable_sort(idx.begin(), idx.end(), [&](int a, int b) { return refs[size_t(a)].zIndex > refs[size_t(b)].zIndex; });
    return idx;
}

LegendGeom layoutLegend(LegendStyle style, const QRectF& c, const std::vector<LegendText>& items, qreal dpr) {
    LegendGeom g;
    g.container = c;
    const int n = int(items.size()), cols = wdcl_cols(style);
    const int rows = (n + cols - 1) / cols;
    const bool oneRow = rows <= 1;
    g.scrollbarW = rows > 2 ? th::scrollbarWidth(dpr) : 0;
    const qreal sb = g.scrollbarW;
    qreal itemW = 0, x0 = 0, stepX = 0;
    if (style == LegendStyle::Aio || style == LegendStyle::Expanded) {
        const qreal pad = style == LegendStyle::Aio ? th::kLegendPadAio : th::kLegendPadExpanded;
        itemW = (c.width() - 2 * pad - sb) / cols;
        x0 = c.x() + sb + pad;
        stepX = itemW;
    } else { // LegendCustom: item = W/cols - 3 % W, margin 1.5 % W on both sides
        const qreal W = (style == LegendStyle::Single ? c.width() + th::kSingleExtraW : c.width()) - sb;
        const qreal m = th::kMacroMarginFrac * W;
        itemW = W / cols - 2 * m;
        x0 = c.x() + sb + m;
        stepX = itemW + 2 * m;
    }
    g.contentH = std::max<qreal>(th::kLegendH, rows * th::kLegendRowH);
    g.track = QRectF(c.x(), c.y(), sb, th::kLegendH);
    const qreal resetPad = style == LegendStyle::Expanded ? th::kResetPadExpanded : th::kResetPad;
    const qreal resetSize = th::kResetIcon + 2 * resetPad;
    if (style == LegendStyle::Aio) {          // .reset-legend-arrow {margin-top: -8px; right: -4px}
        g.reset = QRectF(c.right() + th::kResetRight - resetSize, c.y() + th::kResetDy, resetSize, resetSize);
    } else if (style == LegendStyle::Macro) { // .reset-legend-scroll {right: -4px; bottom: 18px}
        g.reset = QRectF(c.right() + th::kResetRight - resetSize, c.bottom() - th::kResetScrollBottom - resetSize, resetSize,
                         resetSize);
    } else {                                  // expanded (reset-legend-zoom) and chart page: MẶC ĐỊNH of package D
        const qreal resetInset = style == LegendStyle::Expanded ? th::kLegendPadExpanded : 0;
        g.reset = QRectF(c.right() - resetInset - resetSize, c.y() + th::kResetDy, resetSize, resetSize);
    }

    const QFontMetricsF fm(th::exactFont(th::kLegendPx, 400));   // Blink widths and "…" cut (VERIFY_W3 V3)
    g.items.reserve(size_t(n));
    for (int i = 0; i < n; ++i) {
        const int col = i % cols, row = i / cols;
        const qreal x = x0 + col * stepX;
        qreal itemY = c.y() + row * th::kLegendRowH, itemH = th::kLegendRowH, rowTop = itemY;
        if (oneRow) {
            switch (style) {
            case LegendStyle::Macro: itemY = rowTop = c.y() + th::kLegendH - th::kLegendRowH; break; // align-items end
            case LegendStyle::Expanded:
                itemY = c.y();
                itemH = th::kLegendH;
                rowTop = c.y() + (th::kLegendH - th::kLegendRowH) / 2;
                break;
            default: itemY = rowTop = c.y() + (th::kLegendH - th::kLegendRowH) / 2; break;
            }
        }
        LegendItemGeom it;
        it.item = QRectF(x, itemY, itemW, itemH);
        it.row = QRectF(x, rowTop, itemW, th::kLegendRowH);
        it.swatchParts = wdcl_parts(items[size_t(i)].kind, x - th::kSwatchOverhang, rowTop);
        it.textBlock = QRectF(x + th::kTextBlockInset, rowTop, itemW - th::kTextBlockReserve, th::kLegendRowH);
        const qreal maxW = std::max<qreal>(0, itemW - th::kTextReserve);
        const QString& s = items[size_t(i)].text;
        it.shown = th::exactElide(fm, s, th::kLegendPx, maxW, &it.elided, 400);
        it.fullW = th::exactTextWidth(fm, s, th::kLegendPx, 400);
        const qreal tw = std::min(it.fullW, maxW);
        it.text = QRectF(it.textBlock.x(), rowTop, tw, th::kLegendRowH);
        it.infoBox = QRectF(it.text.right(), rowTop + th::kInfoDy, th::kInfoBoxW, th::kInfoBoxH);
        it.infoIcon = QRectF(it.text.right(), rowTop + th::kInfoDy, th::kInfoIcon, th::kInfoIcon);
        const qreal span = std::min(it.fullW + th::kLegendHoverPadR, maxW);   // border-box span while hovered
        it.textHover = QRectF(it.text.x(), rowTop, span, th::kLegendRowH);
        it.infoBoxHover = QRectF(it.text.x() + span, rowTop + th::kInfoDy, th::kInfoBoxW, th::kInfoBoxH);
        it.infoIconHover = QRectF(it.text.x() + span, rowTop + th::kInfoDy, th::kInfoIcon, th::kInfoIcon);
        g.items.push_back(std::move(it));
    }
    return g;
}

void paintSwatch(QPainter& p, SwatchKind kind, const std::vector<QRectF>& parts, const QColor& c, const QColor& neg) {
    if (parts.empty()) return;
    p.save();
    p.setRenderHint(QPainter::Antialiasing, true);
    p.setPen(Qt::NoPen);
    switch (kind) {
    case SwatchKind::Line: p.fillPath(wdcl_round(parts[0], th::kSwatchRadius), c); break;
    case SwatchKind::Dash:
        for (size_t i = 1; i < parts.size(); ++i) p.fillPath(wdcl_round(parts[i], th::kSwatchRadius), c);
        break;
    case SwatchKind::LineMarker:
        p.fillPath(wdcl_round(parts[0], th::kSwatchRadius), c);
        if (parts.size() > 1) {
            QPainterPath dot;
            dot.addEllipse(parts[1]);
            p.fillPath(dot, c);
        }
        break;
    case SwatchKind::Column: p.fillPath(wdcl_round(parts[0], th::kSwatchRadius), c); break;
    case SwatchKind::Column2: wdcl_fill2(p, wdcl_round(parts[0], th::kSwatchRadius), parts[0], c, neg); break;
    case SwatchKind::Area:
        if (parts.size() < 3) break;
        p.fillPath(wdcl_round(parts[1], th::kSwatchRadius), c);
        p.setOpacity(p.opacity() * th::kAreaLowerOpacity);
        p.fillPath(wdcl_block(parts[2]), c);
        break;
    case SwatchKind::Area2:
        if (parts.size() < 3) break;
        wdcl_fill2(p, wdcl_round(parts[1], th::kSwatchRadius), parts[1], c, neg);
        p.setOpacity(p.opacity() * th::kAreaLowerOpacity);
        wdcl_fill2(p, wdcl_block(parts[2]), parts[0], c, neg);
        break;
    }
    p.restore();
}

// ---- popover -------------------------------------------------------------------------------------------------

WdcPopover::WdcPopover(QWidget* owner, Mode mode)
    : QWidget(owner, (mode == Mode::Tip || mode == Mode::TitleTip ? Qt::ToolTip : Qt::Popup) |
                         Qt::FramelessWindowHint | Qt::NoDropShadowWindowHint),
      mode_(mode) {
    const bool tip = mode == Mode::Tip || mode == Mode::TitleTip;
    setAttribute(Qt::WA_TranslucentBackground, true);
    setAttribute(Qt::WA_ShowWithoutActivating, tip);
    setAttribute(Qt::WA_TransparentForMouseEvents, tip);
    setMouseTracking(true);
    margin_ = mode == Mode::TitleTip ? 0 : shadowExtent(shadowCircleBtn());
}

void WdcPopover::setLines(const QStringList& lines) {
    lines_ = lines;
    items_.clear();
    relayout();
}

void WdcPopover::setItems(const std::vector<Item>& items) {
    items_ = items;
    lines_.clear();
    hover_ = -1;
    relayout();
}

QSizeF WdcPopover::frameSize() const { return frame_; }

QStringList WdcPopover::itemIds() const {
    QStringList ids;
    for (const Item& it : items_) ids << it.id;
    return ids;
}

void WdcPopover::trigger(const QString& id) {
    for (const Item& it : items_)
        if (it.id == id && it.enabled) {
            hide();
            emit triggered(id);
            return;
        }
}

void WdcPopover::relayout() {
    if (mode_ == Mode::TitleTip) {
        const QFontMetricsF tfm(th::font(th::kTitleTipPx, 400));
        const qreal dpr = devicePixelRatioF();
        const QString s = lines_.value(0);
        frame_ = QSizeF(th::textWidth(tfm, s, 400) + 2 * th::kTitleTipPad,
                        th::blinkNormalLineH(th::kTitleTipPx, dpr) + 2 * th::kTitleTipPad);
        resize(int(std::ceil(frame_.width())), int(std::ceil(frame_.height())));
        update();
        return;
    }
    const QFontMetricsF fm(th::font(th::kPopoverPx, 400));
    qreal w = 0, h = 0;
    if (mode_ == Mode::Menu) {
        for (const Item& it : items_) w = std::max(w, th::textWidth(fm, it.text, 400));
        w += 2 * th::kMenuRowPadX;
        h = qreal(items_.size()) * th::kMenuRowH;
    } else {
        for (const QString& l : lines_) {
            const QRectF br = fm.boundingRect(QRectF(0, 0, th::kPopoverMaxTextW, 1e5), Qt::TextWordWrap, l);
            w = std::max(w, std::ceil(br.width()));
            h += std::max<qreal>(th::kPopoverLineH, std::ceil(br.height()));
        }
    }
    frame_ = QSizeF(std::ceil(w + 2 * th::kPopoverPad), std::ceil(h + 2 * th::kPopoverPad));
    resize(int(std::ceil(frame_.width() + 2 * margin_)), int(std::ceil(frame_.height() + 2 * margin_)));
    update();
}

void WdcPopover::showAt(const QPoint& globalTopLeft) {
    QPoint tl = globalTopLeft - QPoint(int(margin_), int(margin_));
    if (QScreen* s = QGuiApplication::screenAt(globalTopLeft)) {
        const QRect a = s->availableGeometry();
        tl.setX(std::clamp(tl.x(), a.left(), std::max(a.left(), a.right() - width())));
        tl.setY(std::clamp(tl.y(), a.top(), std::max(a.top(), a.bottom() - height())));
    }
    move(tl);
    show();
    raise();
}

int WdcPopover::itemAt(const QPointF& pos) const {
    if (mode_ != Mode::Menu) return -1;
    const qreal y = pos.y() - margin_ - th::kPopoverPad, x = pos.x() - margin_;
    if (x < 0 || x > frame_.width() || y < 0) return -1;
    const int i = int(y / th::kMenuRowH);
    return i < int(items_.size()) ? i : -1;
}

void WdcPopover::paintEvent(QPaintEvent*) {
    QPainter p(this);
    p.setRenderHint(QPainter::Antialiasing, true);
    p.setRenderHint(QPainter::TextAntialiasing, true);
    const qreal dpr = devicePixelRatioF();
    const QRectF fr(margin_, margin_, frame_.width(), frame_.height());
    if (mode_ == Mode::TitleTip) {
        p.fillPath(wdcl_round(fr, th::kTitleTipRadius), th::color(th::kTitleTipBg));
        p.setFont(th::font(th::kTitleTipPx, 400));
        p.setPen(th::color(th::kTitleTipFg));
        th::drawWebText(p, QPointF(fr.x() + th::kTitleTipPad, fr.y() + th::kTitleTipPad + th::blinkAscent(th::kTitleTipPx, dpr)),
                        lines_.value(0), 400);
        return;
    }
    paintPopoverFrame(p, fr, dpr);
    p.setFont(th::font(th::kPopoverPx, 400));
    p.setPen(th::color(th::kPopoverText));
    if (mode_ == Mode::Menu) {
        for (int i = 0; i < int(items_.size()); ++i) {
            const QRectF row(fr.x() + th::kPopoverPad, fr.y() + th::kPopoverPad + i * th::kMenuRowH,
                             fr.width() - 2 * th::kPopoverPad, th::kMenuRowH);
            if (i == hover_ && items_[size_t(i)].enabled) p.fillPath(wdcl_round(row, 4), th::color(th::kHoverBg));
            p.setOpacity(items_[size_t(i)].enabled ? 1.0 : 0.5);
            th::drawWebText(p, QPointF(row.x() + th::kMenuRowPadX, row.y() + th::blinkBaseline(th::kPopoverPx, th::kMenuRowH, dpr)),
                            items_[size_t(i)].text, 400);
            p.setOpacity(1.0);
        }
        return;
    }
    const QFontMetricsF fm(p.font());
    qreal y = fr.y() + th::kPopoverPad;
    for (const QString& l : lines_) {
        const QRectF br = fm.boundingRect(QRectF(0, 0, th::kPopoverMaxTextW, 1e5), Qt::TextWordWrap, l);
        const qreal h = std::max<qreal>(th::kPopoverLineH, std::ceil(br.height()));
        p.drawText(QRectF(fr.x() + th::kPopoverPad, y, th::kPopoverMaxTextW, h), Qt::TextWordWrap | Qt::AlignLeft | Qt::AlignVCenter, l);
        y += h;
    }
}

void WdcPopover::mouseMoveEvent(QMouseEvent* e) {
    const int h = itemAt(e->position());
    if (h != hover_) { hover_ = h; update(); }
}

void WdcPopover::mouseReleaseEvent(QMouseEvent* e) {
    const int i = itemAt(e->position());
    if (i >= 0) trigger(items_[size_t(i)].id);
    else if (!rect().contains(e->position().toPoint())) hide();
}

void WdcPopover::leaveEvent(QEvent*) {
    hover_ = -1;
    update();
}

void WdcPopover::keyPressEvent(QKeyEvent* e) {
    const int n = int(items_.size());
    switch (e->key()) {
    case Qt::Key_Escape: hide(); return;
    case Qt::Key_Down: if (n) { hover_ = (hover_ + 1) % n; update(); } return;
    case Qt::Key_Up: if (n) { hover_ = (hover_ <= 0 ? n : hover_) - 1; update(); } return;
    case Qt::Key_Return: case Qt::Key_Enter: case Qt::Key_Space:
        if (hover_ >= 0 && hover_ < n) trigger(items_[size_t(hover_)].id);
        return;
    default: QWidget::keyPressEvent(e);
    }
}

// ---- legend widget -----------------------------------------------------------------------------------------

WdcLegend::WdcLegend(QWidget* parent) : QWidget(parent) {
    setMouseTracking(true);
    setAttribute(Qt::WA_StyledBackground, false);
    infoTimer_ = new QTimer(this);
    infoTimer_->setSingleShot(true);
    infoTimer_->setInterval(kInfoDelayMs);
    connect(infoTimer_, &QTimer::timeout, this, [this] { if (infoPending_ >= 0) showInfo(infoPending_); });
}

WdcLegend::~WdcLegend() = default;

void WdcLegend::setLegendStyle(LegendStyle style) {
    style_ = style;
    relayout();
}

void WdcLegend::setEntries(std::vector<LegendEntry> entries, std::shared_ptr<const DashData> keepAlive) {
    hideInfo();
    entries_ = std::move(entries);
    keep_ = std::move(keepAlive);
    hover_ = -1;
    relayout();
}

void WdcLegend::setVisibility(const std::vector<bool>& visibleByRefIndex) {
    visible_ = visibleByRefIndex;
    repaintCached();
}

void WdcLegend::setContainerRect(const QRectF& rectInParent) {
    container_ = rectInParent;
    setGeometry(rectInParent.adjusted(-kOverhang, -kOverhang, kOverhang, kOverhang).toAlignedRect());
    relayout();
}

void WdcLegend::relayout() {
    geomDirty_ = true;   // a card sets style, entries, visibility and rect in a row: lay out once, on first use
    repaintCached();
}

const LegendGeom& WdcLegend::g() const {
    if (geomDirty_) {
        geomDirty_ = false;
        std::vector<LegendText> texts;
        texts.reserve(entries_.size());
        for (const LegendEntry& e : entries_)
            texts.push_back({e.ref ? th::displayName(e.ref->nameRaw) : QString(), e.ref ? swatchKindFor(*e.ref) : SwatchKind::Line});
        const QPointF origin = container_.topLeft() - QPointF(geometry().topLeft());
        geom_ = layoutLegend(style_, QRectF(origin, container_.size()), texts, devicePixelRatioF());
        scrollY_ = std::clamp<qreal>(scrollY_, 0, std::max<qreal>(0, geom_.contentH - th::kLegendH));
    }
    return geom_;
}

LegendGeom WdcLegend::geometryModel() const {
    std::vector<LegendText> texts;
    for (const LegendEntry& e : entries_)
        texts.push_back({e.ref ? th::displayName(e.ref->nameRaw) : QString(), e.ref ? swatchKindFor(*e.ref) : SwatchKind::Line});
    return layoutLegend(style_, container_, texts, devicePixelRatioF());
}

QRectF WdcLegend::itemRectInWidget(int i) const {
    return i >= 0 && i < int(g().items.size()) ? g().items[size_t(i)].item.translated(0, -scrollY_) : QRectF();
}
QRectF WdcLegend::infoRectInWidget(int i) const {   // the icon where it is while its item is hovered
    return i >= 0 && i < int(g().items.size()) ? g().items[size_t(i)].infoBoxHover.translated(0, -scrollY_) : QRectF();
}
QRectF WdcLegend::resetRectInWidget() const { return g().reset; }

bool WdcLegend::isVisibleEntry(int i) const {
    const int r = entries_[size_t(i)].refIndex;
    return r < 0 || r >= int(visible_.size()) || visible_[size_t(r)];
}

bool WdcLegend::isMissing(int i) const {
    const SeriesEntry* e = entries_[size_t(i)].entry;
    return !e || e->data.status == Status::Missing;
}

bool WdcLegend::resetVisible() const {
    for (int i = 0; i < count(); ++i)
        if (!isVisibleEntry(i)) return true;
    return false;
}

// DESIGN §16 C19: the icon shows only while its item is hovered, whatever the status (as on WiData); partial, EST and
// UNVERIFIED are told by the popover of the icon and by the " · EST" suffix of the tooltip.
bool WdcLegend::infoVisible(int i) const { return i >= 0 && i < count() && i == hover_; }

bool WdcLegend::popoverVisible() const { return pop_ && pop_->isVisible(); }

int WdcLegend::hitItem(const QPointF& pos) const {
    const QRectF clip = g().container.adjusted(g().scrollbarW, 0, 0, 0);
    if (!clip.contains(pos)) return -1;
    const QPointF q = pos + QPointF(0, scrollY_);
    for (int i = 0; i < int(g().items.size()); ++i)
        if (g().items[size_t(i)].item.contains(q)) return i;
    return -1;
}

void WdcLegend::repaintCached() {
    cacheDirty_ = true;
    update();
}

void WdcLegend::paintEvent(QPaintEvent*) {
    // The legend is redrawn whenever its card repaints (hover of a button, a chart image arriving): keep the
    // drawing in an image and redraw it only when the legend itself changes (DESIGN §16 C18).
    const qreal dpr = devicePixelRatioF();
    const QSize dev = (QSizeF(size()) * dpr).toSize();
    if (cacheDirty_ || cache_.size() != dev || !qFuzzyCompare(cache_.devicePixelRatio(), dpr)) {
        cache_ = QImage(dev, QImage::Format_ARGB32_Premultiplied);
        cache_.setDevicePixelRatio(dpr);
        cache_.fill(Qt::transparent);
        QPainter q(&cache_);
        paintContent(q, dpr);
        cacheDirty_ = false;
    }
    QPainter p(this);
    p.drawImage(QPointF(0, 0), cache_);
}

void WdcLegend::paintContent(QPainter& p, qreal dpr) {
    p.setRenderHint(QPainter::Antialiasing, true);
    p.setRenderHint(QPainter::TextAntialiasing, true);
    const QFont f = th::font(th::kLegendPx, 400);
    p.setFont(f);
    p.save();
    p.setClipRect(g().container.adjusted(g().scrollbarW, 0, 0, 0));
    p.translate(0, -scrollY_);
    for (int i = 0; i < int(g().items.size()); ++i) {
        const LegendItemGeom& it = g().items[size_t(i)];
        const SeriesRef* ref = entries_[size_t(i)].ref;
        if (!ref) continue;
        const bool hov = i == hover_;   // HOVER_CSS.md: no background rule on the item, so none is drawn
        const qreal base = isVisibleEntry(i) ? 1.0 : th::kOffOpacity;
        const bool missing = isMissing(i);
        p.setOpacity(base * (missing ? th::kMissingSwatchOpacity : 1.0));
        paintSwatch(p, swatchKindFor(*ref), it.swatchParts, ref->color, ref->negativeColor.value_or(ref->color));
        p.setOpacity(base);
        p.setPen(th::color(missing ? th::kMissingText : th::kTextPrimary));
        const QPointF at(it.text.x(), it.row.y() + th::blinkBaseline(th::kLegendPx, th::kLegendRowH, dpr));
        if (hov) { // whole name, clipped at the span edge instead of "…"
            p.save();
            p.setClipRect(it.textHover, Qt::IntersectClip);
            th::drawWebText(p, at, th::displayName(ref->nameRaw), 400);
            p.restore();
        } else {
            th::drawWebText(p, at, it.shown, 400);
        }
        if (infoVisible(i)) paintIcon(p, Icon::InfoRounded, hov ? it.infoIconHover : it.infoIcon, th::color(th::kIconMuted));
        p.setOpacity(1.0);
    }
    p.restore();
    if (g().scrollable()) {
        const qreal vh = th::kLegendH, ratio = vh / std::max(vh, g().contentH);
        const QRectF thumb(g().track.x(), g().track.y() + scrollY_ * ratio, g().track.width(), vh * ratio);
        p.fillPath(wdcl_round(thumb, th::kScrollbarRadius), th::color(th::kScrollThumb));
    }
    if (resetVisible()) {
        const QRectF r = g().reset;
        paintBoxShadow(p, r, th::kResetRadius, shadowReset(), dpr);
        p.fillPath(wdcl_round(r, th::kResetRadius), th::color(th::kAccentReset));
        const qreal pad = (r.width() - th::kResetIcon) / 2;
        paintIcon(p, Icon::RestartAlt, QRectF(r.x() + pad, r.y() + pad, th::kResetIcon, th::kResetIcon), th::color(th::kWhite));
    }
}

void WdcLegend::mouseMoveEvent(QMouseEvent* e) {
    const QPointF pos = e->position();
    const bool onReset = resetVisible() && g().reset.contains(pos);
    const int h = onReset ? -1 : hitItem(pos);
    if (h != hover_ || onReset != hoverReset_) {
        hover_ = h;
        hoverReset_ = onReset;
        repaintCached();
    }
    setCursor(onReset || h >= 0 ? Qt::PointingHandCursor : Qt::ArrowCursor);
    const bool onInfo = h >= 0 && g().items[size_t(h)].infoBoxHover.contains(pos + QPointF(0, scrollY_));
    if (onInfo) {
        if (infoFor_ != h && infoPending_ != h) {
            infoPending_ = h;
            infoTimer_->start();
        }
    } else {
        hideInfo();
    }
}

void WdcLegend::mousePressEvent(QMouseEvent* e) {
    if (e->button() != Qt::LeftButton) return QWidget::mousePressEvent(e);
    pressReset_ = resetVisible() && g().reset.contains(e->position());
    pressed_ = pressReset_ ? -1 : hitItem(e->position());
    if (!pressReset_ && pressed_ < 0) e->ignore();
}

void WdcLegend::mouseReleaseEvent(QMouseEvent* e) {
    if (e->button() != Qt::LeftButton) return QWidget::mouseReleaseEvent(e);
    const QPointF pos = e->position();
    if (pressReset_ && g().reset.contains(pos)) {
        pressReset_ = false;
        std::fill(visible_.begin(), visible_.end(), true);
        repaintCached();
        emit resetRequested();
        return;
    }
    pressReset_ = false;
    const int i = hitItem(pos);
    if (i < 0 || i != pressed_) { pressed_ = -1; return; }
    pressed_ = -1;
    if (g().items[size_t(i)].infoBoxHover.contains(pos + QPointF(0, scrollY_))) {
        showInfo(i); // a click on the info icon opens the popover, it does not toggle (BEH §5.3)
        return;
    }
    const int r = entries_[size_t(i)].refIndex;
    if (r < 0) return;
    if (r >= int(visible_.size())) visible_.resize(size_t(r) + 1, true);
    visible_[size_t(r)] = !visible_[size_t(r)];
    repaintCached();
    emit toggled(r, visible_[size_t(r)]);
}

void WdcLegend::leaveEvent(QEvent*) {
    hover_ = -1;
    hoverReset_ = false;
    hideInfo();
    unsetCursor();
    repaintCached();
}

void WdcLegend::wheelEvent(QWheelEvent* e) {
    const qreal maxY = std::max<qreal>(0, g().contentH - th::kLegendH);
    if (maxY <= 0) { e->ignore(); return; } // not scrollable: let the page scroll
    const qreal dy = !e->pixelDelta().isNull() ? -e->pixelDelta().y() : -e->angleDelta().y() / 120.0 * th::kLegendRowH;
    const qreal y = std::clamp(scrollY_ + dy, 0.0, maxY);
    if (qFuzzyCompare(y + 1, scrollY_ + 1)) { e->ignore(); return; }
    scrollY_ = y;
    hideInfo();
    repaintCached();
    e->accept();
}

void WdcLegend::changeEvent(QEvent* e) {
    if (e->type() == QEvent::DevicePixelRatioChange) relayout();
    QWidget::changeEvent(e);
}

QStringList WdcLegend::infoLines(int i) const {
    const LegendEntry& le = entries_[size_t(i)];
    QStringList out;
    const SeriesEntry* e = le.entry;
    const QString disp = le.ref ? th::displayName(le.ref->nameRaw) : QString();
    out << ((e && !e->meta.name.isEmpty()) ? e->meta.name : disp);
    if (!e || e->data.status == Status::Missing) {
        out << QStringLiteral("[CẦN DATA]: ") + ((e && !e->reason.isEmpty()) ? e->reason : QStringLiteral("chưa có nguồn chính thức"));
        if (e && !e->meta.sourceName.isEmpty()) out << QStringLiteral("Nguồn dự kiến: ") + e->meta.sourceName;
        return out;
    }
    QString src = e->meta.sourceName.isEmpty() ? QStringLiteral("[CẦN DATA]") : e->meta.sourceName;
    if (!e->meta.sourceRef.isEmpty()) src += QStringLiteral(" (") + e->meta.sourceRef + QLatin1Char(')');
    out << QStringLiteral("Nguồn: ") + src;
    const QString unit = !e->unit.isEmpty() ? e->unit : (le.ref ? le.ref->unit : QString());
    if (!unit.isEmpty()) out << QStringLiteral("Đơn vị: ") + unit;
    if (!e->meta.release.isEmpty()) out << QStringLiteral("Lịch công bố: ") + e->meta.release;
    if (!e->asOf.isEmpty()) out << QStringLiteral("Kỳ cuối: ") + e->asOf;
    if (!e->meta.lastUpdated.isEmpty()) out << QStringLiteral("Cập nhật: ") + e->meta.lastUpdated;
    QString tier = QStringLiteral("Tầng: ") + (e->data.tier.isEmpty() ? QStringLiteral("[CẦN DATA]") : e->data.tier);
    if (e->data.status == Status::Partial)
        tier += QStringLiteral(" · một phần") +
                (e->partialReasons.isEmpty() ? QString() : QStringLiteral(" (") + e->partialReasons.join(QStringLiteral(", ")) + QLatin1Char(')'));
    out << tier;
    for (const TierSpan& s : e->tierSpans)
        out << QStringLiteral("Đoạn %1: %2 đến %3").arg(s.tier, wdcl_date(s.from), wdcl_date(s.to));
    for (const auto& b : e->data.breaks) out << QStringLiteral("Gãy chuỗi %1: %2").arg(wdcl_date(b.first), b.second);
    for (const QString& n : e->meta.notes) out << n;
    return out;
}

void WdcLegend::showInfo(int i) {
    infoPending_ = -1;
    if (i < 0 || i >= count()) return;
    if (!pop_) pop_ = new WdcPopover(this, WdcPopover::Mode::Tip);
    pop_->setLines(infoLines(i));
    const QRectF ic = (i == hover_ ? g().items[size_t(i)].infoIconHover : g().items[size_t(i)].infoIcon).translated(0, -scrollY_);
    pop_->showAt(mapToGlobal(QPointF(ic.left(), ic.bottom() + 4)).toPoint());
    infoFor_ = i;
}

void WdcLegend::hideInfo() {
    infoPending_ = -1;
    if (infoTimer_) infoTimer_->stop();
    if (pop_) pop_->hide();
    infoFor_ = -1;
}

} // namespace fincept::screens::wdc
