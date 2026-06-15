import ccxt
import os
import time
import pandas as pd
import numpy as np
from datetime import datetime
import requests

# === CONFIG BYBIT ===
API_KEY = os.getenv('BYBIT_API_KEY')
API_SECRET = os.getenv('BYBIT_API_SECRET')
TELEGRAM_TOKEN = os.getenv('TELEGRAM_TOKEN')
TELEGRAM_CHAT_ID = os.getenv('TELEGRAM_CHAT_ID')

# === CONFIG FRANCOTIRADOR DOGE ===
SYMBOL = 'DOGEUSDT'
TIMEFRAME = '1m'
QTY = 3000
LEVERAGE = 75
RISK_USD = 1
REWARD_USD = 2

# === INPUTS DEL INDICADOR ===
pivotLen = 10 # 10 velas a cada lado para confirmar pivot
bbLen = 20
bbMult = 2.5
rsiLen = 14
rsiLongMax = 40
rsiShortMin = 60
wickPct = 60
volSpike = 3.0
ema9Len = 9
ema21Len = 21
ema50Len = 50
ema200Len = 200
adxLen = 14
adxTrendMin = 25
atrLen = 14

# === SETUP EXCHANGE ===
exchange = ccxt.bybit({
    'apiKey': API_KEY,
    'secret': API_SECRET,
    'enableRateLimit': True,
    'options': {
        'defaultType': 'swap',
    }
})

