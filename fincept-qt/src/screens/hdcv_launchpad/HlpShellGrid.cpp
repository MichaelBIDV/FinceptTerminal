// src/screens/hdcv_launchpad/HlpShellGrid.cpp
// HĐCV LAUNCHPAD shell — the 12-column #grid of index.html: .pnl frames (header .hd + body .bd + border
// ring), render() / panel() / setCtx(), ◀ ▶ ✕, drag & drop of headers, and the overlay-scrolled grid
// viewport. See HlpShell_p.h for how the shell is split.
//
//  - Grid geometry is computed in fractional CSS px (Chrome's grid: sequential auto-placement, row
//    height = max natural panel height, panels stretched to the row) and only rounded when a QWidget
//    geometry is set. Frames paint their rounded background and border antialiased at the exact
//    fractional position, like Chrome paints a rounded box; an overlay "ring" per frame paints the border
//    and masks the corners (`.pnl{overflow:hidden}` clipping of the body).
//  - The #grid scrolls with an overlay scrollbar that takes no space (macOS/Chrome behaviour).
//  - Node click handlers run inside HlpView's event handling, so every action they trigger that rebuilds
//    a tree is deferred one event-loop turn; replaced frames are hidden and deleteLater()'d.
#include "screens/hdcv_launchpad/HlpShell_p.h"

#include "screens/hdcv_launchpad/HlpAtoms.h"
#include "screens/hdcv_launchpad/HlpTheme.h"

#include <QApplication>
#include <QCursor>
#include <QDateTime>
#include <QEnterEvent>
#include <QGraphicsOpacityEffect>
#include <QImage>
#include <QMouseEvent>
#include <QPainter>
#include <QPaintEvent>
#include <QTimer>
#include <QWheelEvent>

#include <cmath>
#include <vector>

