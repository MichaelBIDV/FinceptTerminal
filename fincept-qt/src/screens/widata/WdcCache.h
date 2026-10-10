#pragma once
// WdcCache.h: disk cache of the chart images of WdcRenderService (DESIGN §16 C18), gói UI (đợt 3).
//
// Painting a few dense daily charts costs seconds (package C, measured 04/10: "US_Lợi suất TPCP" 10 s, "Lợi suất trái
// phiếu" 1.2 s), so the images survive the session: one file per render key under
// $WDC_RENDER_CACHE (value "off" disables) or <AppCacheLocation>/widata_render. The key covers the data build (directory
// + generated time, set by the view), the card, X window, visible series, sizes, sub-pixel offsets, DPR and the running
// binary (size + mtime): a new build or a rebuilt app never reuses an old image. Every function touches the disk and
// runs on the render threads only (TASKS E: no disk I/O on the UI thread); reads and writes go through
// readFileCounted / writeFileCounted of WdcData.h so the harness can prove it.
#include <QByteArray>
#include <QImage>
#include <QString>

#include <vector>

namespace fincept::screens::wdc {

struct DiskRender {
    std::vector<QImage> images;   // per pane, null for a pane without numbers
    double paintMs = 0;           // what painting them cost when they were made
};

QString renderCacheDir();                                       // empty when disabled
QByteArray engineStamp();                                       // binary path, size and mtime (computed once)
/// File name stem for a render key (sha1 of tag, engine stamp and the key).
QByteArray diskRenderKey(const QByteArray& tag, const QByteArray& key);
bool loadDiskRender(const QByteArray& diskKey, int panes, DiskRender* out);
bool storeDiskRender(const QByteArray& diskKey, const DiskRender& r);
/// Deletes the least recently written files until the directory holds at most maxBytes.
void trimDiskCache(qint64 maxBytes);

} // namespace fincept::screens::wdc
