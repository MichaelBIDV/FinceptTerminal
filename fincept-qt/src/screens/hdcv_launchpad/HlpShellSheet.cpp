// src/screens/hdcv_launchpad/HlpShellSheet.cpp
// HĐCV LAUNCHPAD shell — the "+ Component" #sheet of index.html: rgba(0,0,0,.66) overlay, centred box
// (min(620px,92vw), max-height 78vh, radius 5, padding 16), h3 + hint + auto-fill grid of component cards
// (panel_defs() order). Card click adds {id, w, h} to the open view; overlay click / Esc closes (SPEC §6).
// See HlpShell_p.h for how the shell is split.
#include "screens/hdcv_launchpad/HlpShell_p.h"

#include "screens/hdcv_launchpad/HlpTheme.h"

#include <QKeyEvent>
#include <QMouseEvent>
#include <QPainter>

#include <cmath>

namespace fincept::screens::hlp {

namespace shell_detail {

hlpsh_Sheet::hlpsh_Sheet(QWidget* parent) : QWidget(parent) {
    hlpsh_mark(this);
    setProperty("hlp_role", QStringLiteral("sheet"));
    setFocusPolicy(Qt::StrongFocus);
    view = new HlpView(this);
    view->show();
}

void hlpsh_Sheet::relayout() {
    const float W = float(width()), H = float(height());
    const float bw = std::min(620.0f, 0.92f * W);
    view->setMaxContentHeight(std::max(0.0f, 0.78f * H - 2.0f)); // border-box max-height minus border
    const float bh = view->preferredHeight(bw - 2.0f) + 2.0f;
    box = QRectF((W - bw) / 2.0f, (H - bh) / 2.0f, bw, bh);
    hlpsh_place(view, box.adjusted(1, 1, -1, -1));
    update();
}

void hlpsh_Sheet::paintEvent(QPaintEvent*) {
    QPainter p(this);
    p.fillRect(rect(), QColor(0, 0, 0, 168)); // rgba(0,0,0,.66)
    p.setRenderHint(QPainter::Antialiasing);
    // the box is laid out at a fractional y (centred: 642.8 at 2300px) but Chrome paints its background
    // and border on the snapped edges (rows 643 and 1656 fully covered, nothing in 642/1657)
    const auto sn = [](qreal v) { return std::floor(v * 2.0 + 0.5) / 2.0; };
    const QRectF sb(QPointF(sn(box.left()), sn(box.top())), QPointF(sn(box.right()), sn(box.bottom())));
    hlpsh_box(p, sb, hlpsh_all(5.0f), pal().panel, pal().line2);
}

void hlpsh_Sheet::mousePressEvent(QMouseEvent* e) {
    // #sheet.onclick: only a click on the overlay itself (not the box) closes
    if (!box.contains(e->position()) && onClose)
        onClose();
}

void hlpsh_Sheet::keyPressEvent(QKeyEvent* e) {
    if (e->key() == Qt::Key_Escape && onClose) {
        onClose();
        return;
    }
    QWidget::keyPressEvent(e);
}

void hlpsh_Sheet::resizeEvent(QResizeEvent* e) {
    QWidget::resizeEvent(e);
    relayout();
}

} // namespace shell_detail

using namespace shell_detail;

void Shell::Impl::openSheet() {
    const Palette& P = pal();
    N root = div();
    root.p(16);
    N h3 = div();
    h3.sans(13, 700).c(P.amber).ls(0.05f).mb(3);
    h3 << text(QStringLiteral("Thêm component"));
    N para = div();
    para.size(11).c(P.ink3).mb(13);
    para << text(QStringLiteral("Bấm để thêm vào view đang mở. Panel có chấm vàng sẽ đi theo mã ở thanh trên."));
    GridSpec g;
    g.autoFitMin = 178;
    g.colGap = 7;
    g.rowGap = 7;
    N list = div();
    list.grid(g).key(QStringLiteral("cgrid"));
    for (const PanelDef& d : panel_defs()) {
        // <button class="card">: Chrome centres button content vertically → flex + align center
        N card = div();
        card.flex(Justify::Start, AlignItems::Center).p(9, 11).bg(P.bg2).border(1, P.line).radius(hlpsh_kRadius);
        card.hoverBorder(P.amber).pointer().left().key(QStringLiteral("card"));
        N inner = div();
        inner.grow(1).minW(0);
        N b = div();
        b.size(11.5f).bold().c(P.ink).mb(2);
        b << text(d.name);
        N s = span();
        s.size(10).c(P.ink3).lhf(1.4f);
        s << text(d.desc);
        inner << b << s;
        card << inner;
        const QString id = d.id;
        card.click([this, id] { defer([this, id] { addPanel(id); }); });
        list << card;
    }
    root << h3 << para << list;
    sheet->view->setRoot(root, false);
    sheet->setGeometry(q->rect());
    sheet->relayout();
    sheet->show();
    sheet->raise();
    sheet->setFocus();
}

void Shell::Impl::closeSheet() {
    sheet->hide();
    q->setFocus();
    syncHoverSoon(); // the panel under the pointer is hovered again (Blink), no mouse move needed
}

void Shell::Impl::addPanel(const QString& id) {
    const PanelDef* d = panel_def(id);
    hlpsh_View* v = cur();
    if (!d || !v)
        return;
    v->panels.push_back({id, d->w > 0 ? d->w : 4, d->h > 0 ? d->h : 300}); // {id:k, w:C.w||4, h:C.h||300}
    closeSheet();
    saveState();
    render();
}

} // namespace fincept::screens::hlp
