import unittest
from datetime import datetime, timezone, timedelta

from liquidation_model import (
    calculate_isolated_liquidation_price,
    validate_bracket_snapshot,
)


NOW = datetime(2026, 11, 18, 12, 0, tzinfo=timezone.utc)


def snapshot(*, symbol="BTC/USDT", retrieved_at=None, tiers=None):
    return {
        "source": "BINANCE_USDM_LEVERAGE_BRACKET",
        "symbol": symbol,
        "retrieved_at": (retrieved_at or NOW).isoformat(),
        "tiers": tiers or [{
            "notional_floor": 0,
            "notional_cap": None,
            "maintenance_margin_rate": 0.01,
            "maintenance_amount": 0,
            "max_leverage": 20,
        }],
    }


class LiquidationModelTests(unittest.TestCase):
    def test_long_isolated_liquidation_price_matches_usdm_formula(self):
        result = calculate_isolated_liquidation_price(
            symbol="BTC/USDT", side="LONG", quantity=1, entry_price=100,
            isolated_wallet_balance=10, leverage=10,
            bracket_snapshot=snapshot(), now=NOW,
        )
        self.assertEqual(result["status"], "CALCULATED_ISOLATED_ESTIMATE")
        self.assertAlmostEqual(result["liquidation_price"], 90 / 0.99, places=10)
        self.assertEqual(result["margin_mode"], "ISOLATED")
        self.assertEqual(result["position_mode"], "ONE_WAY")
        self.assertFalse(result["automatic_orders"])

    def test_short_isolated_liquidation_price_matches_usdm_formula(self):
        result = calculate_isolated_liquidation_price(
            symbol="BTC/USDT", side="SHORT", quantity=1, entry_price=100,
            isolated_wallet_balance=10, leverage=10,
            bracket_snapshot=snapshot(), now=NOW,
        )
        self.assertAlmostEqual(result["liquidation_price"], 110 / 1.01, places=10)

    def test_tier_is_resolved_using_liquidation_notional(self):
        tiers = [
            {"notional_floor": 0, "notional_cap": 80,
             "maintenance_margin_rate": 0.005, "maintenance_amount": 0,
             "max_leverage": 50},
            {"notional_floor": 80, "notional_cap": None,
             "maintenance_margin_rate": 0.01, "maintenance_amount": 0.4,
             "max_leverage": 20},
        ]
        result = calculate_isolated_liquidation_price(
            symbol="BTC/USDT", side="LONG", quantity=1, entry_price=100,
            isolated_wallet_balance=10, leverage=10,
            bracket_snapshot=snapshot(tiers=tiers), now=NOW,
        )
        self.assertAlmostEqual(result["liquidation_price"], (100 - 10 - 0.4) / 0.99)
        self.assertEqual(result["maintenance_margin_rate"], 0.01)

    def test_rejects_wrong_symbol_stale_and_future_snapshots(self):
        with self.assertRaisesRegex(ValueError, "symbol mismatch"):
            validate_bracket_snapshot(snapshot(symbol="ETH/USDT"), symbol="BTC/USDT", now=NOW)
        old = NOW - timedelta(hours=25)
        with self.assertRaisesRegex(ValueError, "stale"):
            validate_bracket_snapshot(snapshot(retrieved_at=old), symbol="BTC/USDT", now=NOW)
        future = NOW + timedelta(minutes=1)
        with self.assertRaisesRegex(ValueError, "future-dated"):
            validate_bracket_snapshot(snapshot(retrieved_at=future), symbol="BTC/USDT", now=NOW)

    def test_rejects_bad_or_noncontiguous_tiers(self):
        with self.assertRaisesRegex(ValueError, "contiguous"):
            validate_bracket_snapshot(snapshot(tiers=[
                {"notional_floor": 0, "notional_cap": 100,
                 "maintenance_margin_rate": .01, "maintenance_amount": 0,
                 "max_leverage": 20},
                {"notional_floor": 101, "notional_cap": None,
                 "maintenance_margin_rate": .02, "maintenance_amount": 1,
                 "max_leverage": 10},
            ]), symbol="BTC/USDT", now=NOW)
        with self.assertRaises(ValueError):
            validate_bracket_snapshot(snapshot(tiers=[{
                "notional_floor": 0, "notional_cap": None,
                "maintenance_margin_rate": True, "maintenance_amount": 0,
                "max_leverage": 20,
            }]), symbol="BTC/USDT", now=NOW)

    def test_rejects_excessive_leverage(self):
        with self.assertRaisesRegex(ValueError, "maximum"):
            calculate_isolated_liquidation_price(
                symbol="BTC/USDT", side="LONG", quantity=1, entry_price=100,
                isolated_wallet_balance=10, leverage=25,
                bracket_snapshot=snapshot(), now=NOW,
            )

    def test_rejects_cross_unsupported_side_and_bad_inputs(self):
        with self.assertRaises(ValueError):
            calculate_isolated_liquidation_price(
                symbol="BTC/USDT", side="BOTH", quantity=1, entry_price=100,
                isolated_wallet_balance=10, leverage=10,
                bracket_snapshot=snapshot(), now=NOW,
            )
        with self.assertRaises(ValueError):
            calculate_isolated_liquidation_price(
                symbol="BTC/USDT", side="LONG", quantity=1, entry_price=100,
                isolated_wallet_balance=True, leverage=10,
                bracket_snapshot=snapshot(), now=NOW,
            )


    def test_one_x_long_has_no_positive_threshold_and_is_not_overclaimed(self):
        result = calculate_isolated_liquidation_price(
            symbol="BTC/USDT", side="LONG", quantity=1, entry_price=100,
            isolated_wallet_balance=100, leverage=1,
            bracket_snapshot=snapshot(), now=NOW,
        )
        self.assertEqual(result["status"], "NO_POSITIVE_LIQUIDATION_PRICE_IN_MODEL")
        self.assertIsNone(result["liquidation_price"])

    def test_isolated_wallet_must_cover_initial_margin(self):
        with self.assertRaisesRegex(ValueError, "below the required initial margin"):
            calculate_isolated_liquidation_price(
                symbol="BTC/USDT", side="LONG", quantity=1, entry_price=100,
                isolated_wallet_balance=5, leverage=10,
                bracket_snapshot=snapshot(), now=NOW,
            )

    def test_rejects_nonmonotonic_or_discontinuous_maintenance_tiers(self):
        bad_rate = [
            {"notional_floor": 0, "notional_cap": 80,
             "maintenance_margin_rate": 0.01, "maintenance_amount": 0,
             "max_leverage": 20},
            {"notional_floor": 80, "notional_cap": None,
             "maintenance_margin_rate": 0.005, "maintenance_amount": 0.4,
             "max_leverage": 10},
        ]
        with self.assertRaisesRegex(ValueError, "must not decrease"):
            validate_bracket_snapshot(
                snapshot(tiers=bad_rate), symbol="BTC/USDT", now=NOW
            )
        bad_continuity = [
            {"notional_floor": 0, "notional_cap": 80,
             "maintenance_margin_rate": 0.005, "maintenance_amount": 0,
             "max_leverage": 50},
            {"notional_floor": 80, "notional_cap": None,
             "maintenance_margin_rate": 0.01, "maintenance_amount": 0.2,
             "max_leverage": 20},
        ]
        with self.assertRaisesRegex(ValueError, "not continuous"):
            validate_bracket_snapshot(
                snapshot(tiers=bad_continuity), symbol="BTC/USDT", now=NOW
            )


if __name__ == "__main__":
    unittest.main()
