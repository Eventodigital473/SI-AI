"""Offline Termux preflight for SI-AI.

Checks local runtime, dependencies, Futures-only policy, and Widget/notification
prerequisites. It does not contact Binance, read credentials, or place orders.
"""
from __future__ import annotations

import importlib
from importlib import metadata
import os
import platform
import shutil
import subprocess
import sys
from pathlib import Path


BASE_DIR = Path(__file__).resolve().parent


def _check(name, status, detail):
    return {"name": name, "status": status, "detail": str(detail)}


def _termux_api_companion_installed():
    """Return True/False when Android package manager can verify the companion; None if unknown."""
    package_manager = Path("/system/bin/pm")
    if not package_manager.is_file():
        return None
    try:
        result = subprocess.run(
            [str(package_manager), "path", "com.termux.api"],
            capture_output=True,
            text=True,
            timeout=3,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired):
        return None
    return (
        result.returncode == 0
        and any(line.strip().startswith("package:") for line in result.stdout.splitlines())
    )


def collect_preflight(
    project_dir=None,
    shortcuts_dir=None,
    command_lookup=None,
    prefix=None,
    package_lookup=None,
):
    project = Path(project_dir) if project_dir is not None else BASE_DIR
    shortcuts = Path(shortcuts_dir) if shortcuts_dir is not None else Path.home() / ".shortcuts"
    lookup = command_lookup or shutil.which
    termux_prefix = os.environ.get("PREFIX", "") if prefix is None else prefix
    checks = []

    checks.append(_check(
        "python_version",
        "PASS" if sys.version_info >= (3, 10) else "FAIL",
        platform.python_version(),
    ))
    checks.append(_check(
        "termux_environment",
        "PASS" if termux_prefix.startswith("/data/data/com.termux/files/usr") else "WARN",
        termux_prefix or "PREFIX is not set; this does not look like a standard Termux shell",
    ))

    for module_name in ("ccxt", "requests", "certifi", "cryptography", "typing_extensions", "flask"):
        try:
            module = importlib.import_module(module_name)
            version = metadata.version(module_name)
            checks.append(_check(f"dependency_{module_name}", "PASS", version))
        except Exception as exc:
            checks.append(_check(f"dependency_{module_name}", "FAIL", f"{type(exc).__name__}: {exc}"))

    try:
        smc = importlib.import_module("SI_AI_smc")
    except Exception as exc:
        smc = None
        checks.append(_check("scanner_config", "FAIL", f"{type(exc).__name__}: {exc}"))

    if smc is not None:
        try:
            scanner = importlib.import_module("si_ai_scanner")
            scanner.validate_config()
            checks.append(_check("scanner_config", "PASS", "scanner.validate_config() passed"))
        except Exception as exc:
            checks.append(_check("scanner_config", "FAIL", f"{type(exc).__name__}: {exc}"))

        checks.append(_check(
            "futures_only",
            "PASS" if list(smc.MARKETS) == ["FUTURES"] else "FAIL",
            f"MARKETS={list(smc.MARKETS)}",
        ))
        checks.append(_check(
            "production_timeframes",
            "PASS" if list(smc.TIMEFRAMES) == ["15m", "1h", "4h", "1d"] else "FAIL",
            f"TIMEFRAMES={list(smc.TIMEFRAMES)}",
        ))
        try:
            policy_ok = (
                float(smc.PAPER_EQUITY_USDT) == 100.0
                and float(smc.RISK_PER_TRADE_PERCENT) == 0.5
                and float(smc.MARGIN_ALLOCATION_PERCENT) == 20.0
                and float(smc.RECOMMENDED_FUTURES_LEVERAGE) == 1.0
                and float(smc.MIN_REWARD_RISK) >= 2.0
            )
        except (TypeError, ValueError, AttributeError):
            policy_ok = False
        checks.append(_check(
            "risk_policy",
            "PASS" if policy_ok else "FAIL",
            "equity=100 USDT; risk=0.5%; margin cap=20%; leverage=1x; minimum R:R=2:1",
        ))

    scanner_file = project / "si_ai_scanner.py"
    checks.append(_check(
        "project_path",
        "PASS" if scanner_file.is_file() else "FAIL",
        project,
    ))
    shortcuts_expected = ("SI-AI Start", "SI-AI Stop", "SI-AI Dry Run", "SI-AI Check")
    missing_shortcuts = [name for name in shortcuts_expected if not (shortcuts / name).is_file()]
    checks.append(_check(
        "termux_widget_shortcuts",
        "PASS" if not missing_shortcuts else "WARN",
        "All four shortcuts installed" if not missing_shortcuts else "Not installed/missing: " + ", ".join(missing_shortcuts),
    ))

    notification = lookup("termux-notification")
    checks.append(_check(
        "termux_api_command",
        "PASS" if notification else "WARN",
        notification or "termux-notification not found; install the Termux:API package",
    ))
    companion_lookup = package_lookup or _termux_api_companion_installed
    companion_installed = companion_lookup()
    if companion_installed is True:
        companion_status = "PASS"
        companion_detail = "Android package com.termux.api is installed"
    elif companion_installed is False:
        companion_status = "WARN"
        companion_detail = (
            "Termux:API companion app is not installed; install it from the same "
            "signing source as Termux, then grant notification permission"
        )
    else:
        companion_status = "INFO"
        companion_detail = (
            "Android package manager unavailable; companion-app installation "
            "must be confirmed with a phone-side notification test"
        )
    checks.append(_check(
        "termux_api_companion_app",
        companion_status,
        companion_detail,
    ))
    toast = lookup("termux-toast")
    checks.append(_check(
        "termux_toast_optional",
        "PASS" if toast else "WARN",
        toast or "termux-toast not found; optional Widget status messages unavailable",
    ))
    checks.append(_check(
        "android_notification_permission",
        "INFO",
        "Cannot be verified offline. A real phone notification and LED test is still required; Android/OEM settings may override LED requests.",
    ))

    statuses = [item["status"] for item in checks]
    overall = "FAIL" if "FAIL" in statuses else "READY_WITH_WARNINGS" if "WARN" in statuses else "READY"
    return {
        "status": overall,
        "checks": checks,
        "network_requests": False,
        "credentials_read": False,
        "automatic_orders": False,
    }


def main():
    report = collect_preflight()
    print(f"SI-AI TERMUX PREFLIGHT: {report['status']}")
    for item in report["checks"]:
        print(f"[{item['status']}] {item['name']}: {item['detail']}")
    print("No Binance network requests, credentials, or orders were used.")
    return 1 if report["status"] == "FAIL" else 0


if __name__ == "__main__":
    raise SystemExit(main())
