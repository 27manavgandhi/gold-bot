
from datetime import time
import pandas as pd
import os

TRADE_LOG = "data/trade_logs.csv"

# Define session boundaries (UTC)
SESSIONS = {
    "ASIAN":  (time(4, 0), time(6, 0)),
    "LONDON": (time(7, 0), time(16, 0)),
    "NY":     (time(12, 0), time(21, 0)),
}


def load_trades() -> pd.DataFrame:
    """Load trade CSV and compute derived fields."""
    if not os.path.exists(TRADE_LOG):
        return pd.DataFrame()
    
    df = pd.read_csv(TRADE_LOG, parse_dates=["timestamp"])
    if df.empty:
        return df
    
    df["weekday"] = df["timestamp"].dt.day_name()
    df["hour"] = df["timestamp"].dt.hour
    df["time"] = df["timestamp"].dt.time
    df["pnl"] = pd.to_numeric(df["pnl"], errors="coerce").fillna(0.0)
    df["result_binary"] = (df["result"] == "WIN").astype(int)
    
    return df


def assign_session(row):
    """Assign session label based on UTC hour."""
    t = row["time"]
    for name, (start, end) in SESSIONS.items():
        if start <= t < end:
            return name
    return "OTHER"


def summary_by_weekday(df: pd.DataFrame) -> pd.DataFrame:
    """Win rate, PnL, and stats grouped by weekday."""
    if df.empty:
        return pd.DataFrame()
    
    grp = df.groupby("weekday").agg(
        total_trades=("result", "count"),
        wins=("result_binary", "sum"),
        losses=("result_binary", lambda x: (~x.astype(bool)).sum()),
        total_pnl=("pnl", "sum"),
        avg_pnl=("pnl", "mean"),
        max_win=("pnl", lambda x: x[x > 0].max() if (x > 0).any() else 0),
        max_loss=("pnl", lambda x: x[x < 0].min() if (x < 0).any() else 0),
    )
    
    grp["win_rate_pct"] = (grp["wins"] / grp["total_trades"] * 100).round(1)
    grp = grp.sort_values("total_trades", ascending=False)
    
    return grp


def summary_by_session(df: pd.DataFrame) -> pd.DataFrame:
    """Win rate, PnL, and stats grouped by trading session."""
    if df.empty:
        return pd.DataFrame()
    
    df_copy = df.copy()
    df_copy["session"] = df_copy.apply(assign_session, axis=1)
    
    grp = df_copy.groupby("session").agg(
        total_trades=("result", "count"),
        wins=("result_binary", "sum"),
        losses=("result_binary", lambda x: (~x.astype(bool)).sum()),
        total_pnl=("pnl", "sum"),
        avg_pnl=("pnl", "mean"),
        max_win=("pnl", lambda x: x[x > 0].max() if (x > 0).any() else 0),
        max_loss=("pnl", lambda x: x[x < 0].min() if (x < 0).any() else 0),
    )
    
    grp["win_rate_pct"] = (grp["wins"] / grp["total_trades"] * 100).round(1)
    grp = grp.sort_values("total_trades", ascending=False)
    
    return grp


def summary_by_signal_type(df: pd.DataFrame) -> pd.DataFrame:
    """Win rate comparison between BUY and SELL signals."""
    if df.empty:
        return pd.DataFrame()
    
    grp = df.groupby("signal").agg(
        total_trades=("result", "count"),
        wins=("result_binary", "sum"),
        total_pnl=("pnl", "sum"),
        avg_pnl=("pnl", "mean"),
    )
    
    grp["win_rate_pct"] = (grp["wins"] / grp["total_trades"] * 100).round(1)
    
    return grp


