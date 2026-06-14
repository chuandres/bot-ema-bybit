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
QTY = 3000 # DOGE fijo por trade
LEVERAGE = 75
RISK_USD = 1 # Stop Loss $1
REWARD_USD = 2 # Take Profit $2

# === INPUTS DEL INDICADOR ===
pivotLen = 10
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

def send_telegram(msg):
    if TELEGRAM_TOKEN and TELEGRAM_CHAT_ID:
        url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
        data = {"chat_id": TELEGRAM_CHAT_ID, "text": msg}
        try:
            requests.post(url, data=data)
        except Exception as e:
            print(f"Error Telegram: {e}")

def get_ohlcv():
    try:
        ohlcv = exchange.fetch_ohlcv(SYMBOL, TIMEFRAME, limit=250)
        df = pd.DataFrame(ohlcv, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume'])
        return df
    except Exception as e:
        print(f"Error fetch_ohlcv: {e}")
        return None

def calc_indicators(df):
    # EMAs
    df['ema9'] = df['close'].ewm(span=ema9Len, adjust=False).mean()
    df['ema21'] = df['close'].ewm(span=ema21Len, adjust=False).mean()
    df['ema50'] = df['close'].ewm(span=ema50Len, adjust=False).mean()
    df['ema200'] = df['close'].ewm(span=ema200Len, adjust=False).mean()
    
    # BB
    df['bbMiddle'] = df['close'].rolling(bbLen).mean()
    bb_std = df['close'].rolling(bbLen).std()
    df['bbUpper'] = df['bbMiddle'] + bb_std * bbMult
    df['bbLower'] = df['bbMiddle'] - bb_std * bbMult
    
    # RSI
    delta = df['close'].diff()
    gain = (delta.where(delta > 0, 0)).rolling(rsiLen).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(rsiLen).mean()
    rs = gain / loss
    df['rsi'] = 100 - (100 / (1 + rs))
    
    # ATR
    high_low = df['high'] - df['low']
    high_close = np.abs(df['high'] - df['close'].shift())
    low_close = np.abs(df['low'] - df['close'].shift())
    ranges = pd.concat([high_low, high_close, low_close], axis=1)
    true_range = np.max(ranges, axis=1)
    df['atr'] = true_range.rolling(atrLen).mean()
    
    # ADX
    plus_dm = df['high'].diff()
    minus_dm = df['low'].diff()
    plus_dm[plus_dm < 0] = 0
    minus_dm[minus_dm > 0] = 0
    tr = true_range
    plus_di = 100 * (plus_dm.ewm(alpha=1/adxLen).mean() / tr.ewm(alpha=1/adxLen).mean())
    minus_di = abs(100 * (minus_dm.ewm(alpha=1/adxLen).mean() / tr.ewm(alpha=1/adxLen).mean()))
    dx = (abs(plus_di - minus_di) / abs(plus_di + minus_di)) * 100
    df['adx'] = dx.ewm(alpha=1/adxLen).mean()
    
    # Volumen
    df['volAvg'] = df['volume'].rolling(20).mean()
    
    # Pivots
    df['pl'] = df['low'][(df['low'].shift(pivotLen) > df['low']) & (df['low'].shift(-pivotLen) > df['low'])]
    df['ph'] = df['high'][(df['high'].shift(pivotLen) < df['high']) & (df['high'].shift(-pivotLen) < df['high'])]
    
    # Mechas
    body = abs(df['close'] - df['open'])
    barRange = df['high'] - df['low']
    upperWick = df['high'] - df[['open', 'close']].max(axis=1)
    lowerWick = df[['open', 'close']].min(axis=1) - df['low']
    df['wickLongPct'] = np.where(barRange > 0, lowerWick / barRange * 100, 0)
    df['wickShortPct'] = np.where(barRange > 0, upperWick / barRange * 100, 0)
    
    return df

def check_signal(df):
    i = len(df) - 2 # PENULTIMA VELA CERRADA - así no espera 1min
    if i < 200: return None, 0, 0
    
    row = df.iloc[i]
    
    # === FILTROS ===
    f_rsiLong = row['rsi'] < rsiLongMax
    f_rsiShort = row['rsi'] > rsiShortMin
    f_bbLong = row['low'] <= row['bbLower']
    f_bbShort = row['high'] >= row['bbUpper']
    f_pivotLong = not pd.isna(row['pl'])
    f_pivotShort = not pd.isna(row['ph'])
    f_vol = row['volume'] >= row['volAvg'] * volSpike
    f_wickLong = row['wickLongPct'] >= wickPct
    f_wickShort = row['wickShortPct'] >= wickPct
    f_candleLong = row['close'] > row['open']
    f_candleShort = row['close'] < row['open']
    
    scoreLong = sum([f_rsiLong, f_bbLong, f_pivotLong, f_vol, f_wickLong, f_candleLong])
    scoreShort = sum([f_rsiShort, f_bbShort, f_pivotShort, f_vol, f_wickShort, f_candleShort])
    
    # === LOG PARA DEBUG ===
    print(f"Vela: {datetime.fromtimestamp(row['timestamp']/1000)} | Close: {row['close']:.5f} | L:{scoreLong}/6 S:{scoreShort}/6")
    
    # === ENTRA CON TRIANGULITO ===
    if scoreLong >= 5:
        print(f"✅ TRIANGULO VERDE L{scoreLong} DETECTADO - ENTRANDO LONG")
        return 'long', df.iloc[-1]['close'], row['atr'] # Usa precio actual para entrar
    if scoreShort >= 5:
        print(f"✅ TRIANGULO ROJO S{scoreShort} DETECTADO - ENTRANDO SHORT")
        return 'short', df.iloc[-1]['close'], row['atr']
    
    return None, scoreLong, scoreShort

def set_leverage():
    try:
        exchange.set_margin_mode('isolated', SYMBOL)
        exchange.set_leverage(LEVERAGE, SYMBOL)
        print(f"Leverage {LEVERAGE}x seteado en {SYMBOL}")
    except ccxt.ExchangeError as e:
        if '110043' in str(e) or 'leverage not modified' in str(e):
            print(f"Leverage ya estaba en {LEVERAGE}x - OK")
        elif '110025' in str(e):
            print(f"Error: Tenés una posición abierta. Cerrala para cambiar leverage")
        else:
            print(f"Leverage error: {e}")

def get_position():
    try:
        positions = exchange.fetch_positions([SYMBOL])
        for pos in positions:
            if pos['symbol'] == SYMBOL and float(pos['contracts'])!= 0:
                return pos
        return None
    except Exception as e:
        print(f"Error get_position: {e}")
        return None

def place_order(signal, price, atr):
    try:
        side = 'buy' if signal == 'long' else 'sell'
        
        # SL y TP por USD fijo
        sl_distance = RISK_USD / QTY
        tp_distance = REWARD_USD / QTY
        
        if signal == 'long':
            sl_price = round(price - sl_distance, 5)
            tp_price = round(price + tp_distance, 5)
        else:
            sl_price = round(price + sl_distance, 5)
            tp_price = round(price - tp_distance, 5)
        
        params = {
            'stopLoss': sl_price,
            'takeProfit': tp_price,
        }
        
        print(f"EJECUTANDO ORDEN: {side.upper()} {QTY} DOGE @ {price:.5f} | SL: {sl_price:.5f} | TP: {tp_price:.5f}")
        
        order = exchange.create_order(SYMBOL, 'market', side, QTY, None, params)
        
        msg = f"🚀 {signal.upper()} DOGE\nEntrada: {price:.5f}\nSL: {sl_price:.5f} (-${RISK_USD})\nTP: {tp_price:.5f} (+${REWARD_USD})\nQty: {QTY}"
        print(msg)
        send_telegram(msg)
        return order
        
    except Exception as e:
        print(f"❌ ERROR ORDEN: {e}")
        send_telegram(f"❌ Error orden: {e}")
        return None

def main():
    print("Francotirador DOGE Bot iniciado - MODO TRIANGULITOS 75x")
    send_telegram("🤖 Bot Francotirador DOGE iniciado - 75x - MODO TRIANGULITOS")
    set_leverage()
    
    while True:
        try:
            pos = get_position()
            if pos is None:
                df = get_ohlcv()
                if df is not None:
                    df = calc_indicators(df)
                    signal, scoreL, scoreS = check_signal(df)
                    
                    if signal:
                        place_order(signal, df.iloc[-1]['close'], df.iloc[-2]['atr'])
                        time.sleep(60) # Espera 1min después de entrar
                    else:
                        print(f"Sin señal. Score actual L:{scoreL} S:{scoreS}")
            else:
                print(f"Posición abierta: {pos['side']} {pos['contracts']} DOGE | PNL: {pos['unrealizedPnl']}")
            
            time.sleep(5) # Check cada 5s
            
        except Exception as e:
            print(f"Error main loop: {e}")
            time.sleep(30)

if __name__ == "__main__":
    main()
