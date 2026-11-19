from datetime import datetime, timedelta, timezone
from unittest.mock import patch

import main


def record(symbol="BTC/USDT", age_seconds=0):
    stamp = (datetime.now(timezone.utc) - timedelta(seconds=age_seconds)).isoformat()
    return {
        "market": "FUTURES",
        "symbol": symbol,
        "signal": "BUY",
        "side": "LONG",
        "status": "ACTIVE",
        "created_at": stamp,
        "last_confirmed_at": stamp,
        "notification_sent_at": stamp,
        "timeframe_1h": "BUY",
        "timeframe_4h": "BUY",
        "alert_text": "validated trade plan",
        "reasons": ["Bullish BOS"],
        "entry_price": 100.0,
        "stop_loss": 98.0,
        "take_profit": 106.0,
        "reward_risk": 2.7,
        "leverage": 1.0,
        "position_size": 0.2,
        "notional_usdt": 20.0,
        "margin_usdt": 20.0,
        "margin_budget_usdt": 20.0,
        "gross_risk_usdt": 0.4,
        "risk_usdt": 0.5,
        "estimated_fees_usdt": 0.02,
        "estimated_slippage_usdt": 0.008,
        "estimated_net_reward_usdt": 1.1,
    }


def test_dashboard_and_signal_routes_render_dashboard():
    client = main.app.test_client()
    for path in ("/", "/signal?symbol=BTC/USDT"):
        response = client.get(path)
        assert response.status_code == 200
        assert b"SI-AI Signal Dashboard" in response.data
        assert b"No automatic orders" in response.data


def test_latest_signals_api_returns_full_trade_plan_and_freshness():
    client = main.app.test_client()
    saved = {"FUTURES|BTC/USDT": record()}
    with patch.object(main.dashboard_store, "load_latest_signals", return_value=saved):
        response = client.get("/api/latest-signals")
    assert response.status_code == 200
    payload = response.get_json()
    assert payload["automatic_orders"] is False
    assert payload["signals"][0]["side"] == "LONG"
    assert payload["signals"][0]["entry_price"] == 100.0
    assert payload["signals"][0]["risk_usdt"] == 0.5
    assert payload["signals"][0]["is_stale"] is False


def test_latest_signals_api_marks_old_records_stale_and_filters_symbol():
    client = main.app.test_client()
    saved = {
        "FUTURES|BTC/USDT": record("BTC/USDT", age_seconds=3 * 60 * 60),
        "FUTURES|ETH/USDT": record("ETH/USDT"),
    }
    with patch.object(main.dashboard_store, "load_latest_signals", return_value=saved):
        response = client.get("/api/latest-signals?symbol=BTC/USDT")
    payload = response.get_json()
    assert len(payload["signals"]) == 1
    assert payload["signals"][0]["symbol"] == "BTC/USDT"
    assert payload["signals"][0]["is_stale"] is True


def test_latest_signals_api_fails_closed_on_corrupt_store():
    client = main.app.test_client()
    with patch.object(
        main.dashboard_store, "load_latest_signals",
        side_effect=RuntimeError("corrupt dashboard store"),
    ):
        response = client.get("/api/latest-signals")
    assert response.status_code == 503
    assert response.get_json()["success"] is False
