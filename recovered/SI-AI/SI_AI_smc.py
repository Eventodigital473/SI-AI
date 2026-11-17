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
# Dynamic Binance USDT universe. Symbols are canonical BASE/USDT strings.
# The discovery layer selects liquid, actively traded markets independently for
# Binance USD-M USDT perpetual contracts only. No order endpoints or credentials are used.
TIMEFRAMES = ["15m", "1h", "4h", "1d"]
CANDLE_LIMIT = 250
MIN_CANDLES = 80
REQUEST_DELAY_SECONDS = 0.35

MIN_ELIGIBLE_COINS = 15
TARGET_UNIVERSE_SIZE = 50
MAX_UNIVERSE_SIZE = 100
UNIVERSE_REFRESH_SECONDS = 900
MIN_FUTURES_QUOTE_VOLUME_USDT = 10_000_000.0
MAX_SPREAD_PERCENT = 0.15
PRIORITY_BASES = ("BTC", "ETH", "BNB", "SOL")
EXCLUDED_BASES = {
    "USDC", "FDUSD", "TUSD", "USDP", "DAI", "USDE", "USDS",
    "BUSD", "USDD", "USD1", "RLUSD", "XUSD", "UST", "USTC", "EUR", "TRY",
    "EURC", "EURI", "AEUR", "USYC", "USDJ", "USDX", "USDB",
    "USDF", "USDK", "USTB", "USDH",
    "WBTC", "WETH", "STETH", "WSTETH", "CBETH", "BETH",
    "WBETH", "WBNB", "BTCB", "WAVAX", "WMATIC", "WFTM",
}
LEVERAGED_SUFFIXES = ("UP", "DOWN", "BULL", "BEAR")
MARKET_SYMBOLS = {"FUTURES": ["BTC/USDT", "ETH/USDT"]}
MARKET_UNIVERSE_STATUS = {
    "FUTURES": "not_refreshed",
}
MARKET_UNIVERSE_DIAGNOSTICS = {
    "FUTURES": {},
}
SYMBOLS = ["BTC/USDT", "ETH/USDT"]
_UNIVERSE_LAST_REFRESH = 0.0

# Futures is intentionally analysed first. Both exchanges use public endpoints.
MARKETS = ["FUTURES"]
_MARKET_UNIVERSE_LAST_REFRESH = {market: 0.0 for market in MARKETS}
FUTURES_EXCHANGE_ID = "binanceusdm"

# Analysis/risk assumptions only; no account balance is queried and no orders sent.
PAPER_EQUITY_USDT = 100.0
RISK_PER_TRADE_PERCENT = 0.5
MARGIN_ALLOCATION_PERCENT = 20.0
RECOMMENDED_FUTURES_LEVERAGE = 1.0
MAX_NOTIONAL_EQUITY_MULTIPLE = (
    MARGIN_ALLOCATION_PERCENT / 100.0 * RECOMMENDED_FUTURES_LEVERAGE
)
MIN_REWARD_RISK = 2.0

# Illustrative paper assumptions, not account-specific exchange rates.
PAPER_TAKER_FEE_RATES = {"FUTURES": 0.0005}
PAPER_SLIPPAGE_RATE = 0.0002

TIMEFRAME_WEIGHTS = {"15m": 1.0, "1h": 1.5, "4h": 2.0, "1d": 2.0}


def make_exchange(market: str):
    if market != "FUTURES":
        raise ValueError("SI-AI supports Binance USD-M Futures only")
    return ccxt.binanceusdm({
        "enableRateLimit": True,
        "timeout": 20000,
        "options": {"defaultType": "future"},
    })

EXCHANGES = {market: make_exchange(market) for market in MARKETS}


def get_symbols(market: str) -> List[str]:
    """Return the latest selected canonical USDT symbols for one market."""
    if market not in MARKETS:
        raise ValueError("Unsupported market")
    return list(MARKET_SYMBOLS.get(market, []))


def _finite_number(value):
    # bool is a numeric subclass in Python, but it is never a valid market price
    # or quote-volume value. Reject it instead of silently treating True as 1.0.
    if isinstance(value, bool):
        return None
    try:
        result = float(value)
    except (TypeError, ValueError):
        return None
    return result if math.isfinite(result) else None


def _eligible_base(base: str) -> bool:
    base = str(base or "").upper()
    if not base or base in EXCLUDED_BASES:
        return False
    if base.endswith(LEVERAGED_SUFFIXES):
        return False
    if any(tag in base for tag in ("2L", "2S", "3L", "3S", "5L", "5S")):
        return False
    return True


