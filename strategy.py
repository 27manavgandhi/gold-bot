"""
strategy.py
Impulse Breakout Continuation Strategy for XAUUSDm (Exness Demo).

Pip definition for XAUUSDm:
  1 pip = $1.00 price move  (e.g. 5120.00 -> 5121.00 = 1 pip)
  point = 0.001 (MT5 minimum tick)
  1 pip = 100 points

SL and TP pips come from challenge_config per level — NOT hardcoded here.
  Level 1 example: lot=0.03, SL=15 pips, TP=20 pips
    BUY  @ 5120.00 -> SL=5105.00, TP=5140.00
    Risk   = 10 * 0.03 * 15 = $4.50
    Profit = 10 * 0.03 * 20 = $6.00
"""

from datetime import datetime, timezone
from typing import Optional

import MetaTrader5 as mt5
import pandas as pd

from config import (
    ATR_MIN, ATR_PERIOD, BARS_NEEDED, CANDLE_BODY_MULTIPLIER,
    EMA_FAST, EMA_SLOW, LEVERAGE_MIN, MT5_SYMBOL,
    SPREAD_MAX_POINTS,
    ASIAN_OPEN_UTC, ASIAN_CLOSE_UTC,
    LONDON_OPEN_UTC, LONDON_CLOSE_UTC,
    NY_OPEN_UTC, NY_CLOSE_UTC,
)
from logger import logger

# 1 pip = $1.00 price move on XAUUSDm
PIP = 1.0


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
        return True, 0
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


