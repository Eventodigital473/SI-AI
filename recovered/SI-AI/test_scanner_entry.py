import unittest

import si_ai_scanner as scanner


class ScannerEntryConfirmationTests(unittest.TestCase):
    def setUp(self):
        self.results = {
            "1h": {
                "signal": "BUY",
                "bos": "Bullish",
                "price": 100.0,
                "stop_loss": 98.0,
                "take_profit": 106.0,
                "reward_risk": 2.5,
            },
            "4h": {"signal": "BUY"},
        }
        self.combined = {"overall_signal": "BUY"}

    def test_buy_requires_directional_one_hour_bos(self):
        self.assertEqual(
            scanner.confirm_signal("FUTURES", self.results, self.combined),
            "BUY",
        )

    def test_score_only_buy_without_one_hour_bos_fails_closed(self):
        self.results["1h"]["bos"] = "None"
        self.assertEqual(
            scanner.confirm_signal("FUTURES", self.results, self.combined),
            "WAIT",
        )



if __name__ == "__main__":
    unittest.main(verbosity=2)
