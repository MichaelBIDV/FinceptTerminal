// src/screens/langkinh/LangKinhScreen.cpp
// Màn hình "langkinh" — xem LangKinhScreen.h.
#include "screens/langkinh/LangKinhScreen.h"

#include "core/session/ScreenStateManager.h"
#include "screens/langkinh/LangKinhPanel.h"
#include "ui/theme/Theme.h"
#include "ui/theme/ThemeManager.h"

#include <QHBoxLayout>
#include <QTimer>
#include <QVBoxLayout>

namespace fincept::screens {

LangKinhScreen::LangKinhScreen(QWidget* parent) : QWidget(parent) {
    setObjectName(QStringLiteral("langKinhScreen"));
    build_ui();
    connect(&ui::ThemeManager::instance(), &ui::ThemeManager::theme_changed, this, &LangKinhScreen::refresh_theme);
    connect(panel_, &LangKinhPanel::state_changed, this,
            [this]() { ScreenStateManager::instance().notify_changed(this); });
}

void LangKinhScreen::build_ui() {
    auto* root = new QVBoxLayout(this);
    root->setContentsMargins(0, 0, 0, 0);
    root->setSpacing(0);

    header_ = new QWidget(this);
    header_->setFixedHeight(40);
    auto* hl = new QHBoxLayout(header_);
    hl->setContentsMargins(12, 0, 12, 0);
    hl->setSpacing(8);
    title_ = new QLabel(tr("LĂNG KÍNH CẤU TRÚC CỔ ĐÔNG & FFT"));
    subtitle_ = new QLabel(tr("Pillar I · III · V — Methodology v1.7 · VN30 · VN100 · VN200"));
    hl->addWidget(title_);
    hl->addWidget(subtitle_);
    hl->addStretch();
    root->addWidget(header_);

    panel_ = new LangKinhPanel(this);
    root->addWidget(panel_, 1);

    refresh_theme();
}

void LangKinhScreen::refresh_theme() {
    using namespace ui::colors;
    header_->setStyleSheet(QStringLiteral("background:%1; border-bottom:1px solid %2;").arg(BG_BASE(), BORDER_DIM()));
    title_->setStyleSheet(QStringLiteral("color:%1; font-size:12px; font-weight:700;"
                                         "letter-spacing:1.5px; background:transparent; border:none;")
                              .arg(TEXT_PRIMARY()));
    subtitle_->setStyleSheet(
        QStringLiteral("color:%1; font-size:10px; background:transparent; border:none;").arg(TEXT_TERTIARY()));
}

void LangKinhScreen::showEvent(QShowEvent* event) {
    QWidget::showEvent(event);
    // Hoãn một vòng sự kiện: router gọi restore_state() ngay sau factory, nên lần nạp đầu
    // dùng đúng rổ/view/mã đã lưu. activate() tự bỏ qua nếu đã có dữ liệu hoặc đang nạp.
    QTimer::singleShot(0, this, [this]() {
        if (panel_)
            panel_->activate();
    });
}

void LangKinhScreen::changeEvent(QEvent* event) {
    if (event->type() == QEvent::LanguageChange)
        retranslateUi();
    QWidget::changeEvent(event);
}

void LangKinhScreen::retranslateUi() {
    if (title_)
        title_->setText(tr("LĂNG KÍNH CẤU TRÚC CỔ ĐÔNG & FFT"));
    if (subtitle_)
        subtitle_->setText(tr("Pillar I · III · V — Methodology v1.7 · VN30 · VN100 · VN200"));
}

// ── IStatefulScreen ───────────────────────────────────────────────────────────

QVariantMap LangKinhScreen::save_state() const {
    return panel_ ? panel_->save_panel_state() : QVariantMap{};
}

void LangKinhScreen::restore_state(const QVariantMap& state) {
    if (panel_)
        panel_->restore_panel_state(state);
}

} // namespace fincept::screens
