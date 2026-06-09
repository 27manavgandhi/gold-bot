

import csv
import os
from datetime import datetime
from threading import Lock
from typing import Optional

import MetaTrader5 as mt5

from config import MT5_SYMBOL, SPREAD_MAX_POINTS

# File paths
SPREAD_LOG_DIR = "data/spread_logs"
SPREAD_LOG_FILE = None  # Will be set when logging starts
_spread_csv_lock = Lock()
_logging_active = False

# CSV headers
SPREAD_CSV_HEADERS = [
    "timestamp",
    "utc_time",
    "spread_points",
    "spread_pips",
    "max_allowed",
    "status",
    "bid",
    "ask",
    "session"
]


def _ensure_spread_log_dir():
    """Create spread_logs directory if it doesn't exist."""
    os.makedirs(SPREAD_LOG_DIR, exist_ok=True)


def start_spread_logging():
    """
    Start a new spread logging session.
    Creates a new CSV file with timestamp in filename.
    """
    global SPREAD_LOG_FILE, _logging_active
    
    _ensure_spread_log_dir()
    
    # Create filename with timestamp
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    SPREAD_LOG_FILE = os.path.join(SPREAD_LOG_DIR, f"spread_log_{timestamp}.csv")
    
    # Create file with headers
    with _spread_csv_lock:
        with open(SPREAD_LOG_FILE, "w", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=SPREAD_CSV_HEADERS)
            writer.writeheader()
    
    _logging_active = True
    print(f"✅ Spread logging started: {SPREAD_LOG_FILE}")
    return SPREAD_LOG_FILE


def stop_spread_logging():
    """
    Stop spread logging session.
    Finalizes the current CSV file.
    """
    global _logging_active
    
    if not _logging_active:
        return
    
    _logging_active = False
    print(f"✅ Spread logging stopped: {SPREAD_LOG_FILE}")
    print(f"   Total records saved to: {SPREAD_LOG_FILE}")


def log_spread(
    spread_points: int,
    bid: float,
    ask: float,
    session: str = "unknown",
    status: str = "checked"
):
    """
    Log current spread data to CSV.
    
    Args:
        spread_points: Spread in MT5 points
        bid: Current bid price
        ask: Current ask price
        session: Trading session (London/NY/Overlap/OffHours)
        status: "OK" if within limits, "BLOCKED" if too high
    """
    if not _logging_active or SPREAD_LOG_FILE is None:
        return
    
    now = datetime.utcnow()
    spread_pips = spread_points / 10  # Convert points to pips
    
    # Determine status if not provided
    if status == "checked":
        status = "OK" if spread_points <= SPREAD_MAX_POINTS else "BLOCKED"
    
    row = {
        "timestamp": now.strftime("%Y-%m-%d %H:%M:%S"),
        "utc_time": now.strftime("%H:%M:%S"),
        "spread_points": spread_points,
        "spread_pips": f"{spread_pips:.1f}",
        "max_allowed": SPREAD_MAX_POINTS,
        "status": status,
        "bid": f"{bid:.5f}",
        "ask": f"{ask:.5f}",
        "session": session
    }
    
    with _spread_csv_lock:
        try:
            with open(SPREAD_LOG_FILE, "a", newline="") as f:
                writer = csv.DictWriter(f, fieldnames=SPREAD_CSV_HEADERS)
                writer.writerow(row)
        except Exception as e:
            print(f"Error writing spread log: {e}")


def log_current_spread(session: str = "unknown") -> Optional[dict]:
    """
    Get current spread from MT5 and log it.
    Returns spread info dict or None.
    """
    if not _logging_active:
        return None
    
    tick = mt5.symbol_info_tick(MT5_SYMBOL)
    info = mt5.symbol_info(MT5_SYMBOL)
    
    if tick is None or info is None:
        return None
    
    spread_points = info.spread
    bid = tick.bid
    ask = tick.ask
    
    log_spread(spread_points, bid, ask, session)
    
    return {
        "spread_points": spread_points,
        "spread_pips": spread_points / 10,
        "bid": bid,
        "ask": ask,
        "status": "OK" if spread_points <= SPREAD_MAX_POINTS else "BLOCKED"
    }


def get_spread_stats(csv_file: str = None) -> dict:
    """
    Analyze spread data from a CSV file.
    Returns statistics about spread patterns.
    """
    if csv_file is None:
        csv_file = SPREAD_LOG_FILE
    
    if csv_file is None or not os.path.exists(csv_file):
        return {"error": "No spread log file found"}
    
    spreads = []
    blocked_count = 0
    ok_count = 0
    
    with open(csv_file, "r") as f:
        reader = csv.DictReader(f)
        for row in reader:
            spread = float(row["spread_points"])
            spreads.append(spread)
            if row["status"] == "BLOCKED":
                blocked_count += 1
            else:
                ok_count += 1
    
    if not spreads:
        return {"error": "No data in file"}
    
    return {
        "total_checks": len(spreads),
        "ok_count": ok_count,
        "blocked_count": blocked_count,
        "blocked_percent": (blocked_count / len(spreads) * 100) if spreads else 0,
        "min_spread": min(spreads),
        "max_spread": max(spreads),
        "avg_spread": sum(spreads) / len(spreads),
        "median_spread": sorted(spreads)[len(spreads) // 2],
    }


def is_logging_active() -> bool:
    """Check if spread logging is currently active."""
    return _logging_active
