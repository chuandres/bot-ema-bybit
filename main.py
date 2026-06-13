import ccxt
import time
import os
from datetime import datetime

# --- CONFIGURACIÓN ---
API_KEY = os.getenv('BYBIT_API_KEY')
API_SECRET = os.getenv('BYBIT_API_SECRET')
SYMBOL = 'BTC/USDT:USDT' # Linear Perpetual
TIMEFRAME = '4h'
QTY = 0.001 # 0.001 BTC = ~$63 con BTC en 63k
LEVERAGE = 1

# --- CONEXIÓN BYBIT TESTNET CON FIX ANTI-403 ---
exchange = ccxt.bybit({
    'apiKey': API_KEY,
    'secret': API_SECRET,
    'enableRateLimit': True,
    'options': {
        'defaultType': 'linear', # Fuerza solo futuros USDT, no toca spot
    },
})
exchange.set_sandbox_mode(True) # Activa testnet

def get_emas():
    """Calcula EMA9 y EMA21 en timeframe 4h"""
    try:
        ohlcv = exchange.fetch_ohlcv(SYMBOL, TIMEFRAME, limit=100)
        closes = [x[4] for x in ohlcv]
        
        # EMA9
        ema9 = closes[0]
        k9 = 2 / (9 + 1)
        for price in closes[1:]:
            ema9 = price * k9 + ema9 * (1 - k9)
        
        # EMA21
        ema21 = closes[0]
        k21 = 2 / (21 + 1)
        for price in closes[1:]:
            ema21 = price * k21 + ema21 * (1 - k21)
            
        return ema9, ema21, closes[-1] # ema9, ema21, precio actual
    except Exception as e:
        print(f"Error calculando EMAs: {e}")
        return None, None, None

def set_leverage():
    """Pone apalancamiento 1x en Bybit Linear"""
    try:
        exchange.set_leverage(LEVERAGE, SYMBOL)
        print(f"Apalancamiento puesto en {LEVERAGE}x")
    except Exception as e:
        # Si ya está en 1x, Bybit tira error pero no pasa nada
        if "leverage not modified" in str(e).lower():
            print(f"Apalancamiento ya estaba en {LEVERAGE}x")
        else:
            print(f"Error poniendo leverage: {e}")

def get_position():
    """Revisa si ya tienes posición abierta"""
    try:
        positions = exchange.fetch_positions([SYMBOL])
        for pos in positions:
            if pos['symbol'] == SYMBOL and float(pos['contracts']) > 0:
                return pos['side'], float(pos['contracts'])
        return None, 0
    except Exception as e:
        print(f"Error revisando posición: {e}")
        return None, 0

def close_position(side):
    """Cierra posición abierta"""
    try:
        close_side = 'sell' if side == 'long' else 'buy'
        exchange.create_order(SYMBOL, 'market', close_side, QTY, params={'reduceOnly': True})
        print(f"Posición {side} cerrada")
    except Exception as e:
        print(f"Error cerrando posición: {e}")

def open_position(side):
    """Abre Long o Short"""
    try:
        order_side = 'buy' if side == 'long' else 'sell'
        exchange.create_order(SYMBOL, 'market', order_side, QTY)
        print(f"Posición {side.upper()} abierta: {QTY} BTC")
    except Exception as e:
        print(f"Error abriendo posición: {e}")

def main():
    print("Bot Bybit Testnet iniciado...")
    set_leverage()
    
    while True:
        try:
            ema9, ema21, price = get_emas()
            
            if ema9 is None:
                time.sleep(60)
                continue
                
            position_side, _ = get_position()
            
            print(f"{datetime.now().strftime('%Y-%m-%d %H:%M:%S')} | Precio: {price:.2f} | EMA9: {ema9:.2f} | EMA21: {ema21:.2f}")
            
            # SEÑAL LONG: EMA9 cruza arriba EMA21
            if ema9 > ema21 and position_side!= 'long':
                if position_side == 'short':
                    close_position('short')
                    time.sleep(2)
                open_position('long')
                
            # SEÑAL SHORT: EMA9 cruza abajo EMA21 
            elif ema9 < ema21 and position_side!= 'short':
                if position_side == 'long':
                    close_position('long')
                    time.sleep(2)
                open_position('short')
            else:
                print("Sin cruce. Esperando...")
                
        except Exception as e:
            print(f"Error en loop principal: {e}")
        
        # Espera 1 hora antes de revisar otra vez
        time.sleep(3600)

if __name__ == "__main__":
    main()
