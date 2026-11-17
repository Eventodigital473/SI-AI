import unittest

import pytest
from unittest.mock import patch

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
                "paper_quantity": 0.12,
                "paper_notional_usdt": 17.1,
                "paper_risk_usdt": 0.42,
                "paper_total_risk_usdt": 0.49,
                "paper_estimated_fees_usdt": 0.0171,
                "paper_estimated_slippage_usdt": 0.00684,
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

    def test_alert_includes_position_size_risk_costs_and_liquidation_warning(self):
        _, content = scanner.make_alert(
            "FUTURES", "BTC/USDT", "BUY", self.results
        )
        self.assertIn("Position size (paper estimate): 0.12 BTC", content)
        self.assertIn("Position notional (paper estimate): 17.1000 USDT", content)
        self.assertIn("Estimated stop risk: 0.4900 USDT incl. estimated costs", content)
        self.assertIn("Risk policy: 0.50% of 100.00 USDT reference equity", content)
        self.assertIn("Estimated round-trip fees: 0.0171 USDT", content)
        self.assertIn("Liquidation price: NOT MODELLED/NOT CERTIFIED", content)
        self.assertIn("amount precision/minimum quantity/minimum notional: NOT", content)
        self.assertIn("round quantity DOWN only", content)

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


    def test_unknown_coin_name_is_not_guessed(self):
        self.assertEqual(
            scanner.coin_display_name("UNKNOWN/USDT"), "Unknown asset"
        )

    def test_buy_notification_uses_green_led_and_high_priority(self):
        command = scanner.notification_command(
            "FUTURES", "BTC/USDT", "BUY", "test"
        )
        self.assertIn("--title", command)
        self.assertIn("🟢 BUY", command[command.index("--title") + 1])
        self.assertEqual(command[command.index("--led-color") + 1], "00C853")
        self.assertEqual(command[command.index("--priority") + 1], "high")
        self.assertIn("--sound", command)

    def test_sell_notification_uses_red_led_and_distinct_vibration(self):
        command = scanner.notification_command(
            "FUTURES", "BTC/USDT", "SELL", "test"
        )
        self.assertIn("🔴 SELL", command[command.index("--title") + 1])
        self.assertEqual(command[command.index("--led-color") + 1], "FF1744")
        self.assertEqual(command[command.index("--priority") + 1], "high")
        self.assertEqual(
            command[command.index("--vibrate") + 1], "0,350,100,350"
        )

    def test_wait_notification_is_neutral_without_sound_or_led(self):
        command = scanner.notification_command(
            "FUTURES", "BTC/USDT", "WAIT", "test"
        )
        self.assertIn("⚪ WAIT", command[command.index("--title") + 1])
        self.assertNotIn("--led-color", command)
        self.assertNotIn("--sound", command)
        self.assertEqual(command[command.index("--priority") + 1], "default")

    @patch.object(scanner.subprocess, "run")
    @patch.object(scanner.shutil, "which", return_value=None)
    def test_missing_termux_api_has_clear_error(self, _which, run_mock):
        with self.assertRaisesRegex(RuntimeError, "Termux:API"):
            scanner.send_notification("FUTURES", "BTC/USDT", "BUY", "test")
        run_mock.assert_not_called()


if __name__ == "__main__":
    unittest.main()


@pytest.mark.parametrize("value", [True, False])
def test_scanner_number_parser_rejects_booleans(value):
    assert scanner.number(value) is None

def test_duplicate_actionable_alert_expires_after_six_hours():
    now = 1_800_000_000
    assert scanner.should_suppress_duplicate("BUY", "BUY", now - 60, now)
    assert not scanner.should_suppress_duplicate(
        "BUY", "BUY", now - scanner.SIGNAL_REPEAT_ALERT_SECONDS - 1, now
    )
    assert not scanner.should_suppress_duplicate("SELL", "BUY", now - 60, now)
    assert not scanner.should_suppress_duplicate("WAIT", "WAIT", now - 60, now)
    assert not scanner.should_suppress_duplicate("BUY", "BUY", None, now)


def test_legacy_signal_state_migrates_without_losing_last_signal(tmp_path, monkeypatch):
    state_file = tmp_path / "scanner-state.json"
    state_file.write_text(
        '{"version":1,"last_signals":{"FUTURES|BTC/USDT":"BUY"}}',
        encoding="utf-8",
    )
    monkeypatch.setattr(scanner, "STATE_FILE", state_file)
    state = scanner.load_state()
    assert state == {
        "version": 2,
        "last_signals": {"FUTURES|BTC/USDT": "BUY"},
        "last_notified_at": {},
    }


@pytest.mark.parametrize("timestamp", [True, False, -1, float("inf"), "not-a-time"])
def test_state_rejects_invalid_notification_timestamps(tmp_path, monkeypatch, timestamp):
    state_file = tmp_path / "scanner-state.json"
    state_file.write_text(
        __import__("json").dumps({
            "version": 2,
            "last_signals": {"FUTURES|BTC/USDT": "BUY"},
            "last_notified_at": {"FUTURES|BTC/USDT": timestamp},
        }),
        encoding="utf-8",
    )
    monkeypatch.setattr(scanner, "STATE_FILE", state_file)
    with pytest.raises(RuntimeError, match="Invalid notification timestamp"):
        scanner.load_state()

def test_missing_state_initializes_notification_timestamp_map(tmp_path, monkeypatch):
    state_file = tmp_path / "scanner-state.json"
    monkeypatch.setattr(scanner, "STATE_FILE", state_file)
    assert scanner.load_state() == {
        "version": 2,
        "last_signals": {},
        "last_notified_at": {},
    }
\n