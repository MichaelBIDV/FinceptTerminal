// src/screens/hdcv_launchpad/HlpView.cpp
// HlpView — renders one node tree as the `.bd` CSS scroll container: layout at the (sub-pixel) view
// width, scrollbars that take layout space, sticky offsets, embedded widgets, hit testing, hover /
// click / tooltip dispatch, geometry dump and innerText for the harness.
#include "screens/hdcv_launchpad/HlpDom.h"

#include "screens/hdcv_launchpad/HlpDomLayout_p.h"

#include <QApplication>
#include <QDesktopServices>
#include <QHash>
#include <QJsonArray>
#include <QJsonDocument>
#include <QJsonObject>
#include <QCursor>
#include <QHelpEvent>
#include <QMouseEvent>
#include <QPaintEvent>
#include <QResizeEvent>
#include <QPainter>
#include <QPainterPath>
#include <QPointer>
#include <QTextBoundaryFinder>
#include <QToolTip>
#include <QUrl>
#include <QWheelEvent>

#include <algorithm>
#include <functional>
#include <cmath>
#include <limits>

namespace fincept::screens::hlp {
namespace {

/// Chrome re-hit-tests only when the pointer moves: a box shown over a still pointer (the "+ Component"
/// sheet opening under the click) leaves the old :hover in place until the next mouse move. Qt sends
/// the view a synthetic Leave instead; this one-shot application filter clears the kept hover state on
/// the first mouse move anywhere (the view's own mouseMoveEvent re-hovers if the pointer is back on it).
class hlpvw_StaleHover : public QObject {
  public:
    hlpvw_StaleHover(QObject* owner, std::function<void()> clear) : QObject(owner), clear_(std::move(clear)) {
        setObjectName(QStringLiteral("hlp_stale_hover"));
        qApp->installEventFilter(this);
    }

  protected:
    bool eventFilter(QObject*, QEvent* e) override {
        if (e->type() == QEvent::MouseMove && clear_) {
            auto clear = std::move(clear_);
            clear_ = nullptr;
            qApp->removeEventFilter(this);
            deleteLater();
            clear();
        }
        return false;
    }

  private:
    std::function<void()> clear_;
};

} // namespace
} // namespace fincept::screens::hlp

