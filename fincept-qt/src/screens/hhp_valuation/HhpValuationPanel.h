// src/screens/hhp_valuation/HhpValuationPanel.h
// ĐỊNH GIÁ HHP — VNINDEX · VN30 · VN100 valuation zones (phương pháp Huỳnh Hoàng Phương),
// built on the same chassis as the Fincept Macro module (EconPanelBase + EconomicsService
// running a Python script), rendered with native QtCharts widgets because this Qt kit has no
// QtWebEngine to embed the Cowork page.
//
// Sections, top to bottom (one scrollable content page):
//   1. Hội đồng Cố vấn AI verdict card (hdcv_verdict: stance · headline · reads · risks)
//   2. VNINDEX — price inside its P/E (or P/B) ±1σ/±2σ price bands + forward projection; ▲▼ keynotes at
//      peaks/troughs, ◆ sell-side targets and the 3-year dashed band forecast (payload `keynotes`/`forecast`);
//      [8 NĂM] (engine window, default) | [TOÀN SỬ 2000→] (+ LOG): price 28/07/2000→, long-window bands, sourced ◇
//      ratio points before the bands, both σ windows side by side (`hhp_valuation.py history`, fetched lazily)
//   3. Rổ VN30 / VN100 — the basket's own P/E (or P/B) vs its history (flat ±1σ/±2σ bands), keynotes and
//      the ratio "nếu giá đứng yên" along the forecast EPS path.
//      Simplification vs the page: the basket follows the toolbar metric (the page has its own
//      P/E|P/B toggle there), so VNINDEX, basket and screener always show the same ratio.
//   4. Non-VIC3 — index P/E and P/B with vs without VIC+VHM+VRE, and the Vin-group weight
//   5. Bộ lọc định giá — every constituent of the selected basket vs its own history
//      (zone chips · search · reliable-only · click a ticker → HhpTickerDialog)
//
// Toolbar: XEM [LIVE][BẢN TUẦN] · [VN30][VN100] universe · [P/E][P/B] metric · freshness ·
// BẢN WEB · FETCH · CSV. One `overview` fetch carries both universes, so switching VN30↔VN100 or
// P/E↔P/B is instant.
//
// BẢN TUẦN view (second content page, hhp::weekly::HhpWeeklyPage): the weekly issue
// hhp_weekly_YYYY-MM-DD.html read by scripts/hhp_weekly.py `weekly [ky]` — the issue verbatim
// plus the audit engine and live overlays. In that view the toolbar shows KỲ [issue combo]
// instead of the universe/metric pills, BẢN WEB opens the issue's HTML file and CSV exports the
// weekly screener. On the LIVE page, `hhp_weekly.py brief` (fetched with every overview) adds a
// banner linking to the latest issue and marks its portfolio / avoid tickers in the screener.
#pragma once

#include "screens/economics/panels/EconPanelBase.h"

#include <QDateTime>
#include <QJsonObject>
#include <QPointer>
#include <QString>
#include <QVector>

class QCheckBox;
class QComboBox;
class QFrame;
class QLabel;
class QLineEdit;
class QPushButton;
class QScrollArea;
class QStackedWidget;
class QTimer;
class QVBoxLayout;

namespace fincept::screens {

namespace hhp {
class HhpChart;
class HhpScreenerTable;
class HhpTickerDialog;
namespace weekly {
class HhpWeeklyPage;
} // namespace weekly
} // namespace hhp

class HhpValuationPanel : public EconPanelBase {
    Q_OBJECT
  public:
    explicit HhpValuationPanel(QWidget* parent = nullptr);

    /// Fetches when nothing is loaded yet or the last successful load is older than the refresh
    /// interval (the HHP pipeline rebuilds 3×/day); otherwise only re-evaluates the data age.
    /// Called on every show of the tab. FETCH always forces a refresh.
    void activate() override;

  protected:
    void build_controls(QHBoxLayout* thl) override;
    /// LIVE view: re-runs `hhp_valuation.py overview` + `hhp_weekly.py brief`; BẢN TUẦN view:
    /// re-runs `hhp_weekly.py weekly [ky]` (cache bypassed).
    void on_fetch() override;
    void on_result(const QString& request_id, const services::EconomicsResult& result) override;

