// src/screens/hdcv_launchpad/HlpPanels_WdDetail.cpp
// HĐCV Launchpad — WIDATA · MARKET SIGNALS, the chart column of wdRender (panels.js 1045–1092 + the
// catalogue <select> and the 3T/6T/1N/Tất cả window): split out of HlpPanels_Wd.cpp (≤800 lines/file).
// Shared pieces (JS value helpers, HlpWdEnv, state keys, .wd-bar/.chips) live in HlpPanels_Wd_p.h.
#include "screens/hdcv_launchpad/HlpAtoms.h"
#include "screens/hdcv_launchpad/HlpCharts.h"
#include "screens/hdcv_launchpad/HlpFmt.h"
#include "screens/hdcv_launchpad/HlpPanels.h"
#include "screens/hdcv_launchpad/HlpPanels_Wd_p.h"
#include "screens/hdcv_launchpad/HlpTheme.h"

#include <QAbstractItemView>
#include <QBrush>
#include <QCollator>
#include <QColor>
#include <QComboBox>
#include <QEvent>
#include <QFont>
#include <QHash>
#include <QJsonObject>
#include <QJsonValue>
#include <QLocale>
#include <QPainter>
#include <QPointer>
#include <QScrollBar>
#include <QSignalBlocker>
#include <QStandardItem>
#include <QStandardItemModel>
#include <QStringList>
#include <QTimer>
#include <QVariant>

#include <algorithm>
#include <cmath>
#include <functional>
#include <optional>
#include <utility>

