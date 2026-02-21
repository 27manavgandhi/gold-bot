"""
main.py
Entry point for the Gold Bot XAUUSD automated trading system.
Starts the Telegram bot and the trading loop in parallel threads.
"""

import asyncio
import os
import signal
import sys
import threading
import time
from datetime import datetime, timezone

import MetaTrader5 as mt5

from challenge_config import get_current_level
from config import MT5_SYMBOL
from execution import (
    close_all_positions,
    get_open_positions,
    place_order,
    record_closed_trade,
)
from logger import logger
from risk_manager import RiskManager
from strategy import check_early_exit, evaluate_signal, is_trading_session
from telegram_interface import (
    build_application,
    inject_state,
    send_daily_report_to_all,
)

# ── Shared mutable state (accessed by both threads) ───────────────────────────
risk_manager = RiskManager()
trading_state: dict = {
    "enabled": False,
    "risk_manager": risk_manager,
    "alias": None,
}

# ── Shutdown event ────────────────────────────────────────────────────────────
shutdown_event = threading.Event()

# ── Trading loop ──────────────────────────────────────────────────────────────
_last_candle_time: datetime | None = None
_daily_report_sent_hour: int = -1


def _get_current_candle_time() -> datetime | None:
    rates = mt5.copy_rates_from_pos(MT5_SYMBOL, mt5.TIMEFRAME_M1, 0, 1)
    if rates is None or len(rates) == 0:
        return None
    return datetime.fromtimestamp(rates[0]["time"], tz=timezone.utc)


def _trading_loop() -> None:
    """
    Main trading loop. Runs in a background thread.
    Polls every 5 seconds; acts on new M1 candle closes.
    """
    global _last_candle_time, _daily_report_sent_hour

    logger.info("Trading loop started.")

    while not shutdown_event.is_set():
        try:
            time.sleep(5)

            if not trading_state["enabled"]:
                continue

            if trading_state["alias"] is None:
                continue

            # ── Check MT5 connection ──────────────────────────────────────────
            if mt5.account_info() is None:
                logger.error("MT5 connection lost. Retrying in 30s...")
                time.sleep(30)
                continue

            account = mt5.account_info()
            equity = account.equity

            # ── Check daily drawdown ──────────────────────────────────────────
            if not risk_manager.check_drawdown(equity):
                trading_state["enabled"] = False
                logger.warning("Trading disabled: daily drawdown limit exceeded.")
                continue

            # ── Detect new M1 candle ──────────────────────────────────────────
            candle_time = _get_current_candle_time()
            if candle_time is None:
                continue

            if candle_time == _last_candle_time:
                # Same candle still forming – check early exits on open positions
                _check_open_positions_early_exit()
                continue

            # New candle confirmed
            _last_candle_time = candle_time
            risk_manager.tick_candle()

            # ── Scheduled daily report at 21:00 UTC ───────────────────────────
            now_utc_hour = datetime.now(timezone.utc).hour
            if now_utc_hour == 21 and _daily_report_sent_hour != 21:
                _daily_report_sent_hour = 21
                # Schedule coroutine to run in the event loop
                asyncio.run_coroutine_threadsafe(
                    _send_report_coroutine(),
                    _telegram_event_loop,
                )
            elif now_utc_hour != 21:
                _daily_report_sent_hour = -1  # reset for next day

            # ── Check existing positions for SL/TP hit ────────────────────────
            _check_closed_positions()

            # ── Skip if not in session ────────────────────────────────────────
            if not is_trading_session():
                continue

            # ── Risk gate ─────────────────────────────────────────────────────
            can, reason = risk_manager.can_trade(equity)
            if not can:
                logger.debug(f"Trade blocked: {reason}")
                continue

            # ── Evaluate signal ───────────────────────────────────────────────
            if len(get_open_positions()) > 0:
                # Only 1 position at a time
                continue

            signal = evaluate_signal()
            if signal is None:
                continue

            # ── Get lot size from challenge level ─────────────────────────────
            balance = account.balance
            level_cfg = get_current_level(balance)
            lot = level_cfg["lot"]

            # ── Place order ───────────────────────────────────────────────────
            result = place_order(
                direction=signal["direction"],
                lot=lot,
                entry=signal["entry"],
                sl=signal["sl"],
                tp=signal["tp"],
            )

            if result is not None:
                risk_manager.record_trade_opened()
                logger.info(
                    f"Trade opened: {signal['direction']} {lot} lots "
                    f"Level={level_cfg['level']}"
                )

        except Exception as exc:
            logger.exception(f"Unhandled error in trading loop: {exc}")
            time.sleep(10)

    logger.info("Trading loop stopped.")


