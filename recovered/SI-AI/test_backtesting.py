import unittest

import backtesting


def candles_with_bars(count=82):
    rows = []
    for i in range(count):
        rows.append([i + 1, 100.0, 101.0, 99.0, 100.0, 1000.0])
    return rows


def fixed_buy(market, symbol, timeframe, history):
    return {"signal": "BUY", "stop_loss": 98.0, "take_profit": 104.0}


class BacktestingTests(unittest.TestCase):
    def test_entry_is_next_candle_open_and_same_bar_stop_wins(self):
        data = candles_with_bars()
        data[80] = [81, 100.0, 105.0, 97.0, 100.0, 1000.0]
        result = backtesting.run_backtest(
            data, "FUTURES", "BTC/USDT", "15m",
            fee_rate=0.0, slippage_rate=0.0,
            max_holding_bars=1, signal_fn=fixed_buy,
        )
        self.assertEqual(len(result["trades"]), 1)
        trade = result["trades"][0]
        self.assertEqual(trade["signal_timestamp"], 80)
        self.assertEqual(trade["entry_timestamp"], 81)
        self.assertEqual(trade["exit_reason"], "STOP")
        self.assertLess(trade["net_pnl_usdt"], 0)
        self.assertEqual(result["assumptions"]["same_bar_stop_and_target"], "stop first (conservative)")
        self.assertFalse(result["automatic_orders"])

    def test_stop_gap_fills_at_worse_open_not_stop_trigger(self):
        data = candles_with_bars()
        data[81] = [82, 95.0, 96.0, 94.0, 95.0, 1000.0]
        result = backtesting.run_backtest(
            data, "FUTURES", "BTC/USDT", "15m",
            fee_rate=0.0, slippage_rate=0.0,
            max_holding_bars=2, signal_fn=fixed_buy,
        )
        trade = result["trades"][0]
        self.assertEqual(trade["exit_reason"], "STOP_GAP")
        self.assertEqual(trade["exit_price"], 95.0)
        self.assertLess(trade["exit_price"], trade["stop_loss"])

    def test_signal_callback_never_receives_future_candles(self):
        data = candles_with_bars(84)
        seen = []

        def callback(market, symbol, timeframe, history):
            seen.append(history[-1][0])
            return {"signal": "WAIT"}

        backtesting.run_backtest(
            data, "FUTURES", "BTC/USDT", "15m",
            signal_fn=callback, start_index=80,
        )
        self.assertEqual(seen[0], 80)
        self.assertLess(seen[0], data[80][0] + 1)

    def test_spot_short_signals_are_not_opened(self):
        data = candles_with_bars()

        def short_signal(*args):
            return {"signal": "SELL", "stop_loss": 102.0, "take_profit": 96.0}

        result = backtesting.run_backtest(
            data, "SPOT", "BTC/USDT", "15m",
            signal_fn=short_signal, max_holding_bars=1,
        )
        self.assertEqual(result["metrics"]["trade_count"], 0)
        self.assertEqual(result["status"], "INCONCLUSIVE")

    def test_chronological_holdout_starts_signals_in_oos_period(self):
        data = candles_with_bars(120)
        def callback(market, symbol, timeframe, history):
            return {"signal": "BUY", "stop_loss": 98.0, "take_profit": 104.0}

        result = backtesting.evaluate_chronological_validation(
            data, "FUTURES", "BTC/USDT", "15m",
            train_fraction=0.70, signal_fn=callback,
            max_holding_bars=1, fee_rate=0.0, slippage_rate=0.0,
        )
        split = result["split_index"]
        self.assertEqual(result["split_timestamp"], data[split][0])
        self.assertEqual(
            result["out_of_sample_trades"][0]["signal_timestamp"],
            data[split - 1][0],
        )
        self.assertEqual(
            result["out_of_sample_trades"][0]["entry_timestamp"],
            data[split][0],
        )


    def test_walk_forward_uses_multiple_sequential_oos_folds(self):
        result = backtesting.evaluate_walk_forward(
            candles_with_bars(180), "FUTURES", "BTC/USDT", "15m",
            folds=3, signal_fn=lambda *args: {"signal": "WAIT"},
        )
        self.assertEqual(len(result["folds"]), 3)
        self.assertEqual(result["status"], "INCONCLUSIVE")

    def test_optional_funding_rate_is_reported_and_deducted(self):
        data = candles_with_bars()
        for row in data:
            row[0] *= 28_800_000
        result = backtesting.run_backtest(
            data, "FUTURES", "BTC/USDT", "15m",
            fee_rate=0.0, slippage_rate=0.0,
            max_holding_bars=2, signal_fn=fixed_buy,
            funding_rate_per_8h=0.001,
        )
        self.assertTrue(result["assumptions"]["funding_costs_included"])
        self.assertGreater(result["trades"][0]["funding_cost_usdt"], 0)

    def test_rejects_bad_candle_order_and_risk(self):
        data = candles_with_bars()
        data[10][0] = data[9][0]
        with self.assertRaises(ValueError):
            backtesting.run_backtest(data, "FUTURES", "BTC/USDT", "15m")
        with self.assertRaises(ValueError):
            backtesting.run_backtest(
                candles_with_bars(), "FUTURES", "BTC/USDT", "15m",
                risk_percent=8.0,
            )

    def test_report_contains_reproducible_data_hash_and_cost_assumptions(self):
        result = backtesting.run_backtest(
            candles_with_bars(), "FUTURES", "BTC/USDT", "15m",
            signal_fn=lambda *args: {"signal": "WAIT"},
        )
        self.assertEqual(len(result["data_sha256"]), 64)
        self.assertIn("fee_rate_per_side", result["assumptions"])
        self.assertFalse(result["assumptions"]["funding_costs_included"])
        self.assertIsNone(result["metrics"]["profit_factor"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
