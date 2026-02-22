"""
strategy.py
Impulse Breakout Continuation Strategy for XAUUSD.
Operates on M1 data with M5 bias filter.
"""

from datetime import datetime, timezone
from typing import Optional

import MetaTrader5 as mt5
import pandas as pd

from config import (
    ATR_MIN, ATR_PERIOD, BARS_NEEDED, CANDLE_BODY_MULTIPLIER,
    EMA_FAST, EMA_SLOW, LEVERAGE_MIN, MT5_SYMBOL, PIP_POINTS,
    SPREAD_MAX_POINTS, LONDON_OPEN_UTC, LONDON_CLOSE_UTC,
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
    """Return True if current UTC time is within London or NY session."""
    now_utc = datetime.now(timezone.utc)
    hour = now_utc.hour
    minute = now_utc.minute
    current_minutes = hour * 60 + minute

    london_open = LONDON_OPEN_UTC[0] * 60 + LONDON_OPEN_UTC[1]
    london_close = LONDON_CLOSE_UTC[0] * 60 + LONDON_CLOSE_UTC[1]
    ny_open = NY_OPEN_UTC[0] * 60 + NY_OPEN_UTC[1]
    ny_close = NY_CLOSE_UTC[0] * 60 + NY_CLOSE_UTC[1]

    in_london = london_open <= current_minutes < london_close
    in_ny = ny_open <= current_minutes < ny_close
    return in_london or in_ny


def check_spread() -> bool:
    """Return True if current spread is within acceptable limits."""
    symbol_info = mt5.symbol_info(MT5_SYMBOL)
    if symbol_info is None:
        return False
    spread = symbol_info.spread
    return spread <= SPREAD_MAX_POINTS


def check_leverage() -> bool:
    """
    Return True if account leverage meets minimum requirement.
    Exness and some brokers report Unlimited leverage as 0 in the MT5 API.
    A value of 0 means unlimited, which always passes this check.
    """
    info = mt5.account_info()
    if info is None:
        return False
    # 0 = Unlimited leverage (Exness, some other brokers)
    if info.leverage == 0:
        logger.debug("Leverage: Unlimited (reported as 0) - check passed.")
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

    last = df.iloc[-2]  # Use confirmed closed candle
    if last["ema_fast"] > last["ema_slow"]:
        return "LONG"
    elif last["ema_fast"] < last["ema_slow"]:
        return "SHORT"
    return None


def evaluate_signal() -> Optional[dict]:
    """
    Main entry point. Evaluate M1 chart for trade signal.
    Returns signal dict or None.

    Signal dict format:
    {
        "direction": "BUY" | "SELL",
        "entry": float,
        "sl": float,
        "tp": float,
        "atr": float,
    }
    """
    # ── Pre-checks ─────────────────────────────────────────────────────────────
    if not is_trading_session():
        return None

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
    df["atr"] = _compute_atr(df, ATR_PERIOD)
    df["body"] = (df["close"] - df["open"]).abs()
    df["avg_body_5"] = df["body"].rolling(5).mean().shift(1)

    # Use last 2 confirmed closed candles (index -3 and -2; -1 is forming)
    last = df.iloc[-2]
    prev = df.iloc[-3]

    atr_value = last["atr"]
    if atr_value < ATR_MIN:
        logger.debug(f"Signal blocked: ATR {atr_value:.3f} < {ATR_MIN}")
        return None

    # ── M5 Bias ────────────────────────────────────────────────────────────────
    m5_bias = get_m5_bias()
    if m5_bias is None:
        return None

    # ── EMA trend check on M1 ──────────────────────────────────────────────────
    ema_bullish = last["ema_fast"] > last["ema_slow"]
    ema_bearish = last["ema_fast"] < last["ema_slow"]

    # ── Candle body strength ───────────────────────────────────────────────────
    avg_body = last["avg_body_5"]
    if avg_body <= 0:
        return None
    strong_body = last["body"] >= CANDLE_BODY_MULTIPLIER * avg_body

    # ── Direction logic ────────────────────────────────────────────────────────
    symbol_info = mt5.symbol_info(MT5_SYMBOL)
    if symbol_info is None:
        return None

    point = symbol_info.point
    pip = PIP_POINTS * point

    direction = None

    # LONG: M5 bias bullish, M1 EMA bullish, strong bull candle, break above prev high
    if (m5_bias == "LONG" and ema_bullish and strong_body
            and last["close"] > last["open"]  # bullish candle
            and last["high"] > prev["high"]):  # breakout above prev high
        direction = "BUY"

    # SHORT: M5 bias bearish, M1 EMA bearish, strong bear candle, break below prev low
    elif (m5_bias == "SHORT" and ema_bearish and strong_body
          and last["close"] < last["open"]  # bearish candle
          and last["low"] < prev["low"]):    # breakout below prev low
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
        f"Signal: {direction} | entry={entry:.5f} sl={sl:.5f} tp={tp:.5f} "
        f"ATR={atr_value:.3f} M5={m5_bias}"
    )

    return {
        "direction": direction,
        "entry": entry,
        "sl": sl,
        "tp": tp,
        "atr": atr_value,
    }


def check_early_exit(position) -> bool:
    """
    Evaluate whether an open position should be closed early due to
    an opposite engulfing candle before reaching +10 pips profit.

    position – MT5 position namedtuple
    Returns True if position should be closed early.
    """
    symbol_info = mt5.symbol_info(MT5_SYMBOL)
    if symbol_info is None:
        return False

    point = symbol_info.point
    pip = PIP_POINTS * point
    early_exit_pip_threshold = 10 * pip

    tick = mt5.symbol_info_tick(MT5_SYMBOL)
    if tick is None:
        return False

    # Only apply early exit if position is below the profit threshold
    if position.type == mt5.ORDER_TYPE_BUY:
        current_price = tick.bid
        profit_in_price = current_price - position.price_open
        if profit_in_price >= early_exit_pip_threshold:
            return False  # Let TP play out
    else:
        current_price = tick.ask
        profit_in_price = position.price_open - current_price
        if profit_in_price >= early_exit_pip_threshold:
            return False

    # Check for opposite engulfing on M1
    df = _fetch_rates(mt5.TIMEFRAME_M1, 10)
    if df is None or len(df) < 3:
        return False

    last = df.iloc[-2]   # confirmed closed candle
    prev = df.iloc[-3]

    is_engulfing_bear = (
        last["close"] < last["open"]  # bearish
        and last["open"] >= prev["close"]
        and last["close"] <= prev["open"]
    )
    is_engulfing_bull = (
        last["close"] > last["open"]  # bullish
        and last["open"] <= prev["close"]
        and last["close"] >= prev["open"]
    )

    if position.type == mt5.ORDER_TYPE_BUY and is_engulfing_bear:
        logger.info(f"Early exit triggered: bearish engulfing against BUY #{position.ticket}")
        return True
    if position.type == mt5.ORDER_TYPE_SELL and is_engulfing_bull:
        logger.info(f"Early exit triggered: bullish engulfing against SELL #{position.ticket}")
        return True

    return False