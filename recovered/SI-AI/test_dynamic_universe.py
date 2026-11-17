import unittest
from unittest.mock import patch

import SI_AI_smc as si
import si_ai_scanner as scanner


class FakeFuturesExchange:
    def __init__(self, count=110, fail=False):
        self.count = count
        self.fail = fail
        self.markets = {}
        self._tickers = {}
        self._book_tickers = {}
        self.book_ticker_calls = 0
        for index in range(count):
            self._add(f"COIN{index:03d}", 50_000_000.0 - index * 1000.0)
        for base, volume in (("BNB", 20_000_000.0), ("SOL", 19_000_000.0),
                             ("BTC", 18_000_000.0), ("ETH", 17_000_000.0)):
            self._add(base, volume)
        for base in ("USDC", "RLUSD", "XUSD", "TOKENUP", "TOKEN3L", "WBNB"):
            self._add(base, 90_000_000.0)
        self._add("LOWVOL", 1_000_000.0)
        self._add("WIDE", 90_000_000.0, ask=1.02)
        self._add("INACTIVE", 90_000_000.0, active=False)
        self._add("UNKNOWN", 90_000_000.0, active=None)

    def _add(self, base, volume, ask=1.0005, active=True):
        symbol = f"{base}/USDT:USDT"
        self.markets[symbol] = {
            "symbol": symbol, "id": f"{base}USDT", "base": base,
            "quote": "USDT", "active": active, "swap": True,
            "linear": True, "settle": "USDT",
        }
        self._tickers[symbol] = {"quoteVolume": volume}
        self._book_tickers[f"{base}USDT"] = {
            "symbol": symbol, "id": f"{base}USDT",
            "bid": 1.0, "ask": ask,
        }

    def load_markets(self):
        if self.fail:
            raise RuntimeError("simulated exchange outage")
        return self.markets

    def fetch_tickers(self):
        if self.fail:
            raise RuntimeError("simulated ticker outage")
        return self._tickers

    def fetch_bids_asks(self):
        self.book_ticker_calls += 1
        if self.fail:
            raise RuntimeError("simulated book ticker outage")
        return self._book_tickers


class FakeCandleExchange:
    def __init__(self, now_ms, active=True):
        self.now_ms = now_ms
        self.calls = 0
        symbol = "BTC/USDT:USDT"
        self.markets = {symbol: {
            "active": active, "quote": "USDT", "swap": True,
            "linear": True, "settle": "USDT",
        }}
        interval = si.TIMEFRAME_MILLISECONDS["15m"]
        current_open = now_ms - (now_ms % interval)
        self.rows = [
            [current_open - (80 - index) * interval,
             100.0, 101.0, 99.0, 100.0, 1000.0]
            for index in range(81)
        ]

    def load_markets(self):
        return self.markets

    def milliseconds(self):
        return self.now_ms

    def fetch_ohlcv(self, symbol, timeframe, limit):
        self.calls += 1
        return self.rows[-limit:]


