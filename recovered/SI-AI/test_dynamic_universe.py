import unittest
from unittest.mock import patch

import SI_AI_smc as si
import si_ai_scanner as scanner


class FakeExchange:
    def __init__(self, market, count=110, fail=False):
        self.market = market
        self.count = count
        self.fail = fail
        self.markets = {}
        self._tickers = {}

        for index in range(count):
            base = f"COIN{index:03d}"
            self._add(base, 50_000_000.0 - index * 1000.0)

        # Named assets are eligible but intentionally rank below the top 100.
        self._add("BNB", 20_000_000.0)
        self._add("SOL", 19_000_000.0)
        self._add("BTC", 18_000_000.0)
        self._add("ETH", 17_000_000.0)

        # These must be excluded by base/volume/spread rules.
        self._add("USDC", 90_000_000.0)
        self._add("TOKENUP", 90_000_000.0)
        self._add("TOKEN3L", 90_000_000.0)
        self._add("LOWVOL", 1_000_000.0)
        self._add("WIDE", 90_000_000.0, ask=1.02)
        self._add("INACTIVE", 90_000_000.0)
        self.markets[
            f"INACTIVE/USDT:USDT" if market == "FUTURES" else "INACTIVE/USDT"
        ]["active"] = False
        self._add("UNKNOWNACTIVE", 90_000_000.0)
        self.markets[
            f"UNKNOWNACTIVE/USDT:USDT" if market == "FUTURES" else "UNKNOWNACTIVE/USDT"
        ]["active"] = None
        self._add("WBNB", 90_000_000.0)

    def _add(self, base, volume, ask=1.0005):
        canonical = f"{base}/USDT"
        exchange_symbol = (
            f"{canonical}:USDT" if self.market == "FUTURES" else canonical
        )
        metadata = {
            "symbol": exchange_symbol,
            "base": base,
            "quote": "USDT",
            "active": True,
            "spot": self.market == "SPOT",
            "swap": self.market == "FUTURES",
            "linear": self.market == "FUTURES",
            "settle": "USDT" if self.market == "FUTURES" else None,
        }
        self.markets[exchange_symbol] = metadata
        self._tickers[exchange_symbol] = {
            "quoteVolume": volume,
            "bid": 1.0,
            "ask": ask,
        }

    def load_markets(self):
        if self.fail:
            raise RuntimeError("simulated exchange outage")
        return self.markets

    def fetch_tickers(self):
        if self.fail:
            raise RuntimeError("simulated ticker outage")
        return self._tickers


