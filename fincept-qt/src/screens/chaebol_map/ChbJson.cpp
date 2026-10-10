// ChbJson.cpp — order-preserving JSON parser (see ChbJson.h).
#include "screens/chaebol_map/ChbJson.h"

#include <QJsonArray>
#include <QJsonObject>
#include <QLocale>

#include <cmath>
#include <cstdlib>
#include <cstring>

namespace fincept::screens::chb {

namespace {

struct ChbjParser {
    const char* p = nullptr;
    const char* end = nullptr;
    const char* begin = nullptr;
    QString err;
    int depth = 0;

    void fail(const char* what) {
        if (err.isEmpty())
            err = QStringLiteral("JSON hỏng tại byte %1: %2").arg(p - begin).arg(QString::fromUtf8(what));
    }
    void ws() {
        while (p < end && (*p == ' ' || *p == '\n' || *p == '\r' || *p == '\t'))
            ++p;
    }
    static int hex(char c) {
        if (c >= '0' && c <= '9') return c - '0';
        if (c >= 'a' && c <= 'f') return c - 'a' + 10;
        if (c >= 'A' && c <= 'F') return c - 'A' + 10;
        return -1;
    }
    bool read_u4(unsigned* out) {
        if (end - p < 4) return false;
        unsigned v = 0;
        for (int i = 0; i < 4; ++i) {
            const int h = hex(p[i]);
            if (h < 0) return false;
            v = v * 16 + unsigned(h);
        }
        p += 4;
        *out = v;
        return true;
    }
    bool str(QString* out) {
        // p at opening quote
        ++p;
        const char* run = p;
        QByteArray buf;
        bool plain = true;
        while (p < end) {
            const char c = *p;
            if (c == '"') {
                if (plain) *out = QString::fromUtf8(run, int(p - run));
                else {
                    buf.append(run, int(p - run));
                    *out = QString::fromUtf8(buf);
                }
                ++p;
                return true;
            }
            if (c == '\\') {
                plain = false;
                buf.append(run, int(p - run));
                ++p;
                if (p >= end) break;
                const char e = *p++;
                switch (e) {
                case '"': buf.append('"'); break;
                case '\\': buf.append('\\'); break;
                case '/': buf.append('/'); break;
                case 'b': buf.append('\b'); break;
                case 'f': buf.append('\f'); break;
                case 'n': buf.append('\n'); break;
                case 'r': buf.append('\r'); break;
                case 't': buf.append('\t'); break;
                case 'u': {
                    unsigned cp = 0;
                    if (!read_u4(&cp)) { fail("\\u sai"); return false; }
                    if (cp >= 0xD800 && cp <= 0xDBFF && end - p >= 6 && p[0] == '\\' && p[1] == 'u') {
                        const char* save = p;
                        p += 2;
                        unsigned lo = 0;
                        if (read_u4(&lo) && lo >= 0xDC00 && lo <= 0xDFFF)
                            cp = 0x10000 + ((cp - 0xD800) << 10) + (lo - 0xDC00);
                        else
                            p = save;
                    }
                    const char32_t c32 = char32_t(cp);
                    buf.append(QString::fromUcs4(&c32, 1).toUtf8());
                    break;
                }
                default: fail("escape lạ"); return false;
                }
                run = p;
                continue;
            }
            ++p;
        }
        fail("chuỗi không đóng");
        return false;
    }
    bool num(double* out) {
        const char* s = p;
        if (p < end && *p == '-') ++p;
        while (p < end && ((*p >= '0' && *p <= '9') || *p == '.' || *p == 'e' || *p == 'E' || *p == '+' || *p == '-'))
            ++p;
        const QByteArray tok(s, int(p - s));
        bool ok = false;
        *out = tok.toDouble(&ok);
        if (!ok) { fail("số sai"); return false; }
        return true;
    }
    bool lit(const char* word) {
        const size_t n = std::strlen(word);
        if (size_t(end - p) < n || std::strncmp(p, word, n) != 0) { fail("từ khoá sai"); return false; }
        p += n;
        return true;
    }
    bool value(JVal* v) {
        ws();
        if (p >= end) { fail("hết dữ liệu"); return false; }
        if (++depth > 400) { fail("lồng quá sâu"); return false; }
        bool ok = true;
        switch (*p) {
        case '{': {
            ++p;
            v->type = JVal::Obj;
            v->obj = std::make_shared<JObj>();
            ws();
            if (p < end && *p == '}') { ++p; break; }
            while (true) {
                ws();
                if (p >= end || *p != '"') { fail("thiếu khoá"); ok = false; break; }
                QString key;
                if (!str(&key)) { ok = false; break; }
                ws();
                if (p >= end || *p != ':') { fail("thiếu ':'"); ok = false; break; }
                ++p;
                JVal child;
                if (!value(&child)) { ok = false; break; }
                // Duplicate key: JSON.parse keeps the FIRST position with the LAST value.
                bool dup = false;
                for (auto& kv : *v->obj)
                    if (kv.first == key) { kv.second = std::move(child); dup = true; break; }
                if (!dup) v->obj->emplace_back(std::move(key), std::move(child));
                ws();
                if (p < end && *p == ',') { ++p; continue; }
                if (p < end && *p == '}') { ++p; break; }
                fail("thiếu ',' hoặc '}'");
                ok = false;
                break;
            }
            break;
        }
        case '[': {
            ++p;
            v->type = JVal::Arr;
            v->arr = std::make_shared<JArr>();
            ws();
            if (p < end && *p == ']') { ++p; break; }
            while (true) {
                JVal child;
                if (!value(&child)) { ok = false; break; }
                v->arr->push_back(std::move(child));
                ws();
                if (p < end && *p == ',') { ++p; continue; }
                if (p < end && *p == ']') { ++p; break; }
                fail("thiếu ',' hoặc ']'");
                ok = false;
                break;
            }
            break;
        }
        case '"':
            v->type = JVal::Str;
            ok = str(&v->s);
            break;
        case 't': v->type = JVal::Bool; v->b = true; ok = lit("true"); break;
        case 'f': v->type = JVal::Bool; v->b = false; ok = lit("false"); break;
        case 'n': v->type = JVal::Null; ok = lit("null"); break;
        default:
            v->type = JVal::Num;
            ok = num(&v->n);
        }
        --depth;
        return ok;
    }
};

const JArr& chbj_empty_arr() {
    static const JArr a;
    return a;
}
const JObj& chbj_empty_obj() {
    static const JObj o;
    return o;
}

} // namespace

const JVal* JVal::get(QStringView key) const {
    if (type != Obj || !obj) return nullptr;
    for (const auto& kv : *obj)
        if (kv.first == key) return &kv.second;
    return nullptr;
}

const JArr& JVal::items() const { return (type == Arr && arr) ? *arr : chbj_empty_arr(); }
const JObj& JVal::members() const { return (type == Obj && obj) ? *obj : chbj_empty_obj(); }

QString js_number_string(double v) {
    if (std::isnan(v)) return QStringLiteral("NaN");
    if (std::isinf(v)) return v > 0 ? QStringLiteral("Infinity") : QStringLiteral("-Infinity");
    if (v == 0) return QStringLiteral("0");
    if (std::fabs(v) < 1e21 && v == std::floor(v)) {
        if (std::fabs(v) < 9.0e15) return QString::number(qlonglong(v));
        return QString::number(v, 'f', 0);
    }
    QString s = QString::number(v, 'g', QLocale::FloatingPointShortest);
    // Qt writes 1e-07 / 1e+21; JS writes 1e-7 / 1e+21.
    const int e = s.indexOf(QLatin1Char('e'));
    if (e >= 0) {
        QString mant = s.left(e), exp = s.mid(e + 1);
        QChar sign = QLatin1Char('+');
        if (exp.startsWith(QLatin1Char('-')) || exp.startsWith(QLatin1Char('+'))) {
            sign = exp[0];
            exp = exp.mid(1);
        }
        while (exp.size() > 1 && exp.startsWith(QLatin1Char('0'))) exp = exp.mid(1);
        s = mant + QLatin1Char('e') + sign + exp;
    }
    return s;
}

QString JVal::toJsString() const {
    switch (type) {
    case Str: return s;
    case Num: return js_number_string(n);
    case Bool: return b ? QStringLiteral("true") : QStringLiteral("false");
    default: return QString();
    }
}

bool json_parse(const QByteArray& utf8, JVal* out, QString* err) {
    ChbjParser ps;
    ps.begin = utf8.constData();
    ps.p = ps.begin;
    ps.end = ps.begin + utf8.size();
    if (utf8.size() >= 3 && uchar(ps.p[0]) == 0xEF && uchar(ps.p[1]) == 0xBB && uchar(ps.p[2]) == 0xBF) ps.p += 3;
    JVal v;
    bool ok = ps.value(&v);
    if (ok) {
        ps.ws();
        if (ps.p != ps.end) {
            ps.fail("dư dữ liệu sau giá trị gốc");
            ok = false;
        }
    }
    if (!ok) {
        if (err) *err = ps.err;
        return false;
    }
    *out = std::move(v);
    return true;
}

JVal json_from_qt(const QJsonValue& v) {
    JVal r;
    switch (v.type()) {
    case QJsonValue::Bool: r.type = JVal::Bool; r.b = v.toBool(); break;
    case QJsonValue::Double: r.type = JVal::Num; r.n = v.toDouble(); break;
    case QJsonValue::String: r.type = JVal::Str; r.s = v.toString(); break;
    case QJsonValue::Array: {
        r.type = JVal::Arr;
        r.arr = std::make_shared<JArr>();
        for (const QJsonValue& x : v.toArray()) r.arr->push_back(json_from_qt(x));
        break;
    }
    case QJsonValue::Object: {
        r.type = JVal::Obj;
        r.obj = std::make_shared<JObj>();
        const QJsonObject o = v.toObject();
        for (auto it = o.begin(); it != o.end(); ++it) r.obj->emplace_back(it.key(), json_from_qt(it.value()));
        break;
    }
    default: break;
    }
    return r;
}

} // namespace fincept::screens::chb
