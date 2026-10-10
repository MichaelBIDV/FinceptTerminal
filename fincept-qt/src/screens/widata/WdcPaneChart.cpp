// WdcPaneChart.cpp, package F: one chart pane outside the grid (expanded overlay, chart page). See WdcPaneChart.h.
#include "screens/widata/WdcPaneChart.h"

#include "screens/widata/WdcHcApi.h"
#include "screens/widata/WdcHcText.h"
#include "screens/widata/WdcRange.h"
#include "screens/widata/WdcTheme_p.h"

#include <QFontMetricsF>
#include <QPainter>

#include <algorithm>
#include <cmath>

namespace fincept::screens::wdc {

namespace th = theme;

namespace {

constexpr double kWdcpcBig = 2048.0;   // Inter unitsPerEm: shaping at this size is exact in font units

bool wdcpc_hasNumbers(const SeriesData& d) {
    if (d.status == Status::Missing) return false;
    return std::any_of(d.pts.begin(), d.pts.end(), [](const QPointF& p) { return std::isfinite(p.y()); });
}

bool wdcpc_opsz14(double px, int weight) { return px > 14 && (weight == 400 || weight == 500); }

} // namespace

std::optional<double> compareBase(const SeriesData& d, std::optional<qint64> axisMin) {
    // compareStart false: compareStart = 1, base = column[i] with x[i + 1] >= (xAxis.min || 0) (HS:47562-47573)
    const size_t n = d.pts.size();
    for (size_t i = 0; i + 1 < n; ++i) {
        const double v = d.pts[i].y();
        if (!std::isfinite(v) || v == 0) continue;
        if (!axisMin || d.pts[i + 1].x() >= double(*axisMin)) return v;
    }
    return std::nullopt;
}

SeriesData compareSeries(const SeriesData& d, std::optional<qint64> axisMin) {
    SeriesData out = d;
    const std::optional<double> base = compareBase(d, axisMin);
    if (!base) return out;
    for (QPointF& p : out.pts)
        if (std::isfinite(p.y())) p.setY(100.0 * (p.y() / *base) - 100.0);   // compareBase != 100 (HS:47734)
    return out;
}

double webTextExactWidth(const QString& s, double px, int weight) {
    static const TextMetrics tm = TextMetrics::native(2.0);   // exactWidth does not depend on the DPR
    if (weight != 400 && weight != 500) return tm.exactWidth(s, px, weight);
    // exactWidth is linear in px; TextMetrics picks opsz 16 from 16 px on, so the opsz 14 width of a 16 px title is
    // the 14 px width scaled
    const double at = std::min(px, 14.0), scale = px / at;
    double w = 0;
    int start = 0, cur = -1;
    for (int i = 0; i < s.size();) {
        const char32_t u = s.at(i).isHighSurrogate() && i + 1 < s.size() ? QChar::surrogateToUcs4(s.at(i), s.at(i + 1))
                                                                         : char32_t(s.at(i).unicode());
        const int k = th::webSubset(u);
        if (cur >= 0 && k != cur) {
            w += tm.exactWidth(s.mid(start, i - start), at, weight);
            start = i;
        }
        cur = k;
        i += u > 0xFFFF ? 2 : 1;
    }
    return (w + tm.exactWidth(s.mid(start), at, weight)) * scale;
}

QFont webFont(double px, int weight) {
    if (!wdcpc_opsz14(px, weight)) return th::font(px, weight);
    QFont f = th::font(14, weight);   // opsz 14 static family, drawn at px
    f.setPixelSize(int(std::lround(px)));
    return f;
}

QString webElide(const QString& s, double px, int weight, double maxWidth) {
    QFont big = webFont(px, weight);   // the outlines of webTextExactWidth, shaped at unitsPerEm
    big.setPixelSize(int(kWdcpcBig));
    return th::elideKeepSpace(s, QFontMetricsF(big), maxWidth * kWdcpcBig / px, nullptr, weight);
}

QString exportSeriesName(const SeriesRef& r, bool unitNull) {
    const QString name = th::displayName(r.nameRaw);
    return unitNull || r.unit.isEmpty() ? name : name + QStringLiteral(" (") + r.unit + QStringLiteral(")");
}

void WdcPaneChart::CompareReg::clear() {
    for (const SeriesData* k : keys) unregisterCompareSource(k);
    keys.clear();
}

void WdcPaneChart::TierReg::set(std::shared_ptr<const DashData> d) {
    if (d == data) return;
    if (data) unregisterDashTiers(*data);
    data = std::move(d);
    if (data) registerDashTiers(*data);
}

void WdcPaneChart::GroupReg::set(const ChartModel* m,
                                 std::shared_ptr<const std::vector<std::vector<QPointF>>> processed) {
    if (key) unregisterProcessedPoints(key);
    key = processed ? m : nullptr;
    if (key) registerProcessedPoints(key, std::move(processed));
}

void WdcPaneChart::setPane(const PaneSpec& pane, std::shared_ptr<const DashData> data) {
    reg_.clear();   // the raw series of the registered copies may go with the old data
    pane_ = pane;
    data_ = std::move(data);
    tiers_.set(data_);
    visible_.assign(pane_.series.size(), true);
    dirty_.on = true;
}

void WdcPaneChart::setData(std::shared_ptr<const DashData> data) {
    reg_.clear();
    data_ = std::move(data);
    tiers_.set(data_);
    dirty_.on = true;
}

void WdcPaneChart::setVisible(const std::vector<bool>& visible) {
    visible_.assign(pane_.series.size(), true);
    for (size_t i = 0; i < visible_.size() && i < visible.size(); ++i) visible_[i] = visible[i];
    dirty_.on = true;
}

void WdcPaneChart::setWindow(std::optional<qint64> xMin, std::optional<qint64> xMax, bool padAuto) {
    xMin_ = xMin;
    xMax_ = xMax;
    padAuto_ = padAuto;
    dirty_.on = true;
}

void WdcPaneChart::setSize(QSizeF size) {
    if (size == size_) return;
    size_ = size;
    dirty_.on = true;
}

void WdcPaneChart::setExpanded(bool on) {
    expanded_ = on;
    dirty_.on = true;
}

void WdcPaneChart::setMarginRight(std::optional<double> m) {
    marginRight_ = m;
    dirty_.on = true;
}

void WdcPaneChart::setCompare(bool on) {
    compare_ = on;
    dirty_.on = true;
}

const SeriesEntry* WdcPaneChart::entry(const QString& sid) const {
    if (!data_) return nullptr;
    const auto it = data_->series.constFind(sid);
    return it == data_->series.cend() ? nullptr : &it.value();
}

bool WdcPaneChart::allMissing() const {
    for (const SeriesRef& r : pane_.series) {
        const SeriesEntry* e = entry(r.sid);
        if (e && wdcpc_hasNumbers(e->data)) return false;
    }
    return true;
}

std::optional<qint64> WdcPaneChart::refMax() const {
    std::optional<qint64> best;
    for (const SeriesRef& r : pane_.series) {
        const SeriesEntry* e = entry(r.sid);
        if (!e || !wdcpc_hasNumbers(e->data)) continue;
        for (auto it = e->data.pts.rbegin(); it != e->data.pts.rend(); ++it)
            if (std::isfinite(it->y())) {
                if (!best || qint64(it->x()) > *best) best = qint64(it->x());
                break;
            }
    }
    return best;
}

void WdcPaneChart::ensure() {
    if (!dirty_.on) return;
    dirty_.on = false;
    reg_.clear();
    tiers_.set(data_);   // a copy registers its own on first use
    spec_ = pane_.chart;
    if (marginRight_) spec_.margin[1] = marginRight_;
    refs_ = pane_.series;
    cmp_.clear();
    cmp_.reserve(refs_.size());
    in_ = ChartInput{};
    in_.spec = &spec_;
    if (compare_) {
        for (YAxisSpec& y : spec_.yAxes) y.format = QStringLiteral("{value}%");
        for (SeriesRef& r : refs_) r.unit = QStringLiteral("%");
    }
    static const SeriesData kMissing{Status::Missing, QString(), QString(), {}, {}};
    for (size_t i = 0; i < refs_.size(); ++i) {
        const SeriesEntry* e = entry(refs_[i].sid);
        const SeriesData* d = e ? &e->data : &kMissing;
        if (compare_) {
            cmp_.push_back(compareSeries(*d, xMin_));
            registerCompareSource(&cmp_.back(), d, pane_.series[i].unit);   // tooltip: + raw value
            reg_.keys.push_back(&cmp_.back());
            d = &cmp_.back();   // reserve() above: no reallocation, the pointer stays valid
        }
        in_.refs.push_back(&refs_[i]);
        in_.data.push_back(d);
    }
    in_.visible = visible_;
    in_.xMin = xMin_;
    in_.xMax = xMax_;
    in_.padAuto = padAuto_;
    in_.size = size_;
    in_.profile = MetricsProfile::Native;
    in_.expanded = expanded_;
    if (allMissing() || size_.isEmpty()) {
        model_ = ChartModel{};
        model_.allMissing = true;
        grouped_.set(nullptr, nullptr);
    } else {   // layoutChart(in_) + the (t, v) behind grouped isStock points for the tooltip (DESIGN §16 C21)
        auto proc = spec_.isStock ? std::make_shared<std::vector<std::vector<QPointF>>>() : nullptr;
        model_ = layoutChartAtDpr(in_, 2.0, proc.get());
        grouped_.set(&model_, std::move(proc));
    }
}

const ChartInput* WdcPaneChart::input() {
    ensure();
    return &in_;
}

const ChartModel* WdcPaneChart::model() {
    ensure();
    return &model_;
}

std::vector<LegendEntry> WdcPaneChart::legendEntries(bool zIndexDesc) const {
    std::vector<LegendEntry> out;
    for (int i : legendOrder(pane_.series, zIndexDesc)) {
        LegendEntry e;
        e.ref = &pane_.series[size_t(i)];
        e.entry = entry(pane_.series[size_t(i)].sid);
        e.refIndex = i;
        out.push_back(e);
    }
    return out;
}

void WdcPaneChart::paint(QPainter& p, const QRectF& chartRect) {
    ensure();
    if (model_.allMissing) {   // DESIGN §8.4: no axis, no grid, label in the middle of the chart area
        p.save();
        p.setFont(th::font(th::kNeedDataPx, th::kNeedDataWeight));
        p.setPen(th::color(th::kNeedDataText));
        p.drawText(chartRect, Qt::AlignCenter, QStringLiteral("[CẦN DATA]"));
        p.restore();
        return;
    }
    p.save();
    p.translate(chartRect.topLeft());
    p.setClipRect(QRectF(QPointF(0, 0), chartRect.size()));
    paintChart(p, model_, in_);
    p.restore();
}

void WdcPaneChart::paintExportLegend(QPainter& p, const QRectF& container, LegendStyle style, bool zIndexDesc,
                                     qreal dpr) const {
    const std::vector<int> order = legendOrder(pane_.series, zIndexDesc);
    std::vector<LegendText> texts;
    for (int i : order) {
        const SeriesRef& r = pane_.series[size_t(i)];
        const bool unitNull = size_t(i) < pane_.extra.size() && pane_.extra[size_t(i)].unitNull;
        texts.push_back({exportSeriesName(r, unitNull), swatchKindFor(r)});
    }
    const LegendGeom g = layoutLegend(style, container, texts, dpr);
    p.save();
    p.setClipRect(container);
    p.setFont(th::font(th::kLegendPx, 400));
    for (size_t k = 0; k < g.items.size() && k < order.size(); ++k) {
        const int i = order[k];
        const SeriesRef& r = pane_.series[size_t(i)];
        const LegendItemGeom& it = g.items[k];
        const SeriesEntry* e = entry(r.sid);
        const bool missing = !e || !wdcpc_hasNumbers(e->data);
        const qreal base = (size_t(i) < visible_.size() && !visible_[size_t(i)]) ? th::kOffOpacity : 1.0;
        p.setOpacity(base * (missing ? th::kMissingSwatchOpacity : 1.0));
        paintSwatch(p, swatchKindFor(r), it.swatchParts, r.color, r.negativeColor.value_or(r.color));
        p.setOpacity(base);
        p.setPen(th::color(missing ? th::kMissingText : th::kTextPrimary));
        th::drawWebText(p, QPointF(it.text.x(), it.row.y() + th::blinkBaseline(th::kLegendPx, th::kLegendRowH, dpr)),
                        it.shown, 400);
    }
    p.restore();
}

} // namespace fincept::screens::wdc