namespace fincept::screens::hlp {

namespace {

namespace a = atoms;

constexpr float hlpwd_kSelectMaxW = 260.0f;  // .wd-bar select { max-width: 260px }
constexpr float hlpwd_kSelectH = 19.5f;      // measured height of the <select> (Arial 10.5px, padding 2px 5px)

/// WD_QG[code] (undefined → "").
QString hlpwd_qg(const QString& code) {
    static const QHash<QString, QString> m = {
        {QStringLiteral("VN"), QStringLiteral("Việt Nam")}, {QStringLiteral("US"), QStringLiteral("Mỹ")},
        {QStringLiteral("CN"), QStringLiteral("Trung Quốc")}, {QStringLiteral("EU"), QStringLiteral("Châu Âu")},
        {QStringLiteral("JP"), QStringLiteral("Nhật Bản")}, {QStringLiteral("INTL"), QStringLiteral("Quốc tế")}};
    return m.value(code);
}

/// WD_TS[tan_suat] (undefined → "").
QString hlpwd_ts(const QString& f) {
    static const QHash<QString, QString> m = {
        {QStringLiteral("daily"), QStringLiteral("ngày")},     {QStringLiteral("weekly"), QStringLiteral("tuần")},
        {QStringLiteral("monthly"), QStringLiteral("tháng")},  {QStringLiteral("quarterly"), QStringLiteral("quý")},
        {QStringLiteral("event"), QStringLiteral("sự kiện")}};
    return m.value(f);
}

/// Math.round(x) as JS prints it.
QString hlpwd_round(double x) {
    if (std::isnan(x))
        return QStringLiteral("NaN");
    return fmt::jsString(std::floor(x + 0.5));
}

// ---- chart column (drawChart, panels.js 1045–1092) ----

/// `<div class="row"><span class="k">k</span><span class="v">v</span></div>`
NodeP hlpwd_kv(const QString& k, const QString& v) {
    N r = a::row();
    N vv = a::v();
    vv << text(v);
    r << a::k(k) << vv;
    return r;
}

/// `.wd-head`: country · sampling · N points + name | big latest value + delta · date.
NodeP hlpwd_head(const QJsonObject& s, const QString& mau) {
    const QString unit = hlpwd_s(s.value(QStringLiteral("don_vi")));
    QString qg = hlpwd_qg(hlpwd_s(s.value(QStringLiteral("quoc_gia"))));
    if (qg.isEmpty())
        qg = hlpwd_or(s.value(QStringLiteral("quoc_gia")), QString());

    N left = div();
    left << a::lbl(QStringLiteral("%1 · %2 · %3 điểm").arg(qg, mau, hlpwd_tpl(s.value(QStringLiteral("n")))))
         << a::b(hlpwd_s(s.value(QStringLiteral("nhan")))).size(12.0f);

    N big = a::big();
    big.size(19.0f).lhf(1.1f).ls(-0.01f) << fmt::wdFmt(hlpwd_val(s.value(QStringLiteral("cuoi"))), unit); // .wd-head .big
    N sub = a::monoD();
    sub.size(10.0f);
    const QJsonValue cu = s.value(QStringLiteral("cuoi"));
    const QJsonValue tr = s.value(QStringLiteral("truoc"));
    if (!hlpwd_nullish(cu) && !hlpwd_nullish(tr)) {
        const double d = fmt::plus(cu).value_or(std::nan("")) - fmt::plus(tr).value_or(std::nan(""));
        sub << fmt::wdDelta(s, d)
            << text(QStringLiteral(" so với %1 · ").arg(hlpwd_or(s.value(QStringLiteral("nhan_truoc")), QStringLiteral("kỳ trước"))));
    }
    const QString nc = hlpwd_or(s.value(QStringLiteral("ngay_cuoi")), QString());
    if (!nc.isEmpty())
        sub << text(nc);
    N right = div();
    right.right() << big << sub;

    N head = div();
    head.key(QStringLiteral("div.wd-head")).flex(Justify::SpaceBetween, AlignItems::Baseline, 8.0f) << left << right;
    return head;
}

/// Rows + warnings under the chart.
void hlpwd_detail(N& wdc, const QJsonObject& s, bool suKien, const QString& tsText) {
    const Palette& P = pal();
    wdc << (a::row().mt(6.0f) << a::k(QStringLiteral("Loại số"))
                              << (a::v() << text(QStringLiteral("%1 · %2").arg(hlpwd_or(s.value(QStringLiteral("loai")), QString()),
                                                                              hlpwd_or(s.value(QStringLiteral("don_vi")), QString())))));

    const QJsonValue qv = s.value(QStringLiteral("khop_tieu_de"));
    const QJsonValue boKiem = s.value(QStringLiteral("bo_kiem_tieu_de"));
    const double q = hlpwd_nullish(qv) ? std::nan("") : fmt::plus(qv).value_or(std::nan(""));
    QString qt = hlpwd_nullish(qv) ? QStringLiteral("—") : hlpwd_round(q * 100.0) + QStringLiteral("%");
    if (hlpwd_truthy(boKiem))
        qt += QStringLiteral(" · không áp dụng");
    N qn = a::v();
    if (!hlpwd_nullish(qv) && q < 0.6 && !hlpwd_truthy(boKiem))
        qn.c(P.down);
    qn << text(qt);
    wdc << (a::row() << a::k(QStringLiteral("Khớp với tiêu đề tín hiệu")) << qn);
    if (hlpwd_truthy(boKiem))
        wdc << (div().size(9.5f).c(P.ink3) << text(QStringLiteral("↳ ") + hlpwd_s(boKiem)));

    const QJsonValue xd = s.value(QStringLiteral("xung_dot_ngay"));
    if (hlpwd_truthy(xd))
        wdc << hlpwd_kv(QStringLiteral("Ngày có bản sửa khác số"), hlpwd_tpl(xd) + QStringLiteral(" (lấy bản sau cùng)"));
    const QJsonValue ds = s.value(QStringLiteral("da_sua_ky_sau"));
    if (hlpwd_truthy(ds))
        wdc << hlpwd_kv(QStringLiteral("Điểm đã thay bằng số sửa của kỳ sau"), hlpwd_tpl(ds));
    const QJsonValue bl = s.value(QStringLiteral("bo_lap"));
    if (hlpwd_truthy(bl))
        wdc << hlpwd_kv(QStringLiteral("Dòng lặp nguyên đã bỏ (ngày nghỉ)"), hlpwd_tpl(bl));
    const QJsonValue kd = s.value(QStringLiteral("kiem_dinh"));
    if (hlpwd_truthy(kd))
        wdc << hlpwd_kv(QStringLiteral("Luật trích"), hlpwd_or(kd.toObject().value(QStringLiteral("ket_qua")), QString()));

    if (hlpwd_truthy(s.value(QStringLiteral("co_the_ngung")))) {
        const QString chuoi = suKien ? QStringLiteral("phát theo sự kiện")
                                     : (tsText.isEmpty() ? hlpwd_s(s.value(QStringLiteral("tan_suat"))) : tsText);
        wdc << (a::warn().mt(5.0f)
                << text(QStringLiteral("Chậm cập nhật: kỳ cuối %1, đã %2 ngày — quá độ trễ thường thấy của chuỗi %3. "
                                       "Đừng đọc số này như số mới nhất.")
                            .arg(hlpwd_or(s.value(QStringLiteral("ngay_cuoi")), QString()),
                                 hlpwd_s(s.value(QStringLiteral("tuoi_ngay"))), chuoi)));
    }
    if (suKien)
        wdc << (div().size(9.5f).c(P.ink3).mt(4.0f)
                << text(QStringLiteral("WiData chỉ phát tín hiệu cho chuỗi này khi có biến động — các điểm là mẫu rời, "
                                       "không phải chuỗi liên tục; nối thẳng giữa hai điểm không có nghĩa giá đi thẳng.")));
    if (hlpwd_truthy(s.value(QStringLiteral("tham_khao"))))
        wdc << (a::warn().mt(5.0f)
                << text(QStringLiteral("Chỉ tham khảo: tầng kiểm định thấy mức giá và %đổi của chuỗi này không khớp "
                                       "nhau ở nhiều phiên.")));
    const QJsonValue cb = s.value(QStringLiteral("canh_bao"));
    if (hlpwd_truthy(cb))
        wdc << (div().size(10.0f).c(P.ink3).lhf(1.45f).mt(4.0f) << text(QStringLiteral("↳ ") + hlpwd_s(cb)));
    wdc << (div().size(9.5f).c(P.ink3).mt(5.0f)
            << text(QStringLiteral("Chuỗi chỉ dài từ khi WiData bắt đầu phát tín hiệu cho chỉ tiêu này — không phải "
                                   "toàn bộ lịch sử như biểu đồ trên widata.vn.")));
}

// ---- catalogue <select id="wdsel"> ----

struct HlpWdOpt {
    QString text;
    QString key;         ///< empty for the placeholder and group headers
    bool header = false; ///< <optgroup label>
};

/// keys sorted by (quoc_gia || '') then nhan ('vi' collation, stable), grouped by quoc_gia || 'INTL' in
/// first-seen order — the <option>/<optgroup> list of wdRender.
QVector<HlpWdOpt> hlpwd_options(const QJsonObject& S) {
    struct K {
        QString key, qg, nhan, n;
    };
    QVector<K> ks;
    ks.reserve(S.size());
    for (auto it = S.begin(); it != S.end(); ++it) {
        const QJsonObject s = it.value().toObject();
        ks.append({it.key(), hlpwd_or(s.value(QStringLiteral("quoc_gia")), QString()),
                   hlpwd_s(s.value(QStringLiteral("nhan"))), hlpwd_tpl(s.value(QStringLiteral("n")))});
    }
    QCollator coll{QLocale(QLocale::Vietnamese, QLocale::Vietnam)};
    std::stable_sort(ks.begin(), ks.end(), [&coll](const K& x, const K& y) {
        const int c = coll.compare(x.qg, y.qg);
        return c != 0 ? c < 0 : coll.compare(x.nhan, y.nhan) < 0;
    });

    QVector<std::pair<QString, QVector<const K*>>> groups;
    for (const K& k : ks) {
        const QString q = k.qg.isEmpty() ? QStringLiteral("INTL") : k.qg;
        auto g = std::find_if(groups.begin(), groups.end(), [&q](const auto& p) { return p.first == q; });
        if (g == groups.end())
            groups.append({q, {&k}});
        else
            g->second.append(&k);
    }

    QVector<HlpWdOpt> opts;
    opts.append({QStringLiteral("— Danh mục %1 chỉ tiêu —").arg(ks.size()), QString(), false});
    for (const auto& [q, members] : groups) {
        const QString label = hlpwd_qg(q);
        opts.append({label.isEmpty() ? q : label, QString(), true});
        for (const K* k : members)
            opts.append({QStringLiteral("%1 · %2 điểm").arg(k->nhan, k->n), k->key, false});
    }
    return opts;
}

/// Chrome's author-styled `<select>` (`.wd-bar select`), painted in place of the QComboBox: the pill
/// (bg-2, 1px line-2, radius 14 clamped like CSS) on the box HlpView hands over ("hlp_box", fractional),
/// the current option in Arial 10.5px through the engine (Qt would round the size to 11px), and the
/// menu-list chevron — an aliased 2px V in ink at 50% whose pixels were read off the Chrome capture
/// (Chrome draws it on integer device pixels, so the pattern only moves with the rounded box).
class HlpWdSelectPaint final : public QObject {
  public:
    explicit HlpWdSelectPaint(QComboBox* box) : QObject(box), box_(box) {
        setObjectName(QStringLiteral("hlpwd_select_paint"));
        box->installEventFilter(this);
    }

