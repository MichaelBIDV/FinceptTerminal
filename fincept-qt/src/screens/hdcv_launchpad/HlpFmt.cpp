// src/screens/hdcv_launchpad/HlpFmt.cpp
// Byte-exact ports of the number/date helpers of panels.js (SPEC §4), verified against V8/ICU:
//  - toFixed() rounds the EXACT binary value, ties go to the larger magnitude ((0.125).toFixed(2) = "0.13",
//    (-2.5).toFixed(0) = "-3", (-0.001).toFixed(2) = "-0.00");
//  - toLocaleString('vi-VN') rounds the SHORTEST round-trip decimal half-away-from-zero
//    ((2.675) → "2,68"), groups with '.', decimal ',', keeps "-0";
//  - Date: "YYYY-MM-DD" is UTC, date-times without offset are local (Asia/Ho_Chi_Minh on this Mac);
//    vi-VN renders {day,month} as "DD-MM", {day,month,year:2-digit} as "DD/MM/YY", time as "HH:MM".
#include "screens/hdcv_launchpad/HlpFmt.h"

#include "screens/hdcv_launchpad/HlpAtoms.h"

#include <QJsonArray>
#include <QLocale>
#include <QRegularExpression>
#include <QTimeZone>

#include <cmath>
#include <cstdio>
#include <cstring>

