// src/screens/hdcv_launchpad/HlpPanels_Wd.cpp
// HĐCV Launchpad — WIDATA · MARKET SIGNALS (panels.js 810–1179), translated template for template:
//   wdsignal.render + WD_VUNG / WD_QG / WD_TS + wdRender: region / impact / "Chỉ tin có biểu đồ" chips,
//   the signal list (≤120 rows; the doanh_nghiep branch with SS-T3 cards), the catalogue <select>
//   grouped by country (optgroup → bold, non-selectable header rows), the 3T/6T/1N/Tất cả window, the
//   chart (charts::wdChart = wdSlice + wdChartHtml + wdHover) and the detail rows/warnings under it.
// This file: render_wdsignal, the list, filter chips, stats, note + the shared helpers of
// HlpPanels_Wd_p.h. The chart column (select, range chips, chart, detail rows) is in HlpPanels_WdDetail.cpp.
// Number/date helpers (wdFmt, wdDelta, wdAgo, wdDate, price) come from HlpFmt.
// Deliberate differences from the web, forced by Qt:
//  - wdHashKey is dropped (Qt has no location.hash); the user's choice lives in RenderCtx::viewState,
//    which plays the role of WD_ST[view] = {vung, muc, chart, key, range}.
//  - The web patches the DOM in place: a row click only moves aria-current to the clicked row and
//    redraws the chart; chip clicks redraw only the list (or only the chart for 3T/6T/1N/Tất cả).
//    Here every click re-renders the body, so the panel instance state remembers the picked row until
//    the next list rebuild, and whether the <select> would have been re-synced.
#include "screens/hdcv_launchpad/HlpAtoms.h"
#include "screens/hdcv_launchpad/HlpFmt.h"
#include "screens/hdcv_launchpad/HlpPanels.h"
#include "screens/hdcv_launchpad/HlpPanels_Wd_p.h"
#include "screens/hdcv_launchpad/HlpTheme.h"

#include <QDateTime>
#include <QJsonArray>
#include <QJsonObject>
#include <QJsonValue>
#include <QRegularExpression>
#include <QStringList>
#include <QVariant>

#include <cmath>
#include <functional>
#include <map>
#include <optional>
#include <utility>

