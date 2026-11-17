"""Legacy public market helper, restricted to Binance USD-M Futures."""
import ccxt
from datetime import datetime

exchange = ccxt.binanceusdm({
    "enableRateLimit": True,
    "options": {"defaultType": "future"},
})


def get_market():
    ticker = exchange.fetch_ticker("BTC/USDT:USDT")
    return {
        "market": "FUTURES",
        "symbol": "BTC/USDT",
        "price": ticker["last"],
        "time": str(datetime.now()),
    }


if __name__ == "__main__":
    print(get_market())
