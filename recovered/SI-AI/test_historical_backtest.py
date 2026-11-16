import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import historical_data
import historical_backtest


def candles(count=240):
    return [
        [1_700_000_000_000 + i * 3_600_000, 100, 101, 99, 100, 1000]
        for i in range(count)
    ]


class HistoricalBacktestRunnerTests(unittest.TestCase):
    def _reports(self):
        chronological = {
            "out_of_sample": {
                "trade_count": 120,
                "net_pnl_usdt": 80.0,
                "expectancy_usdt": 0.66,
                "profit_factor": 1.35,
                "max_drawdown_percent": 8.0,
            },
            "out_of_sample_trades": [],
            "status": "OUT_OF_SAMPLE_PROFITABLE",
        }
        walk_forward = {
            "folds": [
                {"trade_count": 25, "net_pnl_usdt": 20.0},
                {"trade_count": 24, "net_pnl_usdt": 15.0},
                {"trade_count": 30, "net_pnl_usdt": 18.0},
            ],
            "status": "WALK_FORWARD_POSITIVE",
        }
        return chronological, walk_forward

    def test_runner_writes_reproducible_spot_report_and_gate(self):
        rows = candles()
        with tempfile.TemporaryDirectory() as directory:
            dataset_path = historical_data.save_dataset(
                "SPOT", "BTC/USDT", "1h", rows,
                output_path=Path(directory) / "data.json",
            )
            output_path = Path(directory) / "report.json"
            chronological, walk_forward = self._reports()
            with patch.object(
                historical_backtest.backtesting,
                "evaluate_chronological_validation",
                return_value=chronological,
            ), patch.object(
                historical_backtest.backtesting,
                "evaluate_walk_forward",
                return_value=walk_forward,
            ):
                report, saved_path = historical_backtest.run_dataset_backtest(
                    dataset_path, output_path=output_path
                )

            self.assertEqual(saved_path, output_path)
            self.assertEqual(report["profitability_gate"]["status"], "PASS")
            self.assertFalse(report["automatic_orders"])
            saved = json.loads(output_path.read_text(encoding="utf-8"))
            self.assertEqual(saved["dataset"]["data_sha256"], report["dataset"]["data_sha256"])

    def test_runner_keeps_futures_gate_inconclusive_without_required_models(self):
        rows = candles()
        with tempfile.TemporaryDirectory() as directory:
            dataset_path = historical_data.save_dataset(
                "FUTURES", "BTC/USDT", "1h", rows,
                output_path=Path(directory) / "data.json",
            )
            chronological, walk_forward = self._reports()
            with patch.object(
                historical_backtest.backtesting,
                "evaluate_chronological_validation",
                return_value=chronological,
            ), patch.object(
                historical_backtest.backtesting,
                "evaluate_walk_forward",
                return_value=walk_forward,
            ):
                report, _ = historical_backtest.run_dataset_backtest(
                    dataset_path, output_path=Path(directory) / "report.json"
                )
            self.assertEqual(report["profitability_gate"]["status"], "INCONCLUSIVE")

    def test_runner_records_insufficient_data_as_inconclusive(self):
        rows = candles(100)
        with tempfile.TemporaryDirectory() as directory:
            dataset_path = historical_data.save_dataset(
                "SPOT", "BTC/USDT", "1h", rows,
                output_path=Path(directory) / "data.json",
            )
            with patch.object(
                historical_backtest.backtesting,
                "evaluate_chronological_validation",
                side_effect=ValueError("not enough candles"),
            ), patch.object(
                historical_backtest.backtesting,
                "evaluate_walk_forward",
                side_effect=ValueError("not enough folds"),
            ):
                report, _ = historical_backtest.run_dataset_backtest(
                    dataset_path, output_path=Path(directory) / "report.json"
                )
            self.assertEqual(report["profitability_gate"]["status"], "INCONCLUSIVE")
            self.assertEqual(report["walk_forward"]["folds"], [])


if __name__ == "__main__":
    unittest.main()
