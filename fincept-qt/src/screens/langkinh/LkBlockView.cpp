// src/screens/langkinh/LkBlockView.cpp
// Lăng Kính FFT — bộ vẽ trang từ JSON của fincept_langkinh.py (CONTRACT §3.1, §4).
// Nguyên tắc: chỉ ĐỌC và VẼ. Thiếu khoá/sai kiểu → "—" hoặc bỏ block; không suy diễn số.
// Tệp này: lk_color, khung trang (QSS, banner + tiêu đề, điều phối block) và block chart/scatter.
// Các block khác ở LkWidgets.cpp (banner, note, tiles, matrix, lists, html), LkTableBlock.cpp (table) và
// LkStory.cpp / LkTimeline.cpp (story, timeline — DELTA v4 V4.3).
// Block hồ sơ (LK_HOSO_SPEC §6): LkKpiStrip (kpis) · LkPillarBlock (pillars) · LkNumberLine (numline) ·
// LkRrgChart (rrg) · LkCards (cards, tkhead) · LkChips (chips) · LkSodo (sodo) · LkCotMoc (cotmoc);
// màu/phông chung ở LkTheme.h.
// Hợp đồng block v2 (LkPage): layout "hoso" (cột 1180px, .gate, thẻ .fig), "eyebrow" → đầu phần, "row".
#include "screens/langkinh/LkBlockView.h"

#include "screens/langkinh/LkCards.h"
#include "screens/langkinh/LkChart.h"
#include "screens/langkinh/LkChips.h"
#include "screens/langkinh/LkCotMoc.h"
#include "screens/langkinh/LkKpiStrip.h"
#include "screens/langkinh/LkLayouts.h"
#include "screens/langkinh/LkNumberLine.h"
#include "screens/langkinh/LkPage.h"
#include "screens/langkinh/LkPillarBlock.h"
#include "screens/langkinh/LkRrgChart.h"
#include "screens/langkinh/LkSodo.h"
#include "screens/langkinh/LkStory.h"
#include "screens/langkinh/LkTableBlock.h"
#include "screens/langkinh/LkTheme.h"
#include "screens/langkinh/LkWidgets.h"
#include "ui/theme/Theme.h"
#include "ui/theme/ThemeManager.h"

#include <QFrame>
#include <QJsonArray>
#include <QLabel>
#include <QScrollBar>
#include <QStringList>
#include <QTimer>
#include <QVBoxLayout>

#include <algorithm>

