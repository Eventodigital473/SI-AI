import unittest

from binance_high_leverage import build_paper_plan


class RetiredHighLeveragePlannerTests(unittest.TestCase):
    def test_legacy_high_leverage_planner_is_disabled(self):
        with self.assertRaisesRegex(RuntimeError, "0.5% risk"):
            build_paper_plan(
                wallet_equity_usdt=1000,
                entry_price=100,
                stop_loss=98,
                side="BUY",
                leverage_brackets=[{
                    "notionalFloor": 0,
                    "notionalCap": 1000000,
                    "initialLeverage": 100,
                    "maintMarginRatio": 0.005,
                    "cum": 0,
                }],
                bracket_snapshot_age_seconds=0,
            )


if __name__ == "__main__":
    unittest.main()
