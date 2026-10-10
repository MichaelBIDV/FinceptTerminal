// src/screens/hdcv_launchpad/HlpShell.cpp
// HĐCV LAUNCHPAD shell — native clone of the chrome of _System/launchpad/index.html: the #bar (brand ·
// view tabs · MÃ input · GO · + Component · Lưu View · Mặc định · ◐), the 12-column #grid of .pnl frames
// (header .hd + body .bd), the add-component #sheet, and the page script (boot / tabs / render / panel /
// setCtx / sheet / save / reset / theme / keyboard) 1:1 — see SPEC §2 and §6.
//
// This file is the core: Impl construction and teardown, view/state lookups, persistence (boot / save /
// theme / reset), the 60 s data poll, and the public Shell API (activate, setView, setCtx, setDark,
// resetDefaults, keyboard). The rest of the shell is split by responsibility — see HlpShell_p.h.
//
// Rendering split:
//  - #bar, .hd and the sheet content are node trees rendered by HlpView (the same CSS engine as the panel
//    bodies), so text metrics, letter-spacing, ellipsis, hover colours and tooltips match Chrome exactly.
//  - Grid geometry, frames and the overlay scrollbar: HlpShellGrid.cpp.
//
// State = the web's localStorage value ({views, view, ctx}) plus the theme under "_t" (web: LS+'_t'),
// stored as JSON in AppDataLocation/hdcv_launchpad.json ($HDCV_LP_STATE overrides; setStatePath() for
// tests).
#include "screens/hdcv_launchpad/HlpShell_p.h"

#include "screens/hdcv_launchpad/HlpTheme.h"

#include <QApplication>
#include <QDesktopServices>
#include <QDir>
#include <QFile>
#include <QFileInfo>
#include <QJsonDocument>
#include <QKeyEvent>
#include <QMessageBox>
#include <QRegularExpression>
#include <QSaveFile>
#include <QStandardPaths>
#include <QUrl>

