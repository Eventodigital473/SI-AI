import unittest
from contextlib import ExitStack
from unittest.mock import patch
import SI_AI_smc as si


def run_analysis(market, trend, bos, atr=2.0,
                 price=100.0, swing_low=98.0,
                 swing_high=102.0):
    candles = [
        [i, price, price + 1, price - 1, price, 100]
        for i in range(si.MIN_CANDLES)
    ]

    structure = {
        "trend": trend,
        "swing_lows": [(10, swing_low)],
        "swing_highs": [(10, swing_high)],
    }

    with ExitStack() as stack:
        stack.enter_context(patch.object(si, "calculate_atr", return_value=atr))
        stack.enter_context(patch.object(si, "detect_market_structure", return_value=structure))
        stack.enter_context(patch.object(si, "detect_bos", return_value=bos))
        stack.enter_context(patch.object(si, "detect_choch", return_value=None))
        stack.enter_context(patch.object(si, "detect_liquidity", return_value={"sweep": "None"}))
        stack.enter_context(patch.object(si, "detect_fvg", return_value={
            "bullish_fvg": False, "bearish_fvg": False
        }))
        stack.enter_context(patch.object(si, "analyze_volume", return_value={"ratio": 1.0}))
        stack.enter_context(patch.object(si, "detect_order_block", return_value={
            "bullish_ob": False, "bearish_ob": False
        }))
        stack.enter_context(patch.object(si, "ema", return_value=100.0))

        return si.analyze_candles(
            market, "BTC/USDT", "15m", candles
        )


class RiskManagementTests(unittest.TestCase):

    def test_buy_position_sizing(self):
        result = run_analysis("FUTURES", "Bullish", "Bullish")
        self.assertEqual(result["signal"], "BUY")
        self.assertAlmostEqual(result["stop_loss"], 98.0)
        self.assertAlmostEqual(result["take_profit"], 106.0)
        self.assertLess(result["paper_quantity"], 2.5)
        self.assertLessEqual(result["paper_total_risk_usdt"], 0.5)
        self.assertLessEqual(result["paper_notional_usdt"], 20.0)

    def test_futures_sell_position_sizing(self):
        result = run_analysis("FUTURES", "Bearish", "Bearish")
        self.assertEqual(result["signal"], "SELL")
        self.assertAlmostEqual(result["stop_loss"], 102.0)
        self.assertAlmostEqual(result["take_profit"], 94.0)
        self.assertLess(result["paper_quantity"], 2.5)
        self.assertAlmostEqual(result["paper_total_risk_usdt"], 5.0, places=6)

    def test_spot_sell_is_exit_not_short(self):
        result = run_analysis("SPOT", "Bearish", "Bearish")
        self.assertEqual(result["signal"], "SELL/EXIT")
        self.assertIsNone(result["stop_loss"])
        self.assertIsNone(result["take_profit"])
        self.assertIsNone(result["paper_quantity"])
        self.assertIsNone(result["paper_notional_usdt"])
        self.assertIsNone(result["paper_risk_usdt"])
        self.assertIsNone(result["paper_total_risk_usdt"])

    def test_wallet_and_margin_policy_is_twenty_percent(self):
        result = run_analysis("FUTURES", "Bullish", "Bullish")
        self.assertEqual(si.PAPER_EQUITY_USDT, 100.0)
        self.assertEqual(si.MARGIN_ALLOCATION_PERCENT, 20.0)
        self.assertEqual(si.RECOMMENDED_FUTURES_LEVERAGE, 1.0)
        self.assertAlmostEqual(result["paper_margin_budget_usdt"], 20.0)
        self.assertAlmostEqual(result["paper_margin_required_usdt"], result["paper_notional_usdt"])
        self.assertEqual(result["recommended_leverage"], 1.0)

    def test_buy_reward_risk_ratio(self):
        result = run_analysis("FUTURES", "Bullish", "Bullish")
        self.assertGreaterEqual(result["reward_risk"], si.MIN_REWARD_RISK)

    def test_sell_reward_risk_ratio(self):
        result = run_analysis("FUTURES", "Bearish", "Bearish")
        self.assertGreaterEqual(result["reward_risk"], si.MIN_REWARD_RISK)

    def test_maximum_notional_cap(self):
        result = run_analysis(
            "FUTURES", "Bullish", "Bullish",
            atr=0.1, swing_low=99.99
        )
        self.assertEqual(result["signal"], "BUY")
        self.assertAlmostEqual(result["paper_notional_usdt"], 20.0)
        self.assertAlmostEqual(result["paper_quantity"], 0.2)
        self.assertLessEqual(
            result["paper_total_risk_usdt"],
            si.PAPER_EQUITY_USDT * si.RISK_PER_TRADE_PERCENT / 100.0
        )

    def test_wait_signal_has_no_position(self):
        result = run_analysis("FUTURES", "Neutral", "None")
        self.assertEqual(result["signal"], "WAIT")
        self.assertIsNone(result["paper_quantity"])
        self.assertIsNone(result["paper_notional_usdt"])
        self.assertIsNone(result["stop_loss"])
        self.assertIsNone(result["take_profit"])

    def test_invalid_atr_blocks_entry(self):
        result = run_analysis("FUTURES", "Bullish", "Bullish", atr=0)
        self.assertEqual(result["signal"], "WAIT")
        self.assertIsNone(result["paper_quantity"])
        self.assertIsNone(result["stop_loss"])
        self.assertIsNone(result["take_profit"])

    def test_zero_price_is_rejected(self):
        with self.assertRaises(ValueError):
            run_analysis("FUTURES", "Bullish", "Bullish", price=0)

    def test_fee_and_slippage_are_reported(self):
        result = run_analysis("FUTURES", "Bullish", "Bullish")
        self.assertGreater(result["paper_estimated_fees_usdt"], 0)
        self.assertGreater(result["paper_estimated_slippage_usdt"], 0)

    def test_net_reward_risk_meets_minimum(self):
        result = run_analysis("FUTURES", "Bullish", "Bullish")
        self.assertGreaterEqual(
            result["paper_estimated_net_reward_usdt"],
            result["paper_total_risk_usdt"] * si.MIN_REWARD_RISK
        )

    def test_insufficient_candles_are_rejected(self):
        candles = [
            [i, 100, 101, 99, 100, 100]
            for i in range(si.MIN_CANDLES - 1)
        ]
        with self.assertRaises(ValueError):
            si.validate_analysis_inputs(
                "FUTURES", "BTC/USDT", "15m", candles
            )

    def test_invalid_ohlc_is_rejected(self):
        candles = [
            [i, 100, 101, 99, 100, 100]
            for i in range(si.MIN_CANDLES)
        ]
        candles[10] = [10, 100, 98, 99, 100, 100]
        with self.assertRaises(ValueError):
            si.validate_analysis_inputs(
                "FUTURES", "BTC/USDT", "15m", candles
            )

    def test_non_numeric_atr_blocks_entry(self):
        result = run_analysis("FUTURES", "Bullish", "Bullish", atr=None)
        self.assertEqual(result["signal"], "WAIT")
        self.assertIsNone(result["paper_quantity"])
        self.assertIsNone(result["stop_loss"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
