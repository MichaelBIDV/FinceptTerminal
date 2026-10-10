// WdcHcDump.cpp, package B: dumpChart, the JSON shape shared with the Highcharts oracle (package G).
// Key specification: harness/widata_clone/reports/B_dump_keys.md (schema "wdc-dump/1"), amended in ENG_w3.md
// (zoneGraphs/zoneAreas are the zone CLIP regions; a point without marker dumps as null). Coordinates are chart
// coordinates in CSS px (SVG space of the Highcharts container); numbers are full doubles, paths use SVG
// syntax with absolute commands and shortest round-trip numbers.
#include "WdcHcMath.h"
#include "WdcModel.h"

#include <QJsonArray>
#include <QJsonObject>
#include <QStringList>

#include <cmath>

namespace fincept::screens::wdc {

namespace {

QJsonValue wdcDump_num(double v) { return std::isfinite(v) ? QJsonValue(v) : QJsonValue(QJsonValue::Null); }

QString wdcDump_pathD(const QPainterPath& p) {
    QStringList parts;
    auto n = [](double v) { return hcfmt::jsNumberToString(v == 0 ? 0.0 : v); };
    for (int i = 0; i < p.elementCount(); ++i) {
        const QPainterPath::Element e = p.elementAt(i);
        if (e.type == QPainterPath::MoveToElement) {
            parts << QStringLiteral("M") << n(e.x) << n(e.y);
        } else if (e.type == QPainterPath::LineToElement) {
            parts << QStringLiteral("L") << n(e.x) << n(e.y);
        } else if (e.type == QPainterPath::CurveToElement && i + 2 < p.elementCount()) {
            const QPainterPath::Element c2 = p.elementAt(i + 1), to = p.elementAt(i + 2);
            parts << QStringLiteral("C") << n(e.x) << n(e.y) << n(c2.x) << n(c2.y) << n(to.x) << n(to.y);
            i += 2;
        }
    }
    return parts.join(QLatin1Char(' '));
}

QJsonArray wdcDump_paths(const std::vector<QPainterPath>& v) {
    QJsonArray a;
    for (const QPainterPath& p : v) a.append(wdcDump_pathD(p));
    return a;
}

QJsonObject wdcDump_axis(const AxisModel& m) {
    QJsonObject o;
    o["slot"] = m.slot;
    o["hasData"] = m.hasData;
    o["min"] = wdcDump_num(m.min);
    o["max"] = wdcDump_num(m.max);
    o["tickInterval"] = wdcDump_num(m.tickInterval);
    o["transA"] = wdcDump_num(m.transA);
    o["offset"] = wdcDump_num(m.offset);
    o["minPixelPadding"] = wdcDump_num(m.minPixelPadding);
    QJsonArray positions, ticks;
    for (const Tick& t : m.ticks) {
        positions.append(wdcDump_num(t.value));
        QJsonObject to;
        to["value"] = wdcDump_num(t.value);
        to["pixel"] = wdcDump_num(t.pixel);
        to["text"] = t.text;
        to["x"] = wdcDump_num(t.labelPos.x());
        to["y"] = wdcDump_num(t.labelPos.y());
        to["visible"] = t.visible;
        ticks.append(to);
    }
    o["tickPositions"] = positions;
    o["ticks"] = ticks;
    return o;
}

QJsonObject wdcDump_series(const SeriesGeom& g) {
    QJsonObject o;
    o["refIndex"] = g.refIndex;
    o["symbol"] = g.symbol;
    o["graph"] = wdcDump_pathD(g.graph);
    o["area"] = wdcDump_pathD(g.area);
    o["zoneGraphs"] = wdcDump_paths(g.zoneGraphs);
    o["zoneAreas"] = wdcDump_paths(g.zoneAreas);
    o["columns"] = wdcDump_paths(g.columns);
    QJsonArray markers, pts;
    for (const QRectF& r : g.markers)   // index = data point; a point without marker is null (C_requests_to_B §2)
        markers.append(r.isNull() ? QJsonValue(QJsonValue::Null)
                                  : QJsonValue(QJsonArray{wdcDump_num(r.x()), wdcDump_num(r.y()), wdcDump_num(r.width()),
                                                          wdcDump_num(r.height())}));
    for (const QPointF& p : g.plotPts) pts.append(QJsonArray{wdcDump_num(p.x()), wdcDump_num(p.y())});
    o["markers"] = markers;
    o["plotPts"] = pts;
    return o;
}

} // namespace

QJsonObject dumpChart(const ChartModel& m) {
    QJsonObject o;
    o["schema"] = QStringLiteral("wdc-dump/1");
    QJsonObject chart;
    chart["plotLeft"] = wdcDump_num(m.plotBox.x());
    chart["plotTop"] = wdcDump_num(m.plotBox.y());
    chart["plotWidth"] = wdcDump_num(m.plotBox.width());
    chart["plotHeight"] = wdcDump_num(m.plotBox.height());
    o["chart"] = chart;
    o["allMissing"] = m.allMissing;
    o["xAxis"] = wdcDump_axis(m.x);
    QJsonArray ys;
    for (const AxisModel& a : m.y) ys.append(wdcDump_axis(a));
    o["yAxis"] = ys;
    QJsonArray series;
    for (const SeriesGeom& g : m.series) series.append(wdcDump_series(g));
    o["series"] = series;
    return o;
}

} // namespace fincept::screens::wdc
