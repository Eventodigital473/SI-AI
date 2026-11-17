"""SI AI - Futures-first market intelligence engine.

Public market-data analysis only. This module NEVER places orders.
Requires: ccxt (pip install ccxt)
"""
from __future__ import annotations

import math
import time
from datetime import datetime, timezone
from typing import Dict, List, Optional, Tuple

import ccxt

# ----------------------------- CONFIGURATION -----------------------------
SYMBOLS = ["BTC/USDT", "ETH/USDT"]
TIMEFRAMES = ["15m", "1h", "4h", "1d"]
CANDLE_LIMIT = 250
MIN_CANDLES = 80
REQUEST_DELAY_SECONDS = 0.35

# Futures is intentionally analysed first. Both exchanges use public endpoints.
MARKETS = ["FUTURES", "SPOT"]
FUTURES_EXCHANGE_ID = "binanceusdm"
SPOT_EXCHANGE_ID = "binance"

# Analysis/risk assumptions only; no account balance is queried and no orders sent.
PAPER_EQUITY_USDT = 1000.0
RISK_PER_TRADE_PERCENT = 0.5
MAX_NOTIONAL_EQUITY_MULTIPLE = 2.0
MIN_REWARD_RISK = 2.0

# Illustrative paper assumptions, not account-specific exchange rates.
PAPER_TAKER_FEE_RATES = {
    "FUTURES": 0.0005,
    "SPOT": 0.0010,
}
PAPER_SLIPPAGE_RATE = 0.0002

TIMEFRAME_WEIGHTS = {"15m": 1.0, "1h": 1.5, "4h": 2.0, "1d": 2.0}


def make_exchange(market: str):
    exchange_class = getattr(ccxt, FUTURES_EXCHANGE_ID if market == "FUTURES" else SPOT_EXCHANGE_ID)
    return exchange_class({
        "enableRateLimit": True,
        "timeout": 20000,
        "options": {"defaultType": "future" if market == "FUTURES" else "spot"},
    })


EXCHANGES = {market: make_exchange(market) for market in MARKETS}


# ----------------------------- DATA SAFETY -------------------------------
def validate_candles(candles: list) -> List[list]:
    if not isinstance(candles, list) or len(candles) < MIN_CANDLES:
        raise ValueError(f"Need at least {MIN_CANDLES} candles; received {len(candles) if candles else 0}")
    cleaned = []
    previous_ts = -1
    for row in candles:
        if not isinstance(row, (list, tuple)) or len(row) < 6:
            continue
        ts, op, high, low, close, volume = row[:6]
        values = (ts, op, high, low, close, volume)
        if not all(isinstance(v, (int, float)) and math.isfinite(float(v)) for v in values):
            continue
        if min(op, high, low, close) <= 0 or volume < 0 or high < low:
            continue
        if ts <= previous_ts:
            continue
        if high < max(op, close) or low > min(op, close):
            continue
        cleaned.append([int(ts), float(op), float(high), float(low), float(close), float(volume)])
        previous_ts = int(ts)
    if len(cleaned) < MIN_CANDLES:
        raise ValueError("Insufficient valid OHLCV candles after validation")
    # Drop the newest candle because it may still be forming.
    closed = cleaned[:-1]
    if len(closed) < MIN_CANDLES:
        raise ValueError("Insufficient closed candles")
    return closed


def get_candles(market: str, symbol: str, timeframe: str) -> List[list]:
    exchange = EXCHANGES[market]
    exchange.load_markets()

    exchange_symbol = symbol

    if market == "FUTURES" and exchange_symbol not in exchange.markets:
        base, quote = symbol.split("/", 1)
        candidate = f"{base}/{quote}:{quote}"

        if candidate in exchange.markets:
            exchange_symbol = candidate

    if exchange_symbol not in exchange.markets:
        raise ValueError(
            f"Symbol {symbol} is unavailable on {market} exchange"
        )

    raw = exchange.fetch_ohlcv(
        exchange_symbol,
        timeframe=timeframe,
        limit=CANDLE_LIMIT
    )
    return validate_candles(raw)


