"""
config.py
Central configuration for the Gold Bot trading system.
Edit values here before deployment.
"""

import os

# ── Telegram ──────────────────────────────────────────────────────────────────
TELEGRAM_TOKEN: str = os.environ.get("TELEGRAM_TOKEN", "8291494897:AAEi7l_fZbJqCOxxcBgUpYsz1xSfbbP83FU")
ALLOWED_CHAT_IDS: list[int] = [1919885083]
# ── MetaTrader 5 ───────────────────────────────────────────────────────────────
MT5_SYMBOL: str = "XAUUSD"
MT5_DEVIATION: int = 20           # max slippage in points
MT5_MAGIC: int = 20240101         # magic number for identifying bot orders
MT5_TIMEOUT: int = 60_000         # connection timeout ms

# ── Strategy Parameters ───────────────────────────────────────────────────────
EMA_FAST: int = 20
EMA_SLOW: int = 50
ATR_PERIOD: int = 14
ATR_MIN: float = 1.8              # minimum ATR in price units
SPREAD_MAX_POINTS: int = 25       # maximum allowed spread
LEVERAGE_MIN: int = 2000          # minimum required leverage
CANDLE_BODY_MULTIPLIER: float = 1.5  # strong candle body threshold
EARLY_EXIT_PIPS: float = 10.0     # early exit threshold in pips if opposite signal

# ── Risk Management ───────────────────────────────────────────────────────────
MAX_DAILY_DRAWDOWN_PCT: float = 0.35   # 35% of balance
MAX_TRADES_PER_SESSION: int = 5
LOSS_COOLDOWN_CANDLES: int = 5         # candles to wait after a loss

# ── Session Times (UTC) ───────────────────────────────────────────────────────
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
# MetaTrader5 constants cannot be imported here (circular), so we store as ints
# TIMEFRAME_M1 = 1, TIMEFRAME_M5 = 5 in MT5 API
M1_TF_INT: int = 1
M5_TF_INT: int = 5
BARS_NEEDED: int = 100            # candle history to fetch

# ── MT5 Terminal Path (set this if auto-detection fails) ─────────────────────
# Leave as empty string for auto-detection
# Example: MT5_PATH = r"C:\Users\hp\AppData\Roaming\MetaQuotes\Terminal\YOUR_ID\terminal64.exe"
MT5_PATH: str = r"C:\Users\hp\AppData\Roaming\MetaQuotes\Terminal\D0E8209F77C8CF37AD8BF550E51FF075\terminal64.exe"


# ── Pip Definitions ───────────────────────────────────────────────────────────
# XAUUSD: 1 pip = $0.10 (point = $0.01, 10 points = 1 pip)
PIP_POINTS: int = 10              # MT5 points per pip for XAUUSD