def _index_book_tickers(book_tickers: dict) -> Dict[str, dict]:
    """Index unified and raw Binance bookTicker aliases without guessing prices."""
    indexed = {}
    if not isinstance(book_tickers, dict):
        return indexed

    for key, ticker in book_tickers.items():
        if not isinstance(ticker, dict):
            continue
        info = ticker.get("info")
        info = info if isinstance(info, dict) else {}
        aliases = (
            key,
            ticker.get("symbol"),
            ticker.get("id"),
            info.get("symbol"),
        )
        for alias in aliases:
            if alias is not None and str(alias).strip():
                indexed[str(alias).strip()] = ticker
    return indexed


def _find_book_ticker(indexed: dict, exchange_symbol: str,
                      canonical: str, metadata: dict):
    """Resolve CCXT unified symbols and Binance market IDs to one quote."""
    aliases = (
        exchange_symbol,
        canonical,
        metadata.get("symbol"),
        metadata.get("id"),
    )
    for alias in aliases:
        if alias is not None:
            ticker = indexed.get(str(alias).strip())
            if isinstance(ticker, dict):
                return ticker
    return None


def _book_ticker_prices(ticker: dict):
    """Read normalized CCXT bid/ask or raw Binance bidPrice/askPrice."""
    if not isinstance(ticker, dict):
        return None, None
    info = ticker.get("info")
    info = info if isinstance(info, dict) else {}
    bid_values = (
        ticker.get("bid"), ticker.get("bidPrice"), ticker.get("bid_price"),
        info.get("bidPrice"), info.get("bid"),
    )
    ask_values = (
        ticker.get("ask"), ticker.get("askPrice"), ticker.get("ask_price"),
        info.get("askPrice"), info.get("ask"),
    )
    bid = next((value for raw in bid_values
                if (value := _finite_number(raw)) is not None), None)
    ask = next((value for raw in ask_values
                if (value := _finite_number(raw)) is not None), None)
    return bid, ask


def _spread_percent(bid: float, ask: float):
    """Return midpoint-relative spread percentage for a valid two-sided quote."""
    bid_value = _finite_number(bid)
    ask_value = _finite_number(ask)
    if bid_value is None or ask_value is None:
        return None
    if bid_value <= 0 or ask_value < bid_value:
        return None
    total = ask_value + bid_value
    if total <= 0:
        return None
    return 200.0 * (ask_value - bid_value) / total


