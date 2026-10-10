// src/screens/hdcv_launchpad/HlpPanels_Vimo.cpp
// HĐCV LAUNCHPAD — the four "vĩ mô" panels of panels.js, translated 1:1 (template, inline styles,
// status colours, stamp(), error branches):
//   render_dongho   — PANELS.dongho   (panels.js 648–685)  data/vimo.json + D.cong
//   render_chinhphu — PANELS.chinhphu (panels.js 688–728)  data/vimo.json
//   render_fftma    — PANELS.fftma    (panels.js 731–776)  data/vimo.json
//   render_cpicanh  — PANELS.cpicanh  (panels.js 405–443)  data/tien.json
// The web fetches the JSON at render time and shows "Đang tải…" for a moment; here the DataStore has
// already parsed the file, so the body is built directly. A missing/unparsable file takes the web's
// `.catch` branch ("Chưa có data/… — chạy <code>python3 build_….py</code>").
// Template whitespace follows HTML collapsing: a newline between two inline elements is one space.

#include "screens/hdcv_launchpad/HlpAtoms.h"
#include "screens/hdcv_launchpad/HlpFmt.h"
#include "screens/hdcv_launchpad/HlpPanels.h"
#include "screens/hdcv_launchpad/HlpTheme.h"

#include <QJsonArray>
#include <QJsonObject>
#include <QJsonValue>

#include <cmath>
#include <optional>