# Track positions that were open last tick to detect closures
_known_positions: dict[int, object] = {}


def _check_closed_positions() -> None:
    """Detect positions that have been closed (hit SL/TP) and log them."""
    global _known_positions

    current = {p.ticket: p for p in get_open_positions()}

    for ticket, pos in list(_known_positions.items()):
        if ticket not in current:
            # Position was closed externally (SL or TP hit)
            tick = mt5.symbol_info_tick(MT5_SYMBOL)
            close_price = tick.bid if tick else pos.price_open

            # Determine WIN or LOSS based on profit direction vs position type
            pnl = pos.profit
            result_str = "WIN" if pnl >= 0 else "LOSS"

            if result_str == "WIN":
                risk_manager.record_win()
            else:
                risk_manager.record_loss()

            record_closed_trade(pos, close_price, result_str)

    _known_positions = current


def _check_open_positions_early_exit() -> None:
    """Check if any open position should be closed early due to opposite engulf."""
    for pos in get_open_positions():
        if check_early_exit(pos):
            from execution import close_position
            tick = mt5.symbol_info_tick(MT5_SYMBOL)
            close_price = tick.bid if tick else pos.price_open
            if close_position(pos):
                pnl = pos.profit
                result_str = "WIN" if pnl >= 0 else "LOSS"
                if result_str == "WIN":
                    risk_manager.record_win()
                else:
                    risk_manager.record_loss()
                record_closed_trade(pos, close_price, "EARLY_EXIT")


async def _send_report_coroutine() -> None:
    if _telegram_app is not None:
        await send_daily_report_to_all(_telegram_app)


# ── Telegram async runner ─────────────────────────────────────────────────────
_telegram_app = None
_telegram_event_loop: asyncio.AbstractEventLoop | None = None


def _run_telegram(loop: asyncio.AbstractEventLoop) -> None:
    """Run the Telegram bot in a dedicated event loop on a background thread."""
    global _telegram_app

    asyncio.set_event_loop(loop)
    _telegram_app = build_application()
    inject_state(trading_state)

    async def _runner():
        await _telegram_app.initialize()
        await _telegram_app.start()
        await _telegram_app.updater.start_polling(drop_pending_updates=True)
        logger.info("Telegram bot polling started.")
        # Wait until shutdown is signalled
        while not shutdown_event.is_set():
            await asyncio.sleep(1)
        # Graceful shutdown
        await _telegram_app.updater.stop()
        await _telegram_app.stop()
        await _telegram_app.shutdown()
        logger.info("Telegram bot stopped.")

    loop.run_until_complete(_runner())


# ── Signal handling ───────────────────────────────────────────────────────────
def _handle_signal(signum, frame) -> None:
    logger.info(f"Signal {signum} received. Shutting down...")
    shutdown_event.set()


# ── Entry point ───────────────────────────────────────────────────────────────
def main() -> None:
    global _telegram_event_loop

    # Ensure data/reports directories exist
    os.makedirs("data", exist_ok=True)
    os.makedirs("reports", exist_ok=True)

    # Register OS signals for clean shutdown
    signal.signal(signal.SIGINT, _handle_signal)
    signal.signal(signal.SIGTERM, _handle_signal)

    # Initialize MT5 (connection established per account selection)
    if not mt5.initialize():
        logger.warning(
            "MT5 initialize() returned False on startup. "
            "Connect via /select_account in Telegram."
        )

    logger.info("=" * 60)
    logger.info("Gold Bot XAUUSD starting up")
    logger.info("=" * 60)

    # ── Start Telegram thread ─────────────────────────────────────────────────
    _telegram_event_loop = asyncio.new_event_loop()
    tg_thread = threading.Thread(
        target=_run_telegram,
        args=(_telegram_event_loop,),
        name="TelegramThread",
        daemon=True,
    )
    tg_thread.start()

    # ── Start trading thread ──────────────────────────────────────────────────
    trade_thread = threading.Thread(
        target=_trading_loop,
        name="TradingThread",
        daemon=True,
    )
    trade_thread.start()

    logger.info("All threads started. Waiting for shutdown signal...")

    # ── Main thread blocks until shutdown ─────────────────────────────────────
    shutdown_event.wait()

    # Cleanup
    logger.info("Shutting down Gold Bot...")
    close_all_positions()
    mt5.shutdown()
    logger.info("MT5 shutdown complete.")

    tg_thread.join(timeout=10)
    trade_thread.join(timeout=10)
    logger.info("Gold Bot terminated cleanly.")
    sys.exit(0)


if __name__ == "__main__":
    main()
