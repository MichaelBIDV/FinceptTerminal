// src/screens/vnblocks/VnBlocks.h
// Generic page renderer for the Vietnamese research tabs whose Python script already shapes the whole
// page (tabs "msn_reflex" and "so_nguon"). Contract "vnblocks/1": the payload carries
//   "trang": {"sections": [ {"id", "so", "tieu_de", "eyebrow", "lede", "khoi": [block, ...]}, ... ]}
// and every block is one of the kinds below (full key list in scripts/msn_reflex.py docstring):
//   cong       gate strip          {"dong", "tier", "phu"}
//   doan       paragraph / note     {"text", "mau"?, "the"?: true (card with coloured left edge)}
//   o_so       tile grid            {"o": [{"nhan","gia_tri","phu","mau","tier","live"}], "cot"}
//   bang       table                {"cot": [..], "dong": [[cell..]..], "chu_thich", "can_phai": [col idx]}
//              cell = string | {"t", "mau", "pill", "mono", "dam", "tip"}
//   the        cards                {"the": [{"tieu_de","nhan":{"text","mau"},"text","mau_vien","tier"}], "cot"}
//   danh_sach  numbered list        {"muc": [{"so","tieu_de","text","tags":[tier..]}]}
//   trich      quote                {"text", "nguon"}
//   bieu_do    chart                {"tieu_de","chu_thich","nguon","tier","cao","block": {LkLineChart block}}
//   canh_bao   warning list         {"tieu_de", "muc": [..], "mau"}
//   chips      evidence chips       {"chips": [{"tier","text"}]}
// Colour keys ("mau"): xanh | vang | do | xam | lam (blue) | tim (violet) — anything else = ink.
// Consecutive "bieu_do" blocks in one section are laid out two per row; everything else is full width.
// Every data string is HTML-escaped before it reaches a rich-text label; unknown kinds render a muted
// "[khối lạ: <kieu>]" line instead of failing. Builders never return nullptr.
#pragma once

#include <QColor>
#include <QJsonArray>
#include <QJsonObject>
#include <QString>
#include <QWidget>

namespace fincept::screens::vnblocks {

/// Whole page: all sections of payload["trang"], stacked, inside one transparent container owned by `parent`.
QWidget* build_page(const QJsonObject& trang, QWidget* parent);

/// One section (header "<so>  <tieu_de>" + eyebrow + lede + its blocks).
QWidget* build_section(const QJsonObject& section, QWidget* parent);

/// One block of any kind listed above.
QWidget* build_block(const QJsonObject& block, QWidget* parent);

/// Colour for a "mau" key, resolved against the current theme at call time.
QColor colour(const QString& mau);

} // namespace fincept::screens::vnblocks
