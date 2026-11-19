from datetime import datetime, timedelta, timezone

import pytest

import signal_dashboard as dashboard


def sample_results():
    now = datetime.now(timezone.utc).isoformat()
    return {
        "1h": {
            "signal": "BUY",
            "time_utc": now,
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
            "reasons": ["Bullish BOS", "EMA20 above EMA50"],
        },
        "4h": {"signal": "BUY"},
    }


def test_snapshot_contains_manual_trade_plan_fields():
    snapshot = dashboard.make_signal_snapshot(
        "FUTURES", "BTC/USDT", "BUY", sample_results(),
        "validated alert",
    )
    assert snapshot["side"] == "LONG"
    assert snapshot["status"] == "ACTIVE"
    assert snapshot["entry_price"] == 100.0
    assert snapshot["stop_loss"] == 98.0
    assert snapshot["take_profit"] == 106.0
    assert snapshot["leverage"] == 1.0
    assert snapshot["risk_usdt"] == 0.5
    assert snapshot["reasons"] == ["Bullish BOS", "EMA20 above EMA50"]


def test_wait_snapshot_invalidates_entry_and_preserves_notification_time():
    previous = dashboard.make_signal_snapshot(
        "FUTURES", "BTC/USDT", "BUY", sample_results(), "BUY alert",
        notification_sent=True,
    )
    wait_results = sample_results()
    wait_results["1h"]["signal"] = "WAIT"
    wait = dashboard.make_signal_snapshot(
        "FUTURES", "BTC/USDT", "WAIT", wait_results, "WAIT alert",
        previous_record=previous,
        notification_sent=True,
    )
    assert wait["status"] == "INVALIDATED"
    assert wait["side"] is None
    assert wait["entry_price"] is None
    assert wait["notification_sent_at"] is not None


def test_latest_signal_store_round_trip_is_atomic(tmp_path, monkeypatch):
    target = tmp_path / "si_ai_latest_signals_state.json"
    monkeypatch.setattr(dashboard, "BASE_DIR", tmp_path)
    monkeypatch.setattr(dashboard, "LATEST_SIGNALS_FILE", target)
    snapshot = dashboard.make_signal_snapshot(
        "FUTURES", "BTC/USDT", "BUY", sample_results(), "alert",
    )
    dashboard.save_latest_signals({"FUTURES|BTC/USDT": snapshot})
    assert dashboard.load_latest_signals() == {"FUTURES|BTC/USDT": snapshot}
    assert not list(tmp_path.glob(".si_ai_latest_signals_*.tmp"))


def test_store_rejects_invalid_records_without_overwriting(tmp_path, monkeypatch):
    target = tmp_path / "si_ai_latest_signals_state.json"
    target.write_text('{"version":1,"signals":{"SPOT|BTC/USDT":{}}}', encoding="utf-8")
    monkeypatch.setattr(dashboard, "LATEST_SIGNALS_FILE", target)
    with pytest.raises(RuntimeError, match="invalid record"):
        dashboard.load_latest_signals()
