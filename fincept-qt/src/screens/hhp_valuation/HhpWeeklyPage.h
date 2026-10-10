// src/screens/hhp_valuation/HhpWeeklyPage.h
// BẢN TUẦN view of the ĐỊNH GIÁ HHP tab: the weekly issue "Ba chiếc đồng hồ của thị trường…"
// (hhp_weekly_YYYY-MM-DD.html) re-rendered natively from `hhp_weekly.py weekly [ky]`
// (contract: that script's docstring), with the audit engine and live overlays on top.
//
// Layout, top to bottom (one widget; the panel puts it in a QScrollArea):
//   meta line (kỳ · rev · định giá chốt · age / stale warning · warnings)
//   masthead card (kicker · title · lede · evidence chips · the issue's own status paragraph)
//   stat tiles (issue value + "live dd/mm: …" line under each mapped tile)
//   KIỂM BẢN TUẦN card (engine.kiem ✓/✗/• lines · drift table · tickers table · levels · past)
//   section nav (one small button per section id → section_requested)
//   sections: header "00A  title  eyebrow" + blocks (contract BLOCK types; "screener" →
//             HhpWeeklyScreener, "band" → HhpBandStrip, "dist" → HhpSigmaDist, "advisor" → card)
//   footer blocks + fixed not-advice line.
// The whole content is rebuilt by set_payload(); nothing keeps state between payloads except the
// widget itself and, when the new payload has the same meta.ky, the screener's controls
// (HhpWeeklyScreener::State).
#pragma once

#include <QJsonObject>
#include <QPointer>
#include <QString>
#include <QStringList>
#include <QVector>
#include <QWidget>

class QVBoxLayout;

namespace fincept::screens::hhp::weekly {

class HhpWeeklyScreener;

class HhpWeeklyPage : public QWidget {
    Q_OBJECT
  public:
    explicit HhpWeeklyPage(QWidget* parent = nullptr);

    /// Drops the previous content and builds everything from a `weekly` payload. Same meta.ky as the
    /// previous payload (the panel's timed refresh) → the new screener gets the old one's State.
    void set_payload(const QJsonObject& payload);

    /// CSV of the weekly screener as currently filtered (empty when there is none).
    QStringList csv_header() const;
    QVector<QStringList> csv_rows() const;

  signals:
    /// Section nav button clicked: the panel scrolls so `target` is at the top.
    void section_requested(QWidget* target);
    /// A ticker was activated (screener row, advisor header) → panel opens HhpTickerDialog.
    void ticker_activated(const QString& ticker);

  private:
    QVBoxLayout* root_ = nullptr;
    QWidget* body_ = nullptr; ///< everything built from the payload; replaced on set_payload()
    QPointer<HhpWeeklyScreener> screener_;
    QString ky_; ///< meta.ky of the current payload
};

} // namespace fincept::screens::hhp::weekly