  private:
    void build_content_page();
    void apply_overview(const QJsonObject& data);

    void set_universe(const QString& universe); ///< "VN30" | "VN100"
    void set_metric(const QString& metric);     ///< "pe" | "pb"
    void set_zone(const QString& zone_key);     ///< "" | "cheap" | "neutral" | "rich"
    void update_toggle_styles();

    void render_all();
    void render_meta();     ///< freshness label + footer
    void render_verdict();
    void render_index();
    void render_basket();
    void render_exvic3();
    void render_zone_chips();
    void apply_screener_filter();
    void update_count_and_height(); ///< count label + fixed table height (the page scrolls as one)

    void open_ticker(const QString& ticker);
    void export_screener_csv();
    void open_web_page();
    void on_refresh_tick(); ///< timer: re-evaluate data age; re-fetch when visible and due
    bool refresh_due() const;

    // ── BẢN TUẦN view ──
    void set_view(const QString& view); ///< "live" | "weekly" — swaps toolbar controls and content page
    void fetch_weekly();                ///< `hhp_weekly.py weekly [requested_ky_]`
    void fetch_brief();                 ///< `hhp_weekly.py brief` (banner + screener marks)
    void apply_weekly(const QJsonObject& data);
    void apply_brief(const QJsonObject& data);
    void populate_issue_combo();        ///< combo ← meta.issues of the weekly payload (newest first)
    void on_issue_selected(int index);
    void render_weekly_fresh();         ///< toolbar freshness label in the BẢN TUẦN view
    void export_weekly_csv();
    bool weekly_refresh_due() const;

    QJsonObject data_;     ///< last successful `overview` payload
    bool loaded_ = false;
    bool fetching_ = false;          ///< an `overview` request is in flight
    QDateTime fetched_at_;           ///< UTC time of the last successful `overview`
    QTimer* refresh_timer_ = nullptr;
    // Per-instance request ids: result_ready reaches every panel, and a duplicated HHP panel must
    // not take another instance's answer (or error) for its own.
    QString req_prefix_;   ///< "hhp_<n>_"
    QString req_overview_; ///< req_prefix_ + "overview"
    QString req_ticker_;   ///< req_prefix_ + "tk_" (+ ticker)
    QString universe_ = QStringLiteral("VN30");
    QString metric_ = QStringLiteral("pe");
    QString zone_key_;

    // toolbar
    QPushButton* btn_vn30_ = nullptr;
    QPushButton* btn_vn100_ = nullptr;
    QPushButton* btn_pe_ = nullptr;
    QPushButton* btn_pb_ = nullptr;
    QLabel* fresh_lbl_ = nullptr;
    QPushButton* web_btn_ = nullptr;

    // content page
    int page_idx_ = -1;
    QScrollArea* scroll_ = nullptr;
    QLabel* meta_lbl_ = nullptr;      ///< method + generated time (+ stale warning)
    QFrame* verdict_card_ = nullptr;
    QLabel* verdict_chip_ = nullptr;  ///< "🧠 brain | ⚙︎ deterministic · updated"
    QLabel* verdict_lbl_ = nullptr;   ///< rich text
    QLabel* index_title_ = nullptr;
    QLabel* index_stats_ = nullptr;
    hhp::HhpChart* index_chart_ = nullptr;
    QLabel* index_fc_note_ = nullptr;  ///< forecast basis per year + caveats + ▲▼◆ key (hidden without both)
    QLabel* basket_title_ = nullptr;
    QLabel* basket_stats_ = nullptr;
    hhp::HhpChart* basket_chart_ = nullptr;
    QLabel* basket_note_ = nullptr;
    QWidget* ex_section_ = nullptr;   ///< whole Non-VIC3 block, hidden when exvic3 is null
    QLabel* ex_stats_ = nullptr;
    hhp::HhpChart* ex_pe_chart_ = nullptr;
    hhp::HhpChart* ex_pb_chart_ = nullptr;
    hhp::HhpChart* ex_w3_chart_ = nullptr;
    QLabel* ex_note_ = nullptr;
    QLabel* screener_title_ = nullptr;
    QWidget* chips_row_ = nullptr;
    QVector<QPushButton*> chip_btns_; ///< zone chips: all · cheap · neutral · rich (kept, relabelled)
    QVector<QLabel*> chip_lbls_;      ///< rich-text label inside each chip (count coloured by zone)
    QLineEdit* search_edit_ = nullptr;
    QCheckBox* reliable_chk_ = nullptr;
    QLabel* count_lbl_ = nullptr;
    hhp::HhpScreenerTable* table_ = nullptr;
    QLabel* screener_msg_ = nullptr; ///< shown instead of the table when the basket member list is missing
    QLabel* foot_lbl_ = nullptr;
    QLabel* weekly_banner_ = nullptr; ///< LIVE page: "📰 BẢN TUẦN kỳ … → xem" link (hidden without an issue)

