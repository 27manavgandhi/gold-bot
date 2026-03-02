"""
config.py
Central configuration for the Gold Bot trading system.
Edit values here before deployment.
"""

import os

# ── Telegram ──────────────────────────────────────────────────────────────────
TELEGRAM_TOKEN: str = os.environ.get("TELEGRAM_TOKEN", "8291494897:AAEi7l_fZbJqCOxxcBgUpYsz1xSfbbP83FU")
ALLOWED_CHAT_IDS: list[int] = [int(x) for x in os.environ.get("ALLOWED_CHAT_IDS", "1919885083").split(",") if x.strip()]

# ── MetaTrader 5 ──────────────────────────────────────────────────────────────
MT5_PATH: str      = r"C:\Program Files\MetaTrader 5\terminal64.exe"  # path to MT5 terminal
MT5_SYMBOL: str   = "XAUUSDm"
MT5_DEVIATION: int = 20           # max slippage in points
MT5_MAGIC: int     = 20240101     # magic number for bot orders
MT5_TIMEOUT: int   = 60_000       # connection timeout ms

# ── Donchian Channel ──────────────────────────────────────────────────────────
# The video strategy uses Donchian Channel breakout.
# Price must close ABOVE/BELOW the highest/lowest of the last N candles.
# This is a real breakout — not just breaking 1 candle's high like before.
# 10 candles = last 10 minutes on M1. Proven in Trading Rush video testing.
DONCHIAN_PERIOD: int = 10

# ── MACD Parameters ───────────────────────────────────────────────────────────
# Standard MACD settings used by Trading Rush in their strategy videos.
# MACD confirms that momentum is live and accelerating at entry time.
MACD_FAST: int      = 12
MACD_SLOW: int      = 26
MACD_SIGNAL: int    = 9
# Minimum histogram size to confirm the signal is real (not micro-noise)
# For XAUUSDm on M1, 0.05 filters out flat-market false signals
MACD_HIST_MIN: float = 0.05

# ── M5 EMA Trend Bias ─────────────────────────────────────────────────────────
# Used to confirm higher-timeframe trend direction.
# The video explicitly says: MACD/Donchian strategies only work in trending markets.
# EMA cross on M5 ensures we trade WITH the trend, not against it.
EMA_FAST: int = 20
EMA_SLOW: int = 50

# ── Range Filter ──────────────────────────────────────────────────────────────
# Skip entry if market has barely moved in the last N candles.
# Analysis showed 0% win rate when 30-min range < 3.0 price units.
# On M1 with 10 candles (10 minutes), 1.5 minimum range filters dead markets.
# If price only moves 1.5 in 10 minutes, there is no momentum to carry 2.0 to TP.
MIN_RANGE_CANDLES: int  = 10      # look-back window for range check
MIN_RANGE_PRICE: float  = 1.5     # minimum price range in last N candles (XAUUSDm units)

# ── Spread & Leverage ─────────────────────────────────────────────────────────
SPREAD_MAX_POINTS: int = 600      # maximum allowed spread in MT5 points
LEVERAGE_MIN: int      = 2000     # minimum required account leverage

# ── Risk Management ───────────────────────────────────────────────────────────
# Per the video: the challenge uses high risk (23% per trade) intentionally.
# We keep drawdown protection but REMOVE the max trade count per session —
# the video says take trades whenever a good setup appears, no forced limits.
MAX_DAILY_DRAWDOWN_PCT: float = 0.35   # halt if account drops 35% from day open
# NO MAX_TRADES_PER_SESSION — video explicitly removes this restriction
# Loss cooldown: wait 3 candles after a loss before next entry.
# This prevents the 15-trade losing streaks from immediate re-entry.
LOSS_COOLDOWN_CANDLES: int = 3

# ── Session Times (UTC) ───────────────────────────────────────────────────────
# London + NY sessions are the high-volume windows where trend trading works.
# Asian session (04-06 UTC) had 46% WR vs 17-27% in other sessions — keep it.
ASIAN_OPEN_UTC:   tuple = (4,  0)
ASIAN_CLOSE_UTC:  tuple = (6,  0)
LONDON_OPEN_UTC:  tuple = (7,  0)
LONDON_CLOSE_UTC: tuple = (16, 0)
NY_OPEN_UTC:      tuple = (12, 0)
NY_CLOSE_UTC:     tuple = (21, 0)

# ── Paths ─────────────────────────────────────────────────────────────────────
BASE_DIR:      str = os.path.dirname(os.path.abspath(__file__))
DATA_DIR:      str = os.path.join(BASE_DIR, "data")
REPORTS_DIR:   str = os.path.join(BASE_DIR, "reports")
ACCOUNTS_FILE: str = os.path.join(DATA_DIR, "accounts.json")
KEY_FILE:      str = os.path.join(DATA_DIR, "key.key")
TRADE_LOG_FILE:str = os.path.join(DATA_DIR, "trade_logs.csv")

# ── Timeframes ────────────────────────────────────────────────────────────────
# M1 is the primary timeframe — TP of 20 pips (2.0 price move) on XAUUSDm
# completes in 1-5 minutes, so M1 is the only viable execution timeframe.
M1_TF_INT: int = 1
M5_TF_INT: int = 5
BARS_NEEDED: int = 120    # enough history for MACD(26,9) + Donchian(10) + buffer

# ── Pip Definitions ───────────────────────────────────────────────────────────
# XAUUSDm: 1 pip = 0.10 price move
# MT5 point = 0.01 for gold, so 10 points = 1 pip
# Example: SL=15 pips = 1.50 price move, TP=20 pips = 2.00 price move
PIP_POINTS: int = 1   # MT5 points per pip for XAUUSDm

# ── ATR (legacy, kept for compatibility) ─────────────────────────────────────
# Not used in the new Donchian strategy but kept so imports don't break
ATR_PERIOD: int  = 14
ATR_MIN: float   = 1.8