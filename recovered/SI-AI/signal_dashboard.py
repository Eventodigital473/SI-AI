"""Safe local persistence for the SI-AI signal dashboard."""

import json
import math
import os
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


BASE_DIR = Path(__file__).resolve().parent
LATEST_SIGNALS_FILE = BASE_DIR / "si_ai_latest_signals_state.json"
STORE_VERSION = 1
STALE_AFTER_SECONDS = 2 * 60 * 60


def parse_timestamp(value: Any):
    if not isinstance(value, str) or not value.strip():
        return None
    try:
        parsed = datetime.fromisoformat(value.strip().replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        return None
    return parsed.astimezone(timezone.utc)


def load_latest_signals():
    if not LATEST_SIGNALS_FILE.exists():
        return {}
    try:
        with LATEST_SIGNALS_FILE.open("r", encoding="utf-8") as handle:
            payload = json.load(handle)
    except (OSError, json.JSONDecodeError) as exc:
        raise RuntimeError(
            f"Latest-signal store is unreadable; preserving it: {type(exc).__name__}"
        ) from exc

    if not isinstance(payload, dict) or payload.get("version") != STORE_VERSION:
        raise RuntimeError("Latest-signal store has an unsupported format")
    signals = payload.get("signals")
    if not isinstance(signals, dict):
        raise RuntimeError("Latest-signal store must contain a signals object")

    for key, record in signals.items():
        if (
            not isinstance(key, str)
            or not key.startswith("FUTURES|")
            or not isinstance(record, dict)
            or record.get("market") != "FUTURES"
            or not isinstance(record.get("symbol"), str)
            or record.get("signal") not in ("BUY", "SELL", "WAIT")
            or record.get("status") not in ("ACTIVE", "INVALIDATED")
        ):
            raise RuntimeError("Latest-signal store contains an invalid record")
    return signals


def save_latest_signals(signals):
    if not isinstance(signals, dict):
        raise ValueError("Latest signals must be a dictionary")
    payload = {
        "version": STORE_VERSION,
        "updated_at": datetime.now(timezone.utc).isoformat(),
        "signals": signals,
    }
    temporary_path = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            dir=BASE_DIR,
            prefix=".si_ai_latest_signals_",
            suffix=".tmp",
            delete=False,
        ) as handle:
            temporary_path = Path(handle.name)
            json.dump(payload, handle, ensure_ascii=False, indent=2, sort_keys=True)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary_path, LATEST_SIGNALS_FILE)
        temporary_path = None
    finally:
        if temporary_path is not None:
            try:
                temporary_path.unlink(missing_ok=True)
            except OSError:
                pass


def _finite_number(value):
    if isinstance(value, bool):
        return None
    try:
        result = float(value)
    except (TypeError, ValueError):
        return None
    return result if math.isfinite(result) else None


def make_signal_snapshot(
    market,
    symbol,
    signal,
    results,
    alert_text,
    previous_record=None,
    notification_sent=False,
    now=None,
):
    if market != "FUTURES" or signal not in ("BUY", "SELL", "WAIT"):
        raise ValueError("Unsupported market or signal for dashboard snapshot")
    if not isinstance(results, dict) or not isinstance(results.get("1h"), dict):
        raise ValueError("A valid 1h analysis is required")

    reference = results["1h"]
    previous_record = previous_record if isinstance(previous_record, dict) else {}
    current = now or datetime.now(timezone.utc)
    if current.tzinfo is None:
        raise ValueError("Snapshot time must be timezone-aware")
    current_text = current.astimezone(timezone.utc).isoformat()

    analysis_time = reference.get("time_utc")
    if parse_timestamp(analysis_time) is None:
        analysis_time = current_text

    active = signal in ("BUY", "SELL")
    same_signal = previous_record.get("signal") == signal
    reasons = reference.get("reasons", [])
    if not isinstance(reasons, (list, tuple)):
        reasons = []

    fields = {
        "entry_price": "price",
        "stop_loss": "stop_loss",
        "take_profit": "take_profit",
        "reward_risk": "reward_risk",
        "leverage": "recommended_leverage",
        "position_size": "paper_quantity",
        "notional_usdt": "paper_notional_usdt",
        "margin_usdt": "paper_margin_required_usdt",
        "margin_budget_usdt": "paper_margin_budget_usdt",
        "gross_risk_usdt": "paper_risk_usdt",
        "risk_usdt": "paper_total_risk_usdt",
        "estimated_fees_usdt": "paper_estimated_fees_usdt",
        "estimated_slippage_usdt": "paper_estimated_slippage_usdt",
        "estimated_net_reward_usdt": "paper_estimated_net_reward_usdt",
    }
    snapshot = {
        "market": market,
        "symbol": symbol,
        "signal": signal,
        "side": ("LONG" if signal == "BUY" else "SHORT") if active else None,
        "status": "ACTIVE" if active else "INVALIDATED",
        "created_at": (
            previous_record.get("created_at", current_text)
            if same_signal else current_text
        ),
        "last_confirmed_at": analysis_time,
        "notification_sent_at": (
            current_text if notification_sent
            else previous_record.get("notification_sent_at")
        ),
        "timeframe_1h": str(reference.get("signal", "WAIT")),
        "timeframe_4h": str(
            (results.get("4h") or {}).get("signal", "WAIT")
        ),
        "alert_text": str(alert_text)[:12000],
        "reasons": [str(reason)[:300] for reason in reasons[:3]],
    }
    for output_name, source_name in fields.items():
        snapshot[output_name] = (
            _finite_number(reference.get(source_name)) if active else None
        )
    return snapshot
