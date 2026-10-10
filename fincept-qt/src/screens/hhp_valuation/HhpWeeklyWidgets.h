// src/screens/hhp_valuation/HhpWeeklyWidgets.h
// Painted widgets of the BẢN TUẦN view (the page's two SVG chart kinds, redrawn natively):
//   HhpBandStrip  — section 03 "dải giá σ" of one ticker: cheap2…rich2 price bands, fair line,
//                   price marker; a second row shows the SAME ticker's band and price today
//                   (live), on the same x-scale, so drift since the issue is visible at a glance.
//   HhpSigmaDist  — section 04 "Thước σ": one tick per ticker at its σ (min of σ P/E, σ P/B),
//                   zone backgrounds −∞…−2 floor · −2…−1 up · ±1 neutral · +1…+2 down · +2… ceil;
//                   portfolio ticks bold/gold and labelled; issue strip above, live strip below;
//                   hover shows "TK σ".
// Colours: HhpWeeklyCommon.h. Both widgets are read-only and size themselves (heightForWidth-free:
// fixed heights, width follows the layout).
#pragma once

#include <QString>
#include <QStringList>
#include <QVector>
#include <QWidget>

class QMouseEvent;
class QPaintEvent;

namespace fincept::screens::hhp::weekly {

/// One band set in đồng. NaN members are allowed (drawn as absent).
struct BandLevels {
    double cheap2 = 0, cheap1 = 0, fair = 0, rich1 = 0, rich2 = 0, price = 0;
    bool valid() const; ///< cheap2 < cheap1 < fair < rich1 < rich2, all finite
};

class HhpBandStrip : public QWidget {
    Q_OBJECT
  public:
    explicit HhpBandStrip(QWidget* parent = nullptr);

    /// `issue_tag` / `live_tag` = short row captions, e.g. "11/09" and "22/09".
    /// `live` == nullptr (or !live->valid()) → one row only. An invalid `issue` keeps its row as a
    /// "— dải không hợp lệ" line; a valid live row is still drawn, on its own x-scale.
    void set_bands(const BandLevels& issue, const QString& issue_tag, const BandLevels* live, const QString& live_tag);

    QSize sizeHint() const override;
    QSize minimumSizeHint() const override;

  protected:
    void paintEvent(QPaintEvent* event) override;

  private:
    BandLevels issue_;
    BandLevels live_;
    bool has_live_ = false;
    QString issue_tag_;
    QString live_tag_;
};

struct DistPoint {
    QString tk;
    double s = 0;      ///< σ
    bool mine = false; ///< portfolio ticker
};

class HhpSigmaDist : public QWidget {
    Q_OBJECT
  public:
    explicit HhpSigmaDist(QWidget* parent = nullptr);

    /// `live` may be empty (→ one strip). `labels` = tickers to name under their tick.
    void set_data(const QVector<DistPoint>& issue, const QString& issue_tag, const QVector<DistPoint>& live,
                  const QString& live_tag, const QStringList& labels);

    QSize sizeHint() const override;
    QSize minimumSizeHint() const override;

  protected:
    void paintEvent(QPaintEvent* event) override;
    void mouseMoveEvent(QMouseEvent* event) override; ///< tooltip: nearest tick within 4 px → "TK  −1,23σ"

  private:
    QVector<DistPoint> issue_;
    QVector<DistPoint> live_;
    QString issue_tag_;
    QString live_tag_;
    QStringList labels_;
};

} // namespace fincept::screens::hhp::weekly
