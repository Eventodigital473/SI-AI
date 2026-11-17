
import ccxt
import time
from datetime import datetime

# =====================================
# SI AI - SMART MONEY CONCEPTS ENGINE
# =====================================

exchange = ccxt.binance({
    "enableRateLimit": True,
    "timeout": 20000
})

SYMBOLS = [
    "BTC/USDT",
    "ETH/USDT"
]

TIMEFRAMES = [
    "15m",
    "1h",
    "4h",
    "1d"
]

CANDLE_LIMIT = 200


# =====================================
# MARKET DATA
# =====================================

def get_candles(symbol, timeframe):

    candles = exchange.fetch_ohlcv(
        symbol,
        timeframe=timeframe,
        limit=CANDLE_LIMIT
    )

    if not candles or len(candles) < 51:
        raise ValueError("Not enough market candles")

    # Exclude the latest potentially incomplete candle
    closed_candles = candles[:-1]

    if len(closed_candles) < 50:
        raise ValueError("Not enough closed candles")

    return closed_candles


# =====================================
# BASIC CALCULATIONS
# =====================================

def calculate_average(values):

    if not values:
        return 0

    return sum(values) / len(values)


def calculate_atr(candles, period=14):

    true_ranges = []

    for i in range(1, len(candles)):

        high = candles[i][2]
        low = candles[i][3]
        previous_close = candles[i - 1][4]

        tr = max(
            high - low,
            abs(high - previous_close),
            abs(low - previous_close)
        )

        true_ranges.append(tr)

    if len(true_ranges) < period:
        return 0

    return calculate_average(true_ranges[-period:])


# =====================================
# SWING HIGH AND LOW DETECTION
# =====================================

def detect_swings(candles, lookback=3, include_indices=False):

    swing_highs = []
    swing_lows = []

    if lookback < 1 or len(candles) < (lookback * 2 + 1):
        return [], []

    for i in range(lookback, len(candles) - lookback):

        current_high = candles[i][2]
        current_low = candles[i][3]

        left_highs = [
            candles[j][2]
            for j in range(i - lookback, i)
        ]

        right_highs = [
            candles[j][2]
            for j in range(i + 1, i + lookback + 1)
        ]

        left_lows = [
            candles[j][3]
            for j in range(i - lookback, i)
        ]

        right_lows = [
            candles[j][3]
            for j in range(i + 1, i + lookback + 1)
        ]

        if all(current_high > x for x in left_highs + right_highs):
            swing_highs.append((i, current_high))

        if all(current_low < x for x in left_lows + right_lows):
            swing_lows.append((i, current_low))

    if include_indices:
        return swing_highs, swing_lows

    return (
        [price for index, price in swing_highs],
        [price for index, price in swing_lows]
    )


# =====================================
# PART 1 COMPLETE
# =====================================



# =====================================
# MARKET STRUCTURE ANALYSIS
# =====================================

def detect_market_structure(candles):

    swing_highs, swing_lows = detect_swings(candles)

    if len(swing_highs) < 2 or len(swing_lows) < 2:
        return "Unknown"

    higher_high = swing_highs[-1] > swing_highs[-2]
    higher_low = swing_lows[-1] > swing_lows[-2]

    lower_high = swing_highs[-1] < swing_highs[-2]
    lower_low = swing_lows[-1] < swing_lows[-2]

    if higher_high and higher_low:
        return "Bullish Structure"

    if lower_high and lower_low:
        return "Bearish Structure"

    return "Sideways Structure"


# =====================================
# BREAK OF STRUCTURE (BOS)
# =====================================

def detect_bos(candles):

    if len(candles) < 2:
        return "No BOS"

    swing_highs, swing_lows = detect_swings(
        candles, include_indices=True
    )

    previous_close = candles[-2][4]
    current_close = candles[-1][4]

    if swing_highs:
        latest_swing_high = swing_highs[-1][1]

        if (
            previous_close <= latest_swing_high
            and current_close > latest_swing_high
        ):
            return "Bullish BOS"

    if swing_lows:
        latest_swing_low = swing_lows[-1][1]

        if (
            previous_close >= latest_swing_low
            and current_close < latest_swing_low
        ):
            return "Bearish BOS"

    return "No BOS"


# =====================================
# CHANGE OF CHARACTER (CHOCH)
# =====================================

def detect_choch(candles):

    structure = detect_market_structure(candles)
    bos = detect_bos(candles)

    if structure == "Bearish Structure" and bos == "Bullish BOS":
        return "Bullish CHOCH"

    if structure == "Bullish Structure" and bos == "Bearish BOS":
        return "Bearish CHOCH"

    return "No CHOCH"


# =====================================
# LIQUIDITY ANALYSIS
# =====================================

def detect_liquidity(candles):

    highs = [c[2] for c in candles]
    lows = [c[3] for c in candles]

    previous_high = max(highs[-21:-1])
    previous_low = min(lows[-21:-1])

    price = candles[-1][4]

    if price > previous_high:
        high_liquidity = "High Liquidity Swept"
    else:
        high_liquidity = "High Liquidity Available"

    if price < previous_low:
        low_liquidity = "Low Liquidity Swept"
    else:
        low_liquidity = "Low Liquidity Available"

    return {
        "previous_high": previous_high,
        "previous_low": previous_low,
        "high_liquidity": high_liquidity,
        "low_liquidity": low_liquidity
    }


# =====================================
# FAIR VALUE GAP (FVG)
# =====================================

