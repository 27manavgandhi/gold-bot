"""
challenge_config.py
30-level pip challenge ladder for XAUUSD trading system.
Each level compounds balance and lot size geometrically.
SL = 15 pips, TP = 20 pips across all levels.
"""

CHALLENGE_LEVELS = [
    {"level": 1,  "balance": 20.0,    "lot": 0.02, "sl": 15, "tp": 20},
    {"level": 2,  "balance": 44.0,    "lot": 0.03, "sl": 15, "tp": 20},
    {"level": 3,  "balance": 76.0,    "lot": 0.04, "sl": 15, "tp": 20},
    {"level": 4,  "balance": 120.0,   "lot": 0.05, "sl": 15, "tp": 20},
    {"level": 5,  "balance": 180.0,   "lot": 0.07, "sl": 15, "tp": 20},
    {"level": 6,  "balance": 260.0,   "lot": 0.09, "sl": 15, "tp": 20},
    {"level": 7,  "balance": 364.0,   "lot": 0.12, "sl": 15, "tp": 20},
    {"level": 8,  "balance": 500.0,   "lot": 0.15, "sl": 15, "tp": 20},
    {"level": 9,  "balance": 670.0,   "lot": 0.19, "sl": 15, "tp": 20},
    {"level": 10, "balance": 880.0,   "lot": 0.24, "sl": 15, "tp": 20},
    {"level": 11, "balance": 1140.0,  "lot": 0.30, "sl": 15, "tp": 20},
    {"level": 12, "balance": 1460.0,  "lot": 0.37, "sl": 15, "tp": 20},
    {"level": 13, "balance": 1850.0,  "lot": 0.46, "sl": 15, "tp": 20},
    {"level": 14, "balance": 2320.0,  "lot": 0.56, "sl": 15, "tp": 20},
    {"level": 15, "balance": 2880.0,  "lot": 0.68, "sl": 15, "tp": 20},
    {"level": 16, "balance": 3540.0,  "lot": 0.82, "sl": 15, "tp": 20},
    {"level": 17, "balance": 4300.0,  "lot": 0.98, "sl": 15, "tp": 20},
    {"level": 18, "balance": 5180.0,  "lot": 1.18, "sl": 15, "tp": 20},
    {"level": 19, "balance": 6190.0,  "lot": 1.40, "sl": 15, "tp": 20},
    {"level": 20, "balance": 7340.0,  "lot": 1.65, "sl": 15, "tp": 20},
    {"level": 21, "balance": 8640.0,  "lot": 1.94, "sl": 15, "tp": 20},
    {"level": 22, "balance": 10110.0, "lot": 2.27, "sl": 15, "tp": 20},
    {"level": 23, "balance": 11760.0, "lot": 2.64, "sl": 15, "tp": 20},
    {"level": 24, "balance": 13610.0, "lot": 3.06, "sl": 15, "tp": 20},
    {"level": 25, "balance": 15680.0, "lot": 3.53, "sl": 15, "tp": 20},
    {"level": 26, "balance": 17990.0, "lot": 4.06, "sl": 15, "tp": 20},
    {"level": 27, "balance": 20560.0, "lot": 4.65, "sl": 15, "tp": 20},
    {"level": 28, "balance": 23420.0, "lot": 5.31, "sl": 15, "tp": 20},
    {"level": 29, "balance": 26590.0, "lot": 6.04, "sl": 15, "tp": 20},
    {"level": 30, "balance": 30100.0, "lot": 6.86, "sl": 15, "tp": 20},
]


def get_current_level(balance: float) -> dict:
    """Return the challenge level dict matching the current account balance."""
    current = CHALLENGE_LEVELS[0]
    for lvl in CHALLENGE_LEVELS:
        if balance >= lvl["balance"]:
            current = lvl
        else:
            break
    return current


def get_level_by_number(level_num: int) -> dict:
    """Return level dict by level number (1-indexed)."""
    for lvl in CHALLENGE_LEVELS:
        if lvl["level"] == level_num:
            return lvl
    return CHALLENGE_LEVELS[-1]
