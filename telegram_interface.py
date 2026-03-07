"""
telegram_interface.py
Telegram bot interface using python-telegram-bot v20/v21 async API.
All messages use plain text. MT5 auto-detects install path.
"""

import os
from datetime import datetime

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application,
    CommandHandler,
    ContextTypes,
    CallbackQueryHandler,
    ConversationHandler,
    MessageHandler,
    filters,
)

import MetaTrader5 as mt5

from account_manager import add_account, get_account, list_accounts
from challenge_config import get_current_level
from config import ALLOWED_CHAT_IDS, TELEGRAM_TOKEN
from execution import close_all_positions
from logger import compute_daily_stats, read_today_trades, logger

# analysis helpers (weekday/session statistics)
from analyse_trades import load_trades, summary_by_weekday, summary_by_session

# ── Conversation states ────────────────────────────────────────────────────────
ADD_LOGIN, ADD_PASSWORD, ADD_SERVER, ADD_ALIAS = range(4)

# ── Shared state (injected from main.py) ──────────────────────────────────────
_trading_state: dict = {
    "enabled": False,
    "risk_manager": None,
    "alias": None,
}

# ── Known MT5 install paths to try ────────────────────────────────────────────
MT5_CANDIDATE_PATHS = [
    r"C:\Program Files\MetaTrader 5\terminal64.exe",
    r"C:\Program Files (x86)\MetaTrader 5\terminal64.exe",
    r"C:\Program Files\Exness MT5 Terminal\terminal64.exe",
    r"C:\Program Files (x86)\Exness MT5 Terminal\terminal64.exe",
    r"C:\Program Files\Exness Technologies Ltd\Exness MT5 Terminal\terminal64.exe",
]


def _find_and_init_mt5() -> bool:
    """
    Try to initialize MT5 by scanning known paths first,
    then fall back to the default (uses MT5_PATH from config if set).
    Returns True on success.
    """
    from config import MT5_PATH

    # If user set a custom path in config.py, try that first
    if MT5_PATH and os.path.exists(MT5_PATH):
        if mt5.initialize(path=MT5_PATH):
            logger.info("MT5 initialized from config MT5_PATH: %s", MT5_PATH)
            return True

    # Try known candidate paths
    for candidate in MT5_CANDIDATE_PATHS:
        if os.path.exists(candidate):
            if mt5.initialize(path=candidate):
                logger.info("MT5 initialized from: %s", candidate)
                return True

    # Last resort: let MT5 library find it on its own
    if mt5.initialize():
        logger.info("MT5 initialized via default detection.")
        return True

    return False


def inject_state(trading_state: dict) -> None:
    """Called by main.py to inject shared mutable state reference."""
    global _trading_state
    _trading_state = trading_state


def _safe(text: str) -> str:
    """Remove characters that can break Telegram messages."""
    return str(text).replace("<", "").replace(">", "").replace("&", "and")


def _is_authorized(update: Update) -> bool:
    cid = update.effective_chat.id
    if ALLOWED_CHAT_IDS and cid not in ALLOWED_CHAT_IDS:
        return False
    return True


def _auth_required(func):
    """Decorator that blocks unauthorized chat IDs."""
    async def wrapper(update: Update, context: ContextTypes.DEFAULT_TYPE):
        if not _is_authorized(update):
            await update.message.reply_text("Unauthorized.")
            return
        return await func(update, context)
    wrapper.__name__ = func.__name__
    return wrapper


# ── /start ─────────────────────────────────────────────────────────────────────
@_auth_required
async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if _trading_state.get("alias") is None:
        await update.message.reply_text("No account selected. Use /select_account first.")
        return
    _trading_state["enabled"] = True
    if _trading_state.get("risk_manager"):
        _trading_state["risk_manager"].resume()
    await update.message.reply_text("Trading is now ENABLED.")
    logger.info("Trading enabled via Telegram /start")