namespace fincept::screens::hlp {

namespace shell_detail {

const QString& hlpsh_brand() {
    static const QString s = QStringLiteral("◤ HĐCV LAUNCHPAD");
    return s;
}

void hlpsh_mark(QWidget* w) {
    w->setObjectName(QStringLiteral("hlpshW"));
}

void hlpsh_openUrl(const QString& url) {
    static const QRegularExpression re(QStringLiteral("^https?://"), QRegularExpression::CaseInsensitiveOption);
    if (re.match(url).hasMatch())
        QDesktopServices::openUrl(QUrl(url));
}

} // namespace shell_detail

using namespace shell_detail;

namespace {

/// index.html DEFAULTS, restricted to the three Fincept dashboards (SPEC §6).
QVector<hlpsh_View> hlpshcore_defaults() {
    const auto P = [](const char* id, int w, int h) { return hlpsh_PanelSpec{QString::fromLatin1(id), w, h}; };
    return {
        {QStringLiteral("ck"),
         QStringLiteral("Chứng khoán · Mã & Danh mục"),
         {P("cong", 3, 264), P("idx", 5, 264), P("desc", 4, 264), P("monitor", 5, 360), P("sigma", 7, 360),
          P("chart", 5, 290), P("news", 4, 290), P("alerts", 3, 290), P("songuon", 12, 420)}},
        {QStringLiteral("vimo"),
         QStringLiteral("VĨ MÔ · 4 chủ thể"),
         {P("dongho", 5, 400), P("idx", 4, 400), P("cong", 3, 400), P("chinhphu", 7, 400), P("sgitin", 5, 400),
          P("fftma", 6, 380), P("sigma", 6, 380), P("news", 7, 320), P("rasoat", 5, 320), P("wdsignal", 12, 600)}},
        {QStringLiteral("widata"),
         QStringLiteral("WIDATA · Tín hiệu"),
         {P("wdsignal", 12, 640), P("dongho", 4, 360), P("cpicanh", 4, 360), P("chinhphu", 4, 360)}},
    };
}

QVector<hlpsh_PanelSpec> hlpshcore_parsePanels(const QJsonArray& arr) {
    QVector<hlpsh_PanelSpec> out;
    for (const QJsonValue& v : arr) {
        const QJsonObject o = v.toObject();
        const QString id = o.value(QStringLiteral("id")).toString();
        if (id.isEmpty())
            continue;
        out.push_back({id, int(o.value(QStringLiteral("w")).toDouble(4)), int(o.value(QStringLiteral("h")).toDouble(300))});
    }
    return out;
}

QString hlpshcore_defaultStatePath() {
    const QString env = qEnvironmentVariable("HDCV_LP_STATE");
    if (!env.isEmpty())
        return env;
    return QStandardPaths::writableLocation(QStandardPaths::AppDataLocation) + QStringLiteral("/hdcv_launchpad.json");
}

/// Panels whose web render() reads a file other than launchpad_data.json (D). Every panel is redrawn
/// when D changes; wdsignal follows its own rule (cap_nhat), see Impl::pollData().
bool hlpshcore_affected(const QString& id, const QStringList& keys) {
    if (keys.contains(QLatin1String("D")))
        return true;
    static const QHash<QString, QString> own{
        {QStringLiteral("dongho"), QStringLiteral("vimo")},   {QStringLiteral("chinhphu"), QStringLiteral("vimo")},
        {QStringLiteral("fftma"), QStringLiteral("vimo")},    {QStringLiteral("cpicanh"), QStringLiteral("tien")},
        {QStringLiteral("alerts"), QStringLiteral("alerts")}, {QStringLiteral("sgitin"), QStringLiteral("sgi")},
        {QStringLiteral("vietcapma"), QStringLiteral("vcma")}, {QStringLiteral("vietcaptin"), QStringLiteral("vctin")},
    };
    const auto it = own.constFind(id);
    return it != own.constEnd() && keys.contains(it.value());
}

} // namespace

// =================================================================================================
// Shell::Impl — construction, lookups, persistence, poll
// =================================================================================================

void Shell::Impl::build() {
    store = new DataStore(q);
    statePath = hlpshcore_defaultStatePath();

    backdrop = new hlpsh_GridContent(q); // first child = bottom of the z-order
    bar = new HlpView(q);
    bar->setProperty("hlp_role", QStringLiteral("bar"));
    bar->setMaxContentHeight(0);
    tick = new hlpsh_TickEdit(bar);
    QObject::connect(tick, &QLineEdit::returnPressed, q, [this] { q->setCtx(tick->text()); });
    tick->onFocusChange = [this] { defer([this] { renderBar(); }); };

    grid = new hlpsh_GridVp(q);
    grid->onResized = [this] { relayoutSoon(); };

    sheet = new hlpsh_Sheet(q);
    sheet->onClose = [this] { closeSheet(); };
    sheet->hide();

    poll = new QTimer(q);
    poll->setInterval(hlpsh_kPollMs);
    QObject::connect(poll, &QTimer::timeout, q, [this] {
        if (q->isVisible())
            pollData();
    });
    autoScroll = new QTimer(q);
    autoScroll->setInterval(hlpsh_kAutoScrollMs);
    QObject::connect(autoScroll, &QTimer::timeout, q, [this] { dragAutoTick(); });

    backdrop->show();
    bar->show();
    grid->show();
    syncChrome();
}

void Shell::Impl::shutdown() {
    dying = true;
    poll->stop();
    autoScroll->stop();
    qDeleteAll(frames);
    frames.clear();
    delete sheet;
    delete grid;
    delete bar;
    delete backdrop;
    backdrop = nullptr;
    sheet = nullptr;
    grid = nullptr;
    bar = nullptr;
    tick = nullptr;
}

void Shell::Impl::defer(std::function<void()> fn) {
    QTimer::singleShot(0, q, [this, fn = std::move(fn)] {
        if (!dying)
            fn();
    });
}

void Shell::Impl::syncChrome() {
    const int W = q->width(), H = q->height();
    backdrop->setGeometry(0, 0, W, H);
    bar->setGeometry(0, 0, W, int(hlpsh_kBarH));
    grid->setGeometry(0, int(hlpsh_kBarH), W, std::max(0, H - int(hlpsh_kBarH)));
    sheet->setGeometry(0, 0, W, H);
}

hlpsh_View* Shell::Impl::cur() {
    for (hlpsh_View& v : views)
        if (v.key == view)
            return &v;
    return nullptr;
}

int Shell::Impl::indexOfView(const QString& key) const {
    for (int i = 0; i < views.size(); ++i)
        if (views[i].key == key)
            return i;
    return -1;
}

hlpsh_Frame* Shell::Impl::frameByUid(quint64 uid) const {
    for (hlpsh_Frame* f : frames)
        if (f->uid == uid)
            return f;
    return nullptr;
}

// ---- persistence (localStorage LS = 'hdcv_launchpad_v2' and LS+'_t') ----
QJsonObject Shell::Impl::readState() const {
    if (statePath.isEmpty())
        return {};
    QFile f(statePath);
    if (!f.open(QIODevice::ReadOnly))
        return {};
    const QJsonDocument d = QJsonDocument::fromJson(f.readAll());
    return d.isObject() ? d.object() : QJsonObject();
}

void Shell::Impl::writeState(const QJsonObject& o) const {
    if (statePath.isEmpty())
        return;
    QDir().mkpath(QFileInfo(statePath).absolutePath());
    QSaveFile f(statePath);
    if (!f.open(QIODevice::WriteOnly))
        return; // web: try{…}catch(e){} — persistence failures are silent
    f.write(QJsonDocument(o).toJson(QJsonDocument::Compact));
    f.commit();
}
/// save(): localStorage[LS] = {views, view, ctx}; the theme key is left as it is.
void Shell::Impl::saveState() const {
    QJsonObject vs;
    for (const hlpsh_View& v : views) {
        QJsonArray ps;
        for (const hlpsh_PanelSpec& p : v.panels)
            ps.append(QJsonObject{{QStringLiteral("id"), p.id}, {QStringLiteral("w"), p.w}, {QStringLiteral("h"), p.h}});
        vs.insert(v.key, QJsonObject{{QStringLiteral("name"), v.name}, {QStringLiteral("panels"), ps}});
    }
    QJsonObject o = readState();
    o.insert(QStringLiteral("views"), vs);
    o.insert(QStringLiteral("view"), view);
    o.insert(QStringLiteral("ctx"), ctx);
    writeState(o);
}

void Shell::Impl::saveTheme() const {
    QJsonObject o = readState();
    o.insert(QStringLiteral("_t"), is_dark() ? QStringLiteral("dark") : QStringLiteral("light"));
    writeState(o);
}
/// localStorage.removeItem(LS) — the theme survives.
void Shell::Impl::removeState() const {
    const QJsonObject old = readState();
    QJsonObject o;
    if (old.contains(QStringLiteral("_t")))
        o.insert(QStringLiteral("_t"), old.value(QStringLiteral("_t")));
    writeState(o);
}

/// boot(state): DEFAULTS, saved views override (defaults keep their tab slot, new keys append),
/// saved view if it still exists else 'ck', ctx or 'VCB'.
void Shell::Impl::boot(const QJsonObject* st) {
    views = hlpshcore_defaults();
    if (st) {
        const QJsonObject sv = st->value(QStringLiteral("views")).toObject();
        // QJsonObject iterates keys sorted; saved-view keys 'v<ms>' therefore stay chronological.
        for (auto it = sv.constBegin(); it != sv.constEnd(); ++it) {
            if (!it.value().isObject())
                continue;
            const QJsonObject vo = it.value().toObject();
            hlpsh_View v{it.key(), vo.value(QStringLiteral("name")).toString(),
                         hlpshcore_parsePanels(vo.value(QStringLiteral("panels")).toArray())};
            const int i = indexOfView(it.key());
            if (i >= 0)
                views[i] = v;
            else
                views.push_back(v);
        }
    }
    const QString sview = st ? st->value(QStringLiteral("view")).toString() : QString();
    view = (!sview.isEmpty() && indexOfView(sview) >= 0) ? sview : QStringLiteral("ck");
    const QString sctx = st ? st->value(QStringLiteral("ctx")).toString() : QString();
    ctx = sctx.isEmpty() ? QStringLiteral("VCB") : sctx;
}

void Shell::Impl::bootFromFile() {
    const QJsonObject st = readState();
    set_dark(st.value(QStringLiteral("_t")).toString() != QLatin1String("light"));
    tick->restyle();
    const bool has = st.contains(QStringLiteral("views")) || st.contains(QStringLiteral("view")) ||
                     st.contains(QStringLiteral("ctx"));
    boot(has ? &st : nullptr);
}

// ---- data poll (the web has none except wdsignal's 5′ re-fetch; SPEC §6) ----
void Shell::Impl::pollData() {
    if (!booted || dying)
        return;
    const QStringList keys = store->reloadChanged();
    const bool nowOk = store->data().dOk;
    if (nowOk != dataOk) {
        dataOk = nowOk;
        render();
        return;
    }
    if (!dataOk)
        return;
    bool redrawn = false;
    for (hlpsh_Frame* f : frames) {
        if (!f->def)
            continue;
        if (f->def->id == QLatin1String("wdsignal")) {
            if (!keys.contains(QLatin1String("wd")) && !f->wdPending)
                continue;
            // web: redraw only when cap_nhat changed; postpone while focus is inside the panel
            if (store->data().wd.value(QStringLiteral("cap_nhat")) == f->wdVer) {
                f->wdPending = false;
                continue;
            }
            const QWidget* fw = QApplication::focusWidget();
            if (fw && fw != f->body && f->body->isAncestorOf(fw)) {
                f->wdPending = true;
                continue;
            }
            f->wdPending = false;
            renderBody(f, true, false);
            redrawn = true;
        } else if (hlpshcore_affected(f->def->id, keys)) {
            renderBody(f, true, false);
            redrawn = true;
        }
    }
    if (redrawn)
        layoutGrid();
}

QWidget* Shell::Impl::dialogParent() const {
    QWidget* w = q->window();
    return w != q ? w : nullptr; // not the shell itself: its stylesheet is for its own widgets
}

// =================================================================================================
// Shell
// =================================================================================================

Shell::Shell(QWidget* parent) : QWidget(parent), d_(std::make_unique<Impl>(this)) {
    setObjectName(QStringLiteral("hdcvLaunchpadShell"));
    setFocusPolicy(Qt::ClickFocus); // so "/" and Esc reach keyPressEvent after a click anywhere
    // The app QSS paints `QWidget{background}` on plain QWidget subclasses; ours paint themselves.
    setStyleSheet(QStringLiteral("QWidget#hlpshW{background:transparent;border:none;}"));
    d_->build();
}

Shell::~Shell() {
    d_->shutdown();
}

void Shell::activate() {
    if (d_->booted) {
        d_->pollData();
        return;
    }
    d_->booted = true;
    d_->syncChrome();
    d_->bootFromFile();
    d_->dataOk = d_->store->loadAll();
    d_->render();
    d_->poll->start();
    // Web: nothing is focused after load. Without a focus widget, activating the window would hand
    // focus to the first tab-focusable child (#tick: amber ring + caret). Only when the window has no
    // focus yet — never steal it from the rest of the app.
    if (QWidget* w = window(); w && !w->focusWidget())
        setFocus(Qt::OtherFocusReason);
}

QStringList Shell::viewKeys() const {
    QStringList out;
    for (const hlpsh_View& v : d_->views)
        out << v.key;
    return out;
}

QString Shell::currentView() const {
    return d_->view;
}

void Shell::setView(const QString& key) {
    if (d_->indexOfView(key) < 0)
        return;
    d_->view = key;
    d_->saveState();
    d_->render();
}

QString Shell::ctx() const {
    return d_->ctx;
}

void Shell::setCtx(const QString& ticker) {
    d_->setCtx(ticker);
}

bool Shell::dark() const {
    return is_dark();
}

void Shell::setDark(bool dark) {
    set_dark(dark);
    d_->saveTheme();
    d_->tick->restyle();
    d_->render();
    if (d_->sheet->isVisible())
        d_->openSheet();
}

void Shell::resetDefaults(bool askConfirm) {
    if (askConfirm &&
        QMessageBox::question(d_->dialogParent(), QStringLiteral("HĐCV Launchpad"),
                              QStringLiteral("Trả mọi view về mặc định? Các view tự tạo sẽ mất."),
                              QMessageBox::Ok | QMessageBox::Cancel, QMessageBox::Ok) != QMessageBox::Ok)
        return;
    d_->removeState();
    d_->boot(nullptr);
    d_->render();
}

void Shell::setStatePath(const QString& path) {
    d_->statePath = path;
    if (!d_->booted)
        return;
    d_->bootFromFile();
    d_->render();
}


DataStore* Shell::store() const {
    return d_->store;
}

void Shell::keyPressEvent(QKeyEvent* e) {
    if (e->key() == Qt::Key_Escape && d_->sheet->isVisible()) {
        d_->closeSheet();
        e->accept();
        return;
    }
    // "/" outside an input focuses #tick (a focused QLineEdit consumes the key before it gets here)
    if (e->text() == QLatin1String("/")) {
        d_->tick->setFocus(Qt::OtherFocusReason); // tick.focus(): no select-all
        e->accept();
        return;
    }
    QWidget::keyPressEvent(e);
}

void Shell::resizeEvent(QResizeEvent* e) {
    QWidget::resizeEvent(e);
    d_->syncChrome();
    if (d_->sheet->isVisible())
        d_->sheet->relayout();
    d_->layoutGrid();
}

} // namespace fincept::screens::hlp
