// src/screens/hdcv_launchpad/HlpPanels.h
// The component library of the Launchpad (panels.js `PANELS`, all 24 entries). The tab bar shows the
// three dashboards the Fincept tab reproduces — "Chứng khoán · Mã & Danh mục" (ck), "VĨ MÔ · 4 chủ thể"
// (vimo), "WIDATA · Tín hiệu" (widata) — and the "+ Component" sheet adds any of the 24 to a view.
// Each PanelDef mirrors one PANELS entry: name/desc/w/h/linked/title and a render function
// that returns the children of `.bd` (the shell wraps them in the 7px 9px padded scroll box) and sets
// the header `.asof` text through RenderCtx::asof.
//
// Render functions are pure given (data, ctx, state): the shell calls them again on ctx change
// (linked panels), theme toggle, data reload and whenever the panel asks via rc.rerender().
#pragma once

#include "screens/hdcv_launchpad/HlpData.h"
#include "screens/hdcv_launchpad/HlpDom.h"

#include <QDateTime>
#include <QString>
#include <QVariantMap>
#include <QVector>

#include <functional>

class QComboBox;
class QLineEdit;

namespace fincept::screens::hlp {

struct RenderCtx {
    const Data& data;
    QString ctx;                 ///< linked ticker (uppercase), e.g. "MSN"
    QString viewKey;             ///< "ck" | "vimo" | "widata" | saved "v<ms>" (WD_ST is keyed by view)
    QDateTime now;               ///< Date.now() for ages (wdAgo, tuổi…)
    QString* asof = nullptr;     ///< header `.asof` text (stamp())
    QVariantMap* state = nullptr;     ///< per panel INSTANCE, survives re-renders (chip key, filter text…)
    QVariantMap* viewState = nullptr; ///< per (view, panel id), survives theme toggles/re-layouts (WD_ST)
    std::function<void(const QString&)> setCtx;     ///< window.setCtx — re-renders every linked panel
    std::function<void()> rerender;                 ///< re-render THIS panel body, keep scroll
    /// Persistent embedded widgets owned by the panel instance (created on first call with that key,
    /// then returned as-is so text/focus survive re-renders). Style them like input.f / select.
    std::function<QLineEdit*(const QString& key)> lineEdit;
    std::function<QComboBox*(const QString& key)> combo;
    std::function<void(const QString& url)> openUrl; ///< safeUrl + QDesktopServices (http/https only)
};

struct PanelDef {
    QString id;       ///< PANELS key: "cong", "idx", "monitor", …
    QString name;     ///< C.name (add-component sheet card title)
    QString desc;     ///< C.desc (sheet card text)
    int w = 4;        ///< default width in grid columns (sheet adds with this)
    int h = 300;      ///< default body max-height px
    bool linked = false;
    std::function<QString(const QString& ctx)> title; ///< C.title(ctx) — shell uppercases (CSS)
    std::function<NodeP(RenderCtx&)> render;
};

/// Registry in panels.js order: all 24 PANELS entries (the sheet lists them all), each rendering
/// its web template.
const QVector<PanelDef>& panel_defs();
const PanelDef* panel_def(const QString& id);

// ---- render functions (one per PANELS entry) — implemented in HlpPanels_*.cpp ----
// HlpPanels_Ck.cpp
NodeP render_cong(RenderCtx& rc);     ///< CỔNG · Market Regime
NodeP render_idx(RenderCtx& rc);      ///< VN-INDEX · P/E · EX-VIN
NodeP render_monitor(RenderCtx& rc);  ///< MONITOR · VN200 (linked)
NodeP render_desc(RenderCtx& rc);     ///< <ctx> · MÔ TẢ (linked)
NodeP render_chart(RenderCtx& rc);    ///< <ctx> · VÙNG GIÁ σ (linked)
NodeP render_sigma(RenderCtx& rc);    ///< THƯỚC σ · <ctx> trên trục (linked)
// HlpPanels_Misc.cpp
NodeP render_news(RenderCtx& rc);     ///< TIN · THEO CHỦ ĐỀ (linked)
NodeP render_rasoat(RenderCtx& rc);   ///< RÀ SOÁT HẰNG NGÀY
NodeP render_alerts(RenderCtx& rc);   ///< CẢNH BÁO
NodeP render_songuon(RenderCtx& rc);  ///< SỔ NGUỒN
// HlpPanels_Vimo.cpp
NodeP render_dongho(RenderCtx& rc);   ///< CỔNG TIỀN · BA CHIẾC ĐỒNG HỒ
NodeP render_chinhphu(RenderCtx& rc); ///< CHÍNH PHỦ · KPI VĨ MÔ
NodeP render_fftma(RenderCtx& rc);    ///< FFT · PILLAR V
NodeP render_cpicanh(RenderCtx& rc);  ///< ⚠ CPI · TRỘN ĐỊNH NGHĨA
// HlpPanels_Sgi.cpp
NodeP render_sgitin(RenderCtx& rc);   ///< SGI CAPITAL — from the weekly "Trạm Quan Trắc Vĩ Mô" issue
// HlpPanels_Wd.cpp
NodeP render_wdsignal(RenderCtx& rc); ///< WIDATA · MARKET SIGNALS
// HlpPanels_Extra.cpp — not on the three dashboards; added from the "+ Component" sheet
NodeP render_sector(RenderCtx& rc);     ///< CHUYỂN ĐỘNG NGÀNH
NodeP render_bidv(RenderCtx& rc);       ///< ĐIỂM NGÀNH · GHTD ⚠ NỘI BỘ
NodeP render_flash(RenderCtx& rc);      ///< ỨNG VIÊN FLASHNOTE
NodeP render_reports(RenderCtx& rc);    ///< THƯ VIỆN BÁO CÁO
NodeP render_prov(RenderCtx& rc);       ///< NGUỒN · ĐỘ TƯƠI
// HlpPanels_Vietcap.cpp — idem
NodeP render_vietcapma(RenderCtx& rc);  ///< VIETCAP IQ · <ctx> trong bảng (linked)
NodeP render_vietcaptin(RenderCtx& rc); ///< CBTT · lọc <ctx> (linked)
NodeP render_xanhvo(RenderCtx& rc);     ///< ⚠ XANH VỎ ĐỎ LÒNG

} // namespace fincept::screens::hlp