namespace fincept::screens::langkinh {

// ── Màu ngữ nghĩa (định nghĩa DUY NHẤT; LkChart.cpp dùng lại) ────────────────

QColor lk_color(const QString& mau) {
    using namespace ui::colors;
    if (mau == QLatin1String("bull"))
        return QColor(POSITIVE());
    if (mau == QLatin1String("bear"))
        return QColor(NEGATIVE());
    if (mau == QLatin1String("warn"))
        return QColor(WARNING());
    if (mau == QLatin1String("info"))
        return QColor(INFO());
    if (mau == QLatin1String("amber"))
        return QColor(AMBER());
    if (mau == QLatin1String("cyan"))
        return QColor(CYAN());
    if (mau == QLatin1String("dim"))
        return QColor(TEXT_SECONDARY());
    return QColor(TEXT_PRIMARY());
}

// ═════════════════════════════════════════════════════════════════════════════
// LkBlockView
// ═════════════════════════════════════════════════════════════════════════════

LkBlockView::LkBlockView(QWidget* parent) : QScrollArea(parent) {
    setWidgetResizable(true);
    setFrameShape(QFrame::NoFrame);
    setHorizontalScrollBarPolicy(Qt::ScrollBarAsNeeded);
    apply_frame_style();
    render(false);
    // Màu lấy tại lúc dựng → theme đổi thì dựng lại cả trang (giữ vị trí cuộn).
    connect(&ui::ThemeManager::instance(), &ui::ThemeManager::theme_changed, this, [this]() {
        apply_frame_style();
        render(true);
    });
}

void LkBlockView::set_payload(const QJsonObject& payload) {
    payload_ = payload;
    render(false);
}

void LkBlockView::clear() {
    payload_ = QJsonObject();
    render(false);
}

void LkBlockView::apply_frame_style() {
    setStyleSheet(QStringLiteral("QScrollArea { background:%1; border:none; }").arg(ui::colors::BG_BASE()));
}

QString LkBlockView::canvas_qss(bool hoso) const {
    using namespace ui::colors;
    using namespace lkview;
    const QString base = QStringLiteral(
               "QWidget#lkCanvas { background:%1; }"
               "QFrame#lkCard { background:%2; border:1px solid %3; }"
               "QFrame#lkCell { background:%4; border:1px solid %3; }"
               "QLabel#lkH1 { color:%5; font-size:14px; font-weight:700; letter-spacing:0.5px; background:transparent; }"
               "QLabel#lkSub { color:%6; font-size:11px; background:transparent; }"
               "QLabel#lkCap { color:%6; font-size:10px; background:transparent; }"
               "QLabel#lkBlockTitle { color:%5; font-size:12px; font-weight:700; background:transparent; }"
               "QLabel#lkCellTitle { color:%5; font-size:11px; font-weight:700; background:transparent; }"
               "QLabel#lkText { color:%5; font-size:11px; background:transparent; }"
               "QLabel#lkTileK { color:%6; font-size:9px; font-weight:700; letter-spacing:0.5px;"
               "  background:transparent; }"
               "QLabel#lkTileS { color:%6; font-size:10px; background:transparent; }"
               "QLabel#lkColHead { color:%6; font-size:10px; font-weight:700; background:transparent; }"
               "QLabel#lkRowHead { color:%7; font-size:12px; font-weight:700; background:transparent; }"
               "QLabel#lkListRow { color:%5; font-size:11px; background:transparent; }"
               "QLabel#lkMeta { color:%8; font-size:10px; background:transparent; }")
        .arg(BG_BASE(), BG_SURFACE(), BORDER_DIM(), BG_RAISED(), TEXT_PRIMARY(), TEXT_SECONDARY(), AMBER(),
             TEXT_TERTIARY());
    // Container trần của hợp đồng v2 (cột trang, đầu phần, row, đầu trang, khổ chữ): nền trong suốt theo objectName
    // — không lan xuống con như lk_transparent. Chỉ khớp objectName mới → trang cũ không đổi.
    const QString containers = QStringLiteral("QWidget#lkCol, QWidget#lkSec, QWidget#lkRow, QWidget#lkHead,"
                                              " QWidget#lkMeasure { background:transparent; }");
    if (!hoso)
        return base + containers;
    // Trang hồ sơ: thẻ cũ (matrix, lists…) cùng độ nổi với thẻ hồ sơ (surface suy từ theme, bo 10px).
    return base + containers +
           QStringLiteral("QFrame#lkCard { background:%1; border:1px solid %2; border-radius:10px; }"
                          "QFrame#lkCell { background:%3; border:1px solid %2; border-radius:8px; }")
               .arg(lk_qss(lk_col(LkRole::Surface)), lk_qss(lk_col(LkRole::Line)), lk_qss(lk_col(LkRole::Surface2)));
}

QString LkBlockView::table_qss() const {
    using namespace ui::colors;
    return QStringLiteral(
               "QTableWidget { background:%1; color:%2; border:1px solid %3; gridline-color:%3; font-size:11px;"
               "  alternate-background-color:%4; }"
               "QTableWidget::item { padding:5px 8px; border-bottom:1px solid %3; }"
               "QTableWidget::item:selected { background:%5; color:%2; }"
               "QHeaderView::section { background:%6; color:%7; border:none; border-bottom:2px solid %3;"
               "  border-right:1px solid %3; padding:5px 8px; font-size:10px; font-weight:700; letter-spacing:0.5px; }"
               "QHeaderView { background:%6; border:none; }"
               "QTableCornerButton::section { background:%6; border:none; }"
               "QScrollBar:horizontal { background:%1; height:6px; }"
               "QScrollBar::handle:horizontal { background:%8; min-width:24px; }"
               "QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal { width:0; }"
               "QScrollBar:vertical { background:%1; width:6px; }"
               "QScrollBar::handle:vertical { background:%8; min-height:24px; }"
               "QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height:0; }")
        .arg(BG_BASE(), TEXT_PRIMARY(), BORDER_DIM(), BG_SURFACE(), lkview::rgba(QColor(AMBER()), 38), BG_RAISED(),
             TEXT_SECONDARY(), BORDER_BRIGHT());
}

void LkBlockView::render(bool keep_scroll) {
    const int old_scroll = keep_scroll && verticalScrollBar() ? verticalScrollBar()->value() : 0;
    if (QWidget* old = takeWidget()) {
        old->hide();
        old->deleteLater(); // kể cả khi đang trong xử lý chuột của một widget con
    }

    hoso_ = lkview::is_hoso(payload_);
    auto* canvas = new QWidget;
    canvas->setObjectName(QStringLiteral("lkCanvas"));
    canvas->setAttribute(Qt::WA_StyledBackground, true);
    canvas->setStyleSheet(canvas_qss(hoso_) + (hoso_ ? lkview::hoso_table_qss() : table_qss()));
    // Trang cũ: block xếp thẳng trên canvas. Trang hồ sơ: cột canh giữa rộng tối đa 1180px, lề 20px.
    QWidget* host = canvas;
    QVBoxLayout* vl = nullptr;
    if (hoso_) {
        auto* page = new lkview::LkColumnLayout(canvas, lkview::kHosoMaxW, Qt::AlignHCenter);
        page->setContentsMargins(lkview::kHosoGutter, 18, lkview::kHosoGutter, 48);
        host = new QWidget(canvas);
        host->setObjectName(QStringLiteral("lkCol"));
        page->addWidget(host);
        vl = new QVBoxLayout(host);
        vl->setContentsMargins(0, 0, 0, 0);
        vl->setSpacing(lkview::kHosoGap);
    } else {
        vl = new QVBoxLayout(canvas);
        vl->setContentsMargins(12, 10, 12, 16);
        vl->setSpacing(10);
    }

    if (!payload_.isEmpty()) {
        const QJsonArray blocks = payload_.value(QStringLiteral("blocks")).toArray();
        if (hoso_) {
            vl->addWidget(lkview::make_gate(payload_.value(QStringLiteral("cong")), host));
            bool first_tk = false; // khối đầu là đầu mã → bỏ H1/sub (trùng mã), giữ dòng meta
            for (const auto& bv : blocks)
                if (bv.isObject()) {
                    first_tk = bv.toObject().value(QStringLiteral("type")).toString() == QLatin1String("tkhead");
                    break;
                }
            if (QWidget* h = lkview::make_hoso_header(payload_, first_tk, host))
                vl->addWidget(h);
        } else {
            vl->addWidget(lkview::make_banner(payload_.value(QStringLiteral("cong")), canvas));
            vl->addWidget(make_header(canvas));
        }
        const int sec_gap = std::max(0, lkview::kHosoSectionGap - vl->spacing());
        int n = 0;
        for (const auto& bv : blocks) {
            if (!bv.isObject())
                continue;
            const QJsonObject bo = bv.toObject();
            if (QWidget* w = make_any(bo, host)) {
                if (lkview::has_section_head(bo)) // phần mới: cách phần trước ~40px (Artifact section{margin-top})
                    vl->addSpacing(sec_gap);
                vl->addWidget(w);
                ++n;
            }
        }
        if (n == 0)
            vl->addWidget(lkview::make_label(tr("Trang này không có block nào để hiển thị."), "lkCap", host));
    }
    vl->addStretch(1);
    setWidget(canvas);

    if (keep_scroll && old_scroll > 0)
        QTimer::singleShot(0, this, [this, old_scroll]() { verticalScrollBar()->setValue(old_scroll); });
    else if (verticalScrollBar())
        verticalScrollBar()->setValue(0);
}

QWidget* LkBlockView::make_header(QWidget* parent) {
    using namespace ui::colors;
    auto* w = new QWidget(parent);
    auto* vl = new QVBoxLayout(w);
    vl->setContentsMargins(0, 2, 0, 0);
    vl->setSpacing(2);
    const QString title = payload_.value(QStringLiteral("title")).toString().trimmed();
    vl->addWidget(lkview::make_label(title.isEmpty() ? lkview::dash() : title, "lkH1", w));
    const QString sub = payload_.value(QStringLiteral("sub")).toString().trimmed();
    if (!sub.isEmpty())
        vl->addWidget(lkview::make_label(sub, "lkSub", w, Qt::AutoText));

    QStringList meta;
    const QString scope = payload_.value(QStringLiteral("scope")).toString().trimmed();
    const QString as_of = payload_.value(QStringLiteral("as_of")).toString().trimmed();
    const QString tuoi = payload_.value(QStringLiteral("tuoi")).toString().trimmed();
    if (!scope.isEmpty())
        meta << scope;
    if (!as_of.isEmpty())
        meta << tr("dữ liệu tới %1").arg(as_of);
    if (!tuoi.isEmpty())
        meta << tuoi;
    if (!meta.isEmpty()) {
        auto* m = lkview::make_label(meta.join(QStringLiteral(" · ")), "lkMeta", w);
        if (tuoi.contains(QStringLiteral("CŨ")))
            m->setStyleSheet(
                QStringLiteral("QLabel { color:%1; font-size:10px; font-weight:700; background:transparent; }")
                    .arg(WARNING()));
        vl->addWidget(m);
    }
    return w;
}

// ── Các block ─────────────────────────────────────────────────────────────────

QWidget* LkBlockView::make_any(const QJsonObject& b, QWidget* parent) {
    const lkview::BlockFn inner = [this](const QJsonObject& o, QWidget* p) { return make_any(o, p); };
    if (lkview::has_section_head(b)) // make_section bỏ eyebrow khỏi block rồi gọi lại make_any → không đệ quy vô hạn
        return lkview::make_section(b, parent, inner);
    if (b.value(QStringLiteral("type")).toString() == QLatin1String("row"))
        return lkview::make_row(b, parent, inner);
    return make_block(b, parent);
}

QWidget* LkBlockView::make_block(const QJsonObject& b, QWidget* parent) {
    const QString type = b.value(QStringLiteral("type")).toString();
    // Chip ma trận / nhấp đúp hàng bảng → ticker_activated (nối hàng đợi ở panel).
    const lkview::TickerFn on_ticker = [this](const QString& ma) { emit ticker_activated(ma); };
    if (type == QLatin1String("note")) {
        if (!hoso_)
            return lkview::make_note(b, parent);
        QJsonObject n = b; // khoá nội bộ: ghi chú theo thẻ .fig của trang hồ sơ
        n.insert(QStringLiteral("_hoso"), true);
        return lkview::make_note(n, parent);
    }
    if (type == QLatin1String("tiles"))
        return lkview::make_tiles(b, parent);
    if (type == QLatin1String("table")) {
        if (!hoso_)
            return lkview::make_table_block(b, parent, on_ticker);
        QJsonObject t = b; // khoá nội bộ: bảng dựng theo thẻ .fig của trang hồ sơ
        t.insert(QStringLiteral("_hoso"), true);
        return lkview::make_table_block(t, parent, on_ticker);
    }
    if (type == QLatin1String("matrix"))
        return lkview::make_matrix(b, parent, on_ticker);
    if (type == QLatin1String("lists"))
        return lkview::make_lists(b, parent);
    if (type == QLatin1String("html"))
        return lkview::make_html(b, parent);
    if (type == QLatin1String("story")) // bấm thẻ (hoặc mục timeline có link) → mở view chuoi của mã
        return lkview::make_story(b, parent, on_ticker);
    if (type == QLatin1String("timeline"))
        return lkview::make_timeline(b, parent, on_ticker);
    if (type == QLatin1String("chart"))
        return make_chart(b, parent, false);
    if (type == QLatin1String("scatter"))
        return make_chart(b, parent, true);
    // Block hồ sơ (LK_HOSO_SPEC §6) — mỗi hàm trả nullptr khi không có gì để vẽ (vòng render bỏ qua).
    if (type == QLatin1String("kpis"))
        return lkview::make_kpis(b, parent);
    if (type == QLatin1String("pillars"))
        return lkview::make_pillars(b, parent);
    if (type == QLatin1String("numline"))
        return lkview::make_numline(b, parent);
    if (type == QLatin1String("rrg")) // bấm mũi tên/nhãn mã → ticker_activated (panel mở hồ sơ mã)
        return lkview::make_rrg(b, parent, on_ticker);
    if (type == QLatin1String("cards"))
        return lkview::make_cards(b, parent);
    if (type == QLatin1String("chips"))
        return lkview::make_chips(b, parent);
    if (type == QLatin1String("tkhead"))
        return lkview::make_tkhead(b, parent);
    if (type == QLatin1String("sodo")) // thấu kính NTH: sơ đồ hình lý tưởng của mẫu hình
        return lkview::make_sodo(b, parent);
    if (type == QLatin1String("cotmoc")) // cột mốc rời kiểu holdChart (số cổ đông theo mốc)
        return lkview::make_cotmoc(b, parent);
    return lkview::make_label(tr("[block chưa hỗ trợ: %1]").arg(type.isEmpty() ? QStringLiteral("?") : type), "lkCap",
                              parent);
}

QWidget* LkBlockView::make_chart(const QJsonObject& b, QWidget* parent, bool scatter) {
    QFrame* card = nullptr;
    QVBoxLayout* vl = nullptr;
    QJsonObject cb = b;
    if (hoso_) { // thẻ .fig: bo 10, viền line, đệm 14/14/10, tiêu đề sans 14/600 + dòng nguồn muted (+ tag `b`)
        card = lkview::make_fig(parent, &vl);
        lkview::lk_add_head(vl, b, card, lkview::LkHead::Fig);
        cb.insert(QStringLiteral("_hoso"), true);
    } else {
        card = new QFrame(parent);
        card->setObjectName(QStringLiteral("lkCard"));
        vl = new QVBoxLayout(card);
        vl->setContentsMargins(10, 8, 10, 8);
        vl->setSpacing(4);
        lkview::add_head(vl, b, card);
    }
    const int def_h = scatter ? 380 : (hoso_ ? lkview::kFigChartH : 320);
    const int h = std::clamp(b.value(QStringLiteral("height")).toInt(def_h), 160, 900);

    if (scatter) {
        auto* ch = new LkScatterChart(cb, card);
        if (ch->point_count() == 0) {
            delete ch;
            vl->addWidget(lkview::make_label(tr("— không có điểm nào để vẽ —"), "lkCap", card));
        } else {
            ch->setFixedHeight(h);
            connect(ch, &LkScatterChart::ticker_activated, this, &LkBlockView::ticker_activated);
            vl->addWidget(ch);
        }
    } else {
        auto* ch = new LkLineChart(cb, card);
        if (!ch->has_data()) {
            delete ch;
            vl->addWidget(lkview::make_label(tr("— không có dữ liệu để vẽ —"), "lkCap", card));
        } else {
            ch->setFixedHeight(h);
            vl->addWidget(ch);
            // Chú giải riêng (hợp đồng v2): vạch 18px, đứt khi dash — thay ô vuông của QtCharts.
            if (QWidget* lg = lkview::make_legend(b.value(QStringLiteral("legend")).toArray(), hoso_, card))
                vl->addWidget(lg);
        }
    }
    if (hoso_) // thẻ .fig trong "row" kéo cao bằng thẻ bên cạnh: phần dư dồn xuống đáy
        vl->addStretch(1);
    return card;
}

} // namespace fincept::screens::langkinh