# ── /stop ──────────────────────────────────────────────────────────────────────
@_auth_required
async def cmd_stop(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    _trading_state["enabled"] = False
    await update.message.reply_text("Trading PAUSED. Open positions remain open.")
    logger.info("Trading paused via Telegram /stop")


# ── /kill ──────────────────────────────────────────────────────────────────────
@_auth_required
async def cmd_kill(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    _trading_state["enabled"] = False
    if _trading_state.get("risk_manager"):
        _trading_state["risk_manager"].force_halt()
    closed = close_all_positions()
    await update.message.reply_text("Trading KILLED. " + str(closed) + " position(s) closed.")
    logger.warning("Trading killed via Telegram /kill")


# ── /status ────────────────────────────────────────────────────────────────────
@_auth_required
async def cmd_status(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    account = mt5.account_info()
    if account is None:
        await update.message.reply_text("MT5 not connected.\nUse /select_account to connect first.")
        return

    balance = account.balance
    equity = account.equity
    trades = read_today_trades()
    daily_pnl = sum(float(t["pnl"]) for t in trades)
    level = get_current_level(balance)
    enabled = _trading_state.get("enabled", False)
    alias = _safe(_trading_state.get("alias", "N/A"))

    lines = [
        "=== Bot Status ===",
        "Account : " + alias,
        "Trading : " + ("ON" if enabled else "OFF"),
        "",
        "Balance   : $" + "{:,.2f}".format(balance),
        "Equity    : $" + "{:,.2f}".format(equity),
        "Daily PnL : $" + "{:+.2f}".format(daily_pnl),
        "",
        "Level  : " + str(level["level"]) + "/30",
        "Lot    : " + str(level["lot"]),
        "Target : $" + "{:,.2f}".format(level["balance"]),
    ]
    await update.message.reply_text("\n".join(lines))


# ── /daily_report ──────────────────────────────────────────────────────────────
@_auth_required
async def cmd_daily_report(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    trades = read_today_trades()
    stats = compute_daily_stats(trades)
    account = mt5.account_info()
    balance = account.balance if account else 0.0
    level = get_current_level(balance)

    lines = [
        "=== Daily Report ===",
        "Date: " + datetime.utcnow().strftime("%Y-%m-%d") + " UTC",
        "",
        "Total Trades : " + str(stats["total"]),
        "Wins         : " + str(stats["wins"]),
        "Losses       : " + str(stats["losses"]),
        "Win Rate     : " + str(stats["win_rate"]) + "%",
        "Daily PnL    : $" + "{:+.2f}".format(stats["daily_pnl"]),
        "Max Drawdown : " + str(stats["max_drawdown"]) + "%",
        "",
        "Level   : " + str(level["level"]) + "/30",
        "Balance : $" + "{:,.2f}".format(balance),
    ]

    # include a quick weekday/session breakdown using full history
    try:
        full = load_trades()
        if not full.empty:
            wkd = summary_by_weekday(full)
            sess = summary_by_session(full)
            lines.append("")
            lines.append("=== All-time performance ===")
            # show just win rate by weekday (shortened)
            wk_lines = [f"{idx}: {row.win_rate:.1f}% ({int(row.total_trades)} trades)" for idx,row in wkd.iterrows()]
            lines.append("Weekdays – " + "; ".join(wk_lines))
            # show session pnl summary
            sess_lines = [f"{idx}:{row.total_pnl:+.0f}" for idx,row in sess.iterrows()]
            lines.append("Sessions – " + "; ".join(sess_lines))
    except Exception:
        # if pandas not available or something fails, ignore
        pass

    await update.message.reply_text("\n".join(lines))


# ── /add_account conversation ──────────────────────────────────────────────────
@_auth_required
async def cmd_add_account(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    msg = (
        "=== Add MT5 Account ===\n\n"
        "How to find your Exness Demo credentials:\n"
        "1. Log in to exness.com\n"
        "2. Go to My Accounts section\n"
        "3. Click on your demo account\n"
        "4. Click Account Info or the 3-dot menu\n"
        "5. You will see Login number, Server, and Trading Password\n\n"
        "Enter your MT5 Login number:"
    )
    await update.message.reply_text(msg)
    return ADD_LOGIN


async def _get_login(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    text = update.message.text.strip()
    if not text.isdigit():
        await update.message.reply_text("Login must be a number. Please try again:")
        return ADD_LOGIN
    context.user_data["login"] = int(text)
    await update.message.reply_text(
        "Enter your MT5 Password:\n\n"
        "For Exness: find it in exness.com > My Accounts > Account Info > Trading Password"
    )
    return ADD_PASSWORD


async def _get_password(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    context.user_data["password"] = update.message.text.strip()
    await update.message.reply_text(
        "Enter your MT5 Server name.\n\n"
        "For Exness demo it is usually:\n"
        "  Exness-MT5Trial6\n"
        "  Exness-MT5Trial7\n\n"
        "For Exness real it is usually:\n"
        "  Exness-MT5Real9\n\n"
        "Find exact name in exness.com > Account Info > Server"
    )
    return ADD_SERVER


async def _get_server(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    context.user_data["server"] = update.message.text.strip()
    await update.message.reply_text(
        "Enter a friendly name for this account.\n"
        "Example: My_Demo or Exness_Demo"
    )
    return ADD_ALIAS


async def _get_alias(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    alias = update.message.text.strip().replace(" ", "_")
    login = context.user_data["login"]
    password = context.user_data["password"]
    server = context.user_data["server"]
    try:
        add_account(alias, login, password, server)
        await update.message.reply_text(
            "Account '" + alias + "' saved!\n\nNow send /select_account to connect."
        )
    except Exception as exc:
        await update.message.reply_text("Error saving account: " + _safe(str(exc)))
    context.user_data.clear()
    return ConversationHandler.END


async def _cancel_add(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    context.user_data.clear()
    await update.message.reply_text("Cancelled.")
    return ConversationHandler.END


# ── /select_account ────────────────────────────────────────────────────────────
@_auth_required
async def cmd_select_account(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    aliases = list_accounts()
    if not aliases:
        await update.message.reply_text(
            "No accounts saved yet.\nUse /add_account to add your Exness demo account first."
        )
        return
    buttons = [
        [InlineKeyboardButton(alias, callback_data="select:" + alias)]
        for alias in aliases
    ]
    markup = InlineKeyboardMarkup(buttons)
    await update.message.reply_text("Select an account to connect:", reply_markup=markup)


async def _select_account_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    await query.answer()

    if not query.data.startswith("select:"):
        return

    alias = query.data.split(":", 1)[1]
    creds = get_account(alias)
    if creds is None:
        await query.edit_message_text("Could not load account '" + _safe(alias) + "'.")
        return

    await query.edit_message_text("Connecting to '" + _safe(alias) + "'...")

    if not _find_and_init_mt5():
        error = _safe(str(mt5.last_error()))
        await query.edit_message_text(
            "MT5 failed to initialize.\n"
            "Error: " + error + "\n\n"
            "To fix this:\n"
            "1. Open MetaTrader5 on your PC\n"
            "2. In MT5 click File > Open Data Folder\n"
            "3. Copy the path from the File Explorer address bar\n"
            "4. Add terminal64.exe to the end of that path\n"
            "5. Paste it into config.py as MT5_PATH\n"
            "6. Restart the bot"
        )
        return

    logged_in = mt5.login(
        login=creds["login"],
        password=creds["password"],
        server=creds["server"]
    )

    if not logged_in:
        error = _safe(str(mt5.last_error()))
        mt5.shutdown()
        await query.edit_message_text(
            "Login failed for '" + _safe(alias) + "'\n"
            "Error: " + error + "\n\n"
            "Common fixes:\n"
            "- Double-check login number\n"
            "- Password is case-sensitive\n"
            "- Server name must match exactly\n"
            "- Demo account may have expired\n\n"
            "Use /add_account to update credentials."
        )
        return

    _trading_state["alias"] = alias
    account = mt5.account_info()
    balance = account.balance if account else 0.0
    equity = account.equity if account else 0.0
    server_name = _safe(account.server if account else creds["server"])
    account_type = "Demo" if account and account.trade_mode == 0 else "Live"

    if _trading_state.get("risk_manager"):
        _trading_state["risk_manager"].set_starting_balance(balance)

    level = get_current_level(balance)

    lines = [
        "=== Connected! ===",
        "",
        "Account : " + _safe(alias),
        "Type    : " + account_type,
        "Server  : " + server_name,
        "Login   : " + str(creds["login"]),
        "",
        "Balance : $" + "{:,.2f}".format(balance),
        "Equity  : $" + "{:,.2f}".format(equity),
        "Level   : " + str(level["level"]) + "/30",
        "",
        "Send /start to begin trading.",
    ]
    await query.edit_message_text("\n".join(lines))
    logger.info("Account selected: %s (login=%s, type=%s)", alias, creds["login"], account_type)


def build_application() -> Application:
    """Build and configure the Telegram Application."""
    app = (
        Application.builder()
        .token(TELEGRAM_TOKEN)
        .arbitrary_callback_data(False)
        .build()
    )

    app.add_handler(CommandHandler("start", cmd_start))
    app.add_handler(CommandHandler("stop", cmd_stop))
    app.add_handler(CommandHandler("kill", cmd_kill))
    app.add_handler(CommandHandler("status", cmd_status))
    app.add_handler(CommandHandler("daily_report", cmd_daily_report))
    app.add_handler(CommandHandler("select_account", cmd_select_account))
    app.add_handler(CallbackQueryHandler(_select_account_callback, pattern=r"^select:"))

    add_account_conv = ConversationHandler(
        entry_points=[CommandHandler("add_account", cmd_add_account)],
        states={
            ADD_LOGIN:    [MessageHandler(filters.TEXT & ~filters.COMMAND, _get_login)],
            ADD_PASSWORD: [MessageHandler(filters.TEXT & ~filters.COMMAND, _get_password)],
            ADD_SERVER:   [MessageHandler(filters.TEXT & ~filters.COMMAND, _get_server)],
            ADD_ALIAS:    [MessageHandler(filters.TEXT & ~filters.COMMAND, _get_alias)],
        },
        fallbacks=[CommandHandler("cancel", _cancel_add)],
    )
    app.add_handler(add_account_conv)

    return app


async def send_daily_report_to_all(app: Application) -> None:
    """Send automated daily report to all allowed chat IDs."""
    trades = read_today_trades()
    stats = compute_daily_stats(trades)
    account = mt5.account_info()
    balance = account.balance if account else 0.0
    level = get_current_level(balance)

    lines = [
        "=== Automated Daily Report ===",
        "Date: " + datetime.utcnow().strftime("Y-%m-%d") + " UTC",
        "",
        "Total Trades : " + str(stats["total"]),
        "Wins         : " + str(stats["wins"]),
        "Losses       : " + str(stats["losses"]),
        "Win Rate     : " + str(stats["win_rate"]) + "%",
        "Daily PnL    : $" + "{:+.2f}".format(stats["daily_pnl"]),
        "Max Drawdown : " + str(stats["max_drawdown"]) + "%",
        "",
        "Level   : " + str(level["level"]) + "/30",
        "Balance : $" + "{:,.2f}".format(balance),
    ]

    # quick all-time metrics like weekday win rate
    try:
        full = load_trades()
        if not full.empty:
            wkd = summary_by_weekday(full)
            wk_lines = [f"{idx}:{row.win_rate:.1f}%" for idx,row in wkd.iterrows()]
            lines.append("")
            lines.append("All-time weekdays: " + "; ".join(wk_lines))
    except Exception:
        pass

    msg = "\n".join(lines)
    for chat_id in ALLOWED_CHAT_IDS:
        try:
            await app.bot.send_message(chat_id=chat_id, text=msg)
        except Exception as exc:
            logger.error("Failed to send daily report to %s: %s", chat_id, exc)