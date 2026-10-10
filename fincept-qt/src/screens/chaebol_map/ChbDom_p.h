#pragma once
// ChbDom_p.h — Document::Impl (shared by ChbDom.cpp, ChbPaint.cpp, ChbGeom.cpp). Internal.
#include "screens/chaebol_map/ChbDom.h"
#include "screens/chaebol_map/ChbLayout_p.h"
#include "screens/chaebol_map/ChbState.h"

#include <QHash>
#include <QStringList>

#include <deque>
#include <functional>
#include <memory>

namespace fincept::screens::chb {

struct Document::Impl {
    // ---- sources
    std::shared_ptr<SrcTree> top;
    bool buildMode = false;                               ///< top is a shell (<body> + slot)
    QHash<QString, std::shared_ptr<SrcTree>> tabs, incs;
    std::function<QByteArray(const QString&)> tabLoader, incLoader;
    StateStore state;
    float vpW = 1600, vpH = 1000;

    // ---- render tree
    std::deque<RNode> arena;
    ResolveResult rr;
    bool resolveDirty = true;
    bool styleDirty = true;
    std::deque<ComputedStyle> styles;
    ComputedStyle htmlStyle, bodyStyle;
    RNode* rootNode = nullptr;                            ///< resolved root element ("0" in dumps)

    // ---- boxes
    std::deque<Box> boxes;
    Box* body = nullptr;                                  ///< root box (body; implicit in suite mode)
    bool bodyImplicit = true;
    std::vector<std::unique_ptr<ComputedStyle>> anonStyles;
    float layoutWidth = -1;
    bool laidOut = false;
    float docW = 0, docH = 0;
    QColor canvas = QColor(255, 255, 255);
    int gen = 0;

    // ---- scrolling
    float scrollY = 0;
    struct Region {
        Box* box = nullptr;
        float scrollX = 0;
    };
    std::vector<Region> regions;
    QHash<QString, float> regionScrollMemo;               ///< keep scrollX across re-layouts (by node order key)

    QStringList warnings;
    Timing timing;

    // ---- pipeline steps (ChbDom.cpp)
    const SrcTree* load_tree(const QString& kind, const QString& key);
    void do_resolve();
    void do_style();
    void build_boxes();
    void do_layout(float width);
    Box* new_box();
    ComputedStyle* new_anon_style(const ComputedStyle& parent, Display d);

    // ---- helpers
    QPointF sticky_offset(const Box* b) const;             ///< position:sticky offset (nearest scroll container)
    QPointF box_shift(const Box* b) const;                 ///< sticky + horizontal scroll offsets affecting b
    const Box* region_box_of(const Box* b, int* regionId) const;
};

/// Paint entry (ChbPaint.cpp).
void chb_paint_document(Document::Impl& d, QPainter& p, const QRectF& clip);
/// Overflow rectangles + scroll regions after layout (ChbPaint.cpp).
void chb_compute_overflow(Document::Impl& d);

} // namespace fincept::screens::chb
