import unittest

from binance_high_leverage import build_paper_plan


def bracket(leverage=10, mmr=0.005, cap=1000000, cum=0):
    return {
        "notionalFloor": 0,
        "notionalCap": cap,
        "initialLeverage": leverage,
        "maintMarginRatio": mmr,
        "cum": cum,
    }


class BinanceHighLeveragePaperTests(unittest.TestCase):
    def test_builds_10_percent_wallet_risk_plan_with_bracket_max_leverage(self):
        plan = build_paper_plan(
            wallet_equity_usdt=1000, entry_price=100, stop_loss=98,
            side="BUY", leverage_brackets=[bracket(leverage=10)], bracket_snapshot_age_seconds=0,
            fee_rate=0, slippage_rate=0,
        )
        self.assertEqual(plan["risk_percent"], 10.0)
        self.assertAlmostEqual(plan["risk_budget_usdt"], 100.0)
        self.assertEqual(plan["maximum_bracket_leverage"], 10)
        self.assertAlmostEqual(plan["estimated_risk_usdt"], 100.0)
        self.assertLess(plan["estimated_liquidation_price"], 98 * 0.995)

    def test_rejects_maximum_leverage_when_liquidation_is_before_stop(self):
        with self.assertRaisesRegex(ValueError, "liquidation buffer"):
            build_paper_plan(
                wallet_equity_usdt=1000, entry_price=100, stop_loss=99,
                side="BUY", leverage_brackets=[bracket(leverage=100)], bracket_snapshot_age_seconds=0,
                fee_rate=0, slippage_rate=0,
            )

    def test_supports_short_side_when_liquidation_is_beyond_stop(self):
        plan = build_paper_plan(
            wallet_equity_usdt=1000, entry_price=100, stop_loss=102,
            side="SELL", leverage_brackets=[bracket(leverage=10)], bracket_snapshot_age_seconds=0,
            fee_rate=0, slippage_rate=0,
        )
        self.assertEqual(plan["side"], "SELL")
        self.assertGreater(plan["estimated_liquidation_price"], 102 * 1.005)

    def test_caps_notional_to_binance_bracket_ceiling(self):
        plan = build_paper_plan(
            wallet_equity_usdt=10000, entry_price=100, stop_loss=99,
            side="BUY", leverage_brackets=[bracket(leverage=10, cap=50000)], bracket_snapshot_age_seconds=0,
            fee_rate=0, slippage_rate=0,
        )
        self.assertAlmostEqual(plan["notional_usdt"], 50000)
        self.assertLess(plan["estimated_risk_usdt"], plan["risk_budget_usdt"])

    def test_requires_bracket_data(self):
        with self.assertRaisesRegex(ValueError, "brackets are required"):
            build_paper_plan(
                wallet_equity_usdt=1000, entry_price=100, stop_loss=98,
                side="BUY", leverage_brackets=[], bracket_snapshot_age_seconds=0,
            )

    def test_rejects_invalid_side_and_stop(self):
        args = dict(
            wallet_equity_usdt=1000, entry_price=100, stop_loss=98,
            leverage_brackets=[bracket()], bracket_snapshot_age_seconds=0,
        )
        with self.assertRaisesRegex(ValueError, "side must"):
            build_paper_plan(**args, side="WAIT")
        with self.assertRaisesRegex(ValueError, "wrong side"):
            build_paper_plan(**{**args, "stop_loss": 101}, side="BUY")

    def test_rejects_stale_bracket_snapshot(self):
        with self.assertRaisesRegex(ValueError, "stale or invalid"):
            build_paper_plan(
                wallet_equity_usdt=1000, entry_price=100, stop_loss=98,
                side="BUY", leverage_brackets=[bracket()],
                bracket_snapshot_age_seconds=61,
            )

    def test_rejects_malformed_bracket(self):
        with self.assertRaisesRegex(ValueError, "maintenance margin"):
            build_paper_plan(
                wallet_equity_usdt=1000, entry_price=100, stop_loss=98,
                side="BUY", bracket_snapshot_age_seconds=0, leverage_brackets=[{
                    "notionalFloor": 0, "notionalCap": 100000,
                    "initialLeverage": 10,
                }],
            )


if __name__ == "__main__":
    unittest.main()