def refresh_symbol_universe(force: bool = False) -> Dict[str, List[str]]:
    """
    Discover liquid Binance USD-M USDT perpetual markets only.
    Failed refreshes preserve the last-known-good list; no synthetic symbols
    are added to reach the minimum. A market with fewer than 15 qualifiers
    is reported as undersized and the scanner will fail closed for that market.
    """
    global SYMBOLS, _UNIVERSE_LAST_REFRESH
    now = time.monotonic()

    failures = []
    refreshed_any = False
    for market in MARKETS:
        last_refresh = _MARKET_UNIVERSE_LAST_REFRESH.get(market, 0.0)
        if (
            not force
            and last_refresh
            and now - last_refresh < UNIVERSE_REFRESH_SECONDS
        ):
            continue

        exchange = EXCHANGES[market]
        try:
            exchange.load_markets()
            tickers = exchange.fetch_tickers()
            book_tickers = None
            if market == "FUTURES":
                # Binance USD-M 24h tickers do not reliably include bid/ask.
                # Use CCXT's bulk bookTicker endpoint once for the whole market.
                fetch_bids_asks = getattr(exchange, "fetch_bids_asks", None)
                if not callable(fetch_bids_asks):
                    raise RuntimeError(
                        "Futures exchange does not support bulk bid/ask retrieval"
                    )
                book_tickers = fetch_bids_asks()
                if not isinstance(book_tickers, dict) or not book_tickers:
                    raise RuntimeError(
                        "Futures bulk bookTicker response is empty or invalid"
                    )
            candidates = []
            diagnostics = {
                "markets_seen": 0,
                "volume_qualified": 0,
                "book_ticker_matched": 0,
                "valid_bid_ask": 0,
                "spread_qualified": 0,
            }
            book_ticker_index = (
                _index_book_tickers(book_tickers)
                if market == "FUTURES"
                else {}
            )
            minimum_volume = MIN_FUTURES_QUOTE_VOLUME_USDT

            for exchange_symbol, metadata in exchange.markets.items():
                diagnostics["markets_seen"] += 1
                if not isinstance(metadata, dict):
                    continue
                # Require an explicit active flag; unknown status is not eligible.
                if metadata.get("active") is not True:
                    continue
                if metadata.get("quote") != "USDT":
                    continue
                if not _eligible_base(metadata.get("base")):
                    continue

                if not (
                    metadata.get("swap") is True
                    and metadata.get("linear") is True
                    and metadata.get("settle") == "USDT"
                ):
                    continue

                canonical = f"{metadata['base']}/USDT"
                ticker = tickers.get(exchange_symbol) or tickers.get(canonical)
                if not isinstance(ticker, dict):
                    continue

                quote_volume = _finite_number(ticker.get("quoteVolume"))
                if quote_volume is None or quote_volume < minimum_volume:
                    continue
                diagnostics["volume_qualified"] += 1

                book_ticker = _find_book_ticker(
                    book_ticker_index, exchange_symbol, canonical, metadata
                )
                if not isinstance(book_ticker, dict):
                    continue
                diagnostics["book_ticker_matched"] += 1

                bid, ask = _book_ticker_prices(book_ticker)
                if bid is None or ask is None or bid <= 0 or ask < bid:
                    continue
                diagnostics["valid_bid_ask"] += 1

                spread_percent = _spread_percent(bid, ask)
                if spread_percent is None or spread_percent > MAX_SPREAD_PERCENT:
                    continue
                diagnostics["spread_qualified"] += 1

                candidates.append({
                    "symbol": canonical,
                    "base": metadata["base"],
                    "quote_volume": quote_volume,
                })

            candidates.sort(
                key=lambda item: item["quote_volume"], reverse=True
            )
            selected = candidates[:TARGET_UNIVERSE_SIZE]
            selected_symbols = [item["symbol"] for item in selected]

            # Keep the named core assets in the candidate universe when they
            # pass the same liquidity/spread/market filters.
            for preferred in PRIORITY_BASES:
                preferred_symbol = f"{preferred}/USDT"
                if (
                    preferred_symbol not in selected_symbols
                    and any(item["symbol"] == preferred_symbol for item in candidates)
                ):
                    if len(selected_symbols) >= TARGET_UNIVERSE_SIZE:
                        # Replace the lowest-ranked non-priority asset. Do not
                        # repeatedly overwrite the same final slot.
                        replace_index = next(
                            (
                                index
                                for index in range(len(selected_symbols) - 1, -1, -1)
                                if selected_symbols[index].split("/", 1)[0]
                                not in PRIORITY_BASES
                            ),
                            None,
                        )
                        if replace_index is not None:
                            selected_symbols[replace_index] = preferred_symbol
                    else:
                        selected_symbols.append(preferred_symbol)

            MARKET_UNIVERSE_DIAGNOSTICS[market] = {
                **diagnostics,
                "candidate_count": len(candidates),
                "selected_count": len(set(selected_symbols)),
            }
            MARKET_SYMBOLS[market] = list(dict.fromkeys(selected_symbols))
            MARKET_UNIVERSE_STATUS[market] = (
                "ready"
                if len(MARKET_SYMBOLS[market]) >= MIN_ELIGIBLE_COINS
                else "below_minimum"
            )
            _MARKET_UNIVERSE_LAST_REFRESH[market] = now
            refreshed_any = True

        except Exception as exc:
            failures.append(f"{market}: {type(exc).__name__}: {exc}")
            MARKET_UNIVERSE_STATUS[market] = (
                "unavailable_using_last_known_good"
                if MARKET_SYMBOLS.get(market)
                else "unavailable"
            )
            # Keep the last known good universe if the exchange is temporarily
            # unavailable. An empty initial universe remains empty (fail closed).

    if refreshed_any:
        union = []
        for market in MARKETS:
            for symbol in MARKET_SYMBOLS.get(market, []):
                if symbol not in union:
                    union.append(symbol)
        SYMBOLS = union
        _UNIVERSE_LAST_REFRESH = now

    if failures and not any(MARKET_SYMBOLS.get(market) for market in MARKETS):
        raise RuntimeError("Coin-universe discovery failed: " + "; ".join(failures))

    return {market: get_symbols(market) for market in MARKETS}





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
        if not all(
            not isinstance(value, bool)
            and isinstance(value, (int, float))
            and math.isfinite(float(value))
            for value in values
        ):
            continue
        if not float(ts).is_integer():
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


