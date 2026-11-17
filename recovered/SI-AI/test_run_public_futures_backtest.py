import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import run_public_futures_backtest as runner


class FakeExchange:
    def milliseconds(self):
        return 1_800_000_000_000


class PublicFuturesBacktestRunnerTests(unittest.TestCase):
    def test_runner_downloads_all_production_timeframes_and_keeps_gate_inconclusive(self):
        candles = [
            [1_700_000_000_000 + i * 900_000, 100.0, 101.0, 99.0, 100.0, 10.0]
            for i in range(100)
        ]
        verified = {
            "candles": candles,
            "data_sha256": "a" * 64,
        }
        report = {
            "dataset": {"combined_data_sha256": "b" * 64},
            "chronological_validation": {"out_of_sample": {"trade_count": 0}},
            "walk_forward": {"folds": []},
            "profitability_gate": {"status": "INCONCLUSIVE"},
        }
        with tempfile.TemporaryDirectory() as directory, patch.object(
            runner, "REPORT_DIR", Path(directory)
        ), patch.dict(
            runner.smc.EXCHANGES, {"FUTURES": FakeExchange()}, clear=True
        ), patch.object(
            runner.historical_data, "download_ohlcv", return_value=candles
        ) as download, patch.object(
            runner.historical_data, "save_dataset",
            side_effect=lambda *args, **kwargs: Path(directory) / f"{args[2]}.json",
        ), patch.object(
            runner.historical_data, "load_dataset", return_value=verified
        ), patch.object(
            runner.historical_data, "dataset_sha256", return_value="a" * 64
        ), patch.object(
            runner.historical_backtest, "run_dataset_backtest",
            return_value=(report, Path(directory) / "report.json"),
        ):
            summary, summary_path = runner.run_public_futures_backtest(
                symbols=["BTC/USDT"], days=120
            )

        self.assertEqual(download.call_count, 4)
        self.assertEqual(summary["market"], "FUTURES")
        self.assertEqual(summary["certification"], "INCONCLUSIVE")
        self.assertEqual(summary["results"][0]["profitability_gate"], "INCONCLUSIVE")
        self.assertTrue(summary_path.name.startswith("futures_backtest_summary_"))
        self.assertFalse(summary["automatic_orders"])

    def test_runner_rejects_non_futures_symbols_and_spot(self):
        with self.assertRaisesRegex(ValueError, "canonical USDT Futures"):
            runner._validate_symbols(["BTC/BUSD"])
        with self.assertRaisesRegex(ValueError, "canonical USDT Futures"):
            runner._validate_symbols(["BTC/USDT:USDT"])

    def test_runner_rejects_short_history(self):
        with self.assertRaisesRegex(ValueError, "120 and 730"):
            runner.run_public_futures_backtest(symbols=["BTC/USDT"], days=90)


if __name__ == "__main__":
    unittest.main()
