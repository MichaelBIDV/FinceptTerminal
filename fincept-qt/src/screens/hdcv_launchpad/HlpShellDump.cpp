// src/screens/hdcv_launchpad/HlpShellDump.cpp
// HĐCV LAUNCHPAD shell — harness hooks: Shell::grabUnrolled() (the grid laid out without scrolling, like
// Chrome's full-page capture) and Shell::dumpGeometryJson() (panel geometry + text in the shape of
// ref/*_dump.json, see harness compare.py). Read-only views of the shell state.
// See HlpShell_p.h for how the shell is split.
#include "screens/hdcv_launchpad/HlpShell_p.h"

#include "screens/hdcv_launchpad/HlpTheme.h"

#include <QJsonDocument>
#include <QPainter>

#include <cmath>
#include <optional>

namespace fincept::screens::hlp {

namespace {

double hlpshdump_r1(double v) {
    return std::round(v * 10.0) / 10.0;
}

QJsonArray hlpshdump_rectJ(const QRectF& r) {
    return {hlpshdump_r1(r.x()), hlpshdump_r1(r.y()), hlpshdump_r1(r.width()), hlpshdump_r1(r.height())};
}

// ---- HlpView geometry dumps (engine format: array of nodes or {nodes:[…]}; rect or x/y/w/h) ----

void hlpshdump_flatten(const QJsonArray& in, QJsonArray& out) {
    for (const QJsonValue& v : in) {
        const QJsonObject o = v.toObject();
        out.append(o);
        for (const char* kids : {"kids", "children"})
            if (o.value(QLatin1String(kids)).isArray())
                hlpshdump_flatten(o.value(QLatin1String(kids)).toArray(), out);
    }
}

QJsonArray hlpshdump_nodes(const QString& json) {
    const QJsonDocument d = QJsonDocument::fromJson(json.toUtf8());
    QJsonArray out;
    if (d.isArray())
        hlpshdump_flatten(d.array(), out);
    else if (d.isObject())
        hlpshdump_flatten(d.object().value(QStringLiteral("nodes")).toArray(), out);
    return out;
}

std::optional<QRectF> hlpshdump_nodeRect(const QJsonObject& n) {
    const QJsonArray r = n.value(QStringLiteral("rect")).toArray();
    if (r.size() == 4)
        return QRectF(r[0].toDouble(), r[1].toDouble(), r[2].toDouble(), r[3].toDouble());
    if (n.contains(QStringLiteral("x")) && n.contains(QStringLiteral("y")))
        return QRectF(n.value(QStringLiteral("x")).toDouble(), n.value(QStringLiteral("y")).toDouble(),
                      n.value(QStringLiteral("w")).toDouble(), n.value(QStringLiteral("h")).toDouble());
    return std::nullopt;
}

/// Node moved from view coordinates to window coordinates.
QJsonObject hlpshdump_shift(QJsonObject n, const QPointF& d) {
    if (const auto r = hlpshdump_nodeRect(n)) {
        if (n.contains(QStringLiteral("rect"))) {
            n.insert(QStringLiteral("rect"), hlpshdump_rectJ(r->translated(d)));
        } else {
            n.insert(QStringLiteral("x"), hlpshdump_r1(r->x() + d.x()));
            n.insert(QStringLiteral("y"), hlpshdump_r1(r->y() + d.y()));
        }
    }
    n.remove(QStringLiteral("kids"));
    n.remove(QStringLiteral("children"));
    return n;
}

/// Rect (window coordinates) of the first node carrying `key`.
std::optional<QRectF> hlpshdump_keyRect(const QJsonArray& nodes, const QString& key, const QPointF& d) {
    for (const QJsonValue& v : nodes) {
        const QJsonObject o = v.toObject();
        if (o.value(QStringLiteral("key")).toString() == key)
            if (const auto r = hlpshdump_nodeRect(o))
                return r->translated(d);
    }
    return std::nullopt;
}

} // namespace

using namespace shell_detail;

QImage Shell::grabUnrolled() {
    d_->layoutGrid();
    const int W = width();
    const int H = std::max(height(), int(hlpsh_kBarH) + d_->grid->content->height());
    const qreal dpr = devicePixelRatioF();
    QImage img(QSize(int(std::ceil(W * dpr)), int(std::ceil(H * dpr))), QImage::Format_ARGB32_Premultiplied);
    img.setDevicePixelRatio(dpr);
    img.fill(pal().bg);
    QPainter p(&img);
    d_->bar->render(&p, QPoint(0, 0));
    d_->grid->content->render(&p, QPoint(0, int(hlpsh_kBarH))); // the whole content, not the scrolled window
    p.end();
    return img;
}

QString Shell::dumpGeometryJson() {
    d_->layoutGrid();
    const QPointF barOrigin(0, hlpsh_kBarH);
    QJsonObject o;
    const hlpsh_View* cv = d_->cur();
    o.insert(QStringLiteral("view"), cv ? cv->name : QString());
    o.insert(QStringLiteral("vw"), width());
    o.insert(QStringLiteral("vh"), height());
    o.insert(QStringLiteral("bar"), QJsonObject{{QStringLiteral("rect"), hlpshdump_rectJ(QRectF(0, 0, width(), hlpsh_kBarH))}});

    // barItems — same selectors as ref/*_dump.json ("" = the MÃ label)
    const QJsonArray barNodes = hlpshdump_nodes(d_->bar->dumpGeometryJson());
    const QPointF barShift(d_->bar->pos());
    QJsonArray items;
    const auto item = [&](const QString& key, const QString& sel, const QString& txt) {
        if (const auto r = hlpshdump_keyRect(barNodes, key, barShift))
            items.append(QJsonObject{{QStringLiteral("sel"), sel}, {QStringLiteral("text"), txt},
                                     {QStringLiteral("rect"), hlpshdump_rectJ(*r)}});
    };
    item(QStringLiteral("brand"), QStringLiteral("brand"), hlpsh_brand());
    if (d_->dataOk)
        for (const hlpsh_View& v : d_->views)
            item(QStringLiteral("vtab:") + v.key, v.key == d_->view ? QStringLiteral("vtab[sel]") : QStringLiteral("vtab"),
                 v.name);
    item(QStringLiteral("label"), QString(), QStringLiteral("MÃ"));
    item(QStringLiteral("tick"), QStringLiteral("tick"), d_->tick->text());
    item(QStringLiteral("go"), QStringLiteral("go"), QStringLiteral("GO"));
    item(QStringLiteral("add"), QStringLiteral("add"), QStringLiteral("+ Component"));
    item(QStringLiteral("save"), QStringLiteral("save"), QStringLiteral("Lưu View"));
    item(QStringLiteral("reset"), QStringLiteral("reset"), QStringLiteral("Mặc định"));
    item(QStringLiteral("theme"), QStringLiteral("theme"), QStringLiteral("◐"));
    o.insert(QStringLiteral("barItems"), items);
    o.insert(QStringLiteral("grid"),
             QJsonObject{{QStringLiteral("rect"), hlpshdump_rectJ(QRectF(0, hlpsh_kBarH, width(), height() - hlpsh_kBarH))}});

    QJsonArray panels;
    for (const hlpsh_Frame* f : d_->frames) {
        // window coordinates of the unrolled layout: #grid content + the bar
        const QPointF origin = f->exact.topLeft() + barOrigin;
        const float iw = float(f->exact.width()) - 2.0f;
        QJsonObject p;
        p.insert(QStringLiteral("title"), f->rawTitle);
        p.insert(QStringLiteral("rect"), hlpshdump_rectJ(QRectF(origin, f->exact.size())));
        if (f->hd) {
            const QJsonArray hn = hlpshdump_nodes(f->hd->dumpGeometryJson());
            const QPointF hs = QPointF(f->pos() + f->hd->pos()) + barOrigin;
            QJsonObject hd{{QStringLiteral("rect"), hlpshdump_rectJ(QRectF(origin + QPointF(1, 1), QSizeF(iw, f->hdH)))}};
            for (const char* k : {"h2", "link"})
                if (const auto r = hlpshdump_keyRect(hn, QLatin1String(k), hs))
                    hd.insert(QLatin1String(k), QJsonObject{{QStringLiteral("rect"), hlpshdump_rectJ(*r)}});
            QJsonObject as{{QStringLiteral("text"), f->asof}};
            if (const auto r = hlpshdump_keyRect(hn, QStringLiteral("asof"), hs))
                as.insert(QStringLiteral("rect"), hlpshdump_rectJ(*r));
            hd.insert(QStringLiteral("asof"), as);
            static const QString glyph[3] = {QStringLiteral("◀"), QStringLiteral("▶"), QStringLiteral("✕")};
            QJsonArray btns;
            for (int a = 0; a < 3; ++a)
                if (const auto r = hlpshdump_keyRect(hn, QStringLiteral("hbtn%1").arg(a), hs))
                    btns.append(QJsonObject{{QStringLiteral("t"), glyph[a]}, {QStringLiteral("rect"), hlpshdump_rectJ(*r)}});
            hd.insert(QStringLiteral("hbtn"), btns);
            p.insert(QStringLiteral("hd"), hd);
        }
        p.insert(QStringLiteral("bd"),
                 QJsonObject{{QStringLiteral("rect"),
                              hlpshdump_rectJ(QRectF(origin + QPointF(1, 1 + f->hdH), QSizeF(iw, f->bdH)))},
                             {QStringLiteral("scrollH"), qRound(f->body->contentHeight(float(f->body->subpixelGeometry().width())))},
                             {QStringLiteral("maxH"), QStringLiteral("%1px").arg(f->maxBody())}});
        p.insert(QStringLiteral("asof"), f->asof);
        p.insert(QStringLiteral("text"), f->body->plainText());
        const QPointF bs = QPointF(f->pos() + f->body->pos()) + barOrigin;
        QJsonArray nodes;
        for (const QJsonValue& n : hlpshdump_nodes(f->body->dumpGeometryJson()))
            nodes.append(hlpshdump_shift(n.toObject(), bs));
        p.insert(QStringLiteral("nodes"), nodes);
        panels.append(p);
    }
    o.insert(QStringLiteral("panels"), panels);
    return QString::fromUtf8(QJsonDocument(o).toJson(QJsonDocument::Indented));
}

} // namespace fincept::screens::hlp
