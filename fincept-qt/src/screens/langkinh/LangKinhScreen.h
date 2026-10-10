// src/screens/langkinh/LangKinhScreen.h
// Màn hình "langkinh" — Lăng Kính cấu trúc cổ đông & FFT (Pillar I · Pillar V, Methodology v1.7).
// Header 40px + LangKinhPanel (rổ VN30/VN100, 16 chế độ xem, trang block từ fincept_langkinh.py).
// Trạng thái lưu: scope, view, ma.
#pragma once

#include "screens/common/IStatefulScreen.h"

#include <QEvent>
#include <QLabel>
#include <QShowEvent>
#include <QWidget>

namespace fincept::screens {

class LangKinhPanel;

class LangKinhScreen : public QWidget, public IStatefulScreen {
    Q_OBJECT
  public:
    explicit LangKinhScreen(QWidget* parent = nullptr);

    void restore_state(const QVariantMap& state) override;
    QVariantMap save_state() const override;
    QString state_key() const override { return "langkinh"; }
    int state_version() const override { return 1; }

  protected:
    void changeEvent(QEvent* event) override;
    void showEvent(QShowEvent* event) override;

  private:
    void build_ui();
    void refresh_theme();
    void retranslateUi();

    QWidget* header_ = nullptr;
    QLabel* title_ = nullptr;
    QLabel* subtitle_ = nullptr;
    LangKinhPanel* panel_ = nullptr;
};

} // namespace fincept::screens
