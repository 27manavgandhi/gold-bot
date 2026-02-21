"""
logger.py
Handles structured logging to console and CSV trade log.
"""

import csv
import logging
import os
from datetime import datetime

from config import TRADE_LOG_FILE

# ── Console / file logger ──────────────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)

logger = logging.getLogger("GoldBot")

_CSV_HEADERS = [
    "timestamp", "signal", "lot", "sl_price", "tp_price",
    "open_price", "close_price", "result", "pnl", "equity",
]

def _ensure_csv() -> None:
    """Create trade log CSV with headers if it does not exist."""
    if not os.path.exists(TRADE_LOG_FILE):
        os.makedirs(os.path.dirname(TRADE_LOG_FILE), exist_ok=True)
        with open(TRADE_LOG_FILE, "w", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=_CSV_HEADERS)
            writer.writeheader()


def log_trade(
    signal: str,
    lot: float,
    sl_price: float,
    tp_price: float,
    open_price: float,
    close_price: float,
    result: str,
    pnl: float,
    equity: float,
) -> None:
    """Append a completed trade record to the CSV log."""
    _ensure_csv()
    row = {
        "timestamp": datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S"),
        "signal": signal,
        "lot": lot,
        "sl_price": sl_price,
        "tp_price": tp_price,
        "open_price": open_price,
        "close_price": close_price,
        "result": result,
        "pnl": round(pnl, 2),
        "equity": round(equity, 2),
    }
    with open(TRADE_LOG_FILE, "a", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=_CSV_HEADERS)
        writer.writerow(row)
    logger.info(f"Trade logged: {signal} | {result} | PnL={pnl:.2f}")


def read_today_trades() -> list[dict]:
    """Return all trades logged today (UTC)."""
    _ensure_csv()
    today = datetime.utcnow().strftime("%Y-%m-%d")
    trades = []
    with open(TRADE_LOG_FILE, "r", newline="") as f:
        reader = csv.DictReader(f)
        for row in reader:
            if row.get("timestamp", "").startswith(today):
                trades.append(row)
    return trades


def compute_daily_stats(trades: list[dict]) -> dict:
    """Compute summary statistics from a list of trade dicts."""
    total = len(trades)
    if total == 0:
        return {
            "total": 0, "wins": 0, "losses": 0,
            "win_rate": 0.0, "daily_pnl": 0.0, "max_drawdown": 0.0,
        }

    wins = sum(1 for t in trades if t["result"] == "WIN")
    losses = sum(1 for t in trades if t["result"] == "LOSS")
    pnls = [float(t["pnl"]) for t in trades]
    daily_pnl = sum(pnls)

    # Max drawdown: peak-to-trough on running equity
    equities = [float(t["equity"]) for t in trades]
    peak = equities[0]
    max_dd = 0.0
    for eq in equities:
        if eq > peak:
            peak = eq
        dd = (peak - eq) / peak if peak > 0 else 0.0
        if dd > max_dd:
            max_dd = dd

    return {
        "total": total,
        "wins": wins,
        "losses": losses,
        "win_rate": round(wins / total * 100, 1) if total else 0.0,
        "daily_pnl": round(daily_pnl, 2),
        "max_drawdown": round(max_dd * 100, 2),
    }
