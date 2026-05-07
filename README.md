# Gold Bot – XAUUSD Automated Trading System (20 Pips Challenge)

## Deployment Guide

---

### 1. Requirements

- Windows VPS (Windows Server 2019/2022/2023 recommended)
- Python 3.11+
- MetaTrader 5 terminal installed and logged in to your broker
- Telegram Bot Token (from @BotFather)
- Your Telegram Chat ID
- Stable wifi

---

### 2. Install Dependencies

```bash
pip install MetaTrader5 python-telegram-bot==20.7 pandas cryptography pytz
```

---

### 3. Project Setup

```bash
# Clone or copy the gold_bot/ folder to your VPS
# Navigate into it
cd gold_bot

# Create data directory
mkdir data reports
```

---

### 4. Configuration

Edit `config.py`:

```python
TELEGRAM_TOKEN = "YOUR_BOT_TOKEN_FROM_BOTFATHER"
ALLOWED_CHAT_IDS = [123456789]  # Your Telegram numeric chat ID
```

Or set as environment variables (recommended for security):

```powershell
$env:TELEGRAM_TOKEN = "YOUR_TOKEN"
$env:ALLOWED_CHAT_IDS = "123456789"
```

---

### 5. Run the Bot

```bash
python main.py
```

---

### 6. First-Time Usage

1. Open Telegram, message your bot
2. Send `/add_account` and follow the prompts (login, password, server)
3. Send `/select_account` to connect MT5
4. Send `/start` to begin trading

---

### 7. Running as a Windows Service (Optional)

Use NSSM (Non-Sucking Service Manager):

```powershell
# Download nssm.exe
nssm install GoldBot "C:\Python311\python.exe" "C:\gold_bot\main.py"
nssm set GoldBot AppDirectory "C:\gold_bot"
nssm start GoldBot
```

---

### 8. Security Hardening

- **Never share** `data/key.key` – this decrypts your MT5 credentials
- Restrict VPS firewall to allow only your IP for RDP
- Use Windows Defender / Firewall to block unused ports
- Store `TELEGRAM_TOKEN` as an environment variable, not in source code
- Back up `data/accounts.json` and `data/key.key` together (both needed for decryption)
- Enable Windows auto-updates and run antivirus

---

### 9. Bot Commands Reference

| Command | Action |
|---|---|
| `/start` | Enable trading |
| `/stop` | Pause trading (keeps positions open) |
| `/kill` | Close all positions and halt trading |
| `/status` | Show balance, equity, PnL, level |
| `/add_account` | Add new MT5 account (encrypted) |
| `/select_account` | Switch active MT5 account |
| `/daily_report` | Get today's trade summary |

---

### 10. Log Files

- `data/trade_logs.csv` – all trade records
- Console output with timestamps

### 11. Performance Analysis

A helper script `analyse_trades.py` is included to summarise results by
weekday and session.  Run it manually to see which days of the week or which
session windows have produced the highest win rate / PnL:

```bash
python analyse_trades.py
```

The Telegram daily report also includes a quick overview of all‑time weekday
performance.


---

### 12. Challenge Ladder Summary

30 levels from $20 balance / 0.02 lot → $30,100 balance / 6.86 lot.
SL = 15 pips, TP = 20 pips on all levels.
The bot automatically selects the lot size for the current balance level.
