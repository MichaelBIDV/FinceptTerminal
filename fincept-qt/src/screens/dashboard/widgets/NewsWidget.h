#pragma once

#include "screens/dashboard/widgets/BaseWidget.h"
#include "services/news/NewsService.h"

#include <QScrollArea>
#include <QVBoxLayout>
#include <QVector>

namespace fincept::screens::widgets {

class NewsWidget : public BaseWidget {
    Q_OBJECT
  public:
    explicit NewsWidget(QWidget* parent = nullptr);

  protected:
    void apply_styles();
    void on_theme_changed() override;
    void showEvent(QShowEvent* e) override;
    void hideEvent(QHideEvent* e) override;
    void retranslateUi() override;
    bool eventFilter(QObject* obj, QEvent* event) override;

  private:
    void hub_subscribe();
    void hub_unsubscribe();
    void populate(const QVector<services::NewsArticle>& articles);

    QScrollArea* scroll_area_ = nullptr;
    QVBoxLayout* news_layout_ = nullptr;
    QVector<services::NewsArticle> last_articles_;
    bool hub_active_ = false;
};

} // namespace fincept::screens::widgets
