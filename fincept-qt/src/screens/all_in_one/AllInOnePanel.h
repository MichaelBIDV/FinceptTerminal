// src/screens/all_in_one/AllInOnePanel.h
// ALL-IN-ONE: one workspace per VN200 / Chaebol MAP ticker that gathers what the other Vietnamese research tabs already
// know about it (Vietcap IQ, Định giá HHP, Lăng kính FFT, DEEP FA, Chaebol map cổ đông, P/E×LS TV, HSC/BBG
// research, Chaebol Reflex, Sổ nguồn) into a bento grid of tiles. Nothing is computed here: scripts/all_in_one.py
// reads each module's own state files (read-only) and shapes contract "aio/1":
//   meta   {ma, ro, ten, generated, data_to, warnings[], ds_ma[{ma, ten, ro}]}
//   bang   {nhom: [{nhan, ma: [chip]}]}   chip = {ma, ten, gia, pct, mau, live, ngay, nguon, truoc_gdkhq}
//          live=false: price is the last Vietcap close (HNX/UPCOM not on the vnstore board) → muted, dashed chip
//   cong   vnblocks "cong" block (market gate line)
//   o      [{id, tieu_de, eyebrow, cot (1-12 column span), tab, tab_nhan, tier, trang_thai, ghi_chu, khoi[]}]
//          khoi = vnblocks/1 blocks (rendered by vnblocks::build_block); trang_thai = du | cu | thieu
//   csv    {columns, rows}
// Tiles flow left→right in a 12-column grid; under kAioNarrowPx every tile takes the full width. The tile's
// "MỞ <tab> ›" button switches to the source tab through the EventBus ("nav.switch_screen").
// Toolbar: VN30 · VN100 · VN200 · CHAEBOL MAP (board scope) · MÃ (prefix-suggest box) · BẢNG · freshness ·
// FETCH · CSV.
#pragma once

#include "screens/economics/panels/EconPanelBase.h"

#include <QDateTime>
#include <QJsonArray>
#include <QJsonObject>
#include <QList>
#include <QSet>
#include <QString>

class QCompleter;
class QEvent;
class QLabel;
class QLineEdit;
class QPushButton;
class QScrollArea;
class QStandardItemModel;
class QTimer;
class QWidget;

namespace fincept::screens {

class AllInOnePanel : public EconPanelBase {
    Q_OBJECT
  public:
    explicit AllInOnePanel(QWidget* parent = nullptr);

    /// Fetches when nothing is loaded yet or the last load is older than the refresh interval.
    void activate() override;

  protected:
    void build_controls(QHBoxLayout* thl) override;
    void on_fetch() override; ///< `all_in_one.py bang --ro VN30` or `ma --ma <MÃ>`
    void on_result(const QString& request_id, const services::EconomicsResult& result) override;
    void refresh_panel_theme() override;
    bool eventFilter(QObject* obj, QEvent* event) override;

  private:
    void apply_payload(const QJsonObject& data);
    void fill_tickers(const QJsonArray& ds_ma);
    void on_ma_entered(const QString& text);
    void open_board(const QString& ro);
    void rebuild_page(bool keep_scroll);
    QWidget* build_page();
    QWidget* build_board(QWidget* parent);
    QWidget* build_grid(QWidget* parent);
    QWidget* build_tile(const QJsonObject& o, QWidget* parent);

    void render_fresh();
    void restyle_toolbar();
    void update_ma_style();
    void export_payload_csv();

    QJsonObject data_;
    bool loaded_ = false;
    bool fetching_ = false;
    bool narrow_ = false;
    bool refetch_pending_ = false; ///< a newer page was asked while a fetch was in flight (latest wins)
    int board_per_row_ = 0;        ///< chips per row the board was built with
    QDateTime fetched_at_;
    QString ro_ = QStringLiteral("VN30"); ///< board scope: VN30 | VN100 | VN200 | CHAEBOL
    QString ma_;       ///< ticker requested ("" = board page)
    QString shown_ma_; ///< ticker of the page on screen
    QString req_prefix_;
    QString req_current_;
    int req_seq_ = 0;

    // toolbar
    QLineEdit* ma_edit_ = nullptr;
    QCompleter* ma_completer_ = nullptr;
    QStandardItemModel* ma_model_ = nullptr;
    QSet<QString> ds_ma_;
    bool ma_invalid_ = false;
    QPushButton* board_btn_ = nullptr;
    QList<QPushButton*> ro_btns_; ///< VN30 · VN100 · VN200 · CHAEBOL MAP (property "aio_ro" = code)
    QLabel* fresh_lbl_ = nullptr;

    // content page
    int page_idx_ = -1;
    QScrollArea* scroll_ = nullptr;
    QTimer* relayout_timer_ = nullptr; ///< resize debounce → rebuild only when narrow mode / chips per row change
};

} // namespace fincept::screens
