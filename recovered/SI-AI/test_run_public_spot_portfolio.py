import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import SI_AI_smc as smc
import run_public_spot_portfolio as runner


def make_candles(count=100):
    return [
        [1_700_000_000_000 + index * 60_000, 100.0, 102.0, 99.0, 101.0, 10.0]
        for index in range(count)
    ]


class PublicSpotPortfolioRunnerTests(unittest.TestCase):
    def test_runner_uses_spot_only_dynamic_universe_and_shared_portfolio(self):
        symbols = ["AAA/USDT", "BBB/USDT"]
        candles = make_candles()
        verified = {
            "candles": candles,
            "candle_count": len(candles),
            "data_sha256": "a" * 64,
            "start_ms": candles[0][0],
            "end_ms": candles[-1][0] + 60_000,
        }
        fake_report = {
            "dataset": {
                "combined_data_sha256": "b" * 64,
            },
            "chronological_validation": {
                "out_of_sample": {"trade_count": 100},
                "status": "OUT_OF_SAMPLE_PROFITABLE",
                "skipped_overlapping_trades": 3,
            },
            "walk_forward": {
                "metrics": {"trade_count": 60},
                "status": "WALK_FORWARD_POSITIVE",
            },
            "profitability_gate": {"status": "PASS", "checks": []},
            "limitations": ["current-universe survivorship bias"],
        }

        with tempfile.TemporaryDirectory() as directory:
            old_cwd = os.getcwd()
            os.chdir(directory)
            self.addCleanup(os.chdir, old_cwd)
            with patch.object(smc, "MIN_ELIGIBLE_COINS", 2), patch.object(
                smc, "TARGET_UNIVERSE_SIZE", 2
            ), patch.object(
                runner.smc, "refresh_symbol_universe",
                side_effect=lambda force=True: (
                    self.assertEqual(runner.smc.MARKETS, ["SPOT"]),
                    self.assertEqual(
                        runner.smc.EXCHANGES["SPOT"].urls["api"]["public"],
                        runner.PUBLIC_SPOT_DATA_URL,
                    ),
                    {"SPOT": symbols},
                )[-1],
            ), patch.object(
                runner.historical_data, "download_ohlcv", return_value=candles
            ) as download, patch.object(
                runner.historical_data, "save_dataset",
                side_effect=lambda market, symbol, timeframe, *args, **kwargs:
                    Path(directory) / f"{symbol.replace('/', '-')}_{timeframe}.json",
            ), patch.object(
                runner.historical_data, "load_dataset", return_value=verified
            ), patch.object(
                runner.historical_data, "dataset_sha256", return_value="a" * 64
            ), patch.object(
                runner.historical_backtest, "run_multi_symbol_portfolio_backtest",
                return_value=(fake_report, Path(directory) / "portfolio.json"),
            ) as portfolio:
                summary = runner.collect_and_backtest(days=180, symbol_limit=2)

        self.assertEqual(summary["verified_symbol_count"], 2)
        self.assertEqual(summary["profitability_gate"], "PASS")
        self.assertEqual(len(summary["dataset_manifest"]), 8)
        self.assertEqual(download.call_count, 8)
        self.assertEqual(portfolio.call_args.kwargs["initial_equity"], smc.PAPER_EQUITY_USDT)
        self.assertFalse(summary["automatic_orders"])

    def test_runner_rejects_short_history_window(self):
        with self.assertRaises(ValueError):
            runner.collect_and_backtest(days=90, symbol_limit=15)

    def test_runner_requires_minimum_symbol_limit(self):
        with patch.object(smc, "MIN_ELIGIBLE_COINS", 15):
            with self.assertRaises(ValueError):
                runner.collect_and_backtest(days=180, symbol_limit=10)


if __name__ == "__main__":
    unittest.main()
