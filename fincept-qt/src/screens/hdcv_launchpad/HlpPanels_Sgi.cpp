// src/screens/hdcv_launchpad/HlpPanels_Sgi.cpp
// HĐCV LAUNCHPAD — panel "SGI CAPITAL" (id `sgitin`). SPEC §8: the one panel that does NOT copy the
// web template. Per the owner's decision (27/09/2026) it reads the newest weekly issue of the Cowork
// routine "Trạm Quan Trắc Vĩ Mô — bản tuần" (knowledge_os/sgi_ky/<YYYY-MM-DD>.json, schema sgi_ky/1,
// the same file the SGI FA tab reads — loaded by DataStore into rc.data.sgi) instead of the web's
// Facebook-KOL feed. Only the Launchpad's existing vocabulary is used (warn, lbl, big, row, tiles/tile,
// item, tag, note); every string shown comes from the issue or is quoted from SPEC §8. A missing field
// shows [CẦN DATA] or its line is hidden — nothing is inferred.
//
// Composites (TIỀN / CHI PHÍ / GIÁ TRỊ / ĐỘ RỘNG / ĐẦU CƠ): an issue that PRINTS them (`to_hop`
// [{ten, gia_tri, bien, txt, mau, delta_txt}], issue 26/09 on) is shown verbatim — txt, delta_txt and the
// artifact's colour `mau` (ĐẦU CƠ −1 is vàng there, not đỏ). Older issues carry only block scores
// (khoi[].diem) + to_hop_truoc, so the composites are RECOMPUTED here exactly like scripts/sgi_fa.py
// composite(): sum(member block scores) × coefficient, clamped to ±bound; any member score missing →
// [CẦN DATA]; delta vs to_hop_truoc shown as ▲x / ▼x / —; colour by sign.
#include "screens/hdcv_launchpad/HlpAtoms.h"
#include "screens/hdcv_launchpad/HlpFmt.h"
#include "screens/hdcv_launchpad/HlpPanels.h"

#include <QDate>
#include <QFileInfo>
#include <QJsonArray>
#include <QJsonObject>
#include <QRegularExpression>

#include <algorithm>
#include <cmath>
#include <optional>

