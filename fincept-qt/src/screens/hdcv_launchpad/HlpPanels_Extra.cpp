// src/screens/hdcv_launchpad/HlpPanels_Extra.cpp
// HĐCV Launchpad — the five PANELS entries that read launchpad_data.json but are not on the three
// Fincept dashboards (the "+ Component" sheet offers them), translated template for template:
//   sector  (panels.js 239–251) CHUYỂN ĐỘNG NGÀNH          — D.sectors.moves sorted by 5-session %
//   bidv    (panels.js 254–278) ĐIỂM NGÀNH · GHTD ⚠ NỘI BỘ — D.sectors.diem_changes / ghtd_alerts
//   flash   (panels.js 339–353) ỨNG VIÊN FLASHNOTE         — D.flash + D.weekly
//   reports (panels.js 356–378) THƯ VIỆN BÁO CÁO           — D.reports, `.f` filter over JSON.stringify(x)
//   prov    (panels.js 381–402) NGUỒN · ĐỘ TƯƠI            — D.meta.sources, age = (now − mtime)/36e5 h
// Same conventions as HlpPanels_Misc.cpp: whitespace between inline elements is what the HTML templates
// collapse to (single spaces); `esc(x)` is plain node text (the engine never parses HTML).
#include "screens/hdcv_launchpad/HlpAtoms.h"
#include "screens/hdcv_launchpad/HlpFmt.h"
#include "screens/hdcv_launchpad/HlpPanels.h"

#include <QJsonArray>
#include <QJsonObject>
#include <QJsonValue>
#include <QLineEdit>
#include <QStringList>
#include <QVariant>

#include <algorithm>
#include <cmath>
#include <optional>

