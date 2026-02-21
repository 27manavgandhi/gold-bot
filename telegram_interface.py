"""
telegram_interface.py
Telegram bot interface using python-telegram-bot v20+ async API.
Provides /start, /stop, /kill, /status, /add_account, /select_account, /daily_report commands.
"""

import asyncio
from datetime import datetime
from typing import Optional

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

# ── Conversation states ────────────────────────────────────────────────────────
ADD_LOGIN, ADD_PASSWORD, ADD_SERVER, ADD_ALIAS = range(4)

# ── Shared state (injected from main.py) ──────────────────────────────────────
_trading_state: dict = {
    "enabled": False,
    "risk_manager": None,
    "alias": None,
}


def inject_state(trading_state: dict) -> None:
    """Called by main.py to inject shared mutable state reference."""
    global _trading_state
    _trading_state = trading_state


def _is_authorized(update: Update) -> bool:
    cid = update.effective_chat.id
    if ALLOWED_CHAT_IDS and cid not in ALLOWED_CHAT_IDS:
        return False
    return True


def _auth_required(func):
    """Decorator that blocks unauthorized chat IDs."""
    async def wrapper(update: Update, context: ContextTypes.DEFAULT_TYPE):
        if not _is_authorized(update):
            await update.message.reply_text("⛔ Unauthorized.")
            return
        return await func(update, context)
    wrapper.__name__ = func.__name__
    return wrapper


# ── /start ─────────────────────────────────────────────────────────────────────
@_auth_required
async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if _trading_state.get("alias") is None:
        await update.message.reply_text(
            "⚠️ No account selected. Use /select_account first."
        )
        return
    _trading_state["enabled"] = True
    if _trading_state.get("risk_manager"):
        _trading_state["risk_manager"].resume()
    await update.message.reply_text("✅ Trading *ENABLED*.", parse_mode="Markdown")
    logger.info("Trading enabled via Telegram /start")


