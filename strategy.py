import MetaTrader5 as mt5
import pandas as pd
from config import SYMBOL, ATR_THRESHOLD

def get_data():
    rates = mt5.copy_rates_from_pos(SYMBOL, mt5.TIMEFRAME_M1, 0, 200)
    df = pd.DataFrame(rates)
    df['ema20'] = df['close'].ewm(span=20).mean()
    df['ema50'] = df['close'].ewm(span=50).mean()
    df['tr'] = df['high'] - df['low']
    df['atr'] = df['tr'].rolling(14).mean()
    return df

def volatility_ok(df):
    return df['atr'].iloc[-1] >= ATR_THRESHOLD

def impulse_break_long(df):
    last = df.iloc[-1]
    prev = df.iloc[-2]

    body = abs(last['close'] - last['open'])
    avg_body = abs(df['close'] - df['open']).rolling(5).mean().iloc[-1]

    return (
        last['ema20'] > last['ema50'] and
        body >= 1.5 * avg_body and
        last['close'] > prev['high']
    )

def impulse_break_short(df):
    last = df.iloc[-1]
    prev = df.iloc[-2]

    body = abs(last['close'] - last['open'])
    avg_body = abs(df['close'] - df['open']).rolling(5).mean().iloc[-1]

    return (
        last['ema20'] < last['ema50'] and
        body >= 1.5 * avg_body and
        last['close'] < prev['low']
    )

def check_signal():
    df = get_data()
    if not volatility_ok(df):
        return None

    if impulse_break_long(df):
        return "BUY"

    if impulse_break_short(df):
        return "SELL"

    return None