TIMEFRAME_MILLISECONDS = {
    "15m": 15 * 60 * 1000,
    "1h": 60 * 60 * 1000,
    "4h": 4 * 60 * 60 * 1000,
    "1d": 24 * 60 * 60 * 1000,
}


def validate_candle_continuity(candles: List[list], timeframe: str) -> None:
    """Fail closed when any expected timeframe candle is missing."""
    interval_ms = TIMEFRAME_MILLISECONDS.get(timeframe)
    if interval_ms is None:
        raise ValueError(f"Unsupported timeframe for continuity check: {timeframe}")
    if not candles:
        raise ValueError("Cannot validate continuity of an empty candle series")
    for index in range(1, len(candles)):
        delta = int(candles[index][0]) - int(candles[index - 1][0])
        if delta != interval_ms:
            raise ValueError(
                f"Missing or irregular {timeframe} candle between "
                f"rows {index - 1} and {index}: expected {interval_ms} ms, got {delta} ms"
            )


def validate_candle_freshness(candles: List[list], timeframe: str, now_ms: int) -> None:
    """Reject stale or implausibly future-dated closed candles."""
    interval_ms = TIMEFRAME_MILLISECONDS.get(timeframe)
    if interval_ms is None:
        raise ValueError(f"Unsupported timeframe for freshness check: {timeframe}")
    if not candles:
        raise ValueError("Cannot validate freshness of an empty candle series")
    if isinstance(now_ms, bool) or not isinstance(now_ms, (int, float)) or not math.isfinite(float(now_ms)):
        raise ValueError("Current timestamp must be a finite number")

    latest_close_ms = int(candles[-1][0]) + interval_ms
    age_ms = float(now_ms) - latest_close_ms
    if age_ms > 2 * interval_ms:
        raise ValueError(
            f"Stale {timeframe} candles: latest closed candle is "
            f"{age_ms / interval_ms:.2f} intervals old"
        )
    if age_ms < -interval_ms:
        raise ValueError("Candle series contains a future-dated closed candle")


def get_candles(market: str, symbol: str, timeframe: str) -> List[list]:
    exchange = EXCHANGES[market]
    exchange.load_markets()

    exchange_symbol = symbol

    if market == "FUTURES" and exchange_symbol not in exchange.markets:
        base, quote = symbol.split("/", 1)
        candidate = f"{base}/{quote}:{quote}"

        if candidate in exchange.markets:
            exchange_symbol = candidate

    metadata = exchange.markets.get(exchange_symbol)
    if (
        not isinstance(metadata, dict)
        or metadata.get("active") is not True
        or metadata.get("quote") != "USDT"
    ):
        raise ValueError(
            f"Symbol {symbol} is not confirmed as an active USDT market"
        )
    if not (
        metadata.get("swap") is True
        and metadata.get("linear") is True
        and metadata.get("settle") == "USDT"
    ):
        raise ValueError(f"Symbol {symbol} is not an active USDT perpetual market")

    raw = exchange.fetch_ohlcv(
        exchange_symbol,
        timeframe=timeframe,
        limit=CANDLE_LIMIT
    )
    candles = validate_candles(raw)
    validate_candle_continuity(candles, timeframe)
    validate_candle_freshness(candles, timeframe, exchange.milliseconds())
    return candles


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
    if len(candles) < 2 or (not sh and not sl):
        return "None"
    previous_close, close = candles[-2][4], candles[-1][4]
    # A directional BOS only needs the corresponding confirmed swing level.
    # Requiring BOTH a high and a low pivot suppresses valid breakouts in
    # one-sided/early structure histories.
    if sh and previous_close <= sh[-1][1] < close:
        return "Bullish"
    if sl and previous_close >= sl[-1][1] > close:
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