namespace fincept::screens::hlp {

namespace {

namespace a = atoms;

/// JS truthiness of a JSON value (undefined/null/false/0/NaN/"" → false).
bool hlpext_truthy(const QJsonValue& v) {
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

/// esc(s) = String(s ?? '') — unlike fmt::str, 0 and false print ("0", "false").
QString hlpext_esc(const QJsonValue& v) {
    switch (v.type()) {
        case QJsonValue::String:
            return v.toString();
        case QJsonValue::Double:
            return fmt::jsString(v.toDouble());
        case QJsonValue::Bool:
            return v.toBool() ? QStringLiteral("true") : QStringLiteral("false");
        case QJsonValue::Array: {
            QStringList parts;
            for (const QJsonValue& x : v.toArray())
                parts << hlpext_esc(x);
            return parts.join(QLatin1Char(','));
        }
        case QJsonValue::Object:
            return QStringLiteral("[object Object]");
        default:
            return QString();
    }
}

/// `x || fallback` for display text.
QString hlpext_or(const QJsonValue& v, const QString& fallback = QString()) {
    return hlpext_truthy(v) ? hlpext_esc(v) : fallback;
}

/// `v == null ? ND : (+v)…` — null/missing → nullopt, numbers as-is, numeric strings via `+v`.
std::optional<double> hlpext_n(const QJsonValue& v) {
    if (v.isNull() || v.isUndefined())
        return std::nullopt;
    if (v.isDouble())
        return v.toDouble();
    return fmt::plus(v);
}

/// stamp(as, s): `el.textContent = s || ''`.
void hlpext_stamp(RenderCtx& rc, const QString& s) {
    if (rc.asof)
        *rc.asof = s;
}

/// `<td colspan="n" class="nd">msg</td>` inside a plain `<tr>`.
NodeP hlpext_ndRow(int colspan, const QString& msg) {
    N cell = a::tdC();
    cell.colspan(colspan).c(pal().ink3).italic().size(10.0f) << text(msg);
    return a::trow() << cell;
}

} // namespace

// =================================================================================================
// sector — Chuyển động ngành · giá (panels.js 239–251)
// =================================================================================================
NodeP render_sector(RenderCtx& rc) {
    const QJsonObject s = rc.data.D.value(QStringLiteral("sectors")).toObject();
    QVector<QJsonObject> rows;
    for (const QJsonValue& v : s.value(QStringLiteral("moves")).toArray())
        rows.push_back(v.toObject());
    // .sort((a, b) => (b.d5_pct ?? -99) - (a.d5_pct ?? -99)) — a first iff cmp < 0; V8's sort is stable
    const auto d5 = [](const QJsonObject& r) { return fmt::num(r.value(QStringLiteral("d5_pct"))).value_or(-99.0); };
    std::stable_sort(rows.begin(), rows.end(),
                     [&d5](const QJsonObject& x, const QJsonObject& y) { return d5(y) - d5(x) < 0; });

    N root = div();
    if (rows.isEmpty()) {
        root << (a::warn() << text(QStringLiteral("Chưa có sector_moves")));
        return root;
    }
    hlpext_stamp(rc, hlpext_or(s.value(QStringLiteral("asof"))).section(QLatin1Char('|'), 0, 0));

    N tb = a::tbl();
    tb << a::thead({a::thC(QStringLiteral("Ngành")), a::thC(QStringLiteral("Mã"), true),
                    a::thC(QStringLiteral("1 phiên"), true), a::thC(QStringLiteral("5 phiên"), true)});
    for (const QJsonObject& r : rows) {
        N row = a::trow();
        row << (a::tdC() << text(hlpext_esc(r.value(QStringLiteral("sector")))));
        const QJsonValue n = r.value(QStringLiteral("n"));
        N cn = a::tdN();
        if (n.isNull() || n.isUndefined())
            cn << fmt::ND();
        else
            cn << text(hlpext_esc(n));
        row << cn;
        row << (a::tdN() << fmt::pc(hlpext_n(r.value(QStringLiteral("d1_pct")))));
        row << (a::tdN() << fmt::pc(hlpext_n(r.value(QStringLiteral("d5_pct")))));
        tb << row;
    }
    root << tb;
    return root;
}

// =================================================================================================
// bidv — Điểm ngành + GHTD (nội bộ) (panels.js 254–278)
// =================================================================================================
NodeP render_bidv(RenderCtx& rc) {
    const QJsonObject s = rc.data.D.value(QStringLiteral("sectors")).toObject();
    const QJsonArray dc = s.value(QStringLiteral("diem_changes")).toArray();
    const QJsonArray gh = s.value(QStringLiteral("ghtd_alerts")).toArray();
    hlpext_stamp(rc, hlpext_or(s.value(QStringLiteral("data_asof"))));
    const Palette& P = pal();

    N root = div();
    root << (a::warn() << text(QStringLiteral("⚠ Dữ liệu nội bộ BIDV (dư nợ, GHTD). Chỉ xem trên máy này. "
                                              "Không trích ra ngoài — Điều 9 QC 1128.")));

    // `<td style="white-space:normal;max-width:190px">${esc(r.nganh)}</td>`
    const auto nganhTd = [](const QJsonObject& r) -> NodeP {
        N c = a::tdC();
        c.normalWrap().maxW(190) << text(hlpext_esc(r.value(QStringLiteral("nganh"))));
        return c;
    };

    root << a::lbl(QStringLiteral("Đổi bậc (%1)").arg(dc.size()));
    N t1 = a::tbl();
    t1 << a::thead({a::thC(QStringLiteral("Ngành")), a::thC(QStringLiteral("Từ → Đến")),
                    a::thC(QStringLiteral("Dư nợ (tỷ)"), true)});
    for (int i = 0; i < dc.size() && i < 14; ++i) {
        const QJsonObject r = dc.at(i).toObject();
        N c2 = a::tdC();
        c2 << a::monoS(hlpext_esc(r.value(QStringLiteral("tu"))) + QStringLiteral("→") +
                       hlpext_esc(r.value(QStringLiteral("den"))));
        N bac = div();
        bac.size(9.0f).c(P.ink3) << text(hlpext_esc(r.value(QStringLiteral("bac_tu"))) + QStringLiteral(" → "))
                                 << a::b(hlpext_esc(r.value(QStringLiteral("bac_den")))).c(P.amber);
        c2 << bac;
        t1 << (a::trow() << nganhTd(r) << c2 << (a::tdN() << fmt::price(hlpext_n(r.value(QStringLiteral("du_no_ty"))))));
    }
    if (dc.isEmpty())
        t1 << hlpext_ndRow(3, QStringLiteral("Không có thay đổi"));
    root << t1;

    N l2 = a::lbl(QStringLiteral("Vượt GHTD (%1)").arg(gh.size()));
    l2.mt(9.0f);
    root << l2;
    N t2 = a::tbl();
    t2 << a::thead({a::thC(QStringLiteral("Ngành")), a::thC(QStringLiteral("Sử dụng"), true),
                    a::thC(QStringLiteral("Dư nợ / GHTD"), true)});
    for (int i = 0; i < gh.size() && i < 10; ++i) {
        const QJsonObject r = gh.at(i).toObject();
        N use = span();
        use.c(P.down).key(QStringLiteral("down")) << fmt::n1(hlpext_n(r.value(QStringLiteral("su_dung_pct"))))
                                                  << text(QStringLiteral("%"));
        N c3 = a::tdN();
        c3 << fmt::price(hlpext_n(r.value(QStringLiteral("du_no_ty")))) << text(QStringLiteral(" / "))
           << fmt::price(hlpext_n(r.value(QStringLiteral("ghtd_ty"))));
        t2 << (a::trow() << nganhTd(r) << (a::tdN() << use) << c3);
    }
    if (gh.isEmpty())
        t2 << hlpext_ndRow(3, QStringLiteral("Không ngành nào vượt"));
    root << t2;
    return root;
}

// =================================================================================================
// flash — Ứng viên Flashnote (panels.js 339–353)
// =================================================================================================
NodeP render_flash(RenderCtx& rc) {
    const QJsonArray f = rc.data.D.value(QStringLiteral("flash")).toArray();
    const QJsonArray w = rc.data.D.value(QStringLiteral("weekly")).toArray();
    hlpext_stamp(rc, QStringLiteral("%1 flash · %2 tuần").arg(f.size()).arg(w.size()));

    N root = div();
    root << (a::warn() << text(QStringLiteral("DRAFT tự sinh. Chưa điền tác động/hàm ý thật thì validator sẽ "
                                              "chặn khi dựng .docx.")));
    for (const QJsonValue& xv : f) {
        const QJsonObject x = xv.toObject();
        QString ngay = hlpext_or(x.value(QStringLiteral("ngay_phat_sinh")));
        if (ngay.isEmpty())
            ngay = hlpext_or(x.value(QStringLiteral("ngay")));
        N it = a::item();
        it << (a::t() << text(hlpext_esc(x.value(QStringLiteral("tieu_de")))))
           << (a::m() << text(hlpext_or(x.value(QStringLiteral("loai"))) + QStringLiteral(" · ") + ngay));
        root << it; // followed by the .lbl → never :last-child
    }

    N lb = a::lbl(QStringLiteral("Ứng viên bản tuần"));
    lb.mt(9.0f);
    root << lb;
    const int nw = std::min<int>(int(w.size()), 8);
    for (int i = 0; i < nw; ++i) {
        N it = a::item();
        it << (a::t() << text(hlpext_esc(w.at(i).toObject().value(QStringLiteral("tieu_de")))));
        root << (i == nw - 1 ? a::lastItem(it) : it);
    }
    if (nw == 0)
        root << a::ndD(QStringLiteral("—"));
    return root;
}

// =================================================================================================
// reports — Thư viện báo cáo PDF (panels.js 356–378)
// =================================================================================================
NodeP render_reports(RenderCtx& rc) {
    const QJsonArray r = rc.data.D.value(QStringLiteral("reports")).toArray();
    hlpext_stamp(rc, QStringLiteral("%1 bản").arg(r.size()));

    // Filter text lives in the instance state; typing stores it and re-renders this body (the web
    // redraws only the tbody — same result, the QLineEdit survives the re-render).
    QVariantMap* st = rc.state;
    const QString q = st ? st->value(QStringLiteral("q")).toString() : QString();
    QLineEdit* le = rc.lineEdit ? rc.lineEdit(QStringLiteral("f")) : nullptr;
    if (le) {
        le->setPlaceholderText(QStringLiteral("Lọc tiêu đề / nguồn / loại…"));
        le->setAccessibleName(QStringLiteral("Lọc báo cáo"));
        if (le->text() != q)
            le->setText(q);
        if (!le->property("hlpext_wired").toBool()) {
            le->setProperty("hlpext_wired", true);
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
        root << a::filterInput(le);

    N tb = a::tbl();
    tb << a::thead({a::thC(QStringLiteral("Ngày")), a::thC(QStringLiteral("Loại")), a::thC(QStringLiteral("Nguồn")),
                    a::thC(QStringLiteral("Tiêu đề"))});

    // r.filter(x => !q || JSON.stringify(x).toLowerCase().includes(q)).slice(0, 90); key order of the
    // report objects as build_launchpad.py writes them
    static const QStringList kOrder = {QStringLiteral("title"), QStringLiteral("src"),    QStringLiteral("kind"),
                                       QStringLiteral("date"),  QStringLiteral("issuer"), QStringLiteral("path")};
    const QString ql = q.toLower();
    int shown = 0;
    for (const QJsonValue& xv : r) {
        if (shown >= 90)
            break;
        if (!ql.isEmpty() && !fmt::jsonStringify(xv, kOrder).toLower().contains(ql))
            continue;
        ++shown;
        const QJsonObject x = xv.toObject();
        N cDate = a::tdC();
        cDate.mono().size(10.0f) << text(hlpext_or(x.value(QStringLiteral("date"))));
        N cKind = a::tdC();
        cKind << a::tag(hlpext_or(x.value(QStringLiteral("kind"))), pal().violet);
        QString issuer = hlpext_or(x.value(QStringLiteral("issuer")));
        if (issuer.isEmpty())
            issuer = hlpext_or(x.value(QStringLiteral("src")));
        N cSrc = a::tdC();
        cSrc.size(10.0f) << text(issuer);
        N cTitle = a::tdC();
        cTitle.normalWrap() << text(hlpext_esc(x.value(QStringLiteral("title"))));
        tb << (a::trow() << cDate << cKind << cSrc << cTitle);
    }
    if (shown == 0)
        tb << hlpext_ndRow(4, QStringLiteral("Không khớp"));
    root << tb;
    return root;
}

// =================================================================================================
// prov — Nguồn & độ tươi (panels.js 381–402)
// =================================================================================================
NodeP render_prov(RenderCtx& rc) {
    const QJsonObject m = rc.data.D.value(QStringLiteral("meta")).toObject();
    const QJsonArray s = m.value(QStringLiteral("sources")).toArray();
    hlpext_stamp(rc, hlpext_or(m.value(QStringLiteral("built"))));
    const qint64 now = rc.now.toMSecsSinceEpoch();
    const Palette& P = pal();

    N tb = a::tbl();
    tb << a::thead({a::thC(QStringLiteral("Nguồn")), a::thC(QStringLiteral("Tệp")),
                    a::thC(QStringLiteral("Cập nhật"), true), a::thC(QStringLiteral("MB"), true)});
    for (const QJsonValue& xv : s) {
        const QJsonObject x = xv.toObject();
        const QJsonValue mt = x.value(QStringLiteral("mtime"));
        // age = mtime ? (now − new Date(mtime.replace(' ', 'T'))) / 36e5 : null; NaN/null > 36 is false
        std::optional<double> age;
        if (hlpext_truthy(mt)) {
            QString iso = hlpext_esc(mt);
            const int sp = iso.indexOf(QLatin1Char(' '));
            if (sp >= 0)
                iso[sp] = QLatin1Char('T');
            if (const auto ms = fmt::parseMs(iso))
                age = double(now - *ms) / 36e5;
        }
        const QColor col = !hlpext_truthy(x.value(QStringLiteral("ok"))) ? P.down
                           : (age && *age > 36)                        ? P.amber
                                                                       : P.up;
        N c1 = a::tdC();
        c1 << span(QStringLiteral("●")).c(col) << text(QStringLiteral(" ") + hlpext_esc(x.value(QStringLiteral("key"))));
        N c2 = a::tdC();
        c2.size(9.5f).c(P.ink3).normalWrap() << text(hlpext_esc(x.value(QStringLiteral("file"))));
        N c3 = a::tdN();
        c3.size(10.0f) << text(hlpext_or(mt, QStringLiteral("LỖI")));
        N c4 = a::tdN();
        const QJsonValue mb = x.value(QStringLiteral("mb"));
        if (!(mb.isNull() || mb.isUndefined()))
            c4 << text(hlpext_esc(mb));
        tb << (a::trow() << c1 << c2 << c3 << c4);
    }

    N root = div();
    root << tb;
    N n1 = a::note();
    const QString note = hlpext_or(m.value(QStringLiteral("note")));
    if (!note.isEmpty())
        n1 << text(note);
    root << n1;
    N n2 = a::note();
    n2 << text(QStringLiteral("Build lại: ")) << a::code(QStringLiteral("python3 build_launchpad.py"))
       << text(QStringLiteral(" · tự chạy 3×/ngày qua LaunchAgent ")) << a::code(QStringLiteral("com.hoidongcovanai.launchpad"))
       << text(QStringLiteral("."));
    root << n2;
    return root;
}

} // namespace fincept::screens::hlp
