// src/screens/deepfa/DeepFaUniverseTable.cpp
#include "screens/deepfa/DeepFaUniverseTable.h"

#include "screens/deepfa/DeepFaCommon.h"

#include <QAbstractItemView>
#include <QHeaderView>
#include <QJsonArray>
#include <QJsonValue>
#include <QKeyEvent>
#include <QStringList>
#include <QTableWidgetItem>

#include <algorithm>
#include <cmath>
#include <limits>

namespace fincept::screens::deepfa {

namespace {

// Private helpers carry the "ut_" prefix: the unity build may merge this TU with the sections.

const char* ut_kHeaders[DeepFaUniverseTable::ColCount] = {
    "Mã", "DM", "State", "Memo", "Giá", "Δ memo", "σ P/E", "EDI", "BLĐ⚔street", "TP (SS-T3)", "Fund (gate)", "Dòng tiền 20p", "⚠",
};

double ut_num(const QJsonValue& v) {
    return v.isDouble() ? v.toDouble() : std::numeric_limits<double>::quiet_NaN();
}

double ut_numobj(const QJsonObject& r, const char* key) {
    return ut_num(r.value(QLatin1String(key)).toObject().value(QLatin1String("v")));
}

/// Sort key of a row for `col` (numbers as doubles, NaN last; strings compared case-insensitively).
struct ut_Key {
    double d = std::numeric_limits<double>::quiet_NaN();
    QString s;
    bool numeric = true;
};

ut_Key ut_key(const QJsonObject& r, int col) {
    ut_Key k;
    switch (col) {
    case DeepFaUniverseTable::ColTicker:
        k.numeric = false;
        k.s = r.value(QLatin1String("tk")).toString();
        break;
    case DeepFaUniverseTable::ColDm: {
        // NAV weight first, then WATCH, AVOID, others
        const QString dm = r.value(QLatin1String("dm")).toString();
        const double nav = ut_num(r.value(QLatin1String("nav_pct")));
        if (dm == QLatin1String("NAV"))
            k.d = 1000.0 + (std::isnan(nav) ? 0.0 : nav);
        else if (dm == QLatin1String("WATCH"))
            k.d = 500.0;
        else if (dm == QLatin1String("AVOID"))
            k.d = 250.0;
        else
            k.d = 0.0 - ut_num(r.value(QLatin1String("mktcap_rank")));
        break;
    }
    case DeepFaUniverseTable::ColState:
        k.numeric = false;
        k.s = r.value(QLatin1String("state")).toString(QStringLiteral("Z"));
        break;
    case DeepFaUniverseTable::ColMemo:
        k.d = ut_num(r.value(QLatin1String("memo_age_days")));
        break;
    case DeepFaUniverseTable::ColPrice:
        k.d = ut_numobj(r, "gia");
        break;
    case DeepFaUniverseTable::ColDelta:
        k.d = ut_numobj(r, "delta_pct");
        break;
    case DeepFaUniverseTable::ColSigma:
        k.d = ut_numobj(r, "sigma_pe");
        break;
    case DeepFaUniverseTable::ColEdi:
        k.d = ut_numobj(r, "edi");
        break;
    case DeepFaUniverseTable::ColAlign: {
        const double up = ut_num(r.value(QLatin1String("street_up")));
        const double dn = ut_num(r.value(QLatin1String("street_down")));
        k.d = (std::isnan(up) || std::isnan(dn)) ? std::numeric_limits<double>::quiet_NaN() : up - dn;
        break;
    }
    case DeepFaUniverseTable::ColTp:
        k.d = ut_num(r.value(QLatin1String("tp_upside_pct")));
        break;
    case DeepFaUniverseTable::ColFund:
        k.numeric = false;
        k.s = r.value(QLatin1String("fund_label")).toString();
        break;
    case DeepFaUniverseTable::ColFlow: {
        const double a = ut_numobj(r, "foreign_net_20");
        const double b = ut_numobj(r, "prop_net_20");
        k.d = (std::isnan(a) && std::isnan(b)) ? std::numeric_limits<double>::quiet_NaN()
                                               : (std::isnan(a) ? 0.0 : a) + (std::isnan(b) ? 0.0 : b);
        break;
    }
    case DeepFaUniverseTable::ColFlags:
        k.d = static_cast<double>(r.value(QLatin1String("flags")).toArray().size());
        break;
    default:
        break;
    }
    return k;
}

bool ut_less(const ut_Key& a, const ut_Key& b, bool asc) {
    if (!a.numeric || !b.numeric) {
        const int c = QString::compare(a.s, b.s, Qt::CaseInsensitive);
        return asc ? c < 0 : c > 0;
    }
    const bool an = std::isnan(a.d), bn = std::isnan(b.d);
    if (an || bn)
        return !an && bn; // NaN always last, whatever the direction
    return asc ? a.d < b.d : a.d > b.d;
}

QTableWidgetItem* ut_item(const QString& text, const QColor& fg, bool bold = false, Qt::Alignment align = Qt::AlignLeft | Qt::AlignVCenter) {
    auto* it = new QTableWidgetItem(text);
    it->setForeground(fg);
    it->setTextAlignment(align);
    if (bold) {
        QFont f = it->font();
        f.setBold(true);
        it->setFont(f);
    }
    it->setFlags(it->flags() & ~Qt::ItemIsEditable);
    return it;
}

QString ut_join(const QJsonArray& arr) {
    QStringList out;
    for (const QJsonValue& v : arr)
        if (v.isString() && !v.toString().trimmed().isEmpty())
            out << v.toString();
    return out.join(QStringLiteral("\n"));
}

} // namespace

// ── Construction ─────────────────────────────────────────────────────────────

DeepFaUniverseTable::DeepFaUniverseTable(QWidget* parent) : QTableWidget(0, ColCount, parent) {
    setObjectName(QStringLiteral("deepfaUniverseTable"));
    setSelectionBehavior(QAbstractItemView::SelectRows);
    setSelectionMode(QAbstractItemView::SingleSelection);
    setEditTriggers(QAbstractItemView::NoEditTriggers);
    setAlternatingRowColors(true);
    setSortingEnabled(false); // sorting is ours (NaN-last, semantic keys)
    setWordWrap(false);
    verticalHeader()->setVisible(false);
    verticalHeader()->setDefaultSectionSize(26);
    horizontalHeader()->setStretchLastSection(false);
    horizontalHeader()->setSectionsClickable(true);
    horizontalHeader()->setHighlightSections(false);
    connect(horizontalHeader(), &QHeaderView::sectionClicked, this, &DeepFaUniverseTable::sort_by_column);
    connect(this, &QTableWidget::cellDoubleClicked, this, [this](int row, int) { activate_row(row); });
    connect(this, &QTableWidget::cellClicked, this, [this](int row, int col) {
        if (col == ColTicker)
            activate_row(row);
    });
    update_headers();
}

void DeepFaUniverseTable::set_rows(const QJsonArray& rows) {
    rows_ = rows;
    rebuild();
}

void DeepFaUniverseTable::apply(const Filter& f) {
    filter_ = f;
    rebuild();
}

bool DeepFaUniverseTable::passes(const QJsonObject& r, const Filter& f) {
    const QString dm = r.value(QLatin1String("dm")).toString();
    if (f.dm == QLatin1String("DM")) {
        if (dm != QLatin1String("NAV") && dm != QLatin1String("WATCH"))
            return false;
    } else if (!f.dm.isEmpty() && dm != f.dm) {
        return false;
    }
    if (!f.state.isEmpty() && r.value(QLatin1String("state")).toString() != f.state)
        return false;
    if (f.deep_only && !r.value(QLatin1String("deep")).toBool())
        return false;
    if (f.regen_only && !r.value(QLatin1String("can_regen")).toBool())
        return false;
    if (f.flagged_only && r.value(QLatin1String("flags")).toArray().isEmpty())
        return false;
    if (!f.search.trimmed().isEmpty()) {
        const QString q = f.search.trimmed();
        const QString tk = r.value(QLatin1String("tk")).toString();
        const QString name = r.value(QLatin1String("ten")).toString();
        if (!tk.startsWith(q, Qt::CaseInsensitive) && !name.contains(q, Qt::CaseInsensitive))
            return false;
    }
    return true;
}

void DeepFaUniverseTable::rebuild() {
    shown_.clear();
    for (const QJsonValue& v : rows_) {
        const QJsonObject r = v.toObject();
        if (passes(r, filter_))
            shown_.push_back(r);
    }
    const int col = sort_col_;
    const bool asc = sort_asc_;
    std::stable_sort(shown_.begin(), shown_.end(), [col, asc](const QJsonObject& a, const QJsonObject& b) {
        return ut_less(ut_key(a, col), ut_key(b, col), asc);
    });

    setUpdatesEnabled(false);
    clearContents();
    setRowCount(static_cast<int>(shown_.size()));
    for (int i = 0; i < shown_.size(); ++i)
        fill_row(i, shown_.at(i));
    resizeColumnsToContents();
    setUpdatesEnabled(true);
    update_headers();
    emit count_changed(static_cast<int>(shown_.size()));
}

void DeepFaUniverseTable::fill_row(int row, const QJsonObject& r) {
    const QColor ink = col(Role::Ink), muted = col(Role::Muted);
    const QString tk = r.value(QLatin1String("tk")).toString();

    auto* tk_it = ut_item(tk, col(Role::Amber), true);
    tk_it->setToolTip(r.value(QLatin1String("ten")).toString() + QStringLiteral(" · ") +
                      r.value(QLatin1String("nhom")).toString());
    setItem(row, ColTicker, tk_it);

    // DM
    const QString dm = r.value(QLatin1String("dm")).toString();
    QString dm_txt;
    QColor dm_c = muted;
    if (dm == QLatin1String("NAV")) {
        const double nav = ut_num(r.value(QLatin1String("nav_pct")));
        dm_txt = std::isnan(nav) ? QStringLiteral("NAV") : QStringLiteral("NAV %1%").arg(QString::number(nav, 'f', 0));
        dm_c = col(Role::Up);
    } else if (dm == QLatin1String("WATCH")) {
        dm_txt = QStringLiteral("WATCH");
        dm_c = col(Role::Blue);
    } else if (dm == QLatin1String("AVOID")) {
        dm_txt = QStringLiteral("AVOID");
        dm_c = col(Role::Down);
    }
    setItem(row, ColDm, ut_item(dm_txt, dm_c, dm == QLatin1String("NAV")));

    // State
    const QString st = r.value(QLatin1String("state")).toString();
    auto* st_it = ut_item(st.isEmpty() ? QStringLiteral("—") : st, state_color(st), !st.isEmpty(), Qt::AlignCenter);
    st_it->setToolTip(r.value(QLatin1String("state_txt")).toString());
    setItem(row, ColState, st_it);

    // Memo: date · age · deep
    const QString ms = r.value(QLatin1String("memo_status")).toString();
    QString memo_txt;
    if (ms == QLatin1String("missing")) {
        memo_txt = QStringLiteral("chưa có");
    } else {
        memo_txt = r.value(QLatin1String("memo_date")).toString() + QStringLiteral(" · ") +
                   r.value(QLatin1String("memo_age_txt")).toString();
        if (r.value(QLatin1String("deep")).toBool())
            memo_txt += QStringLiteral(" · deep");
        if (r.value(QLatin1String("can_regen")).toBool())
            memo_txt += QStringLiteral(" · ↻");
    }
    auto* memo_it = ut_item(memo_txt, status_color(ms));
    memo_it->setToolTip(or_need(r.value(QLatin1String("can_regen_ly_do")).toString()) + QStringLiteral("\nengine: ") +
                        or_need(r.value(QLatin1String("engine")).toString()));
    setItem(row, ColMemo, memo_it);

    // Price + date
    const QJsonObject gia = r.value(QLatin1String("gia")).toObject();
    auto* p_it = ut_item(num_txt(gia), ink, false, Qt::AlignRight | Qt::AlignVCenter);
    p_it->setToolTip(gia.value(QLatin1String("t")).toString() + QStringLiteral(" · ") + gia.value(QLatin1String("n")).toString());
    setItem(row, ColPrice, p_it);

    // Δ since memo
    const QJsonObject dl = r.value(QLatin1String("delta_pct")).toObject();
    auto* d_it = ut_item(num_txt(dl), dir_color(dl.value(QLatin1String("v"))), false, Qt::AlignRight | Qt::AlignVCenter);
    d_it->setToolTip(dl.value(QLatin1String("n")).toString());
    setItem(row, ColDelta, d_it);

    // σ P/E + zone (+ date)
    const QJsonObject sg = r.value(QLatin1String("sigma_pe")).toObject();
    const double sv = ut_num(sg.value(QLatin1String("v")));
    QColor sc = muted;
    if (!std::isnan(sv))
        sc = sv < -1.0 ? col(Role::Up) : (sv > 1.0 ? col(Role::Down) : ink);
    auto* s_it = ut_item(num_txt(sg), sc, false, Qt::AlignRight | Qt::AlignVCenter);
    s_it->setToolTip(or_need(r.value(QLatin1String("zone_pe")).toString()) + QStringLiteral(" · đo ") +
                     or_need(sg.value(QLatin1String("t")).toString()) + QStringLiteral(" · ") + sg.value(QLatin1String("b")).toString());
    setItem(row, ColSigma, s_it);

    // EDI
    const QJsonObject ed = r.value(QLatin1String("edi")).toObject();
    const QString stage = r.value(QLatin1String("edi_stage")).toString();
    const bool late = r.value(QLatin1String("edi_late")).toBool();
    QString edi_txt = num_txt(ed);
    if (!stage.isEmpty())
        edi_txt += QStringLiteral(" · ") + stage + (late ? QStringLiteral(" (LATE)") : QString());
    setItem(row, ColEdi, ut_item(edi_txt, late ? col(Role::Amber) : ink));

    // BLĐ ⚔ street
    const QString tone = r.value(QLatin1String("bld_tone")).toString();
    const QString align = r.value(QLatin1String("align")).toString();
    const double up = ut_num(r.value(QLatin1String("street_up")));
    const double dn = ut_num(r.value(QLatin1String("street_down")));
    QString al_txt;
    if (!tone.isEmpty())
        al_txt += tone;
    if (!std::isnan(up) || !std::isnan(dn))
        al_txt += (al_txt.isEmpty() ? QString() : QStringLiteral(" ⚔ ")) +
                  QStringLiteral("▲%1/▼%2").arg(std::isnan(up) ? QStringLiteral("—") : QString::number(up, 'f', 0),
                                                 std::isnan(dn) ? QStringLiteral("—") : QString::number(dn, 'f', 0));
    if (al_txt.isEmpty())
        al_txt = QStringLiteral("—");
    auto* al_it = ut_item(al_txt, align.startsWith(QChar(0x26A0)) ? col(Role::Down) : ink);
    al_it->setToolTip(or_need(align));
    setItem(row, ColAlign, al_it);

    // TP (SS-T3)
    const QJsonObject tp = r.value(QLatin1String("tp")).toObject();
    const bool tp_stale = r.value(QLatin1String("tp_stale")).toBool();
    const double ups = ut_num(r.value(QLatin1String("tp_upside_pct")));
    QString tp_txt = num_txt(tp);
    if (!std::isnan(ups) && tp.value(QLatin1String("v")).isDouble())
        tp_txt += QStringLiteral(" (%1%2%)").arg(ups >= 0 ? QStringLiteral("+") : QString(), QString::number(ups, 'f', 0));
    if (tp_stale)
        tp_txt += QStringLiteral(" ⚠cũ");
    auto* tp_it = ut_item(tp_txt, tp_stale ? col(Role::Amber) : col(Role::Violet), false, Qt::AlignRight | Qt::AlignVCenter);
    tp_it->setToolTip(or_need(r.value(QLatin1String("rating")).toString()) + QStringLiteral(" · ") +
                      or_need(tp.value(QLatin1String("t")).toString()) + QStringLiteral(" · ") + tp.value(QLatin1String("b")).toString() +
                      (tp.value(QLatin1String("g")).isString() ? QStringLiteral("\n") + tp.value(QLatin1String("g")).toString() : QString()));
    setItem(row, ColTp, tp_it);

    // Fund intent (gated)
    const QString fg = r.value(QLatin1String("fund_gate")).toString();
    const QString fl = r.value(QLatin1String("fund_label")).toString();
    QString f_txt = fg == QLatin1String("GATE-BLIND") ? QStringLiteral("GATE-BLIND") : (fl.isEmpty() ? QStringLiteral("—") : fl);
    QColor fc = muted;
    if (fg == QLatin1String("GATE-BLIND"))
        fc = col(Role::Down);
    else if (fg == QStringLiteral("CHƯA LỌC"))
        fc = col(Role::Amber);
    else if (fl.startsWith(QLatin1String("ACCUM")))
        fc = col(Role::Up);
    else if (fl.startsWith(QLatin1String("DISTR")))
        fc = col(Role::Down);
    setItem(row, ColFund, ut_item(f_txt, fc));

    // Flow 20 sessions
    const QJsonObject fn = r.value(QLatin1String("foreign_net_20")).toObject();
    const QJsonObject pn = r.value(QLatin1String("prop_net_20")).toObject();
    const QString fl_txt = QStringLiteral("NN %1 · TD %2").arg(num_txt(fn), num_txt(pn));
    auto* fl_it = ut_item(fl_txt, ink, false, Qt::AlignRight | Qt::AlignVCenter);
    fl_it->setToolTip(QStringLiteral("tỷ đồng, Σ20 phiên · ") + or_need(fn.value(QLatin1String("t")).toString()) + QStringLiteral(" · FACT-T2 vc_lk"));
    setItem(row, ColFlow, fl_it);

    // Flags
    const QJsonArray flags = r.value(QLatin1String("flags")).toArray();
    auto* fg_it = ut_item(flags.isEmpty() ? QString() : QString::number(flags.size()), flags.isEmpty() ? muted : col(Role::Amber), !flags.isEmpty(), Qt::AlignCenter);
    fg_it->setToolTip(ut_join(flags));
    setItem(row, ColFlags, fg_it);
}

void DeepFaUniverseTable::update_headers() {
    QStringList labels;
    for (int c = 0; c < ColCount; ++c) {
        QString l = QString::fromUtf8(ut_kHeaders[c]);
        if (c == sort_col_)
            l += sort_asc_ ? QStringLiteral(" ▲") : QStringLiteral(" ▼");
        labels << l;
    }
    setHorizontalHeaderLabels(labels);
}

void DeepFaUniverseTable::sort_by_column(int column) {
    if (column < 0 || column >= ColCount)
        return;
    if (column == sort_col_) {
        sort_asc_ = !sort_asc_;
    } else {
        sort_col_ = column;
        // numbers: descending first (largest/most interesting on top); text: ascending
        sort_asc_ = (column == ColTicker || column == ColState || column == ColFund || column == ColMemo);
    }
    rebuild();
}

void DeepFaUniverseTable::activate_row(int row) {
    if (row < 0 || row >= shown_.size())
        return;
    const QString tk = shown_.at(row).value(QLatin1String("tk")).toString();
    if (!tk.isEmpty())
        emit ticker_activated(tk);
}

void DeepFaUniverseTable::keyPressEvent(QKeyEvent* event) {
    if (event->key() == Qt::Key_Return || event->key() == Qt::Key_Enter) {
        activate_row(currentRow());
        event->accept();
        return;
    }
    QTableWidget::keyPressEvent(event);
}

QJsonArray DeepFaUniverseTable::visible_rows() const {
    QJsonArray out;
    for (const QJsonObject& r : shown_)
        out.append(r);
    return out;
}

QStringList DeepFaUniverseTable::completer_entries() const {
    QStringList out;
    for (const QJsonValue& v : rows_) {
        const QJsonObject r = v.toObject();
        const QString tk = r.value(QLatin1String("tk")).toString();
        if (tk.isEmpty())
            continue;
        out << tk + QStringLiteral(" — ") + r.value(QLatin1String("ten")).toString();
    }
    return out;
}

} // namespace fincept::screens::deepfa
