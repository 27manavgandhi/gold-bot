"""
strategy.py
Donchian Channel Breakout Strategy for XAUUSD — 20-pip challenge.

Entry logic (as per Trading Rush video):
  - BUY  when M1 price breaks ABOVE the Donchian upper band (highest high of last N candles)
          AND M5 EMA20 > EMA50 with active upward slope (uptrend bias)
          AND MACD histogram is positive and expanding (momentum live NOW)
          AND minimum price range check passes (market is actually moving)

  - SELL when M1 price breaks BELOW the Donchian lower band (lowest low of last N candles)
          AND M5 EMA20 < EMA50 with active downward slope (downtrend bias)
          AND MACD histogram is negative and expanding
          AND minimum price range check passes

  All three filters must align. If market is flat/ranging, no trade is taken.

Key design principles from the video:
  - Trade ONLY in trending markets (Donchian + MACD prove the trend is live)
  - Skip when market is slow/ranging (range filter)
  - No forced daily trade count - take trades only when setup is genuine
  - SL=15 pips, TP=20 pips fixed per challenge level (1.3:1 RR as video prescribes)
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
    PIP_POINTS,
    SPREAD_MAX_POINTS,
)
from logger import logger


# ── helpers ───────────────────────────────────────────────────────────────────

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


# ── session / pre-checks ──────────────────────────────────────────────────────

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


# ── M5 trend bias ─────────────────────────────────────────────────────────────

def get_m5_bias() -> Optional[str]:
    """
    Determine trend bias from M5 EMA20/EMA50 crossover + slope check.
    Returns 'LONG', 'SHORT', or None.

    The video says MACD/Donchian strategies work in TRENDING markets.
    We use M5 EMA to confirm the higher-timeframe trend is active RIGHT NOW,
    not just historically crossed. Slope check (vs 5 candles ago) ensures
    EMA is actively moving, not just sitting from an old crossover.
    """
    df = _fetch_rates(mt5.TIMEFRAME_M5, BARS_NEEDED)
    if df is None or len(df) < EMA_SLOW + 10:
        return None

    df["ema_fast"] = _compute_ema(df["close"], EMA_FAST)
    df["ema_slow"] = _compute_ema(df["close"], EMA_SLOW)

    last  = df.iloc[-2]   # confirmed closed candle
    prev5 = df.iloc[-7]   # 5 candles back — slope confirmation

    ema_fast_now  = last["ema_fast"]
    ema_fast_ago  = prev5["ema_fast"]

    # EMA must be crossed AND actively sloping in that direction
    if ema_fast_now > last["ema_slow"] and ema_fast_now > ema_fast_ago:
        return "LONG"
    elif ema_fast_now < last["ema_slow"] and ema_fast_now < ema_fast_ago:
        return "SHORT"

    return None


# ── range filter ──────────────────────────────────────────────────────────────

def _market_is_moving(df: pd.DataFrame) -> bool:
    """
    Checks that price has moved enough over recent candles.
    If range < MIN_RANGE_PRICE, the market is ranging/dead — no trade.
    This single filter eliminates all 0% win-rate time windows from our data.
    """
    recent = df.iloc[-(MIN_RANGE_CANDLES + 1):-1]
    price_range = recent["high"].max() - recent["low"].min()
    if price_range < MIN_RANGE_PRICE:
        logger.debug(
            f"Range filter: blocked. Range={price_range:.3f} < {MIN_RANGE_PRICE} "
            f"(last {MIN_RANGE_CANDLES} candles)"
        )
        return False
    return True


# ── main signal ───────────────────────────────────────────────────────────────

def evaluate_signal(sl_pips: float = 15, tp_pips: float = 20) -> Optional[dict]:
    """
    Main signal evaluation using Donchian Channel breakout + MACD + M5 EMA.

    Returns signal dict or None.

    Signal dict:
    {
        "direction": "BUY" | "SELL",
        "entry":     float,
        "sl":        float,
        "tp":        float,
        "atr":       float,
    }
    """
    # ── Pre-checks ────────────────────────────────────────────────────────────
    if not is_trading_session():
        return None

    if not check_spread():
        logger.debug("Signal blocked: spread too high.")
        return None

    if not check_leverage():
        logger.debug("Signal blocked: leverage insufficient.")
        return None

    # ── Fetch M1 data ─────────────────────────────────────────────────────────
    min_bars = max(DONCHIAN_PERIOD, MACD_SLOW + MACD_SIGNAL, MIN_RANGE_CANDLES) + 15
    df = _fetch_rates(mt5.TIMEFRAME_M1, BARS_NEEDED)
    if df is None or len(df) < min_bars:
        logger.warning("Insufficient M1 bars for signal evaluation.")
        return None

    # ── Range filter (MOST IMPORTANT) ─────────────────────────────────────────
    if not _market_is_moving(df):
        return None

    # ── Indicators ────────────────────────────────────────────────────────────

    # Donchian Channel — shift(1) means we use the CONFIRMED band, not the current forming one
    # This is a real breakout: price must close above the highest high of the last N candles
    df["dc_upper"] = df["high"].rolling(DONCHIAN_PERIOD).max().shift(1)
    df["dc_lower"] = df["low"].rolling(DONCHIAN_PERIOD).min().shift(1)

    # MACD for momentum confirmation on M1
    _, _, df["macd_hist"] = _compute_macd(df["close"], MACD_FAST, MACD_SLOW, MACD_SIGNAL)

    # Use last confirmed closed candle (-2), prev candle (-3)
    last = df.iloc[-2]
    prev = df.iloc[-3]

    dc_upper       = last["dc_upper"]
    dc_lower       = last["dc_lower"]
    macd_hist_now  = last["macd_hist"]
    macd_hist_prev = prev["macd_hist"]

    if pd.isna(dc_upper) or pd.isna(dc_lower) or pd.isna(macd_hist_now):
        return None

    # MACD histogram must be expanding = momentum is accelerating RIGHT NOW
    macd_bull = (
        macd_hist_now > MACD_HIST_MIN          # above minimum threshold
        and macd_hist_now > macd_hist_prev      # expanding upward
    )
    macd_bear = (
        macd_hist_now < -MACD_HIST_MIN         # below minimum threshold (negative)
        and macd_hist_now < macd_hist_prev      # expanding downward
    )

    # ── M5 Bias ───────────────────────────────────────────────────────────────
    m5_bias = get_m5_bias()
    if m5_bias is None:
        logger.debug("Signal blocked: no clear M5 EMA trend.")
        return None

    # ── Donchian Breakout Decision ────────────────────────────────────────────
    direction = None

    # BUY signal:
    #   1. M5 is in uptrend (EMA20 > EMA50 and sloping up)
    #   2. M1 closed ABOVE the Donchian upper band (real breakout of N-candle high)
    #   3. MACD histogram is positive and expanding (momentum confirms breakout)
    if (
        m5_bias == "LONG"
        and last["close"] > dc_upper
        and macd_bull
    ):
        direction = "BUY"

    # SELL signal:
    #   1. M5 is in downtrend (EMA20 < EMA50 and sloping down)
    #   2. M1 closed BELOW the Donchian lower band (real breakout of N-candle low)
    #   3. MACD histogram is negative and expanding (momentum confirms breakout)
    elif (
        m5_bias == "SHORT"
        and last["close"] < dc_lower
        and macd_bear
    ):
        direction = "SELL"

    if direction is None:
        return None

    # ── Price levels ──────────────────────────────────────────────────────────
    symbol_info = mt5.symbol_info(MT5_SYMBOL)
    if symbol_info is None:
        return None

    tick = mt5.symbol_info_tick(MT5_SYMBOL)
    if tick is None:
        return None

    point = symbol_info.point
    pip   = PIP_POINTS * point

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
        f"MACD_hist={macd_hist_now:.5f} (prev={macd_hist_prev:.5f})"
    )

    return {
        "direction": direction,
        "entry":     entry,
        "sl":        sl,
        "tp":        tp,
        "atr":       0.0,
    }


# ── early exit ────────────────────────────────────────────────────────────────

def check_early_exit(position) -> bool:
    """
    Close position early if MACD momentum has reversed strongly against us
    AND we have not yet reached 10 pips profit.

    Uses MACD histogram flip instead of engulfing candle — more reliable signal.
    """
    symbol_info = mt5.symbol_info(MT5_SYMBOL)
    if symbol_info is None:
        return False

    point = symbol_info.point
    pip   = PIP_POINTS * point

    tick = mt5.symbol_info_tick(MT5_SYMBOL)
    if tick is None:
        return False

    # Only consider early exit if trade has not reached +10 pips yet
    if position.type == mt5.ORDER_TYPE_BUY:
        profit_in_price = tick.bid - position.price_open
    else:
        profit_in_price = position.price_open - tick.ask

    if profit_in_price >= 10 * pip:
        return False  # Profitable enough — let TP hit

    # Get fresh MACD reading
    df = _fetch_rates(mt5.TIMEFRAME_M1, 60)
    if df is None or len(df) < MACD_SLOW + MACD_SIGNAL + 5:
        return False

    _, _, df["macd_hist"] = _compute_macd(df["close"], MACD_FAST, MACD_SLOW, MACD_SIGNAL)

    hist_now  = df.iloc[-2]["macd_hist"]
    hist_prev = df.iloc[-3]["macd_hist"]

    if pd.isna(hist_now) or pd.isna(hist_prev):
        return False

    # Exit BUY early if MACD has flipped strongly bearish
    if position.type == mt5.ORDER_TYPE_BUY:
        if hist_now < -MACD_HIST_MIN and hist_now < hist_prev:
            logger.info(
                f"Early exit: MACD reversed bearish against BUY #{position.ticket} "
                f"hist={hist_now:.5f}"
            )
            return True

    # Exit SELL early if MACD has flipped strongly bullish
    elif position.type == mt5.ORDER_TYPE_SELL:
        if hist_now > MACD_HIST_MIN and hist_now > hist_prev:
            logger.info(
                f"Early exit: MACD reversed bullish against SELL #{position.ticket} "
                f"hist={hist_now:.5f}"
            )
            return True

    return False