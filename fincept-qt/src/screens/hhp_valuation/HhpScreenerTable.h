// src/screens/hhp_valuation/HhpScreenerTable.h
// "Bộ lọc định giá" — one row per VN30/VN100 constituent: where the ticker's P/E (or P/B)
// sits versus ITS OWN history (μ ± 1σ/2σ), the price bands that implies, broker catalyst and
// forward 2026F multiple. Mirrors the screener table of hhp_vn100_valuation.html.
//
// Rows are the `rows` array of `hhp_valuation.py overview` (see that script's docstring for
// the exact schema). Filtering (universe / zone / search / reliable-only) and sorting are
// done in place — no re-fetch.
#pragma once

#include <QHash>
#include <QJsonArray>
#include <QJsonObject>
#include <QSet>
#include <QString>
#include <QTableWidget>
#include <QVector>

class QKeyEvent;

namespace fincept::screens::hhp {

class HhpScreenerTable : public QTableWidget {
    Q_OBJECT
  public:
    enum Column {
        ColTicker = 0, ///< "Mã" (+ "·30" marker when the universe is VN100 and the ticker is also in VN30)
        ColNow,        ///< current P/E or P/B
        ColMean,       ///< historical mean of that ratio
        ColGauge,      ///< painted gauge: cheap2…cheap1 green, neutral grey, rich1…rich2 red, marker = price
        ColSigma,      ///< σ position, coloured by zone, "⚠" when the band is unreliable
        ColZone,       ///< RẺ / TRUNG TÍNH / ĐẮT ("CŨ" when the ratio is stale upstream)
        ColPrice,      ///< price now (đồng, Vietcap; source/date in the tooltip, red when a stale fallback)
        ColFair,       ///< band_fair price (đồng)
        ColUpside,     ///< upside_to_fair_pct
        ColRec,        ///< HSC recommendation (fa_rec)
        ColFwd,        ///< forward 2026F P/E or P/B (+ source V/S)
        ColCapiq,      ///< S&P CapIQ consensus "TP · rec" (row.capiq), sorted by capiq.upside_pct
        ColCatalyst,   ///< broker catalyst: rec · upside · revisions · latest title (last: stretches)
        ColCount
    };

    explicit HhpScreenerTable(QWidget* parent = nullptr);

    /// Load the raw `rows` array. Does not change filters; call apply() afterwards.
    void set_rows(const QJsonArray& rows);

    /// Ticker marks from the latest weekly issue (`hhp_weekly.py brief`): `mine` = portfolio
    /// (ticker shown "◆ TK"), `avoid` = avoid list (ticker struck through in red), `notes` = extra
    /// tooltip line per ticker (advisor verdict), `source` = e.g. "bản tuần 14/09". Re-renders.
    void set_marks(const QSet<QString>& mine, const QSet<QString>& avoid, const QHash<QString, QString>& notes,
                   const QString& source);

    /// Filter + re-render.
    /// @param universe       "VN30" | "VN100" (row flags in_vn30 / in_vn100)
    /// @param metric         "pe" | "pb" — which ratio block drives the numeric columns
    /// @param zone_key       "" (all) | "cheap" | "neutral" | "rich" (a stale ratio matches no zone)
    /// @param search         case-insensitive ticker substring ("" = no filter)
    /// @param reliable_only  hide rows whose band is flagged unreliable
    /// Rows with no block for `metric` are hidden (same as the Cowork page).
    void apply(const QString& universe, const QString& metric, const QString& zone_key, const QString& search,
               bool reliable_only);

    int visible_count() const { return visible_count_; }

    /// The rows currently shown (after filter), in display order — used by the CSV export.
    QJsonArray visible_rows() const;

  signals:
    /// Double-click / Enter on a row, or single click on the ticker cell.
    void ticker_activated(const QString& ticker);
    void count_changed(int visible);

  private:
    void rebuild();
    void open_links_menu(const QPoint& pos); ///< context menu: VietCap IQ / MiQuant / Simplize

    void keyPressEvent(QKeyEvent* event) override; ///< Enter/Return → ticker_activated
    void fill_row(int row, const QJsonObject& r);
    void update_headers();                         ///< metric label + ▲/▼ on the sorted column
    void sort_by_column(int column);
    void activate_row(int row);

    QJsonArray rows_;
    QVector<QJsonObject> shown_; ///< filtered + sorted rows, index = table row
    QSet<QString> mark_mine_;
    QSet<QString> mark_avoid_;
    QHash<QString, QString> mark_notes_;
    QString mark_source_;
    QString universe_ = QStringLiteral("VN30");
    QString metric_ = QStringLiteral("pe");
    QString zone_key_;
    QString search_;
    bool reliable_only_ = false;
    int visible_count_ = 0;
    QString sort_key_ = QStringLiteral("sigma"); ///< default: cheapest (lowest σ) first
    int sort_col_ = ColSigma;
    bool sort_asc_ = true;
};

} // namespace fincept::screens::hhp
