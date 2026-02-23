"""
strategy.py
Impulse Breakout Continuation Strategy for XAUUSD.
Includes detailed diagnostic logging every candle so you can see
exactly what the bot is thinking and why trades are or are not taken.
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


def get_session_name() -> str:
    now_utc = datetime.now(timezone.utc)
    m = now_utc.hour * 60 + now_utc.minute
    if ASIAN_OPEN_UTC[0] * 60 <= m < ASIAN_CLOSE_UTC[0] * 60:
        return "Asian"
    if LONDON_OPEN_UTC[0] * 60 <= m < LONDON_CLOSE_UTC[0] * 60:
        return "London"
    if NY_OPEN_UTC[0] * 60 <= m < NY_CLOSE_UTC[0] * 60:
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
            ny_open <= m < ny_close)


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
        return True, 0  # Unlimited
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


def evaluate_signal() -> Optional[dict]:
    """
    Evaluate market for trade signal with full diagnostic logging.
    Every candle you will see exactly what passed and what blocked the trade.
    """
    now_str = datetime.now(timezone.utc).strftime("%H:%M:%S")
    session = get_session_name()

    logger.info("=" * 55)
    logger.info("SCAN @ %s UTC | Session: %s", now_str, session)
    logger.info("=" * 55)

    # ── Session check ──────────────────────────────────────────────────────────
    if not is_trading_session():
        logger.info("BLOCKED >> Not in a trading session (Off-hours). Bot is waiting.")
        return None
    logger.info("PASS   >> Session: %s", session)

    # ── Spread check ───────────────────────────────────────────────────────────
    spread_ok, spread_val = check_spread()
    if not spread_ok:
        logger.info("BLOCKED >> Spread too high: %d points (max allowed: %d)",
                    spread_val, SPREAD_MAX_POINTS)
        return None
    logger.info("PASS   >> Spread: %d points (max: %d)", spread_val, SPREAD_MAX_POINTS)

    # ── Leverage check ─────────────────────────────────────────────────────────
    lev_ok, lev_val = check_leverage()
    if not lev_ok:
        logger.info("BLOCKED >> Leverage too low: %d (min required: %d)",
                    lev_val, LEVERAGE_MIN)
        return None
    lev_display = "Unlimited" if lev_val == 0 else str(lev_val)
    logger.info("PASS   >> Leverage: %s", lev_display)

    # ── Fetch M1 bars ──────────────────────────────────────────────────────────
    df = _fetch_rates(mt5.TIMEFRAME_M1, BARS_NEEDED)
    if df is None or len(df) < EMA_SLOW + 10:
        logger.info("BLOCKED >> Not enough M1 bars to compute indicators.")
        return None

    # ── Compute indicators ─────────────────────────────────────────────────────
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

    logger.info("INDICATORS >> EMA20=%.3f | EMA50=%.3f | ATR=%.3f | Body=%.3f | AvgBody=%.3f | Candle=%s",
                ema_fast, ema_slow, atr_value, body, avg_body, candle_dir)

    # ── ATR filter ─────────────────────────────────────────────────────────────
    if atr_value < ATR_MIN:
        logger.info("BLOCKED >> ATR too low: %.3f (min required: %.1f) — Low volatility, skipping.",
                    atr_value, ATR_MIN)
        return None
    logger.info("PASS   >> ATR: %.3f (min: %.1f)", atr_value, ATR_MIN)

    # ── M5 bias ────────────────────────────────────────────────────────────────
    m5_bias = get_m5_bias()
    if m5_bias is None:
        logger.info("BLOCKED >> M5 bias unclear — EMAs too close, no directional bias.")
        return None
    logger.info("PASS   >> M5 Bias: %s", m5_bias)

    # ── EMA trend on M1 ───────────────────────────────────────────────────────
    ema_bullish = ema_fast > ema_slow
    ema_bearish = ema_fast < ema_slow
    ema_trend   = "BULLISH" if ema_bullish else "BEARISH"
    logger.info("INFO   >> M1 EMA Trend: %s (EMA20 %s EMA50)",
                ema_trend, ">" if ema_bullish else "<")

    # Check M5 vs M1 alignment
    if m5_bias == "LONG" and not ema_bullish:
        logger.info("BLOCKED >> M5=LONG but M1 EMA is BEARISH — no alignment.")
        return None
    if m5_bias == "SHORT" and not ema_bearish:
        logger.info("BLOCKED >> M5=SHORT but M1 EMA is BULLISH — no alignment.")
        return None
    logger.info("PASS   >> M5 and M1 EMA are aligned: %s", m5_bias)

    # ── Candle body strength ───────────────────────────────────────────────────
    if avg_body <= 0:
        logger.info("BLOCKED >> Average body is zero, cannot compute strength.")
        return None
    body_ratio  = body / avg_body
    strong_body = body_ratio >= CANDLE_BODY_MULTIPLIER
    logger.info("INFO   >> Candle body ratio: %.2fx (need >= %.1fx) — %s",
                body_ratio, CANDLE_BODY_MULTIPLIER,
                "STRONG" if strong_body else "WEAK")
    if not strong_body:
        logger.info("BLOCKED >> Candle body too weak (%.2fx < %.1fx). Waiting for impulse.",
                    body_ratio, CANDLE_BODY_MULTIPLIER)
        return None
    logger.info("PASS   >> Strong candle body confirmed.")

    # ── Breakout check ─────────────────────────────────────────────────────────
    broke_high = last["high"] > prev["high"]
    broke_low  = last["low"]  < prev["low"]
    logger.info("INFO   >> Prev High=%.3f | Last High=%.3f | Broke High=%s",
                prev["high"], last["high"], broke_high)
    logger.info("INFO   >> Prev Low=%.3f  | Last Low=%.3f  | Broke Low=%s",
                prev["low"], last["low"], broke_low)

    # ── Direction decision ─────────────────────────────────────────────────────
    symbol_info = mt5.symbol_info(MT5_SYMBOL)
    if symbol_info is None:
        logger.info("BLOCKED >> Cannot get symbol info.")
        return None

    point = symbol_info.point
    pip   = PIP_POINTS * point
    direction = None

    if (m5_bias == "LONG"
            and ema_bullish
            and strong_body
            and last["close"] > last["open"]
            and broke_high):
        direction = "BUY"
        logger.info("SIGNAL >> BUY signal confirmed! All conditions met.")

    elif (m5_bias == "SHORT"
          and ema_bearish
          and strong_body
          and last["close"] < last["open"]
          and broke_low):
        direction = "SELL"
        logger.info("SIGNAL >> SELL signal confirmed! All conditions met.")

    else:
        # Explain exactly why no signal
        if m5_bias == "LONG":
            if last["close"] <= last["open"]:
                logger.info("BLOCKED >> BUY needs bullish candle but last candle is BEARISH.")
            elif not broke_high:
                logger.info("BLOCKED >> BUY needs breakout above prev high (%.3f) but high was %.3f.",
                            prev["high"], last["high"])
        elif m5_bias == "SHORT":
            if last["close"] >= last["open"]:
                logger.info("BLOCKED >> SELL needs bearish candle but last candle is BULLISH.")
            elif not broke_low:
                logger.info("BLOCKED >> SELL needs breakout below prev low (%.3f) but low was %.3f.",
                            prev["low"], last["low"])
        return None

    # ── Calculate entry, SL, TP ────────────────────────────────────────────────
    tick = mt5.symbol_info_tick(MT5_SYMBOL)
    if tick is None:
        logger.info("BLOCKED >> Cannot get current tick price.")
        return None

    if direction == "BUY":
        entry = tick.ask
        sl    = round(entry - 15 * pip, symbol_info.digits)
        tp    = round(entry + 20 * pip, symbol_info.digits)
    else:
        entry = tick.bid
        sl    = round(entry + 15 * pip, symbol_info.digits)
        tp    = round(entry - 20 * pip, symbol_info.digits)

    logger.info("TRADE  >> %s | Entry=%.3f | SL=%.3f | TP=%.3f | Session=%s",
                direction, entry, sl, tp, session)

    return {
        "direction": direction,
        "entry": entry,
        "sl": sl,
        "tp": tp,
        "atr": atr_value,
        "session": session,
    }


def check_early_exit(position) -> bool:
    symbol_info = mt5.symbol_info(MT5_SYMBOL)
    if symbol_info is None:
        return False
    point = symbol_info.point
    pip   = PIP_POINTS * point
    tick  = mt5.symbol_info_tick(MT5_SYMBOL)
    if tick is None:
        return False

    if position.type == mt5.ORDER_TYPE_BUY:
        profit_in_price = tick.bid - position.price_open
    else:
        profit_in_price = position.price_open - tick.ask

    if profit_in_price >= 10 * pip:
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
        logger.info("EARLY EXIT >> Bearish engulfing against BUY #%s", position.ticket)
        return True
    if position.type == mt5.ORDER_TYPE_SELL and is_engulfing_bull:
        logger.info("EARLY EXIT >> Bullish engulfing against SELL #%s", position.ticket)
        return True

    return False