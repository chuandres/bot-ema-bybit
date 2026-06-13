import ccxt
import time
import os
from datetime import datetime

API_KEY = os.getenv('BYBIT_API_KEY')
API_SECRET = os.getenv('BYBIT_API_SECRET')
SYMBOL = 'BTCUSDT' # Para unified se usa así, sin / ni :USDT
TIMEFRAME = '4h'
QTY = 0.001

exchange = ccxt.bybit({
    'apiKey': API_KEY,
    'secret': API_SECRET,
    'enableRateLimit': True,
    'options': {
        'defaultType': 'swap', # SWAP = futuros USDT en unified
    },
})
exchange.set_sandbox_mode(True)

def get_emas():
    try:
        # Para unified hay que pasar category='linear' explícito
        ohlcv = exchange.fetch_ohlcv(SYMBOL, TIMEFRAME, limit=100, params={'category': 'linear'})
        closes = [x[4] for x in ohlcv]
        
        ema9 = closes[0]
        k9 = 2 / (9 + 1)
        for price in closes[1:]:
            ema9 = price * k9 + ema9 * (1 - k9)
        
        ema21 = closes[0]
        k21 = 2 / (21 + 1)
        for price in closes[1:]:
            ema21 = price * k21 + ema21 * (1 - k21)
            
        return ema9, ema21, closes[-1]
    except Exception as e:
        print(f"Error calculando EMAs: {e}")
        return None, None, None

def get_position():
    try:
        positions = exchange.fetch_positions([SYMBOL], params={'category': 'linear'})
        for pos in positions:
            if pos['symbol'] == SYMBOL and float(pos['contracts']) > 0:
                return pos['side'], float(pos['contracts'])
        return None, 0
    except Exception as e:
        print(f"Error revisando posición: {e}")
        return None, 0

def close_position(side):
    try:
        close_side = 'sell' if side == 'long' else 'buy'
        exchange.create_order(SYMBOL, 'market', close_side, QTY, params={'category': 'linear', 'reduceOnly': True})
        print(f"Posición {side} cerrada")
    except Exception as e:
        print(f"Error cerrando: {e}")

def open_position(side):
    try:
        order_side = 'buy' if side == 'long' else 'sell'
        exchange.create_order(SYMBOL, 'market', order_side, QTY, params={'category': 'linear'})
        print(f"Posición {side.upper()} abierta: {QTY} BTC")
    except Exception as e:
        print(f"Error abriendo: {e}")

def main():
    print("Bot Bybit Testnet iniciado...")
    
    while True:
        try:
            ema9, ema21, price = get_emas()
            if ema9 is None:
                time.sleep(60)
                continue
                
            position_side, _ = get_position()
            print(f"{datetime.now().strftime('%Y-%m-%d %H:%M:%S')} | Precio: {price:.2f} | EMA9: {ema9:.2f} | EMA21: {ema21:.2f} | Pos: {position_side}")
            
            if ema9 > ema21 and position_side!= 'long':
                if position_side == 'short':
                    close_position('short')
                    time.sleep(2)
                open_position('long')
                
            elif ema9 < ema21 and position_side!= 'short':
                if position_side == 'long':
                    close_position('long')
                    time.sleep(2)
                open_position('short')
            else:
                print("Sin cruce. Esperando...")
                
        except Exception as e:
            print(f"Error: {e}")
        
        time.sleep(3600)

if __name__ == "__main__":
    main()
