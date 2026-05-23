# Strategy Audit & Alignment with YouTube Video

This document reviews every part of the `gold_bot` project and compares it with the
"20 pips a day" challenge strategy described in the video you summarised.  The goal
is to confirm whether the implementation matches the rules, highlight any
mismatches or missing pieces, and recommend changes for completeness and
improvements (including identifying which days/times are most favourable).

---

## 1. Video Strategy

The original challenge from the video contains the following points:

1. **Fast account growth plan** starting with $20 and ideally reaching $52 k in 30
   levels by making 30 % profit per level (compounding 30 % increments).
2. **Risk per trade** is 23 % of current account, target is 30 % profit per trade
   (RR ≈ 1.3:1).
3. **20‑pips-a-day name** — originally intended to capture 20 pips daily.
   Constrained by one trade per day and winning every day; these rules were
   removed in the modified tests.
4. **Modification** used in the video tests:
   * remove the one‑trade-per-day / 20‑pip-per-day requirements
   * allow multiple trades when good setups appear, skip when none exist
   * keep the 23 % risk and 1.3 RR
   * use a high‑win‑rate strategy (MACD/Donchian channel breakout) that does
     best in trending markets
   * perform 1 000 simulation bots to see how many reach level 30 vs blow up
   * note that performance depends on the sustained win rate (≈ 60 % in trend,
     drops dramatically to 50 % and below)
   * the market should be trending; trend strategies fail in range/flat markets


## 2. Project Structure & File-by-File Review

| File | Purpose | Video Rule Mapping | Notes / Discrepancies |
|------|---------|--------------------|-----------------------|
| `config.py` | Central parameters | Contains almost every rule:
• Donchian/MACD settings (periods, filters)
• Risk management (drawdown, cooldown, no max trades)
• Session windows and spread/leverage guards
• Pip definition for XAUUSDm | ✅ Follows video modifications; includes
extra safeguards (daily drawdown) not in original but sensible.
| `challenge_config.py` | Level definitions (balance, lot size, SL/TP pips) | Encodes 30 levels starting at $20; SL/TP fixed at 15/20 pips;
lot sizes chosen so that risk ≈ 23 % of balance each level. | Hard‑coded to XAUUSDm pip size; video strategy supposed to be
market‑agnostic. If you change symbol the levels need re‑calculation.
| `strategy.py` | Entry and exit rules | Implements Donchian breakout, MACD momentum,
M5 EMA trend bias, range filter, early exit (MACD flip). | All filters described in the video are present. Additional
checks (spread, leverage, session) are reasonable enhancements.
| `risk_manager.py` | Drawdown and cooldown | Keeps loss cooldown, daily drawdown,
no trade‑count cap. | Daily drawdown isn’t part of the challenge but
prevents catastrophic failure.
| `execution.py` | MT5 order handling | Standard wrapper. | Nothing related to strategy logic.
| `account_manager.py` | MT5 account credentials | Unrelated. |
| `logger.py` | Logging and trade CSV | Logging includes equity, which allows
later analysis. | Ready for performance tracking.
| `main.py` | Orchestrates trading, ties sections together | Retrieves level info,
asks `evaluate_signal` for entries, respects risk manager. | Everything is wired correctly.
| `telegram_interface.py` | UI | Provides start/stop, reports, account
selection. | Additional convenience, not part of strategy.


### 2.1 Confirmed Conformity

- **Risk percentage and RR** are encoded via `challenge_config` and
  the selection of SL/TP pips (15/20) — the 1.3 : 1 ratio is constant.
- **Levels and compounding**: `get_current_level()` returns the correct level
  based on balance.  It does not automatically advance or regress; it simply
  chooses the row with the highest minimum-balance ≤ current balance. Works as
  intended for the 30‑level challenge.
- **Trade frequency**: there is no per‑day limit; the loop takes signals as they
  appear and only prevents re‑entry for `LOSS_COOLDOWN_CANDLES` after a losing
  trade, exactly as the video’s modified rules say.
- **Trend requirement**: the M5 EMA bias ensures a trend exists, and the
  range filter discards flat markets.  These correspond directly to the
  “trending market” caveat in the video.
- **Session filtering**: while not explicitly mentioned in the summary, the
  video’s tested bots used the London/NY sessions; the code restricts trading to
  these windows.  (Asian session is optionally early‑morning.)
- **Early exit**: the video didn’t describe an early‑exit rule, but the code’s
  MACD‑flip close is a reasonable enhancement and doesn’t break the challenge
  logic.

### 2.2 Deviations / Missing Pieces

1. **Market‑specific deployment**
   - The architecture is tied to `MT5_SYMBOL = "XAUUSDm"` and `PIP_SIZE = 0.10`.
     The original claim was that the 20‑pip challenge works in *any* market
     (stocks, crypto, forex).  To achieve that you would need to remove the
     hard‑coded pip size and regenerate `LEVELS` programmatically from the
     30 % compounding formula.
   - The current `challenge_config` uses fixed lot sizes.  A generic version
     should calculate lots on‑the‑fly based on risk percentage rather than
     storing them in a list.