namespace fincept::screens::hlp {

namespace shell_detail {

// =================================================================================================
// Geometry / painting
// =================================================================================================

QRect hlpsh_outer(const QRectF& r) {
    const int x0 = int(std::floor(r.left())), y0 = int(std::floor(r.top()));
    const int x1 = int(std::ceil(r.right())), y1 = int(std::ceil(r.bottom()));
    return {x0, y0, std::max(0, x1 - x0), std::max(0, y1 - y0)};
}

void hlpsh_place(HlpView* v, const QRectF& r) {
    const QRect g = hlpsh_outer(r);
    v->setGeometry(g);
    v->setSubpixelGeometry(QRectF(r.topLeft() - QPointF(g.topLeft()), r.size()));
}

QRectF hlpsh_snapHalf(const QRectF& r) {
    // Chrome snaps box-decoration edges to the half-pixel grid (zoom-2 pixel snapping; see
    // HlpDomLayout_p.h snap()): each edge independently, 329.695 → 329.5, 836.83 → 837, 1335.33 → 1335.5
    const auto h = [](double v) { return std::floor(v * 2.0 + 0.5) / 2.0; };
    const double l = h(r.left()), t = h(r.top());
    return QRectF(l, t, h(r.right()) - l, h(r.bottom()) - t);
}

hlpsh_Radii hlpsh_fit(const QRectF& r, const hlpsh_Radii& k) {
    double f = 1.0;
    const auto lim = [&f](double len, double sum) {
        if (sum > len && sum > 0.0)
            f = std::min(f, len / sum);
    };
    lim(r.width(), k.tl + k.tr);
    lim(r.width(), k.bl + k.br);
    lim(r.height(), k.tl + k.bl);
    lim(r.height(), k.tr + k.br);
    return {float(k.tl * f), float(k.tr * f), float(k.br * f), float(k.bl * f)};
}

hlpsh_Radii hlpsh_all(float r) {
    return {r, r, r, r};
}

Radii4 hlpsh_r4(const hlpsh_Radii& k, float inset) {
    const auto v = [inset](float r) { return double(std::max(0.0f, r - inset)); };
    return {{QPointF(v(k.tl), v(k.tl)), QPointF(v(k.tr), v(k.tr)), QPointF(v(k.br), v(k.br)), QPointF(v(k.bl), v(k.bl))}};
}

void hlpsh_box(QPainter& p, const QRectF& r, const hlpsh_Radii& radii, const QColor& bg, const QColor& border) {
    // as Chrome: background shrunk half the border width (bleed avoidance), then the 1px ring (drawDRRect)
    const hlpsh_Radii k = hlpsh_fit(r, radii);
    fillRRect(p, r.adjusted(0.5, 0.5, -0.5, -0.5), hlpsh_r4(k, 0.5f), bg);
    const QRectF hole = r.adjusted(1, 1, -1, -1);
    const Radii4 hk = hlpsh_r4(k, 1.0f);
    fillRRect(p, r, hlpsh_r4(k, 0.0f), border, &hole, &hk);
}

// =================================================================================================
// Panel frame (.pnl) + ring
// =================================================================================================

hlpsh_Ring::hlpsh_Ring(hlpsh_Frame* frame) : QWidget(frame), frame_(frame) {
    hlpsh_mark(this);
    setAttribute(Qt::WA_TransparentForMouseEvents);
}

/// The .pnl box as Chrome paints it before its children: background shrunk half a pixel inside the
/// (half-pixel snapped) border edge — Blink's bleed avoidance, measured: a border half-covering row 329
/// shows page bg under it (25), the row above panel bg (29) — then the 1px border ring.
void hlpsh_paintPnl(QPainter& p, const QRectF& r, const hlpsh_Radii& k, const QColor& bg, const QColor& border) {
    hlpsh_box(p, r, k, bg, border);
}

QColor hlpsh_Frame::borderColor() const {
    const Palette& P = pal();
    return over ? P.amber : hovered ? P.line2 : P.line;
}

void hlpsh_Ring::paintEvent(QPaintEvent*) {
    // `.pnl{overflow:hidden}` clips the children to the padding box (inner border edge, antialiased)
    // and they paint OVER the border. Children only reach past that edge in the four corners, so only
    // there the frame's own pixels (page bg + panel bg + border) are put back with alpha = 1 − inner
    // coverage: result = cov·children + (1 − cov)·frame, exactly Chrome's clip.
    const Palette& P = pal();
    const QRectF r = hlpsh_snapHalf(QRectF(frame_->off, frame_->exact.size()));
    const hlpsh_Radii k = hlpsh_fit(r, hlpsh_all(hlpsh_kRadius));
    const QRectF inner = r.adjusted(1, 1, -1, -1);
    const Radii4 innerRad = hlpsh_r4(k, 1.0f);
    const float rad[4] = {k.tl, k.tr, k.br, k.bl};
    const QPointF corner[4] = {r.topLeft(), r.topRight(), r.bottomRight(), r.bottomLeft()};
    const int sx[4] = {1, -1, -1, 1}, sy[4] = {1, 1, -1, -1};
    QPainter p(this);
    for (int i = 0; i < 4; ++i) {
        if (rad[i] <= 0.0f)
            continue;
        const double ext = double(rad[i]) + 1.0;
        const QRectF cr = QRectF(corner[i], corner[i] + QPointF(sx[i] * ext, sy[i] * ext)).normalized();
        const QRect dev = hlpsh_outer(cr).intersected(rect());
        if (dev.isEmpty())
            continue;
        QImage frameOnly(dev.size(), QImage::Format_ARGB32_Premultiplied);
        frameOnly.fill(P.bg);
        {
            QPainter fp(&frameOnly);
            fp.setRenderHint(QPainter::Antialiasing);
            fp.translate(-dev.topLeft());
            hlpsh_paintPnl(fp, r, k, P.panel, frame_->borderColor());
            fp.setCompositionMode(QPainter::CompositionMode_DestinationOut);
            fillRRect(fp, inner, innerRad, Qt::black); // alpha = 1 − inner coverage (Skia's AA clip)
        }
        p.drawImage(dev.topLeft(), frameOnly);
    }
}

hlpsh_Frame::hlpsh_Frame(QWidget* parent) : QWidget(parent) {
    hlpsh_mark(this);
    setProperty("hlp_role", QStringLiteral("pnl"));
}

hlpsh_Frame::~hlpsh_Frame() {
    // Views first: their node trees hold callbacks that point at rc / state below.
    delete hd;
    delete body;
    hd = nullptr;
    body = nullptr;
}

void hlpsh_Frame::setOver(bool on) {
    if (over == on)
        return;
    over = on;
    update();
    if (ring)
        ring->update();
}

void hlpsh_Frame::paintEvent(QPaintEvent*) {
    QPainter p(this);
    p.setRenderHint(QPainter::Antialiasing);
    const QRectF r = hlpsh_snapHalf(QRectF(off, exact.size()));
    hlpsh_paintPnl(p, r, hlpsh_fit(r, hlpsh_all(hlpsh_kRadius)), pal().panel, borderColor());
}

void hlpsh_Frame::enterEvent(QEnterEvent* e) {
    QWidget::enterEvent(e);
    hovered = true; // .pnl:hover
    update();
    if (ring)
        ring->update();
}

void hlpsh_Frame::leaveEvent(QEvent* e) {
    QWidget::leaveEvent(e);
    hovered = false;
    update();
    if (ring)
        ring->update();
}

bool hlpsh_Frame::eventFilter(QObject* o, QEvent* e) {
    if (o != hd)
        return QWidget::eventFilter(o, e);
    switch (e->type()) {
        case QEvent::MouseButtonPress: {
            const auto* me = static_cast<QMouseEvent*>(e);
            if (me->button() == Qt::LeftButton) {
                armed_ = true;
                pressGlobal_ = me->globalPosition().toPoint();
            }
            break;
        }
        case QEvent::MouseMove: {
            const auto* me = static_cast<QMouseEvent*>(e);
            const QPoint g = me->globalPosition().toPoint();
            if (dragging) {
                if (onDragMove)
                    onDragMove(this, g);
                return true;
            }
            if (armed_ && (me->buttons() & Qt::LeftButton) &&
                (g - pressGlobal_).manhattanLength() >= QApplication::startDragDistance()) {
                dragging = true;
                hd->setCursor(Qt::ClosedHandCursor); // .hd:active{cursor:grabbing}
                if (onDragStart)
                    onDragStart(this);
                if (onDragMove)
                    onDragMove(this, g);
                return true;
            }
            break;
        }
        case QEvent::MouseButtonRelease: {
            const auto* me = static_cast<QMouseEvent*>(e);
            armed_ = false;
            if (dragging && me->button() == Qt::LeftButton) {
                dragging = false;
                hd->setCursor(Qt::OpenHandCursor);
                if (onDragEnd)
                    onDragEnd(this, me->globalPosition().toPoint());
                return true;
            }
            break;
        }
        default:
            break;
    }
    return QWidget::eventFilter(o, e);
}

// =================================================================================================
// #grid — scroll container with an overlay scrollbar (Chrome on macOS: takes no layout space).
// =================================================================================================

hlpsh_GridContent::hlpsh_GridContent(QWidget* parent) : QWidget(parent) {
    hlpsh_mark(this);
}

void hlpsh_GridContent::paintEvent(QPaintEvent* e) {
    QPainter p(this);
    p.fillRect(e->rect(), pal().bg); // body{background:var(--bg)}
}

hlpsh_ScrollThumb::hlpsh_ScrollThumb(QWidget* parent) : QWidget(parent) {
    hlpsh_mark(this);
    setAttribute(Qt::WA_TransparentForMouseEvents);
    hide_.setSingleShot(true);
    hide_.setInterval(hlpsh_kScrollbarShowMs);
    QObject::connect(&hide_, &QTimer::timeout, this, [this] {
        shown_ = false;
        update();
    });
}

void hlpsh_ScrollThumb::flash(int contentH, int viewH, int scroll) {
    contentH_ = contentH;
    viewH_ = viewH;
    scroll_ = scroll;
    shown_ = true;
    update();
    hide_.start();
}

void hlpsh_ScrollThumb::paintEvent(QPaintEvent*) {
    if (!shown_ || contentH_ <= viewH_ || viewH_ <= 0)
        return;
    QPainter p(this);
    p.setRenderHint(QPainter::Antialiasing);
    const double th = std::max(24.0, double(viewH_) * viewH_ / contentH_);
    const double ty = double(scroll_) / double(contentH_ - viewH_) * (viewH_ - th);
    const QRectF thumb(2, ty + 2, 7, th - 4);
    p.setPen(Qt::NoPen);
    p.setBrush(is_dark() ? QColor(255, 255, 255, 110) : QColor(0, 0, 0, 110));
    p.drawRoundedRect(thumb, 3.5, 3.5);
}

hlpsh_GridVp::hlpsh_GridVp(QWidget* parent) : QWidget(parent) {
    hlpsh_mark(this);
    setProperty("hlp_role", QStringLiteral("grid"));
    content = new hlpsh_GridContent(this);
    thumb = new hlpsh_ScrollThumb(this);
    content->show();
    thumb->show();
}

void hlpsh_GridVp::setScrollY(int y) {
    y = std::clamp(y, 0, maxScroll());
    const bool moved = y != scrollY;
    scrollY = y;
    content->move(0, -scrollY);
    if (moved)
        thumb->flash(content->height(), height(), scrollY);
}

void hlpsh_GridVp::wheelEvent(QWheelEvent* e) {
    // Bodies that cannot scroll further leave the event to us (scroll chaining).
    const QPoint px = e->pixelDelta();
    const int dy = !px.isNull() ? px.y() : e->angleDelta().y() * 100 / 120;
    if (dy == 0 || maxScroll() == 0) {
        e->ignore();
        return;
    }
    setScrollY(scrollY - dy);
    e->accept();
}

void hlpsh_GridVp::resizeEvent(QResizeEvent* e) {
    QWidget::resizeEvent(e);
    thumb->setGeometry(width() - 11, 0, 11, height());
    thumb->raise();
    if (onResized)
        onResized();
}

} // namespace shell_detail

using namespace shell_detail;

// =================================================================================================
// render() / panel(): rebuild every panel of the view, #tick = ctx
// =================================================================================================

void Shell::Impl::render() {
    if (!booted || dying)
        return; // activate() renders the first time (state + data loaded)
    renderBar();
    clearFrames();
    if (!dataOk) {
        frames.push_back(makeFrame({QStringLiteral("_nodata"), 12, int(hlpsh_kBdFallback)}, -1, nullptr));
    } else {
        tick->setText(ctx);
        if (const hlpsh_View* v = cur())
            for (int i = 0; i < v->panels.size(); ++i)
                if (const PanelDef* def = panel_def(v->panels[i].id)) // unknown ids (other builds) are skipped
                    frames.push_back(makeFrame(v->panels[i], i, def));
    }
    layoutGrid();
}

void Shell::Impl::clearFrames() {
    for (hlpsh_Frame* f : frames) {
        f->hide();
        f->deleteLater(); // may be the frame whose event handler called us
    }
    frames.clear();
    dragSrc = nullptr;
}

hlpsh_Frame* Shell::Impl::makeFrame(const hlpsh_PanelSpec& spec, int index, const PanelDef* def) {
    auto* f = new hlpsh_Frame(grid->content);
    f->setProperty("hlp_panel", spec.id);
    f->uid = nextUid++;
    f->index = index;
    f->spec = spec;
    f->def = def;
    if (def) {
        f->rawTitle = def->title ? def->title(ctx) : def->id;
        f->hd = new HlpView(f);
        f->hd->setProperty("hlp_role", QStringLiteral("hd"));
        f->hd->setMaxContentHeight(0);
        f->hd->setCursor(Qt::OpenHandCursor); // .hd{cursor:grab}
        f->hd->installEventFilter(f);
        QObject::connect(f->hd, &HlpView::contentResized, q, [this] { relayoutSoon(); });
    }
    f->body = new HlpView(f);
    f->body->setProperty("hlp_role", QStringLiteral("bd"));
    f->body->setMaxContentHeight(f->maxBody());
    QObject::connect(f->body, &HlpView::contentResized, q, [this] { relayoutSoon(); });
    f->ring = new hlpsh_Ring(f); // last child → above header and body
    f->onDragStart = [this](hlpsh_Frame* s) { dragStart(s); };
    f->onDragMove = [this](hlpsh_Frame*, QPoint g) { dragMove(g); };
    f->onDragEnd = [this](hlpsh_Frame* s, QPoint g) { dragEnd(s, g); };
    if (def)
        f->rc = makeRc(f);
    renderBody(f, false, false);
    if (f->hd)
        f->hd->show();
    f->body->show();
    f->ring->show();
    f->show();
    return f;
}

std::unique_ptr<RenderCtx> Shell::Impl::makeRc(hlpsh_Frame* f) {
    const quint64 uid = f->uid;
    QVariantMap* vs = &viewStates[view + QLatin1Char('/') + f->spec.id];
    return std::unique_ptr<RenderCtx>(new RenderCtx{
        store->data(), ctx, view, QDateTime::currentDateTime(), &f->asof, &f->state, vs,
        [this](const QString& t) { defer([this, t] { q->setCtx(t); }); },
        [this, uid] { queueRerender(uid); },
        [f](const QString& key) -> QLineEdit* {
            QPointer<QLineEdit>& slot = f->edits[key];
            if (!slot)
                slot = new hlpsh_FieldEdit(f->body);
            return slot.data();
        },
        [f](const QString& key) -> QComboBox* {
            QPointer<QComboBox>& slot = f->combos[key];
            if (!slot)
                slot = hlpsh_makeSelect(f->body);
            return slot.data();
        },
        [](const QString& url) { hlpsh_openUrl(url); }});
}

/// `.hd`: link dot · h2 (uppercase, ellipsis) · .asof · ◀ ▶ ✕.
void Shell::Impl::renderHeader(hlpsh_Frame* f) {
    if (!f->hd)
        return;
    const Palette& P = pal();
    const bool linked = f->def->linked;
    N hd = div();
    hd.flex(Justify::Start, AlignItems::Center, 6).p(4, 8).bg(P.panelHd).bb(1, P.line).key(QStringLiteral("hd"));
    N dot = div();
    dot.w(7).h(7).radius(3.5f).bg(linked ? P.amber : P.ink3).shrink(0).key(QStringLiteral("link"));
    dot.tip(linked ? QStringLiteral("Đi theo mã ở thanh trên") : QStringLiteral("Không liên kết mã"));
    N h2 = div();
    h2.sans(10.5f, 600).lhf(1.4f).ls(0.07f).c(P.amber).upper().nowrap().ellipsis().minW(0).key(QStringLiteral("h2"));
    h2 << text(f->rawTitle);
    N as = div();
    as.mlAuto().mono(10).lhNormal().c(P.ink3).nowrap().key(QStringLiteral("asof"));
    if (!f->asof.isEmpty())
        as << text(f->asof);
    hd << dot << h2 << as;
    static const QString glyph[3] = {QStringLiteral("◀"), QStringLiteral("▶"), QStringLiteral("✕")};
    const quint64 uid = f->uid;
    for (int a = 0; a < 3; ++a) {
        N b = div(); // .hbtn: padding 0 3px, 12px/1, ink-3, hover amber
        b.sans(12).lh(12).p(0, 3).c(P.ink3).hoverColor(P.amber).pointer().key(QStringLiteral("hbtn%1").arg(a));
        if (a == 2)
            b.tip(QStringLiteral("Đóng"));
        b.click([this, uid, a] { defer([this, uid, a] { headerAction(uid, a); }); });
        b << text(glyph[a]);
        hd << b;
    }
    f->hd->setRoot(hd, false);
}

/// C.render(bd, D, ctx, asof) wrapped in `.bd{padding:7px 9px}`; exceptions → `.warn`.
void Shell::Impl::renderBody(hlpsh_Frame* f, bool keepScroll, bool viaSetCtx) {
    N root = div();
    root.p(7, 9).key(QStringLiteral("bd"));
    if (!f->def) {
        N w = atoms::warn();
        w << text(QStringLiteral("Không đọc được ")) << atoms::code(QStringLiteral("data/launchpad_data.json"))
          << text(QStringLiteral(". Chạy: ")) << atoms::code(QStringLiteral("python3 build_launchpad.py"));
        root << w;
    } else {
        RenderCtx& rc = *f->rc;
        rc.ctx = ctx;
        rc.viewKey = view;
        rc.now = QDateTime::currentDateTime();
        NodeP content;
        QString err;
        bool failed = false;
        try {
            if (f->def->render)
                content = f->def->render(rc);
        } catch (const std::exception& ex) {
            failed = true;
            err = QString::fromUtf8(ex.what());
        } catch (...) {
            failed = true;
            err = QStringLiteral("undefined"); // String(e.message) of a non-Error throw
        }
        if (failed) {
            // panel(): "Panel lỗi: …"; setCtx(): the bare message (index.html differs, kept as is)
            N w = atoms::warn();
            w << text((viaSetCtx ? QString() : QStringLiteral("Panel lỗi: ")) + err.left(120));
            root << w;
        } else if (content) {
            root << content;
        }
        if (f->def->id == QLatin1String("wdsignal"))
            f->wdVer = store->data().wd.value(QStringLiteral("cap_nhat"));
    }
    f->body->setRoot(root, keepScroll);
    renderHeader(f); // .asof / title may have changed
}

void Shell::Impl::queueRerender(quint64 uid) {
    hlpsh_Frame* f = frameByUid(uid);
    if (!f || f->rerenderQueued)
        return;
    f->rerenderQueued = true;
    defer([this, uid] {
        if (hlpsh_Frame* g = frameByUid(uid)) {
            g->rerenderQueued = false;
            renderBody(g, true, false);
            layoutGrid();
        }
    });
}

void Shell::Impl::headerAction(quint64 uid, int a) {
    hlpsh_Frame* f = frameByUid(uid);
    hlpsh_View* v = cur();
    if (!f || !v || f->index < 0 || f->index >= v->panels.size())
        return;
    // hd.onclick: x → splice(i,1) · w+ → min(12,w+1) · w- → max(2,w-1); then save(); render();
    if (a == 2) {
        v->panels.removeAt(f->index);
    } else {
        int& w = v->panels[f->index].w;
        w = a == 1 ? std::min(12, w + 1) : std::max(2, w - 1);
    }
    saveState();
    render();
}

// ---- #grid layout ----
void Shell::Impl::relayoutSoon() {
    if (relayoutQueued || dying)
        return;
    relayoutQueued = true;
    QTimer::singleShot(0, q, [this] {
        if (relayoutQueued && !dying)
            layoutGrid();
    });
}

/// grid-template-columns: repeat(12,1fr); gap/padding 6; sparse auto-placement of `span w`; rows
/// min-content (= max natural panel height); panels stretch to their row; bd max-height = h.
void Shell::Impl::layoutGrid() {
    relayoutQueued = false;
    if (dying)
        return;
    const int Wi = q->width();
    const float W = float(Wi);
    const int cols = Wi <= hlpsh_kNarrowPx ? 4 : 12;
    const float colW = std::max(0.0f, (W - 2 * hlpsh_kGap - float(cols - 1) * hlpsh_kGap) / float(cols));

    std::vector<float> rowH;
    int row = 0, col = 0;
    for (hlpsh_Frame* f : frames) {
        const int span = cols == 4 ? 4 : std::clamp(f->spec.w, 1, 12);
        if (col + span > cols) {
            ++row;
            col = 0;
        }
        f->row = row;
        f->col = col;
        f->span = span;
        col += span;
        // Chrome sizes the 1fr tracks in LayoutUnits (1/128 px) with the fraction carried along: track
        // edge k = floor(k × fr) (measured: 504.5 · 836.828125 · 1335.328125 · span-7 width 1157.171875)
        const auto edge = [colW](int k) { return float(std::floor(double(k) * double(colW) * 128.0 + 1e-6) / 128.0); };
        const float x = hlpsh_kGap + edge(f->col) + float(f->col) * hlpsh_kGap;
        const float w = edge(f->col + span) - edge(f->col) + float(span - 1) * hlpsh_kGap;
        f->exact = QRectF(x, 0, w, 0);
        const float innerW = w - 2.0f; // header/body are laid out at the exact CSS width (hlpsh_place)
        if (f->hd) {
            const float h = f->hd->contentHeight(innerW);
            f->hdH = h > 0.0f ? h : hlpsh_kHdH;
        } else {
            f->hdH = 0.0f;
        }
        const float natural = 2.0f + f->hdH + f->body->preferredHeight(innerW);
        if (rowH.size() <= size_t(row))
            rowH.resize(size_t(row) + 1, 0.0f);
        rowH[size_t(row)] = std::max(rowH[size_t(row)], natural);
    }

    std::vector<float> rowY(rowH.size(), 0.0f);
    float y = hlpsh_kGap;
    for (size_t r = 0; r < rowH.size(); ++r) {
        rowY[r] = y;
        y += rowH[r] + hlpsh_kGap;
    }
    contentH = rowH.empty() ? 2 * hlpsh_kGap : y;

    for (hlpsh_Frame* f : frames) {
        const float h = rowH[size_t(f->row)];
        f->exact = QRectF(f->exact.x(), rowY[size_t(f->row)], f->exact.width(), h);
        f->bdH = std::max(0.0f, std::min(f->maxBody(), h - 2.0f - f->hdH));
        const QRect g = hlpsh_outer(f->exact);
        f->off = f->exact.topLeft() - QPointF(g.topLeft());
        f->setGeometry(g);
        const float iw = float(f->exact.width()) - 2.0f;
        if (f->hd)
            hlpsh_place(f->hd, QRectF(f->off.x() + 1, f->off.y() + 1, iw, f->hdH));
        hlpsh_place(f->body, QRectF(f->off.x() + 1, f->off.y() + 1 + f->hdH, iw, f->bdH));
        f->ring->setGeometry(QRect(QPoint(0, 0), g.size()));
        f->update();
        f->ring->update();
    }
    grid->content->resize(Wi, std::max(grid->height(), int(std::ceil(contentH))));
    grid->setScrollY(grid->scrollY);
    syncHoverSoon();
}

void Shell::Impl::syncHoverSoon() {
    if (hoverQueued || dying)
        return;
    hoverQueued = true;
    QTimer::singleShot(0, q, [this] {
        hoverQueued = false;
        syncHoverNow(true);
    });
}

namespace {
/// One-shot application filter: the next mouse move anywhere runs `fn`, then the filter goes away.
class hlpshg_NextMove final : public QObject {
  public:
    hlpshg_NextMove(QObject* owner, std::function<void()> fn) : QObject(owner), fn_(std::move(fn)) {
        qApp->installEventFilter(this);
    }

