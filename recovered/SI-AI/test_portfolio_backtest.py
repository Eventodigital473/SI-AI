import unittest

import portfolio_backtest


def make_trade(symbol, entry_ts, exit_ts, *, win=True, side="LONG", stop=99.0, rank=0):
    return {
        "symbol": symbol,
        "_symbol_rank": rank,
        "side": side,
        "entry_timestamp": entry_ts,
        "exit_timestamp": exit_ts,
        "entry_price": 100.0,
        "exit_price": 101.0 if win else 99.5,
        "stop_loss": stop,
        "take_profit": 102.0,
    }


class SpotPortfolioReplayTests(unittest.TestCase):
    def test_shared_wallet_skips_overlapping_cross_symbol_trades(self):
        trades = [
            make_trade("AAA/USDT", 1, 3, rank=0),
            make_trade("BBB/USDT", 2, 4, rank=1),
            make_trade("CCC/USDT", 4, 5, rank=2),
        ]
        result = portfolio_backtest.simulate_spot_portfolio(trades)
        self.assertEqual([t["symbol"] for t in result["trades"]], ["AAA/USDT", "CCC/USDT"])
        self.assertEqual(result["skipped_overlapping_trades"], 1)
        self.assertEqual(result["max_concurrent_positions"], 1)
        self.assertGreater(result["metrics"]["ending_equity_usdt"], 100.0)

    def test_position_size_obeys_shared_equity_notional_cap(self):
        trade = make_trade("AAA/USDT", 1, 2, stop=99.99)
        result = portfolio_backtest.simulate_spot_portfolio([trade])
        sized = result["trades"][0]
        self.assertLessEqual(sized["entry_notional_usdt"], 20.0 + 1e-8)
        self.assertLessEqual(sized["quantity"], 0.2 + 1e-8)

    def test_spot_portfolio_rejects_short_trades(self):
        result = portfolio_backtest.simulate_spot_portfolio([
            make_trade("AAA/USDT", 1, 2, side="SHORT")
        ])
        self.assertEqual(result["metrics"]["trade_count"], 0)
        self.assertEqual(result["skipped_invalid_trades"], 1)

    def test_empty_trade_sample_is_inconclusive_metrics_not_an_error(self):
        result = portfolio_backtest.simulate_spot_portfolio([])
        self.assertEqual(result["metrics"]["trade_count"], 0)
        self.assertEqual(result["metrics"]["net_pnl_usdt"], 0.0)
        self.assertFalse(result["automatic_orders"])

    def test_invalid_timestamp_and_price_rows_are_skipped(self):
        invalid = make_trade("AAA/USDT", 0, 2)
        invalid["entry_price"] = float("nan")
        result = portfolio_backtest.simulate_spot_portfolio([invalid])
        self.assertEqual(result["metrics"]["trade_count"], 0)
        self.assertEqual(result["skipped_invalid_trades"], 1)


if __name__ == "__main__":
    unittest.main()