2. **Level downgrades**
   - The video rules say if balance drops below the level’s minimum but remains
     above the previous level, revert to the earlier level. `get_current_level`
     already handles this correctly because it computes the highest level
     ≤ balance; no fix needed.
3. **Risk percentage enforcement**
   - The 23 % risk per trade is implied by the lot sizes plus SL.  It would be
     safer to calculate `lot = risk_pct * balance / (sl_pips * pip_value)` on
     every trade and ignore the pre‑computed table, ensuring the risk ratio
     remains precise even if the broker changes spread or minimum volume.
4. **Day‑of‑week performance**
   - The project contains no code analysing which weekdays or sessions perform
     best.  This is part of your question and currently missing.  We can
     implement a small analysis script that reads `trade_logs.csv` and
     aggregates PnL/WR by weekday and session.
5. **Backtesting / statistical testing**
   - The video ran 1 000 simulated bots; the repo has no backtester.  The live
     trading code could be wrapped in a simulator, but that’s outside the
     existing files.
6. **Clipboard**
   - **20‑pip-a-day name**: not relevant; removed per video.
   - **Winning streak requirement**: removed correctly.
   - **Export of levels spreadsheet**: there is no generated sheet, only the
     hard‑coded table.  If you need the Excel sheet you must recreate it manually
     or add a generator function.


## 3. Recommendations & Fixes

| Issue | Suggested Change | Why it matters |
|-------|------------------|----------------|
| Strategy tied to XAUUSDm/pip size | Replace static `LEVELS` with a generator function that
computes balances, lot sizes and pip targets from a single risk percentage
and pip value parameter.  Alternatively, make `PIP_SIZE` adjustable per
symbol and regenerate levels on start. | Allows running on forex pairs, crypto, stocks.
| Lot sizing not re‑computed | Add helper in `main.py` to calculate lot by risk % at the time of entry
instead of fetching `lot` from level file.  Or verify that the table always
maintains 23 % risk when balance changes. | Ensures risk stays accurate with account drift.
| Day‑of‑week / session analytics missing | Add a new utility script (`analyse_trades.py`) that reads the CSV and
produces summary stats by weekday and session; optionally include this
function in the Telegram report command. | Answers "which days the bot works best".
| No backtesting or simulation | If you want to replicate the 1 000‑bot results you’ll need a separate
simulator module that can feed `evaluate_signal` historic data and
randomised wins/losses. | Useful for research but not strictly necessary for live trading.

### Example of analytics script (skeleton)

```python
# analyse_trades.py
from logger import read_today_trades, compute_daily_stats
import pandas as pd

trades = pd.read_csv("data/trade_logs.csv", parse_dates=["timestamp"])
trades['weekday'] = trades['timestamp'].dt.day_name()
summary = trades.groupby('weekday').agg(
    total=('pnl','count'),
    wins=('result', lambda s: (s=='WIN').sum()),
    pnl=('pnl','sum')
)
print(summary)
```

You could extend this to compute win rate per day, average trade, etc., and
incorporate it into `_send_report_coroutine()`.


## 4. Performance Considerations & "Best Days"

- **What works best?**  The strategy is *trend‑dependent*; you will get the
  strongest results during extended trending periods in the London/New York
  sessions.  Historically, major trend moves often begin around the London
  open (07:00 UTC) and continue into the North American session.  Conversely,
  Fridays tend to be choppy as traders close positions, and weekends have no
  activity.  Without historical data the bot can’t know ahead of time, so you
  rely on the M5 EMA and range filters to self‑select optimal days.
- **Weekday analysis**: The script above will reveal empirically which
  weekdays have the highest win rate or average PnL in your own trading
  history.  Many traders find Monday and Friday weaker and Tuesday–Thursday
  stronger for trend setups on XAUUSD, but your results may differ.
- **Calendar effects**: Holidays, economic news, and major announcements can
  dramatically change winning probability.  The bot currently has no calendar
  awareness.


## 5. Getting It Working

1. **Configuration**: review `config.py` and set the constants according to your
   broker and desired account characteristics (e.g. adjust `MIN_RANGE_PRICE`
   if symbol changes).
2. **MT5 connection**: ensure you saved account details via
   `account_manager.add_account()` and selected it via Telegram.
3. **Run the bot**: `python main.py` — it will log heartbeats and trades to
   `data/trade_logs.csv` and send reports via Telegram if configured.
4. **Analyse results**: either run the analytics script or examine the CSV in
   Excel/LibreOffice to verify win rate and identify best days.


## 6. Conclusions

The existing project is **mostly faithful** to the YouTube strategy as modified
by the video’s author.  It encodes the high‑risk 23 %/30 % rule, uses a
Donchian+MACD trending system, and drops all unrealistic constraints.  The
primary gaps are generality across symbols and absence of performance
analysis by weekday or session.  Those can be fixed by:

* refactoring level computation to be generic,
* calculating lot sizes dynamically from the risk percentage,
* adding a logging/analysis component that summarises results by day.

Once those changes are in place, the bot will not only *match* the video but
also provide you with the information you asked for (“which week day is best
for its working, how to fix missing pieces, etc.”).

---

You can expand this file later with actual empirical data once you’ve run the
bot for a while.  For now it serves as a blueprint and audit of the current
codebase.