  protected:
    bool eventFilter(QObject* obj, QEvent* ev) override {
        if (ev->type() != QEvent::Paint || obj != box_)
            return QObject::eventFilter(obj, ev);
        const Palette& P = pal();
        QRectF r = box_->property("hlp_box").toRectF();
        if (!r.isValid())
            r = QRectF(box_->rect());
        QPainter p(box_);
        p.setRenderHint(QPainter::Antialiasing);
        const double rad = std::min(double(kRadius), std::min(r.width(), r.height()) / 2.0);
        // as every rounded CSS box: background half a pixel inside the border edge, then the ring
        fillRRect(p, r.adjusted(0.5, 0.5, -0.5, -0.5), Radii4::all(std::max(0.0, rad - 0.5)), P.bg2);
        const QRectF hole = r.adjusted(1, 1, -1, -1);
        const Radii4 hk = Radii4::all(std::max(0.0, rad - 1.0));
        fillRRect(p, r, Radii4::all(rad), P.line2, &hole, &hk);
        // option text: padding 2px 5px + border, Chrome's menu-list start inset → 10px from the outer edge
        const QString t = box_->currentText();
        if (!t.isEmpty()) {
            p.save();
            p.setClipRect(QRectF(r.left() + 6.0, r.top(), std::max(0.0, r.width() - 6.0 - 20.0), r.height()));
            const TextVMetrics vm = textVMetricsArial(10.5f);
            const double lineH = double(vm.ascent + vm.descent);
            const double top = r.top() + 3.0 + (r.height() - 6.0 - lineH) / 2.0 + double(vm.ascent);
            const double base = std::floor(std::floor(top * 2.0 + 0.5) / 2.0 + 0.5);
            QRectF css = box_->property("hlp_css").toRectF(); // text starts from the unsnapped layout box
            if (!css.isValid())
                css = r;
            drawTextArial(p, QPointF(css.left() + 10.0, base), t, 10.5f, 400, P.ink);
            p.restore();
        }
        // chevron (Chrome 153, pixels read off the captures): a 1px V in ink, 6 rows starting 14px left of
        // the rounded right edge. Where the box centre falls on a quarter pixel (.25: widata, select at
        // 116.5) the arms sit on pixel centres — each pixel ink, flanked by ink at 25%; on the other
        // quarter (.75: the same select in vimo at 1672) they straddle two rows — ink at 50%, 2px wide.
        // Measured in one window on both views (27/09 07:5x), so the page position decides, not focus.
        const int x0 = int(std::lround(r.right())) - 14;
        const double cy = r.top() + r.height() / 2.0;
        const int y0 = int(std::lround(cy)) - 3;
        const bool straddle = std::abs(cy - std::floor(cy) - 0.75) < 0.125;
        p.setRenderHint(QPainter::Antialiasing, false);
        const auto ink = [&P](float a) {
            QColor c = P.ink;
            c.setAlphaF(a);
            return c;
        };
        if (straddle) {
            static const int kHalf[16][2] = {{1, 0}, {8, 0}, {1, 1}, {2, 1}, {7, 1}, {8, 1}, {2, 2}, {3, 2},
                                             {6, 2}, {7, 2}, {3, 3}, {4, 3}, {5, 3}, {6, 3}, {4, 4}, {5, 4}};
            for (const auto& h : kHalf)
                p.fillRect(QRect(x0 + h[0], y0 + h[1], 1, 1), ink(0.5f));
            p.fillRect(QRect(x0 + 9, y0, 1, 1), ink(0.25f));
            return true;
        }
        static const int kFull[8][2] = {{1, 1}, {2, 2}, {3, 3}, {4, 4}, {8, 1}, {7, 2}, {6, 3}, {5, 4}};
        static const int kQuarter[14][2] = {{8, 0}, {0, 1}, {2, 1}, {7, 1}, {1, 2}, {3, 2}, {6, 2},
                                            {8, 2}, {2, 3}, {4, 3}, {5, 3}, {7, 3}, {3, 4}, {6, 4}};
        for (const auto& q : kQuarter)
            p.fillRect(QRect(x0 + q[0], y0 + q[1], 1, 1), ink(0.25f));
        p.fillRect(QRect(x0 + 4, y0 + 5, 2, 1), ink(0.25f));
        for (const auto& f : kFull)
            p.fillRect(QRect(x0 + f[0], y0 + f[1], 1, 1), P.ink);
        return true;
    }

