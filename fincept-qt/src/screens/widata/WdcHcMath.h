#pragma once
// WdcHcMath.h, pure math of the Highcharts 12.3.0 port (package B). No QtGui dependency.
// Signatures follow analysis/ENGINE_SPEC.md §6.2; every function cites the HS line it mirrors
// (HS = vendor/highcharts-12.3.0/highstock.src.js).
#include <QString>
#include <QtGlobal>

#include <vector>

namespace fincept::screens::wdc {

namespace hcmath {
double jsRound(double x);                                  // Math.round: floor(x + 0.5)
double jsToPrecision(double x, int precision);             // parseFloat(x.toPrecision(p)), exact JS rounding
double correctFloat(double x, int precision = 14);         // HS:1166
double crisp(double v, double lineWidth = 0);              // HS:346
double magnitude(double x);                                // getMagnitude HS:965
// HS:997-1039. multiples == nullptr: default list; magnitude NaN: getMagnitude(interval).
// allowDecimals: 1 true, 0 false, -1 undefined.
double normalizeTickInterval(double interval, const std::vector<double>* multiples, double magnitude,
                             int allowDecimals, bool hasTickAmount);
std::vector<double> getLinearTickPositions(double tickInterval, double min, double max);   // HS:19627-19656
double getClosestDistance(const std::vector<double>& xs);  // HS:1222 (one array); NaN when undefined
} // namespace hcmath

namespace hctime {   // always UTC (time.timezone = UTC at WiData)
struct TimeUnit {
    enum Name { Millisecond, Second, Minute, Hour, Day, Week, Month, Year };
    Name name = Year;
    double unitRange = 0;   // ms of one unit (month 28 days, year 364 days, HS:1175-1184)
    double count = 1;
};
QString unitName(TimeUnit::Name n);
double unitMs(TimeUnit::Name n);
TimeUnit normalizeTimeTickInterval(double tickInterval);                           // HS:22325-22386
// dataGrouping units (HS:58642-58676: day [1], week [1], month [1, 3, 6]) instead of the axis tick units.
TimeUnit normalizeTimeTickInterval(double tickInterval, bool dataGroupingUnits);
std::vector<double> getTimeTicks(const TimeUnit& u, double min, double max, int startOfWeek = 1);   // HS:4373
double makeTime(int year, int month, double day = 1, double hours = 0, double minutes = 0, double seconds = 0,
                double ms = 0);                                                    // Date.UTC with overflow
void toParts(double t, int& year, int& month, int& day, int& hours, int& minutes, int& seconds, int& ms,
             int& weekday);                                                        // weekday 0 = Sunday
QString dateFormat(const QString& fmt, double t);   // %Y %y %m %d %e %H %M %S %L %b %B %a %A %%
} // namespace hctime

namespace hcfmt {
QString jsNumberToString(double v);                 // Number.prototype.toString()
// numberFormat (HS:9367-9437) with lang thousandsSep ',' decimalPoint '.' (WiData); decimals -1 = keep.
QString numberFormat(double v, int decimals, const QString& decimalPoint = QStringLiteral("."),
                     const QString& thousandsSep = QStringLiteral(","));
QString defaultLabel(double value, double tickInterval);   // defaultLabelFormatter HS:19306, symbols K M G T P E
QString formatTemplate(const QString& tpl, double value); // Templating.format for "{value}" (HS:9175-9340)
// Y axis label text: labels.format set ? formatTemplate(format) : defaultLabel.
QString yLabel(const QString& format, double value, double tickInterval);
} // namespace hcfmt

} // namespace fincept::screens::wdc
