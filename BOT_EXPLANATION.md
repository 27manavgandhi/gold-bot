# Gold Bot - Complete System Explanation

## 🤖 What is Gold Bot?

**Gold Bot** is an automated XAUUSD trading system that runs 24/7 on MetaTrader 5 with Telegram control. It executes algorithmic trades based on the **Donchian Channel Breakout Strategy** with strict risk management and real-time trade monitoring via Telegram. It is basically 20 pips challenege

---

## 📊 Trading Strategy

### **Donchian Channel Breakout Strategy**

The bot uses an enhanced Donchian Channel breakout:

#### **Core Logic:**
1. **Donchian Channel (15 candles)** - Tracks the highest and lowest prices over 15 M5 candles
2. **MACD Confirmation** - Validates momentum before entry (threshold: 0.15)
3. **EMA Filter** - Fast EMA (12) and Slow EMA (26) confirm trend direction
4. **Range Expansion Check** - Requires 3.0+ pips movement over 20 candles
5. **Spread Validation** - Only trades when spread ≤ 50 points
6. **M5 Bias Confirmation** - Additional momentum verification on M5 timeframe

#### **Entry Conditions:**
- Price breaks above Donchian high **+** MACD positive **+** EMA fast > EMA slow
- OR price breaks below Donchian low **+** MACD negative **+** EMA fast < EMA slow
- Spread must be tight (≤ 50 points)
- Session must be active (London or New York market hours)

#### **Exit Conditions:**
- **Take Profit**: Risk/Reward ratio of 2:1 (profit = 2 × risk amount)
- **Stop Loss**: Fixed at 20 pips from entry
- **Early Exit**: MACD histogram reversal detection

---

## 🏗️ Architecture & Components

### **Core Modules:**

| Module | Purpose |
|--------|---------|
| **main.py** | Entry point; starts Telegram bot and trading loop in parallel threads |
| **strategy.py** | Donchian breakout logic, indicator calculations, signal evaluation |
| **execution.py** | Places/closes orders, manages positions, handles MT5 connections |
| **telegram_interface.py** | Telegram bot commands, real-time updates, user control |
| **risk_manager.py** | Position sizing, leverage validation, drawdown tracking |
| **account_manager.py** | MT5 account login/logout, credential encryption |
| **challenge_config.py** | Challenge level configuration and validation |
| **config.py** | Global parameters (symbols, timeframes, thresholds) |
| **logger.py** | Centralized logging system |
| **spread_logger.py** | Tracks spread data to CSV for analysis |

---

## 🎮 User Control via Telegram

The bot is fully controlled through Telegram commands:

### **Account Management:**
- `/add_account` - Add MT5 credentials (encrypted storage)
- `/select_account` - Choose active trading account
- `/list_accounts` - View all stored accounts
- `/remove_account` - Delete account credentials

### **Trading Control:**
- `/start` - Enable automated trading
- `/stop` - Disable trading (positions stay open)
- `/close_all` - Close all open positions immediately
- `/status` - Show current bot status, active account, trading state

### **Information & Reports:**
- `/positions` - Show all open positions with details
- `/balance` - Display account balance, equity, margin
- `/trades` - Show recent closed trades
- `/help` - Display all commands
- `/report` - Generate daily trading report

---

## ⚙️ Key Features

### **Security:**
✅ Encrypted credential storage (AES-256 encryption via cryptography library)  
✅ Telegram-only control (chat ID whitelist validation)  
✅ No credentials in source code  
✅ Auto-backup of encryption key and accounts  

### **Risk Management:**
✅ Configurable leverage limits (0.1x to 500x)  
✅ Dynamic position sizing based on account balance  
✅ Drawdown tracking and alerts  
✅ Maximum loss per trade validation  
✅ Account equity-based risk calculations  

### **Trading:**
✅ Multi-timeframe analysis (M1, M5, M15 candles)  
✅ Real-time spread monitoring  
✅ MACD, EMA, Donchian indicators  
✅ Early exit detection  
✅ Session-aware trading (London/New York hours)  

### **Logging & Monitoring:**
✅ Detailed trade logs (entry, exit, P&L)  
✅ Spread logging to CSV (every trade check)  
✅ Daily performance reports  
✅ Real-time Telegram alerts  
✅ Trade analysis and statistics  

