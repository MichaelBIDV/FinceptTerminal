// src/screens/hdcv_launchpad/HlpPanels_Vietcap.cpp
// HĐCV Launchpad — three components of panels.js, translated template for template:
//   vietcapma  (panels.js 446–489) VIETCAP IQ · <ctx> trong bảng — input.f + 8-column table (≤120 rows)
//              + note; data = fincept_bridge/data/vietcap_ma.json (Data::vcMa)
//   vietcaptin (panels.js 492–524) CBTT · lọc <ctx> — chips Tất cả / Mã <ctx>, ≤70 items + FACT-T1 note;
//              data = fincept_bridge/data/vietcap_tin.json (Data::vcTin)
//   xanhvo     (panels.js 527–554) ⚠ XANH VỎ ĐỎ LÒNG — cyan warn + one item per D.deep row
// The web fetches the two Vietcap files on every render, so a failed fetch shows the .catch `.nd`, and
// every re-render (a setCtx included) rebuilds the input / chips from scratch: the filter text and the
// chip key live in the panel instance state, and are reset when the linked ticker changes — exactly
// what the web does — while typing / a chip click / a data reload keep them.
#include "screens/hdcv_launchpad/HlpAtoms.h"
#include "screens/hdcv_launchpad/HlpFmt.h"
#include "screens/hdcv_launchpad/HlpPanels.h"

#include <QJsonArray>
#include <QJsonObject>
#include <QJsonValue>
#include <QLineEdit>
#include <QObject>
#include <QStringList>
#include <QVariant>

#include <algorithm>
#include <cmath>
#include <optional>
#include <utility>

