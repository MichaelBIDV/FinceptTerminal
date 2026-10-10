// src/screens/hdcv_launchpad/HlpPanels_Misc.cpp
// HĐCV Launchpad — four "misc" components of panels.js, translated template for template:
//   news    (panels.js 281–315) TIN · THEO CHỦ ĐỀ   — 5 chips, ≤60 items, upstream-0 warning
//   rasoat  (panels.js 318–336) RÀ SOÁT HẰNG NGÀY   — 2 tiles + one item per finding
//   songuon (panels.js 557–617) SỔ NGUỒN             — cyan warn, 4 chips, 6-column table + ghi_chu rows
//   alerts  (panels.js 620–641) CẢNH BÁO             — reads alerts_state.json (missing → the .catch branch)
// Chip selection lives in the panel instance state ((*rc.state)["k"]) so a data reload or a ctx change
// keeps the chosen filter; clicking a chip stores the key and asks the shell to re-render this body.
// Whitespace between inline elements follows what the HTML templates collapse to (single spaces).
#include "screens/hdcv_launchpad/HlpAtoms.h"
#include "screens/hdcv_launchpad/HlpFmt.h"
#include "screens/hdcv_launchpad/HlpPanels.h"

#include <QJsonArray>
#include <QJsonObject>
#include <QJsonValue>
#include <QRegularExpression>
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
bool hlpmisc_truthy(const QJsonValue& v) {
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

/// JS String(v) for template interpolation (booleans included).
QString hlpmisc_string(const QJsonValue& v) {
    if (v.isBool())
        return v.toBool() ? QStringLiteral("true") : QStringLiteral("false");
    return fmt::str(v);
}

/// `${v ?? fallback}`
QString hlpmisc_nullish(const QJsonValue& v, const QString& fallback) {
    if (v.isNull() || v.isUndefined())
        return fallback;
    return hlpmisc_string(v);
}

/// `${v || fallback}`
QString hlpmisc_or(const QJsonValue& v, const QString& fallback) {
    return hlpmisc_truthy(v) ? hlpmisc_string(v) : fallback;
}

/// safeUrl(u): only http(s) passes, everything else becomes '#'.
QString hlpmisc_safe_url(const QJsonValue& v) {
    static const QRegularExpression re(QStringLiteral("^https?://"), QRegularExpression::CaseInsensitiveOption);
    const QString u = hlpmisc_or(v, QString());
    return re.match(u).hasMatch() ? u : QStringLiteral("#");
}

/// Current chip key of this panel instance (default = first chip).
QString hlpmisc_chip_key(RenderCtx& rc, const QString& fallback) {
    if (!rc.state)
        return fallback;
    const QString k = rc.state->value(QStringLiteral("k")).toString();
    return k.isEmpty() ? fallback : k;
}

/// `.chips` row: one `.chip` per [key,label]; pressed = current key. Click stores the key + re-renders.
NodeP hlpmisc_chips(RenderCtx& rc, const QVector<std::pair<QString, QString>>& kinds, const QString& cur) {
    N box = a::chips();
    QVariantMap* st = rc.state;
    std::function<void()> rerender = rc.rerender;
    for (const auto& [key, label] : kinds) {
        box << a::chip(label, key == cur, [st, rerender, key = key]() {
            if (st)
                st->insert(QStringLiteral("k"), key);
            if (rerender)
                rerender();
        });
    }
    return box;
}

} // namespace