---

## 📁 File Structure

```
gold_bot/
├── main.py                          # Entry point
├── strategy.py                      # Trading logic
├── execution.py                     # Order execution
├── telegram_interface.py            # Telegram bot
├── risk_manager.py                  # Risk controls
├── account_manager.py               # Account management
├── config.py                        # Configuration
├── logger.py                        # Logging
├── spread_logger.py                 # Spread tracking
├── challenge_config.py              # Challenge levels
├── data/
│   ├── accounts.json                # Encrypted account credentials
│   ├── key.key                      # Encryption key (KEEP SAFE!)
│   ├── trade_logs.csv               # Trade history
│   └── spread_logs/                 # Spread data by date
├── reports/                         # Generated trading reports
└── README.md                        # Deployment guide
```

---

## 🚀 How It Works

### **Startup Process:**
1. User runs `python main.py`
2. Telegram bot initializes and awaits commands
3. Trading loop starts in background thread
4. Bot waits for `/add_account` → account stored encrypted
5. `/select_account` → connects to MT5
6. `/start` → begins automated trading

### **Trading Loop (Every M5 Candle):**
1. Fetch last 50 M5 candles for XAUUSD
2. Calculate Donchian Channel
3. Calculate MACD & EMA indicators
4. Check spread (if > 50 points, skip)
5. Evaluate buy/sell signal
6. If signal: validate risk, place order
7. Monitor open positions for exit conditions
8. Log trade to CSV, send Telegram update

### **Daily Report (17:00 UTC):**
- Total trades today
- Win rate
- Total P&L
- Largest win/loss
- Sent to all users via Telegram

---

## 💾 Data Storage

### **accounts.json:**
```json
{
  "profiles": [
    {
      "alias": "Profile1",
      "login": "[encrypted]",
      "password": "[encrypted]",
      "server": "ICMarketsSC-Demo"
    }
  ]
}
```
*Encrypted with AES-256 using key stored in `data/key.key`*

### **trade_logs.csv:**
Columns: Entry Time, Exit Time, Symbol, Pair, Type, Entry Price, Exit Price, Volume, Profit, Status

### **spread_logs/:**
CSV files by date tracking every spread check and value

---

## 🔧 Configuration Parameters (config.py)

| Parameter | Value | Purpose |
|-----------|-------|---------|
| MT5_SYMBOL | "XAUUSD" | Trading instrument |
| LEVERAGE_MIN | 0.1 | Minimum leverage allowed |
| DONCHIAN_PERIOD | 15 | Candles for Donchian Channel |
| MACD_HIST_MIN | 0.15 | Minimum MACD histogram for signal |
| SPREAD_MAX_POINTS | 50 | Maximum spread in points to trade |
| RISK_PER_TRADE | 2.0 | Risk as % of account balance |
| STOP_LOSS_PIPS | 20 | Stop loss distance in pips |

---

## 📈 Risk Management Formula

**Position Size = (Account Equity × Risk % / Stop Loss Pips) / Pip Value**

Example:
- Account: $10,000
- Risk: 2% = $200
- Stop Loss: 20 pips
- Pip Value: $100
- Position: (10,000 × 0.02 / 20) / 100 = **0.1 lot**

---

## ⚠️ Important Notes

✏️ **This bot trades REAL MONEY if connected to a live account**  
🔐 **Never expose `data/key.key` or `accounts.json`**  
📝 **Always test on demo first**  
🛑 **Monitor trades regularly via Telegram**  
💾 **Backup encryption key and accounts regularly**  

---

## 🚀 Quick Start

```bash
# Install dependencies
pip install MetaTrader5 python-telegram-bot==20.7 pandas cryptography pytz

# Configure Telegram
export TELEGRAM_TOKEN="your_token_here"
export ALLOWED_CHAT_IDS="123456789"

# Run
python main.py

# Via Telegram:
/add_account
/select_account
/start
/positions
```

---

**Gold Bot** - Automated XAUUSD Trading | Donchian Breakout Strategy | Telegram Controlled  
*Use at your own risk. Past performance ≠ future results.*