def detect_fvg(candles):

    bullish_fvg = False
    bearish_fvg = False

    if len(candles) < 3:
        return {
            "bullish_fvg": False,
            "bearish_fvg": False
        }

    first = candles[-3]
    third = candles[-1]

    if third[3] > first[2]:
        bullish_fvg = True

    if third[2] < first[3]:
        bearish_fvg = True

    return {
        "bullish_fvg": bullish_fvg,
        "bearish_fvg": bearish_fvg
    }


# =====================================
# ORDER BLOCK DETECTION
# =====================================

def detect_order_block(candles):

    bullish_ob = False
    bearish_ob = False

    if len(candles) < 5:
        return {
            "bullish_ob": False,
            "bearish_ob": False
        }

    last = candles[-1]
    previous = candles[-2]

    if previous[4] < previous[1] and last[4] > previous[2]:
        bullish_ob = True

    if previous[4] > previous[1] and last[4] < previous[3]:
        bearish_ob = True

    return {
        "bullish_ob": bullish_ob,
        "bearish_ob": bearish_ob
    }


# =====================================
# VOLUME ANALYSIS
# =====================================

def analyze_volume(candles):

    volumes = [c[5] for c in candles]

    average_volume = calculate_average(volumes[-21:-1])

    current_volume = volumes[-1]

    if current_volume > average_volume * 1.5:
        signal = "Very High Volume"

    elif current_volume > average_volume:
        signal = "High Volume"

    else:
        signal = "Normal Volume"

    return {
        "current_volume": current_volume,
        "average_volume": average_volume,
        "signal": signal
    }


# =====================================
# PART 2 COMPLETE
# =====================================



# =====================================
# SI AI - COMPLETE SMC ANALYSIS
# =====================================

def analyze(symbol, timeframe):

    candles = get_candles(symbol, timeframe)

    highs = [c[2] for c in candles]
    lows = [c[3] for c in candles]
    closes = [c[4] for c in candles]

    price = closes[-1]

    structure = detect_market_structure(candles)
    bos = detect_bos(candles)
    choch = detect_choch(candles)

    liquidity = detect_liquidity(candles)
    fvg = detect_fvg(candles)
    order_block = detect_order_block(candles)

    volume = analyze_volume(candles)
    atr = calculate_atr(candles)

    previous_high = max(highs[-21:-1])
    previous_low = min(lows[-21:-1])

    # TREND ANALYSIS

    if structure == "Bullish Structure":
        trend = "Bullish"

    elif structure == "Bearish Structure":
        trend = "Bearish"

    else:
        trend = "Range"

    # SIGNAL GENERATION

    score = 0

    if structure == "Bullish Structure":
        score += 2
    elif structure == "Bearish Structure":
        score -= 2

    if bos == "Bullish BOS":
        score += 2
    elif bos == "Bearish BOS":
        score -= 2

    if choch == "Bullish CHOCH":
        score += 2
    elif choch == "Bearish CHOCH":
        score -= 2

    if fvg["bullish_fvg"]:
        score += 1
    if fvg["bearish_fvg"]:
        score -= 1

    if order_block["bullish_ob"]:
        score += 1
    if order_block["bearish_ob"]:
        score -= 1

    if score >= 3:
        signal = "BUY"
    elif score <= -3:
        signal = "SELL"
    else:
        signal = "WAIT"

    # RISK MANAGEMENT

    stop_loss = None
    take_profit = None

    if signal == "BUY":
        stop_loss = price - (atr * 1.5)
        take_profit = price + (atr * 3)

    elif signal == "SELL":
        stop_loss = price + (atr * 1.5)
        take_profit = price - (atr * 3)

    return {
        "symbol": symbol,
        "timeframe": timeframe,
        "price": price,
        "trend": trend,
        "structure": structure,
        "bos": bos,
        "choch": choch,
        "liquidity": liquidity,
        "fvg": fvg,
        "order_block": order_block,
        "volume": volume,
        "atr": atr,
        "score": score,
        "signal": signal,
        "stop_loss": stop_loss,
        "take_profit": take_profit,
        "time": str(datetime.now())
    }


# =====================================
# DISPLAY RESULTS
# =====================================

def run_analysis():

    print("\n================================")
    print("       SI AI SMC ENGINE")
    print("================================")

    for symbol in SYMBOLS:

        print("\n\nMARKET:", symbol)

        for timeframe in TIMEFRAMES:

            try:

                result = analyze(symbol, timeframe)

                print("\n------------------------------")
                print("TIMEFRAME:", timeframe)
                print("------------------------------")

                print("Price:", result["price"])
                print("Trend:", result["trend"])
                print("Structure:", result["structure"])

                print("BOS:", result["bos"])
                print("CHOCH:", result["choch"])

                print("Liquidity:", result["liquidity"])

                print("FVG:", result["fvg"])
                print("Order Block:", result["order_block"])

                print("Volume:", result["volume"]["signal"])

                print("ATR:", result["atr"])
                print("Score:", result["score"])

                print("SIGNAL:", result["signal"])

                print("Stop Loss:", result["stop_loss"])
                print("Take Profit:", result["take_profit"])

                print("Time:", result["time"])

            except Exception as error:

                print(
                    "Analysis Error:",
                    symbol,
                    timeframe,
                    error
                )

            time.sleep(1)


# =====================================
# MAIN PROGRAM
# =====================================

if __name__ == "__main__":

    try:
        run_analysis()

    except KeyboardInterrupt:
        print("\nSI AI stopped by user.")

    except Exception as error:
        print("\nSI AI Error:", error)
