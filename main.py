import ccxt
import time
import os
import requests
from datetime import datetime

API_KEY = os.getenv('BYBIT_API_KEY')
API_SECRET = os.getenv('BYBIT_API_SECRET')
TELEGRAM_TOKEN = os.getenv('TELEGRAM_TOKEN') # Opcional
TELEGRAM_CHAT_ID = os.getenv('TELEGRAM_CHAT_ID') # Opcional

SYMBOL = 'ADA/USDT:USDT'
TIMEFRAME = '4h'
QTY = 10 # 10 ADA = ~$3.5. Bybit mínimo para ADA
LEVERAGE = 2 # 5x te liquida con $10
STOP_LOSS_PCT = 0.02 # 2% = -4% con 2x
TAKE_PROFIT_PCT = 0.04 # 4% = +8% con 2x. Ratio 2:1
ADX_MIN = 25 # Filtro: solo opera si ADX > 25
EMA_TREND = 200 # Filtro: solo long si price > EMA200
MAX_LOSS_STREAK = 3 # Anti-ruina: 3 SL seguidos = pausa 48h

exchange = ccxt.bybit({
    'apiKey': API_KEY,
    'secret': API_SECRET,
    'enableRateLimit': True,
    'options': {'defaultType': 'linear', 'adjustForTimeDifference': True},
})

loss_streak = 0

def telegram(msg):
    if TELEGRAM_TOKEN and TELEGRAM_CHAT_ID:
        try:
            url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
            requests.post(url, data={"chat_id": TELEGRAM_CHAT_ID, "text": msg}, timeout=5)
        except: pass
    print(msg)

def set_leverage():
    try:
        exchange.set_leverage(LEVERAGE, SYMBOL, params={'category': 'linear'})
        exchange.set_margin_mode('isolated', SYMBOL, params={'category': 'linear'})
        telegram(f"✅ Bot iniciado | ADA {LEVERAGE}x | SL: -{STOP_LOSS_PCT*LEVERAGE*100:.0f}% | TP: +{TAKE_PROFIT_PCT*LEVERAGE*100:.0f}%")
    except Exception as e:
        if '110043' not in str(e) and '110013' not in str(e):
            telegram(f"⚠️ Error config: {e}")

def get_indicadores():
    try:
        ohlcv = exchange.fetch_ohlcv(SYMBOL, TIMEFRAME, limit=250)
        closes = [x[4] for x in ohlcv]
        highs = [x[2] for x in ohlcv]
        lows = [x[3] for x in ohlcv]

        def calc_ema(data, period):
            ema = data[0]
            k = 2 / (period + 1)
            for price in data[1:]:
                ema = price * k + ema * (1 - k)
            return ema

        ema9 = calc_ema(closes, 9)
        ema21 = calc_ema(closes, 21)
        ema200 = calc_ema(closes, 200)

        # ADX
        tr = [max(highs[i] - lows[i], abs(highs[i] - closes[i-1]), abs(lows[i] - closes[i-1])) for i in range(1, len(highs))]
        plus_dm = [highs[i] - highs[i-1] if highs[i] - highs[i-1] > lows[i-1] - lows[i] and highs[i] - highs[i-1] > 0 else 0 for i in range(1, len(highs))]
        minus_dm = [lows[i-1] - lows[i] if lows[i-1] - lows[i] > highs[i] - highs[i-1] and lows[i-1] - lows[i] > 0 else 0 for i in range(1, len(lows))]
        atr14 = sum(tr[-14:]) / 14
        plus_di = 100 * (sum(plus_dm[-14:]) / 14) / atr14 if atr14!= 0 else 0
        minus_di = 100 * (sum(minus_dm[-14:]) / 14) / atr14 if atr14!= 0 else 0
        dx = 100 * abs(plus_di - minus_di) / (plus_di + minus_di) if (plus_di + minus_di)!= 0 else 0
        adx = dx

        return round(ema9,4), round(ema21,4), round(ema200,4), round(adx,2), closes[-1]
    except Exception as e:
        telegram(f"⚠️ Error indicadores: {e}")
        return None, None, None, None, None

def get_position():
    try:
        positions = exchange.fetch_positions([SYMBOL], params={'category': 'linear'})
        for pos in positions:
            if pos['symbol'] == SYMBOL and float(pos['contracts']) > 0:
                return pos['side'], float(pos['contracts'])
        return None, 0
    except: return None, 0

