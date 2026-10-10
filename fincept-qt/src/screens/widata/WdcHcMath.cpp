// WdcHcMath.cpp, package B: hcmath / hctime / hcfmt, a line-by-line port of the Highcharts 12.3.0 helpers
// cited in WdcHcMath.h. Exact JavaScript number semantics (toPrecision, toString, Intl rounding) are
// reproduced on the decimal expansion of the double so that T01, T02, T08 match node bit for bit.
#include "WdcHcMath.h"

#include <QStringList>

#include <algorithm>
#include <cmath>
#include <cstdio>
#include <cstdlib>
#include <limits>
#include <string>

// Highcharts runs in JavaScript: no fused multiply-add. Clang contracts a*b+c into FMA by default
// (-ffp-contract=on), which flips spline clamps and tick comparisons by one ulp (ENG_w3 §2).
#if defined(__clang__)
#pragma clang fp contract(off)
#elif defined(__GNUC__)
#pragma GCC optimize("fp-contract=off")
#endif

namespace fincept::screens::wdc {

namespace {

constexpr double kNaN = std::numeric_limits<double>::quiet_NaN();
constexpr double kLN10 = 2.302585092994046;   // Math.LN10

// Exact decimal digits of |x| (x finite, non zero): digits without the point, decimal exponent of digit 0.
void wdcMath_exactDigits(double x, std::string& digits, int& exp10) {
    char buf[128];
    std::snprintf(buf, sizeof buf, "%.70e", std::fabs(x));
    const std::string s(buf);
    const size_t e = s.find('e');
    digits.clear();
    for (size_t i = 0; i < e; ++i)
        if (s[i] != '.') digits.push_back(s[i]);
    exp10 = std::atoi(s.c_str() + e + 1);
}

// Round a digit string to `keep` digits, half up on the magnitude (JS toPrecision / Intl halfExpand).
// Returns the kept digits; exp10 is bumped when the rounding carries out (999 -> 1000).
std::string wdcMath_roundDigits(const std::string& digits, int keep, int& exp10) {
    if (keep <= 0) {
        // all digits dropped: result is 0 or one unit at the first kept position
        const bool up = keep == 0 && !digits.empty() && digits[0] >= '5';
        if (up) { exp10 += 1; return "1"; }
        return "";
    }
    std::string head = digits.substr(0, std::min<size_t>(keep, digits.size()));
    while (int(head.size()) < keep) head.push_back('0');
    if (int(digits.size()) > keep && digits[keep] >= '5') {
        int i = keep - 1;
        while (i >= 0 && head[i] == '9') { head[i] = '0'; --i; }
        if (i < 0) { head.insert(head.begin(), '1'); head.pop_back(); exp10 += 1; }
        else head[i] = char(head[i] + 1);
    }
    return head;
}

double wdcMath_fromDigits(bool neg, const std::string& d, int exp10) {
    std::string s = (neg ? "-" : "") + d.substr(0, 1) + "." + (d.size() > 1 ? d.substr(1) : "0") + "e" +
                    std::to_string(exp10);
    return std::strtod(s.c_str(), nullptr);
}

// Shortest round-trip digits (ECMAScript Number::toString step 5).
void wdcMath_shortest(double x, std::string& digits, int& n) {
    char buf[64];
    for (int p = 1; p <= 17; ++p) {
        std::snprintf(buf, sizeof buf, "%.*e", p - 1, std::fabs(x));
        if (std::strtod(buf, nullptr) == std::fabs(x)) break;
    }
    const std::string s(buf);
    const size_t e = s.find('e');
    digits.clear();
    for (size_t i = 0; i < e; ++i)
        if (s[i] != '.') digits.push_back(s[i]);
    while (digits.size() > 1 && digits.back() == '0') digits.pop_back();
    n = std::atoi(s.c_str() + e + 1) + 1;
}

// Intl.NumberFormat('en', {minimumFractionDigits: f, maximumFractionDigits: f, useGrouping}) as V8/ICU does
// it: the double becomes its shortest round-trip decimal (ICU DecimalQuantity), then halfExpand to f decimals
// (measured against node: exact-binary rounding differs for ...402.805 and for > 17 digit integers).
// Returns "-" prefixed for negatives (U+002D like V8 'en').
QString wdcMath_intlFixed(double v, int f, bool grouping) {
    if (v == 0 || !std::isfinite(v)) {
        QString z = QStringLiteral("0");
        if (f > 0) z += QStringLiteral(".") + QString(f, QLatin1Char('0'));
        return (std::signbit(v) && v == 0) ? QStringLiteral("-") + z : z;
    }
    std::string digits;
    int e = 0;
    wdcMath_shortest(v, digits, e);
    e -= 1;   // wdcMath_shortest returns n (= exponent + 1)
    // keep digits up to 10^-f: count = e + 1 + f
    std::string kept = wdcMath_roundDigits(digits, e + 1 + f, e);
    std::string intPart, frac;
    if (kept.empty()) { intPart = "0"; frac = std::string(f, '0'); }
    else {
        const int intLen = e + 1;
        if (intLen <= 0) {
            intPart = "0";
            frac = std::string(-intLen, '0') + kept;
        } else {
            while (int(kept.size()) < intLen + f) kept.push_back('0');
            intPart = kept.substr(0, intLen);
            frac = kept.substr(intLen);
        }
        frac.resize(f, '0');
    }
    std::string grouped;
    for (size_t i = 0; i < intPart.size(); ++i) {
        if (grouping && i > 0 && (intPart.size() - i) % 3 == 0) grouped.push_back(',');
        grouped.push_back(intPart[i]);
    }
    std::string out = (v < 0 ? "-" : "") + grouped + (f > 0 ? "." + frac : "");
    return QString::fromStdString(out);
}

// Days since 1970-01-01 for a proleptic Gregorian date (month 1..12), Howard Hinnant's algorithm.
long long wdcMath_daysFromCivil(long long y, unsigned m, unsigned d) {
    y -= m <= 2;
    const long long era = (y >= 0 ? y : y - 399) / 400;
    const unsigned yoe = unsigned(y - era * 400);
    const unsigned doy = (153 * (m + (m > 2 ? -3 : 9)) + 2) / 5 + d - 1;
    const unsigned doe = yoe * 365 + yoe / 4 - yoe / 100 + doy;
    return era * 146097 + (long long)doe - 719468;
}

void wdcMath_civilFromDays(long long z, int& y, int& m, int& d) {
    z += 719468;
    const long long era = (z >= 0 ? z : z - 146096) / 146097;
    const unsigned doe = unsigned(z - era * 146097);
    const unsigned yoe = (doe - doe / 1460 + doe / 36524 - doe / 146096) / 365;
    const unsigned doy = doe - (365 * yoe + yoe / 4 - yoe / 100);
    const unsigned mp = (5 * doy + 2) / 153;
    d = int(doy - (153 * mp + 2) / 5 + 1);
    m = int(mp < 10 ? mp + 3 : mp - 9);
    y = int(yoe + era * 400 + (m <= 2));
}

} // namespace

// ---------------------------------------------------------------- hcmath

namespace hcmath {

double jsRound(double x) { return std::floor(x + 0.5); }

double jsToPrecision(double x, int precision) {
    if (!std::isfinite(x) || x == 0) return x;
    std::string digits;
    int e = 0;
    wdcMath_exactDigits(x, digits, e);
    const std::string kept = wdcMath_roundDigits(digits, precision, e);
    return wdcMath_fromDigits(x < 0, kept, e);
}

double correctFloat(double x, int precision) { return x > 1e14 ? x : jsToPrecision(x, precision); }

double crisp(double v, double lineWidth) {
    const double mod = std::fmod(lineWidth, 2.0) / 2.0;
    return jsRound(v - mod) + mod;
}

double magnitude(double x) { return std::pow(10.0, std::floor(std::log(x) / kLN10)); }

double normalizeTickInterval(double interval, const std::vector<double>* multiplesIn, double mag,
                             int allowDecimals, bool hasTickAmount) {
    double retInterval = interval;
    mag = std::isnan(mag) ? magnitude(interval) : mag;
    const double normalized = interval / mag;
    std::vector<double> multiples;
    if (!multiplesIn) {
        multiples = hasTickAmount ? std::vector<double>{1, 1.2, 1.5, 2, 2.5, 3, 4, 5, 6, 8, 10}
                                  : std::vector<double>{1, 2, 2.5, 5, 10};
        if (allowDecimals == 0) {
            if (mag == 1) {
                std::vector<double> f;
                for (double m : multiples)
                    if (std::fmod(m, 1.0) == 0) f.push_back(m);
                multiples = f;
            } else if (mag <= 0.1) {
                multiples = {1 / mag};
            }
        }
    } else {
        multiples = *multiplesIn;
    }
    for (size_t i = 0; i < multiples.size(); ++i) {
        retInterval = multiples[i];
        const double next = i + 1 < multiples.size() ? multiples[i + 1] : multiples[i];
        if ((hasTickAmount && retInterval * mag >= interval) ||
            (!hasTickAmount && normalized <= (multiples[i] + next) / 2))
            break;
    }
    const int prec = int(-jsRound(std::log(0.001) / kLN10));   // = 3
    return correctFloat(retInterval * mag, prec);
}

std::vector<double> getLinearTickPositions(double tickInterval, double min, double max) {
    const double roundedMin = correctFloat(std::floor(min / tickInterval) * tickInterval);
    const double roundedMax = correctFloat(std::ceil(max / tickInterval) * tickInterval);
    std::vector<double> ticks;
    const int precision = correctFloat(roundedMin + tickInterval) == roundedMin ? 20 : 14;
    double pos = roundedMin, lastPos = kNaN;
    while (pos <= roundedMax) {
        ticks.push_back(pos);
        pos = correctFloat(pos + tickInterval, precision);
        if (pos == lastPos) break;
        lastPos = pos;
        if (ticks.size() > 100000) break;   // guard (HS relies on error 19 before reaching here)
    }
    return ticks;
}

double getClosestDistance(const std::vector<double>& xs) {
    double closest = kNaN;
    for (size_t i = xs.size() > 1 ? xs.size() - 1 : 0; i > 0; --i) {
        const double d = xs[i] - xs[i - 1];
        if (d > 0 && (std::isnan(closest) || d < closest)) closest = d;
    }
    return closest;
}

} // namespace hcmath

// ---------------------------------------------------------------- hctime

namespace hctime {

double unitMs(TimeUnit::Name n) {
    switch (n) {
    case TimeUnit::Millisecond: return 1;
    case TimeUnit::Second: return 1000;
    case TimeUnit::Minute: return 60000;
    case TimeUnit::Hour: return 3600000;
    case TimeUnit::Day: return 24 * 3600000.0;
    case TimeUnit::Week: return 7 * 24 * 3600000.0;
    case TimeUnit::Month: return 28 * 24 * 3600000.0;
    case TimeUnit::Year: return 364 * 24 * 3600000.0;
    }
    return 1;
}

QString unitName(TimeUnit::Name n) {
    static const char* names[] = {"millisecond", "second", "minute", "hour", "day", "week", "month", "year"};
    return QString::fromLatin1(names[int(n)]);
}

TimeUnit normalizeTimeTickInterval(double tickInterval) { return normalizeTimeTickInterval(tickInterval, false); }

TimeUnit normalizeTimeTickInterval(double tickInterval, bool dataGroupingUnits) {
    struct U { TimeUnit::Name n; std::vector<double> m; };
    static const std::vector<U> axisUnits = {
        {TimeUnit::Millisecond, {1, 2, 5, 10, 20, 25, 50, 100, 200, 500}}, {TimeUnit::Second, {1, 2, 5, 10, 15, 30}},
        {TimeUnit::Minute, {1, 2, 5, 10, 15, 30}}, {TimeUnit::Hour, {1, 2, 3, 4, 6, 8, 12}},
        {TimeUnit::Day, {1, 2}}, {TimeUnit::Week, {1, 2}}, {TimeUnit::Month, {1, 2, 3, 4, 6}}, {TimeUnit::Year, {}}};
    static const std::vector<U> groupUnits = {
        {TimeUnit::Millisecond, {1, 2, 5, 10, 20, 25, 50, 100, 200, 500}}, {TimeUnit::Second, {1, 2, 5, 10, 15, 30}},
        {TimeUnit::Minute, {1, 2, 5, 10, 15, 30}}, {TimeUnit::Hour, {1, 2, 3, 4, 6, 8, 12}},
        {TimeUnit::Day, {1}}, {TimeUnit::Week, {1}}, {TimeUnit::Month, {1, 3, 6}}, {TimeUnit::Year, {}}};
    const std::vector<U>& units = dataGroupingUnits ? groupUnits : axisUnits;
    size_t i = 0;
    for (; i < units.size(); ++i) {
        if (i + 1 < units.size()) {
            const double lessThan = (unitMs(units[i].n) * units[i].m.back() + unitMs(units[i + 1].n)) / 2;
            if (tickInterval <= lessThan) break;
        }
    }
    if (i >= units.size()) i = units.size() - 1;
    const U& u = units[i];
    const double interval = unitMs(u.n);
    std::vector<double> multiples = u.m;
    const bool nullMultiples = u.n == TimeUnit::Year;
    if (interval == unitMs(TimeUnit::Year) && tickInterval < 5 * interval) multiples = {1, 2, 5};
    const bool useNull = nullMultiples && multiples.empty();
    const double mag = u.n == TimeUnit::Year ? std::max(hcmath::magnitude(tickInterval / interval), 1.0) : 1.0;
    TimeUnit r;
    r.name = u.n;
    r.unitRange = interval;
    r.count = hcmath::normalizeTickInterval(tickInterval / interval, useNull ? nullptr : &multiples, mag, -1, false);
    return r;
}

double makeTime(int year, int month, double day, double hours, double minutes, double seconds, double ms) {
    long long y = year + (long long)std::floor(month / 12.0);
    const int m = ((month % 12) + 12) % 12;
    const double days = double(wdcMath_daysFromCivil(y, unsigned(m + 1), 1)) + (day - 1);
    return days * 86400000.0 + hours * 3600000.0 + minutes * 60000.0 + seconds * 1000.0 + ms;
}

void toParts(double t, int& year, int& month, int& day, int& hours, int& minutes, int& seconds, int& ms,
             int& weekday) {
    const double dayMs = 86400000.0;
    const double days = std::floor(t / dayMs);
    double rem = t - days * dayMs;
    int y, m, d;
    wdcMath_civilFromDays((long long)days, y, m, d);
    year = y; month = m - 1; day = d;
    hours = int(rem / 3600000.0); rem -= hours * 3600000.0;
    minutes = int(rem / 60000.0); rem -= minutes * 60000.0;
    seconds = int(rem / 1000.0); rem -= seconds * 1000.0;
    ms = int(rem);
    weekday = int((((long long)days % 7) + 11) % 7);   // 1970-01-01 was a Thursday (4)
}

std::vector<double> getTimeTicks(const TimeUnit& u, double min, double max, int startOfWeek) {
    std::vector<double> ticks;
    const double count = u.count, unitRange = u.unitRange;
    int year, month, dayOfMonth, hours, minutes, seconds, msPart, wd;
    toParts(min, year, month, dayOfMonth, hours, minutes, seconds, msPart, wd);
    double milliseconds = std::fmod(min, 1000.0);
    const double S = unitMs(TimeUnit::Second), MI = unitMs(TimeUnit::Minute), H = unitMs(TimeUnit::Hour);
    const double D = unitMs(TimeUnit::Day), MO = unitMs(TimeUnit::Month), Y = unitMs(TimeUnit::Year);
    double sec = seconds, mins = minutes, hrs = hours, dom = dayOfMonth, mon = month, yr = year;
    milliseconds = unitRange >= S ? 0 : count * std::floor(milliseconds / count);
    if (unitRange >= S) sec = unitRange >= MI ? 0 : count * std::floor(sec / count);
    if (unitRange >= MI) mins = unitRange >= H ? 0 : count * std::floor(mins / count);
    if (unitRange >= H) hrs = unitRange >= D ? 0 : count * std::floor(hrs / count);
    if (unitRange >= D) dom = unitRange >= MO ? 1 : std::max(1.0, count * std::floor(dom / count));
    if (unitRange >= MO) mon = unitRange >= Y ? 0 : count * std::floor(mon / count);
    if (unitRange >= Y) yr -= std::fmod(yr, count);
    if (unitRange == unitMs(TimeUnit::Week)) {
        double t0 = min;
        if (count) t0 = makeTime(int(yr), int(mon), dom, hrs, mins, sec, milliseconds);
        int a, b, c, d2, e2, f2, g2, weekdayNo;
        toParts(t0, a, b, c, d2, e2, f2, g2, weekdayNo);
        dom += -weekdayNo + startOfWeek + (weekdayNo < startOfWeek ? -7 : 0);
    }
    min = makeTime(int(yr), int(mon), dom, hrs, mins, sec, milliseconds);
    double t = min;
    int i = 1;
    while (t < max) {
        ticks.push_back(t);
        if (unitRange == Y) t = makeTime(int(yr + i * count), 0);
        else if (unitRange == MO) t = makeTime(int(yr), int(mon + i * count));
        else t += unitRange * count;
        ++i;
        if (ticks.size() > 100000) break;
    }
    ticks.push_back(t);
    return ticks;
}

QString dateFormat(const QString& fmt, double t) {
    if (!std::isfinite(t)) return QString();
    int y, mo, d, h, mi, s, ms, wd;
    toParts(t, y, mo, d, h, mi, s, ms, wd);
    static const char* mon[] = {"Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"};
    static const char* monL[] = {"January", "February", "March", "April", "May", "June", "July", "August",
                                 "September", "October", "November", "December"};
    static const char* wdS[] = {"Sun", "Mon", "Tue", "Wed", "Thu", "Fri", "Sat"};
    static const char* wdL[] = {"Sunday", "Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday"};
    auto pad = [](int v, int w) { return QString::number(v).rightJustified(w, QLatin1Char('0')); };
    QString out;
    for (int i = 0; i < fmt.size(); ++i) {
        const QChar c = fmt[i];
        if (c != QLatin1Char('%') || i + 1 >= fmt.size()) { out += c; continue; }
        const char k = fmt[++i].toLatin1();
        switch (k) {
        case 'Y': out += QString::number(y); break;
        case 'y': out += pad(y % 100, 2); break;
        case 'm': out += pad(mo + 1, 2); break;
        case 'd': out += pad(d, 2); break;
        case 'e': out += QString::number(d).rightJustified(2, QLatin1Char(' ')); break;
        case 'H': out += pad(h, 2); break;
        case 'M': out += pad(mi, 2); break;
        case 'S': out += pad(s, 2); break;
        case 'L': out += pad(ms, 3); break;
        case 'b': out += QLatin1String(mon[mo]); break;
        case 'B': out += QLatin1String(monL[mo]); break;
        case 'a': out += QLatin1String(wdS[wd]); break;
        case 'A': out += QLatin1String(wdL[wd]); break;
        case '%': out += QLatin1Char('%'); break;
        default: out += QLatin1Char('%'); out += QLatin1Char(k); break;
        }
    }
    return out;
}

} // namespace hctime

// ---------------------------------------------------------------- hcfmt

namespace hcfmt {

QString jsNumberToString(double v) {
    if (std::isnan(v)) return QStringLiteral("NaN");
    if (v == 0) return QStringLiteral("0");
    if (std::isinf(v)) return v < 0 ? QStringLiteral("-Infinity") : QStringLiteral("Infinity");
    std::string d;
    int n = 0;
    wdcMath_shortest(v, d, n);
    const int k = int(d.size());
    std::string s;
    if (k <= n && n <= 21) s = d + std::string(n - k, '0');
    else if (0 < n && n <= 21) s = d.substr(0, n) + "." + d.substr(n);
    else if (-6 < n && n <= 0) s = "0." + std::string(-n, '0') + d;
    else {
        const int e = n - 1;
        s = d.substr(0, 1) + (k > 1 ? "." + d.substr(1) : "") + "e" + (e < 0 ? "-" : "+") + std::to_string(std::abs(e));
    }
    return QString::fromStdString((v < 0 ? "-" : "") + s);
}

QString numberFormat(double number, int decimals, const QString& decimalPoint, const QString& thousandsSep) {
    if (std::isnan(number)) number = 0;
    const QString str = jsNumberToString(number);
    const QStringList me = str.split(QLatin1Char('e'));
    double mantissa = me.value(0).toDouble();
    const bool hasExp = me.size() > 1;
    double exp = hasExp ? me.value(1).toDouble() : kNaN;
    const int origDec = int(str.section(QLatin1Char('.'), 1, 1).section(QLatin1Char('e'), 0, 0).size());
    const int firstDecimals = decimals;
    if (decimals == -1) {
        decimals = std::min(origDec, 20);
    } else if (decimals && hasExp && exp < 0) {
        const int fractionDigits = decimals + int(exp);
        if (fractionDigits >= 0) {
            char buf[64];
            std::snprintf(buf, sizeof buf, "%.*e", fractionDigits, mantissa);
            mantissa = std::strtod(buf, nullptr);
            decimals = fractionDigits;
        } else {
            mantissa = std::floor(mantissa);
            number = decimals < 20 ? std::strtod(wdcMath_intlFixed(mantissa * std::pow(10.0, exp), decimals, false)
                                                     .toLatin1().constData(), nullptr)
                                   : 0;
            exp = 0;
        }
    }
    const bool expTruthy = hasExp && exp != 0 && !std::isnan(exp);
    if (expTruthy) number = mantissa;
    const bool grouping = !thousandsSep.isEmpty();
    QString ret = wdcMath_intlFixed(number, std::max(decimals, 0), grouping);
    // separators: ',' -> thousandsSep, '.' -> decimalPoint (HS replaces through a '_' marker)
    QString swapped;
    for (const QChar c : ret) {
        if (c == QLatin1Char(',')) swapped += thousandsSep;
        else if (c == QLatin1Char('.')) swapped += decimalPoint;
        else swapped += c;
    }
    ret = swapped;
    bool okNum = false;
    const double asNum = ret.toDouble(&okNum);
    if ((!decimals && okNum && asNum == 0) || (hasExp && exp < 0 && !firstDecimals)) ret = QStringLiteral("0");
    if (expTruthy && !(okNum && asNum == 0))
        ret += QStringLiteral("e") + (exp < 0 ? QString() : QStringLiteral("+")) + jsNumberToString(exp);
    return ret;
}

QString defaultLabel(double value, double tickInterval) {
    static const char* symbols[] = {"K", "M", "G", "T", "P", "E"};
    if (tickInterval >= 1000) {
        for (int i = 5; i >= 0; --i) {
            const double multi = std::pow(1000.0, i + 1);
            if (tickInterval >= multi && std::fmod(value * 10, multi) == 0 && value != 0)
                return numberFormat(value / multi, -1) + QLatin1String(symbols[i]);
        }
    }
    if (std::fabs(value) >= 10000) return numberFormat(value, -1);
    return numberFormat(value, -1, QStringLiteral("."), QString());
}

QString formatTemplate(const QString& tpl, double value) {
    const bool isFloat = std::isnan(value) || std::fmod(value, 1.0) != 0;
    const QString rep = isFloat ? numberFormat(value, -1, QStringLiteral("."), QString()) : jsNumberToString(value);
    QString out = tpl;
    out.replace(QStringLiteral("{value}"), rep);
    return out;
}

QString yLabel(const QString& format, double value, double tickInterval) {
    return format.isEmpty() ? defaultLabel(value, tickInterval) : formatTemplate(format, value);
}

} // namespace hcfmt

} // namespace fincept::screens::wdc