namespace fincept::screens::hlp {

namespace {

namespace a = atoms;

/// scripts/sgi_fa.py TO_HOP — composite definitions (SKILL §7 + the issue's block-8 extension),
/// in artifact order.
struct HlpsgiComposite {
    const char16_t* ten;
    int khoi[3];
    int nKhoi;
    double heSo;
    int bien;
};
constexpr HlpsgiComposite kHlpsgiToHop[] = {
    {u"TIỀN", {1, 2, 5}, 3, 2.0, 12},
    {u"CHI PHÍ", {3, 4, 0}, 2, 1.5, 6},
    {u"GIÁ TRỊ", {6, 0, 0}, 1, 1.5, 3},
    {u"ĐỘ RỘNG", {8, 0, 0}, 1, 1.5, 3},
    {u"ĐẦU CƠ", {7, 0, 0}, 1, 1.0, 2},
};

constexpr int kHlpsgiStaleDays = 8;      ///< SPEC §8.1: older than this → stale warning
constexpr int kHlpsgiEvidenceChars = 160; ///< SPEC §8.7: evidence line cut length

const QString kHlpsgiMinus = QStringLiteral("−");

/// sgi_fa.py fmt_vn(v, dec=2, sign): decimal comma, thousands dot, "−" (U+2212), "+" when asked,
/// trailing zeros trimmed; zero never signed.
QString hlpsgi_num(double v, bool withSign) {
    const QString body = fmt::vi(std::fabs(v), 2);
    if (v == 0.0 || body == QStringLiteral("0"))
        return body;
    if (v < 0)
        return kHlpsgiMinus + body;
    return withSign ? QStringLiteral("+") + body : body;
}

QColor hlpsgi_signColor(double v) {
    return v > 0 ? pal().up : (v < 0 ? pal().down : pal().flat);
}

QString hlpsgi_nfcUpper(const QString& s) {
    return s.normalized(QString::NormalizationForm_C).trimmed().toUpper();
}

/// "1/4" → 1 (sgi_fa bottom_conditions regex `\s*(\d+)\s*/\s*4`).
std::optional<int> hlpsgi_dayCount(const QString& ghi) {
    static const QRegularExpression re(QStringLiteral("^\\s*(\\d+)\\s*/\\s*4"));
    const auto m = re.match(ghi);
    if (!m.hasMatch())
        return std::nullopt;
    return m.captured(1).toInt();
}

/// Artifact colour word (sgi_fa.py norm_mau: accents and dot classes tolerated) → palette colour.
/// do/r → down · vang/a → amber · xanh/g → up · anything else (xam) → ink.
QColor hlpsgi_mauColor(const QString& mau) {
    QString s;
    for (const QChar ch : mau.trimmed().toLower().normalized(QString::NormalizationForm_D)) {
        if (ch.category() == QChar::Mark_NonSpacing)
            continue;
        s += ch == QChar(0x0111) ? QChar(u'd') : ch;
    }
    if (s == QStringLiteral("do") || s == QStringLiteral("r"))
        return pal().down;
    if (s == QStringLiteral("vang") || s == QStringLiteral("a"))
        return pal().amber;
    if (s == QStringLiteral("xanh") || s == QStringLiteral("g"))
        return pal().up;
    return pal().ink;
}

NodeP hlpsgi_textOrNd(const QString& s) {
    return s.isEmpty() ? fmt::ND() : text(s).node();
}

// ---- sections ------------------------------------------------------------------------------------

void hlpsgi_verdict(N& root, const QJsonObject& vd) {
    // 3. Chế độ
    const QString cheDo = fmt::str(vd.value(QStringLiteral("che_do")));
    const QString cheUp = hlpsgi_nfcUpper(cheDo);
    const QColor cheCol = cheUp.contains(QStringLiteral("SIẾT"))  ? pal().down
                          : cheUp.contains(QStringLiteral("NỚI")) ? pal().up
                                                                   : pal().amber;
    root << a::lbl(QStringLiteral("Chế độ"));
    root << a::big(cheDo.isEmpty() ? QStringLiteral("[CẦN DATA]") : cheDo).c(cheCol);
    const QString chot = fmt::str(vd.value(QStringLiteral("chot")));
    if (!chot.isEmpty())
        root << (div().size(11).c(pal().ink2).lhf(1.45) << text(chot));
    // The artifact prints verdict.ghi_chu right under the chot line (the cash-move sentence).
    const QString ghiChu = fmt::str(vd.value(QStringLiteral("ghi_chu")));
    if (!ghiChu.isEmpty())
        root << (div().size(10).c(pal().ink3).lhf(1.45) << text(ghiChu));

    // 4. Four rows
    const QJsonObject tm = vd.value(QStringLiteral("tien_mat")).toObject();
    const auto hienTai = fmt::num(tm.value(QStringLiteral("hien_tai")));
    const auto deXuat = fmt::num(tm.value(QStringLiteral("de_xuat")));
    N vCash = a::v();
    if (hienTai)
        vCash << text(hlpsgi_num(*hienTai, false) + QStringLiteral("%"));
    else
        vCash << fmt::ND();
    vCash << text(QStringLiteral(" → "));
    if (deXuat)
        vCash << text(hlpsgi_num(*deXuat, false) + QStringLiteral("%"));
    else
        vCash << fmt::ND();
    root << (a::row().mt(6) << a::k(QStringLiteral("Tiền mặt đề xuất")) << vCash);

    const auto coPhieu = fmt::num(vd.value(QStringLiteral("co_phieu")));
    const auto san = fmt::num(vd.value(QStringLiteral("san_co_phieu")));
    N vEq = a::v();
    if (coPhieu)
        vEq << text(hlpsgi_num(*coPhieu, false) + QStringLiteral("% NAV"));
    else
        vEq << fmt::ND();
    vEq << text(QStringLiteral(" · sàn "));
    if (san)
        vEq << text(hlpsgi_num(*san, false) + QStringLiteral("%"));
    else
        vEq << fmt::ND();
    root << (a::row() << a::k(QStringLiteral("Cổ phiếu / sàn")) << vEq);

    const QJsonObject hd = vd.value(QStringLiteral("hanh_dong")).toObject();
    QStringList act;
    for (const auto* f : {"tieu_de", "mo_ta"}) {
        const QString s = fmt::str(hd.value(QLatin1String(f)));
        if (!s.isEmpty())
            act << s;
    }
    root << (a::row() << a::k(QStringLiteral("Hành động chính"))
                      << (a::v() << hlpsgi_textOrNd(act.join(QStringLiteral(" · ")))));

    const QString dayGhi = fmt::str(vd.value(QStringLiteral("dieu_kien_day_ghi")));
    N vDay = a::v();
    if (dayGhi.isEmpty()) {
        vDay << fmt::ND();
    } else {
        const auto n = hlpsgi_dayCount(dayGhi);
        vDay << text(dayGhi);
        if (n && *n < 2)
            vDay.c(pal().down);
    }
    root << (a::row() << a::k(QStringLiteral("Điều kiện đáy")) << vDay);
}

/// 5a. Composite tiles printed by the issue (`to_hop`): txt / delta_txt verbatim, colour = mau.
void hlpsgi_printedComposites(N& root, const QJsonArray& toHop) {
    root << a::lbl(QStringLiteral("Điểm thành phần")).mt(10);
    N grid = a::tiles();
    for (const auto& cv : toHop) {
        const QJsonObject c = cv.toObject();
        const QString txt = fmt::str(c.value(QStringLiteral("txt")));
        N valDiv = a::monoD().size(14);
        if (txt.isEmpty())
            valDiv << fmt::ND();
        else
            valDiv.c(hlpsgi_mauColor(fmt::str(c.value(QStringLiteral("mau"))))) << text(txt);
        N t = a::tile();
        t << a::lbl(fmt::str(c.value(QStringLiteral("ten")))) << valDiv;
        const QString dtxt = fmt::str(c.value(QStringLiteral("delta_txt")));
        if (!dtxt.isEmpty())
            t << (div().size(9.5).c(pal().ink3) << text(dtxt + QStringLiteral(" so kỳ trước")));
        grid << t;
    }
    root << grid;
}

/// 5. Composite tiles — the issue's printed `to_hop` when present, else recomputed like
/// sgi_fa.py composite() (issues before 26/09 do not store them).
void hlpsgi_composites(N& root, const QJsonObject& issue) {
    const QJsonArray printed = issue.value(QStringLiteral("to_hop")).toArray();
    if (!printed.isEmpty()) {
        hlpsgi_printedComposites(root, printed);
        return;
    }
    std::optional<double> k[9];
    bool haveBlocks = false;
    for (const auto& bv : issue.value(QStringLiteral("khoi")).toArray()) {
        const QJsonObject b = bv.toObject();
        const auto id = fmt::num(b.value(QStringLiteral("id")));
        if (!id || *id < 1 || *id > 8 || *id != std::floor(*id))
            continue;
        haveBlocks = true;
        k[int(*id)] = fmt::num(b.value(QStringLiteral("diem")));
    }
    if (!haveBlocks)
        return;
    const QJsonObject prev = issue.value(QStringLiteral("to_hop_truoc")).toObject();

    root << a::lbl(QStringLiteral("Điểm thành phần")).mt(10);
    N grid = a::tiles();
    for (const auto& d : kHlpsgiToHop) {
        const QString ten = QString::fromUtf16(d.ten);
        std::optional<double> val;
        bool complete = true;
        double sum = 0;
        for (int i = 0; i < d.nKhoi; ++i) {
            if (!k[d.khoi[i]]) {
                complete = false;
                break;
            }
            sum += *k[d.khoi[i]];
        }
        if (complete)
            val = std::clamp(sum * d.heSo, -double(d.bien), double(d.bien));

        const QString bien = QStringLiteral(" / ±%1").arg(d.bien);
        N valDiv = a::monoD().size(14);
        if (val)
            valDiv.c(*val > 0 ? pal().up : (*val < 0 ? pal().down : pal().ink))
                << text(hlpsgi_num(*val, true) + bien);
        else
            valDiv << fmt::ND() << text(bien);

        N t = a::tile();
        t << a::lbl(ten) << valDiv;
        const auto truoc = fmt::num(prev.value(ten));
        if (val && truoc) {
            const double dlt = *val - *truoc;
            const QString dtxt = dlt > 0   ? QStringLiteral("▲") + hlpsgi_num(dlt, false)
                                 : dlt < 0 ? QStringLiteral("▼") + hlpsgi_num(-dlt, false)
                                           : QStringLiteral("—");
            t << (div().size(9.5).c(pal().ink3) << text(dtxt + QStringLiteral(" so kỳ trước")));
        }
        grid << t;
    }
    root << grid;
}

/// 6. Eight indicator blocks.
void hlpsgi_blocks(N& root, const QJsonArray& khoi) {
    if (khoi.isEmpty())
        return;
    root << a::lbl(QStringLiteral("Tám khối chỉ báo")).mt(10);
    for (const auto& bv : khoi) {
        const QJsonObject b = bv.toObject();
        const auto diem = fmt::num(b.value(QStringLiteral("diem")));
        const NodeP tg = diem ? a::tag(hlpsgi_num(*diem, true), hlpsgi_signColor(*diem)).node()
                              : a::tag(QStringLiteral("[CẦN DATA]"), pal().ink3).node();
        N it = a::item();
        it << (a::t() << tg << text(QStringLiteral(" ") + fmt::str(b.value(QStringLiteral("ten")))));
        const QString doi = fmt::str(b.value(QStringLiteral("doi_ky_nay")));
        if (!doi.isEmpty())
            it << (a::m() << text(doi));
        root << it;
    }
}

/// 7. Four bottom-confirmation conditions.
void hlpsgi_bottom(N& root, const QJsonArray& conds) {
    if (conds.isEmpty())
        return;
    root << a::lbl(QStringLiteral("Bốn điều kiện đáy")).mt(10);
    for (const auto& cv : conds) {
        const QJsonObject c = cv.toObject();
        const QString st = fmt::str(c.value(QStringLiteral("trang_thai")));
        const QString stU = hlpsgi_nfcUpper(st);
        const QColor col = stU == QStringLiteral("ĐẠT")         ? pal().up
                           : stU == QStringLiteral("MỘT PHẦN") ? pal().amber
                           : stU == QStringLiteral("CHƯA")     ? pal().down
                                                                : pal().ink3;
        N it = a::item();
        it << (a::t() << a::tag(st.isEmpty() ? QStringLiteral("[CẦN DATA]") : st, col)
                      << text(QStringLiteral(" ") + fmt::str(c.value(QStringLiteral("ten")))));
        QString ev = fmt::str(c.value(QStringLiteral("bang_chung"))).simplified();
        if (!ev.isEmpty()) {
            if (ev.size() > kHlpsgiEvidenceChars)
                ev = ev.left(kHlpsgiEvidenceChars).trimmed() + QStringLiteral("…");
            it << (div().size(10).c(pal().ink3).lhf(1.45) << text(QStringLiteral("↳ ") + ev));
        }
        root << it;
    }
}

/// Colour of a threshold's current value, from what the issue itself records: `vien` (the artifact's
/// card edge: do / xanh / vang, issue 26/09 on) wins; otherwise `huong` like the SGI FA tab's card edge
/// (dung → up, nguoc → down; xa / chua_ro carry no signal). No signal → ink (the .v default).
std::optional<QColor> hlpsgi_thresholdColor(const QJsonObject& r) {
    const QString vien = fmt::str(r.value(QStringLiteral("vien")));
    if (!vien.isEmpty()) {
        const QColor c = hlpsgi_mauColor(vien);
        return c == pal().ink ? std::nullopt : std::optional<QColor>(c);
    }
    const QString h = fmt::str(r.value(QStringLiteral("huong"))).trimmed().toLower();
    if (h == QStringLiteral("dung"))
        return pal().up;
    if (h == QStringLiteral("nguoc"))
        return pal().down;
    return std::nullopt;
}

/// 8. Reversal thresholds.
void hlpsgi_thresholds(N& root, const QJsonArray& rows) {
    if (rows.isEmpty())
        return;
    root << a::lbl(QStringLiteral("Ngưỡng đảo chiều")).mt(10);
    for (const auto& rv : rows) {
        const QJsonObject r = rv.toObject();
        const QString stU = hlpsgi_nfcUpper(fmt::str(r.value(QStringLiteral("trang_thai"))));
        // The issue writes "CHƯA" until a threshold is hit; sgi_fa's live layer uses "CHẠM".
        const bool hit = !stU.startsWith(QStringLiteral("CHƯA")) &&
                         (stU.contains(QStringLiteral("CHẠM")) || stU == QStringLiteral("ĐẠT"));
        N val = a::v() << hlpsgi_textOrNd(fmt::str(r.value(QStringLiteral("hien_tai"))));
        if (const auto col = hlpsgi_thresholdColor(r))
            val.c(*col);
        if (hit)
            val << span(QStringLiteral(" ✓")).c(pal().up);
        root << (a::row() << a::k(fmt::str(r.value(QStringLiteral("ten")))) << val);
    }
}

} // namespace

NodeP render_sgitin(RenderCtx& rc) {
    N root = div();
    const Data& d = rc.data;

    if (!d.sgiOk) {
        if (d.sgiFile.isEmpty()) {
            root << (a::warn() << text(QStringLiteral(
                         "Chưa có bản tuần Trạm Quan Trắc Vĩ Mô nào trong knowledge_os/sgi_ky/.")));
        } else {
            root << (a::warn() << text(QStringLiteral("Không đọc được bản tuần ") +
                                       QFileInfo(d.sgiFile).fileName() +
                                       QStringLiteral(" (schema sgi_ky/1).")));
        }
        return root;
    }
    const QJsonObject& s = d.sgi;

    // 1. stamp "<ky> · <tuổi> ngày" + stale warning
    const QString ky = fmt::str(s.value(QStringLiteral("ky")));
    const QDate kyDate = QDate::fromString(ky.left(10), Qt::ISODate);
    std::optional<qint64> age;
    if (kyDate.isValid() && rc.now.isValid())
        age = kyDate.daysTo(rc.now.date());
    if (rc.asof)
        *rc.asof = age ? QStringLiteral("%1 · %2 ngày").arg(ky).arg(*age) : ky;
    if (age && *age > kHlpsgiStaleDays) {
        root << (a::warn() << text(QStringLiteral("Bản tuần kỳ %1 đã %2 ngày — bản mới của routine thứ Bảy "
                                                  "chưa về máy. Số dưới đây là của kỳ đó.")
                                       .arg(ky)
                                       .arg(*age)));
    }

    // 2. source + disclaimer (verbatim tuyen_bo)
    QString src = QStringLiteral("Nguồn: artifact Trạm Quan Trắc Vĩ Mô — bản tuần kỳ %1 "
                                 "(routine Cowork 07:00 thứ Bảy).")
                      .arg(ky.isEmpty() ? QStringLiteral("[CẦN DATA]") : ky);
    const QString tuyenBo = fmt::str(s.value(QStringLiteral("tuyen_bo")));
    if (!tuyenBo.isEmpty())
        src += QStringLiteral(" ") + tuyenBo;
    root << (a::warnCyan() << text(src));

    // 3–4. verdict
    const QJsonValue vdv = s.value(QStringLiteral("verdict"));
    if (vdv.isObject())
        hlpsgi_verdict(root, vdv.toObject());
    else
        root << a::lbl(QStringLiteral("Chế độ")) << a::big(QStringLiteral("[CẦN DATA]")).c(pal().amber);

    // 5–8.
    hlpsgi_composites(root, s);
    hlpsgi_blocks(root, s.value(QStringLiteral("khoi")).toArray());
    hlpsgi_bottom(root, s.value(QStringLiteral("dieu_kien_day")).toArray());
    hlpsgi_thresholds(root, s.value(QStringLiteral("nguong_dao_chieu")).toArray());

    // 9. note
    N note = a::note();
    note << text(QStringLiteral("Mỗi số trong bản tuần mang nhãn bậc riêng (FACT-T1 / SS-T3 / EST / NEWS); "
                                "ở đây chỉ hiện kết luận. Mở bản đầy đủ: "));
    const QString url = fmt::str(s.value(QStringLiteral("artifact_url")));
    if (url.isEmpty())
        note << fmt::ND();
    else
        note << a::link(url, url);
    const QString kySau = fmt::str(s.value(QStringLiteral("ky_sau")));
    note << text(kySau.isEmpty() ? QStringLiteral(".") : QStringLiteral(" · kỳ sau %1.").arg(kySau));
    root << note;

    return root;
}

} // namespace fincept::screens::hlp
