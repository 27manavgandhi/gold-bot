# Strategy Overview for Gold Bot (XAUUSDm)

This document summarizes the trading strategy implemented in the Gold Bot codebase. The bot trades the XAUUSDm pair on MetaTrader 5, targeting a fixed **20‑pip** profit per trade with predefined stop‑loss and lot sizes depending on a challenge level structure.

---

## Pip and Instrument Details

- Symbol: `XAUUSDm` (gold vs US dollar, micro contract)
- **PIP** is defined as **0.1 price move** (1 pip = 0.1, 1 point = 0.001).
- Example: entry 5120 → TP 20 pips = 5122.0, SL 15 pips = 5118.5.

---

## Market Sessions

Trading is only allowed during the major forex sessions:

| Session    | UTC Hours        |
|------------|------------------|
| Asian      | 00:00–06:00      |
| London     | 07:00–16:00      |
| New York   | 12:00–21:00      |

The bot blocks execution outside these windows (“Off‑hours”).

---

## Pre‑trade Filters

Before considering an entry, the bot verifies:

1. **Trading session** is active (`is_trading_session`).
2. **Spread** on the symbol is ≤ `SPREAD_MAX_POINTS` (default 500 points).
3. **Account leverage** meets minimum (`LEVERAGE_MIN`, default 20 000) or is unlimited.
4. Enough M1 bars are available (at least `EMA_SLOW + 10` bars).
5. ATR on M1 ≥ `ATR_MIN` (default 0.5).  Calculated with 14‑period ATR.
6. **M5 bias** – fast EMA(20) vs slow EMA(50) on the 5‑minute chart determines a directional bias (`LONG` or `SHORT`).
7. **M1 EMA alignment** – the last closed minute's EMA20/EMA50 should not contradict bias.
8. **Candle strength** – the body of the last M1 candle must be ≥
   `CANDLE_BODY_MULTIPLIER` (default 1) × average body of prior 5 candles.
9. **Breakout** – the last candle must break the previous candle’s high (for longs) or low (for shorts).

If any filter fails, scanning stops and the scan logs a blocking reason.

---

## Entry Logic

Once all filters pass, the bot determines the **direction**:

- **BUY**: M5 bias is `LONG`, last M1 candle bullish, body strong, and high > previous high.
- **SELL**: M5 bias is `SHORT`, last M1 candle bearish, body strong, and low < previous low.

The entry price is taken from the current tick (ask for buys, bid for sells).

---

## Stop‑Loss, Take‑Profit and Position Sizing

Level configuration is managed by `challenge_config.py`, providing 30 levels with
pre‑specified lot sizes, SL pips, and TP pips. Current level is selected based on
account balance.

LEVELS = [
    ( 1,     20.00,   0.03, 15.000000, 20),
    ( 2,     26.00,   0.04, 15.000000, 20),
    ( 3,     34.00,   0.05, 16.000000, 20),
    ( 4,     44.00,   0.07, 14.285714, 20),
    ( 5,     58.00,   0.09, 15.555556, 20),
    ( 6,     76.00,   0.11, 16.363636, 20),
    ( 7,     98.00,   0.14, 15.714286, 20),
    ( 8,    126.00,   0.19, 14.736842, 20),
    ( 9,    164.00,   0.24, 15.833333, 20),
    (10,    212.00,   0.32, 15.000000, 20),
    (11,    276.00,   0.41, 15.609756, 20),
    (12,    358.00,   0.54, 15.185185, 20),
    (13,    466.00,   0.70, 15.428571, 20),
    (14,    606.00,   0.91, 15.400000, 20),
    (15,    788.00,   1.18, 15.423729, 20),
    (16,   1024.00,   1.54, 15.324675, 20),
    (17,   1332.00,   2.00, 15.400000, 20),
    (18,   1732.00,   2.60, 15.384615, 20),
    (19,   2252.00,   3.37, 15.430267, 20),
    (20,   2926.00,   4.39, 15.353075, 20),
    (21,   3804.00,   5.70, 15.403509, 20),
    (22,   4944.00,   7.41, 15.384615, 20),
    (23,   6426.00,   9.64, 15.373444, 20),
    (24,   8354.00,  12.53, 15.387071, 20),
    (25,  10860.00,  16.28, 15.393120, 20),
    (26,  14116.00,  21.17, 15.380255, 20),
    (27,  18350.00,  27.52, 15.385174, 20),
    (28,  23854.00,  35.78, 15.382895, 20),
    (29,  31010.00,  46.51, 15.385939, 20),
    (30,  40312.00,  60.46, 15.385379, 20),
]

Each trade uses:

- **TP** fixed at the level’s `tp_pips` (usually 20 pips) → price distance = `tp_pips * PIP`.
- **SL** defined by `sl_pips` (varies per level, roughly 15 pips) → price distance = `sl_pips * PIP`.
- Lotsize from the level.

The code computes sl/ tp prices rounding to the symbol’s digit precision.

---

## Early Exit Rule

While a position is open the bot continually checks (`check_early_exit`) for an
opposite engulfing M1 candle *if the trade is not already +10 pips in profit*.

- A bearish engulfing candle triggers early close of long positions.
- A bullish engulfing candle triggers early close of short positions.

This rule prevents giving back small gains.

---

## Risk & Money Management Integration

The strategy is integrated with a comprehensive risk manager (`RiskManager`):

- Tracks starting balance and daily drawdown limit (`MAX_DAILY_DRAWDOWN_PCT`).
- Counts trades per session (`MAX_TRADES_PER_SESSION`, huge default).
- Implements a loss cooldown (number of candles to wait after a loss).
- Halts trading on drawdown breach or manual /kill command.

Before any new trade the bot queries `can_trade` for an all‑clear.

---

## Trade Execution Flow (from `main.py`)

1. Polls MT5 every 5 s, watches for new M1 candles.
2. On new candle:
   - Update risk manager (`tick_candle`).
   - Send daily report at 21:00 UTC if due.
   - Check for position closures (SL/TP) and log results.
   - Evaluate trading session and risk manager gate.
   - Ensure no existing positions (only 1 at a time).
   - Fetch level config and run `evaluate_signal`.
   - If a signal is returned, call `place_order`, update risk state, and log.
3. Continuously monitor open positions for early exit conditions.
4. Trades are logged to CSV with timestamps, PnL, equity, etc.

---

## Execution & Telegram Integration

- **`execution.py`** handles MT5 order placement/closure and logging via `logger.log_trade`.
- **Telegram bot** allows manual control (`/start`, `/stop`, `/kill`), account management, status queries, and automatic daily reports.

---

## Summary

This trading robot employs a momentum‑breakout strategy on the 1‑minute timeframe
filtered by a higher‑timeframe bias (5‑minute EMAs).  It targets a consistent 20‑pip
objective with tight stop‑loss levels, sizing bets according to a progressive
challenge structure.  Risk controls ensure limited drawdown, cooldowns after losses,
and operator oversight via Telegram.

The encapsulated strategy is fully deterministic, highly parameterized, and
suitable for automated deployment on MetaTrader 5.