def get_ohlcv(symbol, timeframe, limit=500):
    ohlcv = exchange.fetch_ohlcv(symbol, timeframe, limit=limit)
    df = pd.DataFrame(ohlcv, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume'])
    df['timestamp'] = pd.to_datetime(df['timestamp'], unit='ms')
    return df

def calculate_indicators(df):
    # EMAs
    df['ema9'] = df['close'].ewm(span=ema9Len, adjust=False).mean()
    df['ema21'] = df['close'].ewm(span=ema21Len, adjust=False).mean()
    df['ema50'] = df['close'].ewm(span=ema50Len, adjust=False).mean()
    df['ema200'] = df['close'].ewm(span=ema200Len, adjust=False).mean()
    
    # RSI
    delta = df['close'].diff()
    gain = (delta.where(delta > 0, 0)).rolling(window=rsiLen).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(window=rsiLen).mean()
    rs = gain / loss
    df['rsi'] = 100 - (100 / (1 + rs))
    
    # Bollinger Bands
    df['bb_mid'] = df['close'].rolling(window=bbLen).mean()
    bb_std = df['close'].rolling(window=bbLen).std()
    df['bb_upper'] = df['bb_mid'] + (bb_std * bbMult)
    df['bb_lower'] = df['bb_mid'] - (bb_std * bbMult)
    
    # ADX
    plus_dm = df['high'].diff()
    minus_dm = df['low'].diff()
    plus_dm[plus_dm < 0] = 0
    minus_dm[minus_dm > 0] = 0
    tr1 = pd.DataFrame(df['high'] - df['low'])
    tr2 = pd.DataFrame(abs(df['high'] - df['close'].shift(1)))
    tr3 = pd.DataFrame(abs(df['low'] - df['close'].shift(1)))
    frames = [tr1, tr2, tr3]
    tr = pd.concat(frames, axis=1, join='inner').max(axis=1)
    atr = tr.rolling(adxLen).mean()
    plus_di = 100 * (plus_dm.ewm(alpha=1/adxLen).mean() / atr)
    minus_di = abs(100 * (minus_dm.ewm(alpha=1/adxLen).mean() / atr))
    dx = (abs(plus_di - minus_di) / abs(plus_di + minus_di)) * 100
    df['adx'] = dx.ewm(alpha=1/adxLen).mean()
    
    # ATR
    df['atr'] = tr.rolling(atrLen).mean()
    
    return df

def find_confirmed_pivots(df, pivotLen):
    """
    SOLO marca pivot cuando está 100% confirmado.
    No repinta. Flecha aparece 10 velas después del giro real.
    """
    df['pivot_high'] = False
    df['pivot_low'] = False
    
    # Recorremos dejando espacio para confirmar a ambos lados
    for i in range(pivotLen, len(df) - pivotLen):
        # Pivot High: máximo local confirmado
        if df['high'].iloc[i] == df['high'].iloc[i-pivotLen:i+pivotLen+1].max():
            df.loc[df.index[i], 'pivot_high'] = True
            
        # Pivot Low: mínimo local confirmado 
        if df['low'].iloc[i] == df['low'].iloc[i-pivotLen:i+pivotLen+1].min():
            df.loc[df.index[i], 'pivot_low'] = True
    
    return df

def check_signal(df):
    """
    Ahora las señales solo se dan en pivots confirmados + confluencias
    """
    last_idx = len(df) - pivotLen - 1 # Último pivot confirmable
    if last_idx < 0:
        return None
        
    row = df.iloc[last_idx]
    
    # FILTROS DE CONFLUENCIA
    volume_avg = df['volume'].iloc[last_idx-20:last_idx].mean()
    vol_condition = df['volume'].iloc[last_idx] > volume_avg * volSpike
    
    wick_size = df['high'].iloc[last_idx] - df['low'].iloc[last_idx]
    upper_wick = df['high'].iloc[last_idx] - max(df['open'].iloc[last_idx], df['close'].iloc[last_idx])
    lower_wick = min(df['open'].iloc[last_idx], df['close'].iloc[last_idx]) - df['low'].iloc[last_idx]
    
    trend_long = row['ema9'] > row['ema21'] > row['ema50'] > row['ema200']
    trend_short = row['ema9'] < row['ema21'] < row['ema50'] < row['ema200']
    
    # LONG: Pivot Low confirmado + confluencias
    if row['pivot_low']:
        if (row['rsi'] < rsiLongMax and 
            row['low'] <= row['bb_lower'] and 
            vol_condition and 
            lower_wick / wick_size * 100 > wickPct and
            trend_long and 
            row['adx'] > adxTrendMin):
            
            return {
                'type': 'LONG',
                'price': row['close'],
                'time': row['timestamp'],
                'level': row['low'] # La punta exacta
            }
    
    # SHORT: Pivot High confirmado + confluencias 
    if row['pivot_high']:
        if (row['rsi'] > rsiShortMin and 
            row['high'] >= row['bb_upper'] and 
            vol_condition and 
            upper_wick / wick_size * 100 > wickPct and
            trend_short and 
            row['adx'] > adxTrendMin):
            
            return {
                'type': 'SHORT', 
                'price': row['close'],
                'time': row['timestamp'],
                'level': row['high'] # La punta exacta
            }
    
    return None

def send_telegram(msg):
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    data = {"chat_id": TELEGRAM_CHAT_ID, "text": msg}
    requests.post(url, data=data)

def main():
    exchange.set_leverage(LEVERAGE, SYMBOL)
    last_signal_time = None
    
    while True:
        try:
            df = get_ohlcv(SYMBOL, TIMEFRAME, 500)
            df = calculate_indicators(df)
            df = find_confirmed_pivots(df, pivotLen)
            
            signal = check_signal(df)
            
            if signal and signal['time']!= last_signal_time:
                last_signal_time = signal['time']
                
                if signal['type'] == 'LONG':
                    sl_price = signal['price'] - (RISK_USD / QTY)
                    tp_price = signal['price'] + (REWARD_USD / QTY)
                else:
                    sl_price = signal['price'] + (RISK_USD / QTY)
                    tp_price = signal['price'] - (REWARD_USD / QTY)
                
                msg = f"🚨 {signal['type']} DOGE\nEntrada: {signal['price']:.5f}\nPunta: {signal['level']:.5f}\nSL: {sl_price:.5f}\nTP: {tp_price:.5f}\nHora: {signal['time']}"
                send_telegram(msg)
                print(msg)
                
                # Aquí va tu lógica de ejecución de órdenes
                
        except Exception as e:
            print(f"Error: {e}")
            
        time.sleep(10) # Revisa cada 10s

if __name__ == "__main__":
    main()
