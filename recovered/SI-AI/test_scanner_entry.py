import unittest
from unittest.mock import patch

import si_ai_scanner as scanner


def valid_result(signal="BUY"):
    if signal == "BUY":
        return {
            "signal": "BUY",
            "bos": "Bullish",
            "price": 100.0,
            "stop_loss": 98.0,
            "take_profit": 106.0,
            "reward_risk": 2.7381,
            "paper_quantity": 0.2,
            "paper_notional_usdt": 20.0,
            "paper_risk_usdt": 0.4,
            "paper_total_risk_usdt": 0.42772,
            "paper_estimated_fees_usdt": 0.0198,
            "paper_estimated_slippage_usdt": 0.00792,
            "paper_estimated_net_reward_usdt": 1.17116,
            "recommended_leverage": 1.0,
            "paper_margin_required_usdt": 20.0,
            "paper_margin_budget_usdt": 20.0,
        }
    return {
        "signal": "SELL",
        "bos": "Bearish",
        "price": 100.0,
        "stop_loss": 102.0,
        "take_profit": 94.0,
        "reward_risk": 2.7385,
        "paper_quantity": 0.2,
        "paper_notional_usdt": 20.0,
        "paper_risk_usdt": 0.4,
        "paper_total_risk_usdt": 0.42828,
        "paper_estimated_fees_usdt": 0.0202,
        "paper_estimated_slippage_usdt": 0.00808,
        "paper_estimated_net_reward_usdt": 1.17284,
        "recommended_leverage": 1.0,
        "paper_margin_required_usdt": 20.0,
        "paper_margin_budget_usdt": 20.0,
    }


class ScannerEntryConfirmationTests(unittest.TestCase):
    def setUp(self):
        self.results = {
            "1h": valid_result("BUY"),
            "4h": {"signal": "BUY"},
        }
        self.combined = {"overall_signal": "BUY"}

    def test_valid_buy_passes_independent_risk_and_sizing_validation(self):
        self.assertTrue(
            scanner.valid_risk("FUTURES", "BUY", self.results["1h"])
        )
        self.assertEqual(
            scanner.confirm_signal("FUTURES", self.results, self.combined),
            "BUY",
        )

    def test_valid_futures_sell_passes_independent_risk_and_sizing_validation(self):
        results = {
            "1h": valid_result("SELL"),
            "4h": {"signal": "SELL"},
        }
        self.assertTrue(
            scanner.valid_risk("FUTURES", "SELL", results["1h"])
        )
        self.assertEqual(
            scanner.confirm_signal(
                "FUTURES", results, {"overall_signal": "SELL"}
            ),
            "SELL",
        )

    def test_forged_reward_risk_value_fails_closed(self):
        self.results["1h"]["reward_risk"] = 99.0
        self.assertEqual(
            scanner.confirm_signal("FUTURES", self.results, self.combined),
            "WAIT",
        )

    def test_position_quantity_exceeding_risk_and_margin_caps_fails_closed(self):
        self.results["1h"].update({
            "paper_quantity": 0.5,
            "paper_notional_usdt": 50.0,
            "paper_risk_usdt": 1.0,
            "paper_total_risk_usdt": 1.0693,
            "paper_estimated_fees_usdt": 0.0495,
            "paper_estimated_slippage_usdt": 0.0198,
            "paper_estimated_net_reward_usdt": 2.9279,
            "paper_margin_required_usdt": 50.0,
        })
        self.assertEqual(
            scanner.confirm_signal("FUTURES", self.results, self.combined),
            "WAIT",
        )

    def test_subminimum_actual_net_reward_risk_fails_even_if_field_claims_two(self):
        self.results["1h"].update({
            "take_profit": 102.5,
            "reward_risk": 2.0,
        })
        self.assertEqual(
            scanner.confirm_signal("FUTURES", self.results, self.combined),
            "WAIT",
        )

    def test_inconsistent_notional_fails_closed(self):
        self.results["1h"]["paper_notional_usdt"] = 19.9
        self.assertEqual(
            scanner.confirm_signal("FUTURES", self.results, self.combined),
            "WAIT",
        )

    def test_missing_position_sizing_fields_fail_closed(self):
        self.results["1h"].pop("paper_quantity")
        self.assertEqual(
            scanner.confirm_signal("FUTURES", self.results, self.combined),
            "WAIT",
        )

    def test_score_only_buy_without_one_hour_bos_fails_closed(self):
        self.results["1h"]["bos"] = "None"
        self.assertEqual(
            scanner.confirm_signal("FUTURES", self.results, self.combined),
            "WAIT",
        )

    def test_reference_paper_equity_policy_cannot_change_silently(self):
        with patch.object(scanner.smc, "PAPER_EQUITY_USDT", 1000.0):
            with self.assertRaisesRegex(RuntimeError, "100 USDT"):
                scanner.validate_config()




class ScannerCycleFailClosedTests(unittest.TestCase):
    def setUp(self):
        self.empty_state = {
            "version": 2,
            "last_signals": {},
            "last_notified_at": {},
        }

    def test_http_451_during_universe_refresh_stops_cycle(self):
        with (
            patch.object(scanner, "load_state", return_value=self.empty_state),
            patch.object(
                scanner.smc,
                "refresh_symbol_universe",
                side_effect=RuntimeError("HTTP 451 restricted location"),
            ),
        ):
            with self.assertRaisesRegex(RuntimeError, "HTTP 451"):
                scanner.run_cycle(dry_run=True)

    def test_http_451_during_candle_fetch_stops_without_scanning_more_symbols(self):
        with (
            patch.object(scanner, "load_state", return_value=self.empty_state),
            patch.object(scanner.smc, "refresh_symbol_universe"),
            patch.object(scanner.smc, "get_symbols", return_value=["BTC/USDT"]),
            patch.object(scanner.smc, "MIN_ELIGIBLE_COINS", 1),
            patch.object(
                scanner.smc,
                "get_candles",
                side_effect=RuntimeError("HTTP 451 restricted location"),
            ),
        ):
            with self.assertRaisesRegex(RuntimeError, "HTTP 451"):
                scanner.run_cycle(dry_run=True)

    def test_dry_run_rejects_fewer_than_minimum_successfully_analysed_pairs(self):
        def candles_for_symbol(market, symbol, timeframe):
            if symbol == "ETH/USDT":
                raise RuntimeError("temporary data failure")
            return [[1, 100, 101, 99, 100, 1]]

        with (
            patch.object(scanner, "load_state", return_value=self.empty_state),
            patch.object(scanner.smc, "refresh_symbol_universe"),
            patch.object(
                scanner.smc,
                "get_symbols",
                return_value=["BTC/USDT", "ETH/USDT"],
            ),
            patch.object(scanner.smc, "MIN_ELIGIBLE_COINS", 2),
            patch.object(scanner.smc, "get_candles", side_effect=candles_for_symbol),
            patch.object(
                scanner.smc,
                "analyze_candles",
                return_value={"signal": "WAIT"},
            ),
            patch.object(
                scanner.smc,
                "combine_timeframes",
                return_value={"overall_signal": "WAIT"},
            ),
            patch.object(scanner, "confirm_signal", return_value="WAIT"),
            patch.object(scanner.time, "sleep"),
        ):
            with self.assertRaisesRegex(RuntimeError, "minimum required is 2"):
                scanner.run_cycle(dry_run=True)


if __name__ == "__main__":
    unittest.main(verbosity=2)