# ----------------------------- INDICATORS ---------------------------------
def average(values: List[float]) -> float:
    return sum(values) / len(values) if values else 0.0


def ema(values: List[float], period: int) -> float:
    if not values:
        return 0.0
    if len(values) < period:
        return average(values)
    alpha = 2.0 / (period + 1.0)
    result = average(values[:period])
    for value in values[period:]:
        result = alpha * value + (1.0 - alpha) * result
    return result


def calculate_atr(candles: List[list], period: int = 14) -> float:
    if len(candles) < period + 1:
        return 0.0
    true_ranges = []
    for i in range(1, len(candles)):
        high, low, prev_close = candles[i][2], candles[i][3], candles[i - 1][4]
        true_ranges.append(max(high - low, abs(high - prev_close), abs(low - prev_close)))
    if len(true_ranges) < period:
        return 0.0
    # Wilder smoothing, rather than a simple average of only the last few bars.
    value = average(true_ranges[:period])
    for tr in true_ranges[period:]:
        value = ((period - 1) * value + tr) / period
    return value


def analyze_volume(candles: List[list], period: int = 20) -> Dict:
    vols = [c[5] for c in candles]
    baseline = average(vols[-period - 1:-1])
    current = vols[-1]
    ratio = current / baseline if baseline > 0 else 0.0
    label = "Very High" if ratio >= 2.0 else "High" if ratio >= 1.3 else "Low" if ratio < 0.7 else "Normal"
    return {"current": current, "average": baseline, "ratio": round(ratio, 2), "signal": label}


# ----------------------------- MARKET STRUCTURE --------------------------
def detect_swings(candles: List[list], lookback: int = 3, include_indices: bool = False):
    highs, lows = [], []
    # A pivot is confirmed only after `lookback` bars to its right have closed.
    for i in range(lookback, len(candles) - lookback):
        h, l = candles[i][2], candles[i][3]
        left_right = list(range(i - lookback, i)) + list(range(i + 1, i + lookback + 1))
        if all(h > candles[j][2] for j in left_right):
            highs.append((i, h))
        if all(l < candles[j][3] for j in left_right):
            lows.append((i, l))
    if include_indices:
        return highs, lows
    return [p for _, p in highs], [p for _, p in lows]


def detect_market_structure(candles: List[list]) -> Dict:
    sh, sl = detect_swings(candles, include_indices=True)
    if len(sh) < 2 or len(sl) < 2:
        return {"trend": "Unknown", "higher_high": False, "higher_low": False,
                "lower_high": False, "lower_low": False, "swing_highs": sh, "swing_lows": sl}
    hh, hl = sh[-1][1] > sh[-2][1], sl[-1][1] > sl[-2][1]
    lh, ll = sh[-1][1] < sh[-2][1], sl[-1][1] < sl[-2][1]
    trend = "Bullish" if hh and hl else "Bearish" if lh and ll else "Range"
    return {"trend": trend, "higher_high": hh, "higher_low": hl,
            "lower_high": lh, "lower_low": ll, "swing_highs": sh, "swing_lows": sl}


def detect_bos(candles: List[list], structure: Optional[Dict] = None) -> str:
    structure = structure or detect_market_structure(candles)
    sh, sl = structure["swing_highs"], structure["swing_lows"]
    if not sh or not sl or len(candles) < 2:
        return "None"
    previous_close, close = candles[-2][4], candles[-1][4]
    # Ignore pivots too old to be useful; use the most recent confirmed pivot.
    high_level, low_level = sh[-1][1], sl[-1][1]
    if previous_close <= high_level < close:
        return "Bullish"
    if previous_close >= low_level > close:
        return "Bearish"
    return "None"


