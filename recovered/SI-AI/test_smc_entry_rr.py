import unittest
from unittest.mock import patch

import SI_AI_smc as si


class SMCEntryAndRewardRiskTests(unittest.TestCase):
    def test_bullish_bos_needs_only_a_confirmed_swing_high(self):
        candles = [
            [1, 100.0, 101.0, 99.0, 100.0, 10.0],
            [2, 104.0, 107.0, 103.0, 106.0, 10.0],
        ]
        structure = {"swing_highs": [(0, 105.0)], "swing_lows": []}
        self.assertEqual(si.detect_bos(candles, structure), "Bullish")

    def test_bearish_bos_needs_only_a_confirmed_swing_low(self):
        candles = [
            [1, 100.0, 101.0, 99.0, 100.0, 10.0],
            [2, 96.0, 97.0, 93.0, 94.0, 10.0],
        ]
        structure = {"swing_highs": [], "swing_lows": [(0, 95.0)]}
        self.assertEqual(si.detect_bos(candles, structure), "Bearish")

    def test_net_reward_risk_uses_both_sides_costs_for_long(self):
        rr = si.calculate_net_reward_risk(
            100.0, 98.0, 106.0, "LONG", "FUTURES"
        )
        self.assertGreaterEqual(rr, si.MIN_REWARD_RISK)

    def test_net_reward_risk_uses_both_sides_costs_for_short(self):
        rr = si.calculate_net_reward_risk(
            100.0, 102.0, 94.0, "SHORT", "FUTURES"
        )
        self.assertGreaterEqual(rr, si.MIN_REWARD_RISK)

    def test_net_reward_risk_rejects_wrong_side_levels(self):
        with self.assertRaises(ValueError):
            si.calculate_net_reward_risk(
                100.0, 101.0, 106.0, "LONG", "FUTURES"
            )

    def test_choch_and_bos_are_not_counted_as_two_events(self):
        candles = [
            [i, 100.0, 101.0, 99.0, 100.0, 100.0]
            for i in range(si.MIN_CANDLES)
        ]
        structure = {
            "trend": "Bearish",
            "swing_lows": [(10, 98.0), (20, 97.0)],
            "swing_highs": [(10, 102.0), (20, 101.0)],
        }
        with (
            patch.object(si, "calculate_atr", return_value=2.0),
            patch.object(si, "detect_market_structure", return_value=structure),
            patch.object(si, "detect_bos", return_value="Bullish"),
            patch.object(si, "detect_choch", return_value="Bullish"),
            patch.object(si, "detect_liquidity", return_value={"sweep": "None"}),
            patch.object(si, "detect_fvg", return_value={
                "bullish_fvg": False, "bearish_fvg": False
            }),
            patch.object(si, "analyze_volume", return_value={"ratio": 1.0}),
            patch.object(si, "detect_order_block", return_value={
                "bullish_ob": False, "bearish_ob": False
            }),
            patch.object(si, "ema", return_value=100.0),
        ):
            result = si.analyze_candles(
                "FUTURES", "BTC/USDT", "1h", candles
            )
        # Bearish structure (-2) plus one bullish CHOCH (+2.5), not
        # a second independent +2 BOS contribution.
        self.assertEqual(result["score"], 0.5)


if __name__ == "__main__":
    unittest.main(verbosity=2)
