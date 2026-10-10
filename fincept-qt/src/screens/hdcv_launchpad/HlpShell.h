// src/screens/hdcv_launchpad/HlpShell.h
// The Launchpad chrome (index.html): top bar #bar, the 12-column #grid of panels (.pnl with .hd
// header + HlpView body), the "+ Component" sheet, view persistence, theme toggle, linked ticker.
// Behaviour follows index.html's script block 1:1 (boot/tabs/render/panel/setCtx/sheet/save/reset/
// theme/keyboard) — see SPEC §6.
//
// OWNERSHIP: the shell agent owns this file and may add PRIVATE members / internal classes, but
// must keep every PUBLIC declaration below unchanged (the harness and the screen use them).
#pragma once

#include "screens/hdcv_launchpad/HlpData.h"

#include <QImage>
#include <QString>
#include <QStringList>
#include <QWidget>

#include <memory>

namespace fincept::screens::hlp {

class Shell : public QWidget {
    Q_OBJECT
  public:
    explicit Shell(QWidget* parent = nullptr);
    ~Shell() override;

    /// First show: load data + saved state and build the view. Later shows: reload changed files.
    void activate();

    // ---- state (same model as the web: views{key:{name,panels:[{id,w,h}]}}, view, ctx, theme) ----
    QStringList viewKeys() const;          ///< in tab order
    QString currentView() const;
    void setView(const QString& key);      ///< tab click
    QString ctx() const;
    void setCtx(const QString& ticker);    ///< GO / Enter / row click — re-renders linked panels
    bool dark() const;
    void setDark(bool dark);               ///< ◐ — rebuilds everything, like render()
    void resetDefaults(bool askConfirm);   ///< "Mặc định"
    /// Settings file (JSON, same shape as the web localStorage value). Tests point it elsewhere.
    void setStatePath(const QString& path);

    // ---- harness hooks ----
    /// Render the current view with the grid NOT scrolling (every panel at its full CSS height, like
    /// the Chrome "unrolled" capture) and return the image, width = current width.
    QImage grabUnrolled();
    /// JSON array of panels: {title, rect:[x,y,w,h], hd:[…], bd:[…], asof, text, nodes:[…]} in
    /// window coordinates of the unrolled layout — same shape as ref/*_dump.json.
    QString dumpGeometryJson();
    /// Data store (harness can inject a system dir via HDCV_SYSTEM_DIR before activate()).
    DataStore* store() const;

  protected:
    void keyPressEvent(QKeyEvent* e) override;
    void resizeEvent(QResizeEvent* e) override;

  private:
    struct Impl;
    std::unique_ptr<Impl> d_;
};

} // namespace fincept::screens::hlp
