"""Regression tests for dashboard state when Android notification delivery fails."""

import si_ai_scanner as scanner


TIMEFRAMES = ("15m", "1h", "4h", "1d")


def _results():
    base = {
        "signal": "BUY",
        "price": 100.0,
        "stop_loss": 98.0,
        "take_profit": 106.0,
        "reward_risk": 2.7,
        "recommended_leverage": 1.0,
        "paper_quantity": 0.2,
        "paper_notional_usdt": 20.0,
        "paper_margin_required_usdt": 20.0,
        "paper_margin_budget_usdt": 20.0,
        "paper_risk_usdt": 0.4,
        "paper_total_risk_usdt": 0.5,
        "paper_estimated_fees_usdt": 0.02,
        "paper_estimated_slippage_usdt": 0.008,
        "paper_estimated_net_reward_usdt": 1.1,
        "time_utc": "2026-11-19T12:00:00+00:00",
        "reasons": ["Confirmed structure break"],
    }
    return {timeframe: dict(base) for timeframe in TIMEFRAMES}


def _run_with_failed_notification(monkeypatch, confirmed_signal, previous_signal):
    key = "FUTURES|BTC/USDT"
    previous_alert_time = scanner.time.time() if previous_signal in ("BUY", "SELL") else None
    state = {
        "version": scanner.STATE_VERSION,
        "last_signals": {key: previous_signal},
        "last_notified_at": (
            {key: previous_alert_time} if previous_alert_time is not None else {}
        ),
    }
    saved_dashboard = []
    saved_scanner_state = []
    results = _results()

    monkeypatch.setattr(scanner, "load_state", lambda: state)
    monkeypatch.setattr(scanner, "load_latest_signals", lambda: {})
    monkeypatch.setattr(scanner, "save_latest_signals", lambda value: saved_dashboard.append(value))
    monkeypatch.setattr(scanner, "save_state", lambda value: saved_scanner_state.append(value))
    monkeypatch.setattr(scanner.smc, "refresh_symbol_universe", lambda: None)
    monkeypatch.setattr(scanner.smc, "MARKETS", ["FUTURES"])
    monkeypatch.setattr(scanner.smc, "TIMEFRAMES", list(TIMEFRAMES))
    monkeypatch.setattr(scanner.smc, "MIN_ELIGIBLE_COINS", 1)
    monkeypatch.setattr(scanner.smc, "TARGET_UNIVERSE_SIZE", 1)
    monkeypatch.setattr(scanner.smc, "MAX_UNIVERSE_SIZE", 1)
    monkeypatch.setattr(scanner.smc, "MARKET_UNIVERSE_STATUS", {})
    monkeypatch.setattr(scanner.smc, "MARKET_UNIVERSE_DIAGNOSTICS", {})
    monkeypatch.setattr(scanner.smc, "REQUEST_DELAY_SECONDS", 0)
    monkeypatch.setattr(scanner.smc, "get_symbols", lambda market: ["BTC/USDT"])
    monkeypatch.setattr(scanner.smc, "get_candles", lambda *args: [[1]])
    monkeypatch.setattr(
        scanner.smc, "analyze_candles",
        lambda market, symbol, timeframe, candles: results[timeframe],
    )
    monkeypatch.setattr(
        scanner.smc, "combine_timeframes",
        lambda analyses: {"overall_signal": confirmed_signal},
    )
    monkeypatch.setattr(
        scanner, "confirm_signal", lambda market, analyses, combined: confirmed_signal
    )
    monkeypatch.setattr(scanner.time, "sleep", lambda seconds: None)

    def fail_notification(*args, **kwargs):
        raise RuntimeError("simulated Termux notification failure")

    monkeypatch.setattr(scanner, "send_notification", fail_notification)

    completed = scanner.run_cycle(dry_run=False)
    assert completed == 1
    assert saved_dashboard, "Dashboard state must be saved despite notification failure"
    return saved_dashboard[-1][key], saved_scanner_state


def test_failed_wait_notification_still_invalidates_old_actionable_dashboard_signal(monkeypatch):
    snapshot, saved_state = _run_with_failed_notification(
        monkeypatch, confirmed_signal="WAIT", previous_signal="BUY"
    )
    assert snapshot["signal"] == "WAIT"
    assert snapshot["status"] == "INVALIDATED"
    assert snapshot["side"] is None
    assert snapshot["entry_price"] is None
    assert saved_state, "Scanner state must retain the retryable WAIT transition"
    assert saved_state[-1]["last_signals"]["FUTURES|BTC/USDT"] == "BUY"


def test_failed_buy_notification_still_saves_new_confirmed_dashboard_signal(monkeypatch):
    snapshot, _ = _run_with_failed_notification(
        monkeypatch, confirmed_signal="BUY", previous_signal="WAIT"
    )
    assert snapshot["signal"] == "BUY"
    assert snapshot["status"] == "ACTIVE"
    assert snapshot["side"] == "LONG"
    assert snapshot["entry_price"] == 100.0
    assert snapshot["notification_sent_at"] is None
