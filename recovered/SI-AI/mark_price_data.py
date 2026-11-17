"""Public Binance USD-M historical mark-price candles with integrity checks.

Mark-price OHLC is required for liquidation-event research; last-trade OHLCV
must never be substituted. This module uses the public market-data endpoint
and never reads credentials or calls private account/order endpoints.
"""
from __future__ import annotations

import hashlib
import json
import math
import os
import tempfile
from datetime import datetime, timezone
from pathlib import Path

import requests

import SI_AI_smc as smc
import historical_data


BASE_URL = "https://fapi.binance.com/fapi/v1/markPriceKlines"
DATA_DIR = Path(__file__).resolve().parent / "data" / "historical" / "mark_price"
SCHEMA_VERSION = 1
PAGE_LIMIT = 1500
REQUEST_TIMEOUT_SECONDS = 20


def _timestamp(value, name):
    return historical_data._integer_timestamp(value, name)


def _normalize_row(row, index, interval_ms):
    if not isinstance(row, (list, tuple)) or len(row) < 7:
        raise ValueError(f"Invalid mark-price kline at index {index}")
    timestamp = _timestamp(row[0], f"mark timestamp at row {index}")
    values = []
    for name, value in zip(("open", "high", "low", "close"), row[1:5]):
        if isinstance(value, bool):
            raise ValueError(f"Invalid mark-price {name} at row {index}")
        try:
            number = float(value)
        except (TypeError, ValueError) as exc:
            raise ValueError(f"Invalid mark-price {name} at row {index}") from exc
        if not math.isfinite(number) or number <= 0:
            raise ValueError(f"Invalid mark-price {name} at row {index}")
        values.append(number)
    op, high, low, close = values
    if high < max(op, low, close) or low > min(op, high, close):
        raise ValueError(f"Invalid mark-price OHLC relationship at row {index}")
    close_time = _timestamp(row[6], f"mark close time at row {index}")
    if close_time != timestamp + interval_ms - 1:
        raise ValueError(f"Mark-price close time mismatch at row {index}")
    return [timestamp, op, high, low, close, 0.0]


def mark_price_sha256(candles, timeframe):
    interval_ms = smc.TIMEFRAME_MILLISECONDS.get(timeframe)
    if interval_ms is None:
        raise ValueError("Unsupported timeframe")
    normalized = [
        _normalize_row(row, index, interval_ms)
        for index, row in enumerate(candles)
    ]
    if not normalized:
        raise ValueError("Cannot hash an empty mark-price dataset")
    smc.validate_candle_continuity(normalized, timeframe)
    payload = json.dumps(normalized, separators=(",", ":"), allow_nan=False).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def _infer_interval(candles):
    if not isinstance(candles, list) or len(candles) < 2:
        raise ValueError("At least two mark-price candles are required to infer interval")
    delta = int(candles[1][0]) - int(candles[0][0])
    if delta not in set(smc.TIMEFRAME_MILLISECONDS.values()):
        raise ValueError("Unsupported mark-price candle interval")
    return delta


def download_mark_price_ohlcv(
    symbol, timeframe, start_ms, end_ms, *, http_get=None,
    limit=PAGE_LIMIT, max_pages=10000, now_ms=None,
):
    """Download closed Binance USD-M mark-price candles in [start_ms, end_ms)."""
    if not isinstance(symbol, str) or symbol != symbol.strip() or symbol != symbol.upper():
        raise ValueError("symbol must be canonical uppercase BASE/USDT")
    if symbol.count("/") != 1 or not symbol.split("/", 1)[0] or symbol.split("/", 1)[1] != "USDT":
        raise ValueError("Only canonical BASE/USDT symbols are supported")
    interval_ms = smc.TIMEFRAME_MILLISECONDS.get(timeframe)
    if interval_ms is None:
        raise ValueError("Unsupported timeframe")
    start = _timestamp(start_ms, "start_ms")
    end = _timestamp(end_ms, "end_ms")
    if end <= start:
        raise ValueError("end_ms must be greater than start_ms")
    if isinstance(limit, bool) or not isinstance(limit, int) or not 1 <= limit <= PAGE_LIMIT:
        raise ValueError(f"limit must be an integer between 1 and {PAGE_LIMIT}")
    if isinstance(max_pages, bool) or not isinstance(max_pages, int) or max_pages < 1:
        raise ValueError("max_pages must be a positive integer")
    current = _timestamp(now_ms, "now_ms") if now_ms is not None else int(datetime.now(timezone.utc).timestamp() * 1000)
    getter = http_get or requests.get
    api_symbol = symbol.replace("/", "")
    cursor = start
    collected = []
    previous = None

    for _ in range(max_pages):
        response = getter(
            BASE_URL,
            params={
                "symbol": api_symbol,
                "interval": timeframe,
                "startTime": cursor,
                "endTime": end - 1,
                "limit": limit,
            },
            timeout=REQUEST_TIMEOUT_SECONDS,
        )
        response.raise_for_status()
        batch = response.json()
        if not isinstance(batch, list):
            raise ValueError("Binance mark-price response must be a list")
        if not batch:
            break
        normalized = [_normalize_row(row, i, interval_ms) for i, row in enumerate(batch)]
        for i in range(1, len(normalized)):
            if normalized[i][0] <= normalized[i - 1][0]:
                raise ValueError("Binance returned duplicate or unordered mark-price candles")
        last_raw = normalized[-1][0]
        if last_raw < cursor:
            raise RuntimeError("Mark-price pagination did not advance")
        for candle in normalized:
            ts = candle[0]
            if ts < start:
                continue
            if ts + interval_ms > end:
                continue
            if ts + interval_ms > current:
                continue
            if previous is not None and ts <= previous:
                raise ValueError("Duplicate or unordered mark-price candles across pages")
            collected.append(candle)
            previous = ts
        next_cursor = last_raw + interval_ms
        if next_cursor <= cursor:
            raise RuntimeError("Mark-price pagination cursor failed to advance")
        if last_raw + interval_ms >= end or len(batch) < limit:
            break
        cursor = next_cursor
    else:
        raise RuntimeError("Maximum mark-price pagination pages exceeded")

    if not collected:
        raise ValueError("No fully closed historical mark-price candles were returned")
    smc.validate_candle_continuity(collected, timeframe)
    return collected


