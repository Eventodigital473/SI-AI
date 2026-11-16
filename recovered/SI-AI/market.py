








import ccxt
from datetime import datetime

exchange = ccxt.binance({
    "enableRateLimit": True
})

def get_market():
    ticker = exchange.fetch_ticker("BTC/USDT")
    return {
        "symbol": "BTC/USDT",
        "price": ticker["last"],
        "time": str(datetime.now())
    }

print(get_market())









