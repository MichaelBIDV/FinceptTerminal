#pragma once

#include "services/news/NewsService.h"

#include <QDialog>
#include <QPointer>

namespace fincept::screens {

class NewsDetailPanel;

/// Standalone dialog wrapping NewsDetailPanel to inspect any news article
/// with full details, AI analysis, translation, and clickable link.
class NewsDetailDialog : public QDialog {
    Q_OBJECT
  public:
    explicit NewsDetailDialog(const services::NewsArticle& article, QWidget* parent = nullptr);
    ~NewsDetailDialog() override;

    void set_article(const services::NewsArticle& article);

    /// Convenience launcher: raises/updates active dialog if already open,
    /// or opens a new dialog instance.
    static void show_article(const services::NewsArticle& article, QWidget* parent = nullptr);

  protected:
    void changeEvent(QEvent* event) override;

  private:
    void apply_styles();

    NewsDetailPanel* panel_ = nullptr;
    static QPointer<NewsDetailDialog> s_active_dialog;
};

} // namespace fincept::screens
