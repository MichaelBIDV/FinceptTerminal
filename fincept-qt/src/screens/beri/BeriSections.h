// src/screens/beri/BeriSections.h
// Section builders of the BERI page. Each takes a slice of the `beri.py overview` payload (contract:
// scripts/beri.py module docstring) and returns ONE new widget owned by `parent`. Builders never
// return nullptr: a null / missing slice yields a muted "[CẦN DATA] …" line inside the section, so
// gaps stay visible. The page is rebuilt from scratch on every payload and on theme change, so the
// builders are stateless and read colours at call time (BeriCommon.h).
//
// Live half    — BeriSectionsLive.cpp:    masthead · alert · I lịch · II sổ lệch · III cam kết & mốc neo ·
//                                         IV việc đang mở · V sổ nguồn · VI kho & pipeline
// Charter half — BeriSectionsCharter.cpp: VII hiến chương · VIII tầng E · IX bộ máy 12 ghế ·
//                                         X quy trình & kết luận · XI dòng giá trị · footer
#pragma once

#include <QJsonObject>
#include <QWidget>

namespace fincept::screens::beri {

// ── Live (BeriSectionsLive.cpp) ──────────────────────────────────────────────

/// Masthead: council name, mandate (payload "mandate"), today, local-only notice, warnings (meta).
QWidget* build_masthead(const QJsonObject& mandate, const QJsonObject& meta, QWidget* parent);

/// Nearest-deadline strip (payload "alert").
QWidget* build_alert(const QJsonObject& alert, QWidget* parent);

/// I · Lịch sản phẩm — countdowns per rhythm group (payload "lich").
QWidget* build_calendar(const QJsonObject& lich, QWidget* parent);

/// II · Hai sổ lệch — số liệu (Kho §G) and vận hành (§7), cross-referenced (payload "so_lech").
QWidget* build_ledgers(const QJsonObject& so_lech, QWidget* parent);

/// III · Cam kết mới BC 14/9 + mốc neo văn bản (payload "cam_ket", "moc_neo").
QWidget* build_commitments(const QJsonObject& cam_ket, const QJsonObject& moc_neo, QWidget* parent);

/// IV · Việc đang mở (payload "viec_mo").
QWidget* build_open_work(const QJsonObject& viec_mo, QWidget* parent);

/// V · Sổ nguồn BERI (payload "so_nguon").
QWidget* build_registry(const QJsonObject& so_nguon, QWidget* parent);

/// VI · Tám tệp lõi, Kho số liệu và pipeline tin ngành (payload "kho", "pipeline").
QWidget* build_store(const QJsonObject& kho, const QJsonObject& pipeline, QWidget* parent);

// ── Charter (BeriSectionsCharter.cpp) ────────────────────────────────────────

/// VII · Hiến chương dữ liệu — bậc bằng chứng, quy tắc T4, sáu điều KHÔNG (payload "hien_chuong").
QWidget* build_charter(const QJsonObject& hien_chuong, QWidget* parent);

/// VIII · Tầng E — 18 ghế chuyên gia theo 6 khối (payload "tang_e").
QWidget* build_experts(const QJsonObject& tang_e, QWidget* parent);

/// IX · Bộ máy 12 ghế vận hành, tầng A–D (payload "bo_may").
QWidget* build_operating_seats(const QJsonObject& bo_may, QWidget* parent);

/// X · Quy trình 7 bước + bốn trạng thái kết luận (payload "quy_trinh", "ket_luan").
QWidget* build_process(const QJsonObject& quy_trinh, const QJsonObject& ket_luan, QWidget* parent);

/// XI · Bốn dòng giá trị (payload "gia_tri").
QWidget* build_value_lines(const QJsonObject& gia_tri, QWidget* parent);

/// Footer: the files this page was built from, with their age (meta.sources), and the local-only line.
QWidget* build_footer(const QJsonObject& meta, QWidget* parent);

} // namespace fincept::screens::beri