    // ── BẢN TUẦN view state ──
    QString view_ = QStringLiteral("live");
    QPushButton* btn_view_live_ = nullptr;
    QPushButton* btn_view_weekly_ = nullptr;
    QVector<QWidget*> live_ctrls_;         ///< toolbar widgets shown only in the LIVE view
    QVector<QWidget*> weekly_ctrls_;       ///< toolbar widgets shown only in the BẢN TUẦN view
    QComboBox* issue_combo_ = nullptr;
    QScrollArea* weekly_scroll_ = nullptr;
    hhp::weekly::HhpWeeklyPage* weekly_page_ = nullptr;
    int weekly_page_idx_ = -1;
    QJsonObject weekly_data_;              ///< last successful `weekly` payload
    bool weekly_loaded_ = false;
    bool weekly_fetching_ = false;
    QDateTime weekly_fetched_at_;
    QString req_weekly_;                   ///< id of the newest `weekly` request (prefix + "wk_" + ky|"latest")
    QString requested_ky_;                 ///< issue chosen in the combo ("" = newest, follows new issues)
    QString loaded_request_ky_;            ///< requested_ky_ of the payload on screen
    QString req_brief_;                    ///< req_prefix_ + "brief"
    QJsonObject brief_;                    ///< last successful `brief`

    QPointer<hhp::HhpTickerDialog> dialog_; ///< at most one ticker window; reused

    // ── VNINDEX TOÀN SỬ view (27/09): [8 NĂM] [TOÀN SỬ 2000→] [LOG] on the index card ──
    // 8 NĂM (default) = index_chart_, drawn exactly as before. TOÀN SỬ = a second HhpChart in the same card's stack,
    // created on first use and fed by `hhp_valuation.py history` (fetched lazily on first open, again on FETCH or when
    // the overview is newer). View + LOG are session state of this panel (the app always starts in 8 NĂM).
    void set_index_view(const QString& view); ///< "8y" | "full"
    void set_full_log(bool on);
    void fetch_history();                     ///< `hhp_valuation.py history` (force)
    void apply_history(const QJsonObject& data);
    void render_index_full();                 ///< title + stat rows + full chart + note lines (TOÀN SỬ only)
    void apply_full_notes();                  ///< keynotes (priority_full) + ◇ + ◆ thinned for the visible years
    void update_index_view_styles();
    QString index_view_ = QStringLiteral("8y");
    bool full_log_ = true;
    QJsonObject history_;                     ///< last successful `history` envelope {meta, history}
    bool history_loaded_ = false;
    bool history_fetching_ = false;
    QDateTime history_fetched_at_;            ///< UTC of the last successful `history`; invalid = re-fetch on next open
    QString req_history_;                     ///< req_prefix_ + "history"
    QString history_err_;                     ///< last failure (runner or script error); cleared by a success
    QStackedWidget* index_stack_ = nullptr;
    hhp::HhpChart* index_full_chart_ = nullptr; ///< lazily created (page 1 of index_stack_)
    QPushButton* btn_ix_8y_ = nullptr;
    QPushButton* btn_ix_full_ = nullptr;
    QPushButton* btn_ix_log_ = nullptr;
};

} // namespace fincept::screens