namespace fincept::screens::hlp::hlpdom {

void ViewImpl::release(QWidget* w) {
    if (!w)
        return;
    w->hide();
    auto it = borrowed.find(w);
    QWidget* back = it != borrowed.end() ? it->data() : nullptr;
    if (it != borrowed.end())
        borrowed.erase(it);
    if (w->parentWidget() == q)
        w->setParent(back);
}

// ---- geometry helpers ----
QRectF ViewImpl::sub() const {
    if (subRect.width() > 0 && subRect.height() > 0)
        return subRect;
    const QVariant v = q->property("hlp_subpixel");
    if (v.canConvert<QRectF>()) {
        const QRectF r = v.toRectF();
        if (r.width() > 0 && r.height() > 0)
            return r;
    }
    return QRectF(0, 0, q->width(), q->height());
}

void ViewImpl::rebuild() {
    doc = std::make_unique<Doc>();
    hover.clear();
    pressBox = nullptr;
    customHoverBox = nullptr;
    hcache.clear();
    laidW = -1;
    if (!root)
        return;
    const CS base = rootCS();
    doc->root = build(*doc, root.get(), base, nullptr);
    if (!doc->root)
        return;
    markBfc(doc->root, true);
    prepare(doc->root);
}

/// layout at width w (no scrollbar logic); caches height
QPair<float, float> ViewImpl::measure(float w) {
    const int key = int(std::lround(w * 64.0f));
    auto it = hcache.constFind(key);
    if (it != hcache.constEnd())
        return *it;
    layoutAt(w);
    return hcache.value(key);
}

void ViewImpl::layoutAt(float w) {
    if (!doc || !doc->root) {
        contentH = 0;
        overflowW = 0;
        laidW = w;
        return;
    }
    Layout L(*doc);
    L.run(w);
    laidW = w;
    contentH = L.contentHeight;
    // scrollable overflow: descendants + the container's inline-end padding (Chrome ≥ 91)
    const Style* rs = doc->root->st;
    overflowW = std::max(w, L.overflowRight + (rs ? rs->pr + rs->bw[1] : 0.0f));
    hcache.insert(int(std::lround(w * 64.0f)), {contentH, overflowW});
}

/// decide scrollbars for the current widget size and lay out the active geometry
void ViewImpl::relayout() {
    const float W = viewW(), H = viewH();
    vbar = hbar = false;
    auto fits = [&](float w) { return measure(w); };
    QPair<float, float> m = fits(W);
    if (H > 0 && m.first > H + kEps) {
        vbar = true;
        m = fits(W - kScrollbar);
    }
    if (m.second > layoutW() + 0.5f) {
        hbar = true;
        if (!vbar && m.first > H - kScrollbar + kEps) {
            vbar = true;
            m = fits(W - kScrollbar);
        }
    }
    if (laidW != layoutW())
        layoutAt(layoutW());
    clampScroll();
    placeWidgets();
}

void ViewImpl::clampScroll() {
    scrollY = std::clamp(std::round(scrollY * 2.0f) / 2.0f, 0.0f, maxScrollY());
    scrollX = std::clamp(std::round(scrollX * 2.0f) / 2.0f, 0.0f, maxScrollX());
}

QPointF ViewImpl::scrollerShift() const {
    if (!vbar && !hbar)
        return {}; // no scrollable overflow → not a composited scroller → no shift
    const QRectF s = sub();
    // half-pixel-rounded page position; its .5 remainder is the shift
    auto shift = [](double v) {
        const double f = v - std::floor(v);
        const double h = std::floor(f * 2.0 + 0.5) / 2.0;
        return (h == 0.5) ? 0.5 : 0.0;
    };
    return {shift(s.x()), shift(s.y())};
}

QPointF ViewImpl::layerOrigin() const {
    const QRectF s = sub();
    const QPointF d = scrollerShift();
    return {s.x() + d.x(), s.y() + d.y()};
}

QPointF ViewImpl::paintOrigin() const {
    return layerOrigin() - QPointF(scrollX, scrollY);
}

QPointF ViewImpl::toContent(QPointF widgetPos) const {
    const QRectF s = sub();
    return QPointF(widgetPos.x() - s.x() + scrollX, widgetPos.y() - s.y() + scrollY);
}

// ---- sticky ----
float ViewImpl::stickyShift(Box* b) const {
    if (!b->st || !b->st->sticky)
        return 0;
    // containing block: the table for cells, the parent box otherwise
    Box* cb = b->parent;
    if (b->kind == BK::Cell && cb && cb->parent)
        cb = cb->parent;
    if (!cb)
        return 0;
    // the sticky view rectangle is the scrollport minus the scroll container's padding (the root's
    // padding here): Chrome puts a `top:-8px` th at y = 7 − 8 = −1 of the .bd
    const float pad = (doc && doc->root && doc->root->st) ? doc->root->st->pt : 0.0f;
    const float top = b->ay - scrollY; // position in the scrollport
    float shift = std::max(0.0f, pad + b->st->stickyTop - top);
    const float limit = (cb->ay + cb->h) - (b->ay + b->h);
    shift = std::min(shift, std::max(0.0f, limit));
    return shift;
}

// ---- widgets ----
void ViewImpl::placeWidgets() {
    if (!doc)
        return;
    const QRectF s = sub();
    const QPointF o = paintOrigin();
    for (Box* b : doc->widgets) {
        QWidget* w = b->node->widget;
        if (!w)
            continue;
        if (w->parentWidget() != q) {
            borrowed.insert(w, w->parentWidget());
            w->setParent(q);
        }
        const QRectF r(o.x() + b->ax, o.y() + b->ay, b->w, b->h);
        if (w->property("hlp_paintsFrame").toBool()) {
            // The control paints its own CSS box: give it the covering pixels plus the box snapped the
            // way paintBox snaps ours (half-pixel grid of the layer, scroll applied after) as "hlp_box",
            // in its own coordinates — a 4.5→28.5 border lands half on two rows, like Chrome's.
            const QPointF lo = layerOrigin();
            const auto sx = [&](float v) { return double(snap(v + float(lo.x()))) - double(scrollX); };
            const auto sy = [&](float v) { return double(snap(v + float(lo.y()))) - double(scrollY); };
            const QRectF sr(QPointF(sx(b->ax), sy(b->ay)), QPointF(sx(b->ax + b->w), sy(b->ay + b->h)));
            const int x0 = int(std::floor(sr.left())), y0 = int(std::floor(sr.top()));
            const int x1 = int(std::ceil(sr.right())), y1 = int(std::ceil(sr.bottom()));
            w->setGeometry(QRect(x0, y0, x1 - x0, y1 - y0));
            w->setProperty("hlp_box", sr.translated(-x0, -y0));
            w->setProperty("hlp_css", r.translated(-x0, -y0)); // unsnapped layout box: text is placed from it
        } else {
            // round the edges, not origin + size (keeps both edges within half a pixel of the CSS box)
            const int x0 = int(std::lround(r.left())), y0 = int(std::lround(r.top()));
            w->setGeometry(QRect(x0, y0, int(std::lround(r.right())) - x0, int(std::lround(r.bottom())) - y0));
        }
        const bool vis = r.bottom() > s.y() && r.top() < s.y() + portH();
        w->setVisible(vis);
    }
}

// ---- hit testing ----
Box* ViewImpl::hitBox(Box* b, QPointF p) {
    if (!b)
        return nullptr;
    if (b->ifc) {
        for (const Line& L : b->ifc->lines) {
            const float top = b->ay + L.top, bot = top + L.height;
            if (p.y() < top || p.y() >= bot)
                continue;
            for (const Frag& fr : L.frags) {
                const float x0 = b->ax + fr.x, x1 = x0 + fr.w;
                if (p.x() < x0 || p.x() >= x1)
                    continue;
                if (fr.box->kind == BK::Atomic) {
                    if (Box* h = hitBox(fr.box, p))
                        return h;
                    return fr.box;
                }
                return fr.box;
            }
        }
    } else {
        for (int i = int(b->kids.size()) - 1; i >= 0; --i) {
            Box* k = b->kids[i];
            if (k->kind == BK::Row || k->kind == BK::Cell || !isInlineLevel(k)) {
                const QRectF r(k->ax, k->ay + stickyShift(k), k->w, k->h);
                if (k->kind == BK::Row) {
                    if (r.contains(p)) {
                        if (Box* h = hitBox(k, p))
                            return h;
                        return k;
                    }
                    continue;
                }
                if (r.contains(p)) {
                    if (Box* h = hitBox(k, p))
                        return h;
                    return k;
                }
            }
        }
    }
    return nullptr;
}

QVector<Box*> ViewImpl::chainAt(QPointF widgetPos) {
    QVector<Box*> out;
    if (!doc || !doc->root)
        return out;
    if (laidW != layoutW())
        relayout();
    const QRectF s = sub();
    if (!QRectF(s.x(), s.y(), layoutW(), portH()).contains(widgetPos))
        return out;
    const QPointF p = toContent(widgetPos);
    Box* hit = nullptr;
    // sticky boxes are on top
    for (Box* sb : doc->stickies) {
        const QRectF r(sb->ax, sb->ay + stickyShift(sb), sb->w, sb->h);
        if (stickyShift(sb) > 0 && r.contains(p)) {
            hit = hitBox(sb, p);
            if (!hit)
                hit = sb;
            break;
        }
    }
    if (!hit) {
        Box* r = doc->root;
        if (QRectF(r->ax, r->ay, r->w, r->h).contains(p))
            hit = hitBox(r, p);
        if (!hit && QRectF(r->ax, r->ay, r->w, r->h).contains(p))
            hit = r;
    }
    for (Box* b = hit; b; b = b->parent)
        out.push_back(b);
    return out;
}

} // namespace fincept::screens::hlp::hlpdom

