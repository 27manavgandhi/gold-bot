"""
config.py
Central configuration for the Gold Bot trading system.
FINAL VERSION - Fixed ALL issues including network timeouts
"""

import os

# ── Telegram ──────────────────────────────────────────────────────────────────
TELEGRAM_TOKEN: str = os.environ.get("TELEGRAM_TOKEN", "8291494897:AAEi7l_fZbJqCOxxcBgUpYsz1xSfbbP83FU")
ALLOWED_CHAT_IDS: list[int] = [int(x) for x in os.environ.get("ALLOWED_CHAT_IDS", "1919885083").split(",") if x.strip()]

# ── Telegram Network Settings (FIX FOR TIMEOUT ERRORS) ────────────────────────
TELEGRAM_CONNECT_TIMEOUT: float = 60.0    # Increased from default 5s to 60s
TELEGRAM_READ_TIMEOUT: float = 60.0       # Increased from default 5s to 60s
TELEGRAM_WRITE_TIMEOUT: float = 60.0      # Increased from default 5s to 60s
TELEGRAM_POOL_TIMEOUT: float = 60.0       # Increased from default 1s to 60s

# ── MetaTrader 5 ──────────────────────────────────────────────────────────────
MT5_PATH: str      = r"C:\Users\hp\AppData\Roaming\MetaQuotes\Terminal\D0E8209F77C8CF37AD8BF550E51FF075\terminal64.exe"
MT5_SYMBOL: str   = "XAUUSDm"
MT5_DEVIATION: int = 20
MT5_MAGIC: int     = 20240101
MT5_TIMEOUT: int   = 60_000

# ── Donchian Channel ──────────────────────────────────────────────────────────
# CRITICAL FIX: Increased from 10 to 15 for stronger breakout confirmation
# 15 candles = 15 minutes of consolidation before breakout
# This filters out false micro-breakouts that killed the old strategy
DONCHIAN_PERIOD: int = 15

# ── MACD Parameters ───────────────────────────────────────────────────────────
MACD_FAST: int      = 12
MACD_SLOW: int      = 26
MACD_SIGNAL: int    = 9
# CRITICAL FIX: Increased from 0.05 to 0.15 for real momentum confirmation
# 0.05 was catching noise, 0.15 ensures genuine momentum exists
MACD_HIST_MIN: float = 0.15

# ── M5 EMA Trend Bias ─────────────────────────────────────────────────────────
EMA_FAST: int = 20
EMA_SLOW: int = 50

# ── Range Filter ──────────────────────────────────────────────────────────────
# CRITICAL FIX: Increased from 10 to 20 candles and 1.5 to 3.0 pips
# Need MORE movement over LONGER period to confirm genuine trend
MIN_RANGE_CANDLES: int  = 20
MIN_RANGE_PRICE: float  = 3.0

# ── Spread & Leverage ─────────────────────────────────────────────────────────
# CRITICAL FIX: Reduced from 600 to 50 points (5 pips max)
# 600 points = 60 pips spread was allowing terrible entry conditions!
SPREAD_MAX_POINTS: int = 50
LEVERAGE_MIN: int      = 100

# ── Risk Management ───────────────────────────────────────────────────────────
MAX_DAILY_DRAWDOWN_PCT: float = 0.35
LOSS_COOLDOWN_CANDLES: int = 5  # Increased from 3 to 5 for better recovery time

# ── Session Times (UTC) ───────────────────────────────────────────────────────
# REMOVED Asian session - video says ONLY London + NY overlap
LONDON_OPEN_UTC:  tuple = (8,  0)   # Adjusted to 08:00 for true London open
LONDON_CLOSE_UTC: tuple = (16, 0)
NY_OPEN_UTC:      tuple = (13, 0)   # Adjusted to 13:00 for true NY open
NY_CLOSE_UTC:     tuple = (21, 0)

# ── Paths ─────────────────────────────────────────────────────────────────────
BASE_DIR:      str = os.path.dirname(os.path.abspath(__file__))
DATA_DIR:      str = os.path.join(BASE_DIR, "data")
REPORTS_DIR:   str = os.path.join(BASE_DIR, "reports")
ACCOUNTS_FILE: str = os.path.join(DATA_DIR, "accounts.json")
KEY_FILE:      str = os.path.join(DATA_DIR, "key.key")
TRADE_LOG_FILE:str = os.path.join(DATA_DIR, "trade_logs.csv")

# ── Timeframes ────────────────────────────────────────────────────────────────
M1_TF_INT: int = 1
M5_TF_INT: int = 5
BARS_NEEDED: int = 150    # Increased from 120 for longer lookback

# ── Pip Definitions ──────────────────────────────────────────────────────────
PIP_SIZE: float = 0.10
PIP_POINTS: int = 10

# ── ATR (legacy) ─────────────────────────────────────────────────────────────
ATR_PERIOD: int  = 14
ATR_MIN: float   = 1.8