# ── /stop ──────────────────────────────────────────────────────────────────────
@_auth_required
async def cmd_stop(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    _trading_state["enabled"] = False
    await update.message.reply_text("🛑 Trading *PAUSED*. Open positions remain.", parse_mode="Markdown")
    logger.info("Trading paused via Telegram /stop")


# ── /kill ──────────────────────────────────────────────────────────────────────
@_auth_required
async def cmd_kill(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    _trading_state["enabled"] = False
    if _trading_state.get("risk_manager"):
        _trading_state["risk_manager"].force_halt()
    closed = close_all_positions()
    await update.message.reply_text(
        f"🔴 Trading *KILLED*. {closed} position(s) closed.", parse_mode="Markdown"
    )
    logger.warning("Trading killed via Telegram /kill")


# ── /status ────────────────────────────────────────────────────────────────────
@_auth_required
async def cmd_status(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    account = mt5.account_info()
    if account is None:
        await update.message.reply_text("❌ MT5 not connected.")
        return

    balance = account.balance
    equity = account.equity

    # Daily PnL
    trades = read_today_trades()
    daily_pnl = sum(float(t["pnl"]) for t in trades)

    level = get_current_level(balance)
    enabled = _trading_state.get("enabled", False)
    alias = _trading_state.get("alias", "N/A")

    status_text = (
        f"📊 *Bot Status*\n"
        f"Account: `{alias}`\n"
        f"Trading: {'✅ ON' if enabled else '🔴 OFF'}\n\n"
        f"💰 Balance: `${balance:,.2f}`\n"
        f"📈 Equity: `${equity:,.2f}`\n"
        f"📉 Daily PnL: `${daily_pnl:+.2f}`\n\n"
        f"🎯 Challenge Level: `{level['level']}/30`\n"
        f"Lot Size: `{level['lot']}`\n"
        f"Target Balance: `${level['balance']:,.2f}`"
    )
    await update.message.reply_text(status_text, parse_mode="Markdown")


# ── /daily_report ──────────────────────────────────────────────────────────────
@_auth_required
async def cmd_daily_report(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    trades = read_today_trades()
    stats = compute_daily_stats(trades)

    account = mt5.account_info()
    balance = account.balance if account else 0.0
    level = get_current_level(balance)

    report = (
        f"📋 *Daily Report* — {datetime.utcnow().strftime('%Y-%m-%d')} UTC\n\n"
        f"Total Trades: `{stats['total']}`\n"
        f"Wins: `{stats['wins']}` | Losses: `{stats['losses']}`\n"
        f"Win Rate: `{stats['win_rate']}%`\n"
        f"Daily PnL: `${stats['daily_pnl']:+.2f}`\n"
        f"Max Drawdown: `{stats['max_drawdown']}%`\n\n"
        f"🎯 Current Level: `{level['level']}/30`\n"
        f"Balance: `${balance:,.2f}`"
    )
    await update.message.reply_text(report, parse_mode="Markdown")


# ── /add_account conversation ──────────────────────────────────────────────────
@_auth_required
async def cmd_add_account(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    await update.message.reply_text("Enter MT5 *Login* (account number):", parse_mode="Markdown")
    return ADD_LOGIN


async def _get_login(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    text = update.message.text.strip()
    if not text.isdigit():
        await update.message.reply_text("❌ Login must be numeric. Try again:")
        return ADD_LOGIN
    context.user_data["login"] = int(text)
    await update.message.reply_text("Enter MT5 *Password*:", parse_mode="Markdown")
    return ADD_PASSWORD


async def _get_password(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    context.user_data["password"] = update.message.text.strip()
    await update.message.reply_text("Enter MT5 *Server* (e.g. BrokerName-Live):", parse_mode="Markdown")
    return ADD_SERVER


async def _get_server(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    context.user_data["server"] = update.message.text.strip()
    await update.message.reply_text("Enter a friendly *alias* for this account (e.g. My_Live):", parse_mode="Markdown")
    return ADD_ALIAS


async def _get_alias(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    alias = update.message.text.strip().replace(" ", "_")
    login = context.user_data["login"]
    password = context.user_data["password"]
    server = context.user_data["server"]

    try:
        add_account(alias, login, password, server)
        await update.message.reply_text(f"✅ Account `{alias}` saved securely.", parse_mode="Markdown")
    except Exception as exc:
        await update.message.reply_text(f"❌ Error saving account: {exc}")

    context.user_data.clear()
    return ConversationHandler.END


async def _cancel_add(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    context.user_data.clear()
    await update.message.reply_text("❌ Add account cancelled.")
    return ConversationHandler.END


# ── /select_account ────────────────────────────────────────────────────────────
@_auth_required
async def cmd_select_account(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    aliases = list_accounts()
    if not aliases:
        await update.message.reply_text("No accounts saved. Use /add_account first.")
        return

    buttons = [
        [InlineKeyboardButton(alias, callback_data=f"select:{alias}")]
        for alias in aliases
    ]
    markup = InlineKeyboardMarkup(buttons)
    await update.message.reply_text("Select an account:", reply_markup=markup)


async def _select_account_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    await query.answer()

    if not query.data.startswith("select:"):
        return

    alias = query.data.split(":", 1)[1]
    creds = get_account(alias)
    if creds is None:
        await query.edit_message_text(f"❌ Could not load account '{alias}'.")
        return

    # Attempt MT5 connection
    if not mt5.initialize():
        await query.edit_message_text("❌ MT5 initialize() failed.")
        return

    logged_in = mt5.login(creds["login"], creds["password"], creds["server"])
    if not logged_in:
        mt5.shutdown()
        await query.edit_message_text(
            f"❌ MT5 login failed for '{alias}'. Check credentials."
        )
        return

    _trading_state["alias"] = alias
    account = mt5.account_info()
    balance = account.balance if account else 0.0

    if _trading_state.get("risk_manager"):
        _trading_state["risk_manager"].set_starting_balance(balance)

    await query.edit_message_text(
        f"✅ Connected to `{alias}`\n"
        f"Balance: `${balance:,.2f}`\n"
        f"Use /start to begin trading.",
        parse_mode="Markdown",
    )
    logger.info(f"Account selected: {alias} (login={creds['login']})")


def build_application() -> Application:
    """Build and configure the Telegram Application."""
    app = Application.builder().token(TELEGRAM_TOKEN).build()

    # Simple commands
    app.add_handler(CommandHandler("start", cmd_start))
    app.add_handler(CommandHandler("stop", cmd_stop))
    app.add_handler(CommandHandler("kill", cmd_kill))
    app.add_handler(CommandHandler("status", cmd_status))
    app.add_handler(CommandHandler("daily_report", cmd_daily_report))
    app.add_handler(CommandHandler("select_account", cmd_select_account))

    # Inline keyboard callback
    app.add_handler(CallbackQueryHandler(_select_account_callback, pattern=r"^select:"))

    # Add account conversation
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

    report = (
        f"📋 *Automated Daily Report* — {datetime.utcnow().strftime('%Y-%m-%d')} UTC\n\n"
        f"Total Trades: `{stats['total']}`\n"
        f"Wins: `{stats['wins']}` | Losses: `{stats['losses']}`\n"
        f"Win Rate: `{stats['win_rate']}%`\n"
        f"Daily PnL: `${stats['daily_pnl']:+.2f}`\n"
        f"Max Drawdown: `{stats['max_drawdown']}%`\n\n"
        f"🎯 Current Level: `{level['level']}/30`\n"
        f"Balance: `${balance:,.2f}`"
    )

    for chat_id in ALLOWED_CHAT_IDS:
        try:
            await app.bot.send_message(chat_id=chat_id, text=report, parse_mode="Markdown")
        except Exception as exc:
            logger.error(f"Failed to send daily report to {chat_id}: {exc}")
