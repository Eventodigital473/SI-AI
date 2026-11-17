"""Timestamped Binance USD-M funding history with settlement mark prices.

Public market data only. Each event is valued using Binance's markPrice field
returned alongside the actual funding charge; candle-close proxies are rejected.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Optional

import SI_AI_smc as smc


SCHEMA_VERSION = 1
MAX_PAGE_LIMIT = 1000


def _timestamp(value, name):
    if isinstance(value, bool):
        raise ValueError(f"{name} must be an integer millisecond timestamp")
    try:
        number = float(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{name} must be numeric") from exc
    if not math.isfinite(number) or not number.is_integer() or number <= 0:
        raise ValueError(f"{name} must be a positive integer millisecond timestamp")
    return int(number)


def _finite(value, name):
    if isinstance(value, bool):
        raise ValueError(f"{name} must be finite numeric data")
    try:
        number = float(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{name} must be finite numeric data") from exc
    if not math.isfinite(number):
        raise ValueError(f"{name} must be finite numeric data")
    return number


def _resolve_symbol(exchange, symbol):
    if not isinstance(symbol, str) or symbol != symbol.strip() or symbol != symbol.upper():
        raise ValueError("symbol must be canonical uppercase BASE/USDT")
    parts = symbol.split("/")
    if len(parts) != 2 or not parts[0] or parts[1] != "USDT":
        raise ValueError("Only canonical BASE/USDT symbols are supported")
    exchange.load_markets()
    candidate = symbol if symbol in exchange.markets else f"{parts[0]}/USDT:USDT"
    market = exchange.markets.get(candidate)
    if not isinstance(market, dict):
        raise ValueError("Symbol is not listed on Binance USD-M Futures")
    if not (market.get("swap") is True and market.get("linear") is True
            and market.get("settle") == "USDT" and market.get("quote") == "USDT"):
        raise ValueError("Symbol is not a linear USDT-settled perpetual")
    if not isinstance(market.get("active"), bool):
        raise ValueError("Exchange metadata does not confirm market active/inactive status")
    return candidate


def normalize_funding_event(row, index=0):
    if not isinstance(row, dict):
        raise ValueError(f"Invalid funding event at index {index}")
    info = row.get("info")
    if not isinstance(info, dict):
        raise ValueError(f"Funding event {index} has no raw Binance info; exact markPrice cannot be verified")
    timestamp = _timestamp(row.get("timestamp", info.get("fundingTime")), "funding timestamp")
    raw_timestamp = _timestamp(info.get("fundingTime", timestamp), "raw fundingTime")
    if raw_timestamp != timestamp:
        raise ValueError("Unified and raw funding timestamps disagree")
    rate = _finite(row.get("fundingRate", info.get("fundingRate")), "funding rate")
    if abs(rate) >= 0.05:
        raise ValueError("Funding rate outside supported safety bounds")
    mark_price = _finite(info.get("markPrice", row.get("markPrice")), "funding settlement markPrice")
    if mark_price <= 0:
        raise ValueError("Funding settlement markPrice must be positive")
    symbol_id = info.get("symbol")
    if symbol_id is not None and (not isinstance(symbol_id, str) or not symbol_id.endswith("USDT")):
        raise ValueError("Funding event raw symbol is not a USDT-margined contract")
    return {
        "timestamp": timestamp,
        "funding_rate": rate,
        "mark_price": mark_price,
        "rate_type": str(info.get("rateType", "Regular")),
    }


def validate_normalized_funding_events(events):
    if not isinstance(events, list):
        raise ValueError("funding events must be a list")
    clean = []
    previous = None
    for index, event in enumerate(events):
        if not isinstance(event, dict):
            raise ValueError(f"Invalid normalized funding event at index {index}")
        timestamp = _timestamp(event.get("timestamp"), "funding timestamp")
        rate = _finite(event.get("funding_rate"), "funding rate")
        mark = _finite(event.get("mark_price"), "funding mark price")
        if abs(rate) >= 0.05 or mark <= 0:
            raise ValueError("Funding rate or settlement mark price outside supported bounds")
        if previous is not None and timestamp <= previous:
            raise ValueError("Funding timestamps must be strictly increasing")
        clean.append({
            "timestamp": timestamp,
            "funding_rate": rate,
            "mark_price": mark,
            "rate_type": str(event.get("rate_type", "Regular")),
        })
        previous = timestamp
    return clean


def funding_events_sha256(events: List[Dict]) -> str:
    normalized = [normalize_funding_event({
        "timestamp": event["timestamp"],
        "fundingRate": event["funding_rate"],
        "info": {
            "fundingTime": event["timestamp"],
            "fundingRate": event["funding_rate"],
            "markPrice": event["mark_price"],
            "rateType": event.get("rate_type", "Regular"),
        },
    }, index) for index, event in enumerate(events)]
    if not normalized:
        raise ValueError("Cannot hash an empty funding event dataset")
    for index in range(1, len(normalized)):
        if normalized[index]["timestamp"] <= normalized[index - 1]["timestamp"]:
            raise ValueError("Funding timestamps must be strictly increasing")
    payload = json.dumps(normalized, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()
    return hashlib.sha256(payload).hexdigest()


def download_funding_history(
    market: str,
    symbol: str,
    start_ms: int,
    end_ms: int,
    *,
    exchange=None,
    limit: int = MAX_PAGE_LIMIT,
    max_pages: int = 10000,
) -> List[Dict]:
    """Fetch Binance funding events in [start_ms, end_ms), preserving markPrice."""
    if market != "FUTURES":
        raise ValueError("Funding history supports FUTURES only")
    start = _timestamp(start_ms, "start_ms")
    end = _timestamp(end_ms, "end_ms")
    if end <= start:
        raise ValueError("end_ms must be greater than start_ms")
    if isinstance(limit, bool) or not isinstance(limit, int) or not 1 <= limit <= MAX_PAGE_LIMIT:
        raise ValueError(f"limit must be an integer between 1 and {MAX_PAGE_LIMIT}")
    if isinstance(max_pages, bool) or not isinstance(max_pages, int) or max_pages < 1:
        raise ValueError("max_pages must be a positive integer")

    client = exchange or smc.EXCHANGES[market]
    exchange_symbol = _resolve_symbol(client, symbol)
    if not callable(getattr(client, "fetch_funding_rate_history", None)):
        raise RuntimeError("Installed CCXT Binance client lacks fetch_funding_rate_history")

    events = []
    cursor = start
    previous_timestamp = None
    for _ in range(max_pages):
        batch = client.fetch_funding_rate_history(
            exchange_symbol, since=cursor, limit=limit, params={"until": end - 1}
        )
        if not batch:
            break
        normalized = [normalize_funding_event(row, i) for i, row in enumerate(batch)]
        for index in range(1, len(normalized)):
            if normalized[index]["timestamp"] <= normalized[index - 1]["timestamp"]:
                raise ValueError("Exchange returned duplicate or unordered funding events")
        expected_id = symbol.replace("/", "") 
        for event, raw in zip(normalized, batch):
            raw_symbol = raw.get("info", {}).get("symbol")
            if raw_symbol is not None and raw_symbol != expected_id:
                raise ValueError("Funding event symbol does not match requested contract")
            timestamp = event["timestamp"]
            if timestamp < cursor:
                raise RuntimeError("Funding pagination returned an event before its cursor")
            if timestamp >= end:
                continue
            if previous_timestamp is not None and timestamp <= previous_timestamp:
                raise ValueError("Duplicate or unordered funding events across pages")
            if timestamp >= start:
                events.append(event)
                previous_timestamp = timestamp
        last_timestamp = normalized[-1]["timestamp"]
        if last_timestamp >= end - 1 or len(batch) < limit:
            break
        next_cursor = last_timestamp + 1
        if next_cursor <= cursor:
            raise RuntimeError("Funding pagination cursor failed to advance")
        cursor = next_cursor
    else:
        raise RuntimeError("Maximum funding pagination pages exceeded")

    if not events:
        raise ValueError("No timestamped funding events with settlement mark prices were returned")
    return events


def funding_cost_for_trade(events, side, quantity, entry_timestamp, exit_timestamp):
    """Return signed funding cost; positive means paid, negative means received.

    Exact timestamp ties at entry/exit are charged without assuming a funding
    credit and flagged ambiguous. The profitability gate will not certify a
    report containing such a tie until its position-snapshot ordering is resolved.
    """
    if side not in ("LONG", "SHORT"):
        raise ValueError("side must be LONG or SHORT")
    qty = _finite(quantity, "quantity")
    if qty <= 0:
        raise ValueError("quantity must be positive")
    entry = _timestamp(entry_timestamp, "entry_timestamp")
    exit_ = _timestamp(exit_timestamp, "exit_timestamp")
    if exit_ < entry:
        raise ValueError("exit_timestamp cannot precede entry_timestamp")
    cost = 0.0
    count = 0
    ambiguous = 0
    for event in events:
        timestamp = _timestamp(event.get("timestamp"), "funding timestamp")
        if not entry <= timestamp <= exit_:
            continue
        rate = _finite(event.get("funding_rate"), "funding rate")
        mark = _finite(event.get("mark_price"), "funding mark price")
        if mark <= 0:
            raise ValueError("Funding mark price must be positive")
        signed_cost = qty * mark * rate * (1.0 if side == "LONG" else -1.0)
        if timestamp in (entry, exit_):
            ambiguous += 1
            signed_cost = max(0.0, signed_cost)
        cost += signed_cost
        count += 1
    return {
        "funding_cost_usdt": round(cost, 12),
        "funding_event_count": count,
        "funding_boundary_ambiguities": ambiguous,
    }


def _atomic_write(path: Path, payload: Dict):
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w", encoding="utf-8", dir=path.parent,
            prefix=f".{path.name}.", suffix=".tmp", delete=False
        ) as handle:
            temporary = Path(handle.name)
            json.dump(payload, handle, indent=2, sort_keys=True, allow_nan=False)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
        temporary = None
    finally:
        if temporary is not None:
            try:
                temporary.unlink(missing_ok=True)
            except OSError:
                pass


def save_funding_dataset(market, symbol, events, start_ms, end_ms, output_path):
    if market != "FUTURES":
        raise ValueError("Funding datasets support FUTURES only")
    start = _timestamp(start_ms, "start_ms")
    end = _timestamp(end_ms, "end_ms")
    if end <= start or not events:
        raise ValueError("A non-empty funding dataset and valid time range are required")
    if not isinstance(symbol, str) or symbol != symbol.strip() or symbol != symbol.upper() or len(symbol.split("/")) != 2 or not symbol.endswith("/USDT") or not symbol.split("/")[0]:
        raise ValueError("symbol must be canonical uppercase BASE/USDT")
    normalized = []
    for index, event in enumerate(events):
        item = normalize_funding_event({
            "timestamp": event["timestamp"],
            "fundingRate": event["funding_rate"],
            "info": {
                "fundingTime": event["timestamp"],
                "fundingRate": event["funding_rate"],
                "markPrice": event["mark_price"],
                "rateType": event.get("rate_type", "Regular"),
            },
        }, index)
        if not start <= item["timestamp"] < end:
            raise ValueError("Funding event falls outside declared [start_ms, end_ms) range")
        normalized.append(item)
    digest = funding_events_sha256(normalized)
    payload = {
        "schema_version": SCHEMA_VERSION,
        "market": market,
        "symbol": symbol,
        "start_ms": start,
        "end_ms": end,
        "downloaded_at_utc": datetime.now(timezone.utc).isoformat(),
        "event_count": len(normalized),
        "data_sha256": digest,
        "events": normalized,
        "source": "Binance USD-M GET /fapi/v1/fundingRate; raw markPrice per funding charge",
        "automatic_orders": False,
    }
    path = Path(output_path)
    _atomic_write(path, payload)
    return path


def load_funding_dataset(path):
    with Path(path).open("r", encoding="utf-8") as handle:
        payload = json.load(handle)
    if not isinstance(payload, dict) or payload.get("schema_version") != SCHEMA_VERSION:
        raise ValueError("Unsupported funding dataset schema")
    if payload.get("market") != "FUTURES":
        raise ValueError("Funding dataset must be FUTURES")
    events = payload.get("events")
    if not isinstance(events, list) or not events:
        raise ValueError("Funding dataset has no events")
    symbol = payload.get("symbol")
    if not isinstance(symbol, str) or symbol != symbol.strip() or symbol != symbol.upper() or len(symbol.split("/")) != 2 or not symbol.endswith("/USDT") or not symbol.split("/")[0]:
        raise ValueError("Funding dataset has invalid symbol metadata")
    start = _timestamp(payload.get("start_ms"), "dataset start_ms")
    end = _timestamp(payload.get("end_ms"), "dataset end_ms")
    if end <= start:
        raise ValueError("Funding dataset has invalid time range")
    normalized = []
    for index, event in enumerate(events):
        normalized.append(normalize_funding_event({
            "timestamp": event.get("timestamp"),
            "fundingRate": event.get("funding_rate"),
            "info": {
                "fundingTime": event.get("timestamp"),
                "fundingRate": event.get("funding_rate"),
                "markPrice": event.get("mark_price"),
                "rateType": event.get("rate_type", "Regular"),
            },
        }, index))
    expected_id = symbol.replace("/", "")
    for raw, event in zip(events, normalized):
        raw_symbol = raw.get("symbol")
        if raw_symbol is not None and raw_symbol != expected_id:
            raise ValueError("Funding dataset event symbol does not match dataset symbol")
        if not start <= event["timestamp"] < end:
            raise ValueError("Funding event falls outside declared time range")
    if payload.get("event_count") != len(normalized):
        raise ValueError("Funding event count mismatch")
    if payload.get("data_sha256") != funding_events_sha256(normalized):
        raise ValueError("Funding dataset SHA-256 mismatch")
    payload["events"] = normalized
    return payload


def main():
    parser = argparse.ArgumentParser(
        description="Download public Binance USD-M historical funding events with exact settlement mark prices"
    )
    parser.add_argument("--market", required=True, choices=("FUTURES",))
    parser.add_argument("--symbol", required=True, help="Canonical symbol, e.g. BTC/USDT")
    parser.add_argument("--start-ms", required=True, type=int)
    parser.add_argument("--end-ms", required=True, type=int, help="Exclusive end timestamp in milliseconds")
    parser.add_argument("--output", required=True, help="Funding dataset JSON output path")
    args = parser.parse_args()

    events = download_funding_history(
        args.market, args.symbol, args.start_ms, args.end_ms
    )
    path = save_funding_dataset(
        args.market, args.symbol, events,
        args.start_ms, args.end_ms, args.output,
    )
    print(f"Saved {len(events)} timestamped funding events to {path}")
    print(f"Funding dataset SHA-256: {funding_events_sha256(events)}")
    print("Each event retains Binance's markPrice associated with that funding charge.")
    print("Public market data only. No private credentials or orders.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
