// src/screens/hdcv_launchpad/HlpDom.cpp
// The public node builder of the Launchpad CSS engine (`N`, element constructors, nd()).
// The engine itself is split by stage — all share the private header HlpDomLayout_p.h:
//   HlpDomStyle.cpp   computed style + box tree (anonymous wrappers, BFC roots)
//   HlpDomInline.cpp  inline formatting context: items, break opportunities, line boxes, baselines
//   HlpDomLayout.cpp  block flow (margin collapsing), flex row, grid, intrinsic sizes, absolute positions
//   HlpDomTable.cpp   auto table layout with collapsed borders
//   HlpDomPaint.cpp   painting (Chrome's pixel snapping), sticky layers
//   HlpView.cpp       HlpView — the `.bd` scroll container widget, hit testing, geometry dump
// Everything follows Blink/LayoutNG on macOS so geometry lands on Chrome's coordinates:
//  - lengths in LayoutUnit (1/128 px here) where Blink truncates: computed line-height = floor(size×lh);
//  - font ascent/descent rounded to 0.5px (detail::vmetrics), half-leading ascent side floored;
//  - text advances from the Chrome-exact shaper (HlpFontShape.cpp, via HlpDomLayout_p.h).
#include "screens/hdcv_launchpad/HlpDom.h"

#include "screens/hdcv_launchpad/HlpDomLayout_p.h"

#include <QApplication>
#include <QCursor>
#include <QFocusEvent>
#include <QKeyEvent>

#include <algorithm>

