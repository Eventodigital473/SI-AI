import unittest
from unittest.mock import patch

import main


def sample_result(timeframe, signal="BUY"):
    return {
        "market": "FUTURES",
        "symbol": "BTC/USDT",
        "timeframe": timeframe,
        "signal": signal,
        "score": 4.5,
        "price": 100.0,
        "stop_loss": 98.0,
        "take_profit": 106.0,
        "reward_risk": 2.0,
        "paper_risk_usdt": 4.0,
        "paper_total_risk_usdt": 5.0,
        "paper_quantity": 2.0,
        "paper_notional_usdt": 200.0,
        "paper_estimated_fees_usdt": 0.2,
        "paper_estimated_slippage_usdt": 0.1,
        "paper_estimated_net_reward_usdt": 10.0,
    }


class MainApiTests(unittest.TestCase):

    def setUp(self):
        main.app.config["TESTING"] = True
        self.client = main.app.test_client()

    def test_single_api_preserves_risk_fields(self):
        result = sample_result("1h")

        with patch.object(main.smc, "analyze", return_value=result):
            response = self.client.get(
                "/api/analyze?market=FUTURES&symbol=BTC/USDT&timeframe=1h"
            )

        self.assertEqual(response.status_code, 200)

        data = response.get_json()
        self.assertTrue(data["success"])

        analysis = data["analysis"]

        for key in (
            "stop_loss",
            "take_profit",
            "reward_risk",
            "paper_quantity",
            "paper_notional_usdt",
            "paper_risk_usdt",
            "paper_total_risk_usdt",
            "paper_estimated_fees_usdt",
            "paper_estimated_slippage_usdt",
            "paper_estimated_net_reward_usdt",
        ):
            self.assertIn(key, analysis)

    def test_api_accepts_a_market_specific_dynamic_coin(self):
        result = sample_result("1h")
        result["symbol"] = "SOL/USDT"

        with patch.object(
            main.smc, "get_symbols", return_value=["SOL/USDT"]
        ), patch.object(main.smc, "analyze", return_value=result):
            response = self.client.get(
                "/api/analyze?market=FUTURES&symbol=SOL/USDT&timeframe=1h"
            )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.get_json()["analysis"]["symbol"], "SOL/USDT")

    def test_api_config_exposes_dynamic_universe_policy(self):
        with patch.object(main.smc, "refresh_symbol_universe"):
            response = self.client.get("/api/config")

        self.assertEqual(response.status_code, 200)
        data = response.get_json()
        self.assertIn("symbols_by_market", data)
        self.assertIn("universe_status_by_market", data)
        self.assertEqual(
            data["universe_policy"]["minimum_eligible_coins"], 15
        )
        self.assertEqual(
            data["universe_policy"]["maximum_coins"], 100
        )
        self.assertEqual(data["risk_policy"]["reference_wallet_usdt"], 100.0)
        self.assertEqual(data["risk_policy"]["margin_allocation_percent"], 20.0)
        self.assertEqual(data["risk_policy"]["margin_budget_usdt"], 20.0)
        self.assertEqual(data["risk_policy"]["recommended_futures_leverage"], 1.0)
        self.assertFalse(data["risk_policy"]["automatic_orders"])

    def test_invalid_timeframe_is_rejected(self):
        with patch.object(main.smc, "analyze") as mocked:
            response = self.client.get(
                "/api/analyze?timeframe=invalid"
            )

        self.assertEqual(response.status_code, 400)
        mocked.assert_not_called()

    def test_multi_timeframe_preserves_individual_risk(self):
        results = {
            "15m": sample_result("15m"),
            "1h": sample_result("1h"),
        }

        with patch.object(
            main.smc, "analyze",
            side_effect=lambda market, symbol, tf: results[tf]
        ), patch.object(
            main.smc, "combine_timeframes",
            return_value={
                "weighted_score": 4.5,
                "overall_signal": "BUY",
            }
        ), patch.object(main.time, "sleep"):

            response = self.client.post(
                "/api/multi-timeframe",
                json={
                    "market": "FUTURES",
                    "symbol": "BTC/USDT",
                    "timeframes": ["15m", "1h"],
                },
            )

        self.assertEqual(response.status_code, 200)

        data = response.get_json()
        self.assertTrue(data["success"])
        self.assertEqual(data["timeframe_count"], 2)
        self.assertTrue(data["complete"])
        self.assertEqual(
            data["multi_timeframe"]["analysis_status"], "COMPLETE"
        )

        for result in data["successful_analyses"]:
            self.assertIn("paper_quantity", result)
            self.assertIn("paper_total_risk_usdt", result)
            self.assertIn("stop_loss", result)

    def test_spot_bearish_combined_signal_becomes_exit(self):
        result = sample_result("15m", "SELL/EXIT")

        with patch.object(
            main.smc, "analyze", return_value=result
        ), patch.object(
            main.smc, "combine_timeframes",
            return_value={
                "weighted_score": -4.0,
                "overall_signal": "SELL",
            }
        ), patch.object(main.time, "sleep"):

            response = self.client.post(
                "/api/multi-timeframe",
                json={
                    "market": "SPOT",
                    "symbol": "BTC/USDT",
                    "timeframes": ["15m"],
                },
            )

        self.assertEqual(response.status_code, 200)

        data = response.get_json()
        self.assertEqual(
            data["multi_timeframe"]["overall_signal"],
            "SELL/EXIT",
        )
        self.assertFalse(data["automatic_orders"])

    def test_partial_timeframe_failure_is_reported(self):
        with patch.object(
            main.smc, "analyze",
            side_effect=[
                sample_result("15m"),
                RuntimeError("Temporary test failure"),
            ],
        ), patch.object(
            main.smc, "combine_timeframes",
            return_value={
                "weighted_score": 4.0,
                "overall_signal": "BUY",
            }
        ), patch.object(main.time, "sleep"):

            response = self.client.post(
                "/api/multi-timeframe",
                json={
                    "market": "FUTURES",
                    "symbol": "BTC/USDT",
                    "timeframes": ["15m", "1h"],
                },
            )

        self.assertEqual(response.status_code, 200)

        data = response.get_json()
        self.assertEqual(data["timeframe_count"], 1)
        self.assertEqual(len(data["errors"]), 1)
        self.assertEqual(data["errors"][0]["timeframe"], "1h")
        self.assertFalse(data["complete"])
        self.assertEqual(
            data["multi_timeframe"]["overall_signal"], "WAIT"
        )
        self.assertEqual(
            data["multi_timeframe"]["analysis_status"], "INCOMPLETE"
        )

    def test_duplicate_timeframes_are_rejected(self):
        with patch.object(main.smc, "analyze") as mocked:
            response = self.client.post(
                "/api/multi-timeframe",
                json={
                    "market": "FUTURES",
                    "symbol": "BTC/USDT",
                    "timeframes": ["1h", "1h"],
                },
            )
        self.assertEqual(response.status_code, 400)
        mocked.assert_not_called()

    def test_all_timeframe_failures_return_error(self):
        with patch.object(
            main.smc, "analyze",
            side_effect=RuntimeError("Test failure"),
        ), patch.object(main.time, "sleep"):

            response = self.client.post(
                "/api/multi-timeframe",
                json={
                    "market": "FUTURES",
                    "symbol": "BTC/USDT",
                    "timeframes": ["15m", "1h"],
                },
            )

        self.assertEqual(response.status_code, 502)

        data = response.get_json()
        self.assertFalse(data["success"])
        self.assertEqual(len(data["errors"]), 2)


if __name__ == "__main__":
    unittest.main(verbosity=2)
