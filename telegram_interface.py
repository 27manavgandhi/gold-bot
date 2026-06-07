

import asyncio
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
from spread_logger import start_spread_logging, stop_spread_logging  # NEW

# ── Conversation states ────────────────────────────────────────────────────────
ADD_LOGIN, ADD_PASSWORD, ADD_SERVER, ADD_ALIAS = range(4)

# ── Shared state (injected from main.py) ──────────────────────────────────────
_trading_state: dict = {
    "enabled": False,
    "risk_manager": None,
    "alias": None,
    "selected_accounts": [],  # NEW: list of active account aliases
}

# ── Known MT5 install paths ───────────────────────────────────────────────────
MT5_CANDIDATE_PATHS = [
    r"C:\Program Files\MetaTrader 5\terminal64.exe",
    r"C:\Program Files (x86)\MetaTrader 5\terminal64.exe",
    r"C:\Program Files\Exness MT5 Terminal\terminal64.exe",
    r"C:\Program Files (x86)\Exness MT5 Terminal\terminal64.exe",
    r"C:\Program Files\Exness Technologies Ltd\Exness MT5 Terminal\terminal64.exe",
]


def _find_and_init_mt5() -> bool:
    """Try to initialize MT5 by scanning known paths."""
    from config import MT5_PATH

    if MT5_PATH and os.path.exists(MT5_PATH):
        if mt5.initialize(path=MT5_PATH):
            logger.info("MT5 initialized from config MT5_PATH: %s", MT5_PATH)
            return True

    for candidate in MT5_CANDIDATE_PATHS:
        if os.path.exists(candidate):
            if mt5.initialize(path=candidate):
                logger.info("MT5 initialized from: %s", candidate)
                return True

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
    if not _trading_state.get("selected_accounts"):
        await update.message.reply_text("No accounts selected. Use /select_account first.")
        return
    
    _trading_state["enabled"] = True
    if _trading_state.get("risk_manager"):
        _trading_state["risk_manager"].resume()
    
    # Start spread logging
    spread_log_file = start_spread_logging()
    logger.info(f"Spread logging started: {spread_log_file}")
    
    accounts_str = ", ".join(_trading_state["selected_accounts"])
    await update.message.reply_text(
        f"✅ Trading ENABLED on: {accounts_str}\n\n"
        f"📊 Spread logging active\n"
        f"Logs: {os.path.basename(spread_log_file)}"
    )
    logger.info("Trading enabled on accounts: %s", accounts_str)


