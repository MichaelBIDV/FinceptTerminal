#pragma once
// Equity Trading types — UI state, enums, constants
// Kept separate from trading engine types to avoid coupling.

#include "ui/theme/ThemeManager.h"

#include <QColor>
#include <QString>
#include <QStringList>
#include <QVector>

namespace fincept::screens::equity {

// ── Enums ──────────────────────────────────────────────────────────────────

enum class BottomTab { Positions, Holdings, Orders, Funds, Stats };

enum class TradingMode { Paper, Live };

// ── Danh sách mặc định ─────────────────────────────────────────────────────
//
// Đổi ngày 21/09/2026: ba rổ cũ là NIFTY của thị trường ẤN ĐỘ — đúng với bản gốc upstream
// nhưng sai với chủ hệ. Rổ VN dưới đây SINH TỪ fincept.db (bảng watchlists + watchlist_stocks,
// hai rổ 'VN30' và 'VN100' do lớp dữ liệu nạp), nên nếu rổ trong DB đổi thì sinh lại tệp này
// thay vì sửa tay. Mã để TRẦN, không hậu tố: yfinance_data.py đã định tuyến mã VN sang kho
// vnstock (giá bảng HOSE/HNX/UPCOM), hậu tố .NS/.BO chỉ dành cho sàn Ấn.

inline const QStringList DEFAULT_WATCHLIST = {
    "ACB", "BCM", "BID", "CTG", "FPT", "GAS", "GVR",
    "HDB", "HPG", "LPB", "MBB", "MSN", "MWG", "PLX",
    "POW", "SAB", "SHB", "SSB", "SSI", "STB", "TCB",
    "TPB", "VCB", "VHM", "VIB", "VIC", "VJC", "VNM",
    "VPB", "VRE",
};

inline const QStringList VN100_WATCHLIST = {
    "ACB", "ANV", "BCM", "BID", "BMP", "BSI", "BSR",
    "BVH", "BWE", "CII", "CMG", "CTD", "CTG", "CTR",
    "CTS", "DBC", "DCM", "DGC", "DGW", "DIG", "DPM",
    "DSE", "DXG", "DXS", "EIB", "EVF", "FPT", "FRT",
    "FTS", "GAS", "GEE", "GEX", "GMD", "GVR", "HAG",
    "HCM", "HDB", "HDC", "HDG", "HHV", "HPG", "HSG",
    "HT1", "IMP", "KBC", "KDC", "KDH", "KOS", "LPB",
    "MBB", "MSB", "MSN", "MWG", "NAB", "NKG", "NLG",
    "NT2", "NVL", "OCB", "PAN", "PC1", "PDR", "PHR",
    "PLX", "PNJ", "POW", "PVD", "PVT", "REE", "SAB",
    "SBT", "SCS", "SHB", "SIP", "SJS", "SSB", "SSI",
    "STB", "SZC", "TCB", "TCH", "TPB", "VCB", "VCG",
    "VCI", "VGC", "VHC", "VHM", "VIB", "VIC", "VIX",
    "VJC", "VND", "VNM", "VPB", "VPI", "VPL", "VRE",
    "VSC", "VTP",
};

// Mã trọng yếu của Mỹ: hợp của DJ30 và nhóm vốn hoá lớn NASDAQ/S&P 500.
// Thành phần chỉ số có thay đổi theo kỳ cơ cấu — đây là rổ THEO DÕI, không phải bản sao
// chính thức của chỉ số nào.
inline const QStringList US_WATCHLIST = {
    "AAPL", "MSFT", "NVDA", "GOOGL", "AMZN", "META", "AVGO",
    "TSLA", "JPM", "V", "UNH", "XOM", "JNJ", "PG",
    "HD", "MA", "COST", "WMT", "MRK", "CVX", "KO",
    "MCD", "CSCO", "IBM", "GS", "CAT", "BA", "AXP",
    "DIS", "AMGN", "HON", "CRM", "VZ", "MMM", "TRV",
    "SHW",
};

// Giữ lại cho môi giới Ấn Độ (EquityTradingScreen_Watchlists.cpp chỉ gieo rổ này khi
// profile().region == "IN"). Không còn là mặc định của máy này.
// Full NIFTY 50 constituents (NSE) — seeded as the default watchlist for Indian
// brokers (profile region == "IN"). Plain symbols; each broker's resolver maps them.
inline const QStringList NIFTY50_WATCHLIST = {
    "ADANIENT",   "ADANIPORTS", "APOLLOHOSP", "ASIANPAINT", "AXISBANK",   "BAJAJ-AUTO", "BAJAJFINSV",
    "BAJFINANCE", "BEL",        "BHARTIARTL", "CIPLA",      "COALINDIA",  "DIVISLAB",   "DRREDDY",
    "EICHERMOT",  "GRASIM",     "HCLTECH",    "HDFCBANK",   "HDFCLIFE",   "HEROMOTOCO", "HINDALCO",
    "HINDUNILVR", "ICICIBANK",  "INDUSINDBK", "INFY",       "ITC",        "JIOFIN",     "JSWSTEEL",
    "KOTAKBANK",  "LT",         "M&M",        "MARUTI",     "NESTLEIND",  "NTPC",       "ONGC",
    "POWERGRID",  "RELIANCE",   "SBILIFE",    "SBIN",       "SHRIRAMFIN", "SUNPHARMA",  "TATACONSUM",
    "TATASTEEL",  "TCS",        "TECHM",      "TITAN",      "TRENT",      "ULTRACEMCO", "WIPRO",
};

// ── Constants ──────────────────────────────────────────────────────────────

inline constexpr double DEFAULT_PAPER_BALANCE = 1000000.0; // 10 Lakh INR
inline constexpr int OHLCV_FETCH_COUNT = 200;
inline constexpr int QUOTE_POLL_MS = 5000;
inline constexpr int PORTFOLIO_POLL_MS = 3000;
inline constexpr int WATCHLIST_POLL_MS = 10000;
inline constexpr int CLOCK_UPDATE_MS = 1000;

// ── Design System Colors — live from ThemeManager ──────────────────────────
// These are inline functions so they reflect the active theme at call time.

inline QColor COLOR_BUY() {
    return QColor(fincept::ui::ThemeManager::instance().tokens().positive);
}
inline QColor COLOR_SELL() {
    return QColor(fincept::ui::ThemeManager::instance().tokens().negative);
}
inline QColor COLOR_DIM() {
    return QColor(fincept::ui::ThemeManager::instance().tokens().text_secondary);
}
inline QColor COLOR_ACCENT() {
    return QColor(fincept::ui::ThemeManager::instance().tokens().accent);
}

inline QColor BG_BASE() {
    return QColor(fincept::ui::ThemeManager::instance().tokens().bg_base);
}
inline QColor BG_SURFACE() {
    return QColor(fincept::ui::ThemeManager::instance().tokens().bg_surface);
}
inline QColor BG_RAISED() {
    return QColor(fincept::ui::ThemeManager::instance().tokens().bg_raised);
}
inline QColor BG_HOVER() {
    return QColor(fincept::ui::ThemeManager::instance().tokens().bg_hover);
}

inline QColor BORDER_DIM() {
    return QColor(fincept::ui::ThemeManager::instance().tokens().border_dim);
}
inline QColor BORDER_MED() {
    return QColor(fincept::ui::ThemeManager::instance().tokens().border_med);
}
inline QColor BORDER_BRIGHT() {
    return QColor(fincept::ui::ThemeManager::instance().tokens().border_bright);
}

inline QColor TEXT_PRIMARY() {
    return QColor(fincept::ui::ThemeManager::instance().tokens().text_primary);
}
inline QColor TEXT_SECONDARY() {
    return QColor(fincept::ui::ThemeManager::instance().tokens().text_secondary);
}
inline QColor TEXT_TERTIARY() {
    return QColor(fincept::ui::ThemeManager::instance().tokens().text_tertiary);
}

inline QColor COLOR_WARNING() {
    return QColor(fincept::ui::ThemeManager::instance().tokens().warning);
}
inline QColor COLOR_INFO() {
    return QColor(fincept::ui::ThemeManager::instance().tokens().info);
}
inline QColor ROW_ALT() {
    return QColor(fincept::ui::ThemeManager::instance().tokens().row_alt);
}

// ── Exchange → Currency mapping ────────────────────────────────────────────

inline QString exchange_currency(const QString& exchange) {
    if (exchange == "NSE" || exchange == "BSE" || exchange == "NFO" || exchange == "MCX" || exchange == "CDS")
        return "INR";
    if (exchange == "NYSE" || exchange == "NASDAQ" || exchange == "AMEX" || exchange == "CBOE")
        return "USD";
    if (exchange == "LSE")
        return "GBP";
    if (exchange == "XETRA" || exchange == "EURONEXT")
        return "EUR";
    return "USD";
}

inline QString currency_symbol(const QString& currency) {
    if (currency == "INR")
        return QString::fromUtf8("\u20B9");
    if (currency == "GBP")
        return QString::fromUtf8("\u00A3");
    if (currency == "EUR")
        return QString::fromUtf8("\u20AC");
    if (currency == "JPY")
        return QString::fromUtf8("\u00A5");
    return "$";
}

// \u2500\u2500 Funds / Stats view-models
// \u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500
// The bottom-panel Funds and Stats tabs render from these view-models, so the
// panel is decoupled from the data source: live mode fills them from BrokerFunds
// (the subset it knows), paper mode fills the full set from the paper engine.

struct EquityFundsView {
    QString currency = QStringLiteral("\u20B9"); // symbol, e.g. \u20B9 / $
    bool is_paper = false;