namespace fincept::screens::hlp {

namespace {

namespace a = atoms;

/// JS truthiness of a JSON value (undefined/null/false/0/NaN/"" → false).
bool hlpvc_truthy(const QJsonValue& v) {
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

/// `${v}` in a template literal (raw interpolation, no `|| ''`): null → "null", missing → "undefined".
QString hlpvc_tpl(const QJsonValue& v) {
    if (v.isUndefined())
        return QStringLiteral("undefined");
    if (v.isNull())
        return QStringLiteral("null");
    if (v.isBool())
        return v.toBool() ? QStringLiteral("true") : QStringLiteral("false");
    if (v.isDouble())
        return fmt::jsString(v.toDouble());
    return fmt::str(v);
}

/// esc(v) — String(v ?? ''): null/missing → "", everything else as JS String().
QString hlpvc_esc(const QJsonValue& v) {
    return (v.isNull() || v.isUndefined()) ? QString() : hlpvc_tpl(v);
}

/// `${v || fallback}`
QString hlpvc_or(const QJsonValue& v, const QString& fallback) {
    return hlpvc_truthy(v) ? hlpvc_tpl(v) : fallback;
}

/// Keeps a per-instance state value and clears it when the linked ticker changed since the last render
/// (the web rebuilds the panel body on setCtx, so its <input> / chips start over).
QString hlpvc_state(RenderCtx& rc, const QString& key, const QString& fallback) {
    QVariantMap* st = rc.state;
    if (!st)
        return fallback;
    QString v = st->value(key).toString();
    if (st->contains(QStringLiteral("ctx")) && st->value(QStringLiteral("ctx")).toString() != rc.ctx) {
        v.clear();
        st->insert(key, QString());
    }
    st->insert(QStringLiteral("ctx"), rc.ctx);
    return v.isEmpty() ? fallback : v;
}

/// `.nd` div with mixed content (ndD() would default an empty text to "[CẦN DATA]").
NodeP hlpvc_ndCode(const QString& before, const QString& code) {
    N nd = div();
    nd.c(pal().ink3).italic().size(10).key("nd");
    nd << text(before);
    if (!code.isEmpty())
        nd << a::code(code);
    return nd;
}

/// vietcapma `pct`: v == null ? ND : `${v.toFixed(0)}%`
NodeP hlpvc_pct(std::optional<double> v) {
    if (!v)
        return fmt::ND();
    return text(fmt::toFixed(*v, 0) + u'%');
}

} // namespace

// =================================================================================================
// vietcapma — Vietcap IQ · room ngoại & sở hữu (panels.js 446–489)
// =================================================================================================
NodeP render_vietcapma(RenderCtx& rc) {
    const QString q = hlpvc_state(rc, QStringLiteral("q"), QString());
    N root = div();
    if (!rc.data.vcMaOk) {
        root << hlpvc_ndCode(QStringLiteral("Chưa có vietcap_ma.json — chạy "),
                             QStringLiteral("python3 fincept_bridge/vietcap_iq.py"));
        return root;
    }
    const QJsonObject& t = rc.data.vcMa;
    const QJsonArray rows = t.value(QStringLiteral("dong")).toArray();
    if (rc.asof)
        *rc.asof = QStringLiteral("%1 mã").arg(rows.size());

    // input.f — persistent QLineEdit; typing stores the text and re-renders this body only.
    QLineEdit* le = rc.lineEdit ? rc.lineEdit(QStringLiteral("f")) : nullptr;
    if (le) {
        le->setPlaceholderText(QStringLiteral("Lọc mã / ngành / rating…"));
        le->setAccessibleName(QStringLiteral("Lọc"));
        if (le->text() != q)
            le->setText(q);
        if (!le->property("hlpvc_wired").toBool()) {
            le->setProperty("hlpvc_wired", true);
            QVariantMap* st = rc.state;
            const auto rerender = rc.rerender;
            QObject::connect(le, &QLineEdit::textEdited, le, [st, rerender](const QString& s) {
                if (st)
                    st->insert(QStringLiteral("q"), s);
                if (rerender)
                    rerender();
            });
        }
        root << a::filterInput(le);
    }

    N tb = a::tbl();
    tb << a::thead({a::thC(QStringLiteral("Mã")), a::thC(QStringLiteral("Giá"), true),
                    a::thC(QStringLiteral("Giá MT"), true), a::thC(QStringLiteral("Upside"), true),
                    a::thC(QStringLiteral("Room"), true), a::thC(QStringLiteral("NN giữ"), true),
                    a::thC(QStringLiteral("Nhà nước"), true), a::thC(QStringLiteral("Rating"))});

    // draw(q): JSON.stringify(r).toLowerCase().includes(q) — in the key order vietcap_iq.py writes each
    // row (`{"ma":"msn` must match MSN; a query across two fields' boundary too)
    static const QStringList kOrder = {
        QStringLiteral("ma"),          QStringLiteral("gia"),        QStringLiteral("rating"),
        QStringLiteral("gia_MT"),      QStringLiteral("upside"),     QStringLiteral("room_ngoai"),
        QStringLiteral("NN_dang_giu"), QStringLiteral("nha_nuoc"),   QStringLiteral("nganh"),
        QStringLiteral("analyst"),     QStringLiteral("rating_ngay")};
    const QString ql = q.toLower();
    const auto setCtx = rc.setCtx;
    int shown = 0;
    for (const QJsonValue& rv : rows) {
        if (shown >= 120) // f.slice(0, 120)
            break;
        const QJsonObject r = rv.toObject();
        if (!ql.isEmpty() && !fmt::jsonStringify(r, kOrder).toLower().contains(ql))
            continue;
        ++shown;

        const QString ma = hlpvc_esc(r.value(QStringLiteral("ma")));
        const std::optional<double> room = fmt::num(r.value(QStringLiteral("room_ngoai")));
        const std::optional<double> nn = fmt::num(r.value(QStringLiteral("NN_dang_giu")));
        // Room đã đầy = khối ngoại giữ sát trần. room > 0 required: some tickers report
        // maximumForeignPercentage = 0 (missing data), which would flag them by mistake.
        const bool day = room && *room > 0 && nn && *room - *nn <= 1;

        N row = a::trow(ma == rc.ctx);
        row.click([setCtx, ma] {
            if (setCtx)
                setCtx(ma);
        });
        row << a::tdTk(ma);
        row << (a::tdN() << fmt::price(fmt::num(r.value(QStringLiteral("gia")))));
        row << (a::tdN() << fmt::price(fmt::num(r.value(QStringLiteral("gia_MT")))));
        row << (a::tdN() << fmt::pc(fmt::num(r.value(QStringLiteral("upside")))));
        row << (a::tdN() << hlpvc_pct(room));
        N nnTd = a::tdN();
        if (day)
            nnTd.c(pal().down).key("td.n.down");
        nnTd << hlpvc_pct(nn);
        if (day)
            nnTd << text(QStringLiteral(" ⚠"));
        row << nnTd;
        const QJsonValue nhaNuoc = r.value(QStringLiteral("nha_nuoc"));
        N nnTd2 = a::tdN();
        if (hlpvc_truthy(nhaNuoc))
            nnTd2 << hlpvc_pct(fmt::num(nhaNuoc));
        else
            nnTd2 << text(QStringLiteral("—"));
        row << nnTd2;
        N rating = a::tdC();
        rating.size(10) << text(hlpvc_esc(r.value(QStringLiteral("rating"))));
        row << rating;
        tb << row;
    }
    if (shown == 0) {
        N cell = a::tdC();
        cell.colspan(8).c(pal().ink3).italic().size(10).key("td.nd") << text(QStringLiteral("Không khớp"));
        tb << (a::trow() << cell);
    }
    root << tb;

    N nt = a::note();
    nt << text(hlpvc_or(t.value(QStringLiteral("ghi_chu")), QString()) + QStringLiteral(" Ô "))
       << a::down(QStringLiteral("đỏ"))
       << text(QStringLiteral(" ở cột NN giữ = room còn dưới 1 điểm phần trăm, tức "))
       << a::b(QStringLiteral("đã gần đầy"))
       << text(QStringLiteral(" — upside sell-side có đẹp thì dòng tiền ngoại cũng không vào thêm được."));
    root << nt;
    return root;
}

// =================================================================================================
// vietcaptin — Vietcap IQ · tin CBTT theo mã (panels.js 492–524)
// =================================================================================================
NodeP render_vietcaptin(RenderCtx& rc) {
    const QString k = hlpvc_state(rc, QStringLiteral("k"), QStringLiteral("all"));
    N root = div();
    if (!rc.data.vcTinOk) {
        root << a::ndD(QStringLiteral("Chưa có vietcap_tin.json"));
        return root;
    }
    const QJsonObject& t = rc.data.vcTin;
    const QJsonArray all = t.value(QStringLiteral("dong")).toArray();
    if (rc.asof)
        *rc.asof = QStringLiteral("%1 tin").arg(all.size());

    // .chips — Tất cả / Mã <ctx>; a click stores the key and re-renders this body.
    N chips = a::chips();
    QVariantMap* st = rc.state;
    const auto rerender = rc.rerender;
    const QVector<std::pair<QString, QString>> kinds = {
        {QStringLiteral("all"), QStringLiteral("Tất cả")},
        {QStringLiteral("ctx"), QStringLiteral("Mã %1").arg(rc.ctx)},
    };
    for (const auto& [key, label] : kinds) {
        chips << a::chip(label, key == k, [st, rerender, key = key]() {
            if (st)
                st->insert(QStringLiteral("k"), key);
            if (rerender)
                rerender();
        });
    }
    root << chips;

    // draw(k)
    QVector<QJsonObject> f;
    for (const QJsonValue& rv : all) {
        const QJsonObject r = rv.toObject();
        if (k == QLatin1String("ctx")) {
            const QJsonValue ma = r.value(QStringLiteral("ma"));
            if (!ma.isString() || ma.toString() != rc.ctx)
                continue;
        }
        f.push_back(r);
    }
    N box = div();
    const int count = std::min<int>(int(f.size()), 70);
    for (int i = 0; i < count; ++i) {
        const QJsonObject& r = f.at(i);
        N tt = a::t();
        tt << a::tk(hlpvc_esc(r.value(QStringLiteral("ma"))))
           << text(QStringLiteral(" ") + hlpvc_esc(r.value(QStringLiteral("tieu_de"))));
        N mm = a::m();
        mm << text(hlpvc_esc(r.value(QStringLiteral("luc"))) + QStringLiteral(" · ") +
                   hlpvc_esc(r.value(QStringLiteral("nguon"))));
        N it = a::item();
        it << tt << mm;
        box << (i == count - 1 ? a::lastItem(it) : it);
    }
    if (count == 0)
        box << a::ndD(QStringLiteral("Không có CBTT cho %1 trong kỳ quét.").arg(rc.ctx));
    root << box;

    N nt = a::note();
    nt << text(QStringLiteral("FACT-T1 — đây là CBTT gốc của doanh nghiệp, Vietcap chỉ là kênh dẫn lại nên không "
                              "nâng bậc. ") +
               hlpvc_or(t.value(QStringLiteral("bang")), QString()));
    root << nt;
    return root;
}

// =================================================================================================
// xanhvo — Xanh vỏ đỏ lòng · tuổi NỘI DUNG (panels.js 527–554), data = D.deep
// =================================================================================================
NodeP render_xanhvo(RenderCtx& rc) {
    const QJsonArray rows = rc.data.D.value(QStringLiteral("deep")).toArray();
    N root = div();
    if (rows.isEmpty()) {
        root << a::ndD(QStringLiteral("Chưa có kết quả deep_check."));
        return root;
    }
    int hong = 0;
    for (const QJsonValue& rv : rows)
        if (hlpvc_truthy(rv.toObject().value(QStringLiteral("hong"))))
            ++hong;
    if (rc.asof)
        *rc.asof = QStringLiteral("%1/%2 hỏng").arg(hong).arg(rows.size());

    const Palette& P = pal();
    N wc = a::warnCyan();
    wc << text(QStringLiteral("Panel ")) << a::b(QStringLiteral("Nguồn & độ tươi"))
       << text(QStringLiteral(" đo ")) << a::b(QStringLiteral("mtime tệp"))
       << text(QStringLiteral(" — hop-1. Panel này đo ")) << a::b(QStringLiteral("mốc thời gian trong ruột tệp"))
       << text(QStringLiteral(" — hop-2. Một tệp ghi lại mỗi ngày mà ruột đứng từ 2024 sẽ xanh ở hop-1 và đỏ ở "
                              "đây. Đó là loại lỗi đi thẳng vào báo cáo mà không có dấu hiệu bề mặt."));
    root << wc;

    for (int i = 0; i < rows.size(); ++i) {
        const QJsonObject r = rows.at(i).toObject();
        const bool bad = hlpvc_truthy(r.value(QStringLiteral("hong")));

        N tt = a::t();
        tt << (bad ? a::tag(QStringLiteral("HỎNG"), P.down) : a::tag(QStringLiteral("OK"), P.up))
           << text(QStringLiteral(" ")) << a::b(hlpvc_esc(r.value(QStringLiteral("ten"))));
        N mm = a::m();
        mm << text(hlpvc_esc(r.value(QStringLiteral("tep"))));

        N r1 = a::row();
        N v1 = a::v();
        v1 << text(hlpvc_or(r.value(QStringLiteral("moc_noi_dung")), QStringLiteral("—")));
        r1 << a::k(QStringLiteral("Mốc trong ruột")) << v1;

        N r2 = a::row();
        N v2 = a::v();
        v2.c(bad ? P.down : P.up).key(bad ? "v.down" : "v.up");
        const std::optional<double> tuoi = fmt::num(r.value(QStringLiteral("tuoi_ngay")));
        if (tuoi)
            v2 << text(fmt::toFixed(*tuoi, 0) + QStringLiteral(" ngày"));
        else
            v2 << fmt::ND();
        v2 << text(QStringLiteral(" "))
           << span(QStringLiteral("(ngưỡng %1)").arg(hlpvc_tpl(r.value(QStringLiteral("nguong_ngay"))))).c(P.ink3);
        r2 << a::k(QStringLiteral("Tuổi nội dung")) << v2;

        const QJsonValue hauQua = r.value(QStringLiteral("hau_qua"));
        const bool showHq = bad && hlpvc_truthy(hauQua);

        N it = a::item();
        it << tt << mm << r1 << (showHq ? r2 : a::lastRow(r2));
        if (showHq) {
            N hq = div();
            hq.size(10).c(P.down).lhf(1.45f).mt(3) << text(QStringLiteral("↳ ") + hlpvc_esc(hauQua));
            it << hq;
        }
        root << (i == rows.size() - 1 ? a::lastItem(it) : it);
    }
    return root;
}

} // namespace fincept::screens::hlp
