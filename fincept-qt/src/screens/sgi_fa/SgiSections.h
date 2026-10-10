// src/screens/sgi_fa/SgiSections.h
// Section builders of the SGI FA page. Each takes slices of the `sgi_fa.py overview` payload
// (contract: scripts/sgi_fa.py module docstring) and returns ONE new widget owned by `parent`.
// Builders never throw and never return nullptr: a missing / empty slice yields a small muted
// "[CẦN DATA] …" note inside the section instead of hiding it — gaps must stay visible.
//
// The page is rebuilt from scratch on every successful fetch and on theme change, so builders
// are stateless and read colours at call time (SgiCommon.h).
//
// Top half    — SgiSectionsTop.cpp:    gate · verdict · cycles · machine · conditions · blocks · hhp
// Bottom half — SgiSectionsBottom.cpp: evidence · anchors · thresholds · portfolio · track · inversion · sources
#pragma once

#include <QJsonArray>
#include <QJsonObject>
#include <QWidget>

namespace fincept::screens::sgi {

// ── Top (SgiSectionsTop.cpp) ─────────────────────────────────────────────────

/// One-line CỔNG strip (payload "gate").
QWidget* build_gate(const QJsonObject& gate, QWidget* parent);

/// VERDICT card: regime word + chốt | action + cash current→proposed + equity vs floor |
/// composite scores (engine.to_hop) + bottom-condition count; below it the engine audit lines
/// (engine.kiem) and active overrides (engine.override). `issue` = payload "issue".
QWidget* build_verdict(const QJsonObject& issue, const QJsonObject& engine, QWidget* parent);

/// I · Ba khung chu kỳ (issue.chu_ky).
QWidget* build_cycles(const QJsonObject& chu_ky, QWidget* parent);

/// II · Cỗ máy Tiền↔Hàng (issue.co_may, issue.thu_tu_vo, issue.he_so_truyen_dan).
QWidget* build_machine(const QJsonObject& issue, QWidget* parent);

/// III · Bốn điều kiện xác nhận đáy (issue.dieu_kien_day + engine.day).
QWidget* build_conditions(const QJsonArray& dieu_kien_day, const QJsonObject& engine_day, QWidget* parent);

/// IV · Tám khối chỉ báo (issue.khoi + engine.khoi/engine.to_hop + issue.khoi_ghi_chu).
QWidget* build_blocks(const QJsonObject& issue, const QJsonObject& engine, QWidget* parent);

/// Đối chiếu khung HHP — ba chiếc đồng hồ (issue.doi_chieu_hhp). Small card.
QWidget* build_hhp_crosscheck(const QJsonObject& doi_chieu_hhp, QWidget* parent);

// ── Bottom (SgiSectionsBottom.cpp) ───────────────────────────────────────────

/// V · Bằng chứng: issue tiles + live tiles (payload live.tiles) + chart grid (payload "charts",
/// each rendered with langkinh::LkLineChart) + live breadth summary (live.do_rong).
QWidget* build_evidence(const QJsonObject& issue, const QJsonObject& live, const QJsonArray& charts, QWidget* parent);

/// VI · Neo lịch sử (payload "neo").
QWidget* build_anchors(const QJsonArray& neo, QWidget* parent);

/// VII · Ngưỡng đảo chiều (payload "nguong" — issue thresholds already merged with live checks).
QWidget* build_thresholds(const QJsonArray& nguong, QWidget* parent);

/// VIII · Hàm ý danh mục (issue.danh_muc). Always shows the not-advice line.
QWidget* build_portfolio(const QJsonObject& danh_muc, QWidget* parent);

/// IX · Track record của chính khung này (issue.track_record).
QWidget* build_track_record(const QJsonObject& track_record, QWidget* parent);

/// X · Nghịch đảo (issue.nghich_dao).
QWidget* build_inversion(const QJsonObject& nghich_dao, QWidget* parent);

/// Footer: sources by evidence tier (issue.nguon + meta.sources_live), warnings (issue.canh_bao +
/// meta.warnings), next-issue checklist (issue.can_kiem_ky_sau), disclaimer (issue.tuyen_bo).
QWidget* build_sources(const QJsonObject& meta, const QJsonObject& issue, QWidget* parent);

} // namespace fincept::screens::sgi
