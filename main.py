import ccxt
import time
import os
from datetime import datetime

# ========== CONFIGURACIÓN ETH ==========
API_KEY = os.getenv('BYBIT_API_KEY')
API_SECRET = os.getenv('BYBIT_API_SECRET')
SYMBOL = 'ETH/USDT:USDT'
TIMEFRAME = '4h'
QTY = 0.01 # MÍNIMO DE BYBIT PARA ETH = 0.01 ETH = ~$16.8
LEVERAGE = 5 # 5x = seguro. Con $16 necesitas ~$3.4 de margen
STOP_LOSS_PCT = 0.03 # Stop Loss 3%
# =======================================

exchange = ccxt.bybit({
    'apiKey': API_KEY,
    'secret': API_SECRET,
    'enableRateLimit': True,
    'options': {'defaultType': 'linear'},
})

def set_leverage():
    try:
        exchange.set_leverage(LEVERAGE, SYMBOL)
        exchange.set_margin_mode('isolated', SYMBOL)
        print(f"Apalancamiento {LEVERAGE}x | Margen Isolada configurado para ETH")
    except Exception as e:
        if '110043' not in str(e):
            print(f"Error config: {e}")

def get_emas():
    try:
        ohlcv = exchange.fetch_ohlcv(SYMBOL, TIMEFRAME, limit=100)
        closes = [x[4] for x in ohlcv]
        
        ema9 = closes[0]
        k9 = 2 / (9 + 1)
        for price in closes[1:]:
            ema9 = price * k9 + ema9 * (1 - k9)
        
        ema21 = closes[0]
        k21 = 2 / (21 + 1)
        for price in closes[1:]:
            ema21 = price * k21 + ema21 * (1 - k21)
            
        return round(ema9, 2), round(ema21, 2), closes[-1]
    except Exception as e:
        print(f"Error EMAs: {e}")
        return None, None, None

def get_position():
    try:
        positions = exchange.fetch_positions([SYMBOL])
        for pos