def compute_probability_metrics(df: pd.DataFrame) -> dict:
    """
    Compute key probability metrics for TP vs SL hits.
    
    Given RR ratio = 1.3:1 (20 pips TP, 15 pips SL):
    - Probability of hitting TP vs SL
    - Break-even win rate needed
    - Expected value per trade
    """
    if df.empty:
        return {}
    
    total = len(df)
    wins = (df["result"] == "WIN").sum()
    losses = (df["result"] == "LOSS").sum()
    early_exits = (df["result"] == "EARLY_EXIT").sum()
    
    if total == 0:
        return {}
    
    empirical_wr = wins / total
    
    # Theoretical metrics (1.3:1 RR)
    tp_pips = 20  # 2.0 price units
    sl_pips = 15  # 1.5 price units
    rr_ratio = tp_pips / sl_pips
    
    # Break-even win rate: WR / (1 + WR/RR)
    breakeven_wr = 1 / (1 + rr_ratio)
    
    # Expected value if empirical WR holds
    avg_win = df[df["result"] == "WIN"]["pnl"].mean() if wins > 0 else 0
    avg_loss = abs(df[df["result"] == "LOSS"]["pnl"].mean()) if losses > 0 else 0
    
    ev_per_trade = (empirical_wr * avg_win) - ((1 - empirical_wr) * avg_loss)
    
    return {
        "total_trades": total,
        "wins": wins,
        "losses": losses,
        "early_exits": early_exits,
        "empirical_win_rate": round(empirical_wr * 100, 2),
        "theoretical_breakeven_wr": round(breakeven_wr * 100, 2),
        "rr_ratio": round(rr_ratio, 2),
        "tp_pips": tp_pips,
        "sl_pips": sl_pips,
        "average_win_pnl": round(avg_win, 2),
        "average_loss_pnl": round(avg_loss, 2),
        "expected_value_per_trade": round(ev_per_trade, 2),
        "profitable": ev_per_trade > 0,
    }


def print_pretty_table(title: str, df: pd.DataFrame):
    """Print a nicely formatted table."""
    print(f"\n{'=' * 100}")
    print(f"  {title}")
    print(f"{'=' * 100}\n")
    print(df.to_string())
    print()


def main():
    df = load_trades()
    
    if df.empty:
        print("❌ No trades logged yet. Run the bot and collect data first.\n")
        return
    
    # === SUMMARY BY WEEKDAY ===
    wkd = summary_by_weekday(df)
    print_pretty_table("Win Rate & PnL by Weekday (Which day works best?)", wkd)
    
    # === SUMMARY BY SESSION ===
    sess = summary_by_session(df)
    print_pretty_table("Win Rate & PnL by Session (Which session is best?)", sess)
    
    # === SUMMARY BY SIGNAL TYPE ===
    sig = summary_by_signal_type(df)
    print_pretty_table("BUY vs SELL Performance", sig)
    
    # === PROBABILITY METRICS ===
    prob = compute_probability_metrics(df)
    
    if prob:
        print(f"\n{'=' * 100}")
        print("  Probability & Profitability Analysis")
        print(f"{'=' * 100}\n")
        print(f"Total Trades Analysed:        {prob['total_trades']}")
        print(f"Wins:                         {prob['wins']} ({prob['empirical_win_rate']:.1f}%)")
        print(f"Losses:                       {prob['losses']}")
        print(f"Early Exits:                  {prob['early_exits']}")
        print(f"\nRisk/Reward Setup:")
        print(f"  Take-Profit:                {prob['tp_pips']} pips (2.0 price units)")
        print(f"  Stop-Loss:                  {prob['sl_pips']} pips (1.5 price units)")
        print(f"  RR Ratio:                   1:{prob['rr_ratio']}")
        print(f"\nBreak-Even Analysis:")
        print(f"  Theoretical Break-Even WR:  {prob['theoretical_breakeven_wr']:.1f}%")
        print(f"  Your Empirical WR:          {prob['empirical_win_rate']:.1f}%")
        if prob['empirical_win_rate'] >= prob['theoretical_breakeven_wr']:
            margin = prob['empirical_win_rate'] - prob['theoretical_breakeven_wr']
            print(f"  ✅ PROFITABLE MARGIN:       +{margin:.1f}% above break-even")
        else:
            deficit = prob['theoretical_breakeven_wr'] - prob['empirical_win_rate']
            print(f"  ❌ DEFICIT:                 -{deficit:.1f}% below break-even")
        
        print(f"\nPnL Statistics:")
        print(f"  Average Win:                ${prob['average_win_pnl']:.2f}")
        print(f"  Average Loss:               -${prob['average_loss_pnl']:.2f}")
        print(f"  Expected Value per Trade:   ${prob['expected_value_per_trade']:.2f}")
        print(f"  Profitable Strategy:        {'YES ✅' if prob['profitable'] else 'NO ❌'}")
        print()


if __name__ == "__main__":
    main()
