// src/screens/hdcv_launchpad/HlpPanels_Ck.cpp
// HĐCV LAUNCHPAD — the six "Chứng khoán · Mã & Danh mục" components of panels.js, translated line
// for line into node trees (HlpAtoms + HlpFmt + HlpCharts):
//   cong    (panels.js 54–83)   CỔNG · Market Regime
//   idx     (panels.js 86–114)  VN-INDEX · P/E · EX-VIN
//   monitor (panels.js 117–144) MONITOR · VN200 (linked, filter input)
//   desc    (panels.js 147–173) <ctx> · MÔ TẢ (linked)
//   chart   (panels.js 176–200) <ctx> · VÙNG GIÁ σ (linked)
//   sigma   (panels.js 203–236) THƯỚC σ · <ctx> trên trục (linked)
// Data = rc.data.D (launchpad/data/launchpad_data.json). Inline `style="…"` of the templates are
// reproduced as builder calls next to the class atom they modify. Missing numbers → [CẦN DATA].
#include "screens/hdcv_launchpad/HlpAtoms.h"
#include "screens/hdcv_launchpad/HlpCharts.h"
#include "screens/hdcv_launchpad/HlpFmt.h"
#include "screens/hdcv_launchpad/HlpPanels.h"
#include "screens/hdcv_launchpad/HlpTheme.h"

#include <QByteArray>
#include <QDateTime>
#include <QFile>
#include <QFileInfo>
#include <QHash>
#include <QJsonArray>
#include <QJsonDocument>
#include <QJsonObject>
#include <QLineEdit>
#include <QRegularExpression>
#include <QStringList>
#include <QVector>

#include <algorithm>
#include <cmath>
#include <optional>

