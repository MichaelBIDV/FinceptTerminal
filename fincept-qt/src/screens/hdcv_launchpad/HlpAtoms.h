// src/screens/hdcv_launchpad/HlpAtoms.h
// The Launchpad's CSS classes (index.html <style> "content atoms", after design_system.css) as node
// factories. Each function returns a node pre-styled EXACTLY like the class; panel code then adds
// the inline `style="…"` overrides that panels.js writes. Names follow the class names so a
// template like
//     <div class="row"><span class="k">% trên MA50</span><span class="v">32.7%</span></div>
// becomes
//     row() << k("% trên MA50") << v() << text("32.7%")
// Colours are read from pal() at call time — rebuild the tree after a theme toggle.
#pragma once

#include "screens/hdcv_launchpad/HlpDom.h"

namespace fincept::screens::hlp::atoms {

// ---- text-level classes ----
N lbl(const QString& s = {});      ///< .lbl  600 9px/1.4 sans · ls .09em · ink3 · uppercase (block)
N big(const QString& s = {});      ///< .big  700 21px/1.1 mono · ls -.01em (block)
N monoS(const QString& s = {});    ///< .mono (span): mono family + tabular-nums
N monoD(const QString& s = {});    ///< .mono (div)
N tk(const QString& s = {});       ///< .tk   700 11px mono · amber (span)
N ndS(const QString& s = {});      ///< .nd   ink3 italic 10px (span); text defaults to "[CẦN DATA]"
N ndD(const QString& s = {});      ///< .nd as a div
N up(const QString& s);            ///< .up   color up
N down(const QString& s);          ///< .down color down
N flat(const QString& s);          ///< .flat color flat
N zCheap(const QString& s);        ///< .z-cheap  cheap, 600
N zRich(const QString& s);         ///< .z-rich   rich, 600
N zNeu(const QString& s);          ///< .z-neu    neutral
/// zcls(z): !z → z-neu · /RẺ/ → z-cheap · /ĐẮT/ → z-rich · else z-neu
N zSpan(const QString& zone);
N link(const QString& s, const QString& href); ///< <a>: cyan, underline on hover
N b(const QString& s);             ///< <b> (700, inherits colour)
N code(const QString& s);          ///< <code>: UA `monospace` → Menlo at the parent's font size (dump: 10px inside a 10px .note)

/// .tag — inline-block, padding 0 5px, radius 2px, 600 9px/15px sans, ls .05em, 1px border in
/// currentColor, uppercase. `col` = the inline `style="color:…"` panels.js sets.
N tag(const QString& s, const QColor& col);

// ---- block classes ----
N row();                           ///< .row  flex space-between, gap 8px, padding 2.5px 0, border-bottom 1px line, 11px (last-child: no border — call lastRow() on the final one)
N lastRow(N r);                    ///< drop the bottom border (CSS .row:last-child)
N k(const QString& s = {});        ///< .k   ink2, flex-shrink 0
N v();                             ///< .v   mono, text-align right
N item();                          ///< .item padding 4.5px 0, border-bottom 1px line (last-child: none)
N lastItem(N it);
N t();                             ///< .item .t  11px/1.35, display block
N tLink(const QString& s, const QString& href); ///< <a class="t" …> block link
N m();                             ///< .item .m  9.5px mono ink3, margin-top 2px
N tiles();                         ///< .tiles grid auto-fit minmax(88px,1fr), gap 7px
N tile(bool hot = false);          ///< .tile padding 6px 8px, bg2, radius r, border-left 2px line2 (hot: amber)
N chips();                         ///< .chips flex wrap, gap 3px, margin-bottom 6px
/// .chip button; pressed = aria-pressed=true (amber bg, black 600 text). onClick required.
N chip(const QString& s, bool pressed, std::function<void()> onClick);
N warn();                          ///< .warn padding 5px 8px, down 12% bg, border-left 2px down, radius 0 r r 0, 10.5px, mb 6px
N warnCyan();                      ///< .warn with the inline cyan override (cyan 10% bg, cyan border) used by songuon / xanhvo
N note();                          ///< .note 10px/1.45 ink3, mt 6px, pt 5px, border-top 1px line
N bandbar();                       ///< .bandbar container (use charts::sigmaBar instead)

// ---- tables ----
/// <table> width 100%, border-collapse collapse, 11px. Column layout: CSS auto table layout.
N tbl();
N thead(std::initializer_list<NodeP> cells); ///< header row (isHead) of th cells
N thC(const QString& s, bool numeric = false); ///< th (600 9.5px/1.6, ls .06em, ink3, uppercase, padding 2px 5px, border-bottom 1px line, sticky top -8px, bg panel). `numeric` only tags the class "n" for the dump — CSS has no th.n rule, so th stays LEFT-aligned like in Chrome
N trow(bool selected = false);     ///< tbody tr: cursor pointer, hover bg panel-hd, .sel bg amber 14%
N tdC();                           ///< td padding 2.5px 5px, border-bottom 1px line, white-space nowrap
N tdN();                           ///< td.n  right, mono, tabular
N tdTk(const QString& s);          ///< <td class="tk">

// ---- the `.f` filter input: a real QLineEdit styled like input.f (created by the panel, kept alive) ----
/// Returns the node that hosts `edit` (100% width, margin-bottom 5px, height 21.5px measured).
N filterInput(QWidget* edit);

} // namespace fincept::screens::hlp::atoms
