// src/screens/vnblocks/VnNavHint.h
// One-shot navigation hints between the Vietnamese research tabs. "nav.switch_screen" only carries a screen
// id, and the target screen may not exist yet (DockScreenRouter builds it lazily on the queued navigate), so
// an extra argument cannot travel with the event. Instead the sender leaves a hint keyed by the target tab id
// right before publishing, and the target panel takes (reads + clears) it on its next activate():
//   ALL-IN-ONE tile "MỞ CHAEBOL REFLEX ›": nav_hint::set("msn_reflex", "VIC"); publish("nav.switch_screen", ...)
//   MsnReflexPanel::activate():            const QString ma = nav_hint::take("msn_reflex");  // "" = no hint
// A newer set() for the same tab replaces the older hint; an empty value clears it.
//
// Rules for a consumer, so a hint never lands late or in the wrong place:
//   * Take it on show AND on "nav.switch_screen" to its own id: navigate() only raises a dock that is already
//     visible, so no QShowEvent follows. Queue that take behind WindowFrame's queued navigate.
//   * One hint per tab id, shared by every window and every "<id>#dup<N>" copy: only the instance in the dock
//     whose id is exactly <id> (the one navigate opens) takes it, and on the event only while it is visible.
// Rule for a sender: set a hint only for a tab that consumes it (today only "msn_reflex"). Nothing ever clears a
// hint for a tab without a consumer; it would sit in the store and fire if that tab adopted take() later.
//
// GUI thread only: the store is a plain function-local static with no locking. Header-only.
#pragma once

#include <QHash>
#include <QString>

namespace fincept::screens::nav_hint {

/// The pending hints, tab id → value. Use set()/take() rather than touching it directly.
inline QHash<QString, QString>& store() {
    static QHash<QString, QString> hints;
    return hints;
}

/// Leaves `value` for the tab `tab` to pick up on its next activation (empty `value` clears the hint).
inline void set(const QString& tab, const QString& value) {
    if (value.isEmpty())
        store().remove(tab);
    else
        store().insert(tab, value);
}

/// Returns and clears the hint left for `tab`; "" when there is none.
inline QString take(const QString& tab) {
    return store().take(tab);
}

} // namespace fincept::screens::nav_hint