namespace fincept::screens::hlp {

namespace {

/// JS truthiness of a JSON value (`if (!g.state)`, `r.signal ? … : …`, `x || '—'`).
bool hlpck_truthy(const QJsonValue& v) {
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

/// JS `v == null ? ND : (+v)…` — null/missing → nullopt, numbers as-is, numeric strings via `+v`.
std::optional<double> hlpck_n(const QJsonValue& v) {
    if (v.isNull() || v.isUndefined())
        return std::nullopt;
    if (v.isDouble())
        return v.toDouble();
    return fmt::plus(v);
}

/// JS `x || dflt` for display strings (esc() applied by the node text engine, never as HTML).
QString hlpck_or(const QJsonValue& v, const QString& dflt = QString()) {
    return hlpck_truthy(v) ? fmt::str(v) : dflt;
}

/// stamp(as, s): `el.textContent = s || ''`.
void hlpck_stamp(RenderCtx& rc, const QString& s) {
    if (rc.asof)
        *rc.asof = s;
}

/// find(D, t): first ticker row whose `t` equals `t`.
std::optional<QJsonObject> hlpck_find(const QJsonObject& D, const QString& t) {
    const QJsonArray rows = D.value(QStringLiteral("tickers")).toArray();
    for (const QJsonValue& r : rows) {
        const QJsonObject o = r.toObject();
        if (o.value(QStringLiteral("t")).isString() && o.value(QStringLiteral("t")).toString() == t)
            return o;
    }
    return std::nullopt;
}

/// safeUrl(u): only http(s) passes, everything else becomes '#'.
QString hlpck_safe_url(const QString& u) {
    static const QRegularExpression re(QStringLiteral("^https?://"),
                                       QRegularExpression::CaseInsensitiveOption);
    return re.match(u).hasMatch() ? u : QStringLiteral("#");
}

/// `${zSpan}` preceded by the template's single space; skipped when the zone is empty (the trailing
/// space would collapse at the end of the line in CSS anyway).
void hlpck_zone(N& parent, const QJsonValue& zone) {
    const QString z = hlpck_or(zone);
    if (z.isEmpty())
        return;
    parent << text(QStringLiteral(" ")) << atoms::zSpan(z);
}

// ---------------------------------------------------------------------------------------------
// Key order of `tickers[].links`. QJsonObject sorts keys alphabetically, but the web prints
// Object.entries(L) in insertion order ("vietcap_iq · miquant · simplize"). Recover that order
// from the raw launchpad_data.json (cached per path + mtime + size).
// ---------------------------------------------------------------------------------------------
struct HlpckLinkOrder {
    QString path;
    QDateTime mtime;
    qint64 size = -1;
    QHash<QString, QStringList> byTicker;
};

int hlpck_skip_ws(const QByteArray& s, int i) {
    while (i < s.size() && (s[i] == ' ' || s[i] == '\n' || s[i] == '\r' || s[i] == '\t'))
        ++i;
    return i;
}

/// Reads a JSON string starting at s[i] == '"'. Returns the index after the closing quote, or -1.
int hlpck_read_string(const QByteArray& s, int i, QString* out) {
    if (i >= s.size() || s[i] != '"')
        return -1;
    const int start = i;
    ++i;
    while (i < s.size() && s[i] != '"') {
        if (s[i] == '\\')
            ++i;
        ++i;
    }
    if (i >= s.size())
        return -1;
    ++i;
    if (out) {
        // Decode escapes exactly like the JSON parser does.
        const QByteArray wrapped = '[' + s.mid(start, i - start) + ']';
        *out = QJsonDocument::fromJson(wrapped).array().at(0).toString();
    }
    return i;
}

/// Skips any JSON value starting at s[i]. Returns the index after it, or -1.
int hlpck_skip_value(const QByteArray& s, int i) {
    i = hlpck_skip_ws(s, i);
    if (i >= s.size())
        return -1;
    if (s[i] == '"')
        return hlpck_read_string(s, i, nullptr);
    if (s[i] == '{' || s[i] == '[') {
        int depth = 0;
        while (i < s.size()) {
            const char c = s[i];
            if (c == '"') {
                i = hlpck_read_string(s, i, nullptr);
                if (i < 0)
                    return -1;
                continue;
            }
            if (c == '{' || c == '[')
                ++depth;
            else if (c == '}' || c == ']') {
                if (--depth == 0)
                    return i + 1;
            }
            ++i;
        }
        return -1;
    }
    while (i < s.size() && s[i] != ',' && s[i] != '}' && s[i] != ']')
        ++i;
    return i;
}

/// Keys of the flat object whose '{' is at s[i], in file order.
QStringList hlpck_object_keys(const QByteArray& s, int i) {
    QStringList keys;
    if (i >= s.size() || s[i] != '{')
        return keys;
    ++i;
    while (true) {
        i = hlpck_skip_ws(s, i);
        if (i >= s.size() || s[i] == '}')
            break;
        QString key;
        i = hlpck_read_string(s, i, &key);
        if (i < 0)
            break;
        i = hlpck_skip_ws(s, i);
        if (i >= s.size() || s[i] != ':')
            break;
        i = hlpck_skip_value(s, i + 1);
        if (i < 0)
            break;
        keys << key;
        i = hlpck_skip_ws(s, i);
        if (i < s.size() && s[i] == ',') {
            ++i;
            continue;
        }
        break;
    }
    return keys;
}

const QHash<QString, QStringList>& hlpck_link_orders(const Data& d) {
    static HlpckLinkOrder cache;
    const QString path = d.systemDir + QStringLiteral("/launchpad/data/launchpad_data.json");
    const QFileInfo fi(path);
    if (cache.path == path && cache.mtime == fi.lastModified() && cache.size == fi.size())
        return cache.byTicker;
    cache.path = path;
    cache.mtime = fi.lastModified();
    cache.size = fi.size();
    cache.byTicker.clear();

    QFile f(path);
    if (!f.open(QIODevice::ReadOnly))
        return cache.byTicker;
    const QByteArray raw = f.readAll();

    // Positions of every `"t":"XXX"` and every `"links":{` (byte offsets in the UTF-8 buffer).
    static const QRegularExpression reT(QStringLiteral("\"t\"\\s*:\\s*\"((?:[^\"\\\\]|\\\\.)*)\""));
    static const QRegularExpression reL(QStringLiteral("\"links\"\\s*:\\s*\\{"));
    // Work on Latin-1 view of the bytes so regex offsets are byte offsets (keys/tickers are ASCII).
    const QString lat = QString::fromLatin1(raw);
    QVector<QPair<int, QString>> tickers;
    for (auto it = reT.globalMatch(lat); it.hasNext();) {
        const auto m = it.next();
        tickers.append({static_cast<int>(m.capturedStart()), m.captured(1)});
    }
    int ti = -1;
    for (auto it = reL.globalMatch(lat); it.hasNext();) {
        const auto m = it.next();
        const int pos = static_cast<int>(m.capturedStart());
        while (ti + 1 < tickers.size() && tickers[ti + 1].first < pos)
            ++ti;
        if (ti < 0)
            continue;
        const QString& t = tickers[ti].second;
        if (cache.byTicker.contains(t))
            continue;
        cache.byTicker.insert(t, hlpck_object_keys(raw, static_cast<int>(m.capturedEnd()) - 1));
    }
    return cache.byTicker;
}

/// Object.entries(L) key order for ticker `t`: file order first, then any key the scan missed.
QStringList hlpck_link_keys(const Data& d, const QString& t, const QJsonObject& L) {
    QStringList out;
    const auto& orders = hlpck_link_orders(d);
    const auto it = orders.constFind(t);
    if (it != orders.constEnd()) {
        for (const QString& k : *it)
            if (L.contains(k) && !out.contains(k))
                out << k;
    }
    for (const QString& k : L.keys())
        if (!out.contains(k))
            out << k;
    return out;
}

/// `<table>` of the THƯỚC σ panel (tbl(list) in panels.js 219–223).
NodeP hlpck_sigma_table(const QVector<QJsonObject>& list, const QString& ctx,
                        const std::function<void(const QString&)>& setCtx) {
    N t = atoms::tbl();
    t << atoms::thead({atoms::thC(QStringLiteral("Mã")), atoms::thC(QStringLiteral("P/E"), true),
                       atoms::thC(QStringLiteral("σ"), true), atoms::thC(QStringLiteral("Về fair"), true),
                       atoms::thC(QStringLiteral("Conv"), true)});
    for (const QJsonObject& r : list) {
        const QString tk = fmt::str(r.value(QStringLiteral("t")));
        N row = atoms::trow(tk == ctx);
        row.click([setCtx, tk] {
            if (setCtx)
                setCtx(tk);
        });
        row << atoms::tdTk(tk);
        row << (atoms::tdN() << fmt::n2(hlpck_n(r.value(QStringLiteral("pe")))));
        row << (atoms::tdN() << fmt::sig(hlpck_n(r.value(QStringLiteral("pe_sig")))));
        row << (atoms::tdN() << fmt::pc(hlpck_n(r.value(QStringLiteral("pe_up")))));
        row << (atoms::tdN() << fmt::n1(hlpck_n(r.value(QStringLiteral("conv")))));
        t << row;
    }
    return t;
}

} // namespace

// =============================================================================================
// cong — CỔNG · Market Regime (panels.js 54–83)
// =============================================================================================
NodeP render_cong(RenderCtx& rc) {
    const QJsonObject g = rc.data.D.value(QStringLiteral("cong")).toObject();
    if (!hlpck_truthy(g.value(QStringLiteral("state"))))
        return div() << (atoms::warn() << text(QStringLiteral("Chưa có market_regime.json")));

    QString ga = hlpck_or(g.value(QStringLiteral("generated_at"))).left(16);
    const int tpos = ga.indexOf(QLatin1Char('T')); // String.replace('T',' ') — first match only
    if (tpos >= 0)
        ga[tpos] = QLatin1Char(' ');
    hlpck_stamp(rc, ga);

    const auto sub = [&g](const char* key) { return g.value(QLatin1String(key)).toObject(); };
    struct Four {
        const char* key;
        const char* label;
    };
    static const Four four[] = {
        {"trend", "Trend"}, {"breadth", "Breadth"}, {"cap_rotation", "Rotation"}, {"global_macro", "Macro"}};

    N root = div();
    root << atoms::lbl(QStringLiteral("Trạng thái"));
    root << atoms::big(fmt::str(g.value(QStringLiteral("state")))).c(pal().amber);
    root << (atoms::monoD().c(pal().ink2).size(11)
             << text(QStringLiteral("score ")) << fmt::n1(hlpck_n(g.value(QStringLiteral("regime_score"))))
             << text(QStringLiteral("/100 · size ×"))
             << fmt::n2(hlpck_n(g.value(QStringLiteral("modulation")).toObject().value(QStringLiteral("size_mult")))));

    N tl = atoms::tiles();
    tl.mt(9);
    for (const Four& f : four) {
        const QJsonObject s = sub(f.key);
        N tile = atoms::tile();
        tile << atoms::lbl(QLatin1String(f.label));
        tile << (atoms::monoD().size(14) << fmt::n1(hlpck_n(s.value(QStringLiteral("score")))));
        N st = div();
        st.size(9.5).c(pal().ink3);
        const QString state = hlpck_or(s.value(QStringLiteral("state")));
        if (!state.isEmpty())
            st << text(state);
        tile << st;
        tl << tile;
    }
    root << tl;

    const QJsonObject br = sub("breadth"), cr = sub("cap_rotation"), gm = sub("global_macro");
    N rows = div();
    rows.mt(9);
    rows << (atoms::row() << atoms::k(QStringLiteral("% trên MA50"))
                          << (atoms::v() << fmt::n1(hlpck_n(br.value(QStringLiteral("pct_above_ma50"))))
                                         << text(QStringLiteral("%"))));
    rows << (atoms::row() << atoms::k(QStringLiteral("% trên MA200"))
                          << (atoms::v() << fmt::n1(hlpck_n(br.value(QStringLiteral("pct_above_ma200"))))
                                         << text(QStringLiteral("%"))));
    rows << (atoms::row() << atoms::k(QStringLiteral("Dẫn dắt 3T"))
                          << (atoms::v() << text(hlpck_or(cr.value(QStringLiteral("leader_3m")), QStringLiteral("—")))));
    rows << atoms::lastRow(atoms::row() << atoms::k(QStringLiteral("US10Y / DXY"))
                                        << (atoms::v() << fmt::n2(hlpck_n(gm.value(QStringLiteral("us10y"))))
                                                       << text(QStringLiteral(" / "))
                                                       << fmt::n1(hlpck_n(gm.value(QStringLiteral("dxy"))))));
    root << rows;

    if (hlpck_truthy(g.value(QStringLiteral("note"))))
        root << (atoms::note() << text(fmt::str(g.value(QStringLiteral("note")))));
    return root;
}

// =============================================================================================
// idx — VN-INDEX · P/E · EX-VIN (panels.js 86–114)
// =============================================================================================
NodeP render_idx(RenderCtx& rc) {
    const QJsonObject i = rc.data.D.value(QStringLiteral("index")).toObject();
    if (!hlpck_truthy(i.value(QStringLiteral("pe_now"))))
        return div() << (atoms::warn() << text(QStringLiteral("Chưa có hhp_vn100_valuation.json")));
    hlpck_stamp(rc, hlpck_or(i.value(QStringLiteral("as_of"))));

    const auto num17 = [](std::optional<double> v, const QString& suffix = QString()) {
        N m = atoms::monoD();
        m.size(17) << fmt::n1(v);
        if (!suffix.isEmpty())
            m << text(suffix);
        return m;
    };
    const auto sigLine = [&i](const char* sigKey, const char* zoneKey) {
        N d = div();
        d.size(9.5) << fmt::sig(hlpck_n(i.value(QLatin1String(sigKey))));
        hlpck_zone(d, i.value(QLatin1String(zoneKey)));
        return d;
    };

    N root = div();
    N tl = atoms::tiles();
    tl << (atoms::tile(true) << atoms::lbl(QStringLiteral("VN-Index"))
                             << num17(hlpck_n(i.value(QStringLiteral("price_now")))));
    tl << (atoms::tile() << atoms::lbl(QStringLiteral("P/E toàn phần"))
                         << num17(hlpck_n(i.value(QStringLiteral("pe_now")))) << sigLine("pe_sigma", "pe_zone"));
    tl << (atoms::tile(true) << atoms::lbl(QStringLiteral("P/E ex-Vin"))
                             << num17(hlpck_n(i.value(QStringLiteral("exv3_pe_now"))))
                             << sigLine("exv3_pe_sigma", "exv3_pe_zone"));
    tl << (atoms::tile() << atoms::lbl(QStringLiteral("Họ Vin / vốn hoá"))
                         << num17(hlpck_n(i.value(QStringLiteral("w3_now"))), QStringLiteral("%")));
    root << tl;

    root << atoms::lbl(QStringLiteral("P/E toàn phần (xanh) — chuỗi ~1 năm")).mt(9);
    root << charts::spark(i.value(QStringLiteral("spark_pe_full")).toArray());

    N t = atoms::tbl();
    t.mt(7);
    t << atoms::thead({atoms::thC(QStringLiteral("Họ Vin")), atoms::thC(QStringLiteral("Vốn hoá (ngh.tỷ)"), true),
                       atoms::thC(QStringLiteral("P/E"), true), atoms::thC(QStringLiteral("P/B"), true)});
    const auto setCtx = rc.setCtx;
    for (const QJsonValue& vv : i.value(QStringLiteral("vic3")).toArray()) {
        const QJsonObject v = vv.toObject();
        const QString tk = fmt::str(v.value(QStringLiteral("ticker")));
        N row = atoms::trow();
        row.click([setCtx, tk] {
            if (setCtx)
                setCtx(tk);
        });
        row << atoms::tdTk(tk);
        row << (atoms::tdN() << fmt::n1(hlpck_n(v.value(QStringLiteral("mcap_kty")))));
        row << (atoms::tdN() << fmt::n2(hlpck_n(v.value(QStringLiteral("pe")))));
        row << (atoms::tdN() << fmt::n2(hlpck_n(v.value(QStringLiteral("pb")))));
        t << row;
    }
    root << t;

    root << (atoms::note() << text(QStringLiteral("P/B toàn phần ")) << fmt::n2(hlpck_n(i.value(QStringLiteral("pb_full_now"))))
                           << text(QStringLiteral(" · ex-Vin ")) << fmt::n2(hlpck_n(i.value(QStringLiteral("pb_exv3_now"))))
                           << text(QStringLiteral(". Nêu cả hai con số — chỉ số toàn phần bị VIC bóp méo nặng.")));
    return root;
}

// =============================================================================================
// monitor — MONITOR · VN200 (panels.js 117–144)
// =============================================================================================
NodeP render_monitor(RenderCtx& rc) {
    const QJsonArray rows = rc.data.D.value(QStringLiteral("tickers")).toArray();
    hlpck_stamp(rc, QStringLiteral("%1 mã").arg(rows.size()));

    // Filter text. The web rebuilds the <input> on every render of this panel, so a setCtx (row
    // click / GO) clears the filter; a plain re-render (typing, data reload) keeps it.
    QVariantMap* st = rc.state;
    QString q;
    if (st) {
        q = st->value(QStringLiteral("q")).toString();
        if (st->contains(QStringLiteral("ctx")) && st->value(QStringLiteral("ctx")).toString() != rc.ctx) {
            q.clear();
            st->insert(QStringLiteral("q"), QString());
        }
        st->insert(QStringLiteral("ctx"), rc.ctx);
    }

    QLineEdit* le = rc.lineEdit ? rc.lineEdit(QStringLiteral("f")) : nullptr;
    if (le) {
        le->setPlaceholderText(QStringLiteral("Lọc mã / ngành / tín hiệu…"));
        le->setAccessibleName(QStringLiteral("Lọc"));
        if (le->text() != q)
            le->setText(q);
        if (!le->property("hlpck_wired").toBool()) {
            le->setProperty("hlpck_wired", true);
            const auto rerender = rc.rerender;
            QObject::connect(le, &QLineEdit::textEdited, le, [st, rerender](const QString& s) {
                if (st)
                    st->insert(QStringLiteral("q"), s);
                if (rerender)
                    rerender();
            });
        }
    }

    N root = div();
    if (le)
        root << atoms::filterInput(le);

    N t = atoms::tbl();
    t << atoms::thead({atoms::thC(QStringLiteral("Mã")), atoms::thC(QStringLiteral("Giá"), true),
                       atoms::thC(QStringLiteral("P/E σ"), true), atoms::thC(QStringLiteral("P/B σ"), true),
                       atoms::thC(QStringLiteral("Conv"), true), atoms::thC(QStringLiteral("Tín hiệu")),
                       atoms::thC(QStringLiteral("RRG"))});

    const QString ql = q.toLower();
    const auto setCtx = rc.setCtx;
    int shown = 0;
    for (const QJsonValue& rv : rows) {
        if (shown >= 220) // f.slice(0, 220)
            break;
        const QJsonObject r = rv.toObject();
        const QString tk = fmt::str(r.value(QStringLiteral("t")));
        if (!ql.isEmpty() && !tk.toLower().contains(ql) &&
            !hlpck_or(r.value(QStringLiteral("sector"))).toLower().contains(ql) &&
            !hlpck_or(r.value(QStringLiteral("signal"))).toLower().contains(ql))
            continue;
        ++shown;

        N row = atoms::trow(tk == rc.ctx);
        row.click([setCtx, tk] {
            if (setCtx)
                setCtx(tk);
        });
        row << atoms::tdTk(tk);
        row << (atoms::tdN() << fmt::price(hlpck_n(r.value(QStringLiteral("price")))));
        row << (atoms::tdN() << fmt::sig(hlpck_n(r.value(QStringLiteral("pe_sig")))));
        row << (atoms::tdN() << fmt::sig(hlpck_n(r.value(QStringLiteral("pb_sig")))));
        row << (atoms::tdN() << fmt::n1(hlpck_n(r.value(QStringLiteral("conv")))));

        N sigTd = atoms::tdC();
        const QJsonValue sv = r.value(QStringLiteral("signal"));
        if (hlpck_truthy(sv)) {
            const QString s = fmt::str(sv);
            const QColor col = s == QLatin1String("BUY")     ? pal().up
                               : s == QLatin1String("WATCH") ? pal().amber
                                                             : pal().ink3;
            sigTd << atoms::tag(s, col);
        } else {
            sigTd << fmt::ND();
        }
        row << sigTd;

        N rrg = atoms::tdC();
        rrg.size(10).c(pal().ink2) << text(hlpck_or(r.value(QStringLiteral("rrg")), QStringLiteral("—")));
        row << rrg;
        t << row;
    }
    if (shown == 0) {
        N cell = atoms::tdC();
        cell.colspan(7).c(pal().ink3).italic().size(10) << text(QStringLiteral("Không có mã khớp"));
        t << (atoms::trow() << cell);
    }
    root << t;
    return root;
}

// =============================================================================================
// desc — <ctx> · MÔ TẢ (panels.js 147–173)
// =============================================================================================
NodeP render_desc(RenderCtx& rc) {
    const auto found = hlpck_find(rc.data.D, rc.ctx);
    if (!found) {
        N w = atoms::warn();
        w << text(QStringLiteral("Không có ")) << atoms::b(rc.ctx) << text(QStringLiteral(" trong universe 194 mã."));
        hlpck_stamp(rc, QString());
        return div() << w;
    }
    const QJsonObject& r = *found;
    hlpck_stamp(rc, hlpck_or(r.value(QStringLiteral("sector"))));
    const QJsonObject L = r.value(QStringLiteral("links")).toObject();
    const auto val = [&r](const char* key) { return r.value(QLatin1String(key)); };

    N root = div();

    // <div style="display:flex;align-items:baseline;gap:9px">
    N head = div();
    head.flex(Justify::Start, AlignItems::Baseline, 9);
    head << atoms::tk(fmt::str(val("t"))).size(19);
    head << (atoms::monoS().size(15) << fmt::price(hlpck_n(val("price"))));
    if (hlpck_truthy(val("signal")))
        head << atoms::tag(fmt::str(val("signal")), pal().amber);
    root << head;

    {
        N v = atoms::v();
        v << fmt::n2(hlpck_n(val("pe"))) << text(QStringLiteral(" · ")) << fmt::sig(hlpck_n(val("pe_sig")));
        hlpck_zone(v, val("pe_zone"));
        root << (atoms::row() << atoms::k(QStringLiteral("P/E hiện tại")) << v);
    }
    {
        N v = atoms::v();
        v << fmt::n2(hlpck_n(val("pb"))) << text(QStringLiteral(" · ")) << fmt::sig(hlpck_n(val("pb_sig")));
        hlpck_zone(v, val("pb_zone"));
        root << (atoms::row() << atoms::k(QStringLiteral("P/B hiện tại")) << v);
    }
    root << (atoms::row() << atoms::k(QStringLiteral("Về fair (P/E)"))
                          << (atoms::v() << fmt::pc(hlpck_n(val("pe_up")))));
    {
        N v = atoms::v();
        v << text(QStringLiteral("P/E ")) << fmt::n1(hlpck_n(val("fwd_pe"))) << text(QStringLiteral(" · P/B "))
          << fmt::n1(hlpck_n(val("fwd_pb")));
        const QString src = hlpck_or(val("fwd_src"));
        if (!src.isEmpty())
            v << text(QStringLiteral(" ")) << (span(src).c(pal().ink3));
        root << (atoms::row() << atoms::k(QStringLiteral("Forward 26F")) << v);
    }
    {
        N v = atoms::v();
        v << fmt::n1(hlpck_n(val("conv"))) << text(QStringLiteral(" · size "));
        const auto sz = hlpck_n(val("size_pct"));
        if (!sz)
            v << fmt::ND();
        else
            v << text(fmt::n2s(sz) + QStringLiteral("%"));
        root << (atoms::row() << atoms::k(QStringLiteral("Conviction")) << v);
    }
    root << (atoms::row() << atoms::k(QStringLiteral("RRG / RS"))
                          << (atoms::v() << text(hlpck_or(val("rrg"), QStringLiteral("—")) + QStringLiteral(" · "))
                                         << fmt::n1(hlpck_n(val("rs")))));
    root << (atoms::row() << atoms::k(QStringLiteral("Độ tin σ"))
                          << (atoms::v() << text(QStringLiteral("P/E ") +
                                                 (hlpck_truthy(val("pe_ok")) ? QStringLiteral("✓")
                                                                             : QStringLiteral("✗ sd/μ cao")) +
                                                 QStringLiteral(" · P/B ") +
                                                 (hlpck_truthy(val("pb_ok")) ? QStringLiteral("✓")
                                                                             : QStringLiteral("✗")))));

    if (hlpck_truthy(val("cat")))
        root << (atoms::note() << atoms::b(QStringLiteral("Catalyst:"))
                               << text(QStringLiteral(" ") + fmt::str(val("cat"))));
    if (hlpck_truthy(val("brk"))) {
        N n = atoms::note();
        n.c(pal().down) << atoms::b(QStringLiteral("Điểm gãy thesis:")) << text(QStringLiteral(" ") + fmt::str(val("brk")));
        root << n;
    }

    N links = atoms::note();
    const QStringList keys = hlpck_link_keys(rc.data, fmt::str(val("t")), L);
    if (keys.isEmpty()) {
        links << text(QStringLiteral("Không có link nguồn"));
    } else {
        bool first = true;
        for (const QString& key : keys) {
            if (!first)
                links << text(QStringLiteral(" · "));
            first = false;
            links << atoms::link(key, hlpck_safe_url(fmt::str(L.value(key))));
        }
    }
    root << links;
    return root;
}

// =============================================================================================
// chart — <ctx> · VÙNG GIÁ σ (panels.js 176–200)
// =============================================================================================
NodeP render_chart(RenderCtx& rc) {
    const auto found = hlpck_find(rc.data.D, rc.ctx);
    if (!found) {
        // The web does not stamp here: `.asof` keeps whatever it showed before.
        N w = atoms::warn();
        w << text(QStringLiteral("Không có ")) << atoms::b(rc.ctx) << text(QStringLiteral("."));
        return div() << w;
    }
    const QJsonObject& r = *found;
    const auto val = [&r](const char* key) { return r.value(QLatin1String(key)); };
    const bool peOk = hlpck_truthy(val("pe_ok"));
    hlpck_stamp(rc, peOk ? QStringLiteral("σ tin cậy") : QStringLiteral("σ kém tin cậy"));

    N root = div();
    root << (atoms::lbl() << text(QStringLiteral("P/E — ")) << fmt::n2(hlpck_n(val("pe")))
                          << text(QStringLiteral(" hiện tại")));
    root << charts::sigmaBar(hlpck_n(val("pe_sig")));
    {
        N d = div();
        d.size(10.5).c(pal().ink2).mb(10);
        d << fmt::sig(hlpck_n(val("pe_sig"))) << text(QStringLiteral(" · "))
          << atoms::zSpan(hlpck_or(val("pe_zone"))) << text(QStringLiteral(" · về fair "))
          << fmt::pc(hlpck_n(val("pe_up")));
        if (!peOk)
            d << text(QStringLiteral(" · ")) << atoms::down(QStringLiteral("sd/μ ≥ 0,6 — band kém tin, đọc bằng P/B"));
        root << d;
    }
    root << (atoms::lbl() << text(QStringLiteral("P/B — ")) << fmt::n2(hlpck_n(val("pb")))
                          << text(QStringLiteral(" hiện tại")));
    root << charts::sigmaBar(hlpck_n(val("pb_sig")));
    {
        N d = div();
        d.size(10.5).c(pal().ink2);
        d << fmt::sig(hlpck_n(val("pb_sig"))) << text(QStringLiteral(" · "))
          << atoms::zSpan(hlpck_or(val("pb_zone"))) << text(QStringLiteral(" · về fair "))
          << fmt::pc(hlpck_n(val("pb_up")));
        root << d;
    }
    root << (atoms::note() << text(QStringLiteral(
                 "σ tính trên chuỗi ratio lịch sử của CHÍNH mã này (winsorize P5–P95, ≥250 phiên), "
                 "không phải z-score toàn thị trường. Ngân hàng và mã chu kỳ đọc bằng P/B. "
                 "Nguồn: VnDirect finfo qua engine HHP.")));
    return root;
}

// =============================================================================================
// sigma — THƯỚC σ · <ctx> trên trục (panels.js 203–236)
// =============================================================================================
NodeP render_sigma(RenderCtx& rc) {
    QVector<QJsonObject> rows;
    for (const QJsonValue& rv : rc.data.D.value(QStringLiteral("tickers")).toArray()) {
        const QJsonObject r = rv.toObject();
        if (hlpck_n(r.value(QStringLiteral("pe_sig"))) && hlpck_truthy(r.value(QStringLiteral("pe_ok"))))
            rows << r;
    }
    hlpck_stamp(rc, QStringLiteral("%1 mã σ tin cậy").arg(rows.size()));

    const auto sigOf = [](const QJsonObject& r) { return *hlpck_n(r.value(QStringLiteral("pe_sig"))); };
    int cheap = 0, rich = 0;
    QVector<charts::RulerDot> dots;
    dots.reserve(rows.size());
    for (const QJsonObject& r : rows) {
        const double s = sigOf(r);
        if (s <= -1)
            ++cheap;
        if (s >= 1)
            ++rich;
        dots.append({fmt::str(r.value(QStringLiteral("t"))), s});
    }
    QVector<QJsonObject> sorted = rows;
    std::stable_sort(sorted.begin(), sorted.end(),
                     [&sigOf](const QJsonObject& a, const QJsonObject& b) { return sigOf(a) < sigOf(b); });

    const auto setCtx = rc.setCtx;
    N root = div();
    root << charts::ruler(dots, rc.ctx, [setCtx](const QString& t) {
        if (setCtx)
            setCtx(t);
    });

    N tl = atoms::tiles();
    tl.mb(8);
    tl << (atoms::tile() << atoms::lbl(QStringLiteral("RẺ <−1σ"))
                         << atoms::monoD(QString::number(cheap)).size(15).c(pal().cheap));
    tl << (atoms::tile() << atoms::lbl(QStringLiteral("Trung tính"))
                         << atoms::monoD(QString::number(rows.size() - cheap - rich)).size(15));
    tl << (atoms::tile() << atoms::lbl(QStringLiteral("ĐẮT >+1σ"))
                         << atoms::monoD(QString::number(rich)).size(15).c(pal().rich));
    root << tl;

    root << atoms::lbl(QStringLiteral("Rẻ nhất theo σ"));
    root << hlpck_sigma_table(sorted.mid(0, 14), rc.ctx, setCtx);
    root << atoms::lbl(QStringLiteral("Đắt nhất theo σ")).mt(9);
    QVector<QJsonObject> top = sorted.mid(std::max<qsizetype>(0, sorted.size() - 8)); // slice(-8)
    std::reverse(top.begin(), top.end());
    root << hlpck_sigma_table(top, rc.ctx, setCtx);
    return root;
}

} // namespace fincept::screens::hlp
