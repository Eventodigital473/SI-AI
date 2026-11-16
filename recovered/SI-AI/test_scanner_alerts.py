import unittest

import si_ai_scanner as scanner


class SignalAlertTests(unittest.TestCase):
    def setUp(self):
        self.results = {
            "1h": {
                "signal": "BUY",
                "price": 142.5,
                "stop_loss": 138.0,
                "take_profit": 151.5,
                "reward_risk": 2.0,
                "recommended_leverage": 1.0,
                "paper_margin_required_usdt": 12.0,
                "paper_margin_budget_usdt": 20.0,
                "reasons": ["Bullish structure"],
            },
            "4h": {"signal": "BUY"},
        }

    def test_alert_includes_coin_name_symbol_and_timeframes(self):
        title, content = scanner.make_alert(
            "FUTURES", "SOL/USDT", "BUY", self.results
        )
        self.assertEqual(title, "BUY")
        self.assertIn("Coin: Solana (SOL/USDT)", content)
        self.assertIn("Entry timeframe: 1h", content)
        self.assertIn("Confirmation timeframe: 4h", content)

    def test_alert_includes_entry_sl_three_targets_and_leverage(self):
        _, content = scanner.make_alert(
            "FUTURES", "BTC/USDT", "BUY", self.results
        )
        self.assertIn("Entry price reference (last closed 1h candle): 142.5", content)
        self.assertIn("Stop Loss: 138", content)
        self.assertIn("TP1 (1R reference): 147", content)
        self.assertIn("TP2 (1.5R reference): 149.25", content)
        self.assertIn("TP3 (engine target): 151.5", content)
        self.assertIn("Recommended leverage: 1x", content)
        self.assertIn("Estimated margin: 12.00 USDT / 20.00 USDT budget", content)

    def test_futures_sell_targets_are_below_entry(self):
        self.results["1h"].update({
            "signal": "SELL",
            "price": 100.0,
            "stop_loss": 102.0,
            "take_profit": 94.0,
            "reward_risk": 2.5,
        })
        self.results["4h"]["signal"] = "SELL"
        _, content = scanner.make_alert(
            "FUTURES", "BTC/USDT", "SELL", self.results
        )
        self.assertIn("TP1 (1R reference): 98", content)
        self.assertIn("TP2 (1.5R reference): 97", content)
        self.assertIn("TP3 (engine target): 94", content)

    def test_spot_sell_is_exit_without_short_targets(self):
        self.results["1h"]["signal"] = "SELL/EXIT"
        self.results["4h"]["signal"] = "SELL/EXIT"
        title, content = scanner.make_alert(
            "SPOT", "ETH/USDT", "SELL", self.results
        )
        self.assertEqual(title, "SELL / EXIT")
        self.assertIn("Coin: Ethereum (ETH/USDT)", content)
        self.assertIn("Spot exit only. No short position.", content)
        self.assertNotIn("TP1", content)
        self.assertNotIn("Stop Loss:", content)

    def test_unknown_coin_name_is_not_guessed(self):
        self.assertEqual(
            scanner.coin_display_name("UNKNOWN/USDT"), "Unknown asset"
        )


if __name__ == "__main__":
    unittest.main()
