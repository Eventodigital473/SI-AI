import unittest

import pytest

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


    def test_futures_opposite_signal_closes_position_at_next_open(self):
        data = candles_with_bars(84)
        data[81] = [82, 99.0, 100.0, 98.5, 99.0, 1000.0]
        calls = 0

        def buy_then_reverse(market, symbol, timeframe, history):
            nonlocal calls
            calls += 1
            if calls == 1:
                return {"signal": "BUY", "stop_loss": 98.0, "take_profit": 104.0}
            if calls == 2:
                return {"signal": "SELL"}
            return {"signal": "WAIT"}

        result = backtesting.run_backtest(
            data, "FUTURES", "BTC/USDT", "1h",
            fee_rate=0.0, slippage_rate=0.0,
            max_holding_bars=3, signal_fn=buy_then_reverse,
        )
        self.assertEqual(len(result["trades"]), 1)
        self.assertEqual(result["trades"][0]["exit_reason"], "SIGNAL_REVERSAL")
        self.assertEqual(result["trades"][0]["exit_price"], 99.0)


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

    def test_funding_proxy_counts_utc_settlement_boundaries(self):
        period = 8 * 60 * 60 * 1000
        self.assertEqual(
            backtesting._funding_periods_between(
                period - 60_000, period + 60_000
            ),
            1,
        )
        self.assertEqual(
            backtesting._funding_periods_between(
                period + 60_000, 2 * period - 60_000
            ),
            0,
        )
        self.assertEqual(
            backtesting._funding_periods_between(period, 2 * period),
            1,
        )

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

    def test_timestamped_funding_uses_event_mark_price_and_direction(self):
        data = candles_with_bars(86)
        event = {"timestamp": 82, "funding_rate": 0.001, "mark_price": 100.0}
        calls = 0

        def one_buy_then_wait(market, symbol, timeframe, history):
            nonlocal calls
            calls += 1
            if calls == 1:
                return fixed_buy(market, symbol, timeframe, history)
            return {"signal": "WAIT"}

        result = backtesting.run_backtest(
            data, "FUTURES", "BTC/USDT", "15m",
            fee_rate=0.0, slippage_rate=0.0,
            max_holding_bars=3, signal_fn=one_buy_then_wait,
            funding_events=[event],
        )
        self.assertEqual(len(result["trades"]), 1)
        trade = result["trades"][0]
        self.assertEqual(trade["funding_event_count"], 1)
        self.assertAlmostEqual(
            trade["funding_cost_usdt"],
            trade["quantity"] * 100.0 * 0.001,
            places=7,
        )
        self.assertTrue(result["assumptions"]["historical_funding_series_included"])
        self.assertTrue(result["assumptions"]["funding_mark_price_exact"])
        self.assertFalse(result["assumptions"]["liquidation_modelled"])

    def test_intrabar_exit_candle_funding_event_is_ambiguous(self):
        data = candles_with_bars(86)
        data[81] = [82, 100.0, 105.0, 99.0, 100.0, 1000.0]
        event = {"timestamp": 83, "funding_rate": 0.001, "mark_price": 100.0}
        calls = 0

        def one_buy_then_wait(market, symbol, timeframe, history):
            nonlocal calls
            calls += 1
            return fixed_buy(market, symbol, timeframe, history) if calls == 1 else {"signal": "WAIT"}

        result = backtesting.run_backtest(
            data, "FUTURES", "BTC/USDT", "15m",
            fee_rate=0.0, slippage_rate=0.0,
            max_holding_bars=3, signal_fn=one_buy_then_wait,
            funding_events=[event],
        )
        self.assertEqual(len(result["trades"]), 1)
        trade = result["trades"][0]
        self.assertEqual(trade["exit_reason"], "TARGET")
        self.assertEqual(trade["funding_exit_timing"], "intrabar")
        self.assertEqual(trade["funding_event_count"], 1)
        self.assertEqual(trade["funding_boundary_ambiguities"], 1)
        self.assertGreater(trade["funding_cost_usdt"], 0)

    def test_timestamped_funding_rejects_double_counting_proxy(self):
        with self.assertRaisesRegex(ValueError, "not both"):
            backtesting.run_backtest(
                candles_with_bars(), "FUTURES", "BTC/USDT", "15m",
                funding_rate_per_8h=0.001,
                funding_events=[{"timestamp": 100, "funding_rate": 0.001, "mark_price": 100}],
            )

    def test_exact_entry_funding_boundary_is_flagged_and_not_credited(self):
        result = backtesting.funding_data.funding_cost_for_trade(
            [{"timestamp": 10, "funding_rate": -0.01, "mark_price": 100.0}],
            "LONG", 1.0, 10, 20,
        )
        self.assertEqual(result["funding_boundary_ambiguities"], 1)
        self.assertEqual(result["funding_cost_usdt"], 0.0)

    def test_report_contains_reproducible_data_hash_and_cost_assumptions(self):
        result = backtesting.run_backtest(
            candles_with_bars(), "FUTURES", "BTC/USDT", "15m",
            signal_fn=lambda *args: {"signal": "WAIT"},
        )
        self.assertEqual(len(result["data_sha256"]), 64)
        self.assertIn("fee_rate_per_side", result["assumptions"])
        self.assertFalse(result["assumptions"]["funding_costs_included"])
        self.assertIsNone(result["metrics"]["profit_factor"])


    def test_adverse_entry_gap_below_minimum_net_rr_is_rejected(self):
        data = candles_with_bars()
        # Signal is generated at 100, but the next-open fill gaps to 103.5.
        # The target at 104 is still above entry, but actual net R:R is far
        # below 2:1 and must not be accepted.
        data[80] = [81, 103.5, 104.0, 103.0, 103.5, 1000.0]
        result = backtesting.run_backtest(
            data, "FUTURES", "BTC/USDT", "15m",
            fee_rate=0.0, slippage_rate=0.0,
            max_holding_bars=1, signal_fn=fixed_buy,
        )
        self.assertEqual(result["trades"], [])
        self.assertEqual(result["metrics"]["trade_count"], 0)

    def test_actual_fill_net_rr_is_recorded_for_accepted_trade(self):
        data = candles_with_bars()
        # A favorable gap improves the actual reward/risk and remains valid.
        data[80] = [81, 99.5, 100.0, 99.0, 99.5, 1000.0]
        result = backtesting.run_backtest(
            data, "FUTURES", "BTC/USDT", "15m",
            fee_rate=0.0, slippage_rate=0.0,
            max_holding_bars=1, signal_fn=fixed_buy,
        )
        self.assertEqual(len(result["trades"]), 1)
        self.assertGreaterEqual(
            result["trades"][0]["actual_net_reward_risk"], 2.0
        )


    def test_chronological_report_preserves_holdout_assumptions(self):
        data = candles_with_bars(120)
        result = backtesting.evaluate_chronological_validation(
            data, "FUTURES", "BTC/USDT", "15m",
            train_fraction=0.70,
            signal_fn=lambda *args: {"signal": "WAIT"},
            fee_rate=0.001,
            slippage_rate=0.0005,
        )
        assumptions = result["assumptions"]
        self.assertEqual(assumptions["fee_rate_per_side"], 0.001)
        self.assertEqual(assumptions["slippage_rate_per_side"], 0.0005)
        self.assertIn("historical_funding_series_included", assumptions)
        self.assertFalse(assumptions["historical_funding_series_included"])
        self.assertFalse(assumptions["liquidation_modelled"])


if __name__ == "__main__":
    unittest.main(verbosity=2)


def test_backtesting_numeric_parser_rejects_booleans():
    with pytest.raises(ValueError, match="not boolean"):
        backtesting._number(True, "risk_percent")
    with pytest.raises(ValueError, match="not boolean"):
        backtesting._number(False, "initial_equity")
