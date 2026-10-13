import yfinance as yf
import pandas as pd
import requests
import time
from datetime import datetime, time as dtime
import pytz

# ==================== 設定區 ====================
TELEGRAM_TOKEN = "這裡貼上你的完整Bot Token"     # ← 請改這裡
CHAT_ID = "6983904485"

SYMBOLS = [
    "WMT", "HRL", "ABT", "UNP", "MCD", "AXP", "NLY", "BAC", "GD", "PGR",
    "CSX", "NEE", "PEP", "KVUE", "SO", "USB", "CL", "COST", "TJX", "UL",
    "V", "ROKU", "JPM", "KO", "GSK", "WFC", "MDLZ", "MDT", "JNJ", "PFE", "AFL"
]

MA_LENGTH = 5
ATR_LENGTH = 5
ATR_MULTIPLIER = 0.75
CHECK_INTERVAL = 300          # 開市時每5分鐘檢查一次
# ==============================================

def send_telegram(message: str):
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    payload = {
        "chat_id": CHAT_ID,
        "text": message,
        "parse_mode": "HTML"
    }
    try:
        requests.post(url, data=payload, timeout=10)
    except Exception as e:
        print(f"Telegram 發送失敗: {e}")


def is_market_open():
    """判斷現在是否在美股開市時間（美東時間 09:30-16:00）"""
    eastern = pytz.timezone("US/Eastern")
    now = datetime.now(eastern)
    
    # 週末不開市
    if now.weekday() >= 5:  # 5=週六, 6=週日
        return False
    
    market_open = dtime(9, 30)
    market_close = dtime(16, 0)
    
    current_time = now.time()
    return market_open <= current_time <= market_close


def get_signal(symbol: str):
    try:
        df = yf.download(symbol, period="3mo", interval="1d", progress=False, auto_adjust=True)
        
        if isinstance(df.columns, pd.MultiIndex):
            df.columns = df.columns.droplevel(1)
        
        df = df.dropna()
        
        if len(df) < max(MA_LENGTH, ATR_LENGTH) + 5:
            return None

        df["MA5"] = df["Close"].rolling(window=MA_LENGTH).mean()
        
        high_low = df["High"] - df["Low"]
        high_close = (df["High"] - df["Close"].shift()).abs()
        low_close = (df["Low"] - df["Close"].shift()).abs()
        true_range = pd.concat([high_low, high_close, low_close], axis=1).max(axis=1)
        df["ATR5"] = true_range.rolling(window=ATR_LENGTH).mean()
        df["ATR1"] = true_range

        latest = df.iloc[-1]
        prev = df.iloc[-2]

        close = float(latest["Close"])
        low = float(latest["Low"])
        high = float(latest["High"])
        ma5 = float(latest["MA5"])
        prev_ma5 = float(prev["MA5"])
        prev_close = float(prev["Close"])
        atr5 = float(latest["ATR5"])
        atr_today = float(latest["ATR1"])

        offset = atr5 * ATR_MULTIPLIER
        buy_level = ma5 - offset
        sell_level = ma5 + offset

        ma_rising = ma5 > prev_ma5
        ma_falling = ma5 < prev_ma5

        buy_signal = (low <= buy_level) and (buy_level < prev_close) and ma_rising
        sell_signal = (high >= sell_level) and (sell_level > prev_close) and ma_falling

        ma_dir = "升" if ma_rising else "跌" if ma_falling else "平"

        return {
            "symbol": symbol,
            "price": round(close, 2),
            "ma5": round(ma5, 2),
            "atr_today": round(atr_today, 2),
            "buy_level": round(buy_level, 2),
            "sell_level": round(sell_level, 2),
            "ma_dir": ma_dir,
            "buy": buy_signal,
            "sell": sell_signal,
            "date": latest.name.strftime("%Y-%m-%d")
        }

    except Exception as e:
        print(f"{symbol} 錯誤: {e}")
        return None


def main():
    print("監控機器人已啟動（只在美股開市時運作）...")
    send_telegram("🚀 <b>股票訊號監控已啟動</b>\n只在美股開市時間（美東09:30-16:00）檢查與通知")

    sent_signals = set()

    while True:
        if not is_market_open():
            print(f"[{datetime.now().strftime('%H:%M:%S')}] 目前非開市時間，等待中...")
            time.sleep(60)  # 非開市時每1分鐘檢查一次時間即可
            continue

        print(f"\n[{datetime.now().strftime('%H:%M:%S')}] 開市中，開始檢查訊號...")

        for symbol in SYMBOLS:
            data = get_signal(symbol)
            if data is None:
                continue

            buy_key = f"{symbol}_BUY_{data['date']}"
            sell_key = f"{symbol}_SELL_{data['date']}"

            if data["buy"] and buy_key not in sent_signals:
                msg = (
                    f"🟢 <b>BUY SIGNAL（升）</b>\n"
                    f"股票：<b>{data['symbol']}</b>\n"
                    f"現價：{data['price']}\n"
                    f"買入水位：{data['buy_level']}\n"
                    f"MA5：{data['ma5']}（{data['ma_dir']}）\n"
                    f"ATR：{data['atr_today']}\n"
                    f"日期：{data['date']}"
                )
                send_telegram(msg)
                sent_signals.add(buy_key)
                print(f"✅ 已發送 BUY → {symbol}")

            if data["sell"] and sell_key not in sent_signals:
                msg = (
                    f"🔴 <b>SELL SIGNAL（跌）</b>\n"
                    f"股票：<b>{data['symbol']}</b>\n"
                    f"現價：{data['price']}\n"
                    f"賣出水位：{data['sell_level']}\n"
                    f"MA5：{data['ma5']}（{data['ma_dir']}）\n"
                    f"ATR：{data['atr_today']}\n"
                    f"日期：{data['date']}"
                )
                send_telegram(msg)
                sent_signals.add(sell_key)
                print(f"✅ 已發送 SELL → {symbol}")

        print(f"等待 {CHECK_INTERVAL} 秒後再次檢查...")
        time.sleep(CHECK_INTERVAL)


if __name__ == "__main__":
    main()