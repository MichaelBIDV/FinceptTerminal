#pragma once
// ChbStyle_p.h — internal helpers shared by ChbStyle*.cpp (not part of the engine API).
#include "screens/chaebol_map/ChbStyle.h"

#include <cstring>

namespace fincept::screens::chb {

QStringList css_split_commas_top_functions(QStringView s);
std::shared_ptr<const std::vector<Shadow>> parse_css_shadows(QStringView s);
std::shared_ptr<const TrackList> parse_css_track_list(QStringView s);
bool parse_css_track_size(QStringView s, TrackSize* out);
bool parse_css_grid_line(QStringView s, GridLine* out);
bool parse_css_transform(QStringView s, Transform2D* out);

/// Keyword ids used in SpecValue::kw for multi-purpose props.
enum ChbKw : int {
    KwNone = 0,
    // font-size keywords 1..8, smaller/larger
    KwFsXXSmall = 1, KwFsXSmall, KwFsSmall, KwFsMedium, KwFsLarge, KwFsXLarge, KwFsXXLarge, KwFsXXXLarge,
    KwFsSmaller = 20, KwFsLarger,
    // font-weight
    KwBolder = 30, KwLighter,
    // line-height / spacing
    KwNormal = 40,
    // z-index
    KwAuto = 50,
    // cursor
    KwPointer = 60, KwOtherCursor,
    // text-overflow
    KwEllipsis = 70, KwClip,
};

} // namespace fincept::screens::chb
