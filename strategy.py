"""
strategy.py
FIXED - Donchian Channel Breakout Strategy with STRENGTHENED filters

Changes from previous version:
1. Stricter MACD threshold (0.15 vs 0.05)
2. Longer Donchian period (15 vs 10 candles)
3. Larger range requirement (3.0 pips over 20 candles vs 1.5 over 10)
4. Tighter spread check (50 vs 600 points)
5. Additional momentum expansion verification
6. Stronger M5 bias confirmation
"""

from datetime import datetime, timezone
from typing import Optional

import MetaTrader5 as mt5
import pandas as pd

from config import (
    BARS_NEEDED,
    DONCHIAN_PERIOD,
    EMA_FAST,
    EMA_SLOW,
    LEVERAGE_MIN,
    LONDON_CLOSE_UTC,
    LONDON_OPEN_UTC,
    MACD_FAST,
    MACD_HIST_MIN,
    MACD_SIGNAL,
    MACD_SLOW,
    MIN_RANGE_CANDLES,
    MIN_RANGE_PRICE,
    MT5_SYMBOL,
    NY_CLOSE_UTC,
    NY_OPEN_UTC,
    PIP_SIZE,
    SPREAD_MAX_POINTS,
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


def _compute_macd(series: pd.Series, fast: int, slow: int, signal: int):
    """Return (macd_line, signal_line, histogram) as pd.Series each."""
    ema_fast   = series.ewm(span=fast,   adjust=False).mean()
    ema_slow   = series.ewm(span=slow,   adjust=False).mean()
    macd_line  = ema_fast - ema_slow
    signal_line = macd_line.ewm(span=signal, adjust=False).mean()
    histogram  = macd_line - signal_line
    return macd_line, signal_line, histogram


def is_trading_session() -> bool:
    """Return True if current UTC time is within London or NY session."""
    now_utc = datetime.now(timezone.utc)
    current_minutes = now_utc.hour * 60 + now_utc.minute

    london_open  = LONDON_OPEN_UTC[0]  * 60 + LONDON_OPEN_UTC[1]
    london_close = LONDON_CLOSE_UTC[0] * 60 + LONDON_CLOSE_UTC[1]
    ny_open      = NY_OPEN_UTC[0]      * 60 + NY_OPEN_UTC[1]
    ny_close     = NY_CLOSE_UTC[0]     * 60 + NY_CLOSE_UTC[1]

    in_london = london_open  <= current_minutes < london_close
    in_ny     = ny_open      <= current_minutes < ny_close
    
    return in_london or in_ny


def check_spread() -> bool:
    """Return True if current spread is within acceptable limits."""
    info = mt5.symbol_info(MT5_SYMBOL)
    if info is None:
        return False
    return info.spread <= SPREAD_MAX_POINTS


def check_leverage() -> bool:
    """Return True if account leverage meets minimum requirement."""
    info = mt5.account_info()
    if info is None:
        return False
    return info.leverage >= LEVERAGE_MIN


def get_m5_bias() -> Optional[str]:
    """
    STRENGTHENED M5 bias check with additional confirmation.
    Now requires:
    1. EMA crossover (20 > 50 or 20 < 50)
    2. Active slope (current vs 5 candles ago)
    3. SUSTAINED movement (current vs 10 candles ago) - NEW
    """
    df = _fetch_rates(mt5.TIMEFRAME_M5, BARS_NEEDED)
    if df is None or len(df) < EMA_SLOW + 15:
        return None

    df["ema_fast"] = _compute_ema(df["close"], EMA_FAST)
    df["ema_slow"] = _compute_ema(df["close"], EMA_SLOW)

    last   = df.iloc[-2]
    prev5  = df.iloc[-7]
    prev10 = df.iloc[-12]  # NEW: additional confirmation

    ema_fast_now  = last["ema_fast"]
    ema_fast_ago5 = prev5["ema_fast"]
    ema_fast_ago10 = prev10["ema_fast"]

    # LONG: crossover + immediate slope + sustained slope
    if (ema_fast_now > last["ema_slow"] and 
        ema_fast_now > ema_fast_ago5 and
        ema_fast_now > ema_fast_ago10):
        return "LONG"
    
    # SHORT: crossover + immediate slope + sustained slope
    elif (ema_fast_now < last["ema_slow"] and 
          ema_fast_now < ema_fast_ago5 and
          ema_fast_now < ema_fast_ago10):
        return "SHORT"

    return None


def evaluate_signal(sl_pips: float = 15, tp_pips: float = 20) -> Optional[dict]:
    """
    STRENGTHENED signal evaluation with all video strategy filters.
    """
    # ── Pre-checks ────────────────────────────────────────────────────────────
    if not is_trading_session():
        return None

    spread_info = mt5.symbol_info(MT5_SYMBOL)
    current_spread = spread_info.spread if spread_info else 999
    if not check_spread():
        logger.info(f"BLOCKED >> Spread too high: {current_spread} > {SPREAD_MAX_POINTS}")
        return None

    acct = mt5.account_info()
    current_leverage = acct.leverage if acct else 0
    if not check_leverage():
        logger.info(f"BLOCKED >> Leverage too low: {current_leverage} < {LEVERAGE_MIN}")
        return None

    # ── Fetch M1 data ─────────────────────────────────────────────────────────
    min_bars = max(DONCHIAN_PERIOD, MACD_SLOW + MACD_SIGNAL, MIN_RANGE_CANDLES) + 20
    df = _fetch_rates(mt5.TIMEFRAME_M1, BARS_NEEDED)
    if df is None or len(df) < min_bars:
        logger.warning(f"BLOCKED >> Insufficient M1 bars: got {0 if df is None else len(df)}, need {min_bars}")
        return None

    # ── STRENGTHENED Range filter ────────────────────────────────────────────
    recent = df.iloc[-(MIN_RANGE_CANDLES + 1):-1]
    price_range = recent["high"].max() - recent["low"].min()
    if price_range < MIN_RANGE_PRICE:
        logger.info(f"BLOCKED >> Range too small: {price_range:.3f} < {MIN_RANGE_PRICE} (last {MIN_RANGE_CANDLES} candles)")
        return None

    # ── Indicators ────────────────────────────────────────────────────────────
    df["dc_upper"] = df["high"].rolling(DONCHIAN_PERIOD).max().shift(1)
    df["dc_lower"] = df["low"].rolling(DONCHIAN_PERIOD).min().shift(1)
    _, _, df["macd_hist"] = _compute_macd(df["close"], MACD_FAST, MACD_SLOW, MACD_SIGNAL)

    last = df.iloc[-2]
    prev = df.iloc[-3]
    prev2 = df.iloc[-4]  # NEW: check sustained expansion

    dc_upper       = last["dc_upper"]
    dc_lower       = last["dc_lower"]
    macd_hist_now  = last["macd_hist"]
    macd_hist_prev = prev["macd_hist"]
    macd_hist_prev2 = prev2["macd_hist"]

    if pd.isna(dc_upper) or pd.isna(dc_lower) or pd.isna(macd_hist_now):
        logger.info("BLOCKED >> Indicator NaN — not enough history yet")
        return None

    # STRENGTHENED MACD check: require SUSTAINED expansion over 2 candles
    macd_bull = (macd_hist_now > MACD_HIST_MIN and 
                 macd_hist_now > macd_hist_prev and
                 macd_hist_prev > macd_hist_prev2)  # NEW
    
    macd_bear = (macd_hist_now < -MACD_HIST_MIN and 
                 macd_hist_now < macd_hist_prev and
                 macd_hist_prev < macd_hist_prev2)  # NEW

    # ── M5 Bias ───────────────────────────────────────────────────────────────
    m5_bias = get_m5_bias()

    # ── Full diagnostic ───────────────────────────────────────────────────────
    logger.info(
        f"SCAN >> M5={m5_bias} | close={last['close']:.3f} "
        f"DC_hi={dc_upper:.3f} DC_lo={dc_lower:.3f} | "
        f"MACD={macd_hist_now:.5f}(prev={macd_hist_prev:.5f},prev2={macd_hist_prev2:.5f}) "
        f"bull={macd_bull} bear={macd_bear} | range={price_range:.3f}"
    )

    if m5_bias is None:
        logger.info("BLOCKED >> No clear M5 EMA trend")
        return None

    # ── Donchian Breakout Decision ────────────────────────────────────────────
    direction = None

    # CRITICAL: Only take breakout if ABOVE/BELOW by at least 0.5 pips (buffer)
    if m5_bias == "LONG" and last["close"] > (dc_upper + 0.05) and macd_bull:
        direction = "BUY"
    elif m5_bias == "SHORT" and last["close"] < (dc_lower - 0.05) and macd_bear:
        direction = "SELL"

    if direction is None:
        if m5_bias == "LONG":
            logger.info(
                f"NO SIGNAL >> M5=LONG | "
                f"close({last['close']:.3f})>DC_hi+0.05({dc_upper+0.05:.3f})={last['close']>(dc_upper+0.05)} | "
                f"macd_bull={macd_bull} [hist={macd_hist_now:.5f} need>{MACD_HIST_MIN} & sustained expansion]"
            )
        else:
            logger.info(
                f"NO SIGNAL >> M5=SHORT | "
                f"close({last['close']:.3f})<DC_lo-0.05({dc_lower-0.05:.3f})={last['close']<(dc_lower-0.05)} | "
                f"macd_bear={macd_bear} [hist={macd_hist_now:.5f} need<-{MACD_HIST_MIN} & sustained expansion]"
            )
        return None

    # ── Price levels ──────────────────────────────────────────────────────────
    symbol_info = mt5.symbol_info(MT5_SYMBOL)
    if symbol_info is None:
        return None

    tick = mt5.symbol_info_tick(MT5_SYMBOL)
    if tick is None:
        return None

    pip = PIP_SIZE

    if direction == "BUY":
        entry = tick.ask
        sl    = round(entry - sl_pips * pip, symbol_info.digits)
        tp    = round(entry + tp_pips * pip, symbol_info.digits)
    else:
        entry = tick.bid
        sl    = round(entry + sl_pips * pip, symbol_info.digits)
        tp    = round(entry - tp_pips * pip, symbol_info.digits)

    logger.info(
        f"SIGNAL: {direction} | entry={entry:.5f} sl={sl:.5f} tp={tp:.5f} | "
        f"M5={m5_bias} | DC_upper={dc_upper:.3f} DC_lower={dc_lower:.3f} | "
        f"MACD_hist={macd_hist_now:.5f} (sustained expansion confirmed)"
    )

    return {
        "direction": direction,
        "entry":     entry,
        "sl":        sl,
        "tp":        tp,
        "atr":       0.0,
    }


def check_early_exit(position) -> bool:
    """
    STRENGTHENED early exit check.
    Now requires STRONG momentum reversal (not just any flip).
    """
    symbol_info = mt5.symbol_info(MT5_SYMBOL)
    if symbol_info is None:
        return False

    pip = PIP_SIZE

    tick = mt5.symbol_info_tick(MT5_SYMBOL)
    if tick is None:
        return False

    # Only check if NOT yet at 10 pips profit
    if position.type == mt5.ORDER_TYPE_BUY:
        profit_in_price = tick.bid - position.price_open
    else:
        profit_in_price = position.price_open - tick.ask

    if profit_in_price >= 10 * pip:
        return False

    # Get fresh MACD
    df = _fetch_rates(mt5.TIMEFRAME_M1, 60)
    if df is None or len(df) < MACD_SLOW + MACD_SIGNAL + 5:
        return False

    _, _, df["macd_hist"] = _compute_macd(df["close"], MACD_FAST, MACD_SLOW, MACD_SIGNAL)

    hist_now  = df.iloc[-2]["macd_hist"]
    hist_prev = df.iloc[-3]["macd_hist"]

    if pd.isna(hist_now) or pd.isna(hist_prev):
        return False

    # STRENGTHENED: require histogram to be BEYOND threshold (not just flip)
    if position.type == mt5.ORDER_TYPE_BUY:
        if hist_now < -(MACD_HIST_MIN * 1.5) and hist_now < hist_prev:
            logger.info(
                f"Early exit: STRONG MACD reversal against BUY #{position.ticket} "
                f"hist={hist_now:.5f} (threshold: -{MACD_HIST_MIN*1.5:.5f})"
            )
            return True

    elif position.type == mt5.ORDER_TYPE_SELL:
        if hist_now > (MACD_HIST_MIN * 1.5) and hist_now > hist_prev:
            logger.info(
                f"Early exit: STRONG MACD reversal against SELL #{position.ticket} "
                f"hist={hist_now:.5f} (threshold: {MACD_HIST_MIN*1.5:.5f})"
            )
            return True

    return False