class FakeCandleExchange:
    def __init__(self, market, now_ms, active=True):
        self.now_ms = now_ms
        self.calls = 0
        self.markets = {}
        symbol = "BTC/USDT" if market == "SPOT" else "BTC/USDT:USDT"
        self.markets[symbol] = {
            "active": active,
            "quote": "USDT",
            "spot": market == "SPOT",
            "swap": market == "FUTURES",
            "linear": market == "FUTURES",
            "settle": "USDT" if market == "FUTURES" else None,
        }
        interval = si.TIMEFRAME_MILLISECONDS["15m"]
        current_open = now_ms - (now_ms % interval)
        self.rows = [
            [
                current_open - (80 - index) * interval,
                100.0, 101.0, 99.0, 100.0, 1000.0
            ]
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
            market: list(symbols)
            for market, symbols in si.MARKET_SYMBOLS.items()
        }
        self.original_symbols = list(si.SYMBOLS)
        self.original_refresh = si._UNIVERSE_LAST_REFRESH
        self.original_market_refresh = dict(si._MARKET_UNIVERSE_LAST_REFRESH)

    def tearDown(self):
        si.MARKET_SYMBOLS.clear()
        si.MARKET_SYMBOLS.update(self.original_market_symbols)
        si.SYMBOLS = self.original_symbols
        si._UNIVERSE_LAST_REFRESH = self.original_refresh
        si._MARKET_UNIVERSE_LAST_REFRESH.clear()
        si._MARKET_UNIVERSE_LAST_REFRESH.update(self.original_market_refresh)

    def test_selects_target_50_liquid_coins_per_market_and_prioritizes_core_assets(self):
        fake_futures = FakeExchange("FUTURES")
        fake_spot = FakeExchange("SPOT")

        with patch.dict(
            si.EXCHANGES,
            {"FUTURES": fake_futures, "SPOT": fake_spot},
            clear=False,
        ):
            selected = si.refresh_symbol_universe(force=True)

        for market in si.MARKETS:
            symbols = selected[market]
            self.assertGreaterEqual(len(symbols), si.MIN_ELIGIBLE_COINS)
            self.assertLessEqual(len(symbols), si.TARGET_UNIVERSE_SIZE)
            self.assertEqual(len(symbols), si.TARGET_UNIVERSE_SIZE)
            self.assertIn("BTC/USDT", symbols)
            self.assertIn("ETH/USDT", symbols)
            self.assertIn("SOL/USDT", symbols)
            self.assertIn("BNB/USDT", symbols)
            self.assertNotIn("USDC/USDT", symbols)
            self.assertNotIn("TOKENUP/USDT", symbols)
            self.assertNotIn("TOKEN3L/USDT", symbols)
            self.assertNotIn("LOWVOL/USDT", symbols)
            self.assertNotIn("WIDE/USDT", symbols)
            self.assertNotIn("INACTIVE/USDT", symbols)
            self.assertNotIn("UNKNOWNACTIVE/USDT", symbols)
            self.assertNotIn("WBNB/USDT", symbols)

    def test_does_not_fabricate_coins_to_reach_minimum(self):
        fake_futures = FakeExchange("FUTURES", count=10)
        fake_spot = FakeExchange("SPOT", count=10)
        # Keep only ten valid candidates; remove named preferred assets.
        for fake in (fake_futures, fake_spot):
            for base in ("BNB", "SOL", "BTC", "ETH"):
                symbol = f"{base}/USDT"
                exchange_symbol = (
                    f"{symbol}:USDT" if fake.market == "FUTURES" else symbol
                )
                fake.markets.pop(exchange_symbol, None)
                fake._tickers.pop(exchange_symbol, None)

        with patch.dict(
            si.EXCHANGES,
            {"FUTURES": fake_futures, "SPOT": fake_spot},
            clear=False,
        ):
            selected = si.refresh_symbol_universe(force=True)

        self.assertEqual(len(selected["FUTURES"]), 10)
        self.assertEqual(len(selected["SPOT"]), 10)
        self.assertLess(len(selected["SPOT"]), si.MIN_ELIGIBLE_COINS)

    def test_failed_refresh_preserves_last_known_good_universe(self):
        si.MARKET_SYMBOLS["FUTURES"] = ["KEEP/USDT"]
        si.MARKET_SYMBOLS["SPOT"] = ["KEEP/USDT"]
        with patch.dict(
            si.EXCHANGES,
            {
                "FUTURES": FakeExchange("FUTURES", fail=True),
                "SPOT": FakeExchange("SPOT", fail=True),
            },
            clear=False,
        ):
            selected = si.refresh_symbol_universe(force=True)

        self.assertEqual(selected["FUTURES"], ["KEEP/USDT"])
        self.assertEqual(selected["SPOT"], ["KEEP/USDT"])

    def test_freshness_accepts_recent_closed_candles(self):
        interval = si.TIMEFRAME_MILLISECONDS["15m"]
        now_ms = 1_800_000_000_000
        candles = [
            [now_ms - (80 - index) * interval, 100, 101, 99, 100, 1000]
            for index in range(80)
        ]
        si.validate_candle_freshness(candles, "15m", now_ms)

    def test_freshness_rejects_stale_candles(self):
        interval = si.TIMEFRAME_MILLISECONDS["15m"]
        now_ms = 1_800_000_000_000
        candles = [
            [now_ms - (80 - index) * interval, 100, 101, 99, 100, 1000]
            for index in range(80)
        ]
        candles[-1][0] = now_ms - 4 * interval
        with self.assertRaisesRegex(ValueError, "Stale"):
            si.validate_candle_freshness(candles, "15m", now_ms)

    def test_freshness_rejects_future_dated_candles(self):
        interval = si.TIMEFRAME_MILLISECONDS["1h"]
        now_ms = 1_800_000_000_000
        candles = [[now_ms + interval, 100, 101, 99, 100, 1000]]
        with self.assertRaisesRegex(ValueError, "future-dated"):
            si.validate_candle_freshness(candles, "1h", now_ms)

    def test_failed_market_retries_without_waiting_for_other_market_refresh(self):
        failed_futures = FakeExchange("FUTURES", fail=True)
        good_spot = FakeExchange("SPOT")
        with patch.dict(
            si.EXCHANGES,
            {"FUTURES": failed_futures, "SPOT": good_spot},
            clear=False,
        ):
            si.refresh_symbol_universe(force=True)
            self.assertEqual(si._MARKET_UNIVERSE_LAST_REFRESH["FUTURES"], 0.0)
            self.assertGreater(si._MARKET_UNIVERSE_LAST_REFRESH["SPOT"], 0.0)

            recovered_futures = FakeExchange("FUTURES")
            with patch.dict(
                si.EXCHANGES,
                {"FUTURES": recovered_futures, "SPOT": good_spot},
                clear=False,
            ):
                selected = si.refresh_symbol_universe(force=False)

        self.assertGreaterEqual(
            len(selected["FUTURES"]), si.MIN_ELIGIBLE_COINS
        )
        self.assertEqual(
            si.MARKET_UNIVERSE_STATUS["FUTURES"], "ready"
        )

    def test_scanner_config_rejects_changed_risk_policy(self):
        with patch.object(si, "RISK_PER_TRADE_PERCENT", 1.0):
            with self.assertRaisesRegex(RuntimeError, "0.5%"):
                scanner.validate_config()

    def test_scanner_config_requires_stale_candle_guard(self):
        with patch.object(si, "validate_candle_freshness", None):
            with self.assertRaisesRegex(RuntimeError, "validate_candle_freshness"):
                scanner.validate_config()

    def test_live_candle_fetch_rejects_inactive_market_metadata(self):
        now_ms = 1_800_000_000_000
        fake = FakeCandleExchange("SPOT", now_ms, active=False)
        with patch.dict(si.EXCHANGES, {"SPOT": fake}, clear=False):
            with self.assertRaisesRegex(ValueError, "active USDT market"):
                si.get_candles("SPOT", "BTC/USDT", "15m")
        self.assertEqual(fake.calls, 0)

    def test_live_candle_fetch_returns_only_closed_fresh_candles(self):
        interval = si.TIMEFRAME_MILLISECONDS["15m"]
        now_ms = 1_800_000_000_000
        fake = FakeCandleExchange("SPOT", now_ms, active=True)
        with patch.dict(si.EXCHANGES, {"SPOT": fake}, clear=False):
            candles = si.get_candles("SPOT", "BTC/USDT", "15m")
        self.assertEqual(len(candles), si.MIN_CANDLES)
        self.assertLess(candles[-1][0], fake.rows[-1][0])
        self.assertEqual(candles[-1][0] + interval, fake.rows[-1][0])

    def test_scanner_config_accepts_dynamic_coin_universe(self):
        scanner.validate_config()

    def test_notification_ids_are_stable_and_within_android_integer_range(self):
        first = scanner.notification_id("FUTURES", "SOL/USDT")
        second = scanner.notification_id("FUTURES", "SOL/USDT")
        self.assertEqual(first, second)
        self.assertGreaterEqual(first, 100000)
        self.assertLess(first, 1000000)


if __name__ == "__main__":
    unittest.main(verbosity=2)
