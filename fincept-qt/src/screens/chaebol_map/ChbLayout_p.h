#pragma once
// ChbLayout_p.h — internal layout API shared by ChbLayout*.cpp (block/inline/flex/grid/table/absolute).
#include "screens/chaebol_map/ChbBox_p.h"

#include <QStringList>

#include <algorithm>
#include <limits>

namespace fincept::screens::chb {

constexpr float kInf = std::numeric_limits<float>::infinity();

/// Collapsing-margin accumulator (CSS 2.1 §8.3.1).
struct MarginStrut {
    float pos = 0, neg = 0;
    void add(float m) {
        if (m > 0) pos = std::max(pos, m);
        else neg = std::min(neg, m);
    }
    void merge(const MarginStrut& o) {
        pos = std::max(pos, o.pos);
        neg = std::min(neg, o.neg);
    }
    float sum() const { return pos + neg; }
};

/// Margins passing through a block box (parent/child collapsing).
struct BlockOut {
    MarginStrut top, bottom;
    MarginStrut ownTop;          ///< self-collapsing box: the top strut before its bottom margin joined (positioning)
    bool selfCollapsing = false;
};

struct LayoutCtx {
    StyleEnv env;
    float icbW = 1600, icbH = 1000;
    int gen = 0;                 ///< intrinsic-size cache generation
    QStringList* warnings = nullptr;
};

// ---- common sizing (ChbLayout.cpp)
float lc_len(const Len& l, float base);                     ///< base < 0 → % resolve to 0
void lc_edges(Box* b, float cbW);                           ///< padding, border, non-auto margins (auto → 0)
float lc_hbp(const Box* b);                                 ///< horizontal border+padding
float lc_vbp(const Box* b);
/// Specified border-box width (−1 = auto / indefinite %). Intrinsic keywords are resolved.
float lc_spec_width(LayoutCtx& c, Box* b, float cbW);
float lc_spec_height(Box* b, float cbH);                    ///< −1 = auto / indefinite
float lc_min_width(LayoutCtx& c, Box* b, float cbW);        ///< border box; auto → 0
float lc_max_width(LayoutCtx& c, Box* b, float cbW);        ///< border box; none → +inf
float lc_min_height(Box* b, float cbH);
float lc_max_height(Box* b, float cbH);
float lc_clamp_w(LayoutCtx& c, Box* b, float w, float cbW);
float lc_clamp_h(Box* b, float h, float cbH);

// ---- intrinsic sizes (border box widths)
void lc_intrinsic(LayoutCtx& c, Box* b, float* minW, float* maxW);
/// Outer (margin box) contributions to a parent's intrinsic size, honouring width/min/max.
float lc_min_contribution(LayoutCtx& c, Box* b);
float lc_max_contribution(LayoutCtx& c, Box* b);
float lc_shrink_to_fit(LayoutCtx& c, Box* b, float availBorderW);

// ---- layout entry points
/// Block-level box in block flow: width per CSS 2.1 §10.3.3, then contents and height.
BlockOut lc_layout_block_level(LayoutCtx& c, Box* b, float cbW, float cbH);
/// Box whose border-box width is imposed (flex/grid item, cell, atomic inline, abs). borderH < 0 = auto.
void lc_layout_sized(LayoutCtx& c, Box* b, float borderW, float borderH, float cbW, float cbH);
/// Lay out children of `b` (b->w and edges known, b->definiteH set). Returns the auto content height.
float lc_layout_inside(LayoutCtx& c, Box* b, BlockOut* through);
bool lc_is_bfc_root(const Box* b);

// ---- formatting contexts
float lc_block_flow(LayoutCtx& c, Box* b, float cw, BlockOut* through);
float lc_inline(LayoutCtx& c, Box* b, float cw);
void lc_inline_intrinsic(LayoutCtx& c, Box* b, float* minW, float* maxW);
void lc_inline_prepare(LayoutCtx& c, Box* b);              ///< paragraph + break opportunities (ChbLayoutInlineBreak.cpp)
const FontEntry& chbi_font(const ComputedStyle& s);         ///< primary font of an inline style (default family serif)
const InlineItem* chbi_item_at(const InlineLayout& L, int pos); ///< item covering paragraph position pos, or nullptr
float lc_flex(LayoutCtx& c, Box* b, float cw, float ch);
void lc_flex_intrinsic(LayoutCtx& c, Box* b, float* minW, float* maxW);
float lc_grid(LayoutCtx& c, Box* b, float cw, float ch);
void lc_grid_intrinsic(LayoutCtx& c, Box* b, float* minW, float* maxW);
/// Table: computes its own border-box width (auto → shrink-to-fit ≤ availW, or `forcedW` ≥ 0).
void lc_table(LayoutCtx& c, Box* t, float availW, float forcedW, float cbH);
void lc_table_intrinsic(LayoutCtx& c, Box* t, float* minW, float* maxW);
/// Replaced element (svg/select): used border-box size.
void lc_replaced_size(LayoutCtx& c, Box* b, float cbW, float cbH, float* w, float* h);
void lc_replaced_intrinsic(LayoutCtx& c, Box* b, float* minW, float* maxW);

// ---- post passes
/// Document coordinates for the in-flow subtree of `b` (ref must be positioned).
void lc_finalize(Box* b);
/// Lay out absolutely positioned boxes (containing blocks first), then finalize them.
void lc_absolute_pass(LayoutCtx& c, Box* root);
/// Baseline for inline/table/flex alignment, relative to the border-box top (NaN → caller synthesizes).
float lc_first_baseline(const Box* b);
float lc_inline_block_baseline(const Box* b);

} // namespace fincept::screens::chb