def detect_choch(structure: Dict, bos: str) -> str:
    if structure["trend"] == "Bearish" and bos == "Bullish":
        return "Bullish"
    if structure["trend"] == "Bullish" and bos == "Bearish":
        return "Bearish"
    return "None"


# ----------------------------- LIQUIDITY / FVG / OB -----------------------
def detect_liquidity(candles: List[list], lookback: int = 20) -> Dict:
    if len(candles) < lookback + 2:
        return {"sweep": "None", "pool_high": None, "pool_low": None}
    prior = candles[-lookback - 1:-1]
    pool_high = max(c[2] for c in prior)
    pool_low = min(c[3] for c in prior)
    last = candles[-1]
    # A sweep requires a wick through a prior pool and a close back inside it.
    swept_high = last[2] > pool_high and last[4] < pool_high
    swept_low = last[3] < pool_low and last[4] > pool_low
    sweep = "Buy-side liquidity swept" if swept_high else "Sell-side liquidity swept" if swept_low else "None"
    return {"sweep": sweep, "pool_high": pool_high, "pool_low": pool_low}


def detect_fvg(candles: List[list], scan: int = 30) -> Dict:
    bullish, bearish = None, None
    start = max(2, len(candles) - scan)
    current_price = candles[-1][4]
    for i in range(start, len(candles)):
        first, middle, third = candles[i - 2], candles[i - 1], candles[i]
        if third[3] > first[2]:
            low, high = first[2], third[3]
            if current_price >= low:  # still relevant / not fully traded through
                bullish = {"low": low, "high": high, "index": i}
        if third[2] < first[3]:
            low, high = third[2], first[3]
            if current_price <= high:
                bearish = {"low": low, "high": high, "index": i}
    return {"bullish": bullish, "bearish": bearish,
            "bullish_fvg": bullish is not None, "bearish_fvg": bearish is not None}


def detect_order_block(candles: List[list], atr: float, scan: int = 25) -> Dict:
    bullish = bearish = None
    if atr <= 0:
        return {"bullish": None, "bearish": None, "bullish_ob": False, "bearish_ob": False}
    start = max(1, len(candles) - scan)
    # Last opposite-colour candle before a displacement candle closing beyond its range.
    for i in range(start, len(candles)):
        prev, impulse = candles[i - 1], candles[i]
        body = abs(impulse[4] - impulse[1])
        if body < atr * 0.8:
            continue
        if impulse[4] > impulse[1] and prev[4] < prev[1] and impulse[4] > prev[2]:
            zone = {"low": prev[3], "high": prev[2], "index": i - 1}
            if candles[-1][4] >= zone["low"]:
                bullish = zone
        elif impulse[4] < impulse[1] and prev[4] > prev[1] and impulse[4] < prev[3]:
            zone = {"low": prev[3], "high": prev[2], "index": i - 1}
            if candles[-1][4] <= zone["high"]:
                bearish = zone
    return {"bullish": bullish, "bearish": bearish,
            "bullish_ob": bullish is not None, "bearish_ob": bearish is not None}


# ----------------------------- SIGNAL / RISK ------------------------------


def validate_analysis_inputs(market: str, symbol: str,
                             timeframe: str, candles: list) -> None:
    if market not in MARKETS:
        raise ValueError("Unsupported market")
    if symbol not in SYMBOLS:
        raise ValueError("Unsupported symbol")
    if timeframe not in TIMEFRAMES:
        raise ValueError("Unsupported timeframe")
    if not isinstance(candles, list) or len(candles) < MIN_CANDLES:
        raise ValueError(f"Need at least {MIN_CANDLES} closed candles")

    previous_ts = None

    for row in candles:
        if not isinstance(row, (list, tuple)) or len(row) < 6:
            raise ValueError("Invalid OHLCV candle structure")

        values = row[:6]

        if not all(
            isinstance(v, (int, float))
            and math.isfinite(float(v))
            for v in values
        ):
            raise ValueError("OHLCV values must be finite numbers")

        ts, op, high, low, close, volume = map(float, values)

        if min(op, high, low, close) <= 0 or volume < 0:
            raise ValueError("Invalid OHLCV price or volume")

        if high < low or high < max(op, close) or low > min(op, close):
            raise ValueError("Invalid OHLC price relationships")

        if previous_ts is not None and ts <= previous_ts:
            raise ValueError("Candle timestamps must increase")

        previous_ts = ts