namespace fincept::screens::hlp {



HlpView::HlpView(QWidget* parent) : QWidget(parent), d_(std::make_unique<Impl>()) {
    using namespace hlpdom;
    d_->q = this;
    setMouseTracking(true);
    setAttribute(Qt::WA_OpaquePaintEvent, false);
    QSizePolicy sp(QSizePolicy::Preferred, QSizePolicy::Preferred);
    sp.setHeightForWidth(true);
    setSizePolicy(sp);
}

HlpView::~HlpView() {
    const auto ws = d_->borrowed.keys();
    for (QWidget* w : ws)
        if (w && w->parentWidget() == this)
            d_->release(w);
}

void HlpView::setRoot(const NodeP& root, bool keepScroll) {
    using namespace hlpdom;
    const float sx = d_->scrollX, sy = d_->scrollY;
    // widgets of the previous tree that are not in the new one get hidden
    QVector<QPointer<QWidget>> old;
    if (d_->doc)
        for (Box* b : d_->doc->widgets)
            if (b->node && b->node->widget)
                old.push_back(b->node->widget);
    const QVector<Box*> fOld = d_->focusables(); // keep focus on the same Tab stop across re-renders
    int fi = -1;
    for (int i = 0; i < fOld.size() && d_->focusNode; ++i)
        if (fOld[i]->node == d_->focusNode)
            fi = i;
    const bool hadHover = !d_->hover.isEmpty();
    d_->root = root;
    d_->rebuild();
    const QVector<Box*> fNew = d_->focusables();
    d_->focusNode = fi >= 0 && fi < fNew.size() ? fNew[fi]->node : nullptr;
    if (focusPolicy() == Qt::NoFocus && !fNew.isEmpty())
        setFocusPolicy(Qt::StrongFocus);
    for (const auto& w : old) {
        if (!w)
            continue;
        bool still = false;
        if (d_->doc)
            for (Box* b : d_->doc->widgets)
                if (b->node->widget == w)
                    still = true;
        if (!still)
            d_->release(w);
    }
    d_->scrollX = keepScroll ? sx : 0;
    d_->scrollY = keepScroll ? sy : 0;
    d_->relayout();
    if (hadHover) {
        // Blink: when the hovered element is detached, :hover is re-evaluated at the last pointer
        // position without a mouse move (◐ keeps :hover after the theme re-render; a chip clicked in
        // a re-rendered panel is hovered again). No JS mousemove runs, so custom hovers stay off.
        const QPointF pos = mapFromGlobal(QCursor::pos());
        if (rect().contains(pos.toPoint()))
            d_->hover = d_->chainAt(pos);
    }
    updateGeometry();
    update();
    emit contentResized();
}

NodeP HlpView::root() const {
    using namespace hlpdom;
    return d_->root;
}

void HlpView::setSubpixelGeometry(const QRectF& r) {
    using namespace hlpdom;
    if (r == d_->subRect)
        return;
    const float oldH = d_->contentH;
    d_->subRect = r;
    d_->relayout();
    update();
    if (oldH != d_->contentH)
        emit contentResized();
}

QRectF HlpView::subpixelGeometry() const {
    using namespace hlpdom;
    return d_->sub();
}

void HlpView::setMaxContentHeight(float px) {
    using namespace hlpdom;
    d_->maxH = std::max(0.0f, px);
    updateGeometry();
}

float HlpView::contentHeight(float width) const {
    using namespace hlpdom;
    return d_->measure(width).first;
}

float HlpView::preferredHeight(float width) const {
    using namespace hlpdom;
    QPair<float, float> m = d_->measure(width);
    const float maxH = d_->maxH;
    bool vb = false;
    if (maxH > 0 && m.first > maxH + kEps) {
        vb = true;
        m = d_->measure(width - kScrollbar);
    }
    const float lw = width - (vb ? kScrollbar : 0.0f);
    const bool hb = m.second > lw + 0.5f;
    float h = m.first + (hb ? kScrollbar : 0.0f);
    if (maxH > 0)
        h = std::min(h, maxH);
    // measuring other widths replaced the active geometry: restore it lazily at paint
    return h;
}

int HlpView::scrollY() const {
    using namespace hlpdom;
    return int(std::lround(d_->scrollY));
}

void HlpView::setScrollY(int y) {
    using namespace hlpdom;
    d_->scrollY = float(y);
    d_->clampScroll();
    d_->placeWidgets();
    update();
}

QString HlpView::dumpGeometryJson() const {
    using namespace hlpdom;
    if (d_->laidW != d_->layoutW())
        d_->layoutAt(d_->layoutW());
    QJsonArray arr;
    if (d_->doc && d_->doc->root) {
        const QRectF s = d_->sub();
        d_->dumpBox(d_->doc->root, arr, QPointF(s.x() - d_->scrollX, s.y() - d_->scrollY));
    }
    return QString::fromUtf8(QJsonDocument(arr).toJson(QJsonDocument::Compact));
}

QString HlpView::plainText() const {
    using namespace hlpdom;
    QString out;
    if (d_->doc && d_->doc->root) {
        if (d_->laidW != d_->layoutW())
            d_->layoutAt(d_->layoutW());
        d_->textOf(d_->doc->root, out);
    }
    return out;
}

QSize HlpView::sizeHint() const {
    using namespace hlpdom;
    const int w = width() > 0 ? width() : 300;
    return QSize(w, heightForWidth(w));
}

int HlpView::heightForWidth(int w) const {
    using namespace hlpdom;
    return int(std::ceil(preferredHeight(float(w)) - 1e-3f));
}

void HlpView::paintEvent(QPaintEvent* e) {
    using namespace hlpdom;
    QPainter p(this);
    if (!d_->doc || !d_->doc->root)
        return;
    if (d_->laidW != d_->layoutW())
        d_->relayout();
    const QRectF s = d_->sub();
    // Chrome clips the scroller's content at its padding box snapped to the half-pixel grid, then — once
    // the page has settled (≈1–10 s after load or any change) — takes the top, bottom and right edges
    // DOWN to the whole pixel: a .5 edge shows no clipped row (beri CHUYỂN ĐỘNG NGÀNH 364.695 → content
    // ends at row 363, row 364 = border only; the same at MONITOR 720.39 and FFT 1236.31, and a scrolled
    // .bd at top 64.695 paints row 64 in full). Right after a change Chrome briefly draws that row at half
    // coverage instead; the old ref2 ck/vimo captures caught that transient. Measured 27/09 on 36 edges.
    // The left edge keeps the half-covered column (horizontally scrolled .bd: 671.66 → column 671 at
    // half coverage, still after 14 s). The root's own background/border are painted unclipped (the .hd
    // border-bottom at 735.5–736.5 shows on both rows; next to a scrollbar they too stop at the whole
    // pixel: CHÍNH PHỦ shows no clipped row above its horizontal thumb).
    const QRectF port(s.x(), s.y(), d_->layoutW(), d_->portH());
    const float cl = snap(float(port.left())), ct = snap(float(port.top()));
    const float cr = snap(float(port.right())), cb = snap(float(port.bottom()));
    d_->contentClip = QRectF(QPointF(cl, std::floor(ct)), QPointF(std::floor(cr), std::floor(cb)));
    const QRectF rootClip(QPointF(cl, ct), QPointF(d_->vbar ? std::floor(cr) : cr, d_->hbar ? std::floor(cb) : cb));
    p.setClipRect(rootClip.toAlignedRect().intersected(e->rect()));
    // widget pixels = page pixels: paint content at its exact device offset so every snap in
    // HlpDomPaint.cpp lands on Chrome's grid (fractional box origin + composited-scroller half shift)
    const QPointF lo = d_->layerOrigin();
    d_->pox = float(lo.x());
    d_->poy = float(lo.y());
    p.translate(d_->paintOrigin());
    const QRectF clip(d_->scrollX, d_->scrollY, d_->layoutW(), d_->portH());
    p.setRenderHint(QPainter::TextAntialiasing, true);
    d_->paintBox(p, d_->doc->root, rootCS().color, false, clip);
    d_->paintStickies(p, clip);
    p.resetTransform();
    d_->paintEdgeStrips(p, e->rect());
    p.setClipping(false);
    d_->paintScrollbars(p);
}

void HlpView::resizeEvent(QResizeEvent* e) {
    using namespace hlpdom;
    QWidget::resizeEvent(e);
    const float oldH = d_->contentH;
    d_->relayout();
    if (oldH != d_->contentH)
        emit contentResized();
}

void HlpView::mouseMoveEvent(QMouseEvent* e) {
    using namespace hlpdom;
    const QPointF pos = e->position();
    d_->lastMouse = pos;
    if (d_->dragV) {
        const float track = d_->portH(), len = float(d_->vThumb().height());
        const float range = std::max(1.0f, track - len);
        d_->scrollY = d_->dragScroll0 + (float(pos.y()) - d_->dragStart) * d_->maxScrollY() / range;
        d_->clampScroll();
        d_->placeWidgets();
        update();
        return;
    }
    if (d_->dragH) {
        const float track = d_->layoutW(), len = float(d_->hThumb().width());
        const float range = std::max(1.0f, track - len);
        d_->scrollX = d_->dragScroll0 + (float(pos.x()) - d_->dragStart) * d_->maxScrollX() / range;
        d_->clampScroll();
        d_->placeWidgets();
        update();
        return;
    }
    QVector<Box*> chain = d_->chainAt(pos);
    // custom hover callbacks (sparkline / chart crosshair)
    Box* ch = nullptr;
    for (Box* b : chain)
        if (b->node && b->node->customHover) {
            ch = b;
            break;
        }
    if (d_->customHoverBox && d_->customHoverBox != ch && d_->customHoverBox->node->customHover)
        d_->customHoverBox->node->customHover(QPointF(), false);
    d_->customHoverBox = ch;
    if (ch) {
        const QPointF c = d_->toContent(pos);
        const Style* st = ch->st;
        ch->node->customHover(QPointF(c.x() - ch->ax - st->pl - st->bw[3], c.y() - ch->ay - st->pt - st->bw[0]), true);
        update();
    }
    if (chain != d_->hover) {
        d_->hover = chain;
        update();
    }
    // cursor: any pointer box / link in the chain, or a custom node that says so at this point
    bool pointer = false;
    for (Box* b : chain) {
        if (b->st && (b->st->pointer || (b->node && !b->node->href.isEmpty())))
            pointer = true;
        if (!pointer && b->node && b->node->customPointer) {
            const QPointF c = d_->toContent(pos);
            const Style* st = b->st;
            pointer = b->node->customPointer(
                QPointF(c.x() - b->ax - st->pl - st->bw[3], c.y() - b->ay - st->pt - st->bw[0]));
        }
        if (pointer)
            break;
    }
    const Qt::CursorShape want = pointer ? Qt::PointingHandCursor : Qt::ArrowCursor;
    if (cursor().shape() != want)
        setCursor(want);
}

void HlpView::mousePressEvent(QMouseEvent* e) {
    using namespace hlpdom;
    const QPointF pos = e->position();
    if (e->button() != Qt::LeftButton) {
        QWidget::mousePressEvent(e);
        return;
    }
    if (d_->vbar && d_->vThumb().contains(pos)) {
        d_->dragV = true;
        d_->dragStart = float(pos.y());
        d_->dragScroll0 = d_->scrollY;
        return;
    }
    if (d_->hbar && d_->hThumb().contains(pos)) {
        d_->dragH = true;
        d_->dragStart = float(pos.x());
        d_->dragScroll0 = d_->scrollX;
        return;
    }
    const QRectF s = d_->sub();
    if (d_->vbar && pos.x() >= s.x() + d_->viewW() - kScrollbar) {
        d_->scrollY += (pos.y() < d_->vThumb().top() ? -1.0f : 1.0f) * d_->portH() * 0.875f;
        d_->clampScroll();
        d_->placeWidgets();
        update();
        return;
    }
    const QVector<Box*> chain = d_->chainAt(pos);
    d_->pressBox = chain.isEmpty() ? nullptr : chain.first();
    if (chain != d_->hover) { // mousedown hit-tests and sets :hover like a move (no JS mousemove)
        d_->hover = chain;
        update();
    }
    for (Box* b : chain) // a click focuses the tabindex element (no ring: not :focus-visible)
        if (b->node && b->node->focusable) {
            d_->focusBox(b, false);
            setFocus(Qt::MouseFocusReason);
            break;
        }
}

void HlpView::mouseReleaseEvent(QMouseEvent* e) {
    using namespace hlpdom;
    if (d_->dragV || d_->dragH) {
        d_->dragV = d_->dragH = false;
        return;
    }
    if (e->button() != Qt::LeftButton)
        return;
    const QPointF pos = e->position();
    const QVector<Box*> chain = d_->chainAt(pos);
    Box* press = d_->pressBox;
    d_->pressBox = nullptr;
    if (chain.isEmpty() || !press || !chain.contains(press))
        return;
    // copy what we need BEFORE calling out: handlers may re-render (and destroy the box tree)
    const QPointF c = d_->toContent(pos);
    std::function<bool(QPointF)> customClick;
    QPointF customLocal;
    std::function<void()> onClick;
    QString href;
    for (Box* b : chain) {
        if (!b->node)
            continue;
        if (b->node->customClick && !customClick) {
            customClick = b->node->customClick;
            const Style* st = b->st;
            customLocal = QPointF(c.x() - b->ax - st->pl - st->bw[3], c.y() - b->ay - st->pt - st->bw[0]);
        }
        if (!onClick && b->node->onClick)
            onClick = b->node->onClick;
        if (href.isEmpty() && !b->node->href.isEmpty() && !onClick)
            href = b->node->href;
        if (onClick || !href.isEmpty())
            break;
    }
    QPointer<HlpView> guard(this);
    if (customClick && customClick(customLocal))
        return;
    if (!guard)
        return;
    if (onClick) {
        onClick();
        return;
    }
    if (!href.isEmpty()) {
        const QUrl u(href);
        const QString scheme = u.scheme().toLower();
        if (scheme == "http" || scheme == "https")
            QDesktopServices::openUrl(u);
    }
}

void HlpView::leaveEvent(QEvent* e) {
    using namespace hlpdom;
    if (e)
        QWidget::leaveEvent(e);
    if (e && !d_->hover.isEmpty() && isVisible() && rect().contains(mapFromGlobal(QCursor::pos()))) {
        // pointer still here: something was shown over it — keep :hover until the mouse moves
        if (!findChild<QObject*>(QStringLiteral("hlp_stale_hover"), Qt::FindDirectChildrenOnly)) {
            QPointer<HlpView> self(this);
            new hlpvw_StaleHover(this, [self] {
                if (self && QApplication::widgetAt(QCursor::pos()) != self.data())
                    self->leaveEvent(nullptr);
            });
        }
        return;
    }
    if (d_->customHoverBox && d_->customHoverBox->node->customHover)
        d_->customHoverBox->node->customHover(QPointF(), false);
    d_->customHoverBox = nullptr;
    if (!d_->hover.isEmpty()) {
        d_->hover.clear();
        setCursor(Qt::ArrowCursor);
        update();
    }
}

void HlpView::wheelEvent(QWheelEvent* e) {
    using namespace hlpdom;
    float dy = 0, dx = 0;
    if (!e->pixelDelta().isNull()) {
        dy = float(-e->pixelDelta().y());
        dx = float(-e->pixelDelta().x());
    } else {
        const float step = float(QApplication::wheelScrollLines()) * 20.0f;
        dy = float(-e->angleDelta().y()) / 120.0f * step;
        dx = float(-e->angleDelta().x()) / 120.0f * step;
    }
    if (e->modifiers() & Qt::ShiftModifier && dx == 0) {
        dx = dy;
        dy = 0;
    }
    const float oy = d_->scrollY, ox = d_->scrollX;
    d_->scrollY += dy;
    d_->scrollX += dx;
    d_->clampScroll();
    if (oy == d_->scrollY && ox == d_->scrollX) {
        e->ignore(); // chain to the outer scroller (the grid)
        return;
    }
    e->accept();
    d_->placeWidgets();
    // hover follows the content under the pointer
    const QPointF pos = mapFromGlobal(QCursor::pos());
    d_->hover = d_->chainAt(pos);
    update();
}

bool HlpView::event(QEvent* e) {
    using namespace hlpdom;
    if (e->type() == QEvent::ToolTip) {
        auto* he = static_cast<QHelpEvent*>(e);
        const QVector<Box*> chain = d_->chainAt(QPointF(he->pos()));
        QString tip;
        const QPointF c = d_->toContent(QPointF(he->pos()));
        for (Box* b : chain) {
            if (!b->node)
                continue;
            if (b->node->customTip) {
                const Style* st = b->st;
                tip = b->node->customTip(QPointF(c.x() - b->ax - st->pl - st->bw[3], c.y() - b->ay - st->pt - st->bw[0]));
                if (!tip.isEmpty())
                    break;
            }
            if (!b->node->tip.isEmpty()) {
                tip = b->node->tip;
                break;
            }
        }
        if (tip.isEmpty())
            QToolTip::hideText();
        else
            QToolTip::showText(he->globalPos(), tip, this);
        return true;
    }
    return QWidget::event(e);
}

} // namespace fincept::screens::hlp
