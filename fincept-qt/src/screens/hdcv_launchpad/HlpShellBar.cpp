// src/screens/hdcv_launchpad/HlpShellBar.cpp
// HĐCV LAUNCHPAD shell — the #bar of index.html (brand · view tabs · MÃ input · GO · + Component ·
// Lưu View · Mặc định · ◐) and the form controls: input#tick, input.f and <select>. The bar is a node
// tree rendered by HlpView (the panel-body CSS engine), so metrics, letter-spacing and hover colours
// match Chrome; the controls are real widgets (typing, focus, popups) whose frame is painted here
// antialiased with CSS radius clamping — the widget-level stylesheet beats the app QSS.
// See HlpShell_p.h for how the shell is split.
#include "screens/hdcv_launchpad/HlpShell_p.h"

#include "screens/hdcv_launchpad/HlpTheme.h"

#include <QDateTime>
#include <QGuiApplication>
#include <QInputDialog>
#include <QInputMethodEvent>
#include <QPainter>
#include <QStyleHints>

#include <algorithm>
#include <cmath>

namespace fincept::screens::hlp {

namespace {

/// QSS colour literal (#AARRGGBB — unambiguous alpha, unlike rgba() with a fractional alpha).
QString hlpshbar_qss(const QColor& c) {
    return c.name(QColor::HexArgb);
}

/// macOS text-selection colour Chrome uses in form controls.
QColor hlpshbar_selectionBg() {
    return is_dark() ? QColor(0x3f, 0x63, 0x8b) : QColor(0xb3, 0xd7, 0xff);
}

/// Chrome's ::placeholder colour (#757575, measured in ref2).
const QColor hlpshbar_kPlaceholder(0x75, 0x75, 0x75);

/// The control's CSS border box in its own coordinates: the engine's snapped box ("hlp_box", may be
/// fractional — HlpView gives self-painting controls the covering pixels) or the widget rect.
QRectF hlpshbar_box(const QWidget* w) {
    const QRectF r = w->property("hlp_box").toRectF();
    return r.isValid() ? r : QRectF(w->rect());
}

} // namespace

namespace shell_detail {

// =================================================================================================
// Form controls
// =================================================================================================

hlpsh_EngineEdit::hlpsh_EngineEdit(QWidget* parent) : QLineEdit(parent) {
    blink_.setInterval(std::max(1, QGuiApplication::styleHints()->cursorFlashTime() / 2));
    QObject::connect(&blink_, &QTimer::timeout, this, [this] {
        caretOn_ = !caretOn_;
        update();
    });
    QObject::connect(this, &QLineEdit::cursorPositionChanged, this, [this] { restartBlink(); });
    QObject::connect(this, &QLineEdit::selectionChanged, this, [this] { update(); });
}

void hlpsh_EngineEdit::restartBlink() {
    caretOn_ = true;
    if (hasFocus() && QGuiApplication::styleHints()->cursorFlashTime() > 0)
        blink_.start();
    update();
}

void hlpsh_EngineEdit::focusInEvent(QFocusEvent* e) {
    QLineEdit::focusInEvent(e);
    restartBlink();
}

void hlpsh_EngineEdit::focusOutEvent(QFocusEvent* e) {
    QLineEdit::focusOutEvent(e);
    blink_.stop();
    composing_ = false;
    update();
}

void hlpsh_EngineEdit::inputMethodEvent(QInputMethodEvent* e) {
    composing_ = !e->preeditString().isEmpty();
    QLineEdit::inputMethodEvent(e);
    update();
}

/// The text as Chrome draws an input's inner editor: the engine's shaper (same glyphs/advances as the
/// page text) from the content edge, baseline on the pixel grid (half-pixel snap of the snapped box,
/// round half up); selection behind it, a 1px caret in the text colour (caret-color: auto).
bool hlpsh_EngineEdit::paintContent(QPainter& p, float padX, float padY, float px, int weight, const QColor& color) {
    if (composing_)
        return false;
    const bool ph = text().isEmpty();
    const QString s = ph ? placeholderText() : text();
    const QRectF box = hlpshbar_box(this);
    if (!s.isEmpty() && textWidth(s, true, px, weight) > float(box.width()) - 2.0f - 2.0f * padX)
        return false;
    const TextVMetrics vm = textVMetrics(true, px, weight);
    // x: the inner editor at its LAYOUT position (#tick at 1601.3 → text at 1610.3 → glyphs on the
    // quarter 1610.25, measured with quarter-pixel glyphs); y: from the snapped box as before
    const QRectF css = property("hlp_css").toRectF();
    const double x0 = (css.isValid() ? css.left() : box.left()) + 1.0 + double(padX);
    const double top = box.top() + 1.0 + double(padY) + double(vm.ascent);
    const double base = std::floor(std::floor(top * 2.0 + 0.5) / 2.0 + 0.5);
    const auto xAt = [&](int i) { return x0 + double(textWidth(text().left(i), true, px, weight)); };
    // The inner editor clips at the content box, snapped to the half-pixel grid, and Skia multiplies
    // the glyph coverage by the antialiased clip (#tick "M" at 1610: stem 40% × clip 50% = 20%) —
    // draw on a device-aligned layer, then scale the edge columns by the clip coverage.
    QImage layer(size(), QImage::Format_ARGB32_Premultiplied);
    layer.fill(Qt::transparent);
    {
        QPainter lp(&layer);
        if (!ph && hasSelectedText()) {
            const int a = selectionStart(), b = a + int(selectedText().size());
            lp.fillRect(QRectF(xAt(a), base - vm.ascent, xAt(b) - xAt(a), double(vm.ascent + vm.descent)),
                        hlpshbar_selectionBg());
        }
        if (!s.isEmpty())
            drawText(lp, QPointF(x0, base), s, true, px, weight, ph ? hlpshbar_kPlaceholder : color);
        if (hasFocus() && !isReadOnly() && caretOn_ && !hasSelectedText()) {
            const double cx = std::floor(ph ? x0 : xAt(cursorPosition()));
            lp.fillRect(QRectF(cx, base - vm.ascent, 1.0, double(vm.ascent + vm.descent)), color);
        }
    }
    const double x1 = (css.isValid() ? css.right() : box.right()) - 1.0 - double(padX);
    const double cl = std::floor(x0 * 2.0 + 0.5) / 2.0, cr = std::floor(x1 * 2.0 + 0.5) / 2.0;
    // …and vertically at the same content box: the grave on "ề"/"ồ" of the reports placeholder rises
    // above it and Chrome cuts it at the content top (input 775.09 + 1 + 3 → row 779; rows 777–778
    // show nothing — beri THƯ VIỆN BÁO CÁO, measured 27/09)
    const QRectF vb = css.isValid() ? css : box;
    const double y0 = vb.top() + 1.0 + double(padY), y1 = vb.bottom() - 1.0 - double(padY);
    const double ct = std::floor(y0 * 2.0 + 0.5) / 2.0, cb = std::floor(y1 * 2.0 + 0.5) / 2.0;
    for (int y = 0; y < layer.height(); ++y) {
        QRgb* row = reinterpret_cast<QRgb*>(layer.scanLine(y));
        const double fy = std::clamp(std::min(y + 1.0, cb) - std::max(double(y), ct), 0.0, 1.0);
        for (int x = 0; x < layer.width(); ++x) {
            const double f = fy * std::clamp(std::min(x + 1.0, cr) - std::max(double(x), cl), 0.0, 1.0);
            if (f >= 1.0 || !row[x])
                continue;
            const auto m = [f](int v) { return int(std::lround(v * f)); };
            row[x] = qRgba(m(qRed(row[x])), m(qGreen(row[x])), m(qBlue(row[x])), m(qAlpha(row[x])));
        }
    }
    p.drawImage(QPoint(0, 0), layer);
    return true;
}

hlpsh_TickEdit::hlpsh_TickEdit(QWidget* parent) : hlpsh_EngineEdit(parent) {
    setProperty("hlp_role", QStringLiteral("tick"));
    setProperty("hlp_paintsFrame", true); // HlpView hands over the fractional box (hlp_box)
    setMaxLength(8);
    setPlaceholderText(QStringLiteral("VCB"));
    setAccessibleName(QStringLiteral("Mã chứng khoán liên kết"));
    setFrame(false);
    setAttribute(Qt::WA_MacShowFocusRect, false);
    QObject::connect(this, &QLineEdit::textEdited, this, [this](const QString& s) {
        // text-transform:uppercase — what the user types shows (and is used) in capitals
        const QString u = s.toUpper();
        if (u == s)
            return;
        const int c = cursorPosition();
        setText(u);
        setCursorPosition(c);
    });
    restyle();
}

void hlpsh_TickEdit::focusInEvent(QFocusEvent* e) {
    hlpsh_EngineEdit::focusInEvent(e);
    if (onFocusChange)
        onFocusChange(); // input#tick:focus → border amber (the bar node's style)
}

void hlpsh_TickEdit::focusOutEvent(QFocusEvent* e) {
    hlpsh_EngineEdit::focusOutEvent(e);
    if (onFocusChange)
        onFocusChange();
}

void hlpsh_TickEdit::restyle() {
    const Palette& P = pal();
    // padding: CSS 1px border + 8px padding − QLineEdit's own 2px text margin
    setStyleSheet(QStringLiteral("QLineEdit{background:transparent;border:none;margin:0px;padding:0px 7px;"
                                 "color:%1;font-family:\"%2\";font-size:12px;font-weight:600;"
                                 "selection-background-color:%3;selection-color:%1;"
                                 "placeholder-text-color:%4;}")
                      .arg(hlpshbar_qss(P.amber), mono(12, 600).family(), hlpshbar_qss(hlpshbar_selectionBg()),
                           hlpshbar_qss(hlpshbar_kPlaceholder)));
    update();
}

void hlpsh_TickEdit::paintEvent(QPaintEvent* e) {
    {
        // the frame (bg, border, radius) is the bar node's CSS box, painted by HlpView in DOM order —
        // #go, the next sibling, paints over the border it shares a pixel column with (1697)
        QPainter p(this);
        p.setRenderHint(QPainter::Antialiasing);
        // padding 4px 8px, mono 600 12px, amber — focused or not, like the page
        if (paintContent(p, 8.0f, 4.0f, 12.0f, 600, pal().amber))
            return;
    }
    QLineEdit::paintEvent(e);
}

hlpsh_FieldEdit::hlpsh_FieldEdit(QWidget* parent) : hlpsh_EngineEdit(parent) {
    setProperty("hlp_paintsFrame", true); // atoms::filterInput must not restyle this field
    setFrame(false);
    setAttribute(Qt::WA_MacShowFocusRect, false);
    const Palette& P = pal();
    setStyleSheet(QStringLiteral("QLineEdit{background:transparent;border:none;margin:0px;padding:0px 6px;"
                                 "color:%1;font-family:\"%2\";font-size:11px;font-weight:400;"
                                 "selection-background-color:%3;selection-color:%1;"
                                 "placeholder-text-color:%4;}")
                      .arg(hlpshbar_qss(P.ink), mono(11).family(), hlpshbar_qss(hlpshbar_selectionBg()),
                           hlpshbar_qss(hlpshbar_kPlaceholder)));
}

void hlpsh_FieldEdit::paintEvent(QPaintEvent* e) {
    {
        QPainter p(this);
        p.setRenderHint(QPainter::Antialiasing);
        const QRectF box = hlpshbar_box(this);
        hlpsh_box(p, box, hlpsh_all(hlpsh_kRadius), pal().bg2, hasFocus() ? pal().amberDim : pal().line2);
        // padding 3px 7px, mono 11px, ink — focused or not, like the page
        if (paintContent(p, 7.0f, 3.0f, 11.0f, 400, pal().ink))
            return;
    }
    QLineEdit::paintEvent(e);
}

QComboBox* hlpsh_makeSelect(QWidget* parent) {
    auto* c = new QComboBox(parent);
    const Palette& P = pal();
    c->setStyleSheet(QStringLiteral("QComboBox{background-color:%1;color:%2;border:1px solid %3;border-radius:9px;"
                                    "padding:2px 5px 2px 8px;font-family:Arial;font-size:11px;font-weight:400;}"
                                    "QComboBox::drop-down{border:none;width:16px;}"
                                    "QComboBox QAbstractItemView{background-color:%4;color:%2;border:1px solid %3;"
                                    "outline:0;selection-background-color:%5;selection-color:%2;}")
                         .arg(hlpshbar_qss(P.bg2), hlpshbar_qss(P.ink), hlpshbar_qss(P.line2), hlpshbar_qss(P.panel),
                              hlpshbar_qss(P.panelHd)));
    return c;
}

} // namespace shell_detail

using namespace shell_detail;

// =================================================================================================
// #bar — tabs() + the static header markup
// =================================================================================================

void Shell::Impl::renderBar() {
    const Palette& P = pal();
    const QColor clear(0, 0, 0, 0);
    N root = div();
    root.flex(Justify::Start, AlignItems::Center, 10).h(hlpsh_kBarH).p(0, 10).bg(P.bg2).bb(1, P.line2).key(
        QStringLiteral("bar"));

    N brand = div();
    brand.sans(11, 700).ls(0.06f).c(P.amber).nowrap().key(QStringLiteral("brand"));
    brand << text(hlpsh_brand());
    root << brand;

    // #views — empty when launchpad_data.json failed (index.html never reached render()/tabs()).
    N nav = div();
    nav.flex(Justify::Start, AlignItems::Stretch, 2).key(QStringLiteral("views"));
    if (dataOk) {
        for (const hlpsh_View& v : views) {
            const bool sel = v.key == view;
            const QColor bc = sel ? P.line2 : clear;
            N t = div();
            t.p(4, 11).radius(hlpsh_kRadius, hlpsh_kRadius, 0, 0).size(11).bt(1, bc).bl(1, bc).br(1, bc).pointer();
            t.key(QStringLiteral("vtab:") + v.key);
            if (sel)
                t.bg(P.panel).c(P.amber).weight(600);
            else
                t.c(P.ink2).hoverColor(P.ink);
            const QString key = v.key;
            t.click([this, key] { defer([this, key] { q->setView(key); }); });
            t << text(v.name);
            nav << t;
        }
    }
    root << nav;

    N cx = div();
    cx.flex(Justify::Start, AlignItems::Center, 0).mlAuto().key(QStringLiteral("ctx"));
    N lab = div(); // <label for="tick">
    lab.size(10).c(P.ink3).ls(0.08f).mr(6).key(QStringLiteral("label"));
    lab.click([this] { tick->setFocus(Qt::OtherFocusReason); }); // no select-all, like label activation
    lab << text(QStringLiteral("MÃ"));
    N tk = div(); // input#tick: the box is painted here (before #go), the widget paints the text
    tk.widget(tick).w(96).h(24).key(QStringLiteral("tick"));
    tk.bg(is_dark() ? QColor(0, 0, 0) : QColor(0xff, 0xfb, 0xf2))
        .border(1, tick->hasFocus() ? P.amber : P.amberDim)
        .radius(hlpsh_kRadius, 0, 0, hlpsh_kRadius);
    N go = div();
    go.p(4, 9).bg(P.amber).radius(0, hlpsh_kRadius, hlpsh_kRadius, 0).sans(10, 700).lhf(1.4f).ls(0.05f);
    go.c(QColor(0, 0, 0)).pointer().key(QStringLiteral("go"));
    go.click([this] { defer([this] { q->setCtx(tick->text()); }); });
    go << text(QStringLiteral("GO"));
    cx << lab << tk << go;

    const auto tbtn = [&](const QString& key, const QString& label, std::function<void()> fn) {
        N b = div();
        b.p(4, 9).border(1, P.line2).radius(hlpsh_kRadius).size(10.5f).c(P.ink2);
        b.hoverBorder(P.amberDim).hoverColor(P.amber).pointer().key(key);
        b.click([this, fn = std::move(fn)] { defer(fn); });
        b << text(label);
        return b;
    };
    N add = tbtn(QStringLiteral("add"), QStringLiteral("+ Component"), [this] { openSheet(); });
    add.ml(8);
    N theme = tbtn(QStringLiteral("theme"), QStringLiteral("◐"), [this] { q->setDark(!is_dark()); });
    theme.tip(QStringLiteral("Sáng/tối"));
    cx << add << tbtn(QStringLiteral("save"), QStringLiteral("Lưu View"), [this] { saveViewPrompt(); })
       << tbtn(QStringLiteral("reset"), QStringLiteral("Mặc định"), [this] { q->resetDefaults(true); }) << theme;
    root << cx;

    bar->setRoot(root, false);
}

// ---- "Lưu View" ----
void Shell::Impl::saveViewPrompt() {
    bool ok = false;
    const QString n =
        QInputDialog::getText(dialogParent(), QStringLiteral("HĐCV Launchpad"),
                              QStringLiteral("Tên view mới (để trống = ghi đè view đang mở):"), QLineEdit::Normal,
                              QString(), &ok);
    if (ok && !n.isEmpty()) {
        const QString k = QStringLiteral("v") + QString::number(QDateTime::currentMSecsSinceEpoch());
        const hlpsh_View* v = cur();
        hlpsh_View nv{k, n, v ? v->panels : QVector<hlpsh_PanelSpec>{}};
        views.push_back(nv);
        view = k;
    }
    saveState();
    render();
}

} // namespace fincept::screens::hlp