def analyze_candles(market: str, symbol: str, timeframe: str, candles: List[list]) -> Dict:
    validate_analysis_inputs(market, symbol, timeframe, candles)
    closes = [c[4] for c in candles]
    price = closes[-1]
    atr = calculate_atr(candles)
    atr_valid = (
        isinstance(atr, (int, float))
        and math.isfinite(float(atr))
        and atr > 0
    )
    if not atr_valid:
        atr = 0.0
    structure = detect_market_structure(candles)
    bos = detect_bos(candles, structure)
    choch = detect_choch(structure, bos)
    liquidity = detect_liquidity(candles)
    fvg = detect_fvg(candles)
    volume = analyze_volume(candles)
    order_block = detect_order_block(candles, atr)
    ema_fast, ema_slow = ema(closes, 20), ema(closes, 50)

    score = 0.0
    reasons = []
    trend = structure["trend"]
    if trend == "Bullish": score += 2; reasons.append("Bullish swing structure")
    elif trend == "Bearish": score -= 2; reasons.append("Bearish swing structure")
    if bos == "Bullish": score += 2; reasons.append("Bullish BOS")
    elif bos == "Bearish": score -= 2; reasons.append("Bearish BOS")
    if choch == "Bullish": score += 2; reasons.append("Bullish CHOCH")
    elif choch == "Bearish": score -= 2; reasons.append("Bearish CHOCH")
    if fvg["bullish_fvg"]: score += 1; reasons.append("Bullish FVG present")
    if fvg["bearish_fvg"]: score -= 1; reasons.append("Bearish FVG present")
    if order_block["bullish_ob"]: score += 1; reasons.append("Bullish order block present")
    if order_block["bearish_ob"]: score -= 1; reasons.append("Bearish order block present")
    if liquidity["sweep"] == "Sell-side liquidity swept": score += 1.5; reasons.append("Sell-side liquidity sweep/reclaim")
    elif liquidity["sweep"] == "Buy-side liquidity swept": score -= 1.5; reasons.append("Buy-side liquidity sweep/reclaim")
    if ema_fast > ema_slow: score += 1; reasons.append("EMA20 above EMA50")
    elif ema_fast < ema_slow: score -= 1; reasons.append("EMA20 below EMA50")
    if volume["ratio"] >= 1.3:
        if closes[-1] > candles[-1][1]: score += 0.5
        elif closes[-1] < candles[-1][1]: score -= 0.5
        reasons.append("Elevated volume confirmation")

    score = round(score, 2)
    threshold = 4.0
    signal = "BUY" if score >= threshold else "SELL" if score <= -threshold else "WAIT"
    if not atr_valid or price <= 0:
        signal = "WAIT"
    # Spot has no native short position in this scanner: bearish signals mean exit/avoid, not short.
    if market == "SPOT" and signal == "SELL":
        signal = "SELL/EXIT"

    stop_loss = take_profit = risk_distance = None
    reward_risk = None

    quantity = None
    notional = None
    gross_risk_per_unit = None
    total_risk_per_unit = None

    estimated_fees = None
    estimated_slippage = None
    total_risk_usdt = None
    net_reward_usdt = None

    if signal in ("BUY", "SELL"):
        if signal == "BUY":
            structural_lows = [
                p for _, p in structure["swing_lows"]
                if p < price
            ]
            candidate = (
                max(structural_lows)
                if structural_lows
                else price - atr * 1.5
            )
            stop_loss = min(candidate, price - atr * 0.5)
            risk_distance = price - stop_loss

        else:
            structural_highs = [
                p for _, p in structure["swing_highs"]
                if p > price
            ]
            candidate = (
                min(structural_highs)
                if structural_highs
                else price + atr * 1.5
            )
            stop_loss = max(candidate, price + atr * 0.5)
            risk_distance = stop_loss - price

        fee_rate = PAPER_TAKER_FEE_RATES[market]
        cost_rate = fee_rate + PAPER_SLIPPAGE_RATE

        if (
            stop_loss <= 0
            or risk_distance <= 0
            or not math.isfinite(risk_distance)
            or cost_rate >= 1.0
        ):
            signal = "WAIT"
            stop_loss = take_profit = risk_distance = None

        else:
            gross_risk_per_unit = risk_distance

            # Entry plus stop-exit costs.
            total_risk_per_unit = (
                risk_distance + cost_rate * (price + stop_loss)
            )

            # Net target-distance calculation, including both-side costs.
            if signal == "BUY":
                required_distance = (
                    MIN_REWARD_RISK * total_risk_per_unit
                    + 2.0 * price * cost_rate
                ) / (1.0 - cost_rate)
            else:
                required_distance = (
                    MIN_REWARD_RISK * total_risk_per_unit
                    + 2.0 * price * cost_rate
                ) / (1.0 + cost_rate)

            target_distance = max(
                risk_distance * MIN_REWARD_RISK,
                atr * 3.0,
                required_distance,
            )

            take_profit = (
                price + target_distance
                if signal == "BUY"
                else price - target_distance
            )

            if take_profit <= 0:
                signal = "WAIT"
                stop_loss = take_profit = risk_distance = None
                gross_risk_per_unit = None
                total_risk_per_unit = None

            else:
                net_reward_per_unit = (
                    target_distance
                    - cost_rate * (price + take_profit)
                )

                raw_reward_risk = (
                    net_reward_per_unit / total_risk_per_unit
                    if total_risk_per_unit > 0
                    else 0.0
                )

                if (
                    net_reward_per_unit <= 0
                    or raw_reward_risk < MIN_REWARD_RISK
                ):
                    signal = "WAIT"
                    stop_loss = take_profit = risk_distance = None
                    gross_risk_per_unit = None
                    total_risk_per_unit = None

                else:
                    reward_risk = round(raw_reward_risk, 4)

                    risk_amount = (
                        PAPER_EQUITY_USDT
                        * RISK_PER_TRADE_PERCENT / 100.0
                    )

                    max_notional = (
                        PAPER_EQUITY_USDT
                        * MAX_NOTIONAL_EQUITY_MULTIPLE
                    )

                    quantity = min(
                        risk_amount / total_risk_per_unit,
                        max_notional / price,
                    )

                    notional = quantity * price

                    estimated_fees = (
                        quantity * (price + stop_loss) * fee_rate
                    )

                    estimated_slippage = (
                        quantity * (price + stop_loss)
                        * PAPER_SLIPPAGE_RATE
                    )

                    total_risk_usdt = (
                        quantity * total_risk_per_unit
                    )

                    net_reward_usdt = (
                        quantity * net_reward_per_unit
                    )


    return {
        "market": market, "symbol": symbol, "timeframe": timeframe,
        "price": price, "trend": trend, "structure": structure,
        "bos": bos, "choch": choch, "liquidity": liquidity,
        "fvg": fvg, "order_block": order_block, "volume": volume,
        "atr": atr, "atr_percent": (atr / price * 100.0) if price else 0.0,
        "ema20": ema_fast, "ema50": ema_slow,
        "score": score, "signal": signal, "reasons": reasons,
        "stop_loss": stop_loss, "take_profit": take_profit,
        "reward_risk": reward_risk,
        "paper_risk_usdt": (
            quantity * gross_risk_per_unit
            if quantity is not None and gross_risk_per_unit is not None
            else None
        ),
        "paper_total_risk_usdt": total_risk_usdt,
        "paper_estimated_fees_usdt": estimated_fees,
        "paper_estimated_slippage_usdt": estimated_slippage,
        "paper_estimated_net_reward_usdt": net_reward_usdt,
        "paper_quantity": quantity,
        "paper_notional_usdt": notional,
        "time_utc": datetime.now(timezone.utc).isoformat(),
    }