def evaluate_signal(sl_pips: float, tp_pips: float) -> Optional[dict]:
    """
    Evaluate market for a trade signal.

    sl_pips and tp_pips come from challenge_config for the current level.
    E.g. Level 1: sl_pips=15, tp_pips=20
         Entry 5120.00 SELL -> SL=5135.00, TP=5100.00
    """
    now_str = datetime.now(timezone.utc).strftime("%H:%M:%S")
    session = get_session_name()

    logger.info("=" * 55)
    logger.info("SCAN @ %s UTC | Session: %s", now_str, session)
    logger.info("=" * 55)

    # ── Session ────────────────────────────────────────────────────────────────
    if not is_trading_session():
        logger.info("BLOCKED >> Off-hours.")
        return None
    logger.info("PASS   >> Session: %s", session)

    # ── Spread ─────────────────────────────────────────────────────────────────
    spread_ok, spread_val = check_spread()
    if not spread_ok:
        logger.info("BLOCKED >> Spread %d > max %d", spread_val, SPREAD_MAX_POINTS)
        return None
    logger.info("PASS   >> Spread: %d (max: %d)", spread_val, SPREAD_MAX_POINTS)

    # ── Leverage ───────────────────────────────────────────────────────────────
    lev_ok, lev_val = check_leverage()
    if not lev_ok:
        logger.info("BLOCKED >> Leverage %d < min %d", lev_val, LEVERAGE_MIN)
        return None
    logger.info("PASS   >> Leverage: %s", "Unlimited" if lev_val == 0 else str(lev_val))

    # ── M1 bars ────────────────────────────────────────────────────────────────
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
        "INDICATORS >> EMA20=%.2f | EMA50=%.2f | ATR=%.2f | Body=%.2f | AvgBody=%.2f | %s",
        ema_fast, ema_slow, atr_value, body, avg_body, candle_dir
    )

    # ── ATR filter ─────────────────────────────────────────────────────────────
    if atr_value < ATR_MIN:
        logger.info("BLOCKED >> ATR %.2f < %.1f", atr_value, ATR_MIN)
        return None
    logger.info("PASS   >> ATR: %.2f", atr_value)

    # ── M5 bias ────────────────────────────────────────────────────────────────
    m5_bias = get_m5_bias()
    if m5_bias is None:
        logger.info("BLOCKED >> M5 bias unclear.")
        return None
    logger.info("PASS   >> M5 Bias: %s", m5_bias)

    # ── M1 EMA info ───────────────────────────────────────────────────────────
    ema_bullish = ema_fast > ema_slow
    ema_bearish = ema_fast < ema_slow
    logger.info("INFO   >> M1 EMA: %s | M5: %s",
                "BULLISH" if ema_bullish else "BEARISH", m5_bias)

    # ── Candle body ────────────────────────────────────────────────────────────
    if avg_body <= 0:
        logger.info("BLOCKED >> avg_body is zero.")
        return None
    body_ratio  = body / avg_body
    strong_body = body_ratio >= CANDLE_BODY_MULTIPLIER
    logger.info("INFO   >> Body ratio: %.2fx (need >= %.1fx) — %s",
                body_ratio, CANDLE_BODY_MULTIPLIER, "STRONG" if strong_body else "WEAK")
    if not strong_body:
        logger.info("BLOCKED >> Candle too weak.")
        return None
    logger.info("PASS   >> Strong candle.")

    # ── Breakout ───────────────────────────────────────────────────────────────
    broke_high = last["high"] > prev["high"]
    broke_low  = last["low"]  < prev["low"]
    logger.info("INFO   >> Prev H=%.2f | Last H=%.2f | BrokeHigh=%s",
                prev["high"], last["high"], broke_high)
    logger.info("INFO   >> Prev L=%.2f | Last L=%.2f | BrokeLow=%s",
                prev["low"],  last["low"],  broke_low)

    # ── Symbol info ────────────────────────────────────────────────────────────
    symbol_info = mt5.symbol_info(MT5_SYMBOL)
    if symbol_info is None:
        logger.info("BLOCKED >> No symbol info.")
        return None
    digits = symbol_info.digits

    direction = None

    if m5_bias == "LONG" and strong_body and last["close"] > last["open"] and broke_high:
        direction = "BUY"
        logger.info("SIGNAL >> BUY confirmed!")
    elif m5_bias == "SHORT" and strong_body and last["close"] < last["open"] and broke_low:
        direction = "SELL"
        logger.info("SIGNAL >> SELL confirmed!")
    else:
        if m5_bias == "LONG":
            if last["close"] <= last["open"]:
                logger.info("BLOCKED >> BUY needs bullish candle, got BEARISH.")
            elif not broke_high:
                logger.info("BLOCKED >> BUY needs high > %.2f, got %.2f.", prev["high"], last["high"])
        elif m5_bias == "SHORT":
            if last["close"] >= last["open"]:
                logger.info("BLOCKED >> SELL needs bearish candle, got BULLISH.")
            elif not broke_low:
                logger.info("BLOCKED >> SELL needs low < %.2f, got %.2f.", prev["low"], last["low"])
        return None

    # ── Entry / SL / TP using level's pip distances ────────────────────────────
    tick = mt5.symbol_info_tick(MT5_SYMBOL)
    if tick is None:
        logger.info("BLOCKED >> No tick data.")
        return None

    if direction == "BUY":
        entry = tick.ask
        sl    = round(entry - sl_pips * PIP, digits)
        tp    = round(entry + tp_pips * PIP, digits)
    else:
        entry = tick.bid
        sl    = round(entry + sl_pips * PIP, digits)
        tp    = round(entry - tp_pips * PIP, digits)

    logger.info(
        "TRADE  >> %s | Entry=%.2f | SL=%.2f (-%d pips) | TP=%.2f (+%d pips) | %s",
        direction, entry, sl, sl_pips, tp, tp_pips, session
    )

    return {
        "direction": direction,
        "entry":     entry,
        "sl":        sl,
        "tp":        tp,
        "atr":       atr_value,
        "session":   session,
    }


def check_early_exit(position) -> bool:
    """
    Early exit on opposite engulfing candle when profit < +10 pips.
    """
    tick = mt5.symbol_info_tick(MT5_SYMBOL)
    if tick is None:
        return False

    if position.type == mt5.ORDER_TYPE_BUY:
        profit_pips = (tick.bid - position.price_open) / PIP
    else:
        profit_pips = (position.price_open - tick.ask) / PIP

    # Don't exit if already +10 pips in profit
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
        logger.info("EARLY EXIT >> Bear engulf vs BUY #%s (%.1f pips)",
                    position.ticket, profit_pips)
        return True
    if position.type == mt5.ORDER_TYPE_SELL and engulf_bull:
        logger.info("EARLY EXIT >> Bull engulf vs SELL #%s (%.1f pips)",
                    position.ticket, profit_pips)
        return True

    return False