#pragma once
// ChbState.h — interactive state + resolve for the chaebol_map engine (DESIGN.md §4), mirroring the Chrome
// oracle (harness/chaebol_map/oracle/render.js resolveNode/onClick/commit) so both render the same tree:
//  * state: string → string; missing key reads as "" ; compound key "a|b" = values joined by '|'
//  * if: every term matches (array = any of); evaluated before scope/grp/inc/slot
//  * scope: after each render, scoped keys (all `scope` keys of every loaded tree) not declared by any
//    rendered node go back to their default (or are removed) — no re-render
//  * inc / slot: placeholder replaced by the root of another tree (inc key / state.tab), lazily loaded
//  * count: text = fmt with {n} = number of rendered `grp` nodes (counted after `if`, anywhere in the tree)
//  * sort (tbody): stable sort of rendered children by child.sk[state[key]] — string×string localeCompare,
//    else Number(a) − Number(b) (missing = 0, NaN → 0), × (state[dir] == "desc" ? −1 : 1)
//  * on.set / on.sort click semantics, select bind.
#include "screens/chaebol_map/ChbNode.h"

#include <QHash>
#include <QSet>
#include <QString>

#include <deque>
#include <functional>

namespace fincept::screens::chb {

class StateStore {
  public:
    void set_defaults(const QHash<QString, QString>& d) { defaults_ = d; }
    const QHash<QString, QString>& defaults() const { return defaults_; }
    const QHash<QString, QString>& values() const { return values_; }
    QString get(const QString& k) const { return values_.value(k); }
    bool has(const QString& k) const { return values_.contains(k); }
    void set(const QString& k, const QString& v) { values_.insert(k, v); }
    void remove(const QString& k) { values_.remove(k); }
    void reset_to_defaults() { values_ = defaults_; }
    void merge(const QHash<QString, QString>& kv) {
        for (auto it = kv.begin(); it != kv.end(); ++it) values_.insert(it.key(), it.value());
    }
    /// Value of a (possibly compound "a|b") key.
    QString value_of(const QString& compoundKey) const;
    bool matches(const SrcCond& c) const; ///< condition test (no code evaluation)
    void add_scoped_keys(const QStringList& keys);
    const QSet<QString>& scoped_keys() const { return scoped_; }
    void clear_scoped_keys() { scoped_.clear(); }
    /// Oracle commit(): scoped keys not rendered → default / removed. Returns true if anything changed.
    bool reset_unrendered_scopes(const QSet<QString>& rendered);
    /// Oracle onClick(): on.set then on.sort.
    void apply_on(const SrcNode& n);

  private:
    QHash<QString, QString> defaults_, values_;
    QSet<QString> scoped_;
};

struct ResolveResult {
    RNode* root = nullptr;
    bool rootIsBody = false;          ///< top tree root is <body> (build mode)
    QSet<QString> renderedScopes;
    QHash<QString, int> grpCounts;
    QStringList warnings;
    int nodeCount = 0;
};

/// kind = "inc" (key = inc key) or "slot" (key = slot id; the loader reads state "tab").
using TreeLoader = std::function<const SrcTree*(const QString& kind, const QString& key)>;

/// Resolve `top` into arena-owned RNodes.
ResolveResult resolve_tree(const SrcTree& top, const StateStore& state, const TreeLoader& loader,
                           std::deque<RNode>& arena);

/// JS Number(v) for sort keys (strings trimmed, "" → 0, invalid → NaN).
double js_to_number(const JVal& v);

} // namespace fincept::screens::chb