def analyze(market: str, symbol: str, timeframe: str) -> Dict:
    candles = get_candles(market, symbol, timeframe)
    return analyze_candles(market, symbol, timeframe, candles)


# ----------------------------- MULTI-TIMEFRAME -----------------------------
def combine_timeframes(results: List[Dict]) -> Dict:
    weighted_score, total_weight = 0.0, 0.0
    for item in results:
        weight = TIMEFRAME_WEIGHTS.get(item["timeframe"], 1.0)
        weighted_score += item["score"] * weight
        total_weight += weight
    score = weighted_score / total_weight if total_weight else 0.0
    signal = "BUY" if score >= 3.5 else "SELL" if score <= -3.5 else "WAIT"
    return {"weighted_score": round(score, 2), "overall_signal": signal}


def print_result(result: Dict) -> None:
    print(f"\n[{result['market']}] {result['symbol']} | {result['timeframe']}")
    print(f"Price: {result['price']:.6g} | Trend: {result['trend']} | Score: {result['score']}")
    print(f"BOS: {result['bos']} | CHOCH: {result['choch']} | Liquidity: {result['liquidity']['sweep']}")
    print(f"FVG: bull={result['fvg']['bullish_fvg']} bear={result['fvg']['bearish_fvg']} | OB: bull={result['order_block']['bullish_ob']} bear={result['order_block']['bearish_ob']}")
    print(f"Volume: {result['volume']['signal']} ({result['volume']['ratio']}x) | ATR: {result['atr']:.6g} ({result['atr_percent']:.2f}%)")
    print(f"SIGNAL: {result['signal']} | SL: {result['stop_loss']} | TP: {result['take_profit']} | R:R: {result['reward_risk']}")
    if result["paper_quantity"] is not None:
        print(
            f"PAPER-ONLY sizing: qty={result['paper_quantity']:.6g}, "
            f"notional≈{result['paper_notional_usdt']:.2f} USDT, "
            f"total estimated risk≈{result['paper_total_risk_usdt']:.2f} USDT"
        )
    if result["reasons"]:
        print("Reasons: " + "; ".join(result["reasons"]))


def run_analysis() -> None:
    print("\n========== SI AI | FUTURES-FIRST MARKET INTELLIGENCE ==========")
    print("PUBLIC DATA ONLY | NO API KEYS | NO ORDERS | NOT FINANCIAL ADVICE")
    for market in MARKETS:
        print(f"\n================ {market} ================")
        for symbol in SYMBOLS:
            collected = []
            for timeframe in TIMEFRAMES:
                try:
                    result = analyze(market, symbol, timeframe)
                    collected.append(result)
                    print_result(result)
                except Exception as exc:
                    print(f"Analysis error [{market} {symbol} {timeframe}]: {type(exc).__name__}: {exc}")
                time.sleep(REQUEST_DELAY_SECONDS)
            if collected:
                combined = combine_timeframes(collected)
                print(f"\n>>> {market} {symbol} MULTI-TIMEFRAME: {combined['overall_signal']} (weighted score {combined['weighted_score']})")


if __name__ == "__main__":
    try:
        run_analysis()
    except KeyboardInterrupt:
        print("\nSI AI stopped by user.")
    except Exception as exc:
        print(f"\nSI AI fatal error: {type(exc).__name__}: {exc}")
