// ChbView.cpp — scrolling page widget over the chaebol_map engine (see ChbView.h). File-local helpers: chbv_.
#include "screens/chaebol_map/ChbView.h"

#include "screens/chaebol_map/ChbDom.h"
#include "screens/chaebol_map/ChbFonts.h"

#include <QAction>
#include <QDesktopServices>
#include <QDir>
#include <QFile>
#include <QFileInfo>
#include <QJsonArray>
#include <QJsonDocument>
#include <QJsonParseError>
#include <QKeyEvent>
#include <QMenu>
#include <QMouseEvent>
#include <QPainter>
#include <QPaintEvent>
#include <QPointer>
#include <QScrollBar>
#include <QUrl>
#include <QWheelEvent>

#include <algorithm>
#include <cmath>
#include <vector>

namespace fincept::screens::chb {

namespace {

constexpr QLatin1StringView kChbvSchema{"chaebol_map/1"};
const QColor kChbvCanvas(0x0a, 0x0a, 0x0c);          ///< body background of the page (before the first layout)
constexpr int kChbvRefViewportH = 1000;               ///< ref/*.png viewport height (ref/README §1)
constexpr int kChbvBarPx = 8;                         ///< overlay scrollbar thickness
constexpr int kChbvLineStepPx = 40;                   ///< arrow keys / QScrollBar single step
constexpr double kChbvWheelNotchPx = 100.0;           ///< one 120-unit wheel notch without pixel delta
constexpr double kChbvProbeStepPx = 6.0;              ///< hit-test probe spacing when locating a button
constexpr int kChbvNearProbes = 12;                   ///< probes from the right edge of a flush-right button
constexpr qint64 kChbvMaxFileBytes = 64ll * 1024 * 1024; ///< refuse absurd files (corrupt build) instead of OOM

const char* const kChbvBarQss =
    "QScrollBar:vertical { background: transparent; width: 8px; margin: 2px 1px 2px 1px; border: none; }"
    "QScrollBar:horizontal { background: transparent; height: 8px; margin: 1px 2px 1px 2px; border: none; }"
    "QScrollBar::handle:vertical { background: rgba(232,230,224,70); border-radius: 3px; min-height: 36px; }"
    "QScrollBar::handle:horizontal { background: rgba(232,230,224,70); border-radius: 3px; min-width: 36px; }"
    "QScrollBar::handle:hover { background: rgba(232,230,224,120); }"
    "QScrollBar::add-line, QScrollBar::sub-line { width: 0px; height: 0px; border: none; background: none; }"
    "QScrollBar::add-page, QScrollBar::sub-page { background: none; }";

const char* const kChbvMenuQss =
    "QMenu { background: #13131a; color: #e8e6e0; border: 1px solid #26242c; padding: 4px 0px;"
    " font-family: 'IBM Plex Mono', Menlo; font-size: 11px; }"
    "QMenu::item { padding: 4px 18px 4px 24px; }"
    "QMenu::item:selected { background: #caa75c; color: #0a0a0c; }"
    "QMenu::indicator { width: 10px; height: 10px; left: 7px; }";

/// `rel` inside `base` (both absolute, cleaned); "" when rel is empty/absolute or escapes base.
QString chbv_file_in(const QString& base, const QString& rel) {
    if (base.isEmpty() || rel.trimmed().isEmpty() || QDir::isAbsolutePath(rel)) return {};
    const QString p = QDir::cleanPath(base + QLatin1Char('/') + rel);
    return p.startsWith(base + QLatin1Char('/')) ? p : QString();
}

QByteArray chbv_read_bytes(const QString& path, QString* err) {
    QFile f(path);
    if (!f.open(QIODevice::ReadOnly)) {
        if (err) *err = f.errorString();
        return {};
    }
    if (f.size() > kChbvMaxFileBytes) {
        if (err) *err = QStringLiteral("tệp quá lớn (%1 MB)").arg(f.size() / (1024 * 1024));
        return {};
    }
    QByteArray b = f.readAll();
    if (b.isEmpty() && err) *err = QStringLiteral("tệp rỗng");
    return b;
}

bool chbv_read_json(const QString& path, QJsonObject* out, QString* err) {
    const QByteArray b = chbv_read_bytes(path, err);
    if (b.isEmpty()) return false;
    QJsonParseError pe;
    const QJsonDocument doc = QJsonDocument::fromJson(b, &pe);
    if (pe.error != QJsonParseError::NoError || !doc.isObject()) {
        if (err) *err = pe.error != QJsonParseError::NoError ? pe.errorString() : QStringLiteral("không phải đối tượng JSON");
        return false;
    }
    *out = doc.object();
    return true;
}

bool chbv_scrollable(const ScrollRegion& r) { return r.scrollWidth > r.clientWidth + 0.5f; }

std::vector<float> chbv_scroll_xs(const Document& d) {
    std::vector<float> out;
    for (const ScrollRegion& r : d.scroll_regions()) out.push_back(r.scrollX);
    return out;
}

void chbv_set_scroll_xs(Document& d, const std::vector<float>& xs) {
    const size_t n = std::min(xs.size(), d.scroll_regions().size());
    for (size_t i = 0; i < n; ++i) d.set_scroll_x(int(i), xs[i]);
}

/// Every on.set pair of the action matches the state (the button is the "active" one).
bool chbv_set_active(const Document& d, const Action& a) {
    if (a.set.empty()) return false;
    for (const auto& kv : a.set)
        if (d.get_state(kv.first) != kv.second) return false;
    return true;
}

} // namespace

// ── construction ───────────────────────────────────────────────────────────────────────────────

ChbView::ChbView(QWidget* parent) : QWidget(parent) {
    ensure_fonts();
    setObjectName(QStringLiteral("chbView"));
    setAttribute(Qt::WA_OpaquePaintEvent);
    setMouseTracking(true);
    setFocusPolicy(Qt::StrongFocus); // keyboard page scrolling after a click

    vbar_ = new QScrollBar(Qt::Vertical, this);
    hbar_ = new QScrollBar(Qt::Horizontal, this);
    for (QScrollBar* b : {vbar_, hbar_}) {
        b->setStyleSheet(QString::fromLatin1(kChbvBarQss));
        b->setCursor(Qt::ArrowCursor);
        b->setFocusPolicy(Qt::NoFocus);
        b->hide();
    }
    connect(vbar_, &QScrollBar::valueChanged, this, [this](int v) {
        if (doc_) doc_->set_scroll_y(float(v));
        update();
    });
    connect(hbar_, &QScrollBar::valueChanged, this, [this](int) { update(); });
}

ChbView::~ChbView() = default;

// ── loading ────────────────────────────────────────────────────────────────────────────────────

bool ChbView::set_payload(const QJsonObject& payload, bool keep_state, QString* err) {
    const QString schema = payload.value(QStringLiteral("schema")).toString();
    if (!schema.isEmpty() && schema != kChbvSchema) {
        if (err)
            *err = tr("Kết quả dựng khác phiên bản (schema \"%1\", app cần \"%2\") — cập nhật scripts/chaebol_map.py "
                      "rồi bấm FETCH.").arg(schema, QString(kChbvSchema));
        return false;
    }
    const QString dir = payload.value(QStringLiteral("build")).toString().trimmed();
    if (dir.isEmpty()) {
        if (err)
            *err = tr("Kết quả dựng thiếu đường dẫn \"build\" — bấm FETCH; vẫn lỗi thì chạy thử "
                      "python3 scripts/chaebol_map.py build.");
        return false;
    }
    return load_build_impl(dir, payload.value(QStringLiteral("manifest")).toObject(), keep_state, err);
}

bool ChbView::load_build(const QString& build_dir, bool keep_state, QString* err) {
    return load_build_impl(build_dir, {}, keep_state, err);
}

bool ChbView::load_current(const QString& current_json, bool keep_state, QString* err) {
    QJsonObject cur;
    QString e;
    if (!chbv_read_json(current_json, &cur, &e)) {
        if (err) *err = tr("Không đọc được %1 (%2) — bấm FETCH để dựng lại.").arg(current_json, e);
        return false;
    }
    return set_payload(cur, keep_state, err);
}

bool ChbView::load_build_impl(const QString& dir, const QJsonObject& fallback_manifest, bool keep_state, QString* err) {
    const auto fail = [err](const QString& m) {
        if (err) *err = m;
        return false;
    };
    const QFileInfo fi(dir);
    if (dir.isEmpty() || !fi.isDir())
        return fail(tr("Không thấy thư mục bản dựng %1 — bấm FETCH để dựng lại.").arg(dir));
    const QString base = fi.canonicalFilePath();

    QJsonObject m;
    QString e;
    if (!chbv_read_json(base + QStringLiteral("/manifest.json"), &m, &e)) {
        if (fallback_manifest.isEmpty())
            return fail(tr("manifest.json của bản dựng không đọc được (%1) — bấm FETCH để dựng lại.").arg(e));
        m = fallback_manifest;
    }
    const QString schema = m.value(QStringLiteral("schema")).toString();
    if (schema != kChbvSchema)
        return fail(tr("Bản dựng khác phiên bản (schema \"%1\", app cần \"%2\") — cập nhật scripts/chaebol_map.py "
                       "rồi bấm FETCH.").arg(schema, QString(kChbvSchema)));

    QHash<QString, QString> tabFiles, incFiles, keyTab, defaults;
    QHash<QString, QStringList> opts;
    QStringList tabIds, keys;
    for (const QJsonValue& v : m.value(QStringLiteral("tabs")).toArray()) {
        const QJsonObject t = v.toObject();
        const QString id = t.value(QStringLiteral("id")).toString(), file = t.value(QStringLiteral("file")).toString();
        if (id.isEmpty() || file.isEmpty() || tabFiles.contains(id)) continue;
        tabFiles.insert(id, file);
        tabIds << id;
    }
    if (tabIds.isEmpty()) return fail(tr("Bản dựng không có tab nào (manifest.tabs rỗng) — bấm FETCH để dựng lại."));
    const QJsonObject inc = m.value(QStringLiteral("inc")).toObject();
    for (auto it = inc.begin(); it != inc.end(); ++it) incFiles.insert(it.key(), it.value().toString());
    const QJsonArray states = m.value(QStringLiteral("inventory")).toObject().value(QStringLiteral("states")).toArray();
    for (const QJsonValue& v : states) {
        const QJsonObject s = v.toObject();
        const QString key = s.value(QStringLiteral("key")).toString();
        if (key.isEmpty() || defaults.contains(key)) continue;
        keys << key;
        defaults.insert(key, s.value(QStringLiteral("default")).toString());
        keyTab.insert(key, s.value(QStringLiteral("tab")).toString());
        QStringList o;
        for (const QJsonValue& x : s.value(QStringLiteral("options")).toArray()) o << x.toString();
        opts.insert(key, o);
    }
    const QString tabKey = QStringLiteral("tab");
    if (!defaults.contains(tabKey)) {
        keys.prepend(tabKey);
        opts.insert(tabKey, tabIds);
    }
    if (!tabIds.contains(defaults.value(tabKey))) defaults.insert(tabKey, tabIds.first());

    const QString shellRel = m.value(QStringLiteral("shell")).toString(QStringLiteral("shell.json"));
    const QString shellPath = chbv_file_in(base, shellRel);
    const QByteArray shell = shellPath.isEmpty() ? QByteArray() : chbv_read_bytes(shellPath, &e);
    if (shell.isEmpty())
        return fail(tr("Không đọc được %1 của bản dựng (%2) — bấm FETCH để dựng lại.")
                        .arg(shellRel, shellPath.isEmpty() ? tr("đường dẫn không hợp lệ") : e));
    auto doc = std::make_unique<Document>();
    if (!doc->set_shell(shell, &e)) return fail(tr("%1 hỏng (%2) — bấm FETCH để dựng lại.").arg(shellRel, e));

    // Carry the reader's place over a rebuild: state values the new inventory still accepts + scroll.
    const QString prevTab = tab();
    const int prevY = vbar_->value();
    QHash<QString, QString> carry;
    if (keep_state && doc_) {
        const QHash<QString, QString> old = doc_->state();
        for (auto it = old.begin(); it != old.end(); ++it) {
            if (!defaults.contains(it.key())) continue;
            const QStringList o = opts.value(it.key());
            if (o.isEmpty() || o.contains(it.value())) carry.insert(it.key(), it.value());
        }
    }

    // Commit (the old document and its loaders go away here).
    doc_ = std::move(doc);
    build_dir_ = base;
    manifest_ = m;
    tab_files_ = tabFiles;
    inc_files_ = incFiles;
    tab_ids_ = tabIds;
    state_keys_ = keys;
    options_ = opts;
    key_tab_ = keyTab;
    load_errors_.clear();
    press_valid_ = false;
    doc_->set_tab_loader([this](const QString& id) { return read_build_file(tab_files_.value(id), tr("tab %1").arg(id)); });
    doc_->set_inc_loader([this](const QString& key) { return read_build_file(inc_files_.value(key), tr("inc %1").arg(key)); });
    doc_->set_defaults(defaults);
    doc_->reset_state();
    if (!carry.isEmpty()) doc_->merge_state(carry);
    laid_w_ = laid_h_ = 0;
    relayout(); // first render: commit + scope reset
    if (!keep_state) hbar_->setValue(0);
    if (can_layout()) {
        pending_scroll_y_ = -1;
        vbar_->setValue(keep_state ? prevY : 0);
        reveal_active_buttons();
    } else {
        pending_scroll_y_ = keep_state ? prevY : 0;
        pending_reveal_ = true;
    }
    update();
    if (tab() != prevTab) emit tab_changed(tab());
    return true;
}

bool ChbView::has_page() const { return doc_ != nullptr; }

QString ChbView::build_file(const QString& rel) const { return chbv_file_in(build_dir_, rel); }

QByteArray ChbView::read_build_file(const QString& rel, const QString& what) const {
    QString e;
    const QString path = build_file(rel);
    QByteArray b;
    if (rel.isEmpty()) e = tr("manifest không khai tệp cho %1").arg(what);
    else if (path.isEmpty()) e = tr("%1: đường dẫn ngoài bản dựng (%2)").arg(what, rel);
    else if ((b = chbv_read_bytes(path, &e)).isEmpty()) e = tr("%1: không đọc được %2 (%3) — bản dựng có thể đã bị xoá, bấm FETCH").arg(what, rel, e);
    if (!e.isEmpty() && !load_errors_.contains(e)) load_errors_ << e;
    return b;
}

// ── state ──────────────────────────────────────────────────────────────────────────────────────

QString ChbView::tab() const { return doc_ ? doc_->get_state(QStringLiteral("tab")) : QString(); }

bool ChbView::set_tab(const QString& id) {
    if (!doc_ || !tab_ids_.contains(id)) return false;
    return set_state(QStringLiteral("tab"), id);
}

QStringList ChbView::switch_ids() const {
    const QString cur = tab();
    const bool perTab = std::any_of(state_keys_.begin(), state_keys_.end(), [this](const QString& k) { return !key_tab_.value(k).isEmpty(); });
    QStringList out;
    for (const QString& k : state_keys_)
        if (k != QLatin1String("tab") && (!perTab || key_tab_.value(k) == cur)) out << k;
    return out;
}

QStringList ChbView::options_of(const QString& key) const { return options_.value(key); }

QString ChbView::state_of(const QString& key) const { return doc_ ? doc_->get_state(key) : QString(); }

QHash<QString, QString> ChbView::state() const { return doc_ ? doc_->state() : QHash<QString, QString>(); }

bool ChbView::set_state(const QString& key, const QString& value) {
    QHash<QString, QString> kv;
    kv.insert(key, value);
    return merge_state(kv);
}

bool ChbView::merge_state(const QHash<QString, QString>& kv) {
    if (!doc_ || kv.isEmpty()) return false;
    const QHash<QString, QString> cur = doc_->state();
    bool diff = false;
    for (auto it = kv.begin(); it != kv.end() && !diff; ++it) diff = !cur.contains(it.key()) || cur.value(it.key()) != it.value();
    if (!diff) return false;
    const QString prev = tab();
    doc_->merge_state(kv);
    after_state_change(prev, nullptr, {}, {});
    return true;
}

void ChbView::after_state_change(const QString& prev_tab, const Action* clicked, QPointF click_widget, QPointF click_doc) {
    relayout(); // re-render; scrollY stays, clamped by the new range
    // Horizontal boxes: a clicked button is scrolled minimally into view; a tab switched without a click (API,
    // select) brings the tab button into view. Nothing else moves (Chrome keeps scrollLeft across re-renders).
    const bool tabChanged = tab() != prev_tab;
    if (can_layout()) {
        if (clicked && clicked->region >= 0) reveal_clicked(*clicked, click_widget, click_doc);
        else if (tabChanged) reveal_active_buttons();
    } else if (tabChanged || clicked) {
        pending_reveal_ = true;
    }
    update();
    const QString now = tab();
    if (now != prev_tab) emit tab_changed(now);
}

// ── layout / scrollbars ────────────────────────────────────────────────────────────────────────

bool ChbView::can_layout() const { return isVisible() || testAttribute(Qt::WA_Resized); }

void ChbView::relayout() {
    if (!doc_) {
        sync_scrollbars();
        return;
    }
    if (!can_layout()) {
        // Hidden and never sized: commit the state (scope reset) now, lay out at the real width when shown.
        doc_->resolve();
        pending_layout_ = true;
        return;
    }
    pending_layout_ = false;
    const float w = float(std::max(1, width())), h = float(std::max(1, height()));
    doc_->set_viewport(w, h);
    doc_->layout(w);
    laid_w_ = w;
    laid_h_ = h;
    sync_scrollbars();
}

void ChbView::sync_scrollbars() {
    const int w = width(), h = height();
    const bool laid = doc_ && laid_w_ > 0;
    const int ch = laid ? int(std::ceil(doc_->content_height())) : 0;
    const int cw = laid ? int(std::ceil(doc_->content_width())) : 0;
    const int vmax = std::max(0, ch - h), hmax = std::max(0, cw - w);
    vbar_->setRange(0, vmax);
    vbar_->setPageStep(std::max(1, h));
    vbar_->setSingleStep(kChbvLineStepPx);
    hbar_->setRange(0, hmax);
    hbar_->setPageStep(std::max(1, w));
    hbar_->setSingleStep(kChbvLineStepPx);
    const int bv = vmax > 0 ? kChbvBarPx : 0, bh = hmax > 0 ? kChbvBarPx : 0;
    vbar_->setGeometry(w - kChbvBarPx, 0, kChbvBarPx, std::max(0, h - bh));
    hbar_->setGeometry(0, h - kChbvBarPx, std::max(0, w - bv), kChbvBarPx);
    vbar_->setVisible(vmax > 0);
    hbar_->setVisible(hmax > 0);
    if (doc_) doc_->set_scroll_y(float(vbar_->value()));
}

QPointF ChbView::to_doc(QPointF widget_pt) const { return widget_pt + QPointF(hbar_->value(), vbar_->value()); }

// ── horizontal boxes ───────────────────────────────────────────────────────────────────────────

void ChbView::reveal_in_region(int region, const QRectF& target) {
    const std::vector<ScrollRegion> regs = doc_->scroll_regions();
    if (region < 0 || region >= int(regs.size()) || !chbv_scrollable(regs[size_t(region)])) return;
    const ScrollRegion& r = regs[size_t(region)];
    const double left = target.left() - r.rect.left(), right = target.right() - r.rect.left();
    double x = r.scrollX;
    if (right - x > r.clientWidth) x = std::ceil(right - r.clientWidth);
    if (left < x) x = std::floor(left);
    doc_->set_scroll_x(region, float(x));
}

void ChbView::reveal_clicked(const Action& clicked, QPointF click_widget, QPointF click_doc) {
    // The re-render may have moved the button a little (active style) or clamped scrollY (shorter tab under a
    // sticky bar): re-probe at the click point on screen, then at the old document point.
    QRectF target = clicked.rect;
    int region = clicked.region;
    for (const QPointF& pt : {to_doc(click_widget), click_doc}) {
        const Action now = doc_->hit_test(pt);
        if (now.region >= 0 && now.type == clicked.type && now.set == clicked.set && now.sortCol == clicked.sortCol) {
            target = now.rect;
            region = now.region;
            break;
        }
    }
    reveal_in_region(region, target);
}

void ChbView::reveal_active_buttons() {
    if (!doc_ || laid_w_ <= 0) return;
    // Find each box's active button (first on.set matching the state, as the capture rule does): put it flush
    // right with normalize_hscroll(), probe its rect at scrollY 0 (a top-sticky bar is not shifted there), restore.
    const std::vector<float> saved = chbv_scroll_xs(*doc_);
    const float sy = doc_->scroll_y();
    doc_->set_scroll_y(0);
    doc_->normalize_hscroll();
    const std::vector<ScrollRegion> regs = doc_->scroll_regions();
    std::vector<std::pair<int, QRectF>> found;
    for (const ScrollRegion& r : regs) {
        if (!chbv_scrollable(r) || size_t(r.id) >= saved.size()) continue;
        const bool flushRight = r.scrollX > 0;
        if (!flushRight && saved[size_t(r.id)] <= 0) continue; // visible at 0 (or no active button): nothing to do
        const double y = r.rect.center().y();
        const double stop = flushRight ? r.rect.right() - kChbvNearProbes * kChbvProbeStepPx : r.rect.left();
        for (double x = r.rect.right() - 2; x > stop; x -= kChbvProbeStepPx) {
            const Action a = doc_->hit_test(QPointF(x, y));
            if (a.region == r.id && chbv_set_active(*doc_, a)) {
                found.emplace_back(r.id, a.rect);
                break;
            }
        }
    }
    chbv_set_scroll_xs(*doc_, saved);
    doc_->set_scroll_y(sy);
    for (const auto& f : found) reveal_in_region(f.first, f.second);
}

int ChbView::region_at(QPointF doc_pt) const {
    const std::vector<ScrollRegion> regs = doc_->scroll_regions();
    const Action a = doc_->hit_test(doc_pt); // exact (sticky + nested scroll) when over an actionable node
    if (a.region >= 0 && a.region < int(regs.size()) && chbv_scrollable(regs[size_t(a.region)])) return a.region;
    int best = -1;
    double bestArea = 0;
    for (const ScrollRegion& r : regs) {
        if (!chbv_scrollable(r)) continue;
        QRectF rc = r.rect;
        if (r.sticky) rc.translate(0, std::max(0.0, double(doc_->scroll_y()) - rc.top())); // top:0 bar (the tab bar)
        if (!rc.contains(doc_pt)) continue;
        const double area = rc.width() * rc.height();
        if (best < 0 || area < bestArea) {
            best = r.id;
            bestArea = area;
        }
    }
    return best;
}

// ── events ─────────────────────────────────────────────────────────────────────────────────────

void ChbView::paintEvent(QPaintEvent* event) {
    QPainter p(this);
    const bool laid = doc_ && laid_w_ > 0 && doc_->is_laid_out();
    const QColor canvas = laid && doc_->canvas_color().isValid() ? doc_->canvas_color() : kChbvCanvas;
    p.fillRect(event->rect(), canvas);
    if (!laid) return;
    const float sx = float(hbar_->value()), sy = float(vbar_->value());
    doc_->set_scroll_y(sy);
    p.translate(-sx, -sy);
    doc_->paint(p, QRectF(event->rect()).translated(sx, sy));
}

void ChbView::resizeEvent(QResizeEvent* event) {
    QWidget::resizeEvent(event);
    relayout();
    apply_pending();
}

void ChbView::showEvent(QShowEvent* event) {
    QWidget::showEvent(event);
    if (pending_layout_ || laid_w_ != float(std::max(1, width())) || laid_h_ != float(std::max(1, height()))) relayout();
    apply_pending();
}

void ChbView::apply_pending() {
    if (laid_w_ <= 0) return;
    if (pending_scroll_y_ >= 0) {
        vbar_->setValue(pending_scroll_y_);
        pending_scroll_y_ = -1;
    }
    if (pending_reveal_) {
        pending_reveal_ = false;
        reveal_active_buttons();
        update();
    }
}

void ChbView::wheelEvent(QWheelEvent* event) {
    if (!doc_ || laid_w_ <= 0) {
        event->ignore();
        return;
    }
    const QPointF d = event->pixelDelta().isNull() ? QPointF(event->angleDelta()) * (kChbvWheelNotchPx / 120.0)
                                                   : QPointF(event->pixelDelta());
    double dx = d.x(), dy = d.y();
    if ((event->modifiers() & Qt::ShiftModifier) && qFuzzyIsNull(dx)) std::swap(dx, dy); // shift+wheel = horizontal
    if (std::abs(dx) > std::abs(dy)) {
        const int r = region_at(to_doc(event->position()));
        if (r >= 0) {
            const float before = doc_->scroll_x(r);
            doc_->set_scroll_x(r, before - float(dx));
            if (doc_->scroll_x(r) != before) update();
        } else {
            hbar_->setValue(hbar_->value() - int(std::lround(dx)));
        }
    } else {
        vbar_->setValue(vbar_->value() - int(std::lround(dy)));
    }
    event->accept();
}

void ChbView::set_pointer(bool on) {
    if (on == pointer_) return;
    pointer_ = on;
    if (on) setCursor(Qt::PointingHandCursor);
    else unsetCursor();
}

void ChbView::mouseMoveEvent(QMouseEvent* event) {
    if (doc_ && laid_w_ > 0) set_pointer(doc_->hit_test(to_doc(event->position())).pointer);
    QWidget::mouseMoveEvent(event);
}

void ChbView::leaveEvent(QEvent* event) {
    set_pointer(false);
    QWidget::leaveEvent(event);
}

void ChbView::mousePressEvent(QMouseEvent* event) {
    if (event->button() != Qt::LeftButton || !doc_ || laid_w_ <= 0) {
        QWidget::mousePressEvent(event);
        return;
    }
    const Action a = doc_->hit_test(to_doc(event->position()));
    press_valid_ = a.type != Action::None;
    press_rect_ = a.rect;
    press_type_ = int(a.type);
    event->accept();
}

void ChbView::mouseReleaseEvent(QMouseEvent* event) {
    if (event->button() != Qt::LeftButton || !press_valid_ || !doc_) {
        QWidget::mouseReleaseEvent(event);
        return;
    }
    press_valid_ = false;
    const QPointF dp = to_doc(event->position());
    const Action a = doc_->hit_test(dp);
    event->accept();
    // DOM click: press and release on the same target
    if (a.type == Action::None || int(a.type) != press_type_ || a.rect != press_rect_) return;
    perform(a, event->position(), dp);
}

void ChbView::perform(const Action& a, QPointF widget_pos, QPointF doc_pos) {
    switch (a.type) {
    case Action::Href: {
        const QUrl url(a.href);
        const QString scheme = url.scheme().toLower();
        if (url.isValid() && (scheme == QLatin1String("http") || scheme == QLatin1String("https"))) QDesktopServices::openUrl(url);
        return;
    }
    case Action::Select:
        open_select(a, widget_pos, doc_pos);
        return;
    case Action::Set:
    case Action::Sort:
    case Action::SetAndSort: {
        const QString prev = tab();
        if (doc_->activate(a)) after_state_change(prev, &a, widget_pos, doc_pos);
        return;
    }
    case Action::None:
        return;
    }
}

void ChbView::open_select(const Action& a, QPointF widget_pos, QPointF doc_pos) {
    QMenu menu(this);
    menu.setStyleSheet(QString::fromLatin1(kChbvMenuQss));
    for (int i = 0; i < a.optionValues.size(); ++i) {
        QAction* act = menu.addAction(i < a.optionLabels.size() ? a.optionLabels[i] : a.optionValues[i]);
        act->setCheckable(true);
        act->setChecked(a.optionValues[i] == a.current);
        act->setData(a.optionValues[i]);
    }
    if (menu.isEmpty()) return;
    // Anchor under the select box (offsets taken relative to the click point).
    const QPointF anchor = widget_pos + QPointF(a.rect.left() - doc_pos.x(), a.rect.bottom() - doc_pos.y());
    QPointer<ChbView> self(this);
    const QAction* chosen = menu.exec(mapToGlobal(anchor.toPoint()));
    if (!self || !chosen || !doc_) return;
    const QString prev = tab();
    if (doc_->choose_option(a, chosen->data().toString())) after_state_change(prev, nullptr, {}, {});
}

void ChbView::keyPressEvent(QKeyEvent* event) {
    if (!doc_) {
        QWidget::keyPressEvent(event);
        return;
    }
    const int page = std::max(1, int(height() * 0.875));
    switch (event->key()) {
    case Qt::Key_Down: vbar_->setValue(vbar_->value() + kChbvLineStepPx); break;
    case Qt::Key_Up: vbar_->setValue(vbar_->value() - kChbvLineStepPx); break;
    case Qt::Key_PageDown: vbar_->setValue(vbar_->value() + page); break;
    case Qt::Key_PageUp: vbar_->setValue(vbar_->value() - page); break;
    case Qt::Key_Space: vbar_->setValue(vbar_->value() + ((event->modifiers() & Qt::ShiftModifier) ? -page : page)); break;
    case Qt::Key_Home: vbar_->setValue(0); break;
    case Qt::Key_End: vbar_->setValue(vbar_->maximum()); break;
    case Qt::Key_Left: hbar_->setValue(hbar_->value() - kChbvLineStepPx); break;
    case Qt::Key_Right: hbar_->setValue(hbar_->value() + kChbvLineStepPx); break;
    default: QWidget::keyPressEvent(event); return;
    }
    event->accept();
}

// ── inspection ─────────────────────────────────────────────────────────────────────────────────

namespace {

/// Lay `d` out like a reference capture (width × 1000, scrollY 0, horizontal boxes normalised); returns what
/// chbv_restore needs to put the view's own state back.
struct ChbvSaved {
    std::vector<float> xs;
    float sy = 0;
};

ChbvSaved chbv_unroll(Document& d, int width) {
    ChbvSaved s{chbv_scroll_xs(d), d.scroll_y()};
    d.set_viewport(float(width), float(kChbvRefViewportH));
    d.layout(float(width));
    d.normalize_hscroll();
    d.set_scroll_y(0);
    return s;
}

void chbv_restore(Document& d, float w, float h, const ChbvSaved& s) {
    if (w > 0 && h > 0) {
        d.set_viewport(w, h);
        d.layout(w);
    }
    chbv_set_scroll_xs(d, s.xs);
    d.set_scroll_y(s.sy);
}

} // namespace

QImage ChbView::grab_unrolled(int width) const {
    if (!doc_ || width <= 0) return {};
    Document& d = *doc_;
    const ChbvSaved saved = chbv_unroll(d, width);
    const int w = std::max(1, int(std::ceil(d.content_width())));
    const int h = std::max(1, int(std::ceil(d.content_height())));
    QImage img(w, h, QImage::Format_ARGB32_Premultiplied);
    img.fill(d.canvas_color().isValid() ? d.canvas_color() : kChbvCanvas);
    {
        QPainter p(&img);
        d.paint(p, QRectF(0, 0, w, h));
    }
    chbv_restore(d, laid_w_, laid_h_, saved);
    return img.convertToFormat(QImage::Format_RGB32);
}

QString ChbView::dump_geometry_json(int width) const {
    if (!doc_) return QStringLiteral("{}");
    if (width <= 0) return doc_->is_laid_out() ? doc_->dump_geometry_json() : QStringLiteral("{}");
    Document& d = *doc_;
    const ChbvSaved saved = chbv_unroll(d, width);
    const QString out = d.dump_geometry_json();
    chbv_restore(d, laid_w_, laid_h_, saved);
    return out;
}

QString ChbView::plain_text() const { return doc_ && doc_->is_laid_out() ? doc_->plain_text() : QString(); }

QStringList ChbView::warnings() const {
    QStringList w = load_errors_;
    if (doc_) w += doc_->warnings();
    w.removeDuplicates();
    return w;
}

} // namespace fincept::screens::chb
