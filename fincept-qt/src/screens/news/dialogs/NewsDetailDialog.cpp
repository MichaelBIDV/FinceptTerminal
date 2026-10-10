#include "screens/news/dialogs/NewsDetailDialog.h"

#include "screens/news/NewsDetailPanel.h"
#include "storage/repositories/NewsArticleRepository.h"
#include "ui/theme/Theme.h"

#include <QVBoxLayout>

namespace fincept::screens {

QPointer<NewsDetailDialog> NewsDetailDialog::s_active_dialog = nullptr;

NewsDetailDialog::NewsDetailDialog(const services::NewsArticle& article, QWidget* parent)
    : QDialog(parent) {
    setWindowTitle(tr("Article Detail"));
    setAttribute(Qt::WA_DeleteOnClose);
    setWindowFlags(Qt::Dialog | Qt::WindowCloseButtonHint | Qt::WindowTitleHint);
    setFixedWidth(440);
    setMinimumHeight(600);
    resize(440, 720);

    auto* root = new QVBoxLayout(this);
    root->setContentsMargins(0, 0, 0, 0);
    root->setSpacing(0);

    panel_ = new NewsDetailPanel(this);
    root->addWidget(panel_, 1);

    connect(panel_, &NewsDetailPanel::panel_closed, this, &QDialog::accept);

    connect(panel_, &NewsDetailPanel::analyze_requested, this, [this](const QString& url) {
        QPointer<NewsDetailPanel> p = panel_;
        services::NewsService::instance().analyze_article(url, [p](bool ok, services::NewsAnalysis analysis) {
            if (!p)
                return;
            if (ok)
                p->show_analysis(analysis);
        });
    });

    connect(panel_, &NewsDetailPanel::bookmark_requested, this, [](const services::NewsArticle& a) {
        fincept::NewsArticleRepository::instance().toggle_saved(a.id);
    });

    connect(panel_, &NewsDetailPanel::related_article_clicked, this, [this](const services::NewsArticle& a) {
        set_article(a);
    });

    apply_styles();
    set_article(article);
}

NewsDetailDialog::~NewsDetailDialog() {
    if (s_active_dialog == this)
        s_active_dialog = nullptr;
}

void NewsDetailDialog::set_article(const services::NewsArticle& article) {
    if (!panel_)
        return;
    setWindowTitle(article.headline.isEmpty() ? tr("Article Detail") : article.headline);
    panel_->show_article(article);
    panel_->open_panel();

    if (auto cached = services::NewsService::instance().cached_analysis(article.link)) {
        panel_->show_analysis(*cached);
    }
}

void NewsDetailDialog::show_article(const services::NewsArticle& article, QWidget* parent) {
    if (s_active_dialog) {
        s_active_dialog->set_article(article);
        s_active_dialog->raise();
        s_active_dialog->activateWindow();
        return;
    }
    auto* dlg = new NewsDetailDialog(article, parent ? parent->window() : nullptr);
    s_active_dialog = dlg;
    dlg->show();
    dlg->raise();
    dlg->activateWindow();
}

void NewsDetailDialog::apply_styles() {
    setStyleSheet(QString("QDialog { background: %1; color: %2; }")
                      .arg(ui::colors::BG_BASE(), ui::colors::TEXT_PRIMARY()));
}

void NewsDetailDialog::changeEvent(QEvent* event) {
    if (event->type() == QEvent::LanguageChange) {
        setWindowTitle(tr("Article Detail"));
    }
    QDialog::changeEvent(event);
}

} // namespace fincept::screens
