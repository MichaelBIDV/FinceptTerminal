// src/screens/langkinh/LkNumberLineCard.cpp
// Lăng Kính FFT — thẻ của block "numline" (LK_HOSO_SPEC §6): khung bo 10px + đầu block (title/sub/b) + LkNumberLine
// + pill nhãn VWAP. Tách khỏi LkNumberLine.cpp để mỗi tệp ≤ 800 dòng. Xem LkNumberLine.h.
#include "screens/langkinh/LkNumberLine.h"

#include "screens/langkinh/LkChips.h"

#include <QFont>
#include <QFrame>
#include <QHBoxLayout>
#include <QJsonObject>
#include <QLabel>
#include <QVBoxLayout>

namespace fincept::screens::langkinh {

namespace lknlcard {

/// QSS của thẻ: nền surface, viền line, bo 10px; mọi con nền trong suốt (nhãn tự mang QSS qua lk_label).
QString card_qss() {
    using namespace lkview;
    return QStringLiteral("QFrame#lkNlCard { background:%1; border:1px solid %2; border-radius:10px; }"
                          "QFrame#lkNlCard QWidget { background:transparent; border:none; }")
        .arg(lk_qss(lk_col(LkRole::Surface)), lk_qss(lk_col(LkRole::Line)));
}

/// Pill nhãn VWAP (§4) + diễn giải định nghĩa; mã lạ → pill in hoa nguyên văn, không diễn giải.
QWidget* nhan_row(const QString& code, QWidget* parent) {
    using namespace lkview;
    QString pill;
    QString desc;
    if (code == QLatin1String("kep_nong")) {
        pill = lk_tr("KẸP NÔNG");
        desc = lk_tr("Giá dưới cả ba cụm VWAP, cụm xa nhất cách không quá 6%");
    } else if (code == QLatin1String("kep_sau")) {
        pill = lk_tr("KẸP SÂU");
        desc = lk_tr("Giá dưới cả ba cụm VWAP, có cụm cách hơn 6%");
    } else if (code == QLatin1String("thoat_6t")) {
        pill = lk_tr("THOÁT CỤM 6T");
        desc = lk_tr("Giá trên VWAP 6T, còn dưới 12T và 24T");
    } else if (code == QLatin1String("tren_cum")) {
        pill = lk_tr("TRÊN CỤM");
        desc = lk_tr("Giá trên cả ba cụm VWAP");
    } else {
        pill = code.toUpper();
    }
    auto* w = new QWidget(parent);
    auto* hl = new QHBoxLayout(w);
    hl->setContentsMargins(0, 2, 0, 0);
    hl->setSpacing(10);
    hl->addWidget(new LkPill(pill, LkRole::Amber, w, 11, true), 0, Qt::AlignVCenter);
    if (desc.isEmpty())
        hl->addStretch(1);
    else
        hl->addWidget(lk_label(desc, lk_font_sans(12), lk_col(LkRole::Ink2), w), 1);
    return w;
}

} // namespace lknlcard

namespace lkview {

QWidget* make_numline(const QJsonObject& b, QWidget* parent) {
    const QString mode = b.value(QStringLiteral("mode")).toString().trimmed().toLower();
    if (mode != QLatin1String("vwap") && mode != QLatin1String("sigma") && mode != QLatin1String("ruler"))
        return nullptr;

    auto* card = new QFrame(parent);
    card->setObjectName(QStringLiteral("lkNlCard"));
    card->setAttribute(Qt::WA_StyledBackground, true);
    card->setStyleSheet(lknlcard::card_qss());
    auto* vl = new QVBoxLayout(card);
    vl->setContentsMargins(16, 12, 16, 12);
    vl->setSpacing(6);
    lk_add_head(vl, b, card);

    auto* nl = new LkNumberLine(b, card);
    const QString gaps = nl->missing().join(QStringLiteral(" · "));
    const QFont gap_font = lk_font_mono(11, 600);
    if (nl->valid()) {
        vl->addWidget(nl);
        const QString nhan = b.value(QStringLiteral("nhan")).toString().trimmed();
        if (mode == QLatin1String("vwap") && !nhan.isEmpty())
            vl->addWidget(lknlcard::nhan_row(nhan, card));
        if (!gaps.isEmpty()) // số tuỳ chọn thiếu (một cụm VWAP, dải 52 tuần, mục ruler hỏng): vẫn vẽ, ghi rõ
            vl->addWidget(lk_label(lk_tr("[CẦN DATA] — %1").arg(gaps), gap_font, lk_col(LkRole::Down), card));
    } else {
        delete nl;
        vl->addWidget(lk_label(lk_tr("[CẦN DATA] — %1").arg(gaps.isEmpty() ? dash() : gaps), gap_font,
                               lk_col(LkRole::Down), card));
    }
    vl->addStretch(1); // trong "row" thẻ kéo cao bằng thẻ bên cạnh: phần dư dồn xuống đáy, không giãn khe tiêu đề
    return card;
}

} // namespace lkview

} // namespace fincept::screens::langkinh