// =================================================================================================
// news — Dòng tin theo chủ đề (panels.js 281–315)
// =================================================================================================
NodeP render_news(RenderCtx& rc) {
    const QJsonObject& D = rc.data.D;
    const QJsonArray all = D.value(QStringLiteral("news")).toArray();
    if (rc.asof)
        *rc.asof = QStringLiteral("%1 tin").arg(all.size());

    N root = div();

    // 5 market RSS feeds sometimes die together — say so instead of showing an empty frame.
    const QJsonObject up = D.value(QStringLiteral("news_upstream")).toObject();
    const QJsonValue total = up.value(QStringLiteral("items_total"));
    if (total.isDouble() && total.toDouble() == 0.0) {
        QString at = hlpmisc_or(up.value(QStringLiteral("collected_at")), QString()).left(16);
        const int ti = at.indexOf(QLatin1Char('T'));
        if (ti >= 0)
            at.replace(ti, 1, QLatin1Char(' '));
        N w = a::warn();
        w << text(QStringLiteral("⚠ Cả 5 feed RSS thị trường (CafeF, VnEconomy, Vietstock×3) trả "))
          << a::b(QStringLiteral("0 tin"))
          << text(QStringLiteral(" lúc %1. Mục \"Thị trường\" sẽ trống — đây là lỗi nguồn, không phải hết tin.")
                      .arg(at));
        root << w;
    }

    const QVector<std::pair<QString, QString>> kinds = {
        {QStringLiteral("all"), QStringLiteral("Tất cả")},
        {QStringLiteral("nganh"), QStringLiteral("Ngành")},
        {QStringLiteral("chinh_sach"), QStringLiteral("Chính sách")},
        {QStringLiteral("thi_truong"), QStringLiteral("Thị trường")},
        {QStringLiteral("ctx"), QStringLiteral("Mã %1").arg(rc.ctx)},
    };
    const QString k = hlpmisc_chip_key(rc, QStringLiteral("all"));
    root << hlpmisc_chips(rc, kinds, k);

    // draw(k)
    QVector<QJsonObject> f;
    // JS `new RegExp(`\\b${ctx}\\b`)` — ctx is not escaped on the web either; \b is ASCII-only in both.
    const QRegularExpression ctxRe(QStringLiteral("\\b%1\\b").arg(rc.ctx));
    for (const QJsonValue& nv : all) {
        const QJsonObject n = nv.toObject();
        if (k == QLatin1String("ctx")) {
            if (!ctxRe.isValid() || !ctxRe.match(hlpmisc_or(n.value(QStringLiteral("title")), QString())).hasMatch())
                continue;
        } else if (k != QLatin1String("all")) {
            const QJsonValue kind = n.value(QStringLiteral("kind"));
            if (!kind.isString() || kind.toString() != k)
                continue;
        }
        f.push_back(n);
    }

    N nl = div();
    const int count = std::min<int>(int(f.size()), 60);
    for (int i = 0; i < count; ++i) {
        const QJsonObject& n = f.at(i);
        QString meta = hlpmisc_or(n.value(QStringLiteral("date")), QString()) + QStringLiteral(" · ") +
                       hlpmisc_or(n.value(QStringLiteral("src")), QString());
        const QJsonArray tags = n.value(QStringLiteral("tags")).toArray();
        if (!tags.isEmpty()) {
            QStringList two;
            for (int j = 0; j < tags.size() && j < 2; ++j)
                two << fmt::str(tags.at(j));
            meta += QStringLiteral(" · ") + two.join(QStringLiteral(", "));
        }
        N it = a::item();
        it << a::tLink(fmt::str(n.value(QStringLiteral("title"))), hlpmisc_safe_url(n.value(QStringLiteral("url"))));
        N mm = a::m();
        mm << text(meta);
        it << mm;
        nl << (i == count - 1 ? a::lastItem(it) : it);
    }
    if (count == 0)
        nl << a::ndD(QStringLiteral("Không có tin khớp bộ lọc."));
    root << nl;
    return root;
}