  private:
    QComboBox* box_;
};

/// Chrome on macOS opens a <select> as a native menu with the CURRENT option drawn over the select
/// (a long menu fills the screen height and is scrolled to keep that alignment). Qt's own popup path
/// (styles with SH_ComboBox_Popup) sizes the list the same way but then scrolls the current row to the
/// CENTRE of the list. Once showPopup() has returned, scroll so the current row's top sits on the
/// combo's top again (clamped by the scroll range). Qt's native NSMenu path never shows this container.
class HlpWdPopupAlign final : public QObject {
  public:
    HlpWdPopupAlign(QComboBox* box, QWidget* container) : QObject(container), box_(box) {
        setObjectName(QStringLiteral("hlpwd_popup_align"));
        container->installEventFilter(this);
    }

  protected:
    bool eventFilter(QObject* obj, QEvent* ev) override {
        if (ev->type() == QEvent::Show)
            QTimer::singleShot(0, this, [this] { align(); }); // after showPopup's scrollTo(PositionAtCenter)
        return QObject::eventFilter(obj, ev);
    }

  private:
    void align() {
        if (!box_)
            return;
        QAbstractItemView* v = box_->view();
        if (!v || !v->isVisible())
            return;
        const QRect r = v->visualRect(v->model()->index(box_->currentIndex(), box_->modelColumn(), box_->rootModelIndex()));
        if (!r.isValid() || r.height() <= 0)
            return;
        const int dy = v->viewport()->mapToGlobal(r.topLeft()).y() - box_->mapToGlobal(QPoint(0, 0)).y();
        QScrollBar* sb = v->verticalScrollBar();
        sb->setValue(sb->value() + (v->verticalScrollMode() == QAbstractItemView::ScrollPerItem
                                        ? qRound(double(dy) / r.height())
                                        : dy));
    }

