import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock

import mark_price_data


HOUR = 60 * 60 * 1000


def row(ts, op=100, high=102, low=98, close=101):
    return [ts, str(op), str(high), str(low), str(close), "0",
            ts + HOUR - 1, "0", 60, "0", "0", "0"]


class MarkPriceDataTests(unittest.TestCase):
    def response(self, payload):
        result = Mock()
        result.json.return_value = payload
        result.raise_for_status.return_value = None
        return result

    def test_downloads_and_paginates_public_mark_price_klines(self):
        raw = [row(HOUR), row(2 * HOUR)]
        calls = []

        def getter(url, *, params, timeout):
            calls.append((url, dict(params), timeout))
            eligible = [item for item in raw if item[0] >= params["startTime"]]
            return self.response(eligible[:params["limit"]])

        candles = mark_price_data.download_mark_price_ohlcv(
            "BTC/USDT", "1h", HOUR, 3 * HOUR,
            http_get=getter, limit=1, now_ms=4 * HOUR,
        )
        self.assertEqual([item[0] for item in candles], [HOUR, 2 * HOUR])
        self.assertEqual(len(calls), 2)
        self.assertEqual(calls[0][0], mark_price_data.BASE_URL)
        self.assertEqual(calls[0][1]["symbol"], "BTCUSDT")
        self.assertEqual(calls[0][1]["interval"], "1h")
        self.assertEqual(calls[0][2], mark_price_data.REQUEST_TIMEOUT_SECONDS)
        self.assertEqual(candles[0][5], 0.0)

    def test_excludes_unclosed_mark_price_candle(self):
        candles = mark_price_data.download_mark_price_ohlcv(
            "BTC/USDT", "1h", HOUR, 3 * HOUR,
            http_get=lambda *a, **k: self.response([row(HOUR), row(2 * HOUR)]),
            now_ms=2 * HOUR + 10,
        )
        self.assertEqual([item[0] for item in candles], [HOUR])

    def test_rejects_noncanonical_symbol_and_bad_window(self):
        getter = lambda *a, **k: self.response([row(HOUR)])
        with self.assertRaises(ValueError):
            mark_price_data.download_mark_price_ohlcv(
                "btc/usdt", "1h", HOUR, 2 * HOUR, http_get=getter,
                now_ms=3 * HOUR,
            )
        with self.assertRaises(ValueError):
            mark_price_data.download_mark_price_ohlcv(
                "BTC/USDT", "1h", 2 * HOUR, HOUR, http_get=getter,
                now_ms=3 * HOUR,
            )

    def test_rejects_bad_close_time_and_invalid_ohlc(self):
        bad_close = row(HOUR)
        bad_close[6] += 1
        with self.assertRaisesRegex(ValueError, "close time mismatch"):
            mark_price_data.download_mark_price_ohlcv(
                "BTC/USDT", "1h", HOUR, 2 * HOUR,
                http_get=lambda *a, **k: self.response([bad_close]),
                now_ms=3 * HOUR,
            )
        bad_ohlc = row(HOUR, op=100, high=97, low=98, close=99)
        with self.assertRaisesRegex(ValueError, "OHLC relationship"):
            mark_price_data.download_mark_price_ohlcv(
                "BTC/USDT", "1h", HOUR, 2 * HOUR,
                http_get=lambda *a, **k: self.response([bad_ohlc]),
                now_ms=3 * HOUR,
            )

    def test_rejects_duplicate_or_unordered_rows(self):
        raw = [row(HOUR), row(HOUR)]
        with self.assertRaisesRegex(ValueError, "duplicate or unordered"):
            mark_price_data.download_mark_price_ohlcv(
                "BTC/USDT", "1h", HOUR, 2 * HOUR,
                http_get=lambda *a, **k: self.response(raw),
                now_ms=3 * HOUR,
            )

    def test_save_load_and_checksum_round_trip(self):
        candles = [
            [HOUR, 100.0, 102.0, 98.0, 101.0, 0.0],
            [2 * HOUR, 101.0, 103.0, 99.0, 102.0, 0.0],
        ]
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "mark.json"
            mark_price_data.save_mark_price_dataset(
                "BTC/USDT", "1h", candles, output_path=path,
                start_ms=HOUR, end_ms=3 * HOUR,
            )
            loaded = mark_price_data.load_mark_price_dataset(path)
            self.assertEqual(loaded["source"], "BINANCE_USDM_MARK_PRICE_KLINES")
            self.assertEqual(loaded["candles"], candles)
            self.assertEqual(
                loaded["data_sha256"],
                mark_price_data.mark_price_sha256(candles, "1h"),
            )

            payload = json.loads(path.read_text(encoding="utf-8"))
            payload["candles"][0][2] = 999
            path.write_text(json.dumps(payload), encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "integrity check"):
                mark_price_data.load_mark_price_dataset(path)

    def test_rejects_discontinuous_saved_dataset(self):
        candles = [
            [HOUR, 100.0, 102.0, 98.0, 101.0, 0.0],
            [3 * HOUR, 101.0, 103.0, 99.0, 102.0, 0.0],
        ]
        with tempfile.TemporaryDirectory() as directory:
            with self.assertRaisesRegex(ValueError, "continuous"):
                mark_price_data.save_mark_price_dataset(
                    "BTC/USDT", "1h", candles,
                    output_path=Path(directory) / "bad.json",
                )


if __name__ == "__main__":
    unittest.main()
