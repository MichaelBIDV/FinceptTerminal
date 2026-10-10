// src/screens/hdcv_launchpad/HlpFmt.h
// JS-exact number/date formatting of panels.js, plus the helper spans it builds
// (ND, n1, n2, pc, sig, price, zcls, wdFmt, wdDelta, wdAgo, wdDate). Every function reproduces the
// V8 output byte for byte — see SPEC §4 for the rules (toFixed vs Intl vi-VN rounding differ).
#pragma once

#include "screens/hdcv_launchpad/HlpDom.h"

#include <QDateTime>
#include <QJsonObject>
#include <QJsonValue>
#include <QString>
#include <QStringList>

#include <optional>
#include <utility>

namespace fincept::screens::hlp::fmt {

/// JS `v == null` → nullopt (JSON null or missing). Numbers pass; numeric strings do NOT
/// (panels.js uses `+v` only where the builder guarantees numbers).
std::optional<double> num(const QJsonValue& v);
/// `(+v)` for fields that may be numeric strings (NaN → nullopt).
std::optional<double> plus(const QJsonValue& v);
/// String value or "" (JS `x || ''`). Numbers are converted like JS String(n).
QString str(const QJsonValue& v);
/// JS String(number): shortest round-trip, "1e21" style above 1e21 (not needed in practice).
QString jsString(double v);
/// JSON.stringify(v) byte for byte (the `.f` filters of reports / vietcapma search it). QJsonObject has
/// lost the file's key order (it sorts keys), so `order` gives the insertion order the producing script
/// writes for the top-level object; keys outside it follow alphabetically, nested objects sort.
QString jsonStringify(const QJsonValue& v, const QStringList& order = {});

/// Number.prototype.toFixed(d) — rounds the exact binary value (2.675 → "2.67").
QString toFixed(double v, int digits);
/// Number.prototype.toLocaleString('vi-VN', {maximumFractionDigits:maxFrac, minimumFractionDigits:minFrac})
/// — groups with '.', decimal ',', rounds the SHORTEST decimal form half-away-from-zero
/// (2.675 → "2,68"). Default toLocaleString() = maxFrac 3.
QString vi(double v, int maxFrac = 3, int minFrac = 0);

// ---- panels.js helper spans (return inline nodes) ----
NodeP ND();                                    ///< `<span class="nd">[CẦN DATA]</span>`
NodeP n1(std::optional<double> v);             ///< v==null ? ND : toFixed(1)
NodeP n2(std::optional<double> v);             ///< v==null ? ND : toFixed(2)
NodeP pc(std::optional<double> v);             ///< ±x.xx% coloured up/down/flat
NodeP sig(std::optional<double> v);            ///< ±x.xxσ coloured z-cheap/z-rich/z-neu (≤−1 / ≥1)
NodeP price(std::optional<double> v);          ///< vi-VN integer grouping
QString n1s(std::optional<double> v);          ///< plain-text variants for places that concatenate
QString n2s(std::optional<double> v);

/// JS `new Date(iso)` parsing (ISO with Z / offset, or "YYYY-MM-DD HH:MM" as local) → ms epoch.
std::optional<qint64> parseMs(const QString& iso);

// ---- WiData helpers (panels.js lines 862–904) ----
QString wdFmtText(std::optional<double> v, const QString& unit); ///< plain text, "[CẦN DATA]" if null
NodeP wdFmt(std::optional<double> v, const QString& unit);      ///< ND span if null, else text
NodeP wdDelta(const QJsonObject& s, double d);                  ///< coloured delta with bps / điểm % suffix
/// wdAgo(iso) → [label, fresh] — "N phút trước" (<60′), "HH:MM" (<24h, fresh if <180′), "DD-MM" (vi-VN 2-digit day+month as Chrome renders it). `now` injected for tests.
std::pair<QString, bool> wdAgo(const QString& iso, const QDateTime& now);
/// wdDate(ms) → "DD/MM/YY" (vi-VN day/month/year 2-digit).
QString wdDate(qint64 ms);

} // namespace fincept::screens::hlp::fmt
