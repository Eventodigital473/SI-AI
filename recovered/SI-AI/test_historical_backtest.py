import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import historical_data
import historical_backtest


BASE = 1_700_000_000_000


def candle_rows(count, start, interval):
    return [
        [start + index * interval, 100, 101, 99, 100, 1000]
        for index in range(count)
    ]


def make_dataset_payloads(market="SPOT", symbol="BTC/USDT", counts_override=None):
    intervals = {
        "15m": 900_000,
        "1h": 3_600_000,
        "4h": 14_400_000,
        "1d": 86_400_000,
    }
    starts = {
        "15m": BASE + 79 * intervals["1d"],
        "1h": BASE + 80 * intervals["1d"],
        "4h": BASE + 60 * intervals["1d"],
        "1d": BASE,
    }
    counts = counts_override or {"15m": 2400, "1h": 240, "4h": 240, "1d": 240}
    datasets = {}
    for timeframe, interval in intervals.items():
        rows = candle_rows(counts[timeframe], starts[timeframe], interval)
        datasets[timeframe] = {
            "market": market,
            "symbol": symbol,
            "timeframe": timeframe,
            "candles": rows,
            "candle_count": len(rows),
            "data_sha256": historical_data.dataset_sha256(rows),
            "start_ms": rows[0][0],
            "end_ms": rows[-1][0] + interval,
        }
    return datasets


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

    def _save_datasets(self, directory, market="SPOT", counts=None):
        payloads = make_dataset_payloads(market=market)
        paths = []
        for timeframe, dataset in payloads.items():
            if counts and timeframe in counts:
                interval = historical_data.smc.TIMEFRAME_MILLISECONDS[timeframe]
                rows = dataset["candles"][:counts[timeframe]]
            else:
                rows = dataset["candles"]
            path = Path(directory) / f"{timeframe}.json"
            historical_data.save_dataset(
                market, "BTC/USDT", timeframe, rows, output_path=path
            )
            paths.append(path)
        return paths

    def test_runner_writes_production_multitimeframe_report_and_gate(self):
        with tempfile.TemporaryDirectory() as directory:
            dataset_paths = self._save_datasets(directory)
            output_path = Path(directory) / "report.json"
            chronological, walk_forward = self._reports()
            with patch.object(
                historical_backtest.backtesting,
                "evaluate_chronological_validation",
                return_value=chronological,
            ) as mocked_chrono, patch.object(
                historical_backtest.backtesting,
                "evaluate_walk_forward",
                return_value=walk_forward,
            ) as mocked_walk:
                report, saved_path = historical_backtest.run_dataset_backtest(
                    dataset_paths, output_path=output_path
                )

            self.assertEqual(saved_path, output_path)
            self.assertEqual(report["profitability_gate"]["status"], "PASS")
            self.assertEqual(
                report["strategy"].split(":")[0],
                "Production scanner confluence",
            )
            self.assertEqual(set(report["dataset"]["timeframes"]), {"15m", "1h", "4h", "1d"})
            self.assertIsNotNone(mocked_chrono.call_args.kwargs["signal_fn"])
            self.assertIsNotNone(mocked_walk.call_args.kwargs["signal_fn"])
            self.assertFalse(report["automatic_orders"])
            saved = json.loads(output_path.read_text(encoding="utf-8"))
            self.assertEqual(
                saved["dataset"]["combined_data_sha256"],
                report["dataset"]["combined_data_sha256"],
            )

    def test_production_callback_uses_only_timeframes_closed_by_signal_time(self):
        datasets = make_dataset_payloads()
        primary = datasets["1h"]["candles"]
        history = primary[:100]
        signal_close = history[-1][0] + historical_backtest.smc.TIMEFRAME_MILLISECONDS["1h"]
        observed = {}

        def fake_analyze(market, symbol, timeframe, candles):
            observed[timeframe] = candles[-1][0] + historical_backtest.smc.TIMEFRAME_MILLISECONDS[timeframe]
            return {
                "timeframe": timeframe,
                "signal": "BUY",
                "price": 100.0,
                "stop_loss": 98.0,
                "take_profit": 104.0,
                "reward_risk": 2.0,
            }

        callback = historical_backtest.build_production_signal_callback(datasets)
        with patch.object(historical_backtest.smc, "analyze_candles", side_effect=fake_analyze), patch.object(
            historical_backtest.smc, "combine_timeframes",
            return_value={"overall_signal": "BUY"},
        ), patch.object(
            historical_backtest.scanner, "confirm_signal", return_value="BUY"
        ):
            result = callback("SPOT", "BTC/USDT", "1h", history)

        self.assertEqual(result["signal"], "BUY")
        self.assertEqual(set(observed), {"15m", "1h", "4h", "1d"})
        self.assertTrue(all(close_time <= signal_close for close_time in observed.values()))


    def test_production_callback_matches_live_scanner_250_candle_cap(self):
        datasets = make_dataset_payloads(
            counts_override={"15m": 4800, "1h": 500, "4h": 500, "1d": 500}
        )
        history = datasets["1h"]["candles"][:400]
        signal_close = history[-1][0] + historical_backtest.smc.TIMEFRAME_MILLISECONDS["1h"]
        observed = {}

        def fake_analyze(market, symbol, timeframe, candles):
            observed[timeframe] = (
                len(candles),
                candles[-1][0] + historical_backtest.smc.TIMEFRAME_MILLISECONDS[timeframe],
            )
            return {
                "timeframe": timeframe,
                "signal": "BUY",
                "price": 100.0,
                "stop_loss": 98.0,
                "take_profit": 104.0,
                "reward_risk": 2.0,
            }

        callback = historical_backtest.build_production_signal_callback(datasets)
        with patch.object(historical_backtest.smc, "analyze_candles", side_effect=fake_analyze), patch.object(
            historical_backtest.smc, "combine_timeframes",
            return_value={"overall_signal": "BUY"},
        ), patch.object(
            historical_backtest.scanner, "confirm_signal", return_value="BUY"
        ):
            result = callback("SPOT", "BTC/USDT", "1h", history)

        self.assertEqual(result["signal"], "BUY")
        self.assertEqual(set(observed), {"15m", "1h", "4h", "1d"})
        self.assertTrue(all(length <= historical_backtest.smc.CANDLE_LIMIT for length, _ in observed.values()))
        self.assertEqual(observed["1h"][0], historical_backtest.smc.CANDLE_LIMIT)
        self.assertTrue(all(close_time <= signal_close for _, close_time in observed.values()))

    def test_production_callback_waits_for_all_timeframe_warmups(self):
        datasets = make_dataset_payloads()
        datasets["1d"]["candles"] = datasets["1d"]["candles"][:20]
        callback = historical_backtest.build_production_signal_callback(datasets)
        result = callback(
            "SPOT", "BTC/USDT", "1h", datasets["1h"]["candles"][:100]
        )
        self.assertEqual(result["signal"], "WAIT")

    def test_runner_keeps_futures_gate_inconclusive_without_required_models(self):
        with tempfile.TemporaryDirectory() as directory:
            dataset_paths = self._save_datasets(directory, market="FUTURES")
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
                    dataset_paths, output_path=Path(directory) / "report.json"
                )
            self.assertEqual(report["profitability_gate"]["status"], "INCONCLUSIVE")

    def test_runner_records_insufficient_data_as_inconclusive(self):
        with tempfile.TemporaryDirectory() as directory:
            dataset_paths = self._save_datasets(directory, counts={"1h": 100})
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
                    dataset_paths, output_path=Path(directory) / "report.json"
                )
            self.assertEqual(report["profitability_gate"]["status"], "INCONCLUSIVE")
            self.assertEqual(report["walk_forward"]["folds"], [])


    def test_multi_symbol_portfolio_aggregates_oos_and_walk_forward_trades(self):
        def trade(symbol, entry_ts, *, win=True, rank=0):
            return {
                "symbol": symbol,
                "side": "LONG",
                "entry_timestamp": entry_ts,
                "exit_timestamp": entry_ts + 0.5,
                "entry_price": 100.0,
                "exit_price": 101.0 if win else 99.5,
                "stop_loss": 99.0,
                "take_profit": 102.0,
                "_symbol_rank": rank,
            }

        def fake_report(symbol, rank):
            oos = [
                trade(symbol, 2000 + i * 2 + rank, win=(i % 10 < 7), rank=rank)
                for i in range(50)
            ]
            folds = []
            for fold_index in range(3):
                fold_trades = [
                    trade(
                        symbol,
                        3000 + fold_index * 100 + i * 2 + rank,
                        win=(i % 10 < 7),
                        rank=rank,
                    )
                    for i in range(10)
                ]
                folds.append({
                    "fold": fold_index + 1,
                    "test_start_timestamp": 3000 + fold_index * 100,
                    "test_end_timestamp": 3100 + fold_index * 100,
                    "trade_count": len(fold_trades),
                    "net_pnl_usdt": 1.0,
                    "ending_equity_usdt": 101.0,
                    "trades": fold_trades,
                })
            return {
                "dataset": {
                    "market": "SPOT",
                    "symbol": symbol,
                    "combined_data_sha256": ("a" if rank == 0 else "b") * 64,
                    "timeframes": {},
                },
                "chronological_validation": {
                    "split_timestamp": 1500,
                    "out_of_sample_trades": oos,
                },
                "walk_forward": {"folds": folds},
                "profitability_gate": {"status": "INCONCLUSIVE"},
            }

        reports = [fake_report("AAA/USDT", 0), fake_report("BBB/USDT", 1)]
        with tempfile.TemporaryDirectory() as directory, patch.object(
            historical_backtest.smc, "MIN_ELIGIBLE_COINS", 2
        ), patch.object(
            historical_backtest, "run_dataset_backtest",
            side_effect=[
                (reports[0], Path(directory) / "AAA.json"),
                (reports[1], Path(directory) / "BBB.json"),
            ],
        ):
            report, saved_path = historical_backtest.run_multi_symbol_portfolio_backtest(
                {"AAA/USDT": ["a"], "BBB/USDT": ["b"]},
                output_path=Path(directory) / "portfolio.json",
            )

        self.assertEqual(report["dataset"]["symbol_count"], 2)
        self.assertEqual(report["chronological_validation"]["out_of_sample"]["trade_count"], 100)
        self.assertEqual(
            [fold["trade_count"] for fold in report["walk_forward"]["folds"]],
            [20, 20, 20],
        )
        self.assertEqual(report["profitability_gate"]["status"], "PASS")
        self.assertEqual(report["portfolio_assumptions"]["max_concurrent_positions"], 1)
        self.assertFalse(report["automatic_orders"])

    def test_runner_requires_all_four_timeframes(self):
        with tempfile.TemporaryDirectory() as directory:
            dataset_paths = self._save_datasets(directory)
            with self.assertRaisesRegex(ValueError, "All production timeframes"):
                historical_backtest.run_dataset_backtest(dataset_paths[:3])


if __name__ == "__main__":
    unittest.main()