class DynamicUniverseTests(unittest.TestCase):
    def setUp(self):
        self.original_market_symbols = {
            key: list(value) for key, value in si.MARKET_SYMBOLS.items()
        }
        self.original_symbols = list(si.SYMBOLS)
        self.original_refresh = si._UNIVERSE_LAST_REFRESH
        self.original_market_refresh = dict(si._MARKET_UNIVERSE_LAST_REFRESH)
        self.original_status = dict(si.MARKET_UNIVERSE_STATUS)
        self.original_diagnostics = dict(si.MARKET_UNIVERSE_DIAGNOSTICS)

    def tearDown(self):
        si.MARKET_SYMBOLS.clear()
        si.MARKET_SYMBOLS.update(self.original_market_symbols)
        si.SYMBOLS = self.original_symbols
        si._UNIVERSE_LAST_REFRESH = self.original_refresh
        si._MARKET_UNIVERSE_LAST_REFRESH.clear()
        si._MARKET_UNIVERSE_LAST_REFRESH.update(self.original_market_refresh)
        si.MARKET_UNIVERSE_STATUS.clear()
        si.MARKET_UNIVERSE_STATUS.update(self.original_status)
        si.MARKET_UNIVERSE_DIAGNOSTICS.clear()
        si.MARKET_UNIVERSE_DIAGNOSTICS.update(self.original_diagnostics)

    def test_project_is_futures_only(self):
        self.assertEqual(si.MARKETS, ["FUTURES"])
        self.assertEqual(set(si.EXCHANGES), {"FUTURES"})
        with self.assertRaisesRegex(ValueError, "Futures only"):
            si.make_exchange("SPOT")

    def test_selects_target_50_liquid_futures_and_prioritizes_core_assets(self):
        fake = FakeFuturesExchange()
        with patch.dict(si.EXCHANGES, {"FUTURES": fake}, clear=True):
            selected = si.refresh_symbol_universe(force=True)
        symbols = selected["FUTURES"]
        self.assertEqual(len(symbols), si.TARGET_UNIVERSE_SIZE)
        for base in ("BTC", "ETH", "SOL", "BNB"):
            self.assertIn(f"{base}/USDT", symbols)
        for base in ("USDC", "RLUSD", "XUSD", "TOKENUP", "TOKEN3L",
                     "WBNB", "LOWVOL", "WIDE", "INACTIVE", "UNKNOWN"):
            self.assertNotIn(f"{base}/USDT", symbols)
        self.assertEqual(fake.book_ticker_calls, 1)

    def test_empty_bookticker_preserves_last_known_good_universe(self):
        fake = FakeFuturesExchange()
        si.MARKET_SYMBOLS["FUTURES"] = ["KEEP/USDT"]
        with patch.object(fake, "fetch_bids_asks", return_value={}), patch.dict(
            si.EXCHANGES, {"FUTURES": fake}, clear=True
        ):
            selected = si.refresh_symbol_universe(force=True)
        self.assertEqual(selected["FUTURES"], ["KEEP/USDT"])
        self.assertEqual(
            si.MARKET_UNIVERSE_STATUS["FUTURES"],
            "unavailable_using_last_known_good",
        )

    def test_does_not_fabricate_candidates_to_reach_minimum(self):
        fake = FakeFuturesExchange(count=10)
        for base in ("BNB", "SOL", "BTC", "ETH"):
            symbol = f"{base}/USDT:USDT"
            fake.markets.pop(symbol, None)
            fake._tickers.pop(symbol, None)
            fake._book_tickers.pop(f"{base}USDT", None)
        with patch.dict(si.EXCHANGES, {"FUTURES": fake}, clear=True):
            selected = si.refresh_symbol_universe(force=True)
        self.assertEqual(len(selected["FUTURES"]), 10)
        self.assertEqual(si.MARKET_UNIVERSE_STATUS["FUTURES"], "below_minimum")

    def test_failed_refresh_preserves_last_known_good_universe(self):
        si.MARKET_SYMBOLS["FUTURES"] = ["KEEP/USDT"]
        with patch.dict(
            si.EXCHANGES, {"FUTURES": FakeFuturesExchange(fail=True)}, clear=True
        ):
            selected = si.refresh_symbol_universe(force=True)
        self.assertEqual(selected["FUTURES"], ["KEEP/USDT"])

    def test_freshness_accepts_recent_closed_candles(self):
        interval = si.TIMEFRAME_MILLISECONDS["15m"]
        now_ms = 1_800_000_000_000
        candles = [[now_ms - (80 - i) * interval, 100, 101, 99, 100, 1000]
                   for i in range(80)]
        si.validate_candle_freshness(candles, "15m", now_ms)

    def test_freshness_rejects_stale_candles(self):
        interval = si.TIMEFRAME_MILLISECONDS["15m"]
        now_ms = 1_800_000_000_000
        candles = [[now_ms - (80 - i) * interval, 100, 101, 99, 100, 1000]
                   for i in range(80)]
        candles[-1][0] = now_ms - 4 * interval
        with self.assertRaisesRegex(ValueError, "Stale"):
            si.validate_candle_freshness(candles, "15m", now_ms)

    def test_freshness_rejects_future_dated_candles(self):
        interval = si.TIMEFRAME_MILLISECONDS["1h"]
        now_ms = 1_800_000_000_000
        with self.assertRaisesRegex(ValueError, "future-dated"):
            si.validate_candle_freshness(
                [[now_ms + interval, 100, 101, 99, 100, 1000]], "1h", now_ms
            )

    def test_failed_futures_refresh_can_retry(self):
        failed = FakeFuturesExchange(fail=True)
        with patch.dict(si.EXCHANGES, {"FUTURES": failed}, clear=True):
            si.refresh_symbol_universe(force=True)
        self.assertEqual(si._MARKET_UNIVERSE_LAST_REFRESH["FUTURES"], 0.0)
        recovered = FakeFuturesExchange()
        with patch.dict(si.EXCHANGES, {"FUTURES": recovered}, clear=True):
            selected = si.refresh_symbol_universe(force=False)
        self.assertGreaterEqual(len(selected["FUTURES"]), si.MIN_ELIGIBLE_COINS)
        self.assertEqual(si.MARKET_UNIVERSE_STATUS["FUTURES"], "ready")

    def test_scanner_config_rejects_changed_risk_policy(self):
        with patch.object(si, "RISK_PER_TRADE_PERCENT", 1.0):
            with self.assertRaisesRegex(RuntimeError, "0.5%"):
                scanner.validate_config()

    def test_scanner_config_requires_stale_candle_guard(self):
        with patch.object(si, "validate_candle_freshness", None):
            with self.assertRaisesRegex(RuntimeError, "validate_candle_freshness"):
                scanner.validate_config()

    def test_live_candle_fetch_rejects_inactive_futures_contract(self):
        now_ms = 1_800_000_000_000
        fake = FakeCandleExchange(now_ms, active=False)
        with patch.dict(si.EXCHANGES, {"FUTURES": fake}, clear=True):
            with self.assertRaisesRegex(ValueError, "active USDT market"):
                si.get_candles("FUTURES", "BTC/USDT", "15m")
        self.assertEqual(fake.calls, 0)

    def test_live_candle_fetch_returns_only_closed_fresh_candles(self):
        interval = si.TIMEFRAME_MILLISECONDS["15m"]
        now_ms = 1_800_000_000_000
        fake = FakeCandleExchange(now_ms, active=True)
        with patch.dict(si.EXCHANGES, {"FUTURES": fake}, clear=True):
            candles = si.get_candles("FUTURES", "BTC/USDT", "15m")
        self.assertEqual(len(candles), si.MIN_CANDLES)
        self.assertLess(candles[-1][0], fake.rows[-1][0])
        self.assertEqual(candles[-1][0] + interval, fake.rows[-1][0])

    def test_scanner_config_accepts_futures_only_universe(self):
        scanner.validate_config()

    def test_notification_ids_are_stable_and_within_android_integer_range(self):
        first = scanner.notification_id("FUTURES", "SOL/USDT")
        self.assertEqual(first, scanner.notification_id("FUTURES", "SOL/USDT"))
        self.assertGreaterEqual(first, 100000)
        self.assertLess(first, 1000000)


if __name__ == "__main__":
    unittest.main(verbosity=2)