# ── /stop ──────────────────────────────────────────────────────────────────────
@_auth_required
async def cmd_stop(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    _trading_state["enabled"] = False
    
    # Stop spread logging
    stop_spread_logging()
    logger.info("Spread logging stopped")
    
    await update.message.reply_text(
        "⏸️ Trading PAUSED\n"
        "Open positions remain open.\n\n"
        "📊 Spread logging saved"
    )
    logger.info("Trading paused via Telegram /stop")


# ── /kill ──────────────────────────────────────────────────────────────────────
@_auth_required
async def cmd_kill(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    _trading_state["enabled"] = False
    if _trading_state.get("risk_manager"):
        _trading_state["risk_manager"].force_halt()
    
    # Stop spread logging
    stop_spread_logging()
    logger.info("Spread logging stopped (killed)")
    
    closed = close_all_positions()
    await update.message.reply_text(
        f"🛑 Trading KILLED\n"
        f"{closed} position(s) closed.\n\n"
        f"📊 Spread logging saved"
    )
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
    
    selected = _trading_state.get("selected_accounts", [])
    accounts_str = ", ".join(selected) if selected else "None"

    lines = [
        "=== Bot Status ===",
        "Accounts : " + accounts_str,
        "Trading  : " + ("ON" if enabled else "OFF"),
        "",
        "Balance   : $" + "{:,.2f}".format(balance),
        "Equity    : $" + "{:,.2f}".format(equity),
        "Daily PnL : $" + "{:+.2f}".format(daily_pnl),
        "",
        "Level  : " + str(level["level"]) + "/30",
        "Lot    : " + str(level["lot"]),
        "Target : $" + "{:,.2f}".format(level["min_bal"]),
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
    
    # Add retry logic for network timeouts
    max_retries = 3
    for attempt in range(max_retries):
        try:
            await update.message.reply_text(
                "Enter a friendly name for this account.\n"
                "Example: My_Demo or Exness_Demo"
            )
            return ADD_ALIAS
        except Exception as e:
            logger.warning(f"Telegram send attempt {attempt+1} failed: {e}")
            if attempt < max_retries - 1:
                await asyncio.sleep(2)  # Wait 2 seconds before retry
            else:
                logger.error("Failed to send message after 3 attempts")
                # Continue anyway - user can retry /add_account if needed
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


# ── /select_account (MULTI-SELECT with checkboxes) ────────────────────────────
@_auth_required
async def cmd_select_account(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """NEW: Multi-select accounts with checkbox interface"""
    aliases = list_accounts()
    if not aliases:
        await update.message.reply_text(
            "No accounts saved yet.\nUse /add_account to add your Exness demo account first."
        )
        return
    
    # Initialize selection state
    if "account_selection" not in context.user_data:
        context.user_data["account_selection"] = set()
    
    selected = context.user_data.get("account_selection", set())
    
    # Create checkbox buttons
    buttons = []
    for alias in aliases:
        check = "✅ " if alias in selected else "☐ "
        buttons.append([InlineKeyboardButton(
            check + alias, 
            callback_data="toggle:" + alias
        )])
    
    # Add Done button
    buttons.append([InlineKeyboardButton("✓ Done - Connect Selected", callback_data="done_selection")])
    
    markup = InlineKeyboardMarkup(buttons)
    
    msg = "Select account(s) to trade (click to toggle):\n\n"
    if selected:
        msg += "Selected: " + ", ".join(selected)
    else:
        msg += "None selected yet"
    
    await update.message.reply_text(msg, reply_markup=markup)


async def _account_selection_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle checkbox toggles and final selection"""
    query = update.callback_query
    await query.answer()
    
    if query.data == "done_selection":
        # Finalize selection
        selected = context.user_data.get("account_selection", set())
        
        if not selected:
            await query.edit_message_text("No accounts selected. Use /select_account to try again.")
            return
        
        # Connect to first account (MT5 can only connect to one at a time per terminal)
        # But we store all selected accounts for potential parallel bot instances
        primary = list(selected)[0]
        _trading_state["selected_accounts"] = list(selected)
        _trading_state["alias"] = primary
        
        # Connect MT5
        creds = get_account(primary)
        if creds is None:
            await query.edit_message_text(f"Could not load primary account '{primary}'")
            return
        
        await query.edit_message_text(f"Connecting to {primary} (+ {len(selected)-1} others)...")
        
        # CRITICAL FIX: Check if MT5 is already initialized
        # If it's running with a different account, we need to disconnect first
        already_initialized = False
        current_account = mt5.account_info()
        
        if current_account is not None:
            already_initialized = True
            logger.info(f"MT5 already connected to account {current_account.login}")
            
            # If already logged in to the SAME account, skip re-login
            if current_account.login == creds["login"]:
                logger.info("Already logged in to requested account - skipping login")
                _trading_state["alias"] = primary
                
                balance = current_account.balance
                equity = current_account.equity
                
                if _trading_state.get("risk_manager"):
                    _trading_state["risk_manager"].set_starting_balance(balance)
                
                level = get_current_level(balance)
                
                lines = [
                    "=== Already Connected! ===",
                    "",
                    f"Account: {primary}",
                    f"Login: {current_account.login}",
                    f"Balance: ${balance:,.2f}",
                    f"Equity: ${equity:,.2f}",
                    f"Level: {level['level']}/30",
                    "",
                    "Send /start to begin trading.",
                ]
                await query.edit_message_text("\n".join(lines))
                logger.info("Using existing MT5 connection")
                context.user_data["account_selection"] = set()
                return
            
            # Different account - need to logout and re-login
            logger.info(f"Switching from account {current_account.login} to {creds['login']}")
            mt5.shutdown()
            already_initialized = False
        
        # Initialize MT5 if not already done
        if not already_initialized:
            if not _find_and_init_mt5():
                error = _safe(str(mt5.last_error()))
                await query.edit_message_text(
                    "MT5 failed to initialize.\n"
                    "Error: " + error + "\n\n"
                    "SOLUTION:\n"
                    "1. CLOSE MetaTrader 5 completely\n"
                    "2. Click /select_account again\n"
                    "3. Bot will connect automatically\n\n"
                    "OR keep MT5 open and select the\n"
                    "account you're already logged into."
                )
                return
        
        # Login to the account
        logged_in = mt5.login(
            login=creds["login"],
            password=creds["password"],
            server=creds["server"]
        )
        
        if not logged_in:
            error = _safe(str(mt5.last_error()))
            await query.edit_message_text(
                f"Login failed for '{primary}'\n"
                f"Error: {error}\n\n"
                "COMMON FIXES:\n"
                "1. CLOSE MT5 completely, then retry\n"
                "2. Check login/password/server\n"
                "3. If using demo account, check if expired\n\n"
                "Use /add_account to update credentials."
            )
            return
        
        account = mt5.account_info()
        balance = account.balance if account else 0.0
        equity = account.equity if account else 0.0
        
        if _trading_state.get("risk_manager"):
            _trading_state["risk_manager"].set_starting_balance(balance)
        
        level = get_current_level(balance)
        
        lines = [
            "=== Connected! ===",
            "",
            f"Primary: {primary}",
            f"Also Selected: {', '.join(list(selected)[1:]) if len(selected) > 1 else 'None'}",
            f"Login: {creds['login']}",
            f"Balance: ${balance:,.2f}",
            f"Equity: ${equity:,.2f}",
            f"Level: {level['level']}/30",
            "",
            "Send /start to begin trading.",
            "",
            "NOTE: Bot will trade on primary account.",
            "To run on multiple accounts, start separate",
            "bot instances (one per VPS/terminal)."
        ]
        await query.edit_message_text("\n".join(lines))
        logger.info("Accounts selected: %s (primary: %s)", selected, primary)
        
        # Clear selection state
        context.user_data["account_selection"] = set()
        
    elif query.data.startswith("toggle:"):
        # Toggle account selection
        alias = query.data.split(":", 1)[1]
        selected = context.user_data.get("account_selection", set())
        
        if alias in selected:
            selected.remove(alias)
        else:
            selected.add(alias)
        
        context.user_data["account_selection"] = selected
        
        # Refresh buttons
        aliases = list_accounts()
        buttons = []
        for a in aliases:
            check = "✅ " if a in selected else "☐ "
            buttons.append([InlineKeyboardButton(
                check + a, 
                callback_data="toggle:" + a
            )])
        
        buttons.append([InlineKeyboardButton("✓ Done - Connect Selected", callback_data="done_selection")])
        markup = InlineKeyboardMarkup(buttons)
        
        msg = "Select account(s) to trade (click to toggle):\n\n"
        if selected:
            msg += "Selected: " + ", ".join(selected)
        else:
            msg += "None selected yet"
        
        await query.edit_message_text(msg, reply_markup=markup)


def build_application() -> Application:
    """Build and configure the Telegram Application with extended timeouts."""
    from telegram.request import HTTPXRequest
    from config import (
        TELEGRAM_CONNECT_TIMEOUT,
        TELEGRAM_READ_TIMEOUT, 
        TELEGRAM_WRITE_TIMEOUT,
        TELEGRAM_POOL_TIMEOUT
    )
    
    # Create request with extended timeouts to handle slow networks
    request = HTTPXRequest(
        connect_timeout=TELEGRAM_CONNECT_TIMEOUT,
        read_timeout=TELEGRAM_READ_TIMEOUT,
        write_timeout=TELEGRAM_WRITE_TIMEOUT,
        pool_timeout=TELEGRAM_POOL_TIMEOUT,
    )
    
    app = (
        Application.builder()
        .token(TELEGRAM_TOKEN)
        .request(request)
        .arbitrary_callback_data(False)
        .build()
    )

    app.add_handler(CommandHandler("start", cmd_start))
    app.add_handler(CommandHandler("stop", cmd_stop))
    app.add_handler(CommandHandler("kill", cmd_kill))
    app.add_handler(CommandHandler("status", cmd_status))
    app.add_handler(CommandHandler("daily_report", cmd_daily_report))
    app.add_handler(CommandHandler("select_account", cmd_select_account))
    
    # NEW: Handle checkbox toggles and done button
    app.add_handler(CallbackQueryHandler(_account_selection_callback, pattern=r"^(toggle:|done_selection)"))

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
    msg = "\n".join(lines)
    for chat_id in ALLOWED_CHAT_IDS:
        try:
            await app.bot.send_message(chat_id=chat_id, text=msg)
        except Exception as exc:
            logger.error("Failed to send daily report to %s: %s", chat_id, exc)