def calculate_net_reward_risk(
    entry: float, stop_loss: float, take_profit: float,
    side: str, market: str, *,
    fee_rate: Optional[float] = None,
    slippage_rate: Optional[float] = None,
    entry_slippage_included: bool = False,
) -> float:
    """Return fee/slippage-adjusted reward-to-risk for the supplied fill prices."""
    if market not in PAPER_TAKER_FEE_RATES:
        raise ValueError("Unsupported market for reward/risk calculation")
    values = [_finite_number(value) for value in (entry, stop_loss, take_profit)]
    if any(value is None or value <= 0 for value in values):
        raise ValueError("Entry, stop-loss and take-profit must be finite positive prices")
    entry_price, stop_price, target_price = values
    direction = str(side).upper()
    fee = PAPER_TAKER_FEE_RATES[market] if fee_rate is None else _finite_number(fee_rate)
    slippage = PAPER_SLIPPAGE_RATE if slippage_rate is None else _finite_number(slippage_rate)
    if fee is None or slippage is None or not 0 <= fee < 0.05 or not 0 <= slippage < 0.05:
        raise ValueError("Fee and slippage rates must be finite values in [0, 5%)")
    entry_cost = fee * entry_price
    if not entry_slippage_included:
        entry_cost += slippage * entry_price
    cost_rate = fee + slippage
    if direction == "LONG":
        if not stop_price < entry_price < target_price:
            raise ValueError("Long levels must satisfy stop < entry < target")
        gross_risk = entry_price - stop_price
        gross_reward = target_price - entry_price
    elif direction == "SHORT":
        if not target_price < entry_price < stop_price:
            raise ValueError("Short levels must satisfy target < entry < stop")
        gross_risk = stop_price - entry_price
        gross_reward = entry_price - target_price
    else:
        raise ValueError("side must be LONG or SHORT")
    net_risk = gross_risk + entry_cost + cost_rate * stop_price
    net_reward = gross_reward - entry_cost - cost_rate * target_price
    if net_risk <= 0 or net_reward <= 0:
        return 0.0
    return net_reward / net_risk


def validate_analysis_inputs(market: str, symbol: str,
                             timeframe: str, candles: list) -> None:
    if market not in MARKETS:
        raise ValueError("Unsupported market")
    if (
        not isinstance(symbol, str)
        or symbol != symbol.strip()
        or symbol.count("/") != 1
        or not symbol.split("/", 1)[0]
        or symbol.split("/", 1)[1] != "USDT"
        or symbol != symbol.upper()
    ):
        raise ValueError("symbol must be a canonical BASE/USDT market")
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
            not isinstance(v, bool)
            and isinstance(v, (int, float))
            and math.isfinite(float(v))
            for v in values
        ):
            raise ValueError("OHLCV values must be finite numbers")

        ts, op, high, low, close, volume = map(float, values)

        if not ts.is_integer():
            raise ValueError("Candle timestamps must be integer milliseconds")

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
    # CHOCH is the classification of a counter-trend BOS, not a second
    # independent event. Count one structure-break contribution only.
    if choch == "Bullish":
        score += 2.5
        reasons.append("Bullish CHOCH")
    elif choch == "Bearish":
        score -= 2.5
        reasons.append("Bearish CHOCH")
    elif bos == "Bullish":
        score += 2
        reasons.append("Bullish BOS")
    elif bos == "Bearish":
        score -= 2
        reasons.append("Bearish BOS")
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

                raw_reward_risk = calculate_net_reward_risk(
                    price,
                    stop_loss,
                    take_profit,
                    "LONG" if signal == "BUY" else "SHORT",
                    market,
                )

                if (
                    net_reward_per_unit <= 0
                    or raw_reward_risk < MIN_REWARD_RISK - 1e-9
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

                    margin_budget = (
                        PAPER_EQUITY_USDT
                        * MARGIN_ALLOCATION_PERCENT / 100.0
                    )
                    recommended_leverage = (
                        RECOMMENDED_FUTURES_LEVERAGE
                        if market == "FUTURES" else 1.0
                    )
                    max_notional = margin_budget * recommended_leverage

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
        "recommended_leverage": (
            RECOMMENDED_FUTURES_LEVERAGE
            if market == "FUTURES" and quantity is not None else None
        ),
        "paper_margin_required_usdt": (
            notional / RECOMMENDED_FUTURES_LEVERAGE
            if notional is not None and market == "FUTURES" else notional
        ),
        "paper_margin_budget_usdt": PAPER_EQUITY_USDT * MARGIN_ALLOCATION_PERCENT / 100.0,
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
    print("\n========== SI AI | FUTURES-ONLY MARKET INTELLIGENCE ==========")
    print("PUBLIC DATA ONLY | NO API KEYS | NO ORDERS | NOT FINANCIAL ADVICE")
    refresh_symbol_universe(force=True)
    for market in MARKETS:
        symbols = get_symbols(market)
        if len(symbols) < MIN_ELIGIBLE_COINS:
            print(
                f"\n{market}: only {len(symbols)} eligible coins; "
                f"minimum is {MIN_ELIGIBLE_COINS}. Skipping this market."
            )
            continue
        print(f"\n================ {market} ({len(symbols)} coins) ================")
        for symbol in symbols:
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
