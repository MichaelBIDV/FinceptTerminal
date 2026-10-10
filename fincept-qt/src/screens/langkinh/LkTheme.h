// src/screens/langkinh/LkTheme.h
// Lăng Kính FFT — bảng màu, bậc bằng chứng và phông của "hồ sơ" (LK_HOSO_SPEC §6). Header-only.
//
// Màu đọc từ ui::colors TẠI LÚC GỌI: LkBlockView dựng lại cả trang khi đổi theme, widget tự vẽ gọi lk_col()
// trong paintEvent. Vai có token → dùng token; vai không có token → suy từ theme:
//   bg=BG_BASE · surface=BG_SURFACE · surface2=BG_RAISED · line=BORDER_MED · line2=BORDER_BRIGHT
//   (theme tối có BG_SURFACE gần như trùng BG_BASE — Obsidian #0a0a0a/#080808 — thì surface/surface2 suy từ bg pha
//    4% / 8% về ink, để thẻ nổi khỏi trang như Artifact bg/surface/surface-2; xem lk_flat_surface)
//   ink=TEXT_PRIMARY · ink2=pha 60% TEXT_PRIMARY + 40% TEXT_SECONDARY (không có token giữa hai bậc chữ)
//   muted=TEXT_SECONDARY · amber=AMBER (accent của theme) · up=POSITIVE · down=NEGATIVE · blue=INFO
//   violet, grey: cặp hex §6 (tối/sáng) chọn theo độ sáng BG_BASE.
// Màu nhấn lấy từ token (amber/up/down/blue) được kéo dần về phía ink khi tương phản với surface < 4,5:1,
// để chữ tag 10px vẫn đọc được trên mọi theme. *_soft = cùng màu, alpha 0,13 (tối) / 0,10 (sáng) như Artifact.
//
// Bậc bằng chứng (luật §0.2): FACT-T1=up · FACT-T2=blue · SS-T3=violet · EST=amber · NEWS=grey ·
// UNVERIFIED / CẦN DATA=down. Chấp nhận tiền tố ("FACT-T2 · v1.7", "[CẦN DATA]").
// Phông (Q6): serif Palatino (thay Cormorant), sans Be Vietnam Pro, mono Menlo (chữ số tabular).
// Lưu ý: QSS toàn cục đặt `* { font-family; font-size }` nên QLabel phải nhận phông qua stylesheet —
// dùng lk_font_css(); QPainter dùng thẳng QFont.
#pragma once

#include "ui/theme/Theme.h"

#include <QColor>
#include <QFont>
#include <QLatin1String>
#include <QString>
#include <QStringList>

#include <algorithm>
#include <cmath>
#include <initializer_list>

