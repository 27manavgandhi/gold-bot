"""
strategy.py
Impulse Breakout Continuation Strategy for XAUUSDm (Exness Demo).

Pip definition for XAUUSDm:
  - 1 pip = $1.00 price move (e.g. 5120.00 -> 5121.00 = 1 pip)
  - point = 0.001 (MT5 minimum price increment)
  - 1 pip = 100 points
  - 0.01 lot = $0.01 per point = $1.00 per pip
  - 0.02 lot = $0.02 per point = $2.00 per pip

Example:
  Entry 5120.00, 20 pip TP = 5140.00
  Entry 5120.00, 15 pip SL = 5105.00
  On 0.02 lot: profit = 20 pips x $2/pip = $4.00
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

# ── SL / TP distances in PIPS (1 pip = $1 price move on XAUUSDm) ─────────────
SL_PIPS = 15   # Stop Loss:   15 pips away from entry
TP_PIPS = 25   # Take Profit: 25 pips away from entry
# Risk/Reward = 1:1.67


def _fetch_rates(timeframe: int, count: int) -> Optional[pd.DataFrame]:
    rates = mt5.copy_rates_from_pos(MT5_SYMBOL, timeframe, 0, count)
    if rates is None or len(rates) == 0:
        return None
    df = pd.DataFrame(rates)
    df["time"] = pd.to_datetime(df["time"], unit="s", utc=True)
    return df


def _compute_ema(series: pd.Series, period: int) -> pd.Series:
    return series.ewm(span=period, adjust=False).mean()


def _compute_atr(df: pd.DataFrame, period: int) -> pd.Series:
    high  = df["high"]
    low   = df["low"]
    close = df["close"]
    tr = pd.concat([
        high - low,
        (high - close.shift(1)).abs(),
        (low  - close.shift(1)).abs(),
    ], axis=1).max(axis=1)
    return tr.ewm(span=period, adjust=False).mean()


def get_session_name() -> str:
    now_utc = datetime.now(timezone.utc)
    m = now_utc.hour * 60 + now_utc.minute
    if ASIAN_OPEN_UTC[0]  * 60 <= m < ASIAN_CLOSE_UTC[0]  * 60:
        return "Asian"
    if LONDON_OPEN_UTC[0] * 60 <= m < LONDON_CLOSE_UTC[0] * 60:
        return "London"
    if NY_OPEN_UTC[0]     * 60 <= m < NY_CLOSE_UTC[0]     * 60:
        return "New York"
    return "Off-hours"


def is_trading_session() -> bool:
    now_utc = datetime.now(timezone.utc)
    m = now_utc.hour * 60 + now_utc.minute
    asian_open   = ASIAN_OPEN_UTC[0]   * 60 + ASIAN_OPEN_UTC[1]
    asian_close  = ASIAN_CLOSE_UTC[0]  * 60 + ASIAN_CLOSE_UTC[1]
    london_open  = LONDON_OPEN_UTC[0]  * 60 + LONDON_OPEN_UTC[1]
    london_close = LONDON_CLOSE_UTC[0] * 60 + LONDON_CLOSE_UTC[1]
    ny_open      = NY_OPEN_UTC[0]      * 60 + NY_OPEN_UTC[1]
    ny_close     = NY_CLOSE_UTC[0]     * 60 + NY_CLOSE_UTC[1]
    return (asian_open <= m < asian_close or
            london_open <= m < london_close or
            ny_open     <= m < ny_close)


def check_spread() -> tuple[bool, int]:
    symbol_info = mt5.symbol_info(MT5_SYMBOL)
    if symbol_info is None:
        return False, -1
    return symbol_info.spread <= SPREAD_MAX_POINTS, symbol_info.spread


def check_leverage() -> tuple[bool, int]:
    info = mt5.account_info()
    if info is None:
        return False, -1
    if info.leverage == 0:
        return True, 0   # Unlimited (Exness)
    return info.leverage >= LEVERAGE_MIN, info.leverage


def get_m5_bias() -> Optional[str]:
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


def _get_pip_size(symbol_info) -> float:
    """
    Return 1 pip in price units for XAUUSDm.
    XAUUSDm: point = 0.001, 1 pip = 1.000 (100 points)
    We detect this from the symbol digits:
      digits=3 -> point=0.001 -> pip=1.0
      digits=2 -> point=0.01  -> pip=1.0 (some brokers)
    """
    # For gold (XAUUSDm), 1 pip is always $1.00 price move
    # regardless of point size
    return 1.0


def evaluate_signal() -> Optional[dict]:
    """
    Evaluate market for a trade signal with full diagnostic logging.
    SL = 15 pips, TP = 25 pips (1 pip = $1 price move on XAUUSDm)
    """
    now_str = datetime.now(timezone.utc).strftime("%H:%M:%S")
    session = get_session_name()

    logger.info("=" * 55)
    logger.info("SCAN @ %s UTC | Session: %s", now_str, session)
    logger.info("=" * 55)

    # ── Session check ──────────────────────────────────────────────────────────
    if not is_trading_session():
        logger.info("BLOCKED >> Off-hours. Waiting for next session.")
        return None
    logger.info("PASS   >> Session: %s", session)

    # ── Spread check ───────────────────────────────────────────────────────────
    spread_ok, spread_val = check_spread()
    if not spread_ok:
        logger.info("BLOCKED >> Spread too high: %d (max: %d)", spread_val, SPREAD_MAX_POINTS)
        return None
    logger.info("PASS   >> Spread: %d points (max: %d)", spread_val, SPREAD_MAX_POINTS)

    # ── Leverage check ─────────────────────────────────────────────────────────
    lev_ok, lev_val = check_leverage()
    if not lev_ok:
        logger.info("BLOCKED >> Leverage too low: %d (min: %d)", lev_val, LEVERAGE_MIN)
        return None
    logger.info("PASS   >> Leverage: %s", "Unlimited" if lev_val == 0 else str(lev_val))

    # ── Fetch M1 bars ──────────────────────────────────────────────────────────
    df = _fetch_rates(mt5.TIMEFRAME_M1, BARS_NEEDED)
    if df is None or len(df) < EMA_SLOW + 10:
        logger.info("BLOCKED >> Not enough M1 bars.")
        return None

    # ── Indicators ─────────────────────────────────────────────────────────────
    df["ema_fast"]   = _compute_ema(df["close"], EMA_FAST)
    df["ema_slow"]   = _compute_ema(df["close"], EMA_SLOW)
    df["atr"]        = _compute_atr(df, ATR_PERIOD)
    df["body"]       = (df["close"] - df["open"]).abs()
    df["avg_body_5"] = df["body"].rolling(5).mean().shift(1)

    last = df.iloc[-2]
    prev = df.iloc[-3]

    atr_value  = last["atr"]
    ema_fast   = last["ema_fast"]
    ema_slow   = last["ema_slow"]
    body       = last["body"]
    avg_body   = last["avg_body_5"]
    candle_dir = "BULL" if last["close"] > last["open"] else "BEAR"

    logger.info(
        "INDICATORS >> EMA20=%.2f | EMA50=%.2f | ATR=%.2f | Body=%.2f | AvgBody=%.2f | Candle=%s",
        ema_fast, ema_slow, atr_value, body, avg_body, candle_dir
    )

    # ── ATR filter ─────────────────────────────────────────────────────────────
    if atr_value < ATR_MIN:
        logger.info("BLOCKED >> ATR %.2f < min %.1f — low volatility.", atr_value, ATR_MIN)
        return None
    logger.info("PASS   >> ATR: %.2f (min: %.1f)", atr_value, ATR_MIN)

    # ── M5 bias ────────────────────────────────────────────────────────────────
    m5_bias = get_m5_bias()
    if m5_bias is None:
        logger.info("BLOCKED >> M5 bias unclear — EMAs too close.")
        return None
    logger.info("PASS   >> M5 Bias: %s", m5_bias)

    # ── M1 EMA trend ──────────────────────────────────────────────────────────
    ema_bullish = ema_fast > ema_slow
    ema_bearish = ema_fast < ema_slow
    ema_trend   = "BULLISH" if ema_bullish else "BEARISH"
    logger.info("INFO   >> M1 EMA: %s | M5: %s (alignment skipped for demo)", ema_trend, m5_bias)

    # ── Candle body strength ───────────────────────────────────────────────────
    if avg_body <= 0:
        logger.info("BLOCKED >> Average body is zero.")
        return None
    body_ratio  = body / avg_body
    strong_body = body_ratio >= CANDLE_BODY_MULTIPLIER
    logger.info(
        "INFO   >> Body ratio: %.2fx (need >= %.1fx) — %s",
        body_ratio, CANDLE_BODY_MULTIPLIER, "STRONG" if strong_body else "WEAK"
    )
    if not strong_body:
        logger.info("BLOCKED >> Candle body too weak. Waiting for impulse.")
        return None
    logger.info("PASS   >> Strong candle confirmed.")

    # ── Breakout check ─────────────────────────────────────────────────────────
    broke_high = last["high"] > prev["high"]
    broke_low  = last["low"]  < prev["low"]
    logger.info(
        "INFO   >> Prev High=%.2f | Last High=%.2f | Broke High=%s",
        prev["high"], last["high"], broke_high
    )
    logger.info(
        "INFO   >> Prev Low=%.2f  | Last Low=%.2f  | Broke Low=%s",
        prev["low"], last["low"], broke_low
    )

    # ── Symbol info ────────────────────────────────────────────────────────────
    symbol_info = mt5.symbol_info(MT5_SYMBOL)
    if symbol_info is None:
        logger.info("BLOCKED >> Cannot get symbol info.")
        return None

    pip = _get_pip_size(symbol_info)   # 1.0 for XAUUSDm
    digits = symbol_info.digits        # 3 for XAUUSDm

    direction = None

    # BUY: M5 bullish + strong bull candle + broke previous high
    if (m5_bias == "LONG"
            and strong_body
            and last["close"] > last["open"]
            and broke_high):
        direction = "BUY"
        logger.info("SIGNAL >> BUY confirmed! All conditions met.")

    # SELL: M5 bearish + strong bear candle + broke previous low
    elif (m5_bias == "SHORT"
          and strong_body
          and last["close"] < last["open"]
          and broke_low):
        direction = "SELL"
        logger.info("SIGNAL >> SELL confirmed! All conditions met.")

    else:
        if m5_bias == "LONG":
            if last["close"] <= last["open"]:
                logger.info("BLOCKED >> BUY needs bullish candle but got BEARISH.")
            elif not broke_high:
                logger.info(
                    "BLOCKED >> BUY needs break above %.2f but high was %.2f.",
                    prev["high"], last["high"]
                )
        elif m5_bias == "SHORT":
            if last["close"] >= last["open"]:
                logger.info("BLOCKED >> SELL needs bearish candle but got BULLISH.")
            elif not broke_low:
                logger.info(
                    "BLOCKED >> SELL needs break below %.2f but low was %.2f.",
                    prev["low"], last["low"]
                )
        return None

    # ── Entry / SL / TP ────────────────────────────────────────────────────────
    tick = mt5.symbol_info_tick(MT5_SYMBOL)
    if tick is None:
        logger.info("BLOCKED >> Cannot get tick price.")
        return None

    if direction == "BUY":
        entry = tick.ask
        sl    = round(entry - SL_PIPS * pip, digits)
        tp    = round(entry + TP_PIPS * pip, digits)
    else:
        entry = tick.bid
        sl    = round(entry + SL_PIPS * pip, digits)
        tp    = round(entry - TP_PIPS * pip, digits)

    logger.info(
        "TRADE  >> %s | Entry=%.2f | SL=%.2f (-%d pips) | TP=%.2f (+%d pips) | Session=%s",
        direction, entry, sl, SL_PIPS, tp, TP_PIPS, session
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
    Close position early if opposite engulfing candle appears
    before reaching +10 pip profit.
    """
    symbol_info = mt5.symbol_info(MT5_SYMBOL)
    if symbol_info is None:
        return False

    pip  = _get_pip_size(symbol_info)
    tick = mt5.symbol_info_tick(MT5_SYMBOL)
    if tick is None:
        return False

    if position.type == mt5.ORDER_TYPE_BUY:
        profit_pips = (tick.bid - position.price_open) / pip
    else:
        profit_pips = (position.price_open - tick.ask) / pip

    # Only apply early exit below +10 pips profit
    if profit_pips >= 10:
        return False

    df = _fetch_rates(mt5.TIMEFRAME_M1, 10)
    if df is None or len(df) < 3:
        return False

    last = df.iloc[-2]
    prev = df.iloc[-3]

    engulf_bear = (
        last["close"] < last["open"]
        and last["open"] >= prev["close"]
        and last["close"] <= prev["open"]
    )
    engulf_bull = (
        last["close"] > last["open"]
        and last["open"] <= prev["close"]
        and last["close"] >= prev["open"]
    )

    if position.type == mt5.ORDER_TYPE_BUY and engulf_bear:
        logger.info("EARLY EXIT >> Bearish engulfing vs BUY #%s (profit=%.1f pips)",
                    position.ticket, profit_pips)
        return True
    if position.type == mt5.ORDER_TYPE_SELL and engulf_bull:
        logger.info("EARLY EXIT >> Bullish engulfing vs SELL #%s (profit=%.1f pips)",
                    position.ticket, profit_pips)
        return True

    return False