// WdcData.cpp: reader of the widata_clone/1 build and ChartInput assembly. Package E (DESIGN §4, INT §3.4).
#include "WdcData.h"

#include <QCoreApplication>
#include <QDir>
#include <QFile>
#include <QFileInfo>
#include <QJsonArray>
#include <QJsonDocument>
#include <QMutex>
#include <QSaveFile>
#include <QThread>

#include <algorithm>
#include <cmath>
#include <limits>

namespace fincept::screens::wdc {
namespace {

// ---- I/O accounting ----------------------------------------------------------------------------------

QMutex wdcdata_io_mutex;
IoStats wdcdata_io;

bool wdcdata_on_gui() {
    const QCoreApplication* app = QCoreApplication::instance();
    return app && QThread::currentThread() == app->thread();
}

void wdcdata_count(const QString& path, bool write) {
    const bool gui = wdcdata_on_gui();
    QMutexLocker lock(&wdcdata_io_mutex);
    if (gui) {
        (write ? wdcdata_io.guiWrites : wdcdata_io.guiReads)++;
        if (wdcdata_io.guiPaths.size() < 64) wdcdata_io.guiPaths << path;
    } else {
        (write ? wdcdata_io.workerWrites : wdcdata_io.workerReads)++;
    }
}

// ---- CSS colours -------------------------------------------------------------------------------------

// Hex digits of `h` from `at`, `n` (1 or 2) wide; -1 when not hex. One digit is doubled as in CSS (#f = #ff).
int wdcdata_hex(const QString& h, int at, int n) {
    bool ok = false;
    const int v = h.mid(at, n).toInt(&ok, 16);
    return ok ? (n == 1 ? v * 17 : v) : -1;
}

// ---- JSON helpers: tolerant readers that record a precise path for every problem ------------------

struct WdcdataCtx {
    QStringList* warn;
    void w(const QString& path, const QString& msg) const { if (warn && warn->size() < 200) *warn << path + QStringLiteral(": ") + msg; }
};

double wdcdata_num(const QJsonValue& v, double def, const WdcdataCtx& cx, const QString& path) {
    if (v.isDouble()) return v.toDouble();
    if (!v.isUndefined() && !v.isNull()) cx.w(path, QStringLiteral("không phải số"));
    return def;
}

std::optional<double> wdcdata_optnum(const QJsonValue& v, const WdcdataCtx& cx, const QString& path) {
    if (v.isDouble()) return v.toDouble();
    if (!v.isUndefined() && !v.isNull()) cx.w(path, QStringLiteral("không phải số"));
    return std::nullopt;
}

bool wdcdata_bool(const QJsonValue& v, bool def) { return v.isBool() ? v.toBool() : def; }

QString wdcdata_str(const QJsonValue& v) { return v.isString() ? v.toString() : QString(); }

QColor wdcdata_color(const QJsonValue& v, const WdcdataCtx& cx, const QString& path) {
    if (!v.isString()) return QColor();
    const QColor c = parseCssColor(v.toString());
    if (!c.isValid()) cx.w(path, QStringLiteral("màu không hợp lệ '%1'").arg(v.toString()));
    return c;
}

YAxisSpec wdcdata_yaxis(const QJsonObject& o, const WdcdataCtx& cx, const QString& p, std::optional<double>* tpi) {
    YAxisSpec a{};
    a.slot = int(wdcdata_num(o.value("slot"), 1, cx, p + ".slot"));
    a.format = wdcdata_str(o.value("format"));
    if (const auto t = wdcdata_optnum(o.value("tickAmount"), cx, p + ".tickAmount")) a.tickAmount = int(*t);
    a.startOnTick = wdcdata_bool(o.value("startOnTick"), true);
    a.endOnTick = wdcdata_bool(o.value("endOnTick"), true);
    a.minPadding = wdcdata_num(o.value("minPadding"), 0.05, cx, p + ".minPadding");
    a.maxPadding = wdcdata_num(o.value("maxPadding"), 0.05, cx, p + ".maxPadding");
    a.labelPx = wdcdata_num(o.value("labelPx"), 9, cx, p + ".labelPx");
    a.labelY = wdcdata_optnum(o.value("labelY"), cx, p + ".labelY");
    a.distance = wdcdata_num(o.value("distance"), 15, cx, p + ".distance");
    a.margin = wdcdata_num(o.value("margin"), 0, cx, p + ".margin");
    const QJsonObject g = o.value("grid").toObject();
    a.gridColor = wdcdata_color(g.value("color"), cx, p + ".grid.color");
    if (!a.gridColor.isValid()) a.gridColor = QColor(0xDF, 0xE3, 0xE8);
    a.gridDash = g.value("dash").isString() ? g.value("dash").toString() : QStringLiteral("Dot");
    *tpi = wdcdata_optnum(o.value("tickPixelInterval"), cx, p + ".tickPixelInterval");
    return a;
}

ChartSpec wdcdata_chart(const QJsonObject& o, const WdcdataCtx& cx, const QString& p,
                        std::vector<std::optional<double>>* tpis) {
    ChartSpec c{};
    c.isStock = wdcdata_bool(o.value("isStock"), false);
    c.spacing = {6, 2, 6, 2};
    const QJsonArray sp = o.value("spacing").toArray();
    if (sp.size() == 4) for (int i = 0; i < 4; ++i) c.spacing[i] = wdcdata_num(sp[i], c.spacing[i], cx, p + ".spacing");
    else if (!o.value("spacing").isUndefined()) cx.w(p + ".spacing", QStringLiteral("cần mảng 4 số"));
    const QJsonArray mg = o.value("margin").toArray();
    for (int i = 0; i < 4 && i < mg.size(); ++i) c.margin[i] = wdcdata_optnum(mg[i], cx, p + ".margin");
    const QJsonObject x = o.value("x").toObject();
    const QJsonObject dt = x.value("dtFormats").toObject();
    for (auto it = dt.begin(); it != dt.end(); ++it) c.dtFormats.insert(it.key(), it.value().toString());
    if (c.dtFormats.isEmpty())
        c.dtFormats = {{"day", "%d/%m/%Y"}, {"week", "%d/%m/%Y"}, {"month", "%m/%Y"}, {"year", "%Y"}};
    c.shiftLabelWhenColumn = wdcdata_bool(x.value("shiftLabelWhenColumn"), true);
    c.xMinPadding = wdcdata_num(x.value("minPadding"), c.isStock ? 0 : 0.01, cx, p + ".x.minPadding");
    c.xMaxPadding = wdcdata_num(x.value("maxPadding"), c.isStock ? 0 : 0.01, cx, p + ".x.maxPadding");
    const QJsonArray ys = o.value("yAxes").toArray();
    for (int i = 0; i < ys.size(); ++i) {
        std::optional<double> tpi;
        c.yAxes.push_back(wdcdata_yaxis(ys[i].toObject(), cx, p + QStringLiteral(".yAxes[%1]").arg(i), &tpi));
        tpis->push_back(tpi);
    }
    const QJsonObject pl = o.value("plot").toObject();
    const QJsonObject col = pl.value("column").toObject();
    c.columnRadius = wdcdata_num(col.value("borderRadius"), 2, cx, p + ".plot.column.borderRadius");
    c.pointPadding = wdcdata_num(col.value("pointPadding"), 0.1, cx, p + ".plot.column.pointPadding");
    c.groupPadding = wdcdata_num(col.value("groupPadding"), 0.2, cx, p + ".plot.column.groupPadding");
    c.fillOpacity = wdcdata_num(pl.value("area").toObject().value("fillOpacity"), 0.25, cx, p + ".plot.area.fillOpacity");
    c.markerRadius = wdcdata_num(pl.value("markerRadius"), 4, cx, p + ".plot.markerRadius");
    const QJsonObject in = o.value("interaction").toObject();
    c.sticky = wdcdata_bool(in.value("sticky"), false);
    c.inactiveFade = wdcdata_bool(in.value("inactiveFade"), false);
    return c;
}

SeriesRef wdcdata_series(const QJsonObject& o, const WdcdataCtx& cx, const QString& p, SeriesExtra* ex) {
    SeriesRef s{};
    s.sid = wdcdata_str(o.value("sid"));
    if (s.sid.isEmpty()) cx.w(p + ".sid", QStringLiteral("thiếu sid"));
    s.si = int(wdcdata_num(o.value("si"), 0, cx, p + ".si"));
    s.nameRaw = wdcdata_str(o.value("name_raw"));
    const QString t = wdcdata_str(o.value("type"));
    s.type = t == QLatin1String("column") ? SeriesType::Column
           : t == QLatin1String("areaspline") ? SeriesType::AreaSpline : SeriesType::Spline;
    if (t != QLatin1String("column") && t != QLatin1String("areaspline") && t != QLatin1String("spline"))
        cx.w(p + ".type", QStringLiteral("kiểu '%1' không hỗ trợ, vẽ như spline").arg(t));
    const QString st = wdcdata_str(o.value("stacking"));
    s.stacking = st == QLatin1String("normal") ? Stacking::Normal : st == QLatin1String("percent") ? Stacking::Percent : Stacking::None;
    s.stack = wdcdata_str(o.value("stack"));
    s.slot = int(wdcdata_num(o.value("slot"), 1, cx, p + ".slot"));
    s.color = wdcdata_color(o.value("color"), cx, p + ".color");
    if (!s.color.isValid()) s.color = QColor(0x58, 0x66, 0x7E);
    const QColor neg = wdcdata_color(o.value("negativeColor"), cx, p + ".negativeColor");
    if (neg.isValid()) s.negativeColor = neg;
    s.lineWidth = wdcdata_num(o.value("lineWidth"), 2, cx, p + ".lineWidth");
    s.dashStyle = o.value("dashStyle").isString() ? o.value("dashStyle").toString() : QStringLiteral("no-marker");
    s.marker = wdcdata_bool(o.value("marker"), false);
    s.zIndex = int(wdcdata_num(o.value("zIndex"), 0, cx, p + ".zIndex"));
    ex->unitNull = !o.value("unit").isString();
    s.unit = wdcdata_str(o.value("unit"));
    s.dateType = wdcdata_str(o.value("date_type"));
    s.kind = wdcdata_str(o.value("kind"));
    const QJsonObject sw = o.value("swatch2").toObject();
    if (!sw.isEmpty()) {
        const QColor a = wdcdata_color(sw.value("pos"), cx, p + ".swatch2.pos");
        const QColor b = wdcdata_color(sw.value("neg"), cx, p + ".swatch2.neg");
        if (a.isValid()) ex->swatchPos = a;
        if (b.isValid()) ex->swatchNeg = b;
    }
    for (const QJsonValue& v : o.value("_inferred").toArray()) ex->inferred << v.toString();
    return s;
}

PaneSpec wdcdata_pane(const QJsonObject& o, const WdcdataCtx& cx, const QString& p) {
    PaneSpec pane;
    pane.raw = o.value("chart").toObject();
    if (pane.raw.isEmpty()) cx.w(p + ".chart", QStringLiteral("thiếu"));
    pane.chart = wdcdata_chart(pane.raw, cx, p + ".chart", &pane.yTickPixelInterval);
    const QJsonArray ss = o.value("series").toArray();
    for (int i = 0; i < ss.size(); ++i) {
        SeriesExtra ex;
        pane.series.push_back(wdcdata_series(ss[i].toObject(), cx, p + QStringLiteral(".series[%1]").arg(i), &ex));
        pane.extra.push_back(ex);
    }
    return pane;
}

CardSpec wdcdata_card(const QJsonObject& o, const WdcdataCtx& cx, const QString& p) {
    CardSpec c;
    c.key = wdcdata_str(o.value("key"));
    if (c.key.isEmpty()) cx.w(p + ".key", QStringLiteral("thiếu"));
    c.kind = o.value("kind").isString() ? o.value("kind").toString()
                                        : (c.key.startsWith(QLatin1String("[macro]")) ? QStringLiteral("macro") : QStringLiteral("aio"));
    c.title = wdcdata_str(o.value("title"));
    const QJsonObject g = o.value("grid").toObject();
    if (g.isEmpty()) cx.w(p + ".grid", QStringLiteral("thiếu, dùng 4x4 tại (0,0)"));
    c.grid.x = int(wdcdata_num(g.value("x"), 0, cx, p + ".grid.x"));
    c.grid.y = int(wdcdata_num(g.value("y"), 0, cx, p + ".grid.y"));
    c.grid.w = std::max(1, int(wdcdata_num(g.value("w"), 4, cx, p + ".grid.w")));
    c.grid.h = std::max(1, int(wdcdata_num(g.value("h"), 4, cx, p + ".grid.h")));
    if (const auto v = wdcdata_optnum(g.value("minW"), cx, p + ".grid.minW")) c.grid.minW = int(*v);
    if (const auto v = wdcdata_optnum(g.value("minH"), cx, p + ".grid.minH")) c.grid.minH = int(*v);
    for (const QJsonValue& b : o.value("buttons").toArray()) c.buttons << b.toString();
    if (c.buttons.isEmpty())
        c.buttons = c.isMacro() ? QStringList{"sync", "calendar", "expand", "settings"} : QStringList{"calendar", "expand", "settings"};
    const QJsonObject lg = o.value("legend").toObject();
    c.legendStyle = lg.value("style").isString() ? lg.value("style").toString() : c.kind;
    c.legendOrder = lg.value("order").isString() ? lg.value("order").toString()
                                                 : (c.isMacro() ? QStringLiteral("series") : QStringLiteral("zIndex_desc"));
    const QJsonObject dr = o.value("default_range").toObject();
    if (dr.value("button").isString()) c.defaultRange.button = dr.value("button").toString();
    if (const auto v = wdcdata_optnum(dr.value("days"), cx, p + ".default_range.days")) c.defaultRange.days = int(*v);
    c.defaultRange.reason = wdcdata_str(dr.value("reason"));
    c.allExact = wdcdata_bool(o.value("all_exact"), false);
    c.alignPanesRight = wdcdata_bool(o.value("align_panes_right"), false);
    const QJsonArray ps = o.value("panes").toArray();
    if (ps.isEmpty()) cx.w(p + ".panes", QStringLiteral("rỗng"));
    for (int i = 0; i < ps.size(); ++i) c.panes.push_back(wdcdata_pane(ps[i].toObject(), cx, p + QStringLiteral(".panes[%1]").arg(i)));
    return c;
}

std::vector<QPointF> wdcdata_points(const QJsonArray& a, const WdcdataCtx& cx, const QString& p) {
    std::vector<QPointF> pts;
    pts.reserve(size_t(a.size()));
    bool sorted = true;
    for (int i = 0; i < a.size(); ++i) {
        const QJsonArray pt = a[i].toArray();
        if (pt.size() < 2 || !pt[0].isDouble()) {
            cx.w(p + QStringLiteral("[%1]").arg(i), QStringLiteral("điểm không hợp lệ, bỏ"));
            continue;
        }
        const double y = pt[1].isDouble() ? pt[1].toDouble() : std::numeric_limits<double>::quiet_NaN();
        if (!pts.empty() && pt[0].toDouble() <= pts.back().x()) sorted = false;
        pts.emplace_back(pt[0].toDouble(), y);
    }
    if (!sorted) {   // DESIGN §4.7: increasing, unique t. Repair (stable, last wins) and say so.
        cx.w(p, QStringLiteral("điểm không tăng dần hoặc trùng t, đã sắp lại"));
        std::stable_sort(pts.begin(), pts.end(), [](const QPointF& l, const QPointF& r) { return l.x() < r.x(); });
        std::vector<QPointF> u;
        for (const QPointF& q : pts) {
            if (!u.empty() && u.back().x() == q.x()) u.back() = q;
            else u.push_back(q);
        }
        pts.swap(u);
    }
    return pts;
}

SeriesEntry wdcdata_entry(const QJsonObject& o, const WdcdataCtx& cx, const QString& p) {
    SeriesEntry e;
    e.present = true;
    const QString st = wdcdata_str(o.value("status"));
    e.data.status = st == QLatin1String("ok") ? Status::Ok : st == QLatin1String("partial") ? Status::Partial : Status::Missing;
    if (st != QLatin1String("ok") && st != QLatin1String("partial") && st != QLatin1String("missing"))
        cx.w(p + ".status", QStringLiteral("'%1' không hợp lệ, coi là missing").arg(st));
    e.data.tier = wdcdata_str(o.value("tier"));
    e.data.freq = wdcdata_str(o.value("freq"));
    e.data.pts = wdcdata_points(o.value("points").toArray(), cx, p + ".points");
    for (const QJsonValue& b : o.value("breaks").toArray()) {
        const QJsonObject bo = b.toObject();
        e.data.breaks.emplace_back(qint64(bo.value("t").toDouble()), bo.value("note").toString());
    }
    // Status must agree with the numbers (DESIGN §4.7 "Luật trạng thái"): no finite value => missing.
    const bool anyValue = std::any_of(e.data.pts.begin(), e.data.pts.end(), [](const QPointF& q) { return std::isfinite(q.y()); });
    if (e.data.status != Status::Missing && !anyValue) {
        cx.w(p, QStringLiteral("trạng thái %1 nhưng không có số, coi là missing").arg(st));
        e.data.status = Status::Missing;
    }
    e.unit = wdcdata_str(o.value("unit"));
    e.asOf = wdcdata_str(o.value("as_of"));
    e.reason = wdcdata_str(o.value("reason"));
    for (const QJsonValue& r : o.value("partial_reasons").toArray()) e.partialReasons << r.toString();
    for (const QJsonValue& t : o.value("tier_spans").toArray()) {
        const QJsonObject to = t.toObject();
        e.tierSpans.push_back({qint64(to.value("from").toDouble()), qint64(to.value("to").toDouble()), to.value("tier").toString()});
    }
    const QJsonObject m = o.value("meta").toObject();
    e.meta = {wdcdata_str(m.value("name")), wdcdata_str(m.value("source_name")), wdcdata_str(m.value("source_ref")),
              wdcdata_str(m.value("release")), wdcdata_str(m.value("last_updated")), {}};
    for (const QJsonValue& n : m.value("notes").toArray()) e.meta.notes << n.toString();
    return e;
}

QString wdcdata_system_dir() {
    const QByteArray env = qgetenv("WDC_SYSTEM_DIR");
    return env.isEmpty() ? QDir::homePath() + QStringLiteral("/SECOND BRAIN-OBSIDIAN/_System") : QString::fromLocal8Bit(env);
}

QJsonObject wdcdata_parse_object(const QByteArray& bytes, QString* err) {
    QJsonParseError pe{};
    const QJsonDocument doc = QJsonDocument::fromJson(bytes, &pe);
    if (pe.error != QJsonParseError::NoError) {
        *err = QStringLiteral("JSON hỏng tại byte %1: %2").arg(pe.offset).arg(pe.errorString());
        return {};
    }
    if (!doc.isObject()) *err = QStringLiteral("gốc không phải đối tượng JSON");
    return doc.object();
}

} // namespace

// ---- CSS colours (VERIFY_W3 V1: Qt reads "#RRGGBBAA" as #AARRGGBB, CSS puts alpha last) -------------------

QColor parseCssColor(const QString& css) {
    const QString h = css.trimmed();
    if (h.startsWith(QLatin1Char('#'))) {
        const int len = int(h.size()) - 1;
        if (len != 3 && len != 4 && len != 6 && len != 8) return QColor();
        const int n = len > 4 ? 2 : 1;
        const int r = wdcdata_hex(h, 1, n), g = wdcdata_hex(h, 1 + n, n), b = wdcdata_hex(h, 1 + 2 * n, n);
        const int a = (len == 4 || len == 8) ? wdcdata_hex(h, 1 + 3 * n, n) : 255;
        if (r < 0 || g < 0 || b < 0 || a < 0) return QColor();
        return QColor(r, g, b, a);
    }
    const QString lower = h.toLower();
    if (lower.startsWith(QLatin1String("rgb"))) {      // rgb(r, g, b) | rgba(r, g, b, a), a in 0..1
        const qsizetype open = lower.indexOf(QLatin1Char('(')), close = lower.lastIndexOf(QLatin1Char(')'));
        if (open < 0 || close <= open) return QColor();
        const QStringList parts = lower.mid(open + 1, close - open - 1).split(QLatin1Char(','));
        if (parts.size() != 3 && parts.size() != 4) return QColor();
        int c[3];
        for (int i = 0; i < 3; ++i) {
            bool ok = false;
            const double v = parts[i].trimmed().toDouble(&ok);
            if (!ok) return QColor();
            c[i] = std::clamp(int(std::lround(v)), 0, 255);
        }
        double a = 1.0;
        if (parts.size() == 4) {
            bool ok = false;
            a = parts[3].trimmed().toDouble(&ok);
            if (!ok) return QColor();
        }
        QColor out(c[0], c[1], c[2]);
        out.setAlphaF(float(std::clamp(a, 0.0, 1.0)));
        return out;
    }
    return QColor::fromString(h);                       // named colours ("transparent", "white"...)
}

// ---- I/O ---------------------------------------------------------------------------------------------

IoStats ioStats() { QMutexLocker l(&wdcdata_io_mutex); return wdcdata_io; }
void resetIoStats() { QMutexLocker l(&wdcdata_io_mutex); wdcdata_io = {}; }

QByteArray readFileCounted(const QString& path, QString* error) {
    wdcdata_count(path, false);
    QFile f(path);
    if (!f.open(QIODevice::ReadOnly)) {
        if (error) *error = QStringLiteral("không mở được %1: %2").arg(path, f.errorString());
        return {};
    }
    QByteArray b = f.readAll();
    if (b.isEmpty() && error) *error = QStringLiteral("tệp rỗng: %1").arg(path);
    return b;
}

bool writeFileCounted(const QString& path, const QByteArray& bytes, QString* error) {
    wdcdata_count(path, true);
    QDir().mkpath(QFileInfo(path).absolutePath());
    QSaveFile f(path);
    if (!f.open(QIODevice::WriteOnly) || f.write(bytes) != bytes.size() || !f.commit()) {
        if (error) *error = QStringLiteral("không ghi được %1: %2").arg(path, f.errorString());
        return false;
    }
    return true;
}

bool fileExistsCounted(const QString& path) {
    wdcdata_count(path, false);
    return QFileInfo::exists(path);
}

// ---- lookups -----------------------------------------------------------------------------------------

const CardSpec* DashSpec::card(const QString& key) const {
    for (const CardSpec& c : cards) if (c.key == key) return &c;
    return nullptr;
}

int DashSpec::maxRow() const {
    int m = 0;
    for (const CardSpec& c : cards) m = std::max(m, c.grid.y + c.grid.h);
    return m;
}

const DashSpec* LayoutsDoc::dash(const QString& id) const {
    for (const DashSpec& d : dashboards) if (d.id == id) return &d;
    return nullptr;
}

const SingleChartSpec* LayoutsDoc::single(const QString& id) const {
    for (const SingleChartSpec& s : singleCharts) if (s.id == id) return &s;
    return nullptr;
}

int LayoutsDoc::cardCount() const {
    int n = 0;
    for (const DashSpec& d : dashboards) n += int(d.cards.size());
    return n;
}

const SeriesEntry& seriesFor(const DashData* d, const QString& sid) {
    static const SeriesEntry missing;
    if (!d) return missing;
    const auto it = d->series.constFind(sid);
    return it == d->series.cend() ? missing : it.value();
}

// ---- parse -------------------------------------------------------------------------------------------

Loaded<LayoutsDoc> parseLayouts(const QByteArray& json, bool requireSchema) {
    Loaded<LayoutsDoc> r;
    QString err;
    const QJsonObject root = wdcdata_parse_object(json, &err);
    if (!err.isEmpty()) { r.error = err; r.errorCode = QStringLiteral("bad_json"); return r; }
    auto doc = std::make_shared<LayoutsDoc>();
    doc->schema = wdcdata_str(root.value("schema"));
    if (requireSchema && doc->schema != QLatin1String(kWdcSchema)) {
        r.error = QStringLiteral("schema '%1', cần '%2'").arg(doc->schema, QLatin1String(kWdcSchema));
        r.errorCode = QStringLiteral("bad_schema");
        return r;
    }
    const QJsonArray dbs = root.value("dashboards").toArray();
    if (dbs.isEmpty()) {
        r.error = QStringLiteral("thiếu mảng 'dashboards'");
        r.errorCode = QStringLiteral("bad_schema");
        return r;
    }
    const WdcdataCtx cx{&doc->warnings};
    std::vector<DashSpec> all;
    for (int i = 0; i < dbs.size(); ++i) {
        const QJsonObject d = dbs[i].toObject();
        const QString p = QStringLiteral("dashboards[%1]").arg(i);
        DashSpec ds;
        ds.id = wdcdata_str(d.value("id"));
        ds.name = wdcdata_str(d.value("name"));
        if (ds.id.isEmpty()) { cx.w(p + ".id", QStringLiteral("thiếu, bỏ bố cục")); continue; }
        const QJsonArray cs = d.value("cards").toArray();
        for (int j = 0; j < cs.size(); ++j) ds.cards.push_back(wdcdata_card(cs[j].toObject(), cx, p + QStringLiteral(".cards[%1]").arg(j)));
        all.push_back(std::move(ds));
    }
    for (const QJsonValue& v : root.value("tab_order").toArray()) doc->tabOrder << v.toString();
    for (const QString& id : std::as_const(doc->tabOrder)) {
        auto it = std::find_if(all.begin(), all.end(), [&](const DashSpec& d) { return d.id == id; });
        if (it == all.end()) { cx.w(QStringLiteral("tab_order"), QStringLiteral("không có bố cục %1").arg(id)); continue; }
        doc->dashboards.push_back(std::move(*it));
        all.erase(it);
    }
    for (DashSpec& d : all) doc->dashboards.push_back(std::move(d));   // not in tab_order: keep, at the end
    doc->tabOrder.clear();
    for (const DashSpec& d : doc->dashboards) doc->tabOrder << d.id;
    doc->defaultDash = wdcdata_str(root.value("default_dash"));
    if (!doc->dash(doc->defaultDash)) doc->defaultDash = doc->tabOrder.value(0);
    const QJsonArray sc = root.value("single_charts").toArray();
    for (int i = 0; i < sc.size(); ++i) {
        const QJsonObject o = sc[i].toObject();
        SingleChartSpec s;
        s.id = wdcdata_str(o.value("id"));
        s.title = wdcdata_str(o.value("title"));
        const QJsonValue dr = o.value("default_range");
        s.defaultRange = dr.isString() ? dr.toString() : dr.toObject().value("button").toString(QStringLiteral("3Y"));
        s.pane = wdcdata_pane(o.value("pane").toObject(), cx, QStringLiteral("single_charts[%1].pane").arg(i));
        s.page = o.value("page").toObject();
        doc->singleCharts.push_back(std::move(s));
    }
    r.value = std::move(doc);
    return r;
}

Loaded<DashData> parseDash(const QByteArray& json, const QString& expectId) {
    Loaded<DashData> r;
    QString err;
    const QJsonObject root = wdcdata_parse_object(json, &err);
    if (!err.isEmpty()) { r.error = err; r.errorCode = QStringLiteral("bad_json"); return r; }
    if (root.value("schema").toString() != QLatin1String(kWdcSchema)) {
        r.error = QStringLiteral("schema '%1', cần '%2'").arg(root.value("schema").toString(), QLatin1String(kWdcSchema));
        r.errorCode = QStringLiteral("bad_schema");
        return r;
    }
    auto d = std::make_shared<DashData>();
    d->dashId = wdcdata_str(root.value("dash_id"));
    if (!expectId.isEmpty() && d->dashId != expectId) {
        r.error = QStringLiteral("dash_id '%1' khác bố cục yêu cầu '%2'").arg(d->dashId, expectId);
        r.errorCode = QStringLiteral("id_mismatch");
        return r;
    }
    d->generated = wdcdata_str(root.value("generated"));
    const QJsonValue sv = root.value("series");
    if (!sv.isObject()) {
        r.error = QStringLiteral("thiếu đối tượng 'series'");
        r.errorCode = QStringLiteral("bad_schema");
        return r;
    }
    const WdcdataCtx cx{&d->warnings};
    const QJsonObject so = sv.toObject();
    d->series.reserve(so.size());
    for (auto it = so.begin(); it != so.end(); ++it)
        d->series.insert(it.key(), wdcdata_entry(it.value().toObject(), cx, QStringLiteral("series[%1]").arg(it.key())));
    r.value = std::move(d);
    return r;
}

// ---- disk --------------------------------------------------------------------------------------------

QString defaultStateDir() {
    const QByteArray env = qgetenv("WDC_STATE_DIR");
    if (!env.isEmpty()) return QString::fromLocal8Bit(env);
    return wdcdata_system_dir() + QStringLiteral("/fincept_bridge/state/widata_clone");
}

QString defaultLayoutConstPath() {
    const QByteArray env = qgetenv("WDC_LAYOUT_CONST");
    if (!env.isEmpty()) return QString::fromLocal8Bit(env);
    return wdcdata_system_dir() + QStringLiteral("/fincept_bridge/data/widata_clone/layout_const.json");
}

BuildState readCurrent(const QString& stateDir) {
    BuildState b;
    b.stateDir = stateDir;
    const QString cur = QDir(stateDir).filePath(QStringLiteral("current.json"));
    QString err;
    const QByteArray bytes = readFileCounted(cur, &err);
    if (bytes.isEmpty()) {
        b.error = QStringLiteral("chưa có bản dựng (%1)").arg(err);
        b.errorCode = QStringLiteral("no_current");
        return b;
    }
    const QJsonObject root = wdcdata_parse_object(bytes, &err);
    if (!err.isEmpty()) { b.error = cur + QStringLiteral(": ") + err; b.errorCode = QStringLiteral("bad_json"); return b; }
    if (root.value("schema").toString() != QLatin1String(kWdcSchema) || !root.value("build").isString()) {
        b.error = cur + QStringLiteral(": cần schema '%1' và khoá 'build'").arg(QLatin1String(kWdcSchema));
        b.errorCode = QStringLiteral("bad_schema");
        return b;
    }
    b.buildDir = root.value("build").toString();
    if (QFileInfo(b.buildDir).isRelative()) b.buildDir = QDir(stateDir).filePath(b.buildDir);
    b.manifest = root.value("manifest").toObject();
    b.generated = b.manifest.value("generated").toString();
    b.policy = b.manifest.value("source_policy").toString();
    return b;
}

Loaded<LayoutsDoc> loadLayoutsFile(const QString& path, bool requireSchema) {
    QString err;
    const QByteArray bytes = readFileCounted(path, &err);
    if (bytes.isEmpty()) return {nullptr, err, QStringLiteral("no_file")};
    Loaded<LayoutsDoc> r = parseLayouts(bytes, requireSchema);
    if (!r.ok()) r.error = path + QStringLiteral(": ") + r.error;
    return r;
}

Loaded<LayoutsDoc> loadLayouts(const BuildState& b, const QString& layoutConstPath) {
    Loaded<LayoutsDoc> fromBuild;
    if (b.ok()) {
        fromBuild = loadLayoutsFile(QDir(b.buildDir).filePath(QStringLiteral("layouts.json")), true);
        if (fromBuild.ok()) return fromBuild;
    }
    Loaded<LayoutsDoc> lc = loadLayoutsFile(layoutConstPath, false);
    const QString why = b.ok() ? fromBuild.error : b.error;
    if (!lc.ok()) return {nullptr, why + QStringLiteral("; ") + lc.error, b.ok() ? fromBuild.errorCode : b.errorCode};
    auto doc = std::make_shared<LayoutsDoc>(*lc.value);
    doc->fromLayoutConst = true;
    doc->warnings.prepend(QStringLiteral("dùng layout_const.json (chỉ hình thức): ") + why);
    return {std::move(doc), why, b.ok() ? fromBuild.errorCode : b.errorCode};
}

Loaded<DashData> loadDash(const QString& buildDir, const QString& dashId) {
    const QString path = QDir(buildDir).filePath(QStringLiteral("dash_%1.json").arg(dashId));
    QString err;
    const QByteArray bytes = readFileCounted(path, &err);
    if (bytes.isEmpty()) return {nullptr, err, QStringLiteral("no_file")};
    Loaded<DashData> r = parseDash(bytes, dashId);
    if (!r.ok()) r.error = path + QStringLiteral(": ") + r.error;
    return r;
}

Loaded<DashData> loadSingle(const QString& buildDir, const QString& singleId) {
    const QString path = QDir(buildDir).filePath(QStringLiteral("single_%1.json").arg(singleId));
    QString err;
    const QByteArray bytes = readFileCounted(path, &err);
    if (bytes.isEmpty()) return {nullptr, err, QStringLiteral("no_file")};
    Loaded<DashData> r = parseDash(bytes, QString());
    if (!r.ok()) r.error = path + QStringLiteral(": ") + r.error;
    return r;
}

// ---- assembly ----------------------------------------------------------------------------------------

std::optional<qint64> cardRefMax(const CardSpec& c, const DashData* d) {
    std::optional<qint64> m;
    for (const PaneSpec& p : c.panes)
        for (const SeriesRef& s : p.series) {
            const SeriesEntry& e = seriesFor(d, s.sid);
            if (e.data.status == Status::Missing) continue;
            for (auto it = e.data.pts.rbegin(); it != e.data.pts.rend(); ++it)
                if (std::isfinite(it->y())) {
                    const qint64 t = qint64(it->x());
                    if (!m || t > *m) m = t;
                    break;
                }
        }
    return m;
}

bool paneHasData(const PaneSpec& p, const DashData* d) {
    return std::any_of(p.series.begin(), p.series.end(),
                       [&](const SeriesRef& s) { return seriesFor(d, s.sid).data.status != Status::Missing; });
}

bool cardHasData(const CardSpec& c, const DashData* d) {
    return std::any_of(c.panes.begin(), c.panes.end(), [&](const PaneSpec& p) { return paneHasData(p, d); });
}

ChartInput makeChartInput(const PaneSpec& pane, const DashData* d, QSizeF size, std::optional<qint64> xMin,
                          std::optional<qint64> xMax, bool padAuto, MetricsProfile profile, bool expanded) {
    ChartInput in{};
    in.spec = &pane.chart;
    for (const SeriesRef& s : pane.series) {
        in.refs.push_back(&s);
        in.data.push_back(&seriesFor(d, s.sid).data);
    }
    in.visible.assign(pane.series.size(), true);
    in.xMin = xMin;
    in.xMax = xMax;
    in.padAuto = padAuto;
    in.size = size;
    in.profile = profile;
    in.expanded = expanded;
    return in;
}

} // namespace fincept::screens::wdc