namespace fincept::screens::langkinh::lkview {

enum class LkRole {
    Bg,
    Surface,
    Surface2,
    Line,
    Line2,
    Ink,
    Ink2,
    Muted,
    Amber,
    Up,
    Down,
    Blue,
    Violet,
    Grey,
    AmberSoft,
    UpSoft,
    DownSoft,
    BlueSoft,
    VioletSoft,
    GreySoft,
    AmberLine, ///< amber alpha 0,45 (viền khung CỔNG .gate kiểu Artifact)
};

// ── Toán màu ──────────────────────────────────────────────────────────────────

/// Theme sáng khi BG_BASE sáng hơn nửa thang.
inline bool lk_is_light() {
    return QColor(ui::colors::BG_BASE()).lightness() > 128;
}

/// Pha tuyến tính a→b (t=0 → a, t=1 → b), giữ alpha của a.
inline QColor lk_mix(const QColor& a, const QColor& b, double t) {
    t = std::clamp(t, 0.0, 1.0);
    const auto ch = [t](float x, float y) { return static_cast<float>(x + (y - x) * t); };
    return QColor::fromRgbF(ch(a.redF(), b.redF()), ch(a.greenF(), b.greenF()), ch(a.blueF(), b.blueF()), a.alphaF());
}

/// Màu có alpha phủ lên nền đục → màu đục (dùng cho rich text, nơi rgba() không chắc được hỗ trợ).
inline QColor lk_over(const QColor& top, const QColor& base) {
    const float a = top.alphaF();
    const auto ch = [a](float t, float b) { return t * a + b * (1.0f - a); };
    return QColor::fromRgbF(ch(top.redF(), base.redF()), ch(top.greenF(), base.greenF()), ch(top.blueF(), base.blueF()),
                            1.0f);
}

/// Độ chói tương đối WCAG 2.x.
inline double lk_luminance(const QColor& c) {
    const auto lin = [](double v) { return v <= 0.03928 ? v / 12.92 : std::pow((v + 0.055) / 1.055, 2.4); };
    return 0.2126 * lin(c.redF()) + 0.7152 * lin(c.greenF()) + 0.0722 * lin(c.blueF());
}

inline double lk_contrast(const QColor& a, const QColor& b) {
    const double la = lk_luminance(a);
    const double lb = lk_luminance(b);
    return (std::max(la, lb) + 0.05) / (std::min(la, lb) + 0.05);
}

/// Kéo fg dần về `toward` (10% mỗi bước, tối đa 80%) tới khi tương phản với bg ≥ min_ratio.
inline QColor lk_legible(const QColor& fg, const QColor& bg, const QColor& toward, double min_ratio = 4.5) {
    QColor c = fg;
    for (int i = 1; i <= 8 && lk_contrast(c, bg) < min_ratio; ++i)
        c = lk_mix(fg, toward, 0.1 * i);
    return c;
}

/// Bản "soft" của một màu: alpha 0,13 (tối) / 0,10 (sáng).
inline QColor lk_soft(QColor c) {
    c.setAlphaF(lk_is_light() ? 0.10f : 0.13f);
    return c;
}

/// Màu cho QSS: "#rrggbb" khi đục, "rgba(r,g,b,a)" (a 0..255) khi có alpha.
inline QString lk_qss(const QColor& c) {
    if (c.alpha() == 255)
        return c.name();
    return QStringLiteral("rgba(%1,%2,%3,%4)").arg(c.red()).arg(c.green()).arg(c.blue()).arg(c.alpha());
}

// ── Vai màu ───────────────────────────────────────────────────────────────────

/// Theme tối mà BG_SURFACE lệch BG_BASE < 2% độ sáng (Obsidian: #0a0a0a trên #080808) → thẻ không tách khỏi trang.
inline bool lk_flat_surface() {
    using namespace ui::colors;
    const QColor bg(BG_BASE());
    return !lk_is_light() && std::abs(QColor(BG_SURFACE()).lightnessF() - bg.lightnessF()) < 0.02;
}

inline QColor lk_col(LkRole r) {
    using namespace ui::colors;
    const bool light = lk_is_light();
    const bool flat = lk_flat_surface();
    const QColor surface = flat ? lk_mix(QColor(BG_BASE()), QColor(TEXT_PRIMARY()), 0.04) : QColor(BG_SURFACE());
    const QColor ink(TEXT_PRIMARY());
    const auto accent = [&](const char* token) { return lk_legible(QColor(token), surface, ink); };
    switch (r) {
    case LkRole::Bg:
        return QColor(BG_BASE());
    case LkRole::Surface:
        return surface;
    case LkRole::Surface2:
        return flat ? lk_mix(QColor(BG_BASE()), ink, 0.08) : QColor(BG_RAISED());
    case LkRole::Line:
        return QColor(BORDER_MED());
    case LkRole::Line2:
        return QColor(BORDER_BRIGHT());
    case LkRole::Ink:
        return ink;
    case LkRole::Ink2:
        return lk_mix(ink, QColor(TEXT_SECONDARY()), 0.4);
    case LkRole::Muted:
        return QColor(TEXT_SECONDARY());
    case LkRole::Amber:
        return accent(AMBER());
    case LkRole::Up:
        return accent(POSITIVE());
    case LkRole::Down:
        return accent(NEGATIVE());
    case LkRole::Blue:
        return accent(INFO());
    case LkRole::Violet: // §6: #ad91e3 / #6a4bb3
        return light ? QColor::fromRgb(0x6a, 0x4b, 0xb3) : QColor::fromRgb(0xad, 0x91, 0xe3);
    case LkRole::Grey: // §6: #9aa1a8 / #5f666d
        return light ? QColor::fromRgb(0x5f, 0x66, 0x6d) : QColor::fromRgb(0x9a, 0xa1, 0xa8);
    case LkRole::AmberSoft:
        return lk_soft(lk_col(LkRole::Amber));
    case LkRole::UpSoft:
        return lk_soft(lk_col(LkRole::Up));
    case LkRole::DownSoft:
        return lk_soft(lk_col(LkRole::Down));
    case LkRole::BlueSoft:
        return lk_soft(lk_col(LkRole::Blue));
    case LkRole::VioletSoft:
        return lk_soft(lk_col(LkRole::Violet));
    case LkRole::GreySoft:
        return lk_soft(lk_col(LkRole::Grey));
    case LkRole::AmberLine: {
        QColor c = lk_col(LkRole::Amber);
        c.setAlphaF(0.45f);
        return c;
    }
    }
    return ink;
}

/// Vai theo tên §6: "bg", "surface", "surface2"/"surface-2", "line", "line2", "ink", "ink2", "muted", "amber",
/// "up", "down", "blue", "violet", "grey"/"gray"; hậu tố "_soft"/"-soft" → bản soft. Tên lạ → ink.
inline QColor lk_col(const QString& name) {
    QString s = name.trimmed().toLower();
    s.replace(QLatin1Char('-'), QLatin1Char('_'));
    bool soft = false;
    if (s.endsWith(QLatin1String("_soft"))) {
        soft = true;
        s.chop(5);
    }
    s.remove(QLatin1Char('_'));
    struct Pair {
        const char* key;
        LkRole role;
    };
    static constexpr Pair kMap[] = {
        {"bg", LkRole::Bg},         {"surface", LkRole::Surface}, {"surface2", LkRole::Surface2},
        {"line", LkRole::Line},     {"line2", LkRole::Line2},     {"ink", LkRole::Ink},
        {"ink2", LkRole::Ink2},     {"muted", LkRole::Muted},     {"amber", LkRole::Amber},
        {"up", LkRole::Up},         {"down", LkRole::Down},       {"blue", LkRole::Blue},
        {"violet", LkRole::Violet}, {"grey", LkRole::Grey},       {"gray", LkRole::Grey},
    };
    for (const Pair& p : kMap)
        if (s == QLatin1String(p.key))
            return soft ? lk_soft(lk_col(p.role)) : lk_col(p.role);
    return lk_col(LkRole::Ink);
}

/// Thẻ ngữ nghĩa "mau" của block hồ sơ → vai màu:
///   good|up|yes|bull → Up · bad|down|no|bear → Down · amb|amber|warn|near → Amber · info|blue → Blue ·
///   violet → Violet · neu|grey|gray|dim → Grey · ink → Ink · ink2 → Ink2 · ""/lạ → fallback.
inline LkRole lk_role(const QString& mau, LkRole fallback) {
    const QString m = mau.trimmed().toLower();
    if (m.isEmpty())
        return fallback;
    const auto any = [&m](std::initializer_list<const char*> keys) {
        return std::any_of(keys.begin(), keys.end(), [&m](const char* k) { return m == QLatin1String(k); });
    };
    if (any({"good", "up", "yes", "bull", "pos", "positive"}))
        return LkRole::Up;
    if (any({"bad", "down", "no", "bear", "neg", "negative"}))
        return LkRole::Down;
    if (any({"amb", "amber", "warn", "near", "est"}))
        return LkRole::Amber;
    if (any({"info", "blue"}))
        return LkRole::Blue;
    if (any({"violet"}))
        return LkRole::Violet;
    if (any({"neu", "grey", "gray", "dim", "muted"}))
        return LkRole::Grey;
    if (any({"ink"}))
        return LkRole::Ink;
    if (any({"ink2", "ink-2", "ink_2"})) // chữ phụ (Artifact: chỉ số trên thước σ)
        return LkRole::Ink2;
    return fallback;
}

// ── Bậc bằng chứng ────────────────────────────────────────────────────────────

/// Khoá chuẩn của bậc: "FACT-T1" · "FACT-T2" · "SS-T3" · "NEWS" · "EST" · "UNVERIFIED" · "CẦN DATA" · "" (lạ/rỗng).
/// Chấp nhận tiền tố và phần đuôi ("FACT-T2 · v1.7", "[CẦN DATA] — …", "t2").
inline QString lk_tier_key(const QString& b) {
    QString s = b.trimmed().toUpper();
    while (s.startsWith(QLatin1Char('[')) || s.startsWith(QLatin1Char('(')))
        s.remove(0, 1);
    s = s.trimmed();
    const auto starts = [&s](const char* p) { return s.startsWith(QLatin1String(p)); };
    if (starts("UNVERIFIED"))
        return QStringLiteral("UNVERIFIED");
    if (s.startsWith(QStringLiteral("CẦN DATA")) || s.startsWith(QStringLiteral("CẦN_DATA")) || starts("CAN DATA") ||
        starts("CAN_DATA"))
        return QStringLiteral("CẦN DATA");
    if (starts("FACT-T1") || starts("FACT_T1") || starts("T1"))
        return QStringLiteral("FACT-T1");
    if (starts("FACT-T2") || starts("FACT_T2") || starts("T2"))
        return QStringLiteral("FACT-T2");
    if (starts("SS-T3") || starts("SS_T3") || starts("T3"))
        return QStringLiteral("SS-T3");
    if (starts("EST"))
        return QStringLiteral("EST");
    if (starts("NEWS"))
        return QStringLiteral("NEWS");
    return {};
}

inline LkRole lk_tier_role(const QString& b) {
    const QString k = lk_tier_key(b);
    if (k == QLatin1String("FACT-T1"))
        return LkRole::Up;
    if (k == QLatin1String("FACT-T2"))
        return LkRole::Blue;
    if (k == QLatin1String("SS-T3"))
        return LkRole::Violet;
    if (k == QLatin1String("EST"))
        return LkRole::Amber;
    if (k == QLatin1String("UNVERIFIED") || k == QStringLiteral("CẦN DATA"))
        return LkRole::Down;
    return LkRole::Grey; // NEWS và nhãn lạ
}

/// Màu chữ của tag bậc.
inline QColor lk_tier(const QString& b) {
    return lk_col(lk_tier_role(b));
}

/// Nền soft của tag bậc (có alpha — vẽ lên surface).
inline QColor lk_tier_soft(const QString& b) {
    return lk_soft(lk_tier(b));
}

inline bool lk_tier_unverified(const QString& b) {
    return lk_tier_key(b) == QLatin1String("UNVERIFIED");
}

// ── Phông ─────────────────────────────────────────────────────────────────────

inline QFont lk_font_make(const QStringList& families, QFont::StyleHint hint, int px, int weight) {
    QFont f;
    f.setFamilies(families);
    f.setStyleHint(hint);
    f.setPixelSize(std::max(1, px));
    f.setWeight(static_cast<QFont::Weight>(std::clamp(weight, 100, 900)));
    return f;
}

/// Serif hiển thị (tiêu đề lớn, mã, số thứ tự keynote): Palatino.
inline QFont lk_font_serif(int px, int weight = 600) {
    return lk_font_make({QStringLiteral("Palatino"), QStringLiteral("Palatino Linotype"),
                         QStringLiteral("Iowan Old Style"), QStringLiteral("Georgia")},
                        QFont::Serif, px, weight);
}

/// Sans thân bài: Be Vietnam Pro.
inline QFont lk_font_sans(int px, int weight = 400) {
    return lk_font_make({QStringLiteral("Be Vietnam Pro"), QStringLiteral("Helvetica Neue"), QStringLiteral("Arial")},
                        QFont::SansSerif, px, weight);
}

/// Mono cho số (chữ số tabular): Menlo.
inline QFont lk_font_mono(int px, int weight = 400) {
    QFont f = lk_font_make({QStringLiteral("Menlo"), QStringLiteral("SF Mono"), QStringLiteral("JetBrains Mono"),
                            QStringLiteral("Consolas"), QStringLiteral("DejaVu Sans Mono")},
                           QFont::Monospace, px, weight);
    f.setFixedPitch(true);
    f.setFeature("tnum", 1);
    return f;
}

/// Khối QSS "font-family:…; font-size:Npx; font-weight:W;" cho QLabel (QSS toàn cục ghi đè setFont()).
inline QString lk_font_css(const QFont& f) {
    QStringList fams;
    for (const QString& fam : f.families())
        fams << QStringLiteral("\"%1\"").arg(fam);
    if (fams.isEmpty())
        fams << QStringLiteral("\"%1\"").arg(f.family());
    const QFont::StyleHint h = f.styleHint();
    fams << (h == QFont::Serif ? QStringLiteral("serif")
                               : (h == QFont::Monospace || h == QFont::TypeWriter ? QStringLiteral("monospace")
                                                                                  : QStringLiteral("sans-serif")));
    return QStringLiteral("font-family:%1; font-size:%2px; font-weight:%3;%4")
        .arg(fams.join(QStringLiteral(", ")))
        .arg(std::max(1, f.pixelSize()))
        .arg(static_cast<int>(f.weight()))
        .arg(f.italic() ? QStringLiteral(" font-style:italic;") : QString());
}

} // namespace fincept::screens::langkinh::lkview
