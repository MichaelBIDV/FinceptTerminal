// WdcRange.cpp, package F: time window, dimmed buttons, local store, calendar popover, isStock pan.
// See WdcRange.h for the sources (BEH §3, §4.1, §6.2, §6.3; DESIGN §6.1, §7; HS line numbers).
#include "WdcRange.h"

#include "WdcData.h"
#include "WdcHcMath.h"
#include "WdcHcText.h"
#include "WdcIcons_p.h"
#include "WdcTheme_p.h"

#include <QDateTime>
#include <QFile>
#include <QGuiApplication>
#include <QJsonDocument>
#include <QKeyEvent>
#include <QMouseEvent>
#include <QMutex>
#include <QPainter>
#include <QSaveFile>
#include <QScreen>
#include <QTimeZone>

#include <algorithm>
#include <climits>
#include <cmath>

namespace fincept::screens::wdc {

namespace th = theme;

namespace {

constexpr int kIctOffsetSec = 7 * 3600;           // Asia/Ho_Chi_Minh, fixed since 1975
constexpr double kBtnH = 24, kBtnPad = 4, kBtnRadius = 4, kBtnPx = 13;
constexpr double kBtnLineH = 13.0 * 11.0 / 7.0;   // 20.4286, MUI line-height of the range buttons (UI §4.3)
constexpr double kPopPad = 8, kPopGap = 4;        // DESIGN §6.1 padding 8; gap below the anchor (MẶC ĐỊNH)
constexpr double kPanThreshold = 10;              // Pointer.drag: hasDragged > 10 (HS:26700)
const QColor kSelBg(0x21, 0x23, 0x2E);
const QColor kDimBg(166, 176, 195, 41);           // rgba(166,176,195,0.16)
constexpr double kDimOpacity = 0.5;

const QTimeZone& wdcRange_ict() {
    static const QTimeZone tz(kIctOffsetSec);
    return tz;
}

QDate wdcRange_ictDate(qint64 ms) { return QDateTime::fromMSecsSinceEpoch(ms, wdcRange_ict()).date(); }

qint64 wdcRange_startOfMonth(const QDate& d) {
    return QDateTime(QDate(d.year(), d.month(), 1), QTime(0, 0), wdcRange_ict()).toMSecsSinceEpoch();
}

bool wdcRange_present(const SeriesData* d) {
    if (!d || d->status == Status::Missing) return false;
    return std::any_of(d->pts.begin(), d->pts.end(), [](const QPointF& p) { return std::isfinite(p.y()); });
}

bool wdcRange_visible(const ChartInput& in, size_t i) { return i >= in.visible.size() || in.visible[i]; }

} // namespace

// ---- window ----------------------------------------------------------------------------------------------------

const QStringList& rangeButtons() {
    static const QStringList v = {QStringLiteral("YTD"), QStringLiteral("3M"), QStringLiteral("6M"),
                                  QStringLiteral("1Y"),  QStringLiteral("2Y"), QStringLiteral("3Y"),
                                  QStringLiteral("5Y"),  QStringLiteral("10Y"), QStringLiteral("All")};
    return v;
}

bool isRangeButton(const QString& label) { return rangeButtons().contains(label); }

XWindow windowFor(const QString& button, qint64 refMaxMs, bool exactAll) {
    const QString b = isRangeButton(button) ? button : QStringLiteral("3Y");
    if (b == QLatin1String("All")) return {std::nullopt, std::nullopt, !exactAll};
    const QDate ref = wdcRange_ictDate(refMaxMs);
    const qint64 maxMs = QDateTime(ref, QTime(23, 59, 59), wdcRange_ict()).toMSecsSinceEpoch();
    QDate from;
    if (b == QLatin1String("YTD")) from = QDate(ref.year(), 1, 1);
    else if (b == QLatin1String("3M")) from = ref.addMonths(-3);
    else if (b == QLatin1String("6M")) from = ref.addMonths(-6);
    else from = ref.addYears(-b.chopped(1).toInt());   // 1Y .. 10Y, calendar years (BEH §3.2)
    return {wdcRange_startOfMonth(from), maxMs, false};
}

XWindow windowForCard(const QString& button, std::optional<qint64> refMaxMs, bool exactAll) {
    if (!refMaxMs) return {std::nullopt, std::nullopt, true};
    return windowFor(button, *refMaxMs, exactAll);
}

XWindow windowForPage(const QString& button, std::optional<qint64> refMaxMs, bool exactAll) {
    if (!refMaxMs) return {std::nullopt, std::nullopt, true};
    const QString b = isRangeButton(button) ? button : QStringLiteral("3Y");
    if (b == QLatin1String("All")) return {std::nullopt, std::nullopt, !exactAll};
    const QDate ref = wdcRange_ictDate(*refMaxMs);
    QDate from;
    if (b == QLatin1String("YTD")) from = QDate(ref.year(), 1, 1);
    else if (b.endsWith(QLatin1Char('M'))) from = ref.addMonths(-b.chopped(1).toInt()).addDays(1);
    else from = ref.addYears(-b.chopped(1).toInt()).addDays(1);
    return {QDateTime(from, QTime(0, 0), wdcRange_ict()).toMSecsSinceEpoch(), *refMaxMs, false};
}

QString resolveRangeButton(const QString& stored, const QString& cardDefault) {
    if (isRangeButton(stored)) return stored;
    if (isRangeButton(cardDefault)) return cardDefault;
    return QStringLiteral("3Y");
}

// ---- dimmed buttons ----------------------------------------------------------------------------------------------

int freqPeriodMonths(const QString& freq, const QString& dateType) {
    const QString f = freq.trimmed().toUpper();
    if (f == QLatin1String("D") || f == QLatin1String("W") || f == QLatin1String("TP")) return 0;
    if (f == QLatin1String("M") || f == QLatin1String("YTD")) return 1;
    if (f == QLatin1String("Q")) return 3;
    if (f == QLatin1String("Y")) return 12;
    const QString t = dateType.trimmed().toLower();
    if (t == QLatin1String("ngay")) return 0;
    if (t == QLatin1String("thang")) return 1;
    if (t == QLatin1String("quy")) return 3;
    if (t == QLatin1String("nam")) return 12;
    return -1;
}

int finestPeriodMonths(const std::vector<const ChartInput*>& panes) {
    int best = INT_MAX;
    for (const ChartInput* in : panes) {
        if (!in) continue;
        for (size_t i = 0; i < in->refs.size() && i < in->data.size(); ++i) {
            if (!in->refs[i] || !wdcRange_visible(*in, i) || !wdcRange_present(in->data[i])) continue;
            const int p = freqPeriodMonths(in->data[i]->freq, in->refs[i]->dateType);
            if (p >= 0) best = std::min(best, p);
        }
    }
    return best == INT_MAX ? 0 : best;
}

int rangeButtonMonths(const QString& button, std::optional<qint64> refMaxMs) {
    if (button == QLatin1String("All")) return INT_MAX;
    if (button == QLatin1String("YTD")) return refMaxMs ? wdcRange_ictDate(*refMaxMs).month() : 12;
    if (button.endsWith(QLatin1Char('M'))) return button.chopped(1).toInt();
    if (button.endsWith(QLatin1Char('Y'))) return 12 * button.chopped(1).toInt();
    return INT_MAX;
}

bool rangeButtonDimmed(const QString& button, int finestMonths, std::optional<qint64> refMaxMs) {
    if (finestMonths <= 0 || !isRangeButton(button)) return false;
    const int len = rangeButtonMonths(button, refMaxMs);
    return len != INT_MAX && len <= 2 * finestMonths;
}

QStringList dimmedRangeButtons(const std::vector<const ChartInput*>& panes, std::optional<qint64> refMaxMs) {
    const int p = finestPeriodMonths(panes);
    QStringList out;
    for (const QString& b : rangeButtons())
        if (rangeButtonDimmed(b, p, refMaxMs)) out << b;
    return out;
}

// ---- local store -------------------------------------------------------------------------------------------------

QString WdcRangeStore::get(const QString& dashId, const QString& cardKey) const {
    return map_.value(dashId).value(cardKey);
}

void WdcRangeStore::set(const QString& dashId, const QString& cardKey, const QString& button) {
    if (!isRangeButton(button)) return;
    map_[dashId].insert(cardKey, button);
}

void WdcRangeStore::remove(const QString& dashId, const QString& cardKey) {
    auto it = map_.find(dashId);
    if (it == map_.end()) return;
    it->remove(cardKey);
    if (it->isEmpty()) map_.erase(it);
}

int WdcRangeStore::size() const {
    int n = 0;
    for (const auto& m : map_) n += int(m.size());
    return n;
}

QJsonObject WdcRangeStore::toJson() const {
    QJsonObject ranges;
    for (auto it = map_.constBegin(); it != map_.constEnd(); ++it) {
        QJsonObject cards;
        for (auto c = it->constBegin(); c != it->constEnd(); ++c) cards.insert(c.key(), c.value());
        ranges.insert(it.key(), cards);
    }
    return QJsonObject{{QStringLiteral("schema"), QStringLiteral("wdc_range/1")}, {QStringLiteral("ranges"), ranges}};
}

bool WdcRangeStore::fromJson(const QJsonObject& o) {
    if (o.value(QStringLiteral("schema")).toString() != QLatin1String("wdc_range/1")) return false;
    map_.clear();
    const QJsonObject ranges = o.value(QStringLiteral("ranges")).toObject();
    for (auto it = ranges.constBegin(); it != ranges.constEnd(); ++it) {
        const QJsonObject cards = it.value().toObject();
        for (auto c = cards.constBegin(); c != cards.constEnd(); ++c) set(it.key(), c.key(), c.value().toString());
    }
    return true;
}

bool WdcRangeStore::loadFile(const QString& path, QString* error) {
    QFile f(path);
    if (!f.open(QIODevice::ReadOnly)) {
        if (error) *error = f.errorString();
        return false;
    }
    QJsonParseError pe;
    const QJsonDocument doc = QJsonDocument::fromJson(f.readAll(), &pe);
    if (pe.error != QJsonParseError::NoError || !doc.isObject() || !fromJson(doc.object())) {
        if (error) *error = pe.error != QJsonParseError::NoError ? pe.errorString() : QStringLiteral("bad_schema");
        return false;
    }
    return true;
}

bool WdcRangeStore::saveFile(const QString& path, QString* error) const {
    QSaveFile f(path);
    if (!f.open(QIODevice::WriteOnly) || f.write(QJsonDocument(toJson()).toJson(QJsonDocument::Indented)) < 0 ||
        !f.commit()) {
        if (error) *error = f.errorString();
        return false;
    }
    return true;
}

// ---- popover -------------------------------------------------------------------------------------------------------

std::vector<RangeButtonGeom> layoutRangeButtons(QPointF origin, double dpr, MetricsProfile profile, double height,
                                                double gap) {
    // Chromium lays out in device pixels (zoom for DSF): LayoutUnit = 1/64 device px. The capture ran at page zoom
    // 0.9 on a 2x screen, i.e. 1.8 device px per CSS px (X10); the screen runs at the real DPR.
    const double s = 64.0 * (profile == MetricsProfile::WidataDpr18 ? 1.8 : (dpr > 0 ? dpr : 1.0));
    auto lu = [s](double css) { return std::floor(css * s + 1e-9) / s; };        // LayoutUnit(float): truncation
    auto luText = [s](double css) { return std::ceil(css * s - 1e-7) / s; };     // text run width, rounded up
    const TextMetrics tm = TextMetrics::native(dpr);
    std::vector<RangeButtonGeom> out;
    double x = origin.x();
    const double h = lu(height);
    // the 20.43 line box is centred in the button (flex, align-items center; ref/widata/11 and ref/user/2)
    const double baseline = origin.y() + (h - kBtnLineH) / 2 + th::blinkBaseline(kBtnPx, kBtnLineH, dpr);
    for (const QString& label : rangeButtons()) {
        const double tw = luText(tm.exactWidth(label, kBtnPx, 400));
        const double w = std::max(h, tw + 2 * lu(kBtnPad));
        out.push_back({label, QRectF(x, origin.y(), w, h), x + (w - tw) / 2, baseline});
        x += w + lu(gap);
    }
    return out;
}

double rangeButtonsWidth(double dpr, MetricsProfile profile, double height, double gap) {
    const std::vector<RangeButtonGeom> g = layoutRangeButtons(QPointF(0, 0), dpr, profile, height, gap);
    return g.empty() ? 0 : g.back().rect.right();
}

void paintRangeButton(QPainter& p, const RangeButtonGeom& b, bool sel, bool dim, bool hover, bool pressed) {
    QColor bg = Qt::transparent, fg = th::color(th::kTextPrimary);
    if (sel) { bg = kSelBg; fg = Qt::white; }
    else if (dim) { bg = kDimBg; fg = th::color(th::kTextSecondary); }
    else if (pressed) bg = th::color(th::kActiveBg);
    else if (hover) bg = th::color(th::kHoverBg);
    p.save();
    if (dim && !sel) p.setOpacity(p.opacity() * kDimOpacity);
    QPainterPath box;
    box.addRoundedRect(b.rect, kBtnRadius, kBtnRadius);
    if (bg.alpha()) p.fillPath(box, bg);
    p.setFont(th::font(kBtnPx, 400));
    p.setPen(fg);
    p.drawText(QPointF(b.textX, b.baseline), b.label);
    p.restore();
}

WdcRangePopover::WdcRangePopover(QWidget* owner)
    : QWidget(owner, Qt::Popup | Qt::FramelessWindowHint | Qt::NoDropShadowWindowHint) {
    setAttribute(Qt::WA_TranslucentBackground);
    setMouseTracking(true);
    setFocusPolicy(Qt::StrongFocus);
    margin_ = shadowExtent(shadowCircleBtn());
    const QSizeF fs = frameSize();
    resize(int(std::ceil(fs.width() + 2 * margin_)), int(std::ceil(fs.height() + 2 * margin_)));
}

void WdcRangePopover::setState(const QString& current, const QStringList& dimmed) {
    current_ = current;
    dimmed_ = dimmed;
    focus_ = int(rangeButtons().indexOf(current));
    update();
}

QSizeF WdcRangePopover::frameSize() const {
    const double dpr = devicePixelRatioF() > 0 ? devicePixelRatioF() : 1;
    const std::vector<RangeButtonGeom> g = layoutRangeButtons(QPointF(0, 0), dpr);
    const double border = th::hairline(dpr);
    return QSizeF(g.back().rect.right() + 2 * (kPopPad + border), kBtnH + 2 * (kPopPad + border));
}

QRectF WdcRangePopover::frameRect() const { return QRectF(QPointF(margin_, margin_), frameSize()); }

std::vector<RangeButtonGeom> WdcRangePopover::buttons() const {
    const double dpr = devicePixelRatioF() > 0 ? devicePixelRatioF() : 1;
    const double inset = kPopPad + th::hairline(dpr);
    return layoutRangeButtons(frameRect().topLeft() + QPointF(inset, inset), dpr);
}

void WdcRangePopover::showBelow(const QRect& anchorGlobal) {
    QPointF topLeft(anchorGlobal.left(), anchorGlobal.bottom() + 1 + kPopGap);
    const QSizeF fs = frameSize();
    if (QScreen* s = parentWidget() ? parentWidget()->screen() : QGuiApplication::primaryScreen()) {
        const QRect av = s->availableGeometry();
        topLeft.setX(std::clamp<double>(topLeft.x(), av.left(), std::max<double>(av.left(), av.right() - fs.width())));
        if (topLeft.y() + fs.height() > av.bottom()) topLeft.setY(anchorGlobal.top() - kPopGap - fs.height());
    }
    move(QPoint(int(std::lround(topLeft.x() - margin_)), int(std::lround(topLeft.y() - margin_))));
    show();
    setFocus(Qt::PopupFocusReason);
}

bool WdcRangePopover::pick(const QString& label) {
    if (!isRangeButton(label) || dimmed_.contains(label)) return false;   // dimmed: BEH §6.3, click ignored
    current_ = label;
    update();
    const QPointer<WdcRangePopover> self(this);
    emit picked(label);   // a receiver may delete the popover or its owner card: touch nothing after that
    if (self) close();    // WA_DeleteOnClose: deleteLater, never a synchronous delete under the caller
    return true;
}

int WdcRangePopover::buttonAt(const QPointF& pos) const {
    const std::vector<RangeButtonGeom> g = buttons();
    for (size_t i = 0; i < g.size(); ++i)
        if (g[i].rect.contains(pos)) return int(i);
    return -1;
}

void WdcRangePopover::paintFrame(QPainter& p, qreal dpr) {
    paintPopoverFrame(p, frameRect(), dpr);
    const std::vector<RangeButtonGeom> g = buttons();
    for (size_t i = 0; i < g.size(); ++i) {
        const RangeButtonGeom& b = g[i];
        paintRangeButton(p, b, b.label == current_, dimmed_.contains(b.label), hover_ == int(i), press_ == int(i));
        if (focusVisible_ && focus_ == int(i)) {   // DESIGN §6.1 focus ring: 1 px #58667E, radius 4
            QPainterPath ring;
            ring.addRoundedRect(b.rect.adjusted(0.5, 0.5, -0.5, -0.5), kBtnRadius, kBtnRadius);
            p.strokePath(ring, QPen(th::color(th::kFocusRing), 1));
        }
    }
}

void WdcRangePopover::paintEvent(QPaintEvent*) {
    QPainter p(this);
    p.setRenderHint(QPainter::Antialiasing, true);
    p.setRenderHint(QPainter::TextAntialiasing, true);
    paintFrame(p, devicePixelRatioF());
}

QImage WdcRangePopover::renderImage(qreal dpr) {
    QImage img(QSize(int(std::ceil(width() * dpr)), int(std::ceil(height() * dpr))), QImage::Format_ARGB32_Premultiplied);
    img.setDevicePixelRatio(dpr);
    img.fill(Qt::transparent);
    QPainter p(&img);
    p.setRenderHint(QPainter::Antialiasing, true);
    p.setRenderHint(QPainter::TextAntialiasing, true);
    paintFrame(p, dpr);
    return img;
}

void WdcRangePopover::mouseMoveEvent(QMouseEvent* e) {
    const int i = buttonAt(e->position());
    if (i != hover_) { hover_ = i; update(); }
    setCursor(i >= 0 ? Qt::PointingHandCursor : Qt::ArrowCursor);   // dimmed keeps the pointer (BEH §6.2)
}

void WdcRangePopover::mousePressEvent(QMouseEvent* e) {
    if (!frameRect().contains(e->position())) { close(); return; }
    press_ = buttonAt(e->position());
    focusVisible_ = false;
    update();
}

void WdcRangePopover::mouseReleaseEvent(QMouseEvent* e) {
    const int i = buttonAt(e->position());
    const int pressed = press_;
    press_ = -1;
    update();
    if (i >= 0 && i == pressed) pick(rangeButtons().at(i));
}

void WdcRangePopover::leaveEvent(QEvent*) {
    hover_ = -1;
    update();
}

void WdcRangePopover::keyPressEvent(QKeyEvent* e) {
    const int n = int(rangeButtons().size());
    auto step = [&](int from, int dir) {
        for (int k = 1; k <= n; ++k) {
            const int j = ((from + dir * k) % n + n) % n;
            if (!dimmed_.contains(rangeButtons().at(j))) return j;
        }
        return from;
    };
    switch (e->key()) {
    case Qt::Key_Left: focus_ = step(std::max(focus_, 0), -1); break;
    case Qt::Key_Right: case Qt::Key_Tab: focus_ = step(std::max(focus_, 0), +1); break;
    case Qt::Key_Return: case Qt::Key_Enter: case Qt::Key_Space:
        if (focus_ >= 0) pick(rangeButtons().at(focus_));
        return;
    case Qt::Key_Escape: close(); return;
    default: QWidget::keyPressEvent(e); return;
    }
    focusVisible_ = true;
    update();
}

// ---- compare sources (tooltip of "So sánh biến động") ------------------------------------------------------------------

namespace {

struct WdcRangeCmpSource { const SeriesData* raw = nullptr; QString unit; };

QMutex& wdcRange_cmpMutex() {
    static QMutex m;
    return m;
}

QHash<const SeriesData*, WdcRangeCmpSource>& wdcRange_cmpMap() {
    static QHash<const SeriesData*, WdcRangeCmpSource> map;
    return map;
}

struct WdcRangeTiers { std::vector<TierSpan> spans; int refs = 0; };

QHash<const SeriesData*, WdcRangeTiers>& wdcRange_tierMap() {   // guarded by wdcRange_cmpMutex() too
    static QHash<const SeriesData*, WdcRangeTiers> map;
    return map;
}

} // namespace

void registerDashTiers(const DashData& d) {
    QMutexLocker lock(&wdcRange_cmpMutex());
    for (const SeriesEntry& e : d.series) {
        if (e.tierSpans.empty()) continue;
        WdcRangeTiers& t = wdcRange_tierMap()[&e.data];
        t.spans = e.tierSpans;
        ++t.refs;
    }
}

void unregisterDashTiers(const DashData& d) {
    QMutexLocker lock(&wdcRange_cmpMutex());
    for (const SeriesEntry& e : d.series) {
        const auto it = wdcRange_tierMap().find(&e.data);
        if (it != wdcRange_tierMap().end() && --it->refs <= 0) wdcRange_tierMap().erase(it);
    }
}

QString pointTier(const SeriesData* d, qint64 t) {
    if (!d) return QString();
    QMutexLocker lock(&wdcRange_cmpMutex());
    const auto c = wdcRange_cmpMap().constFind(d);
    const SeriesData* raw = c == wdcRange_cmpMap().cend() ? d : c->raw;
    QString tier = d->tier;
    const auto it = wdcRange_tierMap().constFind(raw);
    if (it != wdcRange_tierMap().cend())
        for (const TierSpan& s : it->spans)
            if (t >= s.from && t <= s.to) tier = s.tier;
    return tier;
}

namespace {
QHash<const ChartModel*, std::shared_ptr<const ProcessedPoints>>& wdcRange_procMap() {   // guarded by wdcRange_cmpMutex()
    static QHash<const ChartModel*, std::shared_ptr<const ProcessedPoints>> map;
    return map;
}
} // namespace

void registerProcessedPoints(const ChartModel* m, std::shared_ptr<const ProcessedPoints> processed) {
    if (!m) return;
    QMutexLocker lock(&wdcRange_cmpMutex());
    if (processed && !processed->empty()) wdcRange_procMap().insert(m, std::move(processed));
    else wdcRange_procMap().remove(m);
}

void unregisterProcessedPoints(const ChartModel* m) {
    QMutexLocker lock(&wdcRange_cmpMutex());
    wdcRange_procMap().remove(m);
}

std::optional<QPointF> processedPoint(const ChartModel* m, int refIndex, int index, size_t plotCount) {
    QMutexLocker lock(&wdcRange_cmpMutex());
    const auto it = wdcRange_procMap().constFind(m);
    if (it == wdcRange_procMap().cend() || refIndex < 0 || size_t(refIndex) >= (*it)->size()) return std::nullopt;
    const std::vector<QPointF>& s = (**it)[size_t(refIndex)];
    if (s.size() != plotCount || index < 0 || size_t(index) >= s.size()) return std::nullopt;   // not this layout
    const QPointF q = s[size_t(index)];
    if (!std::isfinite(q.x()) || !std::isfinite(q.y())) return std::nullopt;
    return q;
}

void registerCompareSource(const SeriesData* shown, const SeriesData* raw, const QString& rawUnit) {
    if (!shown || !raw) return;
    QMutexLocker lock(&wdcRange_cmpMutex());
    wdcRange_cmpMap().insert(shown, {raw, rawUnit});
}

void unregisterCompareSource(const SeriesData* shown) {
    QMutexLocker lock(&wdcRange_cmpMutex());
    wdcRange_cmpMap().remove(shown);
}

QString compareTooltipUnit(const QString& unit, const SeriesData* shown, qint64 t) {
    QMutexLocker lock(&wdcRange_cmpMutex());
    const auto it = wdcRange_cmpMap().constFind(shown);
    if (it == wdcRange_cmpMap().cend()) return unit;
    const std::vector<QPointF>& pts = it->raw->pts;
    const auto p = std::find_if(pts.begin(), pts.end(), [t](const QPointF& q) { return qint64(q.x()) == t; });
    if (p == pts.end() || !std::isfinite(p->y())) return unit;
    QString raw = QStringLiteral("(gốc ") + hcfmt::numberFormat(p->y(), 2);
    if (!it->unit.isEmpty()) raw += QLatin1Char(' ') + it->unit;
    return (unit.isEmpty() ? QString() : unit + QLatin1Char(' ')) + raw + QLatin1Char(')');
}

// ---- isStock pan -----------------------------------------------------------------------------------------------------

std::optional<PanAxis> panAxisFrom(const ChartModel& m, const ChartInput& in) {
    if (!in.spec || !in.spec->isStock || m.plotBox.isEmpty() || !(m.x.transA > 0) || !std::isfinite(m.x.min) ||
        !std::isfinite(m.x.max))
        return std::nullopt;
    double lo = INFINITY, hi = -INFINITY;
    for (size_t i = 0; i < in.refs.size() && i < in.data.size(); ++i) {
        if (!in.refs[i] || !wdcRange_visible(in, i) || !wdcRange_present(in.data[i])) continue;
        for (const QPointF& p : in.data[i]->pts) {   // getXExtremes runs over every x, null y included
            lo = std::min(lo, p.x());
            hi = std::max(hi, p.x());
        }
    }
    if (!std::isfinite(lo) || !std::isfinite(hi)) return std::nullopt;
    PanAxis a;
    a.min = m.x.min;
    a.max = m.x.max;
    a.transA = m.x.transA;
    a.minPixelPadding = m.x.minPixelPadding;
    a.len = m.plotBox.width();
    a.pos = m.plotBox.left();
    a.dataMin = lo;
    a.dataMax = hi;
    a.minPadding = in.spec->xMinPadding;
    a.maxPadding = in.spec->xMaxPadding;
    return a;
}

std::optional<std::pair<double, double>> panTransform(const PanAxis& a, double dx) {
    if (!(a.transA > 0) || !(a.len > 0)) return std::nullopt;
    const double fromCenter = a.len / 2 - a.pos;              // from.x 0, fromLength = len
    if (fromCenter < 0 || fromCenter > a.len) return std::nullopt;   // "zoom only in the pane that receives the input"
    const double toCenter = dx + a.len / 2 - a.pos;           // to.x = dx, toLength = len: scale 1
    const double minPx = fromCenter - toCenter;               // move
    auto toValue = [&](double px) { return (px - a.minPixelPadding) / a.transA + a.min; };   // Axis.translate back
    const double offset = a.minPixelPadding / a.transA;       // minPointOffset (not ordinal, not reversed)
    double newMin = toValue(minPx) + offset, newMax = toValue(minPx + a.len) - offset;
    if (newMin > newMax) std::swap(newMin, newMax);
    const double range = newMax - newMin;
    const double padRange = std::min(range, a.dataMax - a.dataMin);
    const double paddedMin = a.dataMin - padRange * (a.optMin ? 0 : a.minPadding);
    const double paddedMax = a.dataMax + padRange * (a.optMax ? 0 : a.maxPadding);
    // scale === 1: allowZoomOutside, so the current extremes widen floor and ceiling
    const double floor = std::min({a.optMin.value_or(paddedMin), paddedMin, a.min});
    const double ceiling = std::max({a.optMax.value_or(paddedMax), paddedMax, a.max});
    if (newMin < floor) { newMin = floor; newMax = newMin + range; }
    if (newMax > ceiling) { newMax = ceiling; newMin = newMax - range; }
    if ((newMin != a.min || newMax != a.max) && newMin >= floor && newMax <= ceiling)
        return std::make_pair(newMin, newMax);
    return std::nullopt;
}

void XPanState::press(QPointF chartPos) {
    down_ = true;
    cursorMove_ = false;
    downX_ = chartPos.x();
    downY_ = chartPos.y();
    hasDragged_ = 0;
}

std::optional<std::pair<double, double>> XPanState::move(QPointF chartPos, const QRectF& plot, const PanAxis& axis) {
    if (!down_) return std::nullopt;
    // Pointer.drag: the clamped position only measures the drag distance; Chart.pan uses the raw chartX.
    const double cx = std::clamp(chartPos.x(), plot.left(), plot.right());
    const double cy = std::clamp(chartPos.y(), plot.top(), plot.bottom());
    hasDragged_ = std::hypot(downX_ - cx, downY_ - cy);
    if (hasDragged_ <= kPanThreshold) return std::nullopt;
    const bool clickedInside = downX_ >= plot.left() && downX_ <= plot.right() && downY_ >= plot.top() &&
                               downY_ <= plot.bottom();
    if (!clickedInside) return std::nullopt;
    const PanAxis a = axis;
    const double fromCenter = a.len / 2 - a.pos;
    std::optional<std::pair<double, double>> r = panTransform(a, chartPos.x() - downX_);
    if (fromCenter >= 0 && fromCenter <= a.len) downX_ = chartPos.x();   // transform: mouseDownX = event.chartX
    cursorMove_ = true;                                                  // Chart.pan: container cursor 'move'
    return r;
}

void XPanState::release() {
    down_ = false;
    cursorMove_ = false;
    hasDragged_ = 0;
}

} // namespace fincept::screens::wdc