// =================================================================================================
// rasoat — Rà soát hằng ngày (panels.js 318–336)
// =================================================================================================
NodeP render_rasoat(RenderCtx& rc) {
    const QJsonObject r = rc.data.D.value(QStringLiteral("rasoat")).toObject();
    const QJsonArray ph = r.value(QStringLiteral("phat_hien")).toArray();
    if (ph.isEmpty()) {
        N root = div();
        root << a::ndD(QStringLiteral("Chưa có bản rà soát."));
        return root;
    }
    if (rc.asof)
        *rc.asof = hlpmisc_or(r.value(QStringLiteral("ngay")), QString());

    N root = div();

    N tiles = a::tiles();
    tiles.mb(7);
    {
        N t1 = a::tile();
        N v1 = a::monoD(hlpmisc_nullish(r.value(QStringLiteral("tong")), QStringLiteral("—")));
        v1.size(15);
        t1 << a::lbl(QStringLiteral("Tổng")) << v1;
        N t2 = a::tile(true);
        N v2 = a::monoD(hlpmisc_nullish(r.value(QStringLiteral("nghiem_trong")), QStringLiteral("—")));
        v2.size(15).c(pal().down);
        t2 << a::lbl(QStringLiteral("Nghiêm trọng")) << v2;
        tiles << t1 << t2;
    }
    root << tiles;

    static const QRegularExpression severe(QStringLiteral("nghiêm|cao"), QRegularExpression::CaseInsensitiveOption);
    for (int i = 0; i < ph.size(); ++i) {
        const QJsonObject p = ph.at(i).toObject();
        const QString muc = fmt::str(p.value(QStringLiteral("muc")));
        const QColor col = severe.match(hlpmisc_or(p.value(QStringLiteral("muc")), QString())).hasMatch()
                               ? pal().down
                               : pal().amber;
        N tt = a::t();
        tt << a::tag(muc, col) << text(QStringLiteral(" ") + fmt::str(p.value(QStringLiteral("viec"))));

        QString meta = fmt::str(p.value(QStringLiteral("nhom")));
        const QJsonValue ct = p.value(QStringLiteral("chi_tiet"));
        if (hlpmisc_truthy(ct))
            meta += QStringLiteral(" · ") + hlpmisc_string(ct).left(90);
        N mm = a::m();
        mm << text(meta);

        N it = a::item();
        it << tt << mm;
        root << (i == ph.size() - 1 ? a::lastItem(it) : it);
    }
    return root;
}