namespace fincept::screens::hlp {

// ---- shared with HlpPanels_WdDetail.cpp (declared in HlpPanels_Wd_p.h) ----

bool hlpwd_nullish(const QJsonValue& v) {
    return v.isNull() || v.isUndefined();
}

/// JS truthiness (undefined/null/false/0/NaN/"" → false).
bool hlpwd_truthy(const QJsonValue& v) {
    switch (v.type()) {
        case QJsonValue::Bool:
            return v.toBool();
        case QJsonValue::Double: {
            const double d = v.toDouble();
            return d != 0.0 && !std::isnan(d);
        }
        case QJsonValue::String:
            return !v.toString().isEmpty();
        case QJsonValue::Array:
        case QJsonValue::Object:
            return true;
        default:
            return false;
    }
}

/// esc(v) = String(v ?? '').
QString hlpwd_s(const QJsonValue& v) {
    switch (v.type()) {
        case QJsonValue::Null:
        case QJsonValue::Undefined:
            return {};
        case QJsonValue::Bool:
            return v.toBool() ? QStringLiteral("true") : QStringLiteral("false");
        case QJsonValue::Double:
            return fmt::jsString(v.toDouble());
        case QJsonValue::String:
            return v.toString();
        default:
            return fmt::str(v);
    }
}

/// `${v}` (undefined → "undefined", null → "null").
QString hlpwd_tpl(const QJsonValue& v) {
    if (v.isUndefined())
        return QStringLiteral("undefined");
    if (v.isNull())
        return QStringLiteral("null");
    return hlpwd_s(v);
}

/// esc(v || fallback)
QString hlpwd_or(const QJsonValue& v, const QString& fallback) {
    return hlpwd_truthy(v) ? hlpwd_s(v) : fallback;
}

/// Argument of wdFmt / price: `v == null` → nullopt; otherwise JS `+v` (numeric strings coerce, NaN → nullopt).
std::optional<double> hlpwd_val(const QJsonValue& v) {
    if (hlpwd_nullish(v))
        return std::nullopt;
    return fmt::plus(v);
}

/// Re-render after one of OUR handlers (the shell's own re-renders are the web's full wdRender).
/// pick: nullopt = keep the aria-current row (the handler did not rebuild the list), -1 = list rebuilt,
/// ≥0 = row the user clicked. sync = the web handler runs drawChart(), i.e. `sel.value = st.key`.
void hlpwd_redraw(QVariantMap* inst, const std::function<void()>& rerender, std::optional<int> pick, bool sync) {
    if (inst) {
        inst->insert(hlpwd_kSelf, true);
        inst->insert(hlpwd_kSync, sync);
        if (pick)
            inst->insert(hlpwd_kPick, *pick);
    }
    if (rerender)
        rerender();
}

/// `.wd-bar`: flex wrap, align-items center, gap 6px, margin-bottom 6px.
N hlpwd_bar() {
    N b = div();
    b.key(QStringLiteral("div.wd-bar")).flex(Justify::Start, AlignItems::Center, 6.0f).wrap().mb(6.0f);
    return b;
}

/// `.chips` with `style="margin:0"`.
N hlpwd_chips() {
    N c = atoms::chips();
    c.m(0.0f, 0.0f, 0.0f, 0.0f);
    return c;
}

namespace {

namespace a = atoms;

constexpr int hlpwd_kMaxRows = 120;          // feed.filter(…).slice(0, 120)

// ---- WD_VUNG / WD_QG / WD_TS (panels.js 851–854) ----
const QVector<std::pair<QString, QString>>& hlpwd_vung() {
    static const QVector<std::pair<QString, QString>> v = {
        {QStringLiteral("all"), QStringLiteral("Tất cả")},    {QStringLiteral("VN"), QStringLiteral("Việt Nam")},
        {QStringLiteral("US"), QStringLiteral("Mỹ")},          {QStringLiteral("CN"), QStringLiteral("Trung Quốc")},
        {QStringLiteral("EU"), QStringLiteral("Châu Âu")},     {QStringLiteral("INTL"), QStringLiteral("Quốc tế")},
        {QStringLiteral("HH"), QStringLiteral("Hàng hoá")},    {QStringLiteral("TT"), QStringLiteral("Thị trường")},
        {QStringLiteral("DN"), QStringLiteral("Doanh nghiệp")}};
    return v;
}

/// `(x || 0)` compared numerically.
double hlpwd_num0(const QJsonValue& v) {
    if (!hlpwd_truthy(v))
        return 0.0;
    return fmt::plus(v).value_or(std::nan(""));
}

/// safeUrl(u): only http(s) passes, everything else becomes '#'.
QString hlpwd_safe_url(const QJsonValue& v) {
    static const QRegularExpression re(QStringLiteral("^https?://"), QRegularExpression::CaseInsensitiveOption);
    const QString u = hlpwd_or(v, QString());
    return re.match(u).hasMatch() ? u : QStringLiteral("#");
}

/// wdHoa(t): first UTF-16 unit upper-cased.
QString hlpwd_hoa(const QString& t) {
    return t.isEmpty() ? QString() : t.left(1).toUpper() + t.mid(1);
}

// ---- state ----

/// WD_ST[vKey] — the shell's per-(view, panel) map; a static map keyed by view if it gives none.
QVariantMap* hlpwd_view_state(RenderCtx& rc) {
    if (rc.viewState)
        return rc.viewState;
    static std::map<QString, QVariantMap> fallback;
    return &fallback[rc.viewKey.isEmpty() ? QStringLiteral("mac_dinh") : rc.viewKey];
}

/// `{ vung: 'all', muc: 0, chart: false, key: null, range: 'all' }` for keys not set yet.
void hlpwd_init_state(QVariantMap& st) {
    if (!st.contains(hlpwd_kVung))
        st.insert(hlpwd_kVung, QStringLiteral("all"));
    if (!st.contains(hlpwd_kMuc))
        st.insert(hlpwd_kMuc, 0);
    if (!st.contains(hlpwd_kChart))
        st.insert(hlpwd_kChart, false);
    if (!st.contains(hlpwd_kKey))
        st.insert(hlpwd_kKey, QString());
    if (!st.contains(hlpwd_kRange))
        st.insert(hlpwd_kRange, QStringLiteral("all"));
}

// ---- list rows (drawList, panels.js 1104–1138) ----

/// `.wd-it`: grid 70px minmax(0,1fr), gap 8px, padding 6px 4px, border-bottom 1px line, radius r.
N hlpwd_row_box(bool current) {
    const Palette& P = pal();
    GridSpec g;
    g.cols = {Track{70.0f, 0.0f, 0.0f}, Track{-1.0f, 1.0f, 0.0f}};
    g.colGap = 8.0f;
    g.rowGap = 8.0f;
    N it = div();
    it.grid(g).bb(1.0f, P.line).radius(kRadius).pointer().focusable(P.amber); // tabindex=0, :focus-visible
    if (current) {
        // [aria-current]: amber 10% (Chrome dump: oklab(… / 0.1)) + box-shadow: inset 2px 0 0 amber.
        it.key(QStringLiteral("div.wd-it[current]")).bg(mixT(P.amber, 10.0f)).p(6.0f, 4.0f).shadowInset(2.0f, 0.0f, P.amber);
    } else {
        it.key(QStringLiteral("div.wd-it")).p(6.0f, 4.0f).hoverBg(P.bg2);
    }
    return it;
}

/// `.wd-when` (+ `.fresh` → down): 9.5px mono, line-height normal, ink-3, padding-top 1px.
NodeP hlpwd_when(const QJsonValue& tao, const QDateTime& now) {
    const std::pair<QString, bool> ago = fmt::wdAgo(hlpwd_s(tao), now);
    N d = div();
    d.key(QStringLiteral("div.wd-when")).mono(9.5f).lhNormal().c(ago.second ? pal().down : pal().ink3).p(1.0f, 0.0f, 0.0f, 0.0f);
    if (!ago.first.isEmpty())
        d << text(ago.first);
    return d;
}

/// `.wd-sum`: 10px/1.45 ink-3, margin-top 2px, clamped to 2 lines.
NodeP hlpwd_sum(const QString& s) {
    N d = div();
    d.key(QStringLiteral("div.wd-sum")).size(10.0f).c(pal().ink3).lhf(1.45f).mt(2.0f).clamp(2);
    if (!s.isEmpty())
        d << text(s);
    return d;
}

/// `.wd-card`: flex space-between, gap 8px, margin-top 5px, padding 4px 7px, bg-2, radius r, 10px.
N hlpwd_card_box() {
    N c = div();
    c.key(QStringLiteral("div.wd-card"))
        .flex(Justify::SpaceBetween, AlignItems::Stretch, 8.0f)
        .mt(5.0f)
        .p(4.0f, 7.0f)
        .bg(pal().bg2)
        .radius(kRadius)
        .size(10.0f);
    return c;
}

/// card(f): the value card precomputed for THIS signal's period (f.the) — never the series' latest.
NodeP hlpwd_card(const QJsonObject& f, const QJsonObject& S) {
    const QString key = hlpwd_s(f.value(QStringLiteral("key")));
    const QJsonValue thv = f.value(QStringLiteral("the"));
    if (key.isEmpty() || !S.contains(key) || !hlpwd_truthy(thv))
        return nullptr;
    const QJsonObject s = S.value(key).toObject();
    const QJsonObject th = thv.toObject();
    const QString unit = hlpwd_s(s.value(QStringLiteral("don_vi")));

    N v = a::v();
    v.nowrap() << text(QStringLiteral("Hiện tại: ")) << fmt::wdFmt(hlpwd_val(th.value(QStringLiteral("hien_tai"))), unit);
    const QJsonValue tr = th.value(QStringLiteral("truoc"));
    if (!hlpwd_nullish(tr)) {
        const QString nt = hlpwd_hoa(hlpwd_or(th.value(QStringLiteral("nhan_truoc")), QStringLiteral("kỳ trước")));
        v << text(QStringLiteral(" · %1: ").arg(nt)) << fmt::wdFmt(hlpwd_val(tr), unit);
    }
    N card = hlpwd_card_box();
    card << a::b(hlpwd_s(s.value(QStringLiteral("nhan")))).weight(600).c(pal().ink) << v;
    return card;
}

/// `<div class="m mono" style="font-size:9px;color:var(--ink-3);margin-top:3px">nhóm · chủ đề · mức N · <a>…</a>`
NodeP hlpwd_meta(const QJsonObject& f) {
    QString s = hlpwd_or(f.value(QStringLiteral("nhom")), QString());
    const QJsonValue cd = f.value(QStringLiteral("chu_de"));
    if (hlpwd_truthy(cd))
        s += QStringLiteral(" · ") + hlpwd_s(cd);
    const QJsonValue muc = f.value(QStringLiteral("muc"));
    if (hlpwd_truthy(muc))
        s += QStringLiteral(" · mức ") + hlpwd_s(muc);
    // The template's line break before "· <a>" collapses to one space; at the start of the line it vanishes.
    s += s.isEmpty() ? QStringLiteral("· ") : QStringLiteral(" · ");
    N m = a::monoD();
    m.key(QStringLiteral("div.m")).size(9.0f).c(pal().ink3).mt(3.0f);
    m << text(s) << a::link(QStringLiteral("mở trên WiData ↗"), hlpwd_safe_url(f.value(QStringLiteral("url"))));
    return m;
}

/// One row of the main feed. Click (not on the WiData link) → st.key = row key, redraw the chart.
NodeP hlpwd_feed_row(const QJsonObject& f, int idx, const HlpWdEnv& e) {
    const Palette& P = pal();
    const QString fk = hlpwd_s(f.value(QStringLiteral("key")));
    const bool on = e.pick >= 0 ? idx == e.pick : (!fk.isEmpty() && fk == e.key);
    N it = hlpwd_row_box(on);
    it.tip(fk.isEmpty() ? QStringLiteral("Tín hiệu này chưa có chuỗi để vẽ") : QStringLiteral("Bấm để xem biểu đồ"));
    if (!fk.isEmpty()) {
        QVariantMap* vs = e.vs;
        QVariantMap* inst = e.inst;
        const std::function<void()> rerender = e.rerender;
        it.click([vs, inst, rerender, fk, idx] {
            vs->insert(hlpwd_kKey, fk);
            hlpwd_redraw(inst, rerender, idx, true);
        });
    }
    it << hlpwd_when(f.value(QStringLiteral("tao")), e.now);

    const double muc = hlpwd_num0(f.value(QStringLiteral("muc")));
    N ti = span(hlpwd_s(f.value(QStringLiteral("tieu_de"))));
    ti.key(QStringLiteral("span.wd-ti")).size(11.0f).lhf(1.4f);
    if (muc >= 3.0)
        ti.c(P.down).semibold(); // .wd-ti.l3
    else if (f.value(QStringLiteral("muc")).isDouble() && muc == 2.0)
        ti.c(P.amber); // .wd-ti.l2

    N body = div();
    body << ti << hlpwd_sum(hlpwd_s(f.value(QStringLiteral("tom_tat"))));
    if (NodeP card = hlpwd_card(f, e.S))
        body << card;
    body << hlpwd_meta(f);
    it << body;
    return it;
}

/// One row of the "Doanh nghiệp" branch: title is the link, optional SS-T3 recommendation card.
NodeP hlpwd_dn_row(const QJsonObject& f, const QDateTime& now) {
    N it = hlpwd_row_box(false);
    it << hlpwd_when(f.value(QStringLiteral("tao")), now);

    N body = div();
    N ti = a::link(hlpwd_s(f.value(QStringLiteral("tieu_de"))), hlpwd_safe_url(f.value(QStringLiteral("url"))));
    ti.key(QStringLiteral("a.wd-ti")).size(11.0f).lhf(1.4f);
    body << ti << hlpwd_sum(hlpwd_s(f.value(QStringLiteral("tom_tat"))));

    const QJsonValue kn = f.value(QStringLiteral("khuyen_nghi"));
    const QJsonValue gia = f.value(QStringLiteral("gia_muc_tieu"));
    if (hlpwd_truthy(kn) || hlpwd_truthy(gia)) {
        // "<tag>SS-T3</tag>\n  ${ma} · ${khuyen_nghi}" — whitespace runs collapse to one space.
        QString rest = QStringLiteral(" %1 · %2").arg(hlpwd_or(f.value(QStringLiteral("ma")), QString()),
                                                    hlpwd_or(kn, QString()));
        static const QRegularExpression spaces(QStringLiteral(" {2,}"));
        rest.replace(spaces, QStringLiteral(" "));
        N left = span();
        left << a::tag(QStringLiteral("SS-T3"), pal().amber) << text(rest);
        N right = a::v();
        right.nowrap();
        if (hlpwd_truthy(gia))
            right << text(QStringLiteral("Giá mục tiêu ")) << fmt::price(hlpwd_val(gia));
        N card = hlpwd_card_box();
        card << left << right;
        body << card;
    }
    it << body;
    return it;
}

/// drawList(): #wdl for the current filter.
NodeP hlpwd_list(const QJsonObject& W, const QVariantMap& st, const HlpWdEnv& e) {
    const QString vung = st.value(hlpwd_kVung).toString();
    const int muc = st.value(hlpwd_kMuc).toInt();
    const bool chartOnly = st.value(hlpwd_kChart).toBool();
    auto keep = [&](const QJsonObject& f) {
        return (!muc || hlpwd_num0(f.value(QStringLiteral("muc"))) >= muc) &&
               (!chartOnly || hlpwd_truthy(f.value(QStringLiteral("key"))));
    };

    N wdl = div();
    wdl.key(QStringLiteral("div#wdl"));
    int n = 0;
    if (vung == QLatin1String("DN")) {
        // Same filters as the main list: impact level and "chỉ tin có biểu đồ" (no 120 cap).
        for (const QJsonValue& fv : W.value(QStringLiteral("doanh_nghiep")).toArray()) {
            const QJsonObject f = fv.toObject();
            if (!keep(f))
                continue;
            wdl << hlpwd_dn_row(f, e.now);
            ++n;
        }
    } else {
        for (const QJsonValue& fv : W.value(QStringLiteral("feed")).toArray()) {
            if (n >= hlpwd_kMaxRows)
                break;
            const QJsonObject f = fv.toObject();
            if (vung != QLatin1String("all") && hlpwd_s(f.value(QStringLiteral("vung"))) != vung)
                continue;
            if (!keep(f))
                continue;
            wdl << hlpwd_feed_row(f, n, e);
            ++n;
        }
    }
    if (n == 0)
        wdl << a::ndD(QStringLiteral("Không có tín hiệu khớp bộ lọc."));
    return wdl;
}

/// Region chips + impact chips + "Chỉ tin có biểu đồ" (each redraws only the list in the web).
NodeP hlpwd_filter_bar(const QVariantMap& st, const HlpWdEnv& e) {
    QVariantMap* vs = e.vs;
    QVariantMap* inst = e.inst;
    const std::function<void()> rerender = e.rerender;

    N regions = hlpwd_chips();
    const QString vung = st.value(hlpwd_kVung).toString();
    for (const auto& [k, l] : hlpwd_vung()) {
        regions << a::chip(l, k == vung, [vs, inst, rerender, k = k] {
            vs->insert(hlpwd_kVung, k);
            hlpwd_redraw(inst, rerender, -1, false);
        });
    }

    N levels = hlpwd_chips();
    const int muc = st.value(hlpwd_kMuc).toInt();
    const QVector<std::pair<int, QString>> mucs = {
        {0, QStringLiteral("Mọi mức")}, {2, QStringLiteral("Ảnh hưởng ≥2")}, {3, QStringLiteral("Chỉ mức 3")}};
    for (const auto& [m, l] : mucs) {
        levels << a::chip(l, m == muc, [vs, inst, rerender, m = m] {
            vs->insert(hlpwd_kMuc, m);
            hlpwd_redraw(inst, rerender, -1, false);
        });
    }
    levels << a::chip(QStringLiteral("Chỉ tin có biểu đồ"), st.value(hlpwd_kChart).toBool(), [vs, inst, rerender] {
        vs->insert(hlpwd_kChart, !vs->value(hlpwd_kChart).toBool());
        hlpwd_redraw(inst, rerender, -1, false);
    });

    N bar = hlpwd_bar();
    bar << regions << levels;
    return bar;
}

// ---- top-level pieces of wdRender ----

/// `.catch` branch: `<div class="nd">Chưa có data/wdsignal.json — chạy <code>python3 build_wdsignal.py</code></div>`.
NodeP hlpwd_missing() {
    N nd = div();
    nd.c(pal().ink3).italic().size(10.0f);
    nd << text(QStringLiteral("Chưa có data/wdsignal.json — chạy ")) << a::code(QStringLiteral("python3 build_wdsignal.py"));
    return nd;
}

/// "N tín hiệu trong 24 giờ · tin mới nhất … · kho … tín hiệu" (mono 9.5px ink-3, margin-bottom 6px).
NodeP hlpwd_stats(const QJsonObject& W, const QDateTime& now) {
    const qint64 nowMs = now.toMSecsSinceEpoch();
    int moi24 = 0;
    for (const QJsonValue& fv : W.value(QStringLiteral("feed")).toArray()) {
        const std::optional<qint64> t = fmt::parseMs(hlpwd_s(fv.toObject().value(QStringLiteral("tao"))));
        if (t && nowMs - *t < 86400000LL)
            ++moi24;
    }
    const QString tuoi = fmt::wdAgo(hlpwd_s(W.value(QStringLiteral("tin_moi_nhat"))), now).first;
    const QJsonValue tc = W.value(QStringLiteral("tai")).toObject().value(QStringLiteral("tong_cache"));
    const QString kho = hlpwd_nullish(tc) ? QStringLiteral("—") : hlpwd_s(tc);
    N d = a::monoD();
    d.size(9.5f).c(pal().ink3).mb(6.0f)
        << text(QStringLiteral("%1 tín hiệu trong 24 giờ · tin mới nhất %2 · kho %3 tín hiệu").arg(moi24).arg(tuoi, kho));
    return d;
}

/// `.note`: ghi_chu joined by <br>, plus the low title-match series in red.
NodeP hlpwd_note(const QJsonObject& W) {
    N note = a::note();
    const QJsonArray gc = W.value(QStringLiteral("ghi_chu")).toArray();
    for (int i = 0; i < gc.size(); ++i) {
        if (i)
            note << brk();
        note << text(hlpwd_s(gc.at(i)));
    }
    const QJsonArray kt = W.value(QStringLiteral("chuoi_khop_thap")).toArray();
    if (!kt.isEmpty()) {
        QStringList names;
        for (const QJsonValue& v : kt)
            names << hlpwd_s(v);
        note << brk()
             << (span().c(pal().down)
                 << text(QStringLiteral("Chuỗi có tỷ lệ khớp tiêu đề < 0,6 (luật trích cần xem lại): ") +
                         names.join(QStringLiteral(", "))));
    }
    return note;
}

/// Warnings on top: last fetch had errors / no extraction rules yet.
void hlpwd_warnings(N& root, const QJsonObject& W, const QJsonObject& S) {
    const QJsonArray loi = W.value(QStringLiteral("tai")).toObject().value(QStringLiteral("loi")).toArray();
    if (!loi.isEmpty()) {
        QStringList parts;
        for (const QJsonValue& v : loi)
            parts << hlpwd_s(v);
        root << (a::warn() << text(QStringLiteral("Lần tải gần nhất có lỗi: %1. Danh sách dưới đây là bản đã lưu.")
                                       .arg(parts.join(QStringLiteral(" · ")))));
    }
    if (S.isEmpty()) {
        root << (a::warn() << text(QStringLiteral("Chưa có luật trích giá trị ("))
                           << a::code(QStringLiteral("widata_signal_rules.json"))
                           << text(QStringLiteral(") — danh sách tín hiệu vẫn hiện, nhưng chưa vẽ được biểu đồ.")));
    }
}

/// `.wd-split`: list | sticky chart column (2 columns only when ≥700px wide — container query).
NodeP hlpwd_split(RenderCtx& rc, const QJsonObject& W, const QVariantMap& st, const HlpWdEnv& e, bool external,
                  bool sync) {
    const QString range = st.value(hlpwd_kRange).toString();

    N bar = hlpwd_bar();
    if (NodeP sel = hlpwd_select(rc, e, external, sync))
        bar << sel;
    bar << hlpwd_range_chips(range, e);

    N col = div();
    col.key(QStringLiteral("div.wd-chartcol")).p(0.0f, 0.0f, 0.0f, 34.0f).sticky(0.0f);
    col << bar << hlpwd_chart(e.S, e.key, range);

    GridSpec g;
    g.cols = {Track{-1.0f, 1.05f, 0.0f}, Track{-1.0f, 1.0f, 0.0f}};
    g.colGap = 10.0f;
    g.rowGap = 10.0f;
    g.minWidthForCols = 700.0f;
    N split = div();
    split.key(QStringLiteral("div.wd-split")).grid(g);
    split->st.alignItems = AlignItems::Start; // .wd-chartcol { align-self: start } (keeps it sticky)
    split << hlpwd_list(W, st, e) << col;
    return split;
}

} // namespace

// =================================================================================================
// wdsignal — WiData · Market Signals (panels.js 813–846 + wdRender 984–1179)
// =================================================================================================
NodeP render_wdsignal(RenderCtx& rc) {
    if (!rc.data.wdOk) {
        if (rc.asof)
            *rc.asof = QString();
        return hlpwd_missing();
    }
    const QJsonObject& W = rc.data.wd;

    HlpWdEnv e;
    e.S = W.value(QStringLiteral("series")).toObject();
    e.vs = hlpwd_view_state(rc);
    e.inst = rc.state;
    e.rerender = rc.rerender;
    e.now = rc.now;
    if (rc.asof)
        *rc.asof = QStringLiteral("%1 · %2 chỉ tiêu").arg(hlpwd_or(W.value(QStringLiteral("cap_nhat")), QString())).arg(e.S.size());

    // A render we did not ask for is the web's full wdRender: rows rebuilt, <select> rebuilt.
    bool external = true;
    bool sync = false;
    if (e.inst) {
        external = !e.inst->take(hlpwd_kSelf).toBool();
        sync = e.inst->take(hlpwd_kSync).toBool();
        if (external)
            e.inst->insert(hlpwd_kPick, -1);
        e.pick = e.inst->value(hlpwd_kPick, -1).toInt();
    }

    QVariantMap& st = *e.vs;
    hlpwd_init_state(st);
    e.key = st.value(hlpwd_kKey).toString();
    if (!e.S.contains(e.key)) {
        // Default: the first signal of the feed that carries a series key (even one without a series).
        e.key.clear();
        for (const QJsonValue& fv : W.value(QStringLiteral("feed")).toArray()) {
            const QJsonValue k = fv.toObject().value(QStringLiteral("key"));
            if (hlpwd_truthy(k)) {
                e.key = hlpwd_s(k);
                break;
            }
        }
        st.insert(hlpwd_kKey, e.key);
    }

    N root = div();
    root.key(QStringLiteral("div.wd"));
    hlpwd_warnings(root, W, e.S);
    root << hlpwd_filter_bar(st, e) << hlpwd_stats(W, e.now) << hlpwd_split(rc, W, st, e, external, sync)
         << hlpwd_note(W);
    return root;
}

} // namespace fincept::screens::hlp