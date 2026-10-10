// src/screens/deepfa/DeepFaUniverseTable.h
// "Bàn triage" — one row per universe ticker (247): where the memo stands (State · tuổi · deep ·
// cần regen), what today's layers say (giá bảng · Δ từ ngày memo · σ P/E kèm ngày · EDI · BLĐ⚔street
// · TP sell-side với cờ cũ · fund intent qua GATE LVF · dòng tiền 20 phiên) and the ⚠ flags a PM must
// see before opening the page. Rows are the `rows` array of `deepfa.py overview` (contract in that
// script's docstring). Filtering / sorting are done in place — no re-fetch. Every cell is text the
// script pre-formatted; this table never computes a number.
#pragma once

#include <QJsonArray>
#include <QJsonObject>
#include <QString>
#include <QTableWidget>
#include <QVector>

class QKeyEvent;

namespace fincept::screens::deepfa {

class DeepFaUniverseTable : public QTableWidget {
    Q_OBJECT
  public:
    enum Column {
        ColTicker = 0, ///< Mã (+ tên công ty tooltip)
        ColDm,         ///< NAV % / WATCH / AVOID
        ColState,      ///< State A/B/C/D của memo (màu theo state)
        ColMemo,       ///< ngày memo · tuổi (đỏ khi > 45 ngày → UNVERIFIED) · deep ✓
        ColPrice,      ///< giá bảng (đồng) + ngày
        ColDelta,      ///< Δ% từ ngày memo (điều chỉnh CA)
        ColSigma,      ///< σ P/E (HHP) + vùng
        ColEdi,        ///< EDI /100 · stage (LATE đỏ)
        ColAlign,      ///< BLĐ ⚔ street: tone · ▲/▼ · alignment
        ColTp,         ///< TP Vietcap (SS-T3) · upside · cờ cũ >90d
        ColFund,       ///< fund intent sau GATE LVF / GATE-BLIND
        ColFlow,       ///< ngoại · tự doanh 20 phiên (tỷ)
        ColFlags,      ///< ⚠ cờ (đếm + tooltip liệt kê)
        ColCount
    };

    struct Filter {
        QString dm;        ///< "" | "NAV" | "WATCH" | "AVOID" | "DM" (NAV∪WATCH)
        QString state;     ///< "" | "A" | "B" | "C" | "D"
        bool deep_only = false;
        bool regen_only = false;
        bool flagged_only = false;
        QString search;    ///< ticker prefix (case-insensitive) or name substring
    };

    explicit DeepFaUniverseTable(QWidget* parent = nullptr);

    /// Load the raw `rows` array. Does not change filters; call apply() afterwards.
    void set_rows(const QJsonArray& rows);
    /// Filter + re-render.
    void apply(const Filter& f);

    int visible_count() const { return static_cast<int>(shown_.size()); }
    /// The rows currently shown (after filter), in display order — used by the CSV export.
    QJsonArray visible_rows() const;
    /// All tickers with names, for the toolbar completer ("FPT — FPT Corporation").
    QStringList completer_entries() const;

  signals:
    /// Double-click / Enter on a row, or single click on the ticker cell.
    void ticker_activated(const QString& ticker);
    void count_changed(int visible);

  protected:
    void keyPressEvent(QKeyEvent* event) override; ///< Enter/Return → ticker_activated

  private:
    void rebuild();
    void fill_row(int row, const QJsonObject& r);
    void update_headers(); ///< ▲/▼ on the sorted column
    void sort_by_column(int column);
    void activate_row(int row);
    static bool passes(const QJsonObject& r, const Filter& f);

    QJsonArray rows_;
    QVector<QJsonObject> shown_; ///< filtered + sorted rows, index = table row
    Filter filter_;
    int sort_col_ = ColDm;
    bool sort_asc_ = false;
};

} // namespace fincept::screens::deepfa
