// src/screens/deepfa/DeepFaSections.h
// Section builders of the DEEP FA ticker page. Each takes slices of the `deepfa.py ticker <TK>`
// payload (contract: fincept_bridge/DEEPFA_MODULE_SPEC.md §4.3) and returns ONE new widget owned by
// `parent`. Builders never throw and never return nullptr: a missing / empty slice yields a small
// muted "[CẦN DATA] …" note inside the section instead of hiding it — gaps must stay visible.
//
// The page is rebuilt from scratch on every successful fetch and on theme change, so builders are
// stateless and read colours at call time (DeepFaCommon.h). Every data string is escaped before it
// reaches a rich-text QLabel; memo prose arrives as pre-rendered simple HTML ("*_html") from Python.
//
// Order on the page (spec Q1): cong · header · thesis · conditions · tension · chu_the (Top.cpp) ·
// dinh_gia · filing · codex · kg · ledger · phu_luc (Bottom.cpp).
#pragma once

#include <QJsonObject>
#include <QWidget>

namespace fincept::screens::deepfa {

// ── Top (DeepFaSectionsTop.cpp) ──────────────────────────────────────────────

/// CỔNG v1.7 banner (payload "cong"): always the first widget, never collapsible.
QWidget* build_cong(const QJsonObject& cong, QWidget* parent);

/// Header band: mã · tên · rổ · DM · giá bảng+ngày · Δ memo (CA) · State · tuổi memo/bậc · engine ·
/// regen · σ · EDI · TP · fund gate · KG chip (payload "meta" + "header").
QWidget* build_header(const QJsonObject& meta, const QJsonObject& header, QWidget* parent);

/// §1 Thesis (memo prose) + "Điểm gãy" card with CA-rebased price levels (payload "thesis").
QWidget* build_thesis(const QJsonObject& thesis, QWidget* parent);

/// §7 Checklist sống: đúng / gãy / lịch as a 6-column grid (payload "dieu_kien").
QWidget* build_conditions(const QJsonObject& dieu_kien, QWidget* parent);

/// §2 TENSION: memo streams (🧭 dates) ⚔ live matrix + drift + street votes + BLĐ gate + prose.
QWidget* build_tension(const QJsonObject& tension, QWidget* parent);

/// Chủ thể & dòng tiền (payload "chu_the").
QWidget* build_chu_the(const QJsonObject& chu_the, QWidget* parent);

// ── Bottom (DeepFaSectionsBottom.cpp) ────────────────────────────────────────

/// §6 Định giá: σ tiles (dated) · HHP band chart (hhp::HhpChart) · TP strip · prose (payload "dinh_gia").
QWidget* build_dinh_gia(const QJsonObject& dinh_gia, QWidget* parent);

/// §4 Filing teardown: worksheet 10 groups · read list (open PDF) · doc gaps · inventory (payload "filing").
QWidget* build_filing(const QJsonObject& filing, QWidget* parent);

/// §3 Codex + EDI memo vs live + §5 Board (collapsed) (payload "codex").
QWidget* build_codex(const QJsonObject& codex, QWidget* parent);

/// Đồ thị tri thức — 1-step neighbourhood grouped by node type (payload "kg").
QWidget* build_kg(const QJsonObject& kg, QWidget* parent);

/// Ledger alpha spine for this ticker, labelled by its real nature (payload "ledger").
QWidget* build_ledger(const QJsonObject& ledger, QWidget* parent);

/// Appendix: catalyst / news after memo · sources freshness · rigor 6D proxy · registry gaps · regen.
QWidget* build_phu_luc(const QJsonObject& phu_luc, const QJsonObject& meta, QWidget* parent);

} // namespace fincept::screens::deepfa