    double available = 0.0;       // free cash / available margin
    double used_margin = 0.0;     // locked by open intraday positions + pending orders
    double total_equity = 0.0;    // net worth = available + used + holdings + open P&L
    double opening_balance = 0.0; // initial / start-of-day balance
    double holdings_value = 0.0;  // current value of CNC delivery holdings
    double realized_pnl = 0.0;    // realized P&L (today)
    double unrealized_pnl = 0.0;  // open positions + holdings mark-to-market
    double collateral = 0.0;      // pledged collateral (live brokers)
    double margin_util_pct = 0.0; // used / (used + available) * 100
};

struct EquityStatsView {
    QString currency = QStringLiteral("\u20B9");

    double net_pnl = 0.0;   // realized + unrealized
    double today_pnl = 0.0; // realized today
    double realized_pnl = 0.0;
    double unrealized_pnl = 0.0;
    double return_pct = 0.0; // net_pnl / opening_balance * 100
    double win_rate = 0.0;   // 0..1
    long long total_trades = 0;
    long long winning_trades = 0;
    long long losing_trades = 0;
    double profit_factor = 0.0;
    double avg_win = 0.0;
    double avg_loss = 0.0;
    double largest_win = 0.0;
    double largest_loss = 0.0;
    double total_fees = 0.0;
    double turnover = 0.0;
};

} // namespace fincept::screens::equity