  protected:
    bool eventFilter(QObject*, QEvent* e) override {
        if (e->type() == QEvent::MouseMove && fn_) {
            auto fn = std::move(fn_);
            fn_ = nullptr;
            qApp->removeEventFilter(this);
            deleteLater();
            fn();
        }
        return false;
    }

  private:
    std::function<void()> fn_;
};
} // namespace

void Shell::Impl::syncHoverNow(bool rearm) {
    if (dying || dragSrc || !q->isVisible())
        return;
    QWidget* under = QApplication::widgetAt(QCursor::pos());
    for (hlpsh_Frame* f : frames) {
        const bool on = under && (under == f || f->isAncestorOf(under));
        if (on != f->hovered) { // .pnl:hover
            f->hovered = on;
            f->update();
            if (f->ring)
                f->ring->update();
        }
        if (f->hd)
            f->hd->syncHover();
        f->body->syncHover();
    }
    if (rearm && !hoverRecheck)
        hoverRecheck = new hlpshg_NextMove(q, [this] { syncHoverNow(false); });
}

// ---- setCtx(v): only `linked` panels re-render (title + body) ----
void Shell::Impl::setCtx(const QString& raw) {
    const QString v = raw.trimmed().toUpper();
    if (v.isEmpty())
        return;
    ctx = v;
    saveState();
    tick->setText(ctx); // clicking a Monitor row must sync the input too
    for (hlpsh_Frame* f : frames) {
        if (!f->def || !f->def->linked)
            continue;
        f->rawTitle = f->def->title ? f->def->title(ctx) : f->def->id;
        renderBody(f, true, true);
    }
    layoutGrid();
}

// =================================================================================================
// Drag & drop (.hd draggable, .pnl.drag opacity .4, .pnl.over amber border)
// =================================================================================================

hlpsh_Frame* Shell::Impl::frameAtGlobal(const QPoint& g) const {
    if (!grid->rect().contains(grid->mapFromGlobal(g)))
        return nullptr;
    const QPointF p = grid->content->mapFromGlobal(QPointF(g));
    for (hlpsh_Frame* f : frames)
        if (f->exact.contains(p))
            return f;
    return nullptr;
}

void Shell::Impl::dragStart(hlpsh_Frame* f) {
    dragSrc = f;
    auto* eff = new QGraphicsOpacityEffect(f);
    eff->setOpacity(0.4);
    f->setGraphicsEffect(eff);
    autoScroll->start();
}

void Shell::Impl::dragMove(const QPoint& g) {
    dragGlobal = g;
    hlpsh_Frame* target = frameAtGlobal(g);
    for (hlpsh_Frame* f : frames)
        f->setOver(f == target);
    const int vy = grid->mapFromGlobal(g).y();
    const int bottom = grid->height() - hlpsh_kAutoScrollZone;
    autoDy = vy < hlpsh_kAutoScrollZone ? -(hlpsh_kAutoScrollZone - vy) / 2 : vy > bottom ? (vy - bottom) / 2 : 0;
}

void Shell::Impl::dragAutoTick() {
    if (autoDy == 0 || !dragSrc)
        return;
    grid->setScrollY(grid->scrollY + autoDy);
    dragMove(dragGlobal);
}

void Shell::Impl::dragEnd(hlpsh_Frame* src, const QPoint& g) {
    autoScroll->stop();
    autoDy = 0;
    hlpsh_Frame* target = frameAtGlobal(g);
    for (hlpsh_Frame* f : frames)
        f->setOver(false);
    if (src)
        src->setGraphicsEffect(nullptr);
    dragSrc = nullptr;
    hlpsh_View* v = cur();
    if (!src || !target || !v || src->index < 0 || target->index < 0 || src->index >= v->panels.size() ||
        target->index >= v->panels.size())
        return;
    // el.ondrop: arr.splice(i, 0, arr.splice(from, 1)[0]); save(); render();
    const hlpsh_PanelSpec moved = v->panels.takeAt(src->index);
    v->panels.insert(target->index, moved);
    saveState();
    render();
}

} // namespace fincept::screens::hlp
