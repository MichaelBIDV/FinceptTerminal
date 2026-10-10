// src/screens/vnblocks/VnChartsExt.h
// Two extra chart kinds for the vnblocks/1 "bieu_do" card, selected by block["loai"] (absent = the usual
// time-series LkLineChart, so every existing page renders exactly as before):
//
//   "cot"  categorical bars  {"loai":"cot", "huong":"ngang"|"doc", "nhan":[cat..], "nhan_phu":[cat2..]?,
//                             "series":[{"name","y":[num|null..],"mau","mau_tung":[mau|null..]?}],
//                             "gia_tri":true?, "dv":"%"?, "so_le":1?, "dau":true?,
//                             "vach":[{"v","text","mau"}]?, "truc":{"label","min","max"}?}
//   "xy"   numeric x / y     {"loai":"xy", "truc_x":{"label","min","max"}, "truc_y":{...},
//                             "series":[{"name","kieu":"duong"|"net"|"diem","x":[..],"y":[..],"mau",
//                                        "nhan":[text|null..]?,"co":px?}],
//                             "vach_x"|"vach_y":[{"v","text","mau"}]?, "vung_x":[{"x0","x1","mau","alpha","text"}]?,
//                             "vung_y":[{"y0","y1","mau","alpha","text"}]?}
//
// Both are self-painted QWidgets (no QtCharts): theme colours come from the Lăng Kính roles at paint time,
// "mau" accepts the vnblocks keys (xanh vang do xam lam tim) or "#rrggbb". Hover shows the nearest
// bar/point. has_data() is false when nothing finite is drawable, so the card prints its [CẦN DATA] note.
#pragma once

#include <QJsonObject>
#include <QString>
#include <QVector>
#include <QWidget>

namespace fincept::screens::vnblocks {

/// True when `block` asks for one of the extra kinds ("cot" or "xy").
bool is_ext_chart(const QJsonObject& block);

/// Builds the extra chart for `block`; caller checks has_ext_chart_data() and owns/deletes the widget.
QWidget* make_ext_chart(const QJsonObject& block, QWidget* parent);
bool has_ext_chart_data(const QWidget* chart);

} // namespace fincept::screens::vnblocks
