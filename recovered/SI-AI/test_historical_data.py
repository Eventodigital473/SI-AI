import json
import tempfile
import unittest
from pathlib import Path

import historical_data


class FakeExchange:
    def __init__(self, market, candles):
        self.market = market
        self.candles = candles
        self.calls = []
        self.markets = {"BTC/USDT:USDT": {
            "active": True, "quote": "USDT", "swap": True,
            "linear": True, "settle": "USDT",
        }}

    def load_markets(self):
        return self.markets

    def milliseconds(self):
        return 10**15

    def fetch_ohlcv(self, symbol, timeframe, since, limit):
        self.calls.append((symbol, timeframe, since, limit))
        return [row for row in self.candles if row[0] >= since][:limit]


def make_candles(count=7, start=1_700_000_000_000, interval=900_000):
    start = ((start + interval - 1) // interval) * interval
    return [
        [start + index * interval, 100, 101, 99, 100, 1000]
        for index in range(count)
    ]


class HistoricalDataTests(unittest.TestCase):
    def test_spot_market_is_rejected(self):
        rows = make_candles()
        exchange = FakeExchange("FUTURES", rows)
        with self.assertRaisesRegex(ValueError, "FUTURES only"):
            historical_data.download_ohlcv(
                "SPOT", "BTC/USDT", "15m",
                rows[0][0], rows[-1][0] + 900_000,
                exchange=exchange, now_ms=rows[-1][0] + 900_000,
            )

    def test_download_paginates_and_uses_exclusive_end(self):
        rows = make_candles()
        exchange = FakeExchange("FUTURES", rows)
        interval = 900_000
        result = historical_data.download_ohlcv(
            "FUTURES", "BTC/USDT", "15m",
            rows[0][0], rows[-1][0] + interval,
            exchange=exchange, limit=2,
            now_ms=rows[-1][0] + interval,
        )
        self.assertEqual(len(result), len(rows))
        self.assertEqual(result[0][0], rows[0][0])
        self.assertEqual(result[-1][0], rows[-1][0])
        self.assertGreaterEqual(len(exchange.calls), 3)

    def test_download_rejects_missing_first_or_last_candle(self):
        rows = make_candles()
        interval = 900_000
        for incomplete in (rows[1:], rows[:-1]):
            with self.subTest(first=incomplete[0][0], last=incomplete[-1][0]):
                exchange = FakeExchange("FUTURES", incomplete)
                with self.assertRaisesRegex(ValueError, "Incomplete historical 15m"):
                    historical_data.download_ohlcv(
                        "FUTURES", "BTC/USDT", "15m",
                        rows[0][0], rows[-1][0] + interval,
                        exchange=exchange, now_ms=rows[-1][0] + interval,
                    )

    def test_save_rejects_missing_edge_coverage(self):
        rows = make_candles()
        with tempfile.TemporaryDirectory() as directory:
            with self.assertRaisesRegex(ValueError, "Incomplete historical 15m"):
                historical_data.save_dataset(
                    "FUTURES", "BTC/USDT", "15m", rows[1:],
                    output_path=Path(directory) / "partial.json",
                    start_ms=rows[0][0],
                    end_ms=rows[-1][0] + 900_000,
                )

    def test_download_rejects_missing_intermediate_candle(self):
        rows = make_candles()
        gapped = rows[:3] + rows[4:]
        exchange = FakeExchange("FUTURES", gapped)
        with self.assertRaisesRegex(ValueError, "Missing or irregular 15m candle"):
            historical_data.download_ohlcv(
                "FUTURES", "BTC/USDT", "15m",
                rows[0][0], rows[-1][0] + 900_000,
                exchange=exchange, now_ms=rows[-1][0] + 900_000,
            )

    def test_save_rejects_missing_intermediate_candle(self):
        rows = make_candles()
        gapped = rows[:3] + rows[4:]
        with tempfile.TemporaryDirectory() as directory:
            with self.assertRaisesRegex(ValueError, "Missing or irregular 15m candle"):
                historical_data.save_dataset(
                    "FUTURES", "BTC/USDT", "15m", gapped,
                    output_path=Path(directory) / "gapped.json",
                )

    def test_continuity_validator_rejects_wrong_timeframe_spacing(self):
        rows = make_candles()
        with self.assertRaisesRegex(ValueError, "expected 3600000 ms"):
            historical_data.smc.validate_candle_continuity(rows, "1h")

    def test_incomplete_current_candle_is_excluded(self):
        rows = make_candles()
        exchange = FakeExchange("FUTURES", rows)
        interval = 900_000
        now_ms = rows[-1][0] + interval - 1
        result = historical_data.download_ohlcv(
            "FUTURES", "BTC/USDT", "15m",
            rows[0][0], rows[-1][0] + interval,
            exchange=exchange, limit=100,
            now_ms=now_ms,
        )
        self.assertEqual(len(result), len(rows) - 1)

    def test_download_excludes_candle_that_closes_after_requested_end(self):
        rows = make_candles()
        interval = 900_000
        end_ms = rows[-1][0] + interval - 1
        exchange = FakeExchange("FUTURES", rows)
        result = historical_data.download_ohlcv(
            "FUTURES", "BTC/USDT", "15m",
            rows[0][0], end_ms,
            exchange=exchange, now_ms=rows[-1][0] + interval,
        )
        self.assertEqual(len(result), len(rows) - 1)

    def test_save_rejects_dataset_outside_declared_time_window(self):
        rows = make_candles()
        with tempfile.TemporaryDirectory() as directory:
            with self.assertRaisesRegex(ValueError, "outside"):
                historical_data.save_dataset(
                    "FUTURES", "BTC/USDT", "15m", rows,
                    output_path=Path(directory) / "bad.json",
                    start_ms=rows[0][0],
                    end_ms=rows[-1][0] + 900_000 - 1,
                )

    def test_futures_symbol_resolves_to_usdt_settled_contract(self):
        rows = make_candles()
        exchange = FakeExchange("FUTURES", rows)
        result = historical_data.download_ohlcv(
            "FUTURES", "BTC/USDT", "15m",
            rows[0][0], rows[-1][0] + 900_000,
            exchange=exchange, now_ms=rows[-1][0] + 900_000,
        )
        self.assertEqual(len(result), len(rows))
        self.assertTrue(exchange.calls)
        self.assertEqual(exchange.calls[0][0], "BTC/USDT:USDT")

    def test_inactive_or_wrong_market_is_rejected(self):
        rows = make_candles()
        exchange = FakeExchange("FUTURES", rows)
        exchange.markets["BTC/USDT:USDT"]["active"] = None
        with self.assertRaisesRegex(ValueError, "active/inactive status"):
            historical_data.download_ohlcv(
                "FUTURES", "BTC/USDT", "15m",
                rows[0][0], rows[-1][0] + 900_000,
                exchange=exchange, now_ms=rows[-1][0] + 900_000,
            )

    def test_known_inactive_market_can_be_downloaded_for_historical_research(self):
        rows = make_candles()
        exchange = FakeExchange("FUTURES", rows)
        exchange.markets["BTC/USDT:USDT"]["active"] = False
        result = historical_data.download_ohlcv(
            "FUTURES", "BTC/USDT", "15m",
            rows[0][0], rows[-1][0] + 900_000,
            exchange=exchange, now_ms=rows[-1][0] + 900_000,
        )
        self.assertEqual(len(result), len(rows))

    def test_pagination_non_progress_is_rejected(self):
        rows = make_candles()
        exchange = FakeExchange("FUTURES", rows)
        exchange.fetch_ohlcv = lambda *args, **kwargs: rows[:2]
        with self.assertRaisesRegex(RuntimeError, "did not advance"):
            historical_data.download_ohlcv(
                "FUTURES", "BTC/USDT", "15m",
                rows[0][0], rows[-1][0] + 900_000,
                exchange=exchange, limit=2,
                now_ms=rows[-1][0] + 900_000,
            )

    def test_dataset_save_load_and_checksum_verification(self):
        rows = make_candles()
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "dataset.json"
            saved = historical_data.save_dataset(
                "FUTURES", "BTC/USDT", "15m", rows, output_path=path
            )
            loaded = historical_data.load_dataset(saved)
            self.assertEqual(loaded["candles"], rows)
            self.assertEqual(
                loaded["data_sha256"], historical_data.dataset_sha256(rows)
            )
            payload = json.loads(path.read_text(encoding="utf-8"))
            payload["candles"][0][5] = 1001.0
            path.write_text(json.dumps(payload), encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "SHA-256 mismatch"):
                historical_data.load_dataset(path)

    def test_malformed_candles_are_rejected(self):
        rows = make_candles()
        rows[2][2] = 50
        exchange = FakeExchange("FUTURES", rows)
        with self.assertRaisesRegex(ValueError, "OHLC relationship"):
            historical_data.download_ohlcv(
                "FUTURES", "BTC/USDT", "15m",
                rows[0][0], rows[-1][0] + 900_000,
                exchange=exchange, now_ms=rows[-1][0] + 900_000,
            )


if __name__ == "__main__":
    unittest.main()
