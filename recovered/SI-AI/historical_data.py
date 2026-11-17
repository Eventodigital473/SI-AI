"""Public-only historical OHLCV ingestion and integrity-checked local datasets.

No private API credentials or order endpoints are used. Dataset files are local
research artifacts and should not be committed to the repository.
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


DATA_DIR = Path(__file__).resolve().parent / "data" / "historical"
SCHEMA_VERSION = 1
MAX_PAGE_LIMIT = 1000


def _integer_timestamp(value, name: str) -> int:
    if isinstance(value, bool):
        raise ValueError(f"{name} must be an integer millisecond timestamp")
    try:
        numeric = float(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{name} must be numeric") from exc
    if not math.isfinite(numeric) or not numeric.is_integer() or numeric <= 0:
        raise ValueError(f"{name} must be a positive integer millisecond timestamp")
    return int(numeric)


def _normalize_candle(row, index: int) -> List[float]:
    if not isinstance(row, (list, tuple)) or len(row) < 6:
        raise ValueError(f"Invalid OHLCV row at index {index}")
    values = []
    for column, value in enumerate(row[:6]):
        if isinstance(value, bool):
            raise ValueError(f"Non-numeric OHLCV value at row {index}")
        try:
            number = float(value)
        except (TypeError, ValueError) as exc:
            raise ValueError(f"Non-numeric OHLCV value at row {index}") from exc
        if not math.isfinite(number):
            raise ValueError(f"Non-finite OHLCV value at row {index}")
        values.append(number)

    timestamp, open_price, high, low, close, volume = values
    if timestamp <= 0 or not timestamp.is_integer():
        raise ValueError(f"Invalid candle timestamp at row {index}")
    if min(open_price, high, low, close) <= 0 or volume < 0:
        raise ValueError(f"Invalid OHLCV price or volume at row {index}")
    if high < max(open_price, close, low) or low > min(open_price, close, high):
        raise ValueError(f"Invalid OHLC relationship at row {index}")
    return [int(timestamp), open_price, high, low, close, volume]


def _resolve_exchange_symbol(exchange, market: str, symbol: str) -> str:
    if not isinstance(symbol, str) or symbol != symbol.strip() or symbol.count("/") != 1:
        raise ValueError("symbol must be a canonical BASE/USDT string")
    base, quote = symbol.split("/", 1)
    if not base or quote != "USDT" or symbol != symbol.upper():
        raise ValueError("Only canonical uppercase BASE/USDT symbols are supported")

    exchange.load_markets()
    candidate = symbol
    if market == "FUTURES" and candidate not in exchange.markets:
        candidate = f"{base}/{quote}:{quote}"

    metadata = exchange.markets.get(candidate)
    if not isinstance(metadata, dict):
        raise ValueError(f"{symbol} is not listed on the selected Binance market")
    # Historical research may include delisted markets to reduce survivorship
    # bias, but the exchange must explicitly identify their status as boolean.
    if not isinstance(metadata.get("active"), bool) or metadata.get("quote") != "USDT":
        raise ValueError(f"{symbol} metadata does not confirm USDT quote and active/inactive status")

    if market == "SPOT" and metadata.get("spot") is not True:
        raise ValueError(f"{symbol} is not a Binance spot market")
    if market == "FUTURES" and not (
        metadata.get("swap") is True
        and metadata.get("linear") is True
        and metadata.get("settle") == "USDT"
    ):
        raise ValueError(f"{symbol} is not a linear USDT-settled perpetual market")
    return candidate


def download_ohlcv(
    market: str,
    symbol: str,
    timeframe: str,
    start_ms: int,
    end_ms: int,
    *,
    exchange=None,
    limit: int = MAX_PAGE_LIMIT,
    max_pages: int = 10000,
    now_ms: Optional[int] = None,
) -> List[list]:
    """Download closed candles in [start_ms, end_ms), with guarded pagination."""
    if market not in smc.MARKETS:
        raise ValueError("market must be SPOT or FUTURES")
    interval_ms = smc.TIMEFRAME_MILLISECONDS.get(timeframe)
    if interval_ms is None:
        raise ValueError("Unsupported timeframe")
    start = _integer_timestamp(start_ms, "start_ms")
    end = _integer_timestamp(end_ms, "end_ms")
    if end <= start:
        raise ValueError("end_ms must be greater than start_ms")
    if isinstance(limit, bool) or not isinstance(limit, int) or not 1 <= limit <= MAX_PAGE_LIMIT:
        raise ValueError(f"limit must be an integer between 1 and {MAX_PAGE_LIMIT}")
    if isinstance(max_pages, bool) or not isinstance(max_pages, int) or max_pages < 1:
        raise ValueError("max_pages must be a positive integer")

    client = exchange or smc.EXCHANGES[market]
    exchange_symbol = _resolve_exchange_symbol(client, market, symbol)
    current_ms = (
        _integer_timestamp(now_ms, "now_ms")
        if now_ms is not None
        else _integer_timestamp(client.milliseconds(), "exchange current time")
    )

    collected = []
    last_timestamp = None
    cursor = start
    reached_end = False

    for _page in range(max_pages):
        batch = client.fetch_ohlcv(
            exchange_symbol,
            timeframe=timeframe,
            since=cursor,
            limit=limit,
        )
        if not batch:
            break

        normalized = [
            _normalize_candle(row, index)
            for index, row in enumerate(batch)
        ]
        for index in range(1, len(normalized)):
            if normalized[index][0] <= normalized[index - 1][0]:
                raise ValueError("Exchange returned duplicate or unordered candle timestamps")

        raw_last_timestamp = normalized[-1][0]
        if raw_last_timestamp < cursor:
            raise RuntimeError("OHLCV pagination did not advance")

        for candle in normalized:
            timestamp = candle[0]
            if timestamp + interval_ms > end:
                reached_end = True
                break
            if timestamp < start:
                continue
            # Do not include a candle until its full timeframe has closed.
            if timestamp + interval_ms > current_ms:
                continue
            if last_timestamp is not None and timestamp <= last_timestamp:
                raise ValueError("Duplicate or unordered candles across pagination pages")
            collected.append(candle)
            last_timestamp = timestamp

        if reached_end or raw_last_timestamp >= end - interval_ms:
            break

        next_cursor = raw_last_timestamp + interval_ms
        if next_cursor <= cursor:
            raise RuntimeError("OHLCV pagination cursor failed to advance")
        cursor = next_cursor
    else:
        raise RuntimeError("Maximum OHLCV pagination pages exceeded")

    if not collected:
        raise ValueError("No fully closed historical candles were returned")
    return collected


def dataset_sha256(candles: List[list]) -> str:
    """Hash normalized OHLCV so equivalent integer/float inputs are identical."""
    normalized = [
        _normalize_candle(row, index)
        for index, row in enumerate(candles)
    ]
    if not normalized:
        raise ValueError("Cannot hash an empty historical dataset")
    for index in range(1, len(normalized)):
        if normalized[index][0] <= normalized[index - 1][0]:
            raise ValueError("Dataset timestamps must be strictly increasing")
    payload = json.dumps(
        normalized, separators=(",", ":"), allow_nan=False
    ).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def _atomic_json_write(path: Path, payload: Dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            dir=path.parent,
            prefix=f".{path.name}.",
            suffix=".tmp",
            delete=False,
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


def save_dataset(
    market: str,
    symbol: str,
    timeframe: str,
    candles: List[list],
    *,
    output_path: Optional[str | Path] = None,
    start_ms: Optional[int] = None,
    end_ms: Optional[int] = None,
) -> Path:
    if market not in smc.MARKETS or timeframe not in smc.TIMEFRAME_MILLISECONDS:
        raise ValueError("Invalid market or timeframe")
    if not isinstance(symbol, str) or symbol.count("/") != 1 or not symbol.endswith("/USDT"):
        raise ValueError("symbol must be a BASE/USDT string")
    normalized = [_normalize_candle(row, index) for index, row in enumerate(candles)]
    if not normalized:
        raise ValueError("Cannot save an empty dataset")
    for index in range(1, len(normalized)):
        if normalized[index][0] <= normalized[index - 1][0]:
            raise ValueError("Dataset timestamps must be strictly increasing")

    if symbol != symbol.strip() or symbol != symbol.upper() or symbol.count("/") != 1 or not symbol.split("/", 1)[0] or symbol.split("/", 1)[1] != "USDT":
        raise ValueError("symbol must be a canonical uppercase BASE/USDT string")
    interval_ms = smc.TIMEFRAME_MILLISECONDS[timeframe]
    start_value = _integer_timestamp(
        start_ms if start_ms is not None else normalized[0][0], "start_ms"
    )
    end_value = _integer_timestamp(
        end_ms if end_ms is not None else normalized[-1][0] + interval_ms,
        "end_ms",
    )
    if end_value <= start_value:
        raise ValueError("end_ms must be greater than start_ms")
    if normalized[0][0] < start_value or normalized[-1][0] + interval_ms > end_value:
        raise ValueError("Dataset candles fall outside the declared [start_ms, end_ms) range")

    digest = dataset_sha256(normalized)
    path = Path(output_path) if output_path is not None else (
        DATA_DIR / market.lower()
        / f"{symbol.replace('/', '-')}_{timeframe}_{normalized[0][0]}_{normalized[-1][0]}.json"
    )
    payload = {
        "schema_version": SCHEMA_VERSION,
        "market": market,
        "symbol": symbol,
        "timeframe": timeframe,
        "start_ms": start_value,
        "end_ms": end_value,
        "downloaded_at_utc": datetime.now(timezone.utc).isoformat(),
        "candle_count": len(normalized),
        "data_sha256": digest,
        "candles": normalized,
        "automatic_orders": False,
    }
    _atomic_json_write(path, payload)
    return path


def load_dataset(path: str | Path) -> Dict:
    dataset_path = Path(path)
    with dataset_path.open("r", encoding="utf-8") as handle:
        payload = json.load(handle)
    if not isinstance(payload, dict) or payload.get("schema_version") != SCHEMA_VERSION:
        raise ValueError("Unsupported historical dataset schema")
    candles = payload.get("candles")
    if not isinstance(candles, list) or not candles:
        raise ValueError("Historical dataset has no candles")
    market = payload.get("market")
    symbol = payload.get("symbol")
    timeframe = payload.get("timeframe")
    if market not in smc.MARKETS or timeframe not in smc.TIMEFRAME_MILLISECONDS:
        raise ValueError("Historical dataset has invalid market or timeframe metadata")
    if (
        not isinstance(symbol, str) or symbol != symbol.strip()
        or symbol != symbol.upper() or symbol.count("/") != 1
        or not symbol.split("/", 1)[0] or symbol.split("/", 1)[1] != "USDT"
    ):
        raise ValueError("Historical dataset has invalid symbol metadata")
    start_value = _integer_timestamp(payload.get("start_ms"), "dataset start_ms")
    end_value = _integer_timestamp(payload.get("end_ms"), "dataset end_ms")
    if end_value <= start_value:
        raise ValueError("Historical dataset has an invalid time range")

    normalized = [_normalize_candle(row, index) for index, row in enumerate(candles)]
    for index in range(1, len(normalized)):
        if normalized[index][0] <= normalized[index - 1][0]:
            raise ValueError("Historical dataset timestamps are not strictly increasing")
    interval_ms = smc.TIMEFRAME_MILLISECONDS[timeframe]
    if normalized[0][0] < start_value or normalized[-1][0] + interval_ms > end_value:
        raise ValueError("Historical dataset candles fall outside declared time range")
    digest = dataset_sha256(normalized)
    if payload.get("data_sha256") != digest:
        raise ValueError("Historical dataset SHA-256 mismatch")
    if payload.get("candle_count") != len(normalized):
        raise ValueError("Historical dataset candle count mismatch")
    payload["candles"] = normalized
    return payload


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Download public Binance historical OHLCV for SI-AI research"
    )
    parser.add_argument("--market", required=True, choices=("SPOT", "FUTURES"))
    parser.add_argument("--symbol", required=True, help="Canonical symbol, e.g. BTC/USDT")
    parser.add_argument("--timeframe", required=True, choices=tuple(smc.TIMEFRAME_MILLISECONDS))
    parser.add_argument("--start-ms", required=True, type=int)
    parser.add_argument("--end-ms", required=True, type=int, help="Exclusive end timestamp in milliseconds")
    parser.add_argument("--output", default=None, help="Optional JSON output path")
    args = parser.parse_args()

    candles = download_ohlcv(
        args.market, args.symbol, args.timeframe, args.start_ms, args.end_ms
    )
    path = save_dataset(
        args.market, args.symbol, args.timeframe, candles,
        output_path=args.output, start_ms=args.start_ms, end_ms=args.end_ms,
    )
    print(f"Saved {len(candles)} closed candles to {path}")
    print(f"Dataset SHA-256: {dataset_sha256(candles)}")
    print("Public data only. No private credentials or orders.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
