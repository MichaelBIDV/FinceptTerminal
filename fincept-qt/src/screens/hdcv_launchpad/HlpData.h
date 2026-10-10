// src/screens/hdcv_launchpad/HlpData.h
// The exact files the web Launchpad reads — nothing else, so the tab shows the same numbers:
//   launchpad/data/launchpad_data.json  (D — built 3×/day by build_launchpad.py, LaunchAgent)
//   launchpad/data/vimo.json            (dongho, chinhphu, fftma — build_vimo.py)
//   launchpad/data/tien.json            (cpicanh — build_tien.py)
//   launchpad/data/wdsignal.json        (wdsignal — build_wdsignal.py, re-read every 5′ like the web)
//   launchpad/alerts_state.json         (alerts — launchpad_alert.py)
// plus, for the SGI Capital panel ONLY (user decision 27/09/2026), the newest weekly issue of the
// Cowork routine "Trạm Quan Trắc Vĩ Mô — bản tuần" (artifact K54Wp2BnWtaqPz6BNmd6am) as extracted to
//   knowledge_os/sgi_ky/YYYY-MM-DD.json  (schema sgi_ky/1, same file the SGI FA tab reads).
// Root = $HDCV_SYSTEM_DIR or ~/SECOND BRAIN-OBSIDIAN/_System. Read-only; never writes there.
#pragma once

#include <QDateTime>
#include <QHash>
#include <QJsonObject>
#include <QObject>
#include <QString>

namespace fincept::screens::hlp {

struct Data {
    // parsed files (empty object when missing / unparsable; *Ok tells which)
    QJsonObject D;        bool dOk = false;      QString dErr;
    QJsonObject vimo;     bool vimoOk = false;
    QJsonObject tien;     bool tienOk = false;
    QJsonObject wd;       bool wdOk = false;
    QJsonObject alerts;   bool alertsOk = false;
    QJsonObject sgi;      bool sgiOk = false;    QString sgiFile; ///< newest sgi_ky/*.json by name
    // Vietcap IQ components (panels.js fetch '../fincept_bridge/data/…' relative to launchpad/):
    QJsonObject vcMa;     bool vcMaOk = false;   ///< fincept_bridge/data/vietcap_ma.json  (key "vcma")
    QJsonObject vcTin;    bool vcTinOk = false;  ///< fincept_bridge/data/vietcap_tin.json (key "vctin")
    QString systemDir;
};

/// Loads the files, remembers their mtimes, and reloads only what changed (poll from the screen's
/// timer; the web has no push either). Parsing is synchronous: all files together are < 1.5 MB.
class DataStore : public QObject {
    Q_OBJECT
  public:
    explicit DataStore(QObject* parent = nullptr);

    static QString defaultSystemDir();
    const Data& data() const { return data_; }

    /// Load everything (first open). Returns false only if launchpad_data.json is unusable — the
    /// screen then shows the web's single warning panel.
    bool loadAll();
    /// Re-read files whose mtime changed. Returns the set of changed keys
    /// ("D","vimo","tien","wd","alerts","sgi"); empty = nothing to do.
    /// Also "vcma" / "vctin" (Vietcap IQ files of the vietcapma / vietcaptin components).
    QStringList reloadChanged();

  signals:
    void changed(const QStringList& keys);

  private:
    bool loadOne(const QString& key);
    QString pathFor(const QString& key) const;
    Data data_;
    QHash<QString, QDateTime> mtimes_;
};

} // namespace fincept::screens::hlp
