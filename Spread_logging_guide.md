# SPREAD LOGGING FEATURE - Complete Guide

## 📊 **WHAT THIS DOES:**

Your bot now **automatically logs spread data** to a CSV file every time it checks the spread during signal evaluation.

This helps you:
- ✅ Analyze spread patterns by time of day
- ✅ Identify best trading hours
- ✅ Understand why trades are blocked
- ✅ Optimize SPREAD_MAX_POINTS parameter

---

## 🎯 **HOW IT WORKS:**

### **Automatic Logging:**

1. **When you `/start` the bot** → Spread logging begins
2. **Every candle** → Bot checks spread and logs to CSV
3. **When you `/stop` or `/kill`** → Spread logging stops and file is saved

### **What Gets Logged:**

Each row in the CSV contains:
- **timestamp** - Date and time (2026-03-11 17:23:03)
- **utc_time** - Time only (17:23:03)
- **spread_points** - Spread in MT5 points (360)
- **spread_pips** - Spread in pips (36.0)
- **max_allowed** - Your configured max (50)
- **status** - "OK" or "BLOCKED"
- **bid** - Current bid price (5063.761)
- **ask** - Current ask price (5064.121)
- **session** - Trading session (London/NY/London+NY/OffHours)

---

## 📁 **FILE LOCATIONS:**

Spread logs are saved to:
```
C:\Users\hp\Downloads\gold_bot\gold_bot\data\spread_logs\
```

**File naming:**
```
spread_log_20260311_172303.csv
spread_log_20260311_193045.csv
spread_log_20260312_083012.csv
```

Each `/start` command creates a **NEW file** with timestamp in filename.

---

## 📊 **EXAMPLE CSV DATA:**

```csv
timestamp,utc_time,spread_points,spread_pips,max_allowed,status,bid,ask,session
2026-03-11 17:23:03,17:23:03,360,36.0,50,BLOCKED,5063.761,5064.121,OffHours
2026-03-11 17:24:03,17:24:03,340,34.0,50,BLOCKED,5063.850,5064.190,OffHours
2026-03-11 17:25:03,17:25:03,45,4.5,50,OK,5064.120,5064.165,London+NY

```

---

## 🎯 **USAGE WORKFLOW:**

### **Start Trading Session:**
```
In Telegram:
/start

Bot responds:
✅ Trading ENABLED on: MyAccount
📊 Spread logging active
Logs: spread_log_20260311_172303.csv
```

### **While Trading:**
Bot automatically logs spread every time it evaluates a signal (every M1 candle close).

**Console output:**
```
2026-03-11 17:23:03 [INFO] GoldBot: BLOCKED >> Spread too high: 360 > 50 (36.0 pips) | Session: OffHours
2026-03-11 17:24:03 [INFO] GoldBot: BLOCKED >> Spread too high: 340 > 50 (34.0 pips) | Session: OffHours
2026-03-11 17:25:03 [INFO] GoldBot: SCAN >> M5=LONG | close=5064.120 ...
```

### **Stop Trading Session:**
```
In Telegram:
/stop

Bot responds:
⏸️ Trading PAUSED
Open positions remain open.
📊 Spread logging saved
```

---

## 📈 **ANALYZING SPREAD DATA:**

### **Method 1: Open in Excel**

1. Navigate to `data/spread_logs/`
2. Open `spread_log_YYYYMMDD_HHMMSS.csv` in Excel
3. Create pivot table or charts

**Useful Analysis:**
- Average spread by session (London vs NY vs Overlap)
- Spread distribution (histogram)
- Blocked % by time of day
- Min/Max spread by hour

### **Method 2: Use Python Analysis**

```python
import pandas as pd

# Load spread log
df = pd.read_csv('data/spread_logs/spread_log_20260311_172303.csv')

# Statistics
print(df.describe())
print(f"Blocked: {len(df[df.status=='BLOCKED'])} / {len(df)}")
print(f"Blocked %: {len(df[df.status=='BLOCKED'])/len(df)*100:.1f}%")

# By session
print(df.groupby('session')['spread_pips'].agg(['mean', 'min', 'max']))

# By hour
df['hour'] = pd.to_datetime(df['timestamp']).dt.hour
print(df.groupby('hour')['spread_pips'].mean())
```

