#pragma once
// WdcData.h: reading the builder output (schema widata_clone/1) and assembling ChartInput. Package E.
// Contract: DESIGN §4 (current.json, manifest, layouts.json, dash_<id>.json), §4.8 (only place where form
// meets data), INT §3.4 (read rules). Every function that touches the disk is blocking and meant for a
// worker thread (QtConcurrent::run); parse* functions are pure. All file reads go through
// readFileCounted() so the harness can prove that nothing is read on the GUI thread (ioStats()).
#include "WdcModel.h"

#include <QByteArray>
#include <QJsonObject>
#include <QStringList>

#include <memory>

namespace fincept::screens::wdc {

inline constexpr char kWdcSchema[] = "widata_clone/1";

// ---- form (layouts.json / layout_const.json, DESIGN §4.6) ------------------------------------------

struct SeriesExtra {                       // SeriesRef fields that WdcModel.h does not carry
    std::optional<QColor> swatchPos, swatchNeg;   // "swatch2" (legend 2 colours, UI §3.4)
    bool unitNull = false;                 // "unit": null in the source (CRI N7: same as "")
    QStringList inferred;                  // "_inferred"
};

struct PaneSpec {
    ChartSpec chart;
    std::vector<SeriesRef> series;
    std::vector<SeriesExtra> extra;                        // parallel to series
    std::vector<std::optional<double>> yTickPixelInterval; // parallel to chart.yAxes (80 aio, null isStock)
    QJsonObject raw;                       // the pane "chart" object as read (x.crosshair, plot.lineShadow...)
};

struct GridPos { int x = 0, y = 0, w = 4, h = 4; std::optional<int> minW, minH; };
struct RangeSpec { QString button = QStringLiteral("3Y"); std::optional<int> days; QString reason; };

struct CardSpec {
    QString key, kind, title;              // title = detail_name verbatim (may end with a space)
    GridPos grid;
    QStringList buttons;                   // aio: calendar, expand, settings; macro: sync first
    QString legendStyle, legendOrder;      // "aio"|"macro", "zIndex_desc"|"series"
    RangeSpec defaultRange;
    bool allExact = false, alignPanesRight = false;
    std::vector<PaneSpec> panes;           // 1, or 2 for the split cards
    bool isMacro() const { return kind == QLatin1String("macro"); }
};

struct DashSpec {
    QString id, name;
    std::vector<CardSpec> cards;
    const CardSpec* card(const QString& key) const;
    int maxRow() const;                    // max(y + h), 0 when empty
};

struct SingleChartSpec {                   // DESIGN §16 C4, layout_const "single_charts"
    QString id, title, defaultRange;
    PaneSpec pane;
    QJsonObject page;                      // DOM geometry of the single-chart page (package F)
};

struct LayoutsDoc {
    QString schema;
    QStringList tabOrder;                  // ids, tab order (meta.layoutList)
    QString defaultDash;
    std::vector<DashSpec> dashboards;      // sorted by tabOrder
    std::vector<SingleChartSpec> singleCharts;
    bool fromLayoutConst = false;          // no usable build: form only, every series [CẦN DATA]
    QStringList warnings;
    const DashSpec* dash(const QString& id) const;
    const SingleChartSpec* single(const QString& id) const;
    int cardCount() const;
};

// ---- data (dash_<id>.json, DESIGN §4.7) ------------------------------------------------------------

struct TierSpan { qint64 from = 0, to = 0; QString tier; };
struct SeriesMeta { QString name, sourceName, sourceRef, release, lastUpdated; QStringList notes; };

struct SeriesEntry {
    SeriesData data{Status::Missing, {}, {}, {}, {}};   // pts: x = t_ms, y = NaN for null
    QString unit, asOf, reason;
    QStringList partialReasons;
    std::vector<TierSpan> tierSpans;
    SeriesMeta meta;
    bool present = false;                  // false: sid absent from the file (synthesised missing)
};

struct DashData {
    QString dashId, generated;
    QHash<QString, SeriesEntry> series;
    QStringList warnings;
};

// Never null. Absent sid, or d == nullptr (build missing/broken, data not loaded): a shared missing entry.
const SeriesEntry& seriesFor(const DashData* d, const QString& sid);

// ---- build pointer (current.json, DESIGN §4.4, §4.5) ------------------------------------------------

struct BuildState {
    QString stateDir, buildDir, generated, policy;
    QJsonObject manifest;
    QString error, errorCode;              // errorCode empty = ok
    bool ok() const { return errorCode.isEmpty(); }
};

template <typename T> struct Loaded {
    std::shared_ptr<const T> value;
    QString error, errorCode;              // codes: no_file, read_error, bad_json, bad_schema, id_mismatch
    bool ok() const { return value != nullptr; }
};

QString defaultStateDir();                 // $WDC_STATE_DIR | ${WDC_SYSTEM_DIR:-~/SECOND BRAIN-OBSIDIAN/_System}/fincept_bridge/state/widata_clone
QString defaultLayoutConstPath();          // $WDC_LAYOUT_CONST | <system>/fincept_bridge/data/widata_clone/layout_const.json

BuildState readCurrent(const QString& stateDir);                                    // disk
Loaded<LayoutsDoc> loadLayoutsFile(const QString& path, bool requireSchema);         // disk
// layouts.json of the build; when the build is unusable, layout_const.json (fromLayoutConst = true).
Loaded<LayoutsDoc> loadLayouts(const BuildState& b, const QString& layoutConstPath);  // disk
Loaded<DashData> loadDash(const QString& buildDir, const QString& dashId);             // disk: dash_<id>.json
Loaded<DashData> loadSingle(const QString& buildDir, const QString& singleId);         // disk: single_<id>.json

Loaded<LayoutsDoc> parseLayouts(const QByteArray& json, bool requireSchema);          // pure
Loaded<DashData> parseDash(const QByteArray& json, const QString& expectId);          // pure

// ---- assembly (DESIGN §4.8, §7.2) --------------------------------------------------------------------

// refMax: max t of the last non-null point over every ok/partial series of the card (both panes).
std::optional<qint64> cardRefMax(const CardSpec& c, const DashData* d);
bool cardHasData(const CardSpec& c, const DashData* d);   // at least one ok/partial series
bool paneHasData(const PaneSpec& p, const DashData* d);

// The returned ChartInput points into `pane` and `*d`; the caller keeps both alive (shared_ptr).
ChartInput makeChartInput(const PaneSpec& pane, const DashData* d, QSizeF size,
                          std::optional<qint64> xMin, std::optional<qint64> xMax, bool padAuto,
                          MetricsProfile profile = MetricsProfile::Native, bool expanded = false);

// ---- CSS colour (pure) -------------------------------------------------------------------------------

// "#rgb", "#rgba", "#rrggbb", "#rrggbbaa" (alpha LAST, as CSS; QColor::fromString reads 8 digits as #AARRGGBB),
// "rgb(r, g, b)", "rgba(r, g, b, a)" (a in 0..1), else QColor::fromString (names). Invalid QColor on failure.
QColor parseCssColor(const QString& css);

// ---- disk I/O accounting (TASKS E: "không I/O đĩa trên luồng UI") ------------------------------------

struct IoStats { int guiReads = 0, workerReads = 0, guiWrites = 0, workerWrites = 0; QStringList guiPaths; };
IoStats ioStats();
void resetIoStats();
QByteArray readFileCounted(const QString& path, QString* error);          // empty + error on failure
bool writeFileCounted(const QString& path, const QByteArray& bytes, QString* error);   // atomic (QSaveFile)
bool fileExistsCounted(const QString& path);                              // stat, counted as a read

} // namespace fincept::screens::wdc
