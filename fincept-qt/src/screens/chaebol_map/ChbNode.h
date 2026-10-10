#pragma once
// ChbNode.h — source nodes (parsed JSON, immutable) and resolved nodes (after if/inc/slot/count/sort)
// for the chaebol_map engine. Shared by ChbState (resolve), ChbDom (style/layout/paint) and ChbSvg.
#include "screens/chaebol_map/ChbJson.h"
#include "screens/chaebol_map/ChbStyle.h"

#include <QString>
#include <QStringList>

#include <memory>
#include <utility>
#include <vector>

namespace fincept::screens::chb {

/// `"if": {"k": "v" | ["v1","v2"], "a|b": "x|y"}` — every term must match.
struct SrcCond {
    std::vector<std::pair<QString, QStringList>> terms;
    bool empty() const { return terms.empty(); }
};

struct SrcVar {
    SrcCond cond;
    std::vector<DeclListPtr> decls; ///< classes (c) then s
};

struct SrcNode {
    bool isText = false;
    QString text;                ///< text node
    bool hasTag = false;         ///< "t" present
    QString tagName;             ///< "t" as written ("?" when absent)
    Tag tag = Tag::Unknown;
    bool knownHtml = false;      ///< tag in the oracle's HTML set (else rendered as "[t lạ: …]" outside SVG)
    std::vector<DeclListPtr> decls; ///< c (in order) then s
    std::vector<SrcVar> vars;
    bool hasCond = false;
    SrcCond cond;
    bool hasKey = false;
    QString key;
    bool hasInc = false;
    QString inc;
    QString slotId;
    QStringList scope;
    bool hasGrp = false;
    QString grp;
    bool hasCount = false;
    QString countGrp, countFmt;
    bool hasSort = false;
    QString sortKey, sortDir;
    JVal sk;                     ///< sort keys object (string/number values)
    QString bind;                ///< select → state key
    bool hasOnSet = false;
    std::vector<std::pair<QString, QString>> onSet;
    bool hasOnSort = false;
    QString onSortKey, onSortDir, onSortCol;
    bool hasHref = false;
    QString href;
    std::vector<std::pair<QString, QString>> attrs; ///< "a" members as JS strings (bools: "" / skipped)
    std::vector<SrcNode> kids;

    const QString* attr(QStringView name) const {
        for (const auto& kv : attrs)
            if (kv.first == name) return &kv.second;
        return nullptr;
    }
};

/// One JSON tree file: {"cls": {...}, "root": node}.
struct SrcTree {
    QString name;
    SrcNode root;
    bool ok = false;
    QString error;
    QStringList warnings;        ///< unknown classes etc.
    QStringList scopedKeys;      ///< every key appearing in a `scope` (oracle registerTree)
};

/// Parse a tree file. On malformed JSON returns a tree with ok=false and a Vietnamese error.
std::shared_ptr<SrcTree> parse_tree(const QByteArray& json, const QString& name);
std::shared_ptr<SrcTree> parse_tree_value(const JVal& obj, const QString& name);

struct Box;
struct ComputedStyle;

/// Resolved node (one render). Arena-owned by the Document; pointers valid until the next resolve.
struct RNode {
    const SrcNode* src = nullptr;          ///< element/text source (nullptr for count text / unknown label)
    const SrcNode* sortSrc = nullptr;      ///< the child JSON node used for `sk` lookups (placeholder of inc)
    bool isText = false;
    QString text;
    Tag tag = Tag::Unknown;
    bool isLink = false;                   ///< <a> with href
    std::vector<const DeclList*> decls;    ///< active style lists in order
    RNode* parent = nullptr;
    std::vector<RNode*> kids;
    int index = 0;                         ///< position among parent's kids (dump path)
    bool inSvg = false;                    ///< inside an <svg> subtree (SVG namespace)
    ComputedStyle* style = nullptr;        ///< set by the style pass (nullptr for text: uses parent's)
    Box* box = nullptr;                    ///< set by the box builder (nullptr when display:none/SVG child)
    int order = 0;                         ///< document order (pre-order index)

    const ComputedStyle* effectiveStyle() const { return style ? style : (parent ? parent->style : nullptr); }
};

} // namespace fincept::screens::chb
