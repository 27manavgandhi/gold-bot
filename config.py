"""
config.py
Central configuration for the Gold Bot trading system.
"""

import os

# ── Telegram ──────────────────────────────────────────────────────────────────
TELEGRAM_TOKEN: str = "8291494897:AAEi7l_fZbJqCOxxcBgUpYsz1xSfbbP83FU"
ALLOWED_CHAT_IDS: list[int] = [1919885083]

# ── MetaTrader 5 ───────────────────────────────────────────────────────────────
MT5_SYMBOL: str = "XAUUSDm"
MT5_DEVIATION: int = 20
MT5_MAGIC: int = 20240101
MT5_TIMEOUT: int = 60_000

# ── Strategy Parameters ───────────────────────────────────────────────────────
EMA_FAST: int = 20
EMA_SLOW: int = 50
ATR_PERIOD: int = 14
ATR_MIN: float = 0.5
SPREAD_MAX_POINTS: int = 500
LEVERAGE_MIN: int = 20000
CANDLE_BODY_MULTIPLIER: float = 1
EARLY_EXIT_PIPS: float = 10.0

# ── Risk Management ───────────────────────────────────────────────────────────
MAX_DAILY_DRAWDOWN_PCT: float = 0.99
MAX_TRADES_PER_SESSION: int = 100000
LOSS_COOLDOWN_CANDLES: int = 0

# ── Session Times (UTC) ───────────────────────────────────────────────────────
# Asian session:    00:00 - 06:00 UTC
# London session:   07:00 - 16:00 UTC
# New York session: 12:00 - 21:00 UTC
ASIAN_OPEN_UTC: tuple = (0, 0)
ASIAN_CLOSE_UTC: tuple = (6, 0)
LONDON_OPEN_UTC: tuple = (7, 0)
LONDON_CLOSE_UTC: tuple = (16, 0)
NY_OPEN_UTC: tuple = (12, 0)
NY_CLOSE_UTC: tuple = (21, 0)

# ── Paths ─────────────────────────────────────────────────────────────────────
BASE_DIR: str = os.path.dirname(os.path.abspath(__file__))
DATA_DIR: str = os.path.join(BASE_DIR, "data")
REPORTS_DIR: str = os.path.join(BASE_DIR, "reports")
ACCOUNTS_FILE: str = os.path.join(DATA_DIR, "accounts.json")
KEY_FILE: str = os.path.join(DATA_DIR, "key.key")
TRADE_LOG_FILE: str = os.path.join(DATA_DIR, "trade_logs.csv")

# ── Timeframes ────────────────────────────────────────────────────────────────
M1_TF_INT: int = 1
M5_TF_INT: int = 5
BARS_NEEDED: int = 100

# ── MT5 Terminal Path ─────────────────────────────────────────────────────────
MT5_PATH: str = r"C:\Users\hp\AppData\Roaming\MetaQuotes\Terminal\D0E8209F77C8CF37AD8BF550E51FF075\terminal64.exe"


# ── Pip Definitions ───────────────────────────────────────────────────────────
PIP_POINTS: int = 10