---

## 🔍 **EXAMPLE INSIGHTS:**

After running for 24 hours, you might discover:

### **Insight 1: High Spread During Off Hours**
```
Session      Avg Spread    Blocked %
OffHours     35.2 pips     100%
London       8.5 pips      45%
NY           6.2 pips      20%
London+NY    4.1 pips      5%
```

**Action:** Spread is BEST during overlap (6:30-9:30 PM IST)

### **Insight 2: Spread by Hour (IST)**
```
Hour (IST)   Avg Spread
02:00        42.5 pips  ❌ Terrible
08:00        38.1 pips  ❌ Bad
14:00        9.2 pips   ⚠️  Marginal
18:00        4.8 pips   ✅ Good
20:00        3.5 pips   ✅ Excellent
22:00        5.1 pips   ✅ Good
```

**Action:** Focus trading between 6 PM - 11 PM IST

### **Insight 3: Too Many Blocks**
```
Total Checks: 1440 (24 hours @ 1/min)
Blocked: 1200
Blocked %: 83%
```

**Action:** Your SPREAD_MAX_POINTS (50) may be too strict. Consider increasing to 80-100 for more entries.

---

## ⚙️ **CONFIGURATION:**

If you want to **change max spread**, edit `config.py`:

```python
# Current setting
SPREAD_MAX_POINTS: int = 50   # 5 pips max

# If too strict (blocking 80%+ of checks), try:
SPREAD_MAX_POINTS: int = 80   # 8 pips max

# If too loose (allowing bad spreads), try:
SPREAD_MAX_POINTS: int = 30   # 3 pips max
```

Then restart bot.

---

## 📋 **TYPICAL SPREAD VALUES:**

| Condition | Spread (pips) | Status |
|-----------|---------------|--------|
| London+NY Overlap | 2-5 pips | ✅ Excellent |
| London Only | 5-10 pips | ✅ Good |
| NY Only | 5-12 pips | ✅ Good |
| Asian Session | 15-30 pips | ⚠️ Marginal |
| Weekend/Holiday | 30-100+ pips | ❌ Avoid |
| News Events | 50-200+ pips | ❌ Avoid |

---

## 🎯 **OPTIMIZATION WORKFLOW:**

### **Week 1: Data Collection**
1. Run bot for 1 week with current settings
2. Let it log spread data naturally
3. Don't change anything yet

### **Week 2: Analysis**
1. Open all CSV files in Excel
2. Combine into one dataset
3. Calculate:
   - Average spread by session
   - Blocked % by hour
   - Min/Max spread ranges
4. Identify best trading hours

### **Week 3: Optimization**
1. Adjust SPREAD_MAX_POINTS if needed:
   - Too many blocks (>70%) → increase
   - Too many poor entries → decrease
2. Consider restricting trading hours to best periods only
3. Update London/NY session times if needed

### **Week 4: Validation**
1. Run with new settings
2. Compare results to Week 1
3. Fine-tune as needed

---

## 🛠️ **TROUBLESHOOTING:**

### **No CSV file created:**
- Make sure you sent `/start` command
- Check `data/spread_logs/` folder exists
- Bot must be connected to MT5

### **CSV file empty:**
- Bot is only logging during signal evaluation
- Signal evaluation only happens during London/NY sessions
- If off-hours, wait until trading session

### **Too many BLOCKED entries:**
- Normal! Spread is often high outside overlap hours
- This is GOOD data - shows when NOT to trade
- Consider increasing SPREAD_MAX_POINTS if blocking 90%+

---

## 📊 **SUMMARY:**

✅ **Auto-logging** - Starts with `/start`, stops with `/stop`
✅ **Separate files** - New CSV for each trading session
✅ **Rich data** - Timestamp, spread, bid/ask, session, status
✅ **Analysis ready** - Open in Excel or Python for insights
✅ **Optimization tool** - Find best trading hours and spread limits

**Your bot is now a data collection machine! Use the spread logs to optimize your trading times and maximize profitability.** 📈
