#pragma once
// WdcPaneChart.h: one chart pane outside the grid (package F), shared by WdcExpanded (overlay) and WdcSingle (chart
// page). Holds a copy of the pane spec, the dashboard data, legend visibility, the X window, the chart size and the
// two page modes, and hands ChartInput / ChartModel to the engine (layoutChart of B, paintChart of C) exactly like
// WdcCard does for a grid pane (DESIGN §4.8, §5.4).
//
//   expanded   ChartInput.expanded = true (Y labels 11 px), DESIGN §6, §6.2
//   compare    "So sánh biến động" of the chart page (DESIGN §16 C4): Highstock compare: 'percent'
//              (HS:47547-47575 afterProcessData, HS:47715-47745 modifyValue): base = first numeric, non-zero y at
//              index i such that x[i + 1] >= axis min (compareStart false), y' = 100 * y / base - 100; the Y axis
//              format becomes "{value}%" and the tooltip unit "%", followed by the raw value in brackets
//              (MẶC ĐỊNH đợt 4, registerCompareSource of WdcRange.h)
//   export     nameExportPNG = name + " (" + unit + ")", no brackets when the unit is empty (BEH §8, FACT 451/451)
#include "screens/widata/WdcData.h"
#include "screens/widata/WdcLegend.h"
#include "screens/widata/WdcModel.h"

#include <QFont>
#include <QImage>
#include <QRectF>
#include <QString>

#include <memory>
#include <optional>
#include <vector>

class QPainter;

namespace fincept::screens::wdc {

/// Compare base of one series for an axis minimum (nullopt: no minimum, the axis starts at or before the data).
std::optional<double> compareBase(const SeriesData& d, std::optional<qint64> axisMin);
/// Copy of `d` with every finite y mapped to 100 * y / base - 100 (unchanged copy when there is no base).
SeriesData compareSeries(const SeriesData& d, std::optional<qint64> axisMin);
/// Advance of a label as Chromium lays it out on WiData: one shaping run per Google Fonts subset for weights 400/500
/// (theme::webSubset, package D finding), each run measured at 2048 px like TextMetrics::exactWidth (T00). Weights
/// 400/500 always use the opsz 14 outlines, 16 px titles included: WiData serves them as static Google Fonts subsets
/// (FACT: the chart-page h6 "MAI3.09 M2, GDP và Tín dụng" 16/500 is 230.41 wide; opsz 14 gives 230.40, opsz 16 228.61).
double webTextExactWidth(const QString& s, double px, int weight);
/// The QFont that draws such a label (opsz 14 outlines for 400/500 at any size, theme::font otherwise).
QFont webFont(double px, int weight);
/// text-overflow: ellipsis (theme::elideKeepSpace) with the widths of webTextExactWidth.
QString webElide(const QString& s, double px, int weight, double maxWidth);
/// nameExportPNG (BEH §8): collapsed name + " (unit)".
QString exportSeriesName(const SeriesRef& r, bool unitNull = false);

class WdcPaneChart {
  public:
    void setPane(const PaneSpec& pane, std::shared_ptr<const DashData> data);
    void setData(std::shared_ptr<const DashData> data);
    const PaneSpec& pane() const { return pane_; }
    const std::shared_ptr<const DashData>& data() const { return data_; }

    void setVisible(const std::vector<bool>& visible);   // by ref index; missing entries = visible
    const std::vector<bool>& visible() const { return visible_; }
    void setWindow(std::optional<qint64> xMin, std::optional<qint64> xMax, bool padAuto);
    std::optional<qint64> xMin() const { return xMin_; }
    std::optional<qint64> xMax() const { return xMax_; }
    bool padAuto() const { return padAuto_; }
    void setSize(QSizeF size);
    QSizeF size() const { return size_; }
    void setExpanded(bool on);
    void setCompare(bool on);
    bool compare() const { return compare_; }
    /// chart.marginRight forced by the pane alignment of 2-pane cards (DESIGN §4.6 "Lề canh hàng"); nullopt = spec.
    void setMarginRight(std::optional<double> m);

    bool allMissing() const;                     // no series of the pane has a number
    std::optional<qint64> refMax() const;        // DESIGN §7.2, this pane only
    const ChartInput* input();                   // lays out on demand
    const ChartModel* model();
    void invalidate() { dirty_.on = true; }

    /// Legend entries in display order (zIndex_desc for aio cards and the chart page, series order for macro).
    std::vector<LegendEntry> legendEntries(bool zIndexDesc) const;
    /// Chart (or "[CẦN DATA]", DESIGN §8.4) into `chartRect`; p is in the caller's coordinates.
    void paint(QPainter& p, const QRectF& chartRect);
    /// Export legend: layoutLegend(style) with nameExportPNG texts, swatches, off series at 0.4 (BEH §5.2).
    void paintExportLegend(QPainter& p, const QRectF& container, LegendStyle style, bool zIndexDesc, qreal dpr) const;

  private:
    void ensure();
    const SeriesEntry* entry(const QString& sid) const;

    // Derived state points into this object (in_ -> spec_/refs_/cmp_, registered compare copies): a copy starts dirty
    // and registers nothing, so it rebuilds its own on first use instead of reading the source's members.
    struct Dirty {
        bool on = true;
        Dirty() = default;
        Dirty(const Dirty&) {}
        Dirty& operator=(const Dirty&) { on = true; return *this; }
    };
    struct CompareReg {   // compare copies registered for the tooltip (registerCompareSource, WdcRange.h)
        std::vector<const SeriesData*> keys;
        CompareReg() = default;
        CompareReg(const CompareReg&) {}
        CompareReg& operator=(const CompareReg&) { clear(); return *this; }
        ~CompareReg() { clear(); }
        void clear();
    };
    struct TierReg {      // data whose tier_spans the tooltip reads (registerDashTiers, WdcRange.h)
        std::shared_ptr<const DashData> data;
        TierReg() = default;
        TierReg(const TierReg&) {}
        TierReg& operator=(const TierReg&) { set(nullptr); return *this; }
        ~TierReg() { set(nullptr); }
        void set(std::shared_ptr<const DashData> d);
    };
    struct GroupReg {     // grouped isStock points of model_ for hitTest (registerProcessedPoints, WdcRange.h)
        const ChartModel* key = nullptr;
        GroupReg() = default;
        GroupReg(const GroupReg&) {}
        GroupReg& operator=(const GroupReg&) { set(nullptr, nullptr); return *this; }
        ~GroupReg() { set(nullptr, nullptr); }
        void set(const ChartModel* m, std::shared_ptr<const std::vector<std::vector<QPointF>>> processed);
    };

    PaneSpec pane_;
    std::shared_ptr<const DashData> data_;
    std::vector<bool> visible_;
    std::optional<qint64> xMin_, xMax_;
    bool padAuto_ = true, expanded_ = false, compare_ = false;
    Dirty dirty_;
    std::optional<double> marginRight_;
    QSizeF size_;
    ChartSpec spec_{};
    std::vector<SeriesRef> refs_;               // copies (unit "%" in compare mode)
    std::vector<SeriesData> cmp_;               // compare copies
    CompareReg reg_;                            // after cmp_: unregistered before the copies are freed
    TierReg tiers_;
    ChartInput in_{};
    ChartModel model_{};
    GroupReg grouped_;                          // after model_: unregistered before the model goes
};

} // namespace fincept::screens::wdc
