import ccxt
import time
import os
from datetime import datetime

# ========== CONFIGURACIÓN - EDITA AQUÍ ==========
API_KEY = os.getenv('BYBIT_API_KEY')
API_SECRET = os.getenv('BYBIT_API_SECRET')
SYMBOL = 'BTC/USDT:USDT' # USDT Perpétuo Bybit
TIMEFRAME = '4h' # Velas de 4 horas para EMA
QTY = 0.0001 # 0.0001 BTC = ~$6.4. Con 10 USDT usa 0.0001
LEVERAGE = 5 # 5x = seguro. Máximo 10x si eres loco
STOP_LOSS_PCT = 0.03 # 3% de stop loss
MARGIN_MODE = 'isolated' # 'isolated' = solo pierdes esa orden si liquida
SLEEP_SECONDS = 3600 # Revisa cada 1 hora = 3600s
# ================================================

exchange = ccxt.bybit({
    'apiKey': API_KEY,
    'secret': API_SECRET,
    'enableRateLimit': True,
    'options': {
        'defaultType': 'linear', # USDT Perpétuo
        'adjustForTimeDifference': True,
    },
})

def setup_symbol():
    """Configura leverage y margen aislada. Se ejecuta 1 vez."""
    try:
        exchange.set_margin_mode(MARGIN_MODE, SYMBOL)
        print(f"Modo de margen: {MARGIN_MODE.upper()}")
    except Exception as e:
        if '110043' in str(e): # Ya está en isolated
            print("Modo de margen: ISOLATED ya configurado")
        else:
            print(f"Error margen: {e}")
    
    try:
        exchange.set_leverage(LEVERAGE, SYMBOL)
        print(f"Apalancamiento: {LEVERAGE}x configurado")
    except Exception as e:
        print(f"Error leverage: {e}")

def get_emas():
    """Calcula EMA9 y EMA21 del timeframe elegido"""
    try:
        ohlcv = exchange.fetch_ohlcv(SYMBOL, TIMEFRAME, limit=100)
        closes = [x[4] for x in ohlcv]
        
        # EMA 9
        ema9 = closes[0]
        k9 = 2 / (9 + 1)
        for price in closes[1:]: 
            ema9 = price * k9 + ema9 * (1 - k9)
        
        # EMA 21
        ema21 = closes[0]
        k21 = 2 / (21 + 1)
        for price in closes[1:]: 
            ema21 = price * k21 + ema21 * (1 - k21)
            
        return round(ema9, 2), round(ema21, 2), closes[-1]
    except Exception as e:
        print(f"[{datetime.now()}] Error EMAs: {e}")
        return None, None, None

def get_position():
    """Devuelve: side, qty, entry_price"""
    try:
        positions = exchange.fetch_positions([SYMBOL])
        for pos in positions:
            if pos['symbol'] == SYMBOL and float(pos['contracts']) > 0:
                return pos['side'], float(pos['contracts']), float(pos['entryPrice'])
        return None, 0, 0
    except Exception as e:
        print(f"[{datetime.now()}] Error posición: {e}")
        return None, 0, 0

def close_position(side, qty):
    """Cierra posición completa"""
    try:
        order = exchange.create_order(
            SYMBOL, 
            'market', 
            'sell' if side == 'long' else 'buy', 
            qty, 
            params={'reduceOnly': True}
        )
        print(f"[{datetime.now()}] ✅ Posición {side.upper()} CERRADA | Qty: {qty}")
        return True
    except Exception as e:
        print(f"[{datetime.now()}] ❌ Error cerrando: {e}")
        return False

def open_position(side, current_price):
    """Abre posición + Stop Loss automático"""
    try:
        # 1. Abrir orden market
        order = exchange.create_order(
            SYMBOL, 
            'market', 
            'buy' if side == 'long' else 'sell', 
            QTY
        )
        print(f"[{datetime.now()}] 🚀 Posición {side.upper()} ABIERTA | Qty: {QTY} | Precio: {current_price:.2f}")
        
        # 2. Poner Stop Loss
        time.sleep(1) # Esperar que Bybit registre la posición
        if side == 'long':
            sl_price = round(current_price * (1 - STOP_LOSS_PCT), 2)
            exchange.create_order(
                SYMBOL, 
                'market', 
                'sell', 
                QTY, 
                params={'stopLoss': sl_price, 'reduceOnly': True, 'triggerBy': 'LastPrice'}
            )
        else: # short
            sl_price = round(current_price * (1 + STOP_LOSS_PCT), 2)
            exchange.create_order(
                SYMBOL, 
                'market', 
                'buy', 
                QTY, 
                params={'stopLoss': sl_price, 'reduceOnly': True, 'triggerBy': 'LastPrice'}
            )
        
        print(f"[{datetime.now()}] 🛡️ Stop Loss colocado: {sl_price:.2f} | Riesgo máx: {QTY * current_price * STOP_LOSS_PCT:.2f} USDT")
        return True
    except Exception as e:
        print(f"[{datetime.now()}] ❌ Error abriendo: {e}")
        return False

def main():
    print("="*60)
    print(" BOT BYBIT FUTUROS REAL BLINDADO v2.0")
    print(f" Símbolo: {SYMBOL} | Timeframe: {TIMEFRAME}")
    print(f" QTY: {QTY} BTC | Leverage: {LEVERAGE}x | SL: {STOP_LOSS_PCT*100}%")
    print("="*60)
    
    setup_symbol()
    print("\nIniciando loop 24/7...\n")
    
    while True:
        try:
            ema9, ema21, price = get_emas()
            if ema9 is None: 
                time.sleep(60)
                continue
                
            position_side, position_qty, entry_price = get_position()
            
            log = f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] "
            log += f"Precio: {price:.2f} | EMA9: {ema9} | EMA21: {ema21} | "
