"""Offline-safe Binance Vision USD-M archive research runner.

Uses Binance's public ZIP archive (not restricted Futures REST endpoints).
Funding rates are archived for audit but NOT applied because Vision funding
files do not contain the exact settlement markPrice required by SI-AI's
certification contract. Profitability therefore remains INCONCLUSIVE.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import io
import json
import math
import re
import zipfile
from datetime import datetime, timedelta, timezone
from pathlib import Path

import requests

import SI_AI_smc as smc
import historical_data
import historical_backtest
import mark_price_data


BASE_URL = "https://data.binance.vision/data/futures/um"
TIMEFRAMES = ("15m", "1h", "4h", "1d")
MARK_TIMEFRAME = "1h"
MAX_SYMBOLS = 10
TIMEOUT_SECONDS = 90
DATA_DIR = Path(__file__).resolve().parent / "data" / "historical" / "binance_vision"
REPORT_DIR = Path(__file__).resolve().parent / "data" / "reports"


def _months_between(start, end):
    current = start.replace(day=1)
    while current < end:
        yield current.strftime("%Y-%m")
        if current.month == 12:
            current = current.replace(year=current.year + 1, month=1)
        else:
            current = current.replace(month=current.month + 1)


def _download_verified_zip(relative_path, *, get=None):
    if not isinstance(relative_path, str) or relative_path.startswith("/") or ".." in relative_path.split("/"):
        raise ValueError("Invalid Binance Vision archive path")
    getter = get or requests.get
    url = f"{BASE_URL}/{relative_path}"
    response = getter(url, timeout=TIMEOUT_SECONDS)
    response.raise_for_status()
    archive_bytes = response.content
    if not archive_bytes:
        raise ValueError(f"Empty Binance Vision archive: {relative_path}")

    checksum_response = getter(f"{url}.CHECKSUM", timeout=TIMEOUT_SECONDS)
    checksum_response.raise_for_status()
    checksum_text = checksum_response.text.strip()
    match = re.search(r"(?<![0-9a-fA-F])[0-9a-fA-F]{64}(?![0-9a-fA-F])", checksum_text)
    if not match:
        raise ValueError(f"Missing SHA-256 checksum for {relative_path}")
    actual = hashlib.sha256(archive_bytes).hexdigest()
    if actual.lower() != match.group(0).lower():
        raise ValueError(f"Binance Vision ZIP checksum mismatch: {relative_path}")

    with zipfile.ZipFile(io.BytesIO(archive_bytes)) as archive:
        members = [name for name in archive.namelist() if name.lower().endswith(".csv")]
        if len(members) != 1:
            raise ValueError(f"Expected exactly one CSV in {relative_path}")
        with archive.open(members[0]) as raw:
            text = io.TextIOWrapper(raw, encoding="utf-8-sig", newline="")
            rows = list(csv.reader(text))
    if not rows:
        raise ValueError(f"CSV is empty in {relative_path}")
    return rows, actual


def _parse_numeric_rows(rows, *, expected_columns, label):
    parsed = []
    for index, row in enumerate(rows):
        if len(row) < expected_columns:
            raise ValueError(f"{label}: malformed CSV row {index}")
        try:
            values = [float(value) for value in row[:expected_columns]]
        except (TypeError, ValueError):
            if index == 0:
                # Skip only the documented Binance CSV headers. Treating any
                # malformed first record as a header could silently discard a
                # real first funding event or candle.
                first_cell = str(row[0]).strip().lower()
                expected_header = "calc_time" if expected_columns == 3 else "open_time"
                if first_cell == expected_header:
                    continue
            raise ValueError(f"{label}: non-numeric CSV row {index}")
        if not all(math.isfinite(value) for value in values):
            raise ValueError(f"{label}: non-finite CSV row {index}")
        parsed.append(values)
    if not parsed:
        raise ValueError(f"{label}: no numeric data rows")
    return parsed


def _validate_candle_coverage(candles, timeframe, start_ms, end_ms):
    """Require exact requested start/end coverage after internal continuity checks."""
    interval_ms = smc.TIMEFRAME_MILLISECONDS.get(timeframe)
    if interval_ms is None:
        raise ValueError(f"Unsupported timeframe for archive coverage: {timeframe}")
    if (
        isinstance(start_ms, bool) or not isinstance(start_ms, int)
        or isinstance(end_ms, bool) or not isinstance(end_ms, int)
        or end_ms <= start_ms
        or start_ms % interval_ms
        or end_ms % interval_ms
        or (end_ms - start_ms) % interval_ms
    ):
        raise ValueError("Requested archive window must be positive and timeframe-aligned")
    expected_count = (end_ms - start_ms) // interval_ms
    if (
        not candles
        or candles[0][0] != start_ms
        or candles[-1][0] != end_ms - interval_ms
        or len(candles) != expected_count
    ):
        first = candles[0][0] if candles else None
        last = candles[-1][0] if candles else None
        raise ValueError(
            f"Incomplete Binance Vision {timeframe} archive coverage: "
            f"expected start={start_ms}, end={end_ms} exclusive, candles={expected_count}; "
            f"received first={first}, last={last}, candles={len(candles)}"
        )


def _load_monthly_candles(symbol, timeframe, start_ms, end_ms, months, *, mark=False):
    kind = "markPriceKlines" if mark else "klines"
    interval_ms = smc.TIMEFRAME_MILLISECONDS[timeframe]
    collected = {}
    archive_hashes = []
    raw_symbol = symbol.replace("/", "")

    for month in months:
        filename = f"{raw_symbol}-{timeframe}-{month}.zip"
        relative = f"monthly/{kind}/{raw_symbol}/{timeframe}/{filename}"
        rows, archive_hash = _download_verified_zip(relative)
        values = _parse_numeric_rows(
            rows, expected_columns=7 if mark else 12,
            label=f"{symbol} {timeframe} {kind} {month}",
        )
        archive_hashes.append({"month": month, "zip_sha256": archive_hash})
        for row in values:
            timestamp = int(row[0])
            if timestamp < start_ms or timestamp + interval_ms > end_ms:
                continue
            close_time = int(row[6])
            if close_time != timestamp + interval_ms - 1:
                raise ValueError(f"{kind} close-time mismatch for {symbol} {timeframe} at {timestamp}")
            candle = [
                timestamp, row[1], row[2], row[3], row[4],
                0.0 if mark else row[5],
            ]
            if timestamp in collected:
                raise ValueError(f"Duplicate archive candle: {symbol} {timeframe} {timestamp}")
            collected[timestamp] = candle

    candles = [collected[key] for key in sorted(collected)]
    if not candles:
        raise ValueError(f"No Binance Vision {kind} data for {symbol} {timeframe}")

    # Binance publishes daily markPriceKlines archives as well as monthly
    # archives. Use a checksum-verified daily file only to fill an identified
    # missing interval; never interpolate or synthesize a mark price.
    if mark and timeframe == "1h":
        interval_ms = smc.TIMEFRAME_MILLISECONDS[timeframe]
        missing = []
        for previous, current in zip(candles, candles[1:]):
            delta = current[0] - previous[0]
            if delta > interval_ms and delta % interval_ms == 0:
                missing.extend(range(previous[0] + interval_ms, current[0], interval_ms))
            elif delta != interval_ms:
                raise ValueError(
                    f"Irregular {kind} timestamps for {symbol} {timeframe}: "
                    f"{previous[0]} -> {current[0]} ({delta} ms)"
                )
        if missing:
            raw_symbol = symbol.replace("/", "")
            missing_by_day = {}
            for timestamp in missing:
                day = datetime.fromtimestamp(timestamp / 1000, timezone.utc).strftime("%Y-%m-%d")
                missing_by_day.setdefault(day, set()).add(timestamp)
            for day, required_timestamps in sorted(missing_by_day.items()):
                filename = f"{raw_symbol}-{timeframe}-{day}.zip"
                relative = f"daily/{kind}/{raw_symbol}/{timeframe}/{filename}"
                rows, archive_hash = _download_verified_zip(relative)
                values = _parse_numeric_rows(
                    rows, expected_columns=7,
                    label=f"{symbol} {timeframe} {kind} daily fallback {day}",
                )
                archive_hashes.append({
                    "date": day, "zip_sha256": archive_hash, "daily_gap_repair": True,
                })
                for row in values:
                    timestamp = int(row[0])
                    if timestamp not in required_timestamps:
                        continue
                    if int(row[6]) != timestamp + interval_ms - 1:
                        raise ValueError(
                            f"Daily mark-price close-time mismatch for {symbol} at {timestamp}"
                        )
                    collected[timestamp] = [
                        timestamp, row[1], row[2], row[3], row[4], 0.0,
                    ]
            candles = [collected[key] for key in sorted(collected)]

    try:
        smc.validate_candle_continuity(candles, timeframe)
    except ValueError as exc:
        interval_ms = smc.TIMEFRAME_MILLISECONDS[timeframe]
        gap = next(
            ((left[0], right[0], right[0] - left[0])
             for left, right in zip(candles, candles[1:])
             if right[0] - left[0] != interval_ms),
            None,
        )
        if gap:
            raise ValueError(
                f"Binance Vision {kind} coverage gap for {symbol} {timeframe}: "
                f"{gap[0]} -> {gap[1]} ({gap[2]} ms); daily archive fallback did not repair it"
            ) from exc
        raise
    _validate_candle_coverage(candles, timeframe, start_ms, end_ms)
    return candles, archive_hashes


def _load_monthly_funding_rates(symbol, months):
    raw_symbol = symbol.replace("/", "")
    events = []
    archive_hashes = []
    for month in months:
        filename = f"{raw_symbol}-fundingRate-{month}.zip"
        relative = f"monthly/fundingRate/{raw_symbol}/{filename}"
        rows, archive_hash = _download_verified_zip(relative)
        values = _parse_numeric_rows(
            rows, expected_columns=3,
            label=f"{symbol} fundingRate {month}",
        )
        archive_hashes.append({"month": month, "zip_sha256": archive_hash})
        for timestamp, interval_hours, rate in values:
            if timestamp <= 0 or not timestamp.is_integer():
                raise ValueError("Funding archive timestamp must be positive integer milliseconds")
            if interval_hours <= 0 or not interval_hours.is_integer():
                raise ValueError("Funding archive interval must be a positive integer hour count")
            if abs(rate) >= 0.05:
                raise ValueError("Funding archive rate exceeds supported safety bounds")
            events.append({
                "timestamp": int(timestamp),
                "funding_interval_hours": int(interval_hours),
                "funding_rate": rate,
            })
    events.sort(key=lambda event: event["timestamp"])
    for previous, current in zip(events, events[1:]):
        if current["timestamp"] <= previous["timestamp"]:
            raise ValueError("Funding archive contains duplicate or unordered settlement timestamps")
    if not events:
        raise ValueError(f"No Binance Vision funding history for {symbol}")
    return events, archive_hashes


def _save_funding_rate_audit(symbol, start_ms, end_ms, events, archive_hashes):
    payload = {
        "schema_version": 1,
        "source": "BINANCE_VISION_USDM_MONTHLY_FUNDING_RATE",
        "market": "FUTURES",
        "symbol": symbol,
        "start_ms": start_ms,
        "end_ms": end_ms,
        "event_count": len(events),
        "archive_hashes": archive_hashes,
        "events": events,
        "settlement_mark_price_included": False,
        "applied_to_backtest_pnl": False,
        "automatic_orders": False,
    }
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()
    payload["data_sha256"] = hashlib.sha256(encoded).hexdigest()
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    path = DATA_DIR / f"{symbol.replace('/', '-')}_funding_rates_{start_ms}_{end_ms}.json"
    path.write_text(json.dumps(payload, indent=2, sort_keys=True, allow_nan=False) + "\n", encoding="utf-8")
    return path, payload["data_sha256"]


def _validate_symbols(symbols):
    if not isinstance(symbols, (list, tuple)) or not symbols:
        raise ValueError("At least one Futures symbol is required")
    normalized = []
    for symbol in symbols:
        if not isinstance(symbol, str) or not re.fullmatch(r"[A-Z0-9]+/USDT", symbol):
            raise ValueError(f"Invalid canonical USDT Futures symbol: {symbol!r}")
        if symbol not in normalized:
            normalized.append(symbol)
    if len(normalized) > MAX_SYMBOLS:
        raise ValueError(f"At most {MAX_SYMBOLS} symbols are allowed per archive run")
    return normalized


def run_archive_backtest(*, symbols=("BTC/USDT",), days=180, initial_equity=100.0):
    selected = _validate_symbols(symbols)
    if isinstance(days, bool) or not isinstance(days, int) or not 120 <= days <= 730:
        raise ValueError("days must be an integer between 120 and 730")
    if isinstance(initial_equity, bool) or not isinstance(initial_equity, (int, float)) or not math.isfinite(initial_equity) or initial_equity <= 0:
        raise ValueError("initial_equity must be a positive finite number")

    # End at the first UTC day of the current month so every required monthly
    # archive (including fundingRate) is complete and published.
    now = datetime.now(timezone.utc)
    end_dt = datetime(now.year, now.month, 1, tzinfo=timezone.utc)
    start_dt = end_dt - timedelta(days=days)
    start_ms = int(start_dt.timestamp() * 1000)
    end_ms = int(end_dt.timestamp() * 1000)
    months = list(_months_between(start_dt, end_dt))
    REPORT_DIR.mkdir(parents=True, exist_ok=True)
    results = []

    for symbol in selected:
        dataset_paths = []
        timeframe_manifests = {}
        for timeframe in TIMEFRAMES:
            candles, hashes = _load_monthly_candles(symbol, timeframe, start_ms, end_ms, months)
            path = historical_data.save_dataset(
                "FUTURES", symbol, timeframe, candles,
                start_ms=candles[0][0],
                end_ms=candles[-1][0] + smc.TIMEFRAME_MILLISECONDS[timeframe],
            )
            verified = historical_data.load_dataset(path)
            if verified["data_sha256"] != historical_data.dataset_sha256(verified["candles"]):
                raise RuntimeError(f"Dataset integrity check failed: {symbol} {timeframe}")
            dataset_paths.append(path)
            timeframe_manifests[timeframe] = {
                "candle_count": len(candles),
                "data_sha256": verified["data_sha256"],
                "archive_hashes": hashes,
            }

        mark_candles, mark_hashes = _load_monthly_candles(
            symbol, MARK_TIMEFRAME, start_ms, end_ms, months, mark=True,
        )
        mark_path = mark_price_data.save_mark_price_dataset(
            symbol, MARK_TIMEFRAME, mark_candles,
            start_ms=mark_candles[0][0],
            end_ms=mark_candles[-1][0] + smc.TIMEFRAME_MILLISECONDS[MARK_TIMEFRAME],
        )
        verified_mark = mark_price_data.load_mark_price_dataset(mark_path)

        funding_events, funding_hashes = _load_monthly_funding_rates(symbol, months)
        funding_events = [
            event for event in funding_events
            if start_ms <= event["timestamp"] < end_ms
        ]
        if not funding_events:
            raise ValueError(f"No Binance Vision funding events inside requested range for {symbol}")
        funding_path, funding_digest = _save_funding_rate_audit(
            symbol, start_ms, end_ms, funding_events, funding_hashes,
        )

        stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        report_path = REPORT_DIR / f"futures_vision_{symbol.replace('/', '-')}_{days}d_{stamp}.json"
        report, saved_path = historical_backtest.run_dataset_backtest(
            dataset_paths,
            output_path=report_path,
            initial_equity=float(initial_equity),
            mark_price_dataset_path=mark_path,
            # No funding events are passed: Vision's monthly funding-rate CSV
            # has no event-specific markPrice, so applying it as exact cashflow
            # would violate SI-AI's own fail-closed evidence contract.
        )
        report["dataset"]["archive_source"] = "BINANCE_VISION_PUBLIC_ARCHIVE"
        report["dataset"]["archive_months"] = months
        report["dataset"]["timeframes"] = timeframe_manifests
        report["dataset"]["mark_price"]["archive_hashes"] = mark_hashes
        report["dataset"]["funding_rate_audit"] = {
            "path": str(funding_path),
            "event_count": len(funding_events),
            "data_sha256": funding_digest,
            "archive_hashes": funding_hashes,
            "settlement_mark_price_included": False,
            "applied_to_backtest_pnl": False,
        }
        report["limitations"].append(
            "Funding rates were independently archived and checksum-verified but not applied: Binance Vision monthly funding files do not include the exact settlement markPrice required for exact funding cashflows."
        )
        report["limitations"].append(
            "Historical mark-price OHLC is present, but liquidation is not simulated because timestamp-matched historical maintenance-tier snapshots are unavailable."
        )
        historical_backtest._atomic_write(saved_path, report)

        results.append({
            "symbol": symbol,
            "report_path": str(saved_path),
            "funding_audit_path": str(funding_path),
            "dataset_sha256": report["dataset"]["combined_data_sha256"],
            "timeframes": timeframe_manifests,
            "mark_price_candles": verified_mark["candle_count"],
            "funding_events_archived": len(funding_events),
            "funding_applied": False,
            "out_of_sample": report["chronological_validation"].get("out_of_sample", {}),
            "walk_forward": report["walk_forward"].get("metrics", {}),
            "profitability_gate": report["profitability_gate"]["status"],
            "automatic_orders": False,
        })

    summary = {
        "market": "FUTURES",
        "exchange": "Binance USD-M",
        "source": "Binance Vision public monthly archives",
        "requested_days": days,
        "actual_window_start_utc": start_dt.isoformat(),
        "actual_window_end_utc_exclusive": end_dt.isoformat(),
        "symbols": selected,
        "results": results,
        "portfolio_simulation": False,
        "certification": "INCONCLUSIVE",
        "limitations": [
            "Per-symbol reports use independent reference equity; no shared-wallet portfolio simulation is performed.",
            "Funding rates are archived but not applied because the archive does not include exact settlement markPrice values.",
            "Historical liquidation events are not simulated; timestamp-matched historical maintenance-tier snapshots are unavailable.",
            "Mark-price OHLC does not replace exact intrabar liquidation sequencing.",
            "Historical results do not guarantee future performance.",
        ],
        "automatic_orders": False,
    }
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    summary_path = REPORT_DIR / f"futures_vision_summary_{stamp}.json"
    summary_path.write_text(json.dumps(summary, indent=2, sort_keys=True, allow_nan=False) + "\n", encoding="utf-8")
    print(json.dumps(summary, indent=2, sort_keys=True, allow_nan=False))
    print(f"Summary report: {summary_path}")
    return summary, summary_path


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--days", type=int, default=180)
    parser.add_argument("--symbol", action="append", dest="symbols")
    parser.add_argument("--initial-equity", type=float, default=100.0)
    args = parser.parse_args()
    run_archive_backtest(
        symbols=args.symbols or ["BTC/USDT"],
        days=args.days,
        initial_equity=args.initial_equity,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
