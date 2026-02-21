"""
execution.py
Handles all MetaTrader5 order placement, modification, and closure.
"""

from typing import Optional

import MetaTrader5 as mt5

from config import MT5_DEVIATION, MT5_MAGIC, MT5_SYMBOL
from logger import log_trade, logger


def place_order(
    direction: str,
    lot: float,
    entry: float,
    sl: float,
    tp: float,
) -> Optional[mt5.OrderSendResult]:
    """
    Submit a market order to MT5.

    direction – "BUY" or "SELL"
    lot       – lot size
    entry     – intended entry price (for logging; market order uses current price)
    sl        – stop loss price
    tp        – take profit price

    Returns OrderSendResult on success, None on failure.
    """
    order_type = mt5.ORDER_TYPE_BUY if direction == "BUY" else mt5.ORDER_TYPE_SELL

    tick = mt5.symbol_info_tick(MT5_SYMBOL)
    if tick is None:
        logger.error("Cannot get tick for order placement.")
        return None

    price = tick.ask if direction == "BUY" else tick.bid

    request = {
        "action": mt5.TRADE_ACTION_DEAL,
        "symbol": MT5_SYMBOL,
        "volume": float(lot),
        "type": order_type,
        "price": price,
        "sl": sl,
        "tp": tp,
        "deviation": MT5_DEVIATION,
        "magic": MT5_MAGIC,
        "comment": "GoldBot",
        "type_time": mt5.ORDER_TIME_GTC,
        "type_filling": mt5.ORDER_FILLING_IOC,
    }

    result = mt5.order_send(request)
    if result is None or result.retcode != mt5.TRADE_RETCODE_DONE:
        retcode = result.retcode if result else "None"
        comment = result.comment if result else "no result"
        logger.error(f"Order failed: retcode={retcode} comment={comment}")
        return None

    logger.info(
        f"Order placed: {direction} {lot} lots @ {price:.5f} "
        f"SL={sl:.5f} TP={tp:.5f} ticket={result.order}"
    )
    return result


def close_position(position) -> bool:
    """
    Close a specific open position.
    position – MT5 position namedtuple from positions_get()
    Returns True on success.
    """
    tick = mt5.symbol_info_tick(MT5_SYMBOL)
    if tick is None:
        logger.error("Cannot get tick for position closure.")
        return False

    if position.type == mt5.ORDER_TYPE_BUY:
        close_type = mt5.ORDER_TYPE_SELL
        price = tick.bid
    else:
        close_type = mt5.ORDER_TYPE_BUY
        price = tick.ask

    request = {
        "action": mt5.TRADE_ACTION_DEAL,
        "symbol": MT5_SYMBOL,
        "volume": position.volume,
        "type": close_type,
        "position": position.ticket,
        "price": price,
        "deviation": MT5_DEVIATION,
        "magic": MT5_MAGIC,
        "comment": "GoldBot_Close",
        "type_time": mt5.ORDER_TIME_GTC,
        "type_filling": mt5.ORDER_FILLING_IOC,
    }

    result = mt5.order_send(request)
    if result is None or result.retcode != mt5.TRADE_RETCODE_DONE:
        retcode = result.retcode if result else "None"
        comment = result.comment if result else "no result"
        logger.error(f"Close failed for ticket {position.ticket}: retcode={retcode} {comment}")
        return False

    logger.info(f"Position {position.ticket} closed @ {price:.5f}")
    return True


def close_all_positions() -> int:
    """
    Close all open positions on XAUUSD managed by this bot.
    Returns count of successfully closed positions.
    """
    positions = mt5.positions_get(symbol=MT5_SYMBOL)
    if positions is None:
        return 0

    closed = 0
    for pos in positions:
        if pos.magic == MT5_MAGIC:
            if close_position(pos):
                closed += 1
    logger.info(f"Closed {closed} position(s).")
    return closed


def get_open_positions() -> list:
    """Return list of open positions belonging to this bot."""
    positions = mt5.positions_get(symbol=MT5_SYMBOL)
    if positions is None:
        return []
    return [p for p in positions if p.magic == MT5_MAGIC]


def record_closed_trade(
    position,
    close_price: float,
    result: str,
) -> None:
    """
    Log a completed trade to CSV.
    position   – original position (or snapshot with open price, type, volume)
    close_price – price at which the trade was closed
    result     – "WIN", "LOSS", or "EARLY_EXIT"
    """
    account = mt5.account_info()
    equity = account.equity if account else 0.0

    direction = "BUY" if position.type == mt5.ORDER_TYPE_BUY else "SELL"
    pnl = position.profit

    log_trade(
        signal=direction,
        lot=position.volume,
        sl_price=position.sl,
        tp_price=position.tp,
        open_price=position.price_open,
        close_price=close_price,
        result=result,
        pnl=pnl,
        equity=equity,
    )