namespace fincept::screens::hlp {

namespace {

// ---- JS value semantics for JSON fields (file-local, prefixed for the unity build) ----

/// `${v}` inside a template literal: String(v) — "undefined"/"null" included, numbers like JS.
QString hlpvimo_tpl(const QJsonValue& v) {
    switch (v.type()) {
    case QJsonValue::Undefined: return QStringLiteral("undefined");
    case QJsonValue::Null: return QStringLiteral("null");
    case QJsonValue::Bool: return v.toBool() ? QStringLiteral("true") : QStringLiteral("false");
    case QJsonValue::Double: return fmt::jsString(v.toDouble());
    case QJsonValue::String: return v.toString();
    case QJsonValue::Array: {
        QStringList parts;
        for (const QJsonValue& e : v.toArray())
            parts << ((e.isNull() || e.isUndefined()) ? QString() : hlpvimo_tpl(e));
        return parts.join(QLatin1Char(','));
    }
    case QJsonValue::Object: return QStringLiteral("[object Object]");
    }
    return QString();
}

/// panels.js `esc(s)` = String(s ?? '') (escaping is irrelevant: text nodes are never parsed).
QString hlpvimo_esc(const QJsonValue& v) {
    if (v.isNull() || v.isUndefined())
        return QString();
    return hlpvimo_tpl(v);
}

/// JS truthiness of a JSON value.
bool hlpvimo_truthy(const QJsonValue& v) {
    switch (v.type()) {
    case QJsonValue::Undefined:
    case QJsonValue::Null: return false;
    case QJsonValue::Bool: return v.toBool();
    case QJsonValue::Double: {
        const double d = v.toDouble();
        return d != 0.0 && !std::isnan(d);
    }
    case QJsonValue::String: return !v.toString().isEmpty();
    case QJsonValue::Array:
    case QJsonValue::Object: return true;
    }
    return false;
}

/// `esc(v || def)`.
QString hlpvimo_or(const QJsonValue& v, const QString& def) {
    return hlpvimo_truthy(v) ? hlpvimo_tpl(v) : def;
}

/// Argument of n1()/n2(): `v == null ? ND : (+v)`.
std::optional<double> hlpvimo_numArg(const QJsonValue& v) {
    if (v.isNull() || v.isUndefined())
        return std::nullopt;
    if (v.isBool())
        return v.toBool() ? 1.0 : 0.0;
    if (v.isDouble())
        return v.toDouble();
    return fmt::plus(v);
}

/// `x != null && x > 2` for a JSON value (numbers, or numeric strings coerced like JS).
bool hlpvimo_gt(const QJsonValue& v, double limit) {
    if (v.isNull() || v.isUndefined())
        return false;
    const std::optional<double> d = hlpvimo_numArg(v);
    return d.has_value() && *d > limit;
}

/// `/re/.test(s)` where s may be undefined (JS stringifies it).
bool hlpvimo_test(const QJsonValue& v, const QString& needle) {
    return hlpvimo_tpl(v).contains(needle);
}

/// Append a text leaf only when it is non-empty (an empty HTML text node creates no line box).
N& hlpvimo_add(N& n, const QString& s) {
    if (!s.isEmpty())
        n << text(s);
    return n;
}

void hlpvimo_stamp(RenderCtx& rc, const QString& s) {
    if (rc.asof)
        *rc.asof = s;
}

/// `<div style="font-size:10px;color:var(--ink-3);line-height:1.45;margin-top:3px">…</div>`
N hlpvimo_sub3(const QString& s) {
    N d = div().size(10).c(pal().ink3).lhf(1.45).mt(3);
    hlpvimo_add(d, s);
    return d;
}

/// The `.catch` branch: `<div class="nd">Chưa có data/<file> — chạy <code>python3 <script></code></div>`.
NodeP hlpvimo_missing(const QString& file, const QString& script) {
    N root = div();
    root << (div().c(pal().ink3).italic().size(10)
             << text(QStringLiteral("Chưa có data/%1 — chạy ").arg(file))
             << atoms::code(QStringLiteral("python3 %1").arg(script)));
    return root;
}

NodeP hlpvimo_missingVimo() {
    return hlpvimo_missing(QStringLiteral("vimo.json"), QStringLiteral("build_vimo.py"));
}

/// `<div class="warn">…</div>` as the whole body (panel without artifact).
NodeP hlpvimo_warnOnly(const QString& s) {
    N root = div();
    N w = atoms::warn();
    hlpvimo_add(w, s);
    root << w;
    return root;
}

/// A `<td class="mono">` (mono family + tabular-nums).
N hlpvimo_tdMono() {
    return atoms::tdC().mono().tabnum();
}

} // namespace

// =================================================================================================
// dongho — CỔNG TIỀN · BA CHIẾC ĐỒNG HỒ (panels.js 648–685)
// =================================================================================================
NodeP render_dongho(RenderCtx& rc) {
    if (!rc.data.vimoOk)
        return hlpvimo_missingVimo();

    const QJsonObject& v = rc.data.vimo;
    const QJsonObject g = v.value(QStringLiteral("cong")).toObject();
    const QJsonArray dh = hlpvimo_truthy(v.value(QStringLiteral("dong_ho")))
                              ? v.value(QStringLiteral("dong_ho")).toArray()
                              : QJsonArray();
    const QJsonObject reg = rc.data.D.value(QStringLiteral("cong")).toObject();
    hlpvimo_stamp(rc, hlpvimo_or(v.value(QStringLiteral("cap_nhat")), QString()));

    const Palette& P = pal();
    const QJsonValue chuKy = g.value(QStringLiteral("chu_ky_tien"));
    const QString chuKyS = hlpvimo_tpl(chuKy);
    // mau(t): 'ĐẮT' → down · 'RẺ' → up · else amber (strict equality)
    const QColor mau = (chuKy.isString() && chuKyS == QStringLiteral("ĐẮT"))  ? P.down
                       : (chuKy.isString() && chuKyS == QStringLiteral("RẺ")) ? P.up
                                                                              : P.amber;
    // tt(s): ĐÃ CHUÔNG → up · GẦN ĐỦ → amber · CẦN DATA → ink3 · else down
    auto tt = [&P](const QJsonValue& s) -> QColor {
        if (hlpvimo_test(s, QStringLiteral("ĐÃ CHUÔNG")))
            return P.up;
        if (hlpvimo_test(s, QStringLiteral("GẦN ĐỦ")))
            return P.amber;
        if (hlpvimo_test(s, QStringLiteral("CẦN DATA")))
            return P.ink3;
        return P.down;
    };
    int reo = 0;
    for (const QJsonValue& d : dh)
        if (hlpvimo_test(d.toObject().value(QStringLiteral("trang_thai")), QStringLiteral("ĐÃ CHUÔNG")))
            ++reo;

    N root = div();

    // <div class="lbl">CỔNG · chu kỳ tiền <span class="mono" style="color:var(--ink-3)">N ngày tuổi</span></div>
    const QJsonValue tuoi = g.value(QStringLiteral("tuoi_ngay"));
    const QString tuoiS = (tuoi.isNull() || tuoi.isUndefined())
                              ? QString()
                              : hlpvimo_tpl(tuoi) + QStringLiteral(" ngày tuổi");
    {
        N l = atoms::lbl();
        if (tuoiS.isEmpty()) {
            l << text(QStringLiteral("CỔNG · chu kỳ tiền"));
        } else {
            l << text(QStringLiteral("CỔNG · chu kỳ tiền ")) << atoms::monoS(tuoiS).c(P.ink3);
        }
        root << l;
    }

    // <div class="big" style="color:…">chu_ky_tien || [CẦN DATA]</div>
    root << atoms::big(hlpvimo_or(chuKy, QStringLiteral("[CẦN DATA]"))).c(mau);

    // <div style="font-size:10px;color:var(--ink-2);line-height:1.45">bang_chung</div>
    {
        N d = div().size(10).c(P.ink2).lhf(1.45);
        hlpvimo_add(d, hlpvimo_esc(g.value(QStringLiteral("bang_chung"))));
        root << d;
    }

    // <div class="row" style="margin-top:6px">Đối chiếu market_regime | state · score n1</div>
    root << (atoms::row().mt(6)
             << atoms::k(QStringLiteral("Đối chiếu market_regime"))
             << (atoms::v()
                 << text(hlpvimo_or(reg.value(QStringLiteral("state")), QStringLiteral("—")) +
                         QStringLiteral(" · score "))
                 << fmt::n1(hlpvimo_numArg(reg.value(QStringLiteral("regime_score"))))));

    // <div class="lbl" style="margin-top:10px">Ba chiếc đồng hồ — reo/3 đã chuông</div>
    root << atoms::lbl(QStringLiteral("Ba chiếc đồng hồ — %1/3 đã chuông").arg(reo)).mt(10);

    for (const QJsonValue& dv : dh) {
        const QJsonObject d = dv.toObject();
        const QJsonValue st = d.value(QStringLiteral("trang_thai"));
        N t = atoms::t();
        t << atoms::tag(hlpvimo_esc(st), tt(st)) << text(QStringLiteral(" "))
          << atoms::b(hlpvimo_esc(d.value(QStringLiteral("ten"))));
        const QJsonValue so = d.value(QStringLiteral("so"));
        if (hlpvimo_truthy(so))
            t << text(QStringLiteral(" · ")) << atoms::monoS(hlpvimo_esc(so));
        N mm = atoms::m();
        hlpvimo_add(mm, hlpvimo_esc(d.value(QStringLiteral("nguon"))));
        root << (atoms::item() << t << hlpvimo_sub3(hlpvimo_esc(d.value(QStringLiteral("dien_giai")))) << mm);
    }

    root << (atoms::note() << text(
                 QStringLiteral("Nguồn CỔNG là ") + hlpvimo_esc(g.value(QStringLiteral("nguon"))) +
                 QStringLiteral(", kỳ ") + hlpvimo_or(g.value(QStringLiteral("ky")), QString()).left(60) +
                 QStringLiteral(". Hai đồng hồ chuông KHÔNG bằng ba — đồng hồ Thời gian chưa có bộ đo, "
                                "nên chưa kết luận đáy. Quality Investing xếp SAU câu hỏi "
                                "“chủ thể có đang cần thị trường không”.")));
    return root;
}

// =================================================================================================
// chinhphu — CHÍNH PHỦ · KPI VĨ MÔ (panels.js 688–728)
// =================================================================================================
NodeP render_chinhphu(RenderCtx& rc) {
    if (!rc.data.vimoOk)
        return hlpvimo_missingVimo();

    const QJsonObject c = rc.data.vimo.value(QStringLiteral("chinhphu")).toObject();
    if (!hlpvimo_truthy(c.value(QStringLiteral("co"))))
        return hlpvimo_warnOnly(hlpvimo_or(c.value(QStringLiteral("ly_do")), QStringLiteral("không có artifact")));

    const QString ngay = hlpvimo_or(c.value(QStringLiteral("ngay")), QString());
    const QJsonValue tuoi = c.value(QStringLiteral("tuoi_ngay"));
    hlpvimo_stamp(rc, ngay + QStringLiteral(" · ") + hlpvimo_tpl(tuoi) + QStringLiteral(" ngày"));

    const Palette& P = pal();
    // nh(n): FACT-T1 up · FACT-T2 cyan · NEWS ink2 · else amber
    auto nh = [&P](const QJsonValue& n) -> QColor {
        const QString s = n.isString() ? n.toString() : QString();
        if (n.isString() && s == QStringLiteral("FACT-T1"))
            return P.up;
        if (n.isString() && s == QStringLiteral("FACT-T2"))
            return P.cyan;
        if (n.isString() && s == QStringLiteral("NEWS"))
            return P.ink2;
        return P.amber;
    };
    const bool cu = hlpvimo_gt(tuoi, 2.0);

    N root = div();
    if (cu) {
        root << (atoms::warn()
                 << text(QStringLiteral("Artifact ") + ngay + QStringLiteral(" — đã ") + hlpvimo_tpl(tuoi) +
                         QStringLiteral(" ngày. Số trong bảng là ảnh chụp ngày đó, KHÔNG phải số hôm nay.")));
    }

    N tb = atoms::tbl();
    tb << atoms::thead({atoms::thC(QStringLiteral("Chỉ tiêu")), atoms::thC(QStringLiteral("Giá trị")),
                        atoms::thC(QStringLiteral("Nhãn")), atoms::thC(QStringLiteral("Ghi chú"))});
    for (const QJsonValue& kv : c.value(QStringLiteral("kpi")).toArray()) {
        const QJsonObject k = kv.toObject();
        N c1 = atoms::tdC();
        hlpvimo_add(c1, hlpvimo_esc(k.value(QStringLiteral("chi_tieu"))));
        N c2 = hlpvimo_tdMono();
        c2 << atoms::b(hlpvimo_esc(k.value(QStringLiteral("gia_tri"))));
        const QJsonValue nhan = k.value(QStringLiteral("nhan"));
        N sp = span().c(nh(nhan)).size(9.5f);
        hlpvimo_add(sp, hlpvimo_esc(nhan));
        N c3 = atoms::tdC();
        c3 << sp;
        N c4 = atoms::tdC().size(9.5f).c(P.ink3).normalWrap();
        hlpvimo_add(c4, hlpvimo_esc(k.value(QStringLiteral("ghi_chu"))));
        tb << (atoms::trow() << c1 << c2 << c3 << c4);
    }
    root << tb;

    root << atoms::lbl(QStringLiteral("Các mục trong bản ") + ngay).mt(9);
    for (const QJsonValue& m : c.value(QStringLiteral("muc")).toArray()) {
        N t = atoms::t();
        hlpvimo_add(t, hlpvimo_esc(m));
        root << (atoms::item() << t);
    }
    {
        N w = atoms::warn().mt(9);
        hlpvimo_add(w, hlpvimo_or(c.value(QStringLiteral("canh_bao_pipeline")), QString()));
        root << w;
    }

    root << (atoms::note()
             << text(QStringLiteral("Toàn bộ bảng lấy nguyên văn từ "))
             << atoms::code(hlpvimo_or(c.value(QStringLiteral("tep")), QString()))
             << text(QStringLiteral(", ") + hlpvimo_tpl(c.value(QStringLiteral("so_kpi"))) +
                     QStringLiteral(" dòng KPI. Nhãn giữ đúng như artifact ghi; dòng nào artifact "
                                    "không gắn nhãn thì hiện [CẦN NHÃN], không tự suy. "))
             << atoms::b(QStringLiteral("Đối chiếu CPI:"))
             << text(QStringLiteral(" dòng “CPI T8 ~+4,89% YoY” ở đây mang nhãn FACT-T1 "
                                    "nhưng artifact KHÔNG phải nguồn phát hành gốc — Cục Thống kê mới là. "
                                    "Chuỗi "))
             << atoms::code(QStringLiteral("wc-cpicom"))
             << text(QStringLiteral(" đang nuôi lãi suất thực Fisher cho số khác "
                                    "(xem panel ⚠ CPI · TRỘN ĐỊNH NGHĨA ở view TIỀN) và tiền tố “~” "
                                    "cho thấy chính artifact cũng coi đây là số xấp xỉ. Chưa hoà giải được "
                                    "hai con số — đừng dùng cái nào cho quyết định trước khi tra Cục Thống kê.")));
    return root;
}

// =================================================================================================
// fftma — FFT · PILLAR V (panels.js 731–776)
// =================================================================================================
NodeP render_fftma(RenderCtx& rc) {
    if (!rc.data.vimoOk)
        return hlpvimo_missingVimo();

    const QJsonObject f = rc.data.vimo.value(QStringLiteral("fft")).toObject();
    if (!hlpvimo_truthy(f.value(QStringLiteral("co"))))
        return hlpvimo_warnOnly(hlpvimo_or(f.value(QStringLiteral("ly_do")), QStringLiteral("không có RAWTEXT FFT")));

    const QString ngay = hlpvimo_or(f.value(QStringLiteral("ngay")), QString());
    hlpvimo_stamp(rc, ngay + QStringLiteral(" · ") + hlpvimo_tpl(f.value(QStringLiteral("tuoi_ngay"))) +
                          QStringLiteral(" ngày"));

    const Palette& P = pal();
    auto fv = [&f](const char* key) { return f.value(QLatin1String(key)); };

    // <div class="tile"><div class="lbl">…</div><div class="mono" style="font-size:15px">…</div>
    //   <div style="font-size:9.5px;color:var(--ink-3)">…</div></div>
    auto tileOf = [&P, &fv](const QString& name, const char* val, const char* ghi) {
        N sub = div().size(9.5f).c(P.ink3);
        hlpvimo_add(sub, hlpvimo_esc(fv(ghi)));
        return atoms::tile() << atoms::lbl(name) << atoms::monoD(hlpvimo_or(fv(val), QStringLiteral("—"))).size(15)
                             << sub;
    };

    N root = div();
    root << (atoms::tiles() << tileOf(QStringLiteral("VN100 · TB 4 tuần"), "vn100_4tuan", "vn100_vi_tri")
                            << tileOf(QStringLiteral("VN30 · TB 4 tuần"), "vn30_4tuan", "vn30_vi_tri")
                            << tileOf(QStringLiteral("Cạn cung ≤P20"), "can_cung", "can_cung_ghi")
                            << tileOf(QStringLiteral("Phân phối ≥P75"), "phan_phoi", "phan_phoi_ghi"));

    // .row: k | v = "<value> <span style="color:var(--ink-3);font-size:9.5px">ghi</span>"
    auto rowOf = [&P, &fv](const QString& label, const char* val, const char* ghi) {
        N sub = span().c(P.ink3).size(9.5f);
        hlpvimo_add(sub, hlpvimo_esc(fv(ghi)));
        return atoms::row() << atoms::k(label)
                            << (atoms::v() << text(hlpvimo_or(fv(val), QStringLiteral("—")) + QStringLiteral(" "))
                                           << sub);
    };
    root << rowOf(QStringLiteral("Cổ đông bùng nổ ≥+50% từ đáy 2N"), "bung_no", "bung_no_ghi").mt(8);
    root << rowOf(QStringLiteral("Cổ đông đặc lại ở đáy 2N"), "dac_lai", "dac_lai_ghi");

    root << atoms::lbl(QStringLiteral("FFT thấp nhất rổ (") + hlpvimo_tpl(fv("so_ma")) +
                       QStringLiteral(" mã đọc được)"))
                .mt(9);

    N tb = atoms::tbl();
    tb << atoms::thead({atoms::thC(QStringLiteral("Mã")), atoms::thC(QStringLiteral("FFT %/tuần")),
                        atoms::thC(QStringLiteral("Giá ") + ngay.mid(5)), atoms::thC(QStringLiteral("1 năm"))});
    const QJsonArray thap =
        hlpvimo_truthy(fv("ma_fft_thap")) ? fv("ma_fft_thap").toArray() : QJsonArray();
    for (const QJsonValue& mv : thap) {
        const QJsonObject m = mv.toObject();
        N c1 = hlpvimo_tdMono();
        c1 << atoms::b(hlpvimo_esc(m.value(QStringLiteral("ma"))));
        N c2 = hlpvimo_tdMono();
        c2 << text(hlpvimo_tpl(m.value(QStringLiteral("fft_pct"))) + QStringLiteral("%"));
        N c3 = hlpvimo_tdMono();
        hlpvimo_add(c3, hlpvimo_esc(m.value(QStringLiteral("gia_10_09"))));
        N c4 = atoms::tdC();
        c4 << fmt::ND();
        tb << (atoms::trow() << c1 << c2 << c3 << c4);
    }
    root << tb;

    root << (atoms::note()
             << text(QStringLiteral(
                    "FFT thấp = thanh khoản trên free float đã cạn, KHÔNG tự nó là tín hiệu mua. "
                    "Proxy này đã bỏ sót FPT, VCB, MBB, HPG, CTG — bốn trong năm mã đó là 29% NAV, "
                    "nên đừng kết luận “không có phân phối” chỉ vì FFT không bùng. "
                    "Cột 1 năm bị cắt trong RAWTEXT của PDF nên để [CẦN DATA], không nội suy. "
                    "Giá trong bảng là giá chốt phiên artifact, không phải giá hôm nay.")));
    return root;
}

// =================================================================================================
// cpicanh — ⚠ CPI · TRỘN ĐỊNH NGHĨA (panels.js 405–443)
// =================================================================================================
NodeP render_cpicanh(RenderCtx& rc) {
    if (!rc.data.tienOk)
        return hlpvimo_missing(QStringLiteral("tien.json"), QStringLiteral("build_tien.py"));

    const QJsonObject& t = rc.data.tien;
    const QJsonObject n = t.value(QStringLiteral("nguon_chuoi")).toObject();
    hlpvimo_stamp(rc, hlpvimo_or(t.value(QStringLiteral("cap_nhat")), QString()));

    const Palette& P = pal();
    // col(m): 'NGHIÊM TRỌNG' → down · else amber
    auto col = [&P](const QJsonValue& m) {
        return (m.isString() && m.toString() == QStringLiteral("NGHIÊM TRỌNG")) ? P.down : P.amber;
    };

    N root = div();
    const QJsonArray canhBao = hlpvimo_truthy(t.value(QStringLiteral("canh_bao")))
                                   ? t.value(QStringLiteral("canh_bao")).toArray()
                                   : QJsonArray();
    for (const QJsonValue& cv : canhBao) {
        const QJsonObject c = cv.toObject();
        const QJsonValue muc = c.value(QStringLiteral("muc"));
        N tt = atoms::t();
        tt << atoms::tag(hlpvimo_esc(muc), col(muc)) << text(QStringLiteral(" "))
           << atoms::b(hlpvimo_esc(c.value(QStringLiteral("viec"))));
        root << (atoms::item() << tt
                               << hlpvimo_sub3(QStringLiteral("↳ ") +
                                               hlpvimo_esc(c.value(QStringLiteral("bang_chung")))));
    }

    root << atoms::lbl(QStringLiteral("Chuỗi đang dùng")).mt(9);
    {
        N vv = atoms::v();
        hlpvimo_add(vv, hlpvimo_or(n.value(QStringLiteral("ten")), QString()));
        root << (atoms::row() << atoms::k(QStringLiteral("Tên")) << vv);
    }
    root << (atoms::row() << atoms::k(QStringLiteral("Đơn vị · freq"))
                          << (atoms::v()
                              << text(hlpvimo_or(n.value(QStringLiteral("don_vi")), QString()) + QStringLiteral(" · "))
                              << atoms::down(hlpvimo_or(n.value(QStringLiteral("freq")), QString()))));
    root << (atoms::row() << atoms::k(QStringLiteral("Điểm · mới nhất"))
                          << (atoms::v()
                              << text(hlpvimo_tpl(n.value(QStringLiteral("so_diem"))) + QStringLiteral(" · ") +
                                      hlpvimo_or(n.value(QStringLiteral("moi_nhat")), QString()) +
                                      QStringLiteral(" = ") + hlpvimo_tpl(n.value(QStringLiteral("gia_tri_cuoi"))) +
                                      QStringLiteral("%"))));

    root << atoms::lbl(QStringLiteral("Dáng chuỗi theo năm — bằng chứng")).mt(9);
    N tb = atoms::tbl();
    tb << atoms::thead({atoms::thC(QStringLiteral("Năm")), atoms::thC(QStringLiteral("Dáng")),
                        atoms::thC(QStringLiteral("Chuỗi"))});
    const QJsonArray dang = hlpvimo_truthy(t.value(QStringLiteral("dang_theo_nam")))
                                ? t.value(QStringLiteral("dang_theo_nam")).toArray()
                                : QJsonArray();
    for (const QJsonValue& dv : dang) {
        const QJsonObject d = dv.toObject();
        const QJsonValue dg = d.value(QStringLiteral("dang"));
        const bool bad = hlpvimo_test(dg, QStringLiteral("ĐƠN ĐIỆU"));
        N c1 = hlpvimo_tdMono();
        c1 << text(hlpvimo_tpl(d.value(QStringLiteral("nam"))));
        N c2 = atoms::tdC();
        c2 << (bad ? atoms::down(hlpvimo_esc(dg)) : atoms::up(hlpvimo_esc(dg))).size(10);
        N c3 = hlpvimo_tdMono().size(9.5f).normalWrap();
        hlpvimo_add(c3, hlpvimo_esc(d.value(QStringLiteral("chuoi"))));
        tb << (atoms::trow() << c1 << c2 << c3);
    }
    root << tb;

    root << (atoms::note()
             << text(QStringLiteral("2023–2025 dao động đúng dáng YoY tháng; riêng 2026 tăng đơn điệu — "
                                    "dáng của một số bình quân luỹ kế. Excel gốc widata tách riêng "))
             << atoms::code(QStringLiteral("CPI_YoY")) << text(QStringLiteral(" và "))
             << atoms::code(QStringLiteral("CPI_YoY_AVE"))
             << text(QStringLiteral(", còn chuỗi này gộp một nhãn. "
                                    "Chưa sửa engine: luật của chủ máy cấm đụng weights/scoring.")));
    return root;
}

} // namespace fincept::screens::hlp