namespace fincept::screens::hlp {

// ============================================================================================
// N builder
// ============================================================================================
N::N() : p_(std::make_shared<Node>()) {}
N::N(NodeP p) : p_(p ? std::move(p) : std::make_shared<Node>()) {}

N& N::operator<<(const NodeP& child) {
    if (child)
        p_->kids.push_back(child);
    return *this;
}
N& N::operator<<(const N& child) {
    return *this << child.node();
}
N& N::add(const QVector<NodeP>& kids) {
    for (const auto& k : kids)
        if (k)
            p_->kids.push_back(k);
    return *this;
}

N& N::display(Display d) { p_->st.display = d; return *this; }
N& N::inlineBlock() { p_->st.display = Display::InlineBlock; return *this; }
N& N::flex(Justify j, AlignItems a, float gap) {
    p_->st.display = Display::Flex;
    p_->st.justify = j;
    p_->st.alignItems = a;
    p_->st.gap = gap;
    return *this;
}
N& N::wrap() { p_->st.flexWrap = true; return *this; }
N& N::grid(const GridSpec& g) {
    p_->st.display = Display::Grid;
    p_->st.grid = g;
    return *this;
}
N& N::none() { p_->st.display = Display::None; return *this; }

N& N::m(float t, float r, float b, float l) {
    p_->st.mt = t; p_->st.mr = r; p_->st.mb = b; p_->st.ml = l;
    return *this;
}
N& N::mt(float v) { p_->st.mt = v; return *this; }
N& N::mr(float v) { p_->st.mr = v; return *this; }
N& N::mb(float v) { p_->st.mb = v; return *this; }
N& N::ml(float v) { p_->st.ml = v; return *this; }
N& N::mlAuto() { p_->st.mlAuto = true; return *this; }
N& N::p(float all) { return p(all, all, all, all); }
N& N::p(float v, float h) { return p(v, h, v, h); }
N& N::p(float t, float r, float b, float l) {
    p_->st.pt = t; p_->st.pr = r; p_->st.pb = b; p_->st.pl = l;
    return *this;
}
N& N::border(float w, const QColor& c) {
    for (int i = 0; i < 4; ++i) {
        p_->st.bw[i] = w;
        p_->st.bc[i] = c;
    }
    return *this;
}
N& N::bt(float w, const QColor& c) { p_->st.bw[0] = w; p_->st.bc[0] = c; return *this; }
N& N::br(float w, const QColor& c) { p_->st.bw[1] = w; p_->st.bc[1] = c; return *this; }
N& N::bb(float w, const QColor& c) { p_->st.bw[2] = w; p_->st.bc[2] = c; return *this; }
N& N::bl(float w, const QColor& c) { p_->st.bw[3] = w; p_->st.bc[3] = c; return *this; }
N& N::radius(float r) { return radius(r, r, r, r); }
N& N::radius(float tl, float tr, float brr, float bl) {
    p_->st.radius[0] = tl; p_->st.radius[1] = tr; p_->st.radius[2] = brr; p_->st.radius[3] = bl;
    return *this;
}
N& N::bg(const QColor& c) { p_->st.bg = c; return *this; }
N& N::w(float px) { p_->st.width = px; return *this; }
N& N::h(float px) { p_->st.height = px; return *this; }
N& N::minW(float px) { p_->st.minWidth = px; return *this; }
N& N::maxW(float px) { p_->st.maxWidth = px; return *this; }
N& N::maxH(float px) { p_->st.maxHeight = px; return *this; }
N& N::wPct(float pct) { p_->st.widthPct = pct; return *this; }
N& N::opacity(float o) { p_->st.opacity = o; return *this; }
N& N::grow(float g) { p_->st.flexGrow = g; return *this; }
N& N::shrink(float s) { p_->st.flexShrink = s; return *this; }
N& N::alignSelf(AlignItems a) { p_->st.alignSelf = a; return *this; }
N& N::shadowInset(float x, float y, float blur, float spread, const QColor& c) {
    p_->st.boxShadowInset = Style::InsetShadow{x, y, blur, spread, c};
    return *this;
}
N& N::shadowInset(float x, float y, const QColor& c) { return shadowInset(x, y, 0.0f, 0.0f, c); }
N& N::colspan(int n) { p_->st.colspan = std::max(1, n); return *this; }
N& N::head() {
    p_->st.isHead = true;
    p_->st.hoverBg.reset();
    p_->st.pointer = false;
    return *this;
}

N& N::sans(float px, int weight) {
    p_->st.monoFamily = false;
    p_->st.arialFamily = false;
    p_->st.fontSize = px;
    p_->st.weight = weight;
    return *this;
}
N& N::mono() {
    p_->st.monoFamily = true;
    p_->st.arialFamily = false;
    p_->st.tabularNums = true;
    return *this;
}
N& N::mono(float px, int weight) {
    mono();
    p_->st.fontSize = px;
    p_->st.weight = weight;
    return *this;
}
N& N::arial(float px, int weight) {
    p_->st.arialFamily = true;
    p_->st.monoFamily = false;
    p_->st.fontSize = px;
    p_->st.weight = weight;
    return *this;
}
N& N::size(float px) { p_->st.fontSize = px; return *this; }
N& N::weight(int w) { p_->st.weight = w; return *this; }
N& N::bold() { p_->st.weight = 700; return *this; }
N& N::semibold() { p_->st.weight = 600; return *this; }
N& N::italic(bool on) { p_->st.italic = on; return *this; }
N& N::ls(float em) { p_->st.letterSpacingEm = em; return *this; }
N& N::upper() { p_->st.upper = true; return *this; }
N& N::c(const QColor& col) { p_->st.color = col; return *this; }
N& N::lh(float px) {
    p_->st.lineHeightPx = px;
    p_->st.lineHeightFactor.reset();
    p_->st.lineHeightNormal.reset();
    return *this;
}
N& N::lhf(float factor) {
    p_->st.lineHeightFactor = factor;
    p_->st.lineHeightPx.reset();
    p_->st.lineHeightNormal.reset();
    return *this;
}
N& N::lhNormal() {
    p_->st.lineHeightNormal = true;
    p_->st.lineHeightPx.reset();
    p_->st.lineHeightFactor.reset();
    return *this;
}
N& N::nowrap() { p_->st.whiteSpace = WhiteSpace::NoWrap; return *this; }
N& N::normalWrap() { p_->st.whiteSpace = WhiteSpace::Normal; return *this; }
N& N::right() { p_->st.textAlign = TextAlign::Right; return *this; }
N& N::left() { p_->st.textAlign = TextAlign::Left; return *this; }
N& N::center() { p_->st.textAlign = TextAlign::Center; return *this; }
N& N::tabnum() { p_->st.tabularNums = true; return *this; }

N& N::underline() { p_->st.underline = true; return *this; }
N& N::clamp(int lines) { p_->st.lineClamp = std::max(0, lines); return *this; }
N& N::ellipsis() { p_->st.ellipsis = true; return *this; }
N& N::sticky(float top) {
    p_->st.sticky = true;
    p_->st.stickyTop = top;
    return *this;
}

N& N::click(std::function<void()> fn) { p_->onClick = std::move(fn); return *this; }
N& N::link(const QString& href) {
    // UA/page CSS for <a>: a{color:var(--cyan);text-decoration:none} a:hover{text-decoration:underline}
    p_->href = href;
    if (!p_->st.color)
        p_->st.color = pal().cyan;
    p_->st.hoverUnderline = true;
    p_->st.pointer = true;
    return *this;
}
N& N::tip(const QString& t) { p_->tip = t; return *this; }
N& N::key(const QString& k) { p_->key = k; return *this; }
N& N::hoverBg(const QColor& c) { p_->st.hoverBg = c; return *this; }
N& N::hoverColor(const QColor& c) { p_->st.hoverColor = c; return *this; }
N& N::hoverBorder(const QColor& c) { p_->st.hoverBorderColor = c; return *this; }
N& N::hoverUnderline() { p_->st.hoverUnderline = true; return *this; }
N& N::pointer() { p_->st.pointer = true; return *this; }
N& N::focusable(const QColor& ring) { p_->focusable = true; p_->focusRing = ring; return *this; }

N& N::custom(std::function<float(float)> height, std::function<void(QPainter&, const QRectF&)> paint) {
    p_->customHeight = std::move(height);
    p_->customPaint = std::move(paint);
    return *this;
}
N& N::onHover(std::function<void(QPointF, bool)> fn) { p_->customHover = std::move(fn); return *this; }
N& N::onCustomClick(std::function<bool(QPointF)> fn) { p_->customClick = std::move(fn); return *this; }
N& N::customTip(std::function<QString(QPointF)> fn) { p_->customTip = std::move(fn); return *this; }
N& N::customPointer(std::function<bool(QPointF)> fn) { p_->customPointer = std::move(fn); return *this; }
N& N::customText(const QString& t) { p_->customText = t; return *this; }
N& N::widget(QWidget* w) { p_->widget = w; return *this; }

// ---- element constructors ----
N div() {
    return N();
}
N span() {
    N n;
    n->st.display = Display::Inline;
    return n;
}
N span(const QString& text) {
    N n = span();
    n->text = text;
    return n;
}
N text(const QString& t) {
    // A bare DOM text node. It differs from span(t) only inside flex/grid containers, where every
    // element becomes its own item but consecutive text nodes share one anonymous item.
    N n = span(t);
    n->textNode = true;
    return n;
}
N brk() {
    N n = span();
    n->br = true;
    return n;
}
N table() {
    // index.html: table{width:100%;border-collapse:collapse;font-size:11px}
    N n;
    n->st.display = Display::Table;
    n->st.widthPct = 100.0f;
    n->st.fontSize = 11.0f;
    return n;
}
N tr() {
    // tbody tr{cursor:pointer} tbody tr:hover{background:var(--panel-hd)} (thead rows: call head())
    N n;
    n->st.display = Display::TableRow;
    n->st.pointer = true;
    n->st.hoverBg = pal().panelHd;
    return n;
}
N td() {
    // td{padding:2.5px 5px;border-bottom:1px solid var(--line);white-space:nowrap}
    N n;
    n->st.display = Display::TableCell;
    n->st.pt = n->st.pb = 2.5f;
    n->st.pl = n->st.pr = 5.0f;
    n->st.bw[2] = 1.0f;
    n->st.bc[2] = pal().line;
    n->st.whiteSpace = WhiteSpace::NoWrap;
    return n;
}
N th() {
    // th{text-align:left;font:600 9.5px/1.6 var(--sans);letter-spacing:.06em;color:var(--ink-3);
    //    text-transform:uppercase;padding:2px 5px;position:sticky;top:-8px;background:var(--panel);
    //    border-bottom:1px solid var(--line)}
    N n;
    n->st.display = Display::TableCell;
    n->st.textAlign = TextAlign::Left;
    n->st.monoFamily = false;
    n->st.fontSize = 9.5f;
    n->st.weight = 600;
    n->st.lineHeightFactor = 1.6f;
    n->st.letterSpacingEm = 0.06f;
    n->st.color = pal().ink3;
    n->st.upper = true;
    n->st.pt = n->st.pb = 2.0f;
    n->st.pl = n->st.pr = 5.0f;
    n->st.sticky = true;
    n->st.stickyTop = -8.0f;
    n->st.bg = pal().panel;
    n->st.bw[2] = 1.0f;
    n->st.bc[2] = pal().line;
    return n;
}

NodeP nd(const QString& textOverride) {
    // <span class="nd">[CẦN DATA]</span> — .nd{color:var(--ink-3);font-style:italic;font-size:10px}
    N n = span(textOverride.isEmpty() ? QStringLiteral("[CẦN DATA]") : textOverride);
    n->st.color = pal().ink3;
    n->st.italic = true;
    n->st.fontSize = 10.0f;
    return n;
}

// ---------------------------------------------------------------------------------------------
// keyboard focus (tabindex="0" nodes): document-order Tab stops inside one view, Enter / Space →
// onClick, :focus-visible ring only after keyboard interaction (painted in ViewImpl::paintBox)
// ---------------------------------------------------------------------------------------------
namespace hlpdom {

QVector<Box*> ViewImpl::focusables() const {
    QVector<Box*> out;
    if (!doc)
        return out;
    for (const Box& b : doc->boxes)
        if (b.node && b.node->focusable && b.kind != BK::Text && (out.isEmpty() || out.last()->node != b.node))
            out.push_back(const_cast<Box*>(&b));
    return out;
}

void ViewImpl::focusBox(Box* b, bool visible) {
    focusNode = b ? b->node : nullptr;
    focusVisible = b && visible;
    if (b && visible) { // scrollIntoView(nearest)
        if (b->ay < scrollY)
            scrollY = b->ay;
        else if (b->ay + b->h > scrollY + portH())
            scrollY = b->ay + b->h - portH();
        clampScroll();
        placeWidgets();
    }
    q->update();
}

} // namespace hlpdom

void HlpView::syncHover() {
    if (!d_->doc || !isVisible())
        return;
    const QPoint g = QCursor::pos();
    QWidget* under = QApplication::widgetAt(g);
    QVector<hlpdom::Box*> chain;
    if (under == this || isAncestorOf(under))
        chain = d_->chainAt(mapFromGlobal(QPointF(g)));
    if (chain != d_->hover) {
        d_->hover = chain;
        update();
    }
}

void HlpView::keyPressEvent(QKeyEvent* e) {
    const int k = e->key();
    if (d_->focusNode && d_->focusNode->onClick && (k == Qt::Key_Return || k == Qt::Key_Enter || k == Qt::Key_Space)) {
        d_->focusVisible = true;
        const auto fn = d_->focusNode->onClick; // may re-render this view
        fn();
        update();
        e->accept();
        return;
    }
    QWidget::keyPressEvent(e);
}

void HlpView::focusInEvent(QFocusEvent* e) {
    QWidget::focusInEvent(e);
    const QVector<hlpdom::Box*> f = d_->focusables();
    if (!f.isEmpty() && e->reason() == Qt::TabFocusReason)
        d_->focusBox(f.first(), true);
    else if (!f.isEmpty() && e->reason() == Qt::BacktabFocusReason)
        d_->focusBox(f.last(), true);
    update();
}

void HlpView::focusOutEvent(QFocusEvent* e) {
    QWidget::focusOutEvent(e);
    update();
}

bool HlpView::focusNextPrevChild(bool next) {
    if (hasFocus()) {
        const QVector<hlpdom::Box*> f = d_->focusables();
        int i = -1;
        for (int j = 0; j < f.size(); ++j)
            if (f[j]->node == d_->focusNode)
                i = j;
        const int j = next ? i + 1 : (i < 0 ? int(f.size()) - 1 : i - 1);
        if (j >= 0 && j < f.size()) {
            d_->focusBox(f[j], true);
            return true;
        }
        d_->focusBox(nullptr, false);
    }
    return QWidget::focusNextPrevChild(next);
}

} // namespace fincept::screens::hlp
