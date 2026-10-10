#pragma once
// ChbJson.h — order-preserving JSON value + parser for the chaebol_map engine.
//
// Why not QJsonDocument: QJsonObject sorts keys alphabetically, but style dicts must be applied in the
// JSON key order (CSSOM semantics of `el.style[k] = v`, like the Chrome oracle: shorthand then longhand
// ≠ longhand then shorthand). This parser keeps object members in document order.
#include <QByteArray>
#include <QJsonValue>
#include <QString>
#include <QStringView>

#include <memory>
#include <utility>
#include <vector>

namespace fincept::screens::chb {

struct JVal;
using JArr = std::vector<JVal>;
using JObj = std::vector<std::pair<QString, JVal>>;

struct JVal {
    enum Type : unsigned char { Null, Bool, Num, Str, Arr, Obj };
    Type type = Null;
    bool b = false;
    double n = 0.0;
    QString s;
    std::shared_ptr<JArr> arr;
    std::shared_ptr<JObj> obj;

    bool isNull() const { return type == Null; }
    bool isBool() const { return type == Bool; }
    bool isNum() const { return type == Num; }
    bool isStr() const { return type == Str; }
    bool isArr() const { return type == Arr; }
    bool isObj() const { return type == Obj; }
    /// Member lookup (linear; objects are small). nullptr when absent or not an object.
    const JVal* get(QStringView key) const;
    const JArr& items() const;   ///< empty when not an array
    const JObj& members() const; ///< empty when not an object
    /// JS `String(v)`: numbers in shortest round-trip form ("12", "0.5"), bools "true"/"false", null "".
    QString toJsString() const;
};

/// Parse UTF-8 JSON. Returns false (and a Vietnamese message in *err) on malformed input.
bool json_parse(const QByteArray& utf8, JVal* out, QString* err = nullptr);
/// Convenience for callers holding Qt JSON (key order is then alphabetical — see note above).
JVal json_from_qt(const QJsonValue& v);
/// JS-like number → string (shortest round trip, no trailing ".0").
QString js_number_string(double v);

} // namespace fincept::screens::chb