namespace fincept::screens::hlp::fmt {

namespace {

/// Shortest round-trip digits of |v| (no leading zeros) and the decimal exponent `pt` such that
/// |v| = 0.d1d2d3… × 10^pt.
void hlpfmt_shortest(double v, QByteArray& digits, int& pt) {
    // Qt's shortest round-trip (double-conversion), scientific: d.ddde±XX
    const QByteArray s = QByteArray::number(std::abs(v), 'e', QLocale::FloatingPointShortest);
    const int e = s.indexOf('e');
    QByteArray mant = s.left(e);
    const int exp = s.mid(e + 1).toInt();
    mant.replace(".", "");
    while (mant.size() > 1 && mant.endsWith('0'))
        mant.chop(1);
    digits = mant;
    pt = exp + 1;
}

/// Exact decimal expansion of |v| as integer digits + fraction digits.
void hlpfmt_exact(double v, QByteArray& intPart, QByteArray& frac) {
    // %.1100f prints the exact binary value (every double has a finite decimal expansion)
    static thread_local char buf[1400];
    std::snprintf(buf, sizeof(buf), "%.1100f", std::abs(v));
    const char* dot = std::strchr(buf, '.');
    intPart = QByteArray(buf, int(dot - buf));
    frac = QByteArray(dot + 1);
}

/// Round the digit string "int.frac" half-up (away from zero on magnitudes) to `d` fraction digits.
QByteArray hlpfmt_roundHalfUp(QByteArray intPart, QByteArray frac, int d, bool* allZero = nullptr) {
    while (frac.size() < d + 1)
        frac.append('0');
    const bool up = frac.at(d) >= '5';
    QByteArray digits = intPart + frac.left(d);
    if (up) {
        int i = int(digits.size()) - 1;
        while (i >= 0) {
            if (digits[i] == '9') {
                digits[i] = '0';
                --i;
            } else {
                digits[i] = char(digits[i] + 1);
                break;
            }
        }
        if (i < 0)
            digits.prepend('1');
    }
    const int ni = int(digits.size()) - d;
    QByteArray ip = digits.left(ni), fp = digits.mid(ni);
    int k = 0;
    while (k < ip.size() - 1 && ip[k] == '0')
        ++k;
    ip = ip.mid(k);
    if (allZero) {
        *allZero = true;
        for (char c : ip + fp)
            if (c != '0')
                *allZero = false;
    }
    return fp.isEmpty() ? ip : ip + "." + fp;
}

QString hlpfmt_group(const QString& ip, QChar sep) {
    QString out;
    const int n = int(ip.size());
    for (int i = 0; i < n; ++i) {
        out += ip.at(i);
        const int rem = n - 1 - i;
        if (rem > 0 && rem % 3 == 0)
            out += sep;
    }
    return out;
}

} // namespace

std::optional<double> num(const QJsonValue& v) {
    if (v.isDouble())
        return v.toDouble();
    return std::nullopt;
}

std::optional<double> plus(const QJsonValue& v) {
    // JS unary +: null → 0, undefined → NaN, bool → 0/1, string → Number(str)
    if (v.isDouble())
        return v.toDouble();
    if (v.isNull())
        return 0.0;
    if (v.isBool())
        return v.toBool() ? 1.0 : 0.0;
    if (v.isString()) {
        const QString s = v.toString().trimmed();
        if (s.isEmpty())
            return 0.0;
        bool ok = false;
        double d = 0;
        if (s.startsWith(QStringLiteral("0x"), Qt::CaseInsensitive))
            d = double(s.mid(2).toLongLong(&ok, 16));
        else if (s == QStringLiteral("Infinity") || s == QStringLiteral("+Infinity"))
            return std::numeric_limits<double>::infinity();
        else if (s == QStringLiteral("-Infinity"))
            return -std::numeric_limits<double>::infinity();
        else {
            static const QRegularExpression re(QStringLiteral(R"(^[+-]?(\d+\.?\d*|\.\d+)([eE][+-]?\d+)?$)"));
            if (re.match(s).hasMatch())
                d = s.toDouble(&ok);
        }
        if (!ok || std::isnan(d))
            return std::nullopt;
        return d;
    }
    return std::nullopt;
}

QString jsString(double v) {
    if (std::isnan(v))
        return QStringLiteral("NaN");
    if (std::isinf(v))
        return v > 0 ? QStringLiteral("Infinity") : QStringLiteral("-Infinity");
    if (v == 0)
        return QStringLiteral("0");
    QByteArray d;
    int n = 0;
    hlpfmt_shortest(v, d, n);
    const int k = int(d.size());
    QByteArray out;
    if (k <= n && n <= 21) {
        out = d + QByteArray(n - k, '0');
    } else if (0 < n && n <= 21) {
        out = d.left(n) + "." + d.mid(n);
    } else if (-6 < n && n <= 0) {
        out = "0." + QByteArray(-n, '0') + d;
    } else {
        const int e = n - 1;
        out = d.left(1);
        if (k > 1)
            out += "." + d.mid(1);
        out += "e";
        out += e >= 0 ? "+" : "-";
        out += QByteArray::number(std::abs(e));
    }
    return (v < 0 ? QStringLiteral("-") : QString()) + QString::fromLatin1(out);
}

namespace {

/// JSON.stringify of a string: `"`, `\`, \b \f \n \r \t escaped, other C0 controls as \u00xx.
QString hlpfmt_jsonQuote(const QString& s) {
    QString o;
    o.reserve(s.size() + 2);
    o += QLatin1Char('"');
    for (const QChar ch : s) {
        const char16_t c = ch.unicode();
        switch (c) {
            case u'"': o += QStringLiteral("\\\""); break;
            case u'\\': o += QStringLiteral("\\\\"); break;
            case u'\b': o += QStringLiteral("\\b"); break;
            case u'\f': o += QStringLiteral("\\f"); break;
            case u'\n': o += QStringLiteral("\\n"); break;
            case u'\r': o += QStringLiteral("\\r"); break;
            case u'\t': o += QStringLiteral("\\t"); break;
            default:
                if (c < 0x20)
                    o += QStringLiteral("\\u%1").arg(int(c), 4, 16, QLatin1Char('0'));
                else
                    o += ch;
        }
    }
    o += QLatin1Char('"');
    return o;
}

} // namespace

QString jsonStringify(const QJsonValue& v, const QStringList& order) {
    switch (v.type()) {
        case QJsonValue::Bool:
            return v.toBool() ? QStringLiteral("true") : QStringLiteral("false");
        case QJsonValue::Double: {
            const double d = v.toDouble();
            return std::isfinite(d) ? jsString(d) : QStringLiteral("null");
        }
        case QJsonValue::String:
            return hlpfmt_jsonQuote(v.toString());
        case QJsonValue::Array: {
            QStringList parts;
            for (const QJsonValue& x : v.toArray())
                parts << jsonStringify(x);
            return QLatin1Char('[') + parts.join(QLatin1Char(',')) + QLatin1Char(']');
        }
        case QJsonValue::Object: {
            const QJsonObject o = v.toObject();
            QStringList keys;
            for (const QString& k : order)
                if (o.contains(k))
                    keys << k;
            for (auto it = o.begin(); it != o.end(); ++it)
                if (!order.contains(it.key()))
                    keys << it.key();
            QStringList parts;
            for (const QString& k : keys)
                parts << hlpfmt_jsonQuote(k) + QLatin1Char(':') + jsonStringify(o.value(k));
            return QLatin1Char('{') + parts.join(QLatin1Char(',')) + QLatin1Char('}');
        }
        default:
            return QStringLiteral("null");
    }
}

QString str(const QJsonValue& v) {
    // JS `x || ''`: every falsy value (null, undefined, false, 0, NaN, "") gives ""
    if (v.isString())
        return v.toString();
    if (v.isDouble()) {
        const double d = v.toDouble();
        if (d == 0 || std::isnan(d))
            return QString();
        return jsString(d);
    }
    if (v.isBool())
        return v.toBool() ? QStringLiteral("true") : QString();
    return QString();
}

QString toFixed(double v, int digits) {
    digits = std::clamp(digits, 0, 100);
    if (std::isnan(v))
        return QStringLiteral("NaN");
    if (std::abs(v) >= 1e21 || std::isinf(v))
        return jsString(v);
    QByteArray ip, fp;
    hlpfmt_exact(v, ip, fp);
    const QByteArray r = hlpfmt_roundHalfUp(ip, fp, digits);
    return (v < 0 ? QStringLiteral("-") : QString()) + QString::fromLatin1(r); // -0 → "0.00"; -0.001 → "-0.00"
}

QString vi(double v, int maxFrac, int minFrac) {
    if (std::isnan(v))
        return QStringLiteral("NaN");
    if (std::isinf(v))
        return v > 0 ? QStringLiteral("∞") : QStringLiteral("-∞");
    maxFrac = std::clamp(maxFrac, 0, 100);
    minFrac = std::clamp(minFrac, 0, maxFrac);
    const bool neg = std::signbit(v);
    QByteArray ip("0"), fp;
    if (v != 0) {
        QByteArray d;
        int n = 0;
        hlpfmt_shortest(v, d, n);
        if (n <= 0) {
            ip = "0";
            fp = QByteArray(-n, '0') + d;
        } else if (n >= d.size()) {
            ip = d + QByteArray(n - int(d.size()), '0');
        } else {
            ip = d.left(n);
            fp = d.mid(n);
        }
    }
    QByteArray r = hlpfmt_roundHalfUp(ip, fp, maxFrac);
    QString s = QString::fromLatin1(r);
    QString intS = s, fracS;
    const int dot = int(s.indexOf(u'.'));
    if (dot >= 0) {
        intS = s.left(dot);
        fracS = s.mid(dot + 1);
    }
    while (fracS.size() > minFrac && fracS.endsWith(u'0'))
        fracS.chop(1);
    QString out = hlpfmt_group(intS, u'.');
    if (!fracS.isEmpty())
        out += u',' + fracS;
    return (neg ? QStringLiteral("-") : QString()) + out;
}

// ---- helper spans ----------------------------------------------------------------------------
NodeP ND() {
    return nd();
}

NodeP n1(std::optional<double> v) {
    if (!v)
        return ND();
    return text(toFixed(*v, 1));
}

NodeP n2(std::optional<double> v) {
    if (!v)
        return ND();
    return text(toFixed(*v, 2));
}

NodeP pc(std::optional<double> v) {
    if (!v)
        return ND();
    const double x = *v;
    const QString s = QString(x > 0 ? QStringLiteral("+") : QString()) + toFixed(x, 2) + u'%';
    if (x > 0)
        return atoms::up(s);
    if (x < 0)
        return atoms::down(s);
    return atoms::flat(s);
}

NodeP sig(std::optional<double> v) {
    if (!v)
        return ND();
    const double x = *v;
    const QString s = QString(x > 0 ? QStringLiteral("+") : QString()) + toFixed(x, 2) + QStringLiteral("σ");
    if (x <= -1)
        return atoms::zCheap(s);
    if (x >= 1)
        return atoms::zRich(s);
    return atoms::zNeu(s);
}

NodeP price(std::optional<double> v) {
    if (!v)
        return ND();
    return text(vi(*v));
}

QString n1s(std::optional<double> v) {
    return v ? toFixed(*v, 1) : QStringLiteral("[CẦN DATA]");
}

QString n2s(std::optional<double> v) {
    return v ? toFixed(*v, 2) : QStringLiteral("[CẦN DATA]");
}

// ---- dates -----------------------------------------------------------------------------------
std::optional<qint64> parseMs(const QString& isoIn) {
    const QString iso = isoIn.trimmed();
    if (iso.isEmpty())
        return std::nullopt;
    static const QRegularExpression dateOnly(QStringLiteral(R"(^(\d{4})-(\d{2})-(\d{2})$)"));
    static const QRegularExpression dateTime(QStringLiteral(
        R"(^(\d{4})-(\d{2})-(\d{2})[T ](\d{2}):(\d{2})(?::(\d{2})(?:\.(\d{1,9}))?)?\s*(Z|[+-]\d{2}:?\d{2})?$)"));
    if (auto m = dateOnly.match(iso); m.hasMatch()) {
        const QDate d(m.captured(1).toInt(), m.captured(2).toInt(), m.captured(3).toInt());
        if (!d.isValid())
            return std::nullopt;
        return QDateTime(d, QTime(0, 0), QTimeZone::UTC).toMSecsSinceEpoch();
    }
    auto m = dateTime.match(iso);
    if (!m.hasMatch())
        return std::nullopt;
    const QDate d(m.captured(1).toInt(), m.captured(2).toInt(), m.captured(3).toInt());
    int ms = 0;
    if (!m.captured(7).isEmpty())
        ms = m.captured(7).left(3).leftJustified(3, u'0').toInt();
    const QTime t(m.captured(4).toInt(), m.captured(5).toInt(), m.captured(6).isEmpty() ? 0 : m.captured(6).toInt(), ms);
    if (!d.isValid() || !t.isValid())
        return std::nullopt;
    const QString tz = m.captured(8);
    if (tz.isEmpty())
        return QDateTime(d, t).toMSecsSinceEpoch(); // local time
    if (tz == u"Z")
        return QDateTime(d, t, QTimeZone::UTC).toMSecsSinceEpoch();
    QString z = tz;
    z.remove(u':');
    const int sign = z.startsWith(u'-') ? -1 : 1;
    const int off = sign * (z.mid(1, 2).toInt() * 3600 + z.mid(3, 2).toInt() * 60);
    return QDateTime(d, t, QTimeZone::fromSecondsAheadOfUtc(off)).toMSecsSinceEpoch();
}

QString wdFmtText(std::optional<double> v, const QString& unit) {
    if (!v || !std::isfinite(*v))
        return QStringLiteral("[CẦN DATA]");
    const double a = std::abs(*v);
    const int d = a >= 100000 ? 0 : a >= 10000 ? 1 : a >= 10 ? 2 : a >= 1 ? 3 : 4;
    const QString s = vi(*v, d);
    if (unit.isEmpty())
        return s;
    if (unit == u"%")
        return s + u'%';
    if (unit == u"bps")
        return s + QStringLiteral(" bps");
    return s + u' ' + unit;
}

NodeP wdFmt(std::optional<double> v, const QString& unit) {
    if (!v || !std::isfinite(*v))
        return ND();
    return text(wdFmtText(v, unit));
}

NodeP wdDelta(const QJsonObject& s, double d) {
    const bool bps = s.value(QStringLiteral("loai")).toString() == QStringLiteral("rate_pct");
    const double v = bps ? d * 100.0 : d;
    const QString txt = bps ? vi(v, 1) : wdFmtText(v, QString());
    static const QRegularExpression nz(QStringLiteral("[1-9]"));
    const bool zero = !nz.match(txt).hasMatch();
    const QString suf = bps ? QStringLiteral(" bps")
                            : (s.value(QStringLiteral("don_vi")).toString() == QStringLiteral("%") ? QStringLiteral(" điểm %")
                                                                                              : QString());
    const QString out = (zero ? QStringLiteral("0") : (d > 0 ? QStringLiteral("+") : QString()) + txt) + suf;
    if (zero)
        return atoms::flat(out);
    return d > 0 ? atoms::up(out) : atoms::down(out);
}

std::pair<QString, bool> wdAgo(const QString& iso, const QDateTime& now) {
    const auto t = parseMs(iso);
    if (!t || *t == 0)
        return {QString(), false};
    const double m = double(now.toMSecsSinceEpoch() - *t) / 60000.0;
    if (m < 60) {
        const double r = std::floor(m + 0.5); // Math.round
        return {QString::number(std::max(1.0, r), 'f', 0) + QStringLiteral(" phút trước"), true};
    }
    const QDateTime dt = QDateTime::fromMSecsSinceEpoch(*t).toLocalTime();
    if (m < 60 * 24)
        return {dt.toString(QStringLiteral("HH:mm")), m < 180};
    return {dt.toString(QStringLiteral("dd-MM")), false};
}

QString wdDate(qint64 ms) {
    return QDateTime::fromMSecsSinceEpoch(ms).toLocalTime().toString(QStringLiteral("dd/MM/yy"));
}

} // namespace fincept::screens::hlp::fmt