    QPointer<QComboBox> box_;
};

/// `.wd-bar select`: bg-2, ink, 1px line-2, radius r (clamped to the pill), Arial 10.5px, padding 2px 5px
/// (+ Chrome's inner start inset → text 10px from the outer edge). Popup: panel bg, bold optgroup rows.
void hlpwd_style_select(QComboBox* sel) {
    const Palette& P = pal();
    const QFont f = arial(10.5f);
    const QString fs = f.pointSizeF() > 0 ? QStringLiteral("%1pt").arg(f.pointSizeF())
                                          : QStringLiteral("%1px").arg(f.pixelSize());
    const auto hex = [](const QColor& c) { return c.name(QColor::HexArgb); };
    const QString qss =
        QStringLiteral("QComboBox{background-color:%1;color:%2;border:1px solid %3;border-radius:9px;"
                       "padding:2px 5px 2px 8px;font-family:Arial;font-size:%4;font-weight:400;}"
                       "QComboBox::drop-down{border:none;width:16px;}"
                       "QComboBox::down-arrow{image:none;width:0px;height:0px;}"
                       "QComboBox QAbstractItemView{background-color:%5;color:%2;border:1px solid %3;outline:0;"
                       "selection-background-color:%6;selection-color:%2;font-family:Arial;font-size:%4;}"
                       "QComboBox QAbstractItemView::item{padding:1px 6px;border:none;}")
            .arg(hex(P.bg2), hex(P.ink), hex(P.line2), fs, hex(P.panel), hex(mixT(P.amber, 25.0f)));
    if (sel->styleSheet() != qss)
        sel->setStyleSheet(qss);
    sel->setProperty("hlp_paintsFrame", true); // HlpView hands over the fractional box ("hlp_box")
    if (!sel->property("hlpwd_paint").toBool()) {
        sel->setProperty("hlpwd_paint", true);
        new HlpWdSelectPaint(sel);
    }
    if (!sel->property("hlpwd_popup_align").toBool()) {
        sel->setProperty("hlpwd_popup_align", true);
        new HlpWdPopupAlign(sel, sel->view()->window()); // view() creates the popup container
    }
}

/// Rebuild the items only when the catalogue (or the theme) changed, so an open popup survives renders.
void hlpwd_fill_select(QComboBox* sel, const QVector<HlpWdOpt>& opts) {
    QStringList parts{is_dark() ? QStringLiteral("d") : QStringLiteral("l")};
    for (const HlpWdOpt& o : opts)
        parts << (o.header ? QStringLiteral("#") : QString()) + o.text + QChar(0x1f) + o.key;
    const QString sig = parts.join(QChar(0x1e));
    if (sel->property("hlpwd_sig").toString() == sig)
        return;

    const QSignalBlocker block(sel);
    sel->clear();
    auto* model = qobject_cast<QStandardItemModel*>(sel->model());
    QFont bold;
    bold.setBold(true);
    for (const HlpWdOpt& o : opts) {
        sel->addItem(o.text, o.header ? QVariant() : QVariant(o.key));
        if (o.header && model) {
            QStandardItem* it = model->item(sel->count() - 1);
            it->setFlags(it->flags() & ~(Qt::ItemIsSelectable | Qt::ItemIsEnabled));
            it->setData(bold, Qt::FontRole);
            it->setData(QBrush(pal().ink), Qt::ForegroundRole);
        }
    }
    sel->setProperty("hlpwd_sig", sig);
}

/// sel.onchange — re-wired on every render so the handler never holds a stale state pointer.
void hlpwd_wire_select(QComboBox* sel, QVariantMap* vs, QVariantMap* inst, const std::function<void()>& rerender) {
    const QString guardName = QStringLiteral("hlpwd_sel_guard");
    for (QObject* old : sel->findChildren<QObject*>(guardName, Qt::FindDirectChildrenOnly)) {
        QObject::disconnect(sel, nullptr, old, nullptr);
        old->setObjectName(QString());
        old->deleteLater();
    }
    auto* guard = new QObject(sel);
    guard->setObjectName(guardName);
    QObject::connect(sel, &QComboBox::activated, guard, [sel, vs, inst, rerender](int i) {
        const QString k = sel->itemData(i).toString();
        if (k.isEmpty()) // wdOwn(S, '') — placeholder or group header
            return;
        vs->insert(hlpwd_kKey, k);
        hlpwd_redraw(inst, rerender, -1, true);
    });
}

} // namespace

/// #wdc: the chart block for st.key, or the hint when the key has no series.
NodeP hlpwd_chart(const QJsonObject& S, const QString& key, const QString& range) {
    N wdc = div();
    wdc.key(QStringLiteral("div#wdc"));
    if (key.isEmpty() || !S.contains(key)) {
        wdc << a::ndD(QStringLiteral("Bấm một tín hiệu có thẻ chỉ tiêu, hoặc chọn trong danh mục, để xem biểu đồ."))
                   .m(24.0f, 0.0f, 24.0f, 0.0f);
        return wdc;
    }
    const QJsonObject s = S.value(key).toObject();
    const bool suKien = s.value(QStringLiteral("lay_mau")).toString() == QLatin1String("su_kien");
    const QString ts = hlpwd_ts(hlpwd_s(s.value(QStringLiteral("tan_suat"))));
    const QString mau = suKien ? QStringLiteral("theo sự kiện") : (ts.isEmpty() ? hlpwd_or(s.value(QStringLiteral("tan_suat")), QString()) : ts);
    wdc << hlpwd_head(s, mau) << charts::wdChart(s, range);
    hlpwd_detail(wdc, s, suKien, ts);
    return wdc;
}

/// The <select> node. Selected option: st.key when it has a series and the web would have run
/// `sel.value = st.key`; a fresh wdRender otherwise shows the placeholder; a list-only redraw keeps it.
NodeP hlpwd_select(RenderCtx& rc, const HlpWdEnv& e, bool external, bool sync) {
    QComboBox* sel = rc.combo ? rc.combo(QStringLiteral("sel")) : nullptr;
    if (!sel)
        return nullptr;
    const QVector<HlpWdOpt> opts = hlpwd_options(e.S);
    hlpwd_style_select(sel);
    hlpwd_fill_select(sel, opts);
    sel->setAccessibleName(QStringLiteral("Chọn chỉ tiêu để vẽ"));

    const int want = (!e.key.isEmpty() && e.S.contains(e.key)) ? sel->findData(e.key) : -1;
    if (want >= 0 && (external || sync))
        sel->setCurrentIndex(want);
    else if (external)
        sel->setCurrentIndex(0);
    hlpwd_wire_select(sel, e.vs, e.inst, e.rerender);

    // Intrinsic width (widest option + measured insets: text 10px in, chevron area ~22px), capped at 260.
    float widest = 0;
    for (const HlpWdOpt& o : opts)
        widest = std::max(widest, textWidthArial(o.text, 10.5f));
    const float w = std::min(hlpwd_kSelectMaxW, float(widest) + 32.0f);

    N n = div();
    n.key(QStringLiteral("select#wdsel")).widget(sel).w(w).h(hlpwd_kSelectH);
    return n;
}

/// 3T / 6T / 1N / Tất cả (redraws only the chart in the web).
NodeP hlpwd_range_chips(const QString& range, const HlpWdEnv& e) {
    QVariantMap* vs = e.vs;
    QVariantMap* inst = e.inst;
    const std::function<void()> rerender = e.rerender;
    const QVector<std::pair<QString, QString>> ranges = {{QStringLiteral("m3"), QStringLiteral("3T")},
                                                         {QStringLiteral("m6"), QStringLiteral("6T")},
                                                         {QStringLiteral("y1"), QStringLiteral("1N")},
                                                         {QStringLiteral("all"), QStringLiteral("Tất cả")}};
    N c = hlpwd_chips();
    for (const auto& [k, l] : ranges) {
        c << a::chip(l, k == range, [vs, inst, rerender, k = k] {
            vs->insert(hlpwd_kRange, k);
            hlpwd_redraw(inst, rerender, std::nullopt, true);
        });
    }
    return c;
}

} // namespace fincept::screens::hlp
