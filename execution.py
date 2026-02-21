import MetaTrader5 as mt5
from challenge_config import CHALLENGE_LEVELS
from config import SYMBOL

def get_current_level(balance):
    level = CHALLENGE_LEVELS[0]
    for l in CHALLENGE_LEVELS:
        if balance >= l["balance"]:
            level = l
    return level

def leverage_is_unlimited():
    account = mt5.account_info()
    return account.leverage >= 2000

def place_trade(signal):
    account = mt5.account_info()
    level = get_current_level(account.balance)

    lot = level["lot"]
    sl_pips = level["sl"]
    tp_pips = level["tp"]

    price = mt5.symbol_info_tick(SYMBOL).ask if signal == "BUY" else mt5.symbol_info_tick(SYMBOL).bid
    point = mt5.symbol_info(SYMBOL).point

    sl = price - sl_pips * point if signal == "BUY" else price + sl_pips * point
    tp = price + tp_pips * point if signal == "BUY" else price - tp_pips * point

    request = {
        "action": mt5.TRADE_ACTION_DEAL,
        "symbol": SYMBOL,
        "volume": lot,
        "type": mt5.ORDER_TYPE_BUY if signal == "BUY" else mt5.ORDER_TYPE_SELL,
        "price": price,
        "sl": sl,
        "tp": tp,
        "deviation": 5,
        "magic": 10001,
        "comment": "20pip_bot",
        "type_time": mt5.ORDER_TIME_GTC,
        "type_filling": mt5.ORDER_FILLING_IOC,
    }

    result = mt5.order_send(request)
    return result