def save_mark_price_dataset(symbol, timeframe, candles, *, output_path=None,
                            start_ms=None, end_ms=None):
    if not isinstance(symbol, str) or symbol != symbol.strip() or symbol != symbol.upper() or symbol.count("/") != 1 or not symbol.endswith("/USDT"):
        raise ValueError("symbol must be canonical uppercase BASE/USDT")
    interval_ms = smc.TIMEFRAME_MILLISECONDS.get(timeframe)
    if interval_ms is None:
        raise ValueError("Unsupported timeframe")
    normalized = [_normalize_row(row, i, interval_ms) for i, row in enumerate(candles)]
    if not normalized:
        raise ValueError("Cannot save an empty mark-price dataset")
    for i in range(1, len(normalized)):
        if normalized[i][0] - normalized[i - 1][0] != interval_ms:
            raise ValueError("Mark-price candles must be strictly continuous")
    start = _timestamp(start_ms if start_ms is not None else normalized[0][0], "start_ms")
    end = _timestamp(end_ms if end_ms is not None else normalized[-1][0] + interval_ms, "end_ms")
    if end <= start or normalized[0][0] < start or normalized[-1][0] + interval_ms > end:
        raise ValueError("Mark-price candles fall outside declared [start_ms, end_ms) range")
    digest = hashlib.sha256(json.dumps(normalized, separators=(",", ":"), allow_nan=False).encode()).hexdigest()
    path = Path(output_path) if output_path is not None else (
        DATA_DIR / f"{symbol.replace('/', '-')}_{timeframe}_{start}_{end}.json"
    )
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "schema_version": SCHEMA_VERSION,
        "source": "BINANCE_USDM_MARK_PRICE_KLINES",
        "market": "FUTURES",
        "symbol": symbol,
        "timeframe": timeframe,
        "start_ms": start,
        "end_ms": end,
        "downloaded_at_utc": datetime.now(timezone.utc).isoformat(),
        "candle_count": len(normalized),
        "data_sha256": digest,
        "candles": normalized,
        "automatic_orders": False,
    }
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", dir=path.parent,
                                         prefix=f".{path.name}.", suffix=".tmp",
                                         delete=False) as handle:
            temporary = Path(handle.name)
            json.dump(payload, handle, indent=2, sort_keys=True, allow_nan=False)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
        temporary = None
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)
    return path


def load_mark_price_dataset(path):
    with Path(path).open("r", encoding="utf-8") as handle:
        payload = json.load(handle)
    if not isinstance(payload, dict) or payload.get("schema_version") != SCHEMA_VERSION:
        raise ValueError("Unsupported mark-price dataset schema")
    if payload.get("source") != "BINANCE_USDM_MARK_PRICE_KLINES" or payload.get("market") != "FUTURES":
        raise ValueError("Mark-price dataset source/market is invalid")
    symbol = payload.get("symbol")
    timeframe = payload.get("timeframe")
    interval_ms = smc.TIMEFRAME_MILLISECONDS.get(timeframe)
    if not isinstance(symbol, str) or symbol != symbol.upper() or symbol.count("/") != 1 or not symbol.endswith("/USDT") or interval_ms is None:
        raise ValueError("Mark-price dataset symbol/timeframe is invalid")
    candles = payload.get("candles")
    if not isinstance(candles, list) or not candles:
        raise ValueError("Mark-price dataset is empty")
    normalized = [_normalize_row(row, i, interval_ms) for i, row in enumerate(candles)]
    smc.validate_candle_continuity(normalized, timeframe)
    start = _timestamp(payload.get("start_ms"), "dataset start_ms")
    end = _timestamp(payload.get("end_ms"), "dataset end_ms")
    if normalized[0][0] < start or normalized[-1][0] + interval_ms > end:
        raise ValueError("Mark-price candles fall outside declared time range")
    digest = hashlib.sha256(json.dumps(normalized, separators=(",", ":"), allow_nan=False).encode()).hexdigest()
    if payload.get("data_sha256") != digest or payload.get("candle_count") != len(normalized):
        raise ValueError("Mark-price dataset integrity check failed")
    payload["candles"] = normalized
    return payload
