// src/screens/hdcv_launchpad/HlpAtoms.cpp
// The Launchpad's content classes (index.html "content atoms" + design_system.css --r:14px) as node
// factories. Every value is the computed style Chrome reports for the class (SPEC §3,
// ref/*_dump.json). Remember the CSS `font:` shorthand resets line-height to `normal`: that is why
// .tk / .m / .item .m use lhNormal() while .mono keeps the inherited 1.45.
// Each node gets `key` = its class name so geometry dumps line up with the Chrome dump.
#include "screens/hdcv_launchpad/HlpAtoms.h"

#include <QLineEdit>
#include <QPalette>

namespace fincept::screens::hlp::atoms {

namespace {

N hlpat_withText(N n, const QString& s) {
    if (!s.isEmpty())
        n << text(s);
    return n;
}

} // namespace

// ---- text-level classes ----------------------------------------------------------------------
N lbl(const QString& s) {
    // .lbl{font:600 9px/1.4 var(--sans);letter-spacing:.09em;color:var(--ink-3);text-transform:uppercase}
    N n = div();
    n.sans(9.0f, 600).lhf(1.4f).ls(0.09f).c(pal().ink3).upper().key("lbl");
    return hlpat_withText(n, s);
}

N big(const QString& s) {
    // .big{font:700 21px/1.1 var(--mono);letter-spacing:-.01em}
    N n = div();
    n.mono(21.0f, 700).lhf(1.1f).ls(-0.01f).key("big");
    return hlpat_withText(n, s);
}

N monoS(const QString& s) {
    // .mono{font-family:var(--mono);font-variant-numeric:tabular-nums}
    N n = span();
    n.mono().key("mono");
    return hlpat_withText(n, s);
}

N monoD(const QString& s) {
    N n = div();
    n.mono().key("mono");
    return hlpat_withText(n, s);
}

N tk(const QString& s) {
    // .tk{font:700 11px var(--mono);color:var(--amber)}
    N n = span();
    n.mono(11.0f, 700).lhNormal().c(pal().amber).key("tk");
    return hlpat_withText(n, s);
}

N ndS(const QString& s) {
    N n = span();
    n.c(pal().ink3).italic().size(10.0f).key("nd");
    return hlpat_withText(n, s.isEmpty() ? QStringLiteral("[CẦN DATA]") : s);
}

N ndD(const QString& s) {
    N n = div();
    n.c(pal().ink3).italic().size(10.0f).key("nd");
    return hlpat_withText(n, s.isEmpty() ? QStringLiteral("[CẦN DATA]") : s);
}

N up(const QString& s) {
    N n = span(s);
    n.c(pal().up).key("up");
    return n;
}

N down(const QString& s) {
    N n = span(s);
    n.c(pal().down).key("down");
    return n;
}

N flat(const QString& s) {
    N n = span(s);
    n.c(pal().flat).key("flat");
    return n;
}

N zCheap(const QString& s) {
    N n = span(s);
    n.c(pal().cheap).semibold().key("z-cheap");
    return n;
}

N zRich(const QString& s) {
    N n = span(s);
    n.c(pal().rich).semibold().key("z-rich");
    return n;
}

N zNeu(const QString& s) {
    N n = span(s);
    n.c(pal().neutral).key("z-neu");
    return n;
}

N zSpan(const QString& zone) {
    // zcls: !z → z-neu · /RẺ/ → z-cheap · /ĐẮT/ → z-rich · else z-neu
    if (zone.isEmpty())
        return zNeu(zone);
    if (zone.contains(QStringLiteral("RẺ")))
        return zCheap(zone);
    if (zone.contains(QStringLiteral("ĐẮT")))
        return zRich(zone);
    return zNeu(zone);
}

N link(const QString& s, const QString& href) {
    N n = span(s);
    n.link(href).key("a");
    return n;
}

N b(const QString& s) {
    N n = span(s);
    n.bold().key("b");
    return n;
}

N code(const QString& s) {
    // UA code{font-family:monospace} → Menlo at the parent's size
    N n = span(s);
    n.mono().key("code");
    n->st.tabularNums.reset();
    return n;
}

N tag(const QString& s, const QColor& col) {
    // .tag{display:inline-block;padding:0 5px;border-radius:2px;font:600 9px/15px var(--sans);
    //      letter-spacing:.05em;border:1px solid currentColor;text-transform:uppercase}
    N n = span();
    n.inlineBlock().p(0.0f, 5.0f).radius(2.0f).sans(9.0f, 600).lh(15.0f).ls(0.05f).upper().c(col).key("tag");
    n.border(1.0f, QColor()); // invalid colour = currentColor
    return hlpat_withText(n, s);
}

// ---- block classes ---------------------------------------------------------------------------
N row() {
    // .row{display:flex;justify-content:space-between;gap:8px;padding:2.5px 0;
    //      border-bottom:1px solid var(--line);font-size:11px}
    N n = div();
    n.flex(Justify::SpaceBetween, AlignItems::Stretch, 8.0f).p(2.5f, 0.0f).bb(1.0f, pal().line).size(11.0f).key("row");
    return n;
}

N lastRow(N r) {
    r->st.bw[2] = 0.0f;
    return r;
}

N k(const QString& s) {
    // .k{color:var(--ink-2);flex-shrink:0}
    N n = span();
    n.c(pal().ink2).shrink(0.0f).key("k");
    return hlpat_withText(n, s);
}

N v() {
    // .v{font-family:var(--mono);text-align:right}
    N n = span();
    n.mono().right().key("v");
    n->st.tabularNums.reset();
    return n;
}

N item() {
    // .item{padding:4.5px 0;border-bottom:1px solid var(--line)}
    N n = div();
    n.p(4.5f, 0.0f).bb(1.0f, pal().line).key("item");
    return n;
}

N lastItem(N it) {
    it->st.bw[2] = 0.0f;
    return it;
}

N t() {
    // .item .t{font-size:11px;line-height:1.35;display:block}
    N n = div();
    n.size(11.0f).lhf(1.35f).key("t");
    return n;
}

N tLink(const QString& s, const QString& href) {
    N n = t();
    n.link(href).key("a.t");
    return hlpat_withText(n, s);
}

N m() {
    // .item .m{font:9.5px var(--mono);color:var(--ink-3);margin-top:2px}
    N n = div();
    n.mono(9.5f, 400).lhNormal().c(pal().ink3).mt(2.0f).key("m");
    n->st.tabularNums.reset();
    return n;
}

N tiles() {
    // .tiles{display:grid;grid-template-columns:repeat(auto-fit,minmax(88px,1fr));gap:7px}
    GridSpec g;
    g.autoFitMin = 88.0f;
    g.colGap = 7.0f;
    g.rowGap = 7.0f;
    N n = div();
    n.grid(g).key("tiles");
    return n;
}

N tile(bool hot) {
    // .tile{padding:6px 8px;background:var(--bg-2);border-radius:var(--r);border-left:2px solid var(--line-2)}
    N n = div();
    n.p(6.0f, 8.0f).bg(pal().bg2).radius(kRadius).bl(2.0f, hot ? pal().amber : pal().line2).key(hot ? "tile.hot" : "tile");
    return n;
}

N chips() {
    // .chips{display:flex;flex-wrap:wrap;gap:3px;margin-bottom:6px}
    N n = div();
    n.flex(Justify::Start, AlignItems::Stretch, 3.0f).wrap().mb(6.0f).key("chips");
    return n;
}

N chip(const QString& s, bool pressed, std::function<void()> onClick) {
    // .chip{padding:1.5px 7px;border:1px solid var(--line-2);border-radius:9px;font-size:9.5px;color:var(--ink-2)}
    // .chip:hover{border-color:var(--amber-dim);color:var(--amber)}
    // .chip[aria-pressed="true"]{background:var(--amber);color:#000;border-color:var(--amber);font-weight:600}
    N n = span();
    n.inlineBlock().p(1.5f, 7.0f).border(1.0f, pal().line2).radius(9.0f).size(9.5f).c(pal().ink2).pointer();
    if (pressed) {
        n.bg(pal().amber).c(QColor(0, 0, 0)).border(1.0f, pal().amber).semibold().key("chip[pressed]");
    } else {
        n.hoverBorder(pal().amberDim).hoverColor(pal().amber).key("chip");
    }
    n.center(); // UA button{text-align:center}
    if (onClick)
        n.click(std::move(onClick));
    return hlpat_withText(n, s);
}

N warn() {
    // .warn{padding:5px 8px;background:color-mix(in oklab,var(--down) 12%,transparent);
    //       border-left:2px solid var(--down);border-radius:0 var(--r) var(--r) 0;font-size:10.5px;margin-bottom:6px}
    N n = div();
    n.p(5.0f, 8.0f).bg(mixT(pal().down, 12.0f)).bl(2.0f, pal().down).radius(0.0f, kRadius, kRadius, 0.0f).size(10.5f).mb(6.0f).key("warn");
    return n;
}

N warnCyan() {
    // style="background:color-mix(in oklab,var(--cyan) 10%,transparent);border-left-color:var(--cyan)"
    N n = warn();
    n.bg(mixT(pal().cyan, 10.0f)).bl(2.0f, pal().cyan);
    return n;
}

N note() {
    // .note{font-size:10px;color:var(--ink-3);line-height:1.45;margin-top:6px;padding-top:5px;border-top:1px solid var(--line)}
    N n = div();
    n.size(10.0f).c(pal().ink3).lhf(1.45f).mt(6.0f).bt(1.0f, pal().line);
    n->st.pt = 5.0f;
    n.key("note");
    return n;
}

N bandbar() {
    // .bandbar{position:relative;height:20px;background:var(--bg-2);border-radius:2px;margin:5px 0 2px}
    N n = div();
    n.h(20.0f).bg(pal().bg2).radius(2.0f).m(5.0f, 0.0f, 2.0f, 0.0f).key("bandbar");
    return n;
}

// ---- tables ----------------------------------------------------------------------------------
N tbl() {
    N n = table();
    n.key("table");
    return n;
}

N thead(std::initializer_list<NodeP> cells) {
    N r = tr();
    r.head().key("tr");
    for (const NodeP& c : cells)
        r << c;
    return r;
}

N thC(const QString& s, bool numeric) {
    N n = th();
    n.key(numeric ? "th.n" : "th");
    return hlpat_withText(n, s);
}

N trow(bool selected) {
    N n = tr();
    if (selected) {
        // tbody tr.sel{background:color-mix(in oklab,var(--amber) 14%,transparent)} (wins over :hover)
        n.bg(mixT(pal().amber, 14.0f)).key("tr.sel");
        n->st.hoverBg.reset();
    } else {
        n.key("tr");
    }
    return n;
}

N tdC() {
    N n = td();
    n.key("td");
    return n;
}

N tdN() {
    // td.n{text-align:right;font-family:var(--mono);font-variant-numeric:tabular-nums}
    N n = td();
    n.right().mono().key("td.n");
    return n;
}

N tdTk(const QString& s) {
    // <td class="tk"> — .tk{font:700 11px var(--mono);color:var(--amber)}
    N n = td();
    n.mono(11.0f, 700).lhNormal().c(pal().amber).key("td.tk");
    return hlpat_withText(n, s);
}

// ---- input.f ---------------------------------------------------------------------------------
N filterInput(QWidget* edit) {
    // input.f{width:100%;padding:3px 7px;background:var(--bg-2);border:1px solid var(--line-2);
    //         color:var(--ink);border-radius:var(--r);font-size:11px;margin-bottom:5px;font-family:var(--mono)}
    // Height in Chrome: Menlo 11px normal line (12.5) + 2×3 padding + 2×1 border = 20.5px.
    // The shell's rc.lineEdit() field paints input.f itself (radius clamped like CSS); a QSS
    // border-radius of 14px on a 20px-high QLineEdit is dropped by Qt and draws square corners.
    auto* le = qobject_cast<QLineEdit*>(edit);
    if (le && !le->property("hlp_paintsFrame").toBool()) {
        const Palette& p = pal();
        le->setFont(hlp::mono(11.0f));
        le->setFrame(false);
        le->setAttribute(Qt::WA_MacShowFocusRect, false);
        le->setStyleSheet(QStringLiteral("QLineEdit{background:%1;border:1px solid %2;border-radius:%3px;color:%4;"
                                         "padding:2px 6px;selection-background-color:%5;}"
                                         "QLineEdit:focus{border:1px solid %6;}")
                              .arg(css(p.bg2), css(p.line2))
                              .arg(int(kRadius))
                              .arg(css(p.ink), css(mixT(p.amber, 35.0f)), css(p.amberDim)));
        QPalette pl = le->palette();
        pl.setColor(QPalette::PlaceholderText, QColor(0x75, 0x75, 0x75));
        pl.setColor(QPalette::Text, p.ink);
        le->setPalette(pl);
    }
    N n = div();
    n.widget(edit).h(20.5f).mb(5.0f).key("input.f");
    return n;
}

} // namespace fincept::screens::hlp::atoms
