// WdcShell.cpp: "Bố cục:" bar, "+ Thêm biểu đồ" block, tab menu and tips of the WiData clone. Package E.
// Geometry: UI §1.2 (TB[] of CAP), §2.2 (AC[]), §5.3 (Blink baselines); states and popover: DESIGN §6.1.
// Tokens, icons, shadows, Chromium text runs: WdcTheme_p.h / WdcIcons_p.h of package D (no second copy here).
#include "WdcView.h"

#include "WdcIcons_p.h"
#include "WdcTheme_p.h"

#include <QFocusEvent>
#include <QKeyEvent>
#include <QMouseEvent>
#include <QPainter>
#include <QWheelEvent>

#include <algorithm>
#include <cmath>

namespace fincept::screens::wdc {
namespace {

namespace th = theme;

const QString kLabel = QStringLiteral("Bố cục:"), kAdd = QStringLiteral("Thêm"), kAddChart = QStringLiteral("Thêm biểu đồ");
const QString kWave2 = QStringLiteral("Đợt 2");
constexpr double kTabW = 120, kTabGap = 8, kRowY = 16, kRowH = 32, kAddW = 64, kBtn = 32;
constexpr double kLhTab = 20.4286, kLhBtn = 22.2857;
constexpr double kBlTab = 15.21, kBlBtn = 16.14, kBlLabel = 16.5;   // UI §5.3 (Blink rounding at DPR 1)
constexpr double kMenuItemH = th::kMenuRowH, kMenuMinW = 200;

QColor wdcshell_c(QRgb c) { return th::color(c); }
double wdcshell_dpr(const QWidget* w) { return std::max(1.0, w->devicePixelRatioF()); }

// HOVER_CSS.md (stylesheet of the reference site): ">" `.css-1rn2iod:hover {background-color: #F6F5F4}` (the last rule wins);
// "<" mirrors it. ▾ `.css-7fxovo:hover {background-color: rgba(166,176,195,.08)}`. "+ Thêm" `.css-1awvl63:hover`:
// transparent, no shadow, colour #21232E. A plain tab has no hover rule: it does not change.
const QColor kWsDropHover(166, 176, 195, 20);

void wdcshell_circle_button(QPainter& g, const QRectF& r, Icon icon, double dpr, bool hover) {
    paintBoxShadow(g, r, -1, shadowCircleBtn(), dpr);
    paintHairlineBox(g, r, r.width() / 2, wdcshell_c(hover ? th::kBgSubtle : th::kBgSurface), wdcshell_c(th::kBorder), dpr);
    paintIcon(g, icon, QRectF(r.x() + 7, r.y() + 7, 18, 18), wdcshell_c(th::kTextSecondary));
}

} // namespace

// ---- pure geometry -----------------------------------------------------------------------------------

QRectF addChartIconRect(const QRectF& r, double b) {
    const double tw = th::textWidth(QFontMetricsF(th::font(13, 500)), kAddChart, 500);
    const double inner = r.width() - 24 - 2 * b;          // padding 4 12, border b
    const double start = r.x() + b + 12 + (inner - (-4 + 20 + 8 + tw)) / 2;   // icon margin 0 8 0 -4
    return {start - 4, r.y() + (r.height() - 20) / 2, 20, 20};
}

ShellMetrics qtShellMetrics() {
    const QFontMetricsF fl(th::font(14, 400)), ft(th::font(13, 500)), fa(th::font(13, 400));
    return {[fl](const QString& s) { return th::textWidth(fl, s, 400); },
            [ft](const QString& s) { return th::textWidth(ft, s, 500); },
            [fa](const QString& s) { return th::textWidth(fa, s, 400); },
            [ft](const QString& s, double w) { return th::elideKeepSpace(s, ft, w, nullptr, 500); }};
}

ShellGeom layoutShell(double panelW, double b, const QStringList& names, int active, double scrollX, const ShellMetrics& m) {
    ShellGeom g;
    g.row = QRectF(8, kRowY, std::max(0.0, panelW - 16), kRowH);
    const double labelW = m.label(kLabel) + 4;   // padding-right 4
    g.label = QRectF(8, kRowY + (kRowH - 22) / 2, labelW, 22);
    g.labelBaseline = g.label.y() + kBlLabel;
    const double cx = g.label.right() + 8;
    g.cluster = QRectF(cx, kRowY, std::max(0.0, g.row.right() - cx), kRowH);
    g.addBtn = QRectF(g.cluster.right() - kAddW, kRowY, kAddW, kRowH);
    g.frame = QRectF(cx, kRowY, std::max(0.0, g.cluster.width() - 8 - kAddW), kRowH);
    g.nextBtn = QRectF(g.addBtn.x() + 2 - kBtn, kRowY, kBtn, kBtn);   // right edge = "Thêm" left + 2
    g.prevBtn = QRectF(g.frame.x(), kRowY, kBtn, kBtn);               // DESIGN §6.1, mirror of ">"
    const double textY = kRowY + (kRowH - kLhTab) / 2;
    g.tabBaseline = textY + kBlTab;
    std::vector<double> widths;
    for (int i = 0; i < names.size(); ++i) widths.push_back(i == active ? 32 + 2 * b + m.tab(names[i]) + 6 + 20 : kTabW);
    for (size_t i = 0; i < widths.size(); ++i) g.contentW += widths[i] + (i ? kTabGap : 0);
    g.maxScroll = std::max(0.0, g.contentW - g.frame.width());
    g.scrollX = std::clamp(scrollX, 0.0, g.maxScroll);
    double x = g.frame.x() - g.scrollX;
    for (int i = 0; i < names.size(); ++i) {
        ShellTabGeom t;
        t.active = i == active;
        t.box = QRectF(x, kRowY, widths[size_t(i)], kRowH);
        if (t.active) {
            t.text = QRectF(x + 16 + b, textY, m.tab(names[i]), kLhTab);   // selected: not cut
            t.shown = names[i];
            g.dropBtn = QRectF(t.text.right() + 6, kRowY + 6, 20, 20);
        } else {
            const double maxW = kTabW - 32 - 2 * b;                          // 86.89 at DPR 1.8
            t.text = QRectF(x + 16 + b, textY, maxW, kLhTab);
            t.shown = m.elideTab(names[i], maxW);
            t.elided = t.shown != names[i];
        }
        g.tabs.push_back(t);
        x += widths[size_t(i)] + kTabGap;
    }
    g.showNext = g.scrollX < g.maxScroll - 0.5;
    g.showPrev = g.scrollX > 0.5;
    // "+ Thêm": padding 4 5, flex centre of [icon margin -2..8] + text, overflowing the 64 px box (UI §1.2 #7)
    const double cluster = -2 + 18 + 8 + m.add(kAdd);
    const double start = g.addBtn.x() + 5 + ((kAddW - 10) - cluster) / 2;
    g.addIcon = QRectF(start - 2, kRowY + (kRowH - 18) / 2, 18, 18);
    g.addTextX = g.addIcon.right() + 8;
    g.addBaseline = kRowY + (kRowH - kLhBtn) / 2 + kBlBtn;
    return g;
}

// ---- WdcShell ----------------------------------------------------------------------------------------

WdcShell::WdcShell(QWidget* parent) : QWidget(parent), metrics_(qtShellMetrics()) {
    setMouseTracking(true);
    setFocusPolicy(Qt::TabFocus);
    setAttribute(Qt::WA_OpaquePaintEvent);
    tipTimer_.setSingleShot(true);
    tipTimer_.setInterval(th::kTitleTipDelayMs);
    connect(&tipTimer_, &QTimer::timeout, this, [this] {
        if (hover_.part == Part::Add) emit tipRequested(kWave2, geom().addBtn);
    });
}

void WdcShell::setTabs(const QStringList& ids, const QStringList& names) {
    ids_ = ids;
    names_ = names;
    active_ = std::min<int>(active_, int(ids_.size()) - 1);
    focus_ = -1;
    update();
}

void WdcShell::setActive(const QString& id) {
    active_ = int(ids_.indexOf(id));
    focus_ = -1;   // keyboard navigation restarts from the active tab (it may have been -1: chart page open)
    setScrollX(scrollX_);
}

void WdcShell::refreshMetrics() {
    metrics_ = qtShellMetrics();
    setScrollX(scrollX_);
}

ShellGeom WdcShell::geom() const { return layoutShell(width(), th::hairline(wdcshell_dpr(this)), names_, active_, scrollX_, metrics_); }

void WdcShell::setScrollX(double x) {
    scrollX_ = layoutShell(width(), th::hairline(wdcshell_dpr(this)), names_, active_, x, metrics_).scrollX;
    update();
}

void WdcShell::scrollNext() {   // reveal the first tab cut by the ">" button
    const ShellGeom g = geom();
    for (const ShellTabGeom& t : g.tabs)
        if (t.box.right() > g.nextBtn.x() + 0.5) { setScrollX(scrollX_ + (t.box.right() - g.nextBtn.x())); return; }
}

void WdcShell::scrollPrev() {   // reveal the last tab cut by the "<" button
    const ShellGeom g = geom();
    for (auto it = g.tabs.rbegin(); it != g.tabs.rend(); ++it)
        if (it->box.x() < g.prevBtn.right() - 0.5) { setScrollX(scrollX_ - (g.prevBtn.right() - it->box.x())); return; }
}

void WdcShell::ensureTabVisible(int i) {
    const ShellGeom g = geom();
    if (i < 0 || i >= int(g.tabs.size())) return;
    const QRectF b = g.tabs[size_t(i)].box;
    if (b.x() < g.frame.x()) setScrollX(scrollX_ - (g.frame.x() - b.x()));
    else if (b.right() > g.frame.right()) setScrollX(scrollX_ + (b.right() - g.frame.right()));
}

WdcShell::HitRes WdcShell::hitAt(const QPointF& p) const {
    const ShellGeom g = geom();
    if (g.showNext && g.nextBtn.contains(p)) return {Part::Next, -1};
    if (g.showPrev && g.prevBtn.contains(p)) return {Part::Prev, -1};
    if (g.addBtn.contains(p)) return {Part::Add, -1};
    if (!g.frame.contains(p)) return {};
    if (active_ >= 0 && g.dropBtn.contains(p)) return {Part::Drop, active_};
    for (size_t i = 0; i < g.tabs.size(); ++i)
        if (g.tabs[i].box.contains(p)) return {Part::Tab, int(i)};
    return {};
}

void WdcShell::paintEvent(QPaintEvent*) {
    QPainter g(this);
    g.setRenderHint(QPainter::Antialiasing);
    g.setRenderHint(QPainter::TextAntialiasing);
    g.fillRect(rect(), wdcshell_c(th::kBgSurface));
    const double dpr = wdcshell_dpr(this);
    const ShellGeom s = geom();
    g.setFont(th::font(14, 400));
    g.setPen(wdcshell_c(th::kTextPrimary));
    th::drawWebText(g, QPointF(s.label.x(), s.labelBaseline), kLabel, 400);

    g.save();
    g.setClipRect(s.frame);
    g.setFont(th::font(13, 500));
    for (size_t i = 0; i < s.tabs.size(); ++i) {
        const ShellTabGeom& t = s.tabs[i];
        if (t.box.right() < s.frame.x() || t.box.x() > s.frame.right()) continue;
        paintHairlineBox(g, t.box, 4, wdcshell_c(t.active ? th::kBgTabActive : th::kBgSurface), wdcshell_c(th::kBorder), dpr);
        g.setPen(wdcshell_c(t.active ? th::kTextPrimary : th::kTextSecondary));
        th::drawWebText(g, QPointF(t.text.x(), s.tabBaseline), t.shown, 500);
        if (t.active) {
            if (hover_.part == Part::Drop) {   // MUI IconButton: round (border-radius 50%)
                g.setPen(Qt::NoPen);
                g.setBrush(kWsDropHover);
                g.drawEllipse(s.dropBtn);
            }
            paintIcon(g, Icon::ArrowDropDown, s.dropBtn, wdcshell_c(th::kTextPrimary));
        }
    }
    g.restore();

    if (hasFocus() && focusVisible_ && focus_ >= 0 && focus_ < int(s.tabs.size())) {   // §6.1 focus ring
        g.setPen(QPen(wdcshell_c(th::kFocusRing), 1));
        g.setBrush(Qt::NoBrush);
        g.drawRoundedRect(s.tabs[size_t(focus_)].box.adjusted(0.5, 0.5, -0.5, -0.5), 4, 4);
    }
    if (s.showPrev) wdcshell_circle_button(g, s.prevBtn, Icon::ChevronLeft, dpr, hover_.part == Part::Prev);
    if (s.showNext) wdcshell_circle_button(g, s.nextBtn, Icon::ChevronRight, dpr, hover_.part == Part::Next);

    const QRgb addColor = hover_.part == Part::Add ? th::kTextPrimary : th::kTextSecondary;
    paintIcon(g, Icon::AddRounded, s.addIcon, wdcshell_c(addColor));
    g.setFont(th::font(13, 400));
    g.setPen(wdcshell_c(addColor));
    th::drawWebText(g, QPointF(s.addTextX, s.addBaseline), kAdd, 400);
}

void WdcShell::mouseMoveEvent(QMouseEvent* e) {
    const HitRes h = hitAt(e->position());
    if (h == hover_) return;
    hover_ = h;
    emit tipHidden();
    if (h.part == Part::Add) tipTimer_.start();
    else tipTimer_.stop();
    setCursor(h.part == Part::None || h.part == Part::Add ? Qt::ArrowCursor : Qt::PointingHandCursor);
    update();
}

void WdcShell::mousePressEvent(QMouseEvent* e) {
    if (e->button() != Qt::LeftButton) return;
    press_ = hitAt(e->position());
    update();
}

void WdcShell::mouseReleaseEvent(QMouseEvent* e) {
    const HitRes h = hitAt(e->position()), p = press_;
    press_ = {};
    update();
    if (e->button() != Qt::LeftButton || !(h == p)) return;
    switch (h.part) {
    case Part::Tab: if (h.index != active_) emit tabActivated(ids_.value(h.index)); break;
    case Part::Drop: emit menuRequested(geom().dropBtn); break;
    case Part::Next: scrollNext(); break;
    case Part::Prev: scrollPrev(); break;
    case Part::Add: tipTimer_.stop(); emit tipRequested(kWave2, geom().addBtn); break;   // "+ Thêm": đợt 2
    case Part::None: break;
    }
}

void WdcShell::leaveEvent(QEvent*) {
    hover_ = {};
    tipTimer_.stop();
    emit tipHidden();
    update();
}

void WdcShell::wheelEvent(QWheelEvent* e) {   // BEH §7.2: the tab strip also scrolls with the wheel
    const QPoint px = e->pixelDelta();
    const double d = !px.isNull() ? (std::abs(px.x()) > std::abs(px.y()) ? px.x() : px.y())
                                  : (e->angleDelta().x() ? e->angleDelta().x() : e->angleDelta().y()) / 120.0 * 100;
    setScrollX(scrollX_ - d);
    e->accept();
}

void WdcShell::keyPressEvent(QKeyEvent* e) {   // Left/Right move the focus ring, Enter/Space select (or open ▾)
    if (ids_.isEmpty()) return QWidget::keyPressEvent(e);
    if (focus_ < 0) focus_ = std::max(0, active_);
    switch (e->key()) {
    case Qt::Key_Left: focus_ = std::max(0, focus_ - 1); break;
    case Qt::Key_Right: focus_ = std::min(int(ids_.size()) - 1, focus_ + 1); break;
    case Qt::Key_Return: case Qt::Key_Enter: case Qt::Key_Space:
        if (focus_ != active_) emit tabActivated(ids_.value(focus_));
        else emit menuRequested(geom().dropBtn);
        break;
    default: return QWidget::keyPressEvent(e);
    }
    focusVisible_ = true;
    ensureTabVisible(focus_);
    update();
}

void WdcShell::focusInEvent(QFocusEvent* e) {
    focusVisible_ = e->reason() == Qt::TabFocusReason || e->reason() == Qt::BacktabFocusReason;
    if (focus_ < 0) focus_ = std::max(0, active_);
    update();
}

void WdcShell::focusOutEvent(QFocusEvent*) {
    focusVisible_ = false;
    update();
}

// ---- WdcContent --------------------------------------------------------------------------------------

WdcContent::WdcContent(QWidget* parent) : QWidget(parent) {
    setMouseTracking(true);
    setAttribute(Qt::WA_OpaquePaintEvent);
    tipTimer_.setSingleShot(true);
    tipTimer_.setInterval(th::kTitleTipDelayMs);
    connect(&tipTimer_, &QTimer::timeout, this, [this] { if (hover_) emit tipRequested(kWave2, page_.addBtn); });
}

void WdcContent::paintEvent(QPaintEvent* e) {
    QPainter g(this);
    g.setRenderHint(QPainter::Antialiasing);
    g.setRenderHint(QPainter::TextAntialiasing);
    g.fillRect(e->rect(), wdcshell_c(th::kBgSurface));
    const double dpr = wdcshell_dpr(this);
    if (!notice_.isEmpty()) {   // no layout at all: DESIGN §8.4 token
        const QFont f = th::font(th::kNeedDataPx, th::kNeedDataWeight);
        g.setFont(f);
        g.setPen(wdcshell_c(th::kNeedDataText));
        const QFontMetricsF fm(f);
        const double w = th::textWidth(fm, notice_, th::kNeedDataWeight);
        th::drawWebText(g, QPointF(kPadX + (page_.gridW - w) / 2, 60 - fm.height() / 2 + fm.ascent()), notice_, th::kNeedDataWeight);
    }
    const QRectF r = page_.addBtn;
    if (r.isEmpty() || !e->rect().intersects(r.toAlignedRect())) return;
    // HOVER_CSS.md: `.css-v0gle5:hover {background: #F0F0F0}` (the last rule wins)
    paintHairlineBox(g, r, 4, wdcshell_c(hover_ ? th::kBgTabActive : th::kBgSubtle), wdcshell_c(th::kBorder), dpr);
    const QRectF icon = addChartIconRect(r, th::hairline(dpr));
    paintIcon(g, Icon::AddRounded, icon, wdcshell_c(th::kTextPrimary));
    g.setFont(th::font(13, 500));
    g.setPen(wdcshell_c(th::kTextPrimary));
    th::drawWebText(g, QPointF(icon.right() + 8, r.y() + (r.height() - kLhBtn) / 2 + kBlBtn), kAddChart, 500);
}

void WdcContent::mouseMoveEvent(QMouseEvent* e) {
    const bool h = page_.addBtn.contains(e->position());
    if (h != hover_) {
        hover_ = h;
        update(page_.addBtn.toAlignedRect().adjusted(-1, -1, 1, 1));
        emit tipHidden();
        if (h) tipTimer_.start();
        else tipTimer_.stop();
    }
    e->ignore();
}

void WdcContent::mousePressEvent(QMouseEvent* e) {
    if (!page_.addBtn.contains(e->position())) return e->ignore();
    tipTimer_.stop();
    emit tipRequested(kWave2, page_.addBtn);   // "+ Thêm biểu đồ": đợt 2
}

void WdcContent::leaveEvent(QEvent*) {
    if (hover_) update(page_.addBtn.toAlignedRect().adjusted(-1, -1, 1, 1));
    hover_ = false;
    tipTimer_.stop();
    emit tipHidden();
}

// ---- WdcPopup: tab menu (popover §6.1) and tips (title-tooltip token §6.1) -----------------------------

WdcPopup::WdcPopup(QWidget* view) : QWidget(view) {
    setMouseTracking(true);
    hide();
}

void WdcPopup::showMenu(const QPointF& at, const std::vector<Item>& items) {
    menu_ = true;
    items_ = items;
    hover_ = -1;
    setAttribute(Qt::WA_TransparentForMouseEvents, false);
    const QFontMetricsF fm(th::font(th::kPopoverPx, 400));
    double w = kMenuMinW;
    for (const Item& it : items_) w = std::max(w, th::textWidth(fm, it.text, 400) + 2 * th::kMenuRowPadX + 2 * th::kPopoverPad);
    const double h = items_.size() * kMenuItemH + 2 * th::kPopoverPad;
    const QWidget* p = parentWidget();
    const double x = std::clamp(at.x(), 8.0, std::max(8.0, p->width() - w - 8));
    box_ = QRectF(x, at.y(), w, h);
    setGeometry(p->rect());   // full-view scrim: a click outside the box closes the menu
    setFocusPolicy(Qt::StrongFocus);
    show();
    raise();
    setFocus(Qt::PopupFocusReason);
    update();
}

void WdcPopup::showTip(const QString& text, const QRectF& anchor) {
    menu_ = false;
    tip_ = text;
    setAttribute(Qt::WA_TransparentForMouseEvents, true);
    const QFontMetricsF fm(th::font(th::kTitleTipPx, 400));
    const double w = th::textWidth(fm, text, 400) + 2 * th::kTitleTipPad, h = std::ceil(fm.height()) + 2 * th::kTitleTipPad;
    const QWidget* p = parentWidget();
    const double x = std::clamp(anchor.center().x() - w / 2, 4.0, std::max(4.0, p->width() - w - 4));
    double y = anchor.bottom() + th::kTitleTipGap;
    if (y + h > p->height()) y = anchor.top() - th::kTitleTipGap - h;
    const QRect geo = QRectF(x, y, w, h).toAlignedRect();
    box_ = QRectF(QPointF(x, y) - geo.topLeft(), QSizeF(w, h));
    setGeometry(geo);
    show();
    raise();
    update();
}

void WdcPopup::dismiss() {
    hide();
    items_.clear();
    menu_ = false;
}

int WdcPopup::itemAt(const QPointF& p) const {
    if (!menu_ || !box_.contains(p)) return -1;
    const int i = int((p.y() - box_.y() - th::kPopoverPad) / kMenuItemH);
    return i >= 0 && i < int(items_.size()) ? i : -1;
}

void WdcPopup::paintEvent(QPaintEvent*) {
    QPainter g(this);
    g.setRenderHint(QPainter::Antialiasing);
    g.setRenderHint(QPainter::TextAntialiasing);
    if (!menu_) {
        g.setPen(Qt::NoPen);
        g.setBrush(wdcshell_c(th::kTitleTipBg));
        g.drawRoundedRect(box_, th::kTitleTipRadius, th::kTitleTipRadius);
        const QFont f = th::font(th::kTitleTipPx, 400);
        g.setFont(f);
        g.setPen(wdcshell_c(th::kTitleTipFg));
        const QFontMetricsF fm(f);
        th::drawWebText(g, QPointF(box_.x() + th::kTitleTipPad, box_.center().y() - fm.height() / 2 + fm.ascent()), tip_, 400);
        return;
    }
    paintPopoverFrame(g, box_, wdcshell_dpr(this));
    g.setFont(th::font(th::kPopoverPx, 400));
    for (int i = 0; i < int(items_.size()); ++i) {
        const QRectF r(box_.x() + th::kPopoverPad, box_.y() + th::kPopoverPad + i * kMenuItemH, box_.width() - 2 * th::kPopoverPad, kMenuItemH);
        const Item& it = items_[size_t(i)];
        if (i == hover_ && it.enabled) {
            g.setPen(Qt::NoPen);
            g.setBrush(wdcshell_c(th::kHoverBg));
            g.drawRoundedRect(r, 4, 4);
        }
        g.setOpacity(it.enabled ? 1.0 : th::kOffOpacity);   // "Đợt 2" items faded
        g.setPen(wdcshell_c(th::kPopoverText));
        th::drawWebText(g, QPointF(r.x() + th::kMenuRowPadX, r.y() + (kMenuItemH - kLhBtn) / 2 + kBlBtn), it.text, 400);
        g.setOpacity(1.0);
    }
}

void WdcPopup::mouseMoveEvent(QMouseEvent* e) {
    const int h = itemAt(e->position());
    if (h != hover_) { hover_ = h; update(); }
}

void WdcPopup::mousePressEvent(QMouseEvent* e) {
    const int i = itemAt(e->position());
    if (i >= 0 && !items_[size_t(i)].enabled) return;   // faded items do nothing
    const QString action = i >= 0 ? items_[size_t(i)].action : QString();
    dismiss();
    if (!action.isEmpty()) emit triggered(action);
}

void WdcPopup::keyPressEvent(QKeyEvent* e) {
    if (e->key() == Qt::Key_Escape) dismiss();
    else QWidget::keyPressEvent(e);
}

} // namespace fincept::screens::wdc
