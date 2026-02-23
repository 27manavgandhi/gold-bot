"""
strategy.py
Impulse Breakout Continuation Strategy for XAUUSD.
Operates on M1 data with M5 bias filter.
Trades during Asian, London, and New York sessions.
"""

from datetime import datetime, timezone
from typing import Optional

import MetaTrader5 as mt5
import pandas as pd

from config import (
    ATR_MIN, ATR_PERIOD, BARS_NEEDED, CANDLE_BODY_MULTIPLIER,
    EMA_FAST, EMA_SLOW, LEVERAGE_MIN, MT5_SYMBOL, PIP_POINTS,
    SPREAD_MAX_POINTS,
    ASIAN_OPEN_UTC, ASIAN_CLOSE_UTC,
    LONDON_OPEN_UTC, LONDON_CLOSE_UTC,
    NY_OPEN_UTC, NY_CLOSE_UTC,
)
from logger import logger


def _fetch_rates(timeframe: int, count: int) -> Optional[pd.DataFrame]:
    """Fetch OHLCV bars from MT5 and return as DataFrame."""
    rates = mt5.copy_rates_from_pos(MT5_SYMBOL, timeframe, 0, count)
    if rates is None or len(rates) == 0:
        return None
    df = pd.DataFrame(rates)
    df["time"] = pd.to_datetime(df["time"], unit="s", utc=True)
    return df


def _compute_ema(series: pd.Series, period: int) -> pd.Series:
    return series.ewm(span=period, adjust=False).mean()


def _compute_atr(df: pd.DataFrame, period: int) -> pd.Series:
    high = df["high"]
    low = df["low"]
    close = df["close"]
    tr = pd.concat([
        high - low,
        (high - close.shift(1)).abs(),
        (low - close.shift(1)).abs(),
    ], axis=1).max(axis=1)
    return tr.ewm(span=period, adjust=False).mean()


def is_trading_session() -> bool:
    """
    Return True if current UTC time is within Asian, London, or New York session.

    Asian session:    00:00 - 06:00 UTC
    London session:   07:00 - 16:00 UTC
    New York session: 12:00 - 21:00 UTC
    """
    now_utc = datetime.now(timezone.utc)
    current_minutes = now_utc.hour * 60 + now_utc.minute

    asian_open  = ASIAN_OPEN_UTC[0]  * 60 + ASIAN_OPEN_UTC[1]
    asian_close = ASIAN_CLOSE_UTC[0] * 60 + ASIAN_CLOSE_UTC[1]
    london_open  = LONDON_OPEN_UTC[0]  * 60 + LONDON_OPEN_UTC[1]
    london_close = LONDON_CLOSE_UTC[0] * 60 + LONDON_CLOSE_UTC[1]
    ny_open  = NY_OPEN_UTC[0]  * 60 + NY_OPEN_UTC[1]
    ny_close = NY_CLOSE_UTC[0] * 60 + NY_CLOSE_UTC[1]

    in_asian  = asian_open  <= current_minutes < asian_close
    in_london = london_open <= current_minutes < london_close
    in_ny     = ny_open     <= current_minutes < ny_close

    return in_asian or in_london or in_ny


def get_session_name() -> str:
    """Return the name of the current active session for logging."""
    now_utc = datetime.now(timezone.utc)
    current_minutes = now_utc.hour * 60 + now_utc.minute

    if ASIAN_OPEN_UTC[0] * 60 <= current_minutes < ASIAN_CLOSE_UTC[0] * 60:
        return "Asian"
    if LONDON_OPEN_UTC[0] * 60 <= current_minutes < LONDON_CLOSE_UTC[0] * 60:
        return "London"
    if NY_OPEN_UTC[0] * 60 <= current_minutes < NY_CLOSE_UTC[0] * 60:
        return "New York"
    return "Off-hours"


def check_spread() -> bool:
    """Return True if current spread is within acceptable limits."""
    symbol_info = mt5.symbol_info(MT5_SYMBOL)
    if symbol_info is None:
        return False
    return symbol_info.spread <= SPREAD_MAX_POINTS


def check_leverage() -> bool:
    """
    Return True if account leverage meets minimum requirement.
    Exness reports Unlimited leverage as 0 in the MT5 API.
    A value of 0 means unlimited — always passes.
    """
    info = mt5.account_info()
    if info is None:
        return False
    if info.leverage == 0:
        logger.debug("Leverage: Unlimited (0) - check passed.")
        return True
    return info.leverage >= LEVERAGE_MIN


def get_m5_bias() -> Optional[str]:
    """
    Determine trend bias from M5 chart.
    Returns 'LONG', 'SHORT', or None if no clear bias.
    """
    df = _fetch_rates(mt5.TIMEFRAME_M5, BARS_NEEDED)
    if df is None or len(df) < EMA_SLOW + 5:
        return None

    df["ema_fast"] = _compute_ema(df["close"], EMA_FAST)
    df["ema_slow"] = _compute_ema(df["close"], EMA_SLOW)

    last = df.iloc[-2]
    if last["ema_fast"] > last["ema_slow"]:
        return "LONG"
    elif last["ema_fast"] < last["ema_slow"]:
        return "SHORT"
    return None


