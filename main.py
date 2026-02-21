import MetaTrader5 as mt5
import time
from strategy import check_signal
from execution import place_trade, leverage_is_unlimited
from telegram_interface import run_bot, TRADING_ENABLED

if not mt5.initialize():
    print("MT5 init failed")

run_bot()

while True:
    if TRADING_ENABLED and leverage_is_unlimited():
        signal = check_signal()
        if signal:
            place_trade(signal)
    time.sleep(10)