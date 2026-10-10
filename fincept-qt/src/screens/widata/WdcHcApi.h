#pragma once
// WdcHcApi.h, engine entry points beyond the frozen WdcModel.h (package ENG, waves 3 and 4).
//
// ChartInput has no device pixel ratio, but the Native text profile needs one (DESIGN §16 C13: Blink rounds
// the label bbox height to device pixels, 15 px for a 12 px label at DPR 1, 14.5 at DPR 2). layoutChart(in)
// keeps the Retina default (DPR 2); a caller that knows the DPR of the target surface (card pixmap, harness)
// calls layoutChartAtDpr. Proposal recorded for DESIGN §13: add `double dpr` to ChartInput.
#include "WdcModel.h"

#include <vector>

namespace fincept::screens::wdc {

ChartModel layoutChartAtDpr(const ChartInput& in, double dpr);   // WdcHcLayout.cpp; dpr <= 0 means 2

// dataGrouping of the isStock charts (DESIGN §16 C21, ENG2 w4): Highstock averages daily data into day/week/month
// groups when the points outnumber plotWidth / 2. A grouped series keeps SeriesGeom::plotPts / markers indexed like
// its data sorted by x: the group's point sits at the index of its first raw point, every other index is NaN /
// null. `processed` (same run, optional) gives the (t, v) Highstock holds behind each plotPts index: group start and
// average for a grouped series, the data itself otherwise (NaN where nothing is drawn). Tooltip / hit test of a
// grouped series should read t and v there; the raw point at that index is only the first of the group.
ChartModel layoutChartAtDpr(const ChartInput& in, double dpr, std::vector<std::vector<QPointF>>* processed);

} // namespace fincept::screens::wdc
