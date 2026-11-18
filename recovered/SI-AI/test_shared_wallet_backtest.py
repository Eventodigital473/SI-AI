import unittest

from shared_wallet_backtest import HOUR_MS, simulate_shared_wallet


class SharedWalletTests(unittest.TestCase):
    def setUp(self):
        self.t0 = 1_800_000_000_000
        self.marks = {
            "BTC/USDT": [
                [self.t0, 100, 102, 98, 100, 0],
                [self.t0 + HOUR_MS, 100, 103, 97, 100, 0],
                [self.t0 + 2 * HOUR_MS, 100, 102, 98, 100, 0],
            ],
            "ETH/USDT": [
                [self.t0, 50, 51, 49, 50, 0],
                [self.t0 + HOUR_MS, 50, 52, 48, 50, 0],
                [self.t0 + 2 * HOUR_MS, 50, 51, 49, 50, 0],
            ],
        }

    def trade(self, symbol="BTC/USDT", entry=None, exit=None, side="LONG", pnl=1.0):
        entry = self.t0 if entry is None else entry
        exit = self.t0 + HOUR_MS if exit is None else exit
        price = 100.0 if symbol == "BTC/USDT" else 50.0
        stop = price - 1 if side == "LONG" else price + 1
        return {
            "symbol": symbol, "side": side,
            "entry_timestamp": entry, "exit_timestamp": exit,
            "entry_price": price, "stop_loss": stop,
            "quantity": 0.1, "net_pnl_usdt": pnl,
            "funding_exit_timing": "intrabar",
        }

    def test_single_trade_is_sized_and_closed(self):
        result = simulate_shared_wallet([self.trade()], self.marks)
        self.assertEqual(result["candidate_trade_count"], 1)
        self.assertEqual(result["executed_trade_count"], 1)
        self.assertEqual(result["capacity_skipped_trade_count"], 0)
        self.assertFalse(result["funding_included"])
        self.assertFalse(result["liquidation_modelled"])
        self.assertFalse(result["automatic_orders"])

    def test_simultaneous_entries_share_one_margin_cap_pro_rata(self):
        trades = [self.trade("BTC/USDT"), self.trade("ETH/USDT")]
        result = simulate_shared_wallet(trades, self.marks)
        self.assertEqual(result["executed_trade_count"], 2)
        completed = result["completed_trades"]
        self.assertAlmostEqual(
            completed[0]["allocated_quantity"] * 100
            + completed[1]["allocated_quantity"] * 50,
            20.0,
            places=6,
        )

    def test_later_entry_cannot_use_margin_before_same_hour_exit(self):
        trades = [
            self.trade("BTC/USDT", entry=self.t0, exit=self.t0 + HOUR_MS),
            self.trade("ETH/USDT", entry=self.t0 + HOUR_MS, exit=self.t0 + 2 * HOUR_MS),
        ]
        result = simulate_shared_wallet(trades, self.marks)
        self.assertEqual(result["executed_trade_count"], 1)
        self.assertEqual(result["capacity_skipped_trade_count"], 1)
        self.assertEqual(result["candidate_trade_count"], 2)

    def test_open_exit_releases_margin_before_same_timestamp_entry(self):
        first = self.trade("BTC/USDT", entry=self.t0, exit=self.t0 + HOUR_MS)
        first["funding_exit_timing"] = "open"
        second = self.trade("ETH/USDT", entry=self.t0 + HOUR_MS, exit=self.t0 + 2 * HOUR_MS)
        result = simulate_shared_wallet([first, second], self.marks)
        self.assertEqual(result["executed_trade_count"], 2)
        self.assertEqual(result["capacity_skipped_trade_count"], 0)

    def test_open_exit_does_not_mark_the_following_candle(self):
        first = self.trade("BTC/USDT", entry=self.t0, exit=self.t0 + HOUR_MS)
        first["funding_exit_timing"] = "open"
        self.marks["BTC/USDT"][1][3] = 1.0
        result = simulate_shared_wallet([first], self.marks)
        self.assertLess(result["max_drawdown_percent"], 5.0)

    def test_missing_mark_candle_fails_closed(self):
        with self.assertRaisesRegex(ValueError, "missing BTC/USDT mark candle"):
            simulate_shared_wallet(
                [self.trade(exit=self.t0 + 2 * HOUR_MS)],
                {"BTC/USDT": self.marks["BTC/USDT"][:1]},
            )

    def test_overlapping_same_symbol_trades_rejected(self):
        trades = [
            self.trade(entry=self.t0, exit=self.t0 + 2 * HOUR_MS),
            self.trade(entry=self.t0 + HOUR_MS, exit=self.t0 + 2 * HOUR_MS),
        ]
        with self.assertRaisesRegex(ValueError, "overlapping trades"):
            simulate_shared_wallet(trades, self.marks)

    def test_same_symbol_intrabar_exit_entry_boundary_is_rejected_as_ambiguous(self):
        trades = [
            self.trade(entry=self.t0, exit=self.t0 + HOUR_MS),
            self.trade(entry=self.t0 + HOUR_MS, exit=self.t0 + 2 * HOUR_MS),
        ]
        with self.assertRaisesRegex(ValueError, "overlapping trades"):
            simulate_shared_wallet(trades, self.marks)

    def test_same_symbol_open_exit_entry_boundary_is_allowed(self):
        first = self.trade(entry=self.t0, exit=self.t0 + HOUR_MS)
        first["funding_exit_timing"] = "open"
        second = self.trade(entry=self.t0 + HOUR_MS, exit=self.t0 + 2 * HOUR_MS)
        result = simulate_shared_wallet([first, second], self.marks)
        self.assertEqual(result["executed_trade_count"], 2)

    def test_bad_stop_direction_rejected(self):
        trade = self.trade(side="LONG")
        trade["stop_loss"] = 101
        with self.assertRaisesRegex(ValueError, "wrong side"):
            simulate_shared_wallet([trade], self.marks)

    def test_short_position_uses_adverse_high_for_drawdown(self):
        result = simulate_shared_wallet([self.trade(side="SHORT", pnl=-1)], self.marks)
        self.assertGreater(result["max_drawdown_percent"], 0)

    def test_accounting_includes_skipped_and_executed_trades(self):
        result = simulate_shared_wallet(
            [self.trade(), self.trade("ETH/USDT")],
            self.marks,
            margin_allocation_percent=0.001,
        )
        self.assertEqual(
            result["executed_trade_count"] + result["capacity_skipped_trade_count"],
            result["candidate_trade_count"],
        )


if __name__ == "__main__":
    unittest.main()
