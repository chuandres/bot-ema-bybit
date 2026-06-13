import ccxt
import time
import os
from datetime import datetime

API_KEY = os.getenv('BYBIT_API_KEY')
API_SECRET = os.getenv('BYBIT_API_SECRET')
SYMBOL = 'BTC/USDT:USDT'
TIMEFRAME = '4h'
QTY = 0.0001  # Con 10 USDT usa 0.0001 = $6.4 por trade
LEVERAGE = 5  # 5x = seguro. No subas de 10x
STOP_LOSS_PCT = 0.03  # 3% Stop Loss

exchange = ccxt.bybit({
    'apiKey': API_KEY,
    'secret': API_SECRET,
    'enableRateLimit': True,
    'options': {'defaultType': 'linear'},
})

def set_leverage():
    try:
        exchange.set_leverage(LEVERAGE, SYMBOL)
        exchange.set_margin_mode('isolated', SYMBOL) # Modo isolado = no te liquida toda la cuenta
        print(f"Apalancamiento {LEVERAGE}x | Margen Isolada configurado")
    except Exception as e:
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
        return ema9, ema21, closes[-1]
    except Exception as e:
        print(f"Error EMAs: {e}")
        return None, None, None

def get_position():
    try:
        positions = exchange.fetch_positions([SYMBOL])
        for pos in positions:
            if pos['symbol'] == SYMBOL and float(pos['contracts']) > 0:
                return pos['side'], float(pos['contracts']), float(pos['entryPrice'])
        return None, 0, 0
    except Exception as e:
        print(f"Error posición: {e}")
        return None, 0, 0

def close_position(side):
    try:
        exchange.create_order(SYMBOL, 'market', 'sell' if side == 'long' else 'buy', QTY, params={'reduceOnly': True})
        print(f"Posición {side} cerrada")
    except Exception as e:
        print(f"Error cerrando: {e}")

def open_position(side, current_price):
    try:
        # 1. Abre la orden
        exchange.create_order(SYMBOL, 'market', 'buy' if side == 'long' else 'sell', QTY)
        
        # 2. Calcula Stop Loss
        if side == 'long':
            sl_price = current_price * (1 - STOP_LOSS_PCT)
            exchange.create_order(SYMBOL, 'market', 'sell', QTY, params={'stopLoss': sl_price, 'reduceOnly': True, 'triggerBy': 'LastPrice'})
        else:
            sl_price = current_price * (1 + STOP_LOSS_PCT)
            exchange.create_order(SYMBOL, 'market', 'buy', QTY, params={'stopLoss': sl_price, 'reduceOnly': True, 'triggerBy': 'LastPrice'})
        
        print(f"Posición {side.upper()} abierta: {QTY} BTC | SL: {sl_price:.2f}")
    except Exception as e:
        print(f"Error abriendo: {e}")

def main():
    set_leverage()
    print("Bot Bybit FUTUROS REAL BLINDADO iniciado...")
    while True:
        try:
            ema9, ema21, price = get_emas()
            if ema9 is None: 
                time.sleep(60)
                continue
            
            position_side, _, entry_price = get_position()
            log = f"{datetime.now().strftime('%Y-%m-%d %H:%M:%S')} | Precio: {price:.2f} | EMA9: {ema9:.2f} | EMA21: {ema21:.2f} | Pos: {position_side}"
            print(log)
            
            if ema9 > ema21 and position_side != 'long':
                if position_side == 'short': 
                    close_position('short')
                    time.sleep(2)
                open_position('long', price)
            elif ema9 < ema21 and position_side != 'short':
                if position_side == 'long': 
                    close_position('long')
                    time.sleep(2)
                open_position('short', price)
            else: 
                print("Sin cruce. Esperando...")
                
        except Exception as e: 
            print(f"Error general: {e}")
        time.sleep(3600)

if __name__ == "__main__":
    main()
