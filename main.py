import ccxt
import time
import os
from datetime import datetime

API_KEY = os.getenv('BYBIT_API_KEY')
API_SECRET = os.getenv('BYBIT_API_SECRET')
SYMBOL = 'ETH/USDT:USDT'
TIMEFRAME = '4h'
QTY = 0.002
LEVERAGE = 5
STOP_LOSS_PCT = 0.03

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
        print(f"Apalancamiento {LEVERAGE}x | Margen Isolada configurado")
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
        for pos in positions:
            if pos['symbol'] == SYMBOL and float(pos['contracts']) > 0:
                return pos['side'], float(pos['contracts'])
        return None, 0
    except Exception as e:
        print(f"Error posición: {e}")
        return None, 0

def close_position(side):
    try:
        exchange.create_order(SYMBOL, 'market', 'sell' if side == 'long' else 'buy', QTY, params={'reduceOnly': True})
        print(f"Posición {side} ETH cerrada")
    except Exception as e:
        print(f"Error cerrando: {e}")

def open_position(side, current_price):
    try:
        exchange.create_order(SYMBOL, 'market', 'buy' if side == 'long' else 'sell', QTY)
        if side == 'long':
            sl_price = round(current_price * (1 - STOP_LOSS_PCT), 2)
            exchange.create_order(SYMBOL, 'market', 'sell', QTY, params={'stopLoss': sl_price, 'reduceOnly': True})
        else:
            sl_price = round(current_price * (1 + STOP_LOSS_PCT), 2)
            exchange.create_order(SYMBOL, 'market', 'buy', QTY, params={'stopLoss': sl_price, 'reduceOnly': True})
        print(f"Posición {side.upper()} ETH abierta: {QTY} | Stop Loss: {sl_price}")
    except Exception as e:
        print(f"Error abriendo: {e}")

def main():
    set_leverage()
    print("Bot Bybit ETH FUTUROS REAL BLINDADO iniciado...")
    while True:
        try:
            ema9, ema21, price = get_emas()
            if ema9 is None:
                time.sleep(60)
                continue
            position_side, _ = get_position()
            print(f"{datetime.now().strftime('%Y-%m-%d %H:%M:%S')} | ETH: {price:.2f} | EMA9: {ema9:.2f} | EMA21: {ema21:.2f} | Pos: {position_side}")
            
            if ema9 > ema21 and position_side!= 'long':
                if position_side == 'short':
                    close_position('short')
                    time.sleep(2)
                open_position('long', price)
            elif ema9 < ema21 and position_side!= 'short':
                if position_side == 'long':
                    close_position('long')
                    time.sleep(2)
                open_position('short', price)
            else:
                print("Sin cruce ETH. Esperando...")
        except Exception as e:
