import ccxt
import time
import os
from datetime import datetime

SYMBOL = 'BTCUSDT'
TIMEFRAME = '4h'
QTY = 0.001
LEVERAGE = 1

api_key = os.getenv('BYBIT_API_KEY')
api_secret = os.getenv('BYBIT_API_SECRET')

exchange = ccxt.bybit({
    'apiKey': api_key,
    'secret': api_secret,
    'enableRateLimit': True,
    'options': {'defaultType': 'linear'},
})

exchange.set_sandbox_mode(True)

def set_leverage():
    try:
        exchange.set_leverage(LEVERAGE, SYMBOL)
        print(f"Apalancamiento puesto en {LEVERAGE}x")
    except Exception as e:
        print(f"Error leverage: {e}")

def get_ema():
    ohlcv = exchange.fetch_ohlcv(SYMBOL, TIMEFRAME, limit=50)
    closes = [x[4] for x in ohlcv]
    ema9 = sum(closes[-9:]) / 9
    ema21 = sum(closes[-21:]) / 21
    return ema9, ema21, closes[-1]

def get_position():
    positions = exchange.fetch_positions([SYMBOL])
    for pos in positions:
        if float(pos['contracts']) > 0:
            return pos['side'], float(pos['contracts'])
    return None, 0

def close_position(side):
    exchange.create_order(SYMBOL, 'market', 'sell' if side == 'long' else 'buy', QTY, None, {'reduceOnly': True})
    print(f"Posición {side} cerrada")

def open_position(side):
    exchange.create_order(SYMBOL, 'market', 'buy' if side == 'long' else 'sell', QTY)
    print(f"Abriendo {side} de {QTY} BTC")

def run():
    set_leverage()
    while True:
        try:
            ema9, ema21, price = get_ema()
            side, size = get_position()
            print(f"{datetime.now()} | Precio: {price:.2f} | EMA9: {ema9:.2f} | EMA21: {ema21:.2f} | Pos: {side}")

            if ema9 > ema21 and side!= 'long':
                if side == 'short': close_position('short')
                open_position('long')
            elif ema9 < ema21 and side!= 'short':
                if side == 'long': close_position('long')
                open_position('short')
            else:
                print("Sin cruce. Esperando...")

            time.sleep(3600)
        except Exception as e:
            print(f"Error: {e}")
            time.sleep(60)

if __name__ == "__main__":
    print("Bot Bybit Testnet iniciado...")
    run()
