#include "services/news/NewsMonitorService.h"

#include "core/logging/Logger.h"
#include "services/news/NewsViText.h"
#include "storage/repositories/NewsMonitorRepository.h"

#include <QUuid>

#include <algorithm>

namespace fincept::services {

const QStringList& monitor_colors() {
    static const QStringList colors = {
        "#00E5FF", "#00FF88", "#FF6B35", "#FFD700", "#9D4EDD", "#FF4D6D", "#4CC9F0", "#F72585", "#7FFF00", "#FF9500",
    };
    return colors;
}

NewsMonitorService& NewsMonitorService::instance() {
    static NewsMonitorService s;
    return s;
}

NewsMonitorService::NewsMonitorService() {
    // Table now created by MigrationRunner v001 — no ensure_table() needed
    load_from_db();
}

void NewsMonitorService::load_from_db() {
    monitors_.clear();
    auto result = fincept::NewsMonitorRepository::instance().list_all();
    if (result.is_err())
        return;
    for (const auto& row : result.value()) {
        NewsMonitor m;
        m.id = row.id;
        m.label = row.label;
        m.keywords = row.keywords;
        m.color = row.color;
        m.enabled = row.enabled;
        monitors_.append(m);
    }
}

void NewsMonitorService::save_to_db(const NewsMonitor& m) {
    fincept::NewsMonitorRow row{m.id, m.label, m.keywords, m.color, m.enabled};
    fincept::NewsMonitorRepository::instance().upsert(row);
}

void NewsMonitorService::remove_from_db(const QString& id) {
    fincept::NewsMonitorRepository::instance().remove(id);
}

QVector<NewsMonitor> NewsMonitorService::get_monitors() const {
    return monitors_;
}

void NewsMonitorService::add_monitor(const QString& label, const QStringList& keywords, const QString& color) {
    NewsMonitor m;
    m.id = QUuid::createUuid().toString(QUuid::WithoutBraces).left(8);
    m.label = label;
    m.keywords = keywords;
    m.color = color.isEmpty() ? monitor_colors()[monitors_.size() % monitor_colors().size()] : color;
    m.enabled = true;
    monitors_.append(m);
    save_to_db(m);
}

void NewsMonitorService::update_monitor(const NewsMonitor& monitor) {
    for (auto& m : monitors_) {
        if (m.id == monitor.id) {
            m = monitor;
            save_to_db(m);
            return;
        }
    }
}

void NewsMonitorService::delete_monitor(const QString& id) {
    monitors_.erase(
        std::remove_if(monitors_.begin(), monitors_.end(), [&](const NewsMonitor& m) { return m.id == id; }),
        monitors_.end());
    remove_from_db(id);
}

void NewsMonitorService::toggle_monitor(const QString& id) {
    for (auto& m : monitors_) {
        if (m.id == id) {
            m.enabled = !m.enabled;
            save_to_db(m);
            return;
        }
    }
}

QMap<QString, QVector<NewsArticle>> NewsMonitorService::scan_monitors(const QVector<NewsMonitor>& monitors,
                                                                      const QVector<NewsArticle>& articles) const {
    QMap<QString, QVector<NewsArticle>> result;

    // Keyword match on Unicode word boundaries. The old `\b…\b` regex was ASCII-only, so "khởi tố"
    // matched 0 articles (7 expected) and "đình chỉ" never matched. A keyword typed WITH diacritics
    // is compared against the accented lowercase text (folding would let "nằm sàn" hit "Việt Nam sẵn
    // sàng"); a plain-ASCII keyword is compared against the folded text, so "lai suat" finds "lãi suất".
    struct Keyword {
        QString text;
        bool ascii;
    };
    auto prepare = [](const QStringList& raw) {
        QVector<Keyword> out;
        for (const auto& kw : raw) {
            const QString k = vitext::clean(kw.trimmed()).toLower();
            if (k.isEmpty())
                continue;
            const bool ascii = std::all_of(k.cbegin(), k.cend(), [](QChar c) { return c.unicode() < 0x80; });
            out.append({ascii ? vitext::fold(k) : k, ascii});
        }
        return out;
    };

    QVector<QString> lowered, folded;
    bool texts_ready = false;

    for (const auto& mon : monitors) {
        if (!mon.enabled || mon.keywords.isEmpty())
            continue;
        const QVector<Keyword> keywords = prepare(mon.keywords);
        if (keywords.isEmpty())
            continue;

        if (!texts_ready) {
            lowered.reserve(articles.size());
            folded.reserve(articles.size());
            for (const auto& a : articles) {
                const QString text = a.headline + " " + a.summary;
                lowered.append(vitext::clean(text).toLower());
                folded.append(vitext::fold(text));
            }
            texts_ready = true;
        }

        QVector<NewsArticle> matches;
        for (int i = 0; i < articles.size(); ++i) {
            const bool hit = std::any_of(keywords.cbegin(), keywords.cend(), [&](const Keyword& k) {
                return vitext::has_word(k.ascii ? folded[i] : lowered[i], k.text);
            });
            if (hit)
                matches.append(articles[i]);
        }
        if (!matches.isEmpty())
            result[mon.id] = matches;
    }

    return result;
}

} // namespace fincept::services
