// src/screens/hdcv_launchpad/HlpPanels_Wd_p.h
// INTERNAL to the WIDATA panel (owned by the wd agent) — shared between
//   HlpPanels_Wd.cpp        render_wdsignal, the signal list, filter chips, stats, note
//   HlpPanels_WdDetail.cpp  the chart column: catalogue <select>, 3T/6T/1N/Tất cả, chart + detail rows
// Not a contract header: no other file includes it. Every name carries the hlpwd_/HlpWd prefix so it
// cannot collide with another panel file in a unity build.
#pragma once

#include "screens/hdcv_launchpad/HlpDom.h"
#include "screens/hdcv_launchpad/HlpPanels.h"

#include <QDateTime>
#include <QJsonObject>
#include <QJsonValue>
#include <QString>
#include <QVariantMap>

#include <functional>
#include <optional>

namespace fincept::screens::hlp {

// ---- WD_ST keys (RenderCtx::viewState) and per-instance keys (RenderCtx::state) ----
inline const QString hlpwd_kVung = QStringLiteral("vung");
inline const QString hlpwd_kMuc = QStringLiteral("muc");
inline const QString hlpwd_kChart = QStringLiteral("chart");
inline const QString hlpwd_kKey = QStringLiteral("key");
inline const QString hlpwd_kRange = QStringLiteral("range");
inline const QString hlpwd_kSelf = QStringLiteral("wd_self"); ///< next render comes from our own click handler
inline const QString hlpwd_kPick = QStringLiteral("wd_pick"); ///< row index that holds aria-current after a click
inline const QString hlpwd_kSync = QStringLiteral("wd_sync"); ///< the handler's web code sets sel.value = st.key

/// What the list/chart builders need from wdRender's closure.
struct HlpWdEnv {
    QJsonObject S;
    QVariantMap* vs = nullptr;   ///< WD_ST[view]
    QVariantMap* inst = nullptr; ///< panel instance state
    std::function<void()> rerender;
    QString key;                 ///< st.key after defaulting
    int pick = -1;               ///< row holding aria-current after a click, -1 = every row of st.key
    QDateTime now;
};

// ---- JS value semantics (HlpPanels_Wd.cpp) ----
bool hlpwd_nullish(const QJsonValue& v);                        ///< v == null
bool hlpwd_truthy(const QJsonValue& v);                         ///< JS truthiness
QString hlpwd_s(const QJsonValue& v);                           ///< esc(v) = String(v ?? '')
QString hlpwd_tpl(const QJsonValue& v);                         ///< `${v}`
QString hlpwd_or(const QJsonValue& v, const QString& fallback); ///< esc(v || fallback)
std::optional<double> hlpwd_val(const QJsonValue& v);           ///< wdFmt/price argument (JS +v)

/// Re-render after one of OUR handlers. pick: nullopt = keep the aria-current row, -1 = list rebuilt,
/// ≥0 = row the user clicked. sync = the web handler runs drawChart(), i.e. `sel.value = st.key`.
void hlpwd_redraw(QVariantMap* inst, const std::function<void()>& rerender, std::optional<int> pick, bool sync);

/// `.wd-bar`: flex wrap, align-items center, gap 6px, margin-bottom 6px.
N hlpwd_bar();
/// `.chips` with `style="margin:0"`.
N hlpwd_chips();

// ---- chart column (HlpPanels_WdDetail.cpp) ----
/// #wdc: the chart block for st.key, or the hint when the key has no series.
NodeP hlpwd_chart(const QJsonObject& S, const QString& key, const QString& range);
/// The catalogue <select id="wdsel"> (nullptr when the shell gives no combo).
NodeP hlpwd_select(RenderCtx& rc, const HlpWdEnv& e, bool external, bool sync);
/// 3T / 6T / 1N / Tất cả (redraws only the chart in the web).
NodeP hlpwd_range_chips(const QString& range, const HlpWdEnv& e);

} // namespace fincept::screens::hlp