def cancelar_ordenes():
    try: exchange.cancel_all_orders(SYMBOL, params={'category': 'linear'})
    except: pass

def open_position(side, current_price):
    try:
        cancelar_ordenes()
        exchange.create_order(SYMBOL, 'market', 'buy' if side == 'long' else 'sell', QTY, params={'category': 'linear'})
        time.sleep(2)

        if side == 'long':
            sl_price = round(current_price * (1 - STOP_LOSS_PCT), 4)
            tp_price = round(current_price * (1 + TAKE_PROFIT_PCT), 4)
            sl_side, trigger_direction = 'sell', 2
        else:
            sl_price = round(current_price * (1 + STOP_LOSS_PCT), 4)
            tp_price = round(current_price * (1 - TAKE_PROFIT_PCT), 4)
            sl_side, trigger_direction = 'buy', 1

        # Stop Loss - SÍ SE PONE AUTOMÁTICO
        exchange.create_order(SYMBOL, 'stop_market', sl_side, QTY, params={
            'triggerPrice': sl_price, 'triggerDirection': trigger_direction,
            'reduceOnly': True, 'category': 'linear', 'triggerBy': 'LastPrice'
        })
        # Take Profit - TAMBIÉN SE PONE AUTOMÁTICO
        exchange.create_order(SYMBOL, 'limit', sl_side, QTY, params={
            'price': tp_price, 'reduceOnly': True, 'category': 'linear'
        })

        telegram(f"📈 {side.upper()} ADA abierto\nEntrada: ${current_price:.4f}\nSL: ${sl_price:.4f} | TP: ${tp_price:.4f}")
    except Exception as e:
        telegram(f"⚠️ Error abriendo: {e}")

def main():
    global loss_streak
    set_leverage()
    while True:
        try:
            if loss_streak >= MAX_LOSS_STREAK:
                telegram(f"🛑 Pausa 48h por {MAX_LOSS_STREAK} SL seguidos")
                time.sleep(172800)
                loss_streak = 0
                continue

            ema9, ema21, ema200, adx, price = get_indicadores()
            if ema9 is None: time.sleep(60); continue

            position_side, _ = get_position()

            # LOG COMPLETO PARA QUE VEAS POR QUÉ NO ENTRA
            log_msg = f"{datetime.now().strftime('%H:%M')} | ADA: {price:.4f} | EMA9:{ema9:.4f} | EMA21:{ema21:.4f} | EMA200:{ema200:.4f} | ADX:{adx} | Pos:{position_side}"
            print(log_msg)

            cond_long = ema9 > ema21 and price > ema200 and adx > ADX_MIN
            cond_short = ema9 < ema21 and price < ema200 and adx > ADX_MIN

            # TE DICE EXACTO POR QUÉ NO ENTRA
            if position_side is None:
                if adx <= ADX_MIN:
                    print("❌ Sin señal: ADX <= 25. Mercado lateral, no opera")
                elif ema9 > ema21 and price <= ema200:
                    print("❌ Sin señal: Precio debajo de EMA200. Tendencia macro bajista")
                elif ema9 < ema21 and price >= ema200:
                    print("❌ Sin señal: Precio arriba de EMA200 pero EMA9 < EMA21")
                elif ema9 <= ema21 and ema9 >= ema21:
                    print("❌ Sin señal: EMAs pegadas. Esperando cruce")
                else:
                    print("❌ Sin señal: No cumple condiciones")

            if cond_long and position_side!= 'long':
                if position_side == 'short':
                    exchange.create_order(SYMBOL, 'market', 'buy', QTY, params={'reduceOnly': True, 'category': 'linear'})
                    loss_streak += 1
                    time.sleep(2)
                open_position('long', price)

            elif cond_short and position_side!= 'short':
                if position_side == 'long':
                    exchange.create_order(SYMBOL, 'market', 'sell', QTY, params={'reduceOnly': True, 'category': 'linear'})
                    loss_streak += 1
                    time.sleep(2)
                open_position('short', price)

        except Exception as e:
            telegram(f"⚠️ Error loop: {e}")
        time.sleep(3600) # Revisa cada 1h

if __name__ == "__main__":
    main()