def evaluate_signal() -> Optional[dict]:
    """
    Main entry point. Evaluate M1 chart for trade signal.

    Returns signal dict or None:
    {
        "direction": "BUY" | "SELL",
        "entry": float,
        "sl": float,
        "tp": float,
        "atr": float,
        "session": str,
    }
    """
    # ── Session check ──────────────────────────────────────────────────────────
    if not is_trading_session():
        return None

    session = get_session_name()

    # ── Pre-checks ─────────────────────────────────────────────────────────────
    if not check_spread():
        logger.debug("Signal blocked: spread too high.")
        return None

    if not check_leverage():
        logger.debug("Signal blocked: leverage insufficient.")
        return None

    # ── Fetch M1 data ──────────────────────────────────────────────────────────
    df = _fetch_rates(mt5.TIMEFRAME_M1, BARS_NEEDED)
    if df is None or len(df) < EMA_SLOW + 10:
        logger.warning("Insufficient M1 bars for signal evaluation.")
        return None

    # ── Indicators ─────────────────────────────────────────────────────────────
    df["ema_fast"] = _compute_ema(df["close"], EMA_FAST)
    df["ema_slow"] = _compute_ema(df["close"], EMA_SLOW)
    df["atr"]      = _compute_atr(df, ATR_PERIOD)
    df["body"]     = (df["close"] - df["open"]).abs()
    df["avg_body_5"] = df["body"].rolling(5).mean().shift(1)

    last = df.iloc[-2]
    prev = df.iloc[-3]

    atr_value = last["atr"]
    if atr_value < ATR_MIN:
        logger.debug("Signal blocked: ATR %.3f < %.1f", atr_value, ATR_MIN)
        return None

    # ── M5 Bias ────────────────────────────────────────────────────────────────
    m5_bias = get_m5_bias()
    if m5_bias is None:
        return None

    # ── EMA trend on M1 ───────────────────────────────────────────────────────
    ema_bullish = last["ema_fast"] > last["ema_slow"]
    ema_bearish = last["ema_fast"] < last["ema_slow"]

    # ── Candle body strength ───────────────────────────────────────────────────
    avg_body = last["avg_body_5"]
    if avg_body <= 0:
        return None
    strong_body = last["body"] >= CANDLE_BODY_MULTIPLIER * avg_body

    # ── Symbol info ────────────────────────────────────────────────────────────
    symbol_info = mt5.symbol_info(MT5_SYMBOL)
    if symbol_info is None:
        return None

    point = symbol_info.point
    pip   = PIP_POINTS * point

    direction = None

    # LONG: M5 bullish, M1 EMA bullish, strong bull candle, break above prev high
    if (m5_bias == "LONG"
            and ema_bullish
            and strong_body
            and last["close"] > last["open"]
            and last["high"] > prev["high"]):
        direction = "BUY"

    # SHORT: M5 bearish, M1 EMA bearish, strong bear candle, break below prev low
    elif (m5_bias == "SHORT"
          and ema_bearish
          and strong_body
          and last["close"] < last["open"]
          and last["low"] < prev["low"]):
        direction = "SELL"

    if direction is None:
        return None

    # ── Price levels ───────────────────────────────────────────────────────────
    tick = mt5.symbol_info_tick(MT5_SYMBOL)
    if tick is None:
        return None

    if direction == "BUY":
        entry = tick.ask
        sl = round(entry - 15 * pip, symbol_info.digits)
        tp = round(entry + 20 * pip, symbol_info.digits)
    else:
        entry = tick.bid
        sl = round(entry + 15 * pip, symbol_info.digits)
        tp = round(entry - 20 * pip, symbol_info.digits)

    logger.info(
        "Signal: %s | entry=%.5f sl=%.5f tp=%.5f ATR=%.3f M5=%s Session=%s",
        direction, entry, sl, tp, atr_value, m5_bias, session
    )

    return {
        "direction": direction,
        "entry": entry,
        "sl": sl,
        "tp": tp,
        "atr": atr_value,
        "session": session,
    }


def check_early_exit(position) -> bool:
    """
    Check if an open position should be closed early due to
    an opposite engulfing candle before reaching +10 pips profit.
    Returns True if position should be closed.
    """
    symbol_info = mt5.symbol_info(MT5_SYMBOL)
    if symbol_info is None:
        return False

    point = symbol_info.point
    pip   = PIP_POINTS * point
    early_exit_threshold = 10 * pip

    tick = mt5.symbol_info_tick(MT5_SYMBOL)
    if tick is None:
        return False

    if position.type == mt5.ORDER_TYPE_BUY:
        profit_in_price = tick.bid - position.price_open
    else:
        profit_in_price = position.price_open - tick.ask

    # Only apply early exit if below the profit threshold
    if profit_in_price >= early_exit_threshold:
        return False

    df = _fetch_rates(mt5.TIMEFRAME_M1, 10)
    if df is None or len(df) < 3:
        return False

    last = df.iloc[-2]
    prev = df.iloc[-3]

    is_engulfing_bear = (
        last["close"] < last["open"]
        and last["open"] >= prev["close"]
        and last["close"] <= prev["open"]
    )
    is_engulfing_bull = (
        last["close"] > last["open"]
        and last["open"] <= prev["close"]
        and last["close"] >= prev["open"]
    )

    if position.type == mt5.ORDER_TYPE_BUY and is_engulfing_bear:
        logger.info("Early exit: bearish engulfing against BUY #%s", position.ticket)
        return True
    if position.type == mt5.ORDER_TYPE_SELL and is_engulfing_bull:
        logger.info("Early exit: bullish engulfing against SELL #%s", position.ticket)
        return True

    return False