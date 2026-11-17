import json
import tempfile
import unittest
from pathlib import Path

import funding_data


class FakeExchange:
    def __init__(self, events):
        self.events = events
        self.markets = {"BTC/USDT:USDT": {
            "active": True, "quote": "USDT", "swap": True,
            "linear": True, "settle": "USDT",
        }}
        self.calls = []

    def load_markets(self):
        return self.markets

    def fetch_funding_rate_history(self, symbol, since=None, limit=None, params=None):
        self.calls.append((symbol, since, limit, params))
        return [
            row for row in self.events
            if since <= row["timestamp"] <= params["until"]
        ][:limit]


def event(timestamp, rate, mark="100"):
    return {
        "symbol": "BTCUSDT",
        "timestamp": timestamp,
        "fundingRate": rate,
        "info": {
            "symbol": "BTCUSDT",
            "fundingTime": timestamp,
            "fundingRate": str(rate),
            "markPrice": mark,
            "rateType": "Regular",
        },
    }


class FundingDataTests(unittest.TestCase):
    def test_download_paginates_and_preserves_exact_settlement_mark_price(self):
        rows = [event(1000, "0.001", "101"), event(2000, "-0.002", "102"),
                event(3000, "0.0005", "103")]
        exchange = FakeExchange(rows)
        result = funding_data.download_funding_history(
            "FUTURES", "BTC/USDT", 1000, 4000,
            exchange=exchange, limit=2,
        )
        self.assertEqual(len(result), 3)
        self.assertEqual([item["timestamp"] for item in result], [1000, 2000, 3000])
        self.assertEqual(result[0]["mark_price"], 101.0)
        self.assertEqual(len(exchange.calls), 2)
        self.assertEqual(exchange.calls[1][1], 2001)

    def test_spot_and_non_usdt_contracts_are_rejected(self):
        exchange = FakeExchange([event(1000, "0.001")])
        with self.assertRaisesRegex(ValueError, "FUTURES only"):
            funding_data.download_funding_history("SPOT", "BTC/USDT", 1000, 2000, exchange=exchange)
        with self.assertRaisesRegex(ValueError, "BASE/USDT"):
            funding_data.download_funding_history("FUTURES", "BTC/BUSD", 1000, 2000, exchange=exchange)

    def test_wrong_contract_symbol_is_rejected(self):
        wrong = event(1000, "0.001")
        wrong["info"]["symbol"] = "ETHUSDT"
        with self.assertRaisesRegex(ValueError, "does not match"):
            funding_data.download_funding_history(
                "FUTURES", "BTC/USDT", 1000, 2000,
                exchange=FakeExchange([wrong]),
            )

    def test_normalized_series_rejects_duplicate_and_nonpositive_mark_price(self):
        duplicate = [
            {"timestamp": 1000, "funding_rate": 0.001, "mark_price": 100},
            {"timestamp": 1000, "funding_rate": 0.001, "mark_price": 100},
        ]
        with self.assertRaisesRegex(ValueError, "strictly increasing"):
            funding_data.validate_normalized_funding_events(duplicate)
        with self.assertRaisesRegex(ValueError, "outside supported bounds"):
            funding_data.validate_normalized_funding_events([
                {"timestamp": 1000, "funding_rate": 0.001, "mark_price": 0}
            ])

    def test_missing_raw_mark_price_is_rejected(self):
        row = event(1000, "0.001")
        del row["info"]["markPrice"]
        with self.assertRaisesRegex(ValueError, "markPrice"):
            funding_data.normalize_funding_event(row)

    def test_timestamp_mismatch_is_rejected(self):
        row = event(1000, "0.001")
        row["info"]["fundingTime"] = 1001
        with self.assertRaisesRegex(ValueError, "timestamps disagree"):
            funding_data.normalize_funding_event(row)

    def test_unordered_and_duplicate_events_are_rejected(self):
        rows = [event(2000, "0.001"), event(1000, "0.001")]
        with self.assertRaisesRegex(ValueError, "unordered"):
            funding_data.download_funding_history(
                "FUTURES", "BTC/USDT", 1000, 3000,
                exchange=FakeExchange(rows), limit=10,
            )

    def test_positive_and_negative_funding_signs_for_long_and_short(self):
        events = [{"timestamp": 2000, "funding_rate": 0.01, "mark_price": 100.0}]
        long_cost = funding_data.funding_cost_for_trade(events, "LONG", 2, 1000, 3000)
        short_cost = funding_data.funding_cost_for_trade(events, "SHORT", 2, 1000, 3000)
        self.assertAlmostEqual(long_cost["funding_cost_usdt"], 2.0)
        self.assertAlmostEqual(short_cost["funding_cost_usdt"], -2.0)
        events[0]["funding_rate"] = -0.01
        self.assertAlmostEqual(
            funding_data.funding_cost_for_trade(events, "LONG", 2, 1000, 3000)["funding_cost_usdt"],
            -2.0,
        )
        self.assertAlmostEqual(
            funding_data.funding_cost_for_trade(events, "SHORT", 2, 1000, 3000)["funding_cost_usdt"],
            2.0,
        )

    def test_trade_interval_includes_settlement_and_flags_exact_boundary_ties(self):
        events = [
            {"timestamp": 1000, "funding_rate": 0.01, "mark_price": 100.0},
            {"timestamp": 2000, "funding_rate": 0.01, "mark_price": 100.0},
            {"timestamp": 3000, "funding_rate": 0.01, "mark_price": 100.0},
            {"timestamp": 4000, "funding_rate": 0.01, "mark_price": 100.0},
        ]
        result = funding_data.funding_cost_for_trade(events, "LONG", 1, 1000, 3000)
        self.assertEqual(result["funding_event_count"], 3)
        self.assertEqual(result["funding_boundary_ambiguities"], 2)
        self.assertAlmostEqual(result["funding_cost_usdt"], 2.0)

    def test_dataset_round_trip_and_checksum_tampering(self):
        events = [{"timestamp": 1000, "funding_rate": 0.001, "mark_price": 101.0}]
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "funding.json"
            funding_data.save_funding_dataset(
                "FUTURES", "BTC/USDT", events, 1000, 2000, path
            )
            loaded = funding_data.load_funding_dataset(path)
            self.assertEqual(loaded["events"], events)
            payload = json.loads(path.read_text())
            payload["events"][0]["mark_price"] = 102.0
            path.write_text(json.dumps(payload))
            with self.assertRaisesRegex(ValueError, "SHA-256 mismatch"):
                funding_data.load_funding_dataset(path)


if __name__ == "__main__":
    unittest.main(verbosity=2)
