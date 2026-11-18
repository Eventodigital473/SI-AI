import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import SI_AI_smc as smc
import termux_preflight


class TermuxPreflightTests(unittest.TestCase):
    def test_preflight_reports_missing_android_extras_as_warnings(self):
        with tempfile.TemporaryDirectory() as directory:
            report = termux_preflight.collect_preflight(
                project_dir=termux_preflight.BASE_DIR,
                shortcuts_dir=Path(directory),
                command_lookup=lambda name: None,
                prefix="/data/data/com.termux/files/usr",
            )
        self.assertEqual(report["status"], "READY_WITH_WARNINGS")
        checks = {item["name"]: item for item in report["checks"]}
        self.assertEqual(checks["scanner_config"]["status"], "PASS")
        self.assertEqual(checks["risk_policy"]["status"], "PASS")
        self.assertEqual(checks["termux_api_command"]["status"], "WARN")
        self.assertFalse(report["network_requests"])
        self.assertFalse(report["credentials_read"])
        self.assertFalse(report["automatic_orders"])

    def test_preflight_fails_if_active_risk_policy_changes(self):
        with tempfile.TemporaryDirectory() as directory, patch.object(
            smc, "RISK_PER_TRADE_PERCENT", 1.0
        ):
            report = termux_preflight.collect_preflight(
                project_dir=termux_preflight.BASE_DIR,
                shortcuts_dir=Path(directory),
                command_lookup=lambda name: "/usr/bin/" + name,
                prefix="/data/data/com.termux/files/usr",
            )
        self.assertEqual(report["status"], "FAIL")
        risk = next(item for item in report["checks"] if item["name"] == "risk_policy")
        self.assertEqual(risk["status"], "FAIL")

    def test_preflight_is_ready_when_all_local_requirements_are_present(self):
        with tempfile.TemporaryDirectory() as directory:
            shortcuts = Path(directory)
            for name in ("SI-AI Start", "SI-AI Stop", "SI-AI Dry Run", "SI-AI Check"):
                (shortcuts / name).write_text("shortcut")
            report = termux_preflight.collect_preflight(
                project_dir=termux_preflight.BASE_DIR,
                shortcuts_dir=shortcuts,
                command_lookup=lambda name: "/usr/bin/" + name,
                prefix="/data/data/com.termux/files/usr",
                package_lookup=lambda: True,
            )
        self.assertEqual(report["status"], "READY")

    def test_preflight_warns_when_termux_api_companion_is_missing(self):
        with tempfile.TemporaryDirectory() as directory:
            report = termux_preflight.collect_preflight(
                project_dir=termux_preflight.BASE_DIR,
                shortcuts_dir=Path(directory),
                command_lookup=lambda name: "/usr/bin/" + name,
                prefix="/data/data/com.termux/files/usr",
                package_lookup=lambda: False,
            )
        checks = {item["name"]: item for item in report["checks"]}
        self.assertEqual(checks["termux_api_companion_app"]["status"], "WARN")
        self.assertIn("same signing source", checks["termux_api_companion_app"]["detail"])
        self.assertEqual(report["status"], "READY_WITH_WARNINGS")


if __name__ == "__main__":
    unittest.main(verbosity=2)