// =================================================================================================
// songuon — Sổ nguồn · BERI và Chứng khoán (panels.js 557–617)
// =================================================================================================
NodeP render_songuon(RenderCtx& rc) {
    const QJsonObject s = rc.data.D.value(QStringLiteral("songuon")).toObject();
    const QJsonArray all = s.value(QStringLiteral("nguon")).toArray();
    if (all.isEmpty()) {
        N root = div();
        N w = a::warn();
        w << text(QStringLiteral("Chưa có songuon_registry.json"));
        root << w;
        return root;
    }
    if (rc.asof)
        *rc.asof = QStringLiteral("%1 nguồn · %2").arg(all.size()).arg(hlpmisc_or(s.value(QStringLiteral("cap_nhat")), QString()));

    const Palette& P = pal();
    // TT: trang_thai → [label, colour]
    auto status = [&P](const QString& tt) -> std::pair<QString, QColor> {
        if (tt == QLatin1String("song"))
            return {QStringLiteral("Đang chảy"), P.up};
        if (tt == QLatin1String("thu_cong"))
            return {QStringLiteral("Thủ công"), P.amber};
        if (tt == QLatin1String("chan"))
            return {QStringLiteral("Bị chặn"), P.down};
        if (tt == QLatin1String("chua_co"))
            return {QStringLiteral("Chưa có quyền"), P.ink3};
        // chập chờn: reachable but unstable — kept apart from 'song' so it is not counted as reliable.
        if (tt == QLatin1String("chap_chon"))
            return {QStringLiteral("Chập chờn"), P.amber};
        return {QStringLiteral("?"), P.ink3};
    };

    N root = div();

    N wc = a::warnCyan();
    wc << a::b(QStringLiteral("Kênh không nâng bậc."))
       << text(QStringLiteral(" Số của Cục Thống kê lấy qua Bloomberg vẫn là số Cục Thống kê và xếp bậc theo "
                              "Cục Thống kê. Hai nguồn cùng dẫn về một gốc chỉ tính là MỘT nguồn."))
       << brk()
       << text(QStringLiteral("BERI dùng thang T1–T4 (sell-side = T4) · Chứng khoán dùng FACT-T1 > FACT-T2 > "
                              "SS-T3 > EST. "))
       << a::b(QStringLiteral("Hai thang khác nhau — không trộn."));
    root << wc;

    const QVector<std::pair<QString, QString>> tabs = {
        {QStringLiteral("all"), QStringLiteral("Tất cả")},
        {QStringLiteral("beri"), QStringLiteral("BERI")},
        {QStringLiteral("ck"), QStringLiteral("Chứng khoán")},
        {QStringLiteral("van_de"), QStringLiteral("⚠ Có vấn đề")},
    };
    const QString k = hlpmisc_chip_key(rc, QStringLiteral("all"));
    root << hlpmisc_chips(rc, tabs, k);

    N tb = a::tbl();
    tb << a::thead({a::thC(QStringLiteral("Nguồn")), a::thC(QStringLiteral("Bậc")), a::thC(QStringLiteral("Cơ quan gốc")),
                    a::thC(QStringLiteral("Kênh")), a::thC(QStringLiteral("Độ tươi"), true),
                    a::thC(QStringLiteral("Trạng thái"))});

    static const QRegularExpression reT1(QStringLiteral("T1"));
    static const QRegularExpression reT4(QStringLiteral("T4|EST"));

    for (const QJsonValue& xv : all) {
        const QJsonObject x = xv.toObject();
        const QString tt = fmt::str(x.value(QStringLiteral("trang_thai")));
        const std::optional<double> gio = fmt::num(x.value(QStringLiteral("gio_tuoi")));
        if (k == QLatin1String("beri") || k == QLatin1String("ck")) {
            const QJsonValue he = x.value(QStringLiteral("he"));
            if (!he.isString() || he.toString() != k)
                continue;
        } else if (k == QLatin1String("van_de")) {
            const bool bad = x.value(QStringLiteral("trang_thai")) != QJsonValue(QStringLiteral("song")) ||
                             (gio && *gio > 40);
            if (!bad)
                continue;
        }

        const auto [lab, col] = status(tt);
        const bool stale = gio && *gio > 40;
        const QString ghiChu = hlpmisc_or(x.value(QStringLiteral("ghi_chu")), QString());

        N row = a::trow();
        if (!ghiChu.isEmpty())
            row.tip(ghiChu);

        // Nguồn: [NỘI BỘ] <b>ten</b> + nhom (9px ink3)
        N c1 = a::tdC();
        c1.normalWrap().maxW(210);
        if (hlpmisc_truthy(x.value(QStringLiteral("noi_bo"))))
            c1 << a::tag(QStringLiteral("NỘI BỘ"), P.down) << text(QStringLiteral(" "));
        c1 << a::b(fmt::str(x.value(QStringLiteral("ten"))));
        N nhom = div();
        nhom.size(9).c(P.ink3) << text(fmt::str(x.value(QStringLiteral("nhom"))));
        c1 << nhom;

        // Bậc: tag coloured by tier
        const QString tier = fmt::str(x.value(QStringLiteral("tier")));
        const QColor tierCol = reT1.match(tier).hasMatch() ? P.up : reT4.match(tier).hasMatch() ? P.amber : P.cyan;
        N c2 = a::tdC();
        c2 << a::tag(tier, tierCol);

        N c3 = a::tdC();
        c3.normalWrap().maxW(150).size(10).c(P.ink2) << text(fmt::str(x.value(QStringLiteral("nguon_goc"))));
        N c4 = a::tdC();
        c4.normalWrap().maxW(150).size(10).c(P.ink3) << text(fmt::str(x.value(QStringLiteral("kenh"))));

        // Độ tươi
        N c5 = a::tdN();
        if (stale)
            c5 << text(QStringLiteral("⚠ "));
        if (!gio)
            c5 << a::ndS(QStringLiteral("—"));
        else if (*gio > 48)
            c5 << a::down(fmt::toFixed(*gio / 24.0, 0) + QStringLiteral(" ngày"));
        else
            c5 << text(fmt::toFixed(*gio, 1) + QStringLiteral("h"));

        // Trạng thái
        N c6 = a::tdC();
        c6.size(10) << span(QStringLiteral("●")).c(col) << text(QStringLiteral(" ") + lab);

        row << c1 << c2 << c3 << c4 << c5 << c6;
        tb << row;

        if (!ghiChu.isEmpty()) {
            N gr = a::trow();
            N gc = a::tdC();
            gc.colspan(6).p(0, 5, 6, 5).bb(1, P.line);
            N sp = span(ghiChu);
            sp.size(10).c(P.ink3).normalWrap().display(Display::Block).lhf(1.45);
            gc << sp;
            gr << gc;
            tb << gr;
        }
    }

    N sg = div();
    sg << tb;
    root << sg;
    return root;
}

// =================================================================================================
// alerts — Cảnh báo đang bật (panels.js 620–641), data = launchpad/alerts_state.json
// =================================================================================================
NodeP render_alerts(RenderCtx& rc) {
    if (rc.asof)
        *rc.asof = QString();

    const QJsonObject& s = rc.data.alerts;
    const QJsonValue firedV = s.value(QStringLiteral("fired"));
    const bool firedBad = hlpmisc_truthy(firedV) && !firedV.isArray(); // `.map` would throw → .catch

    N root = div();
    if (!rc.data.alertsOk || firedBad) {
        // `.nd` div with mixed content (ndD() would default its text to "[CẦN DATA]").
        N nd = div();
        nd.c(pal().ink3).italic().size(10);
        nd << text(QStringLiteral("Chưa có alerts_state.json — chạy "))
           << a::code(QStringLiteral("python3 launchpad_alert.py"))
           << text(QStringLiteral(" một lần để khởi tạo."));
        root << nd;
        return root;
    }

    const QJsonArray f = firedV.toArray();

    auto kv = [](const QString& key, const QString& val) -> NodeP {
        N r = a::row();
        N vv = a::v();
        vv << text(val);
        r << a::k(key) << vv;
        return r;
    };
    root << kv(QStringLiteral("Lần quét gần nhất"), hlpmisc_or(s.value(QStringLiteral("checked_at")), QStringLiteral("—")))
         << kv(QStringLiteral("Luật đang bật"), hlpmisc_nullish(s.value(QStringLiteral("rules_on")), QStringLiteral("—")))
         << kv(QStringLiteral("Bắn lần này"), QString::number(f.size()));

    for (const QJsonValue& xv : f) {
        const QJsonObject x = xv.toObject();
        N tt = a::t();
        tt << text(fmt::str(x.value(QStringLiteral("msg"))));
        N mm = a::m();
        mm << text(fmt::str(x.value(QStringLiteral("rule"))) + QStringLiteral(" · ") +
                   hlpmisc_or(x.value(QStringLiteral("at")), QString()));
        N it = a::item();
        it << tt << mm;
        root << it;
    }
    if (f.isEmpty()) {
        N nd = a::ndD(QStringLiteral("Không có cảnh báo nào bắn ở lần quét gần nhất."));
        nd.mt(7);
        root << nd;
    }

    N nt = a::note();
    nt << text(QStringLiteral("Sửa luật tại ")) << a::code(QStringLiteral("launchpad/rules.json"))
       << text(QStringLiteral(". Telegram đi qua cổng tg_gate (1 tin/ngày/loại, chặn tin rỗng và trùng)."));
    root << nt;
    return root;
}

} // namespace fincept::screens::hlp
