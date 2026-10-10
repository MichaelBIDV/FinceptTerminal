// src/screens/hhp_valuation/HhpWeeklyScreener.h
// Section 07 of the weekly issue — "Bộ lọc VN200": the issue's frozen screener (194 rows,
// compact schema of hhp_weekly.py `snapshot.rows`) with the page's controls, plus one column the
// page cannot have: σ LIVE (snapshot.live) next to the issue's σ.
//
// Controls (own row, like the page): search · [P/E|P/B] · [Tất cả|VN30|VN100|Danh mục|Chỉ RẺ] ·
// "chỉ band đáng tin" (checked by default) · count "n / 194 mã".
// Columns: Mã (+VN30/V100 tag, "band lỏng") · Ratio · μ · Vị thế (painted σ gauge −3…+3) · σ ·
// σ live (→ arrow when the zone changed) · Giá · Giá TB · →TB · Fwd 26F (+V/S) · TP (+rating) ·
// Catalyst mới nhất. Sorting: click a sortable header (default σ ascending = cheapest first).
// Rows: mine → gold tint + gold ticker; avoid → ticker struck through in red. The widget caps its
// height (~620 px) and scrolls inside, like the page's max-height box.
#pragma once

#include <QJsonArray>
#include <QJsonObject>
#include <QSet>
#include <QString>
#include <QStringList>
#include <QVector>
#include <QWidget>

class QCheckBox;
class QLabel;
class QLineEdit;
class QPushButton;
class QTableWidget;

namespace fincept::screens::hhp::weekly {

class HhpWeeklyScreener : public QWidget {
    Q_OBJECT
  public:
    /// What the user set on the controls; HhpWeeklyPage carries it across a same-kỳ rebuild.
    struct State {
        QString metric = QStringLiteral("pe");
        QString filter = QStringLiteral("all");
        bool reliable_only = true;
        QString sort_key = QStringLiteral("sigma");
        int sort_dir = 1;
        QString search;
        bool search_focused = false; ///< the search box held its window's focus
    };

    explicit HhpWeeklyScreener(QWidget* parent = nullptr);

    /// @param rows      snapshot.rows (compact ROW schema)
    /// @param live      snapshot.live ({TK: {pe:[now,σ]|null, pb:[now,σ]|null, price}}) — may be empty
    /// @param mine      core.mine   @param avoid core.avoid
    /// @param as_of_txt snapshot.as_of_txt   @param live_as_of_txt snapshot.live_as_of_txt
    void set_data(const QJsonArray& rows, const QJsonObject& live, const QStringList& mine, const QStringList& avoid,
                  const QString& as_of_txt, const QString& live_as_of_txt);

    State state() const;
    /// Applies `s` (unknown metric / filter / sort keys are ignored) and refills the table; focus goes
    /// back to the search box on the next event-loop turn when `s.search_focused`.
    void restore_state(const State& s);

    /// Rows currently shown (after filter + sort) as display strings, for CSV export. Besides the
    /// table's columns: "Danh mục" ("danh mục" | "tránh" | "", as the contract csv) after Mã, and
    /// the full rating after TP.
    QStringList csv_header() const;
    QVector<QStringList> csv_rows() const;

  signals:
    /// Double-click / Enter on a row, or single click on the ticker cell.
    void ticker_activated(const QString& ticker);

  private:
    void rebuild(); ///< filter + sort + fill the table
    void restyle_segments();

    QJsonArray rows_;
    QJsonObject live_;
    QSet<QString> mine_;
    QSet<QString> avoid_;
    QString as_of_txt_;
    QString live_as_of_txt_;

    QString metric_ = QStringLiteral("pe");  ///< "pe" | "pb"
    QString filter_ = QStringLiteral("all"); ///< "all" | "30" | "100" | "mine" | "cheap"
    bool reliable_only_ = true;
    QString sort_key_ = QStringLiteral("sigma"); ///< t · now · mean · sigma · live · p · fair · up · fpe · tp
    int sort_dir_ = 1;                            ///< +1 ascending, −1 descending

    QLineEdit* search_ = nullptr;
    QVector<QPushButton*> metric_btns_; ///< P/E, P/B
    QVector<QPushButton*> filter_btns_; ///< Tất cả, VN30, VN100, Danh mục, Chỉ RẺ
    QCheckBox* reliable_ = nullptr;
    QLabel* count_ = nullptr;
    QTableWidget* table_ = nullptr;
    QLabel* foot_ = nullptr;
    QVector<QJsonObject> shown_; ///< filtered + sorted rows, index = table row
};

} // namespace fincept::screens::hhp::weekly
