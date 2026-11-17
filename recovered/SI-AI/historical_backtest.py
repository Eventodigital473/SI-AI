"""Run production-equivalent multi-timeframe SI-AI backtests on saved datasets."""
from __future__ import annotations

import bisect
import argparse
import hashlib
import json
import os
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, Optional

import SI_AI_smc as smc
import backtesting
import historical_data
import funding_data
import profitability_gate
import si_ai_scanner as scanner


REPORT_DIR = Path(__file__).resolve().parent / "data" / "reports"
REQUIRED_TIMEFRAMES = tuple(smc.TIMEFRAMES)


def _atomic_write(path: Path, report: Dict) -> None:
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
            json.dump(report, handle, indent=2, sort_keys=True, allow_nan=False)
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


def _load_timeframe_datasets(dataset_paths) -> Dict[str, Dict]:
    if isinstance(dataset_paths, dict):
        paths = list(dataset_paths.values())
    elif isinstance(dataset_paths, (list, tuple)):
        paths = list(dataset_paths)
    else:
        raise ValueError("Provide four dataset paths, one for each production timeframe")

    datasets = {}
    for path in paths:
        dataset = historical_data.load_dataset(path)
        timeframe = dataset["timeframe"]
        if timeframe not in REQUIRED_TIMEFRAMES:
            raise ValueError(f"Unexpected dataset timeframe: {timeframe}")
        if timeframe in datasets:
            raise ValueError(f"Duplicate dataset for timeframe: {timeframe}")
        datasets[timeframe] = dataset

    if set(datasets) != set(REQUIRED_TIMEFRAMES):
        missing = sorted(set(REQUIRED_TIMEFRAMES) - set(datasets))
        raise ValueError(f"All production timeframes are required; missing: {missing}")

    markets = {item["market"] for item in datasets.values()}
    symbols = {item["symbol"] for item in datasets.values()}
    if len(markets) != 1 or len(symbols) != 1:
        raise ValueError("All timeframe datasets must use the same market and symbol")

    for timeframe, dataset in datasets.items():
        if len(dataset["candles"]) < smc.MIN_CANDLES:
            raise ValueError(f"{timeframe} dataset needs at least {smc.MIN_CANDLES} candles")

    overlap_start = max(
        dataset["candles"][0][0] + smc.TIMEFRAME_MILLISECONDS[timeframe]
        for timeframe, dataset in datasets.items()
    )
    overlap_end = min(
        dataset["candles"][-1][0] + smc.TIMEFRAME_MILLISECONDS[timeframe]
        for timeframe, dataset in datasets.items()
    )
    if overlap_end <= overlap_start:
        raise ValueError("The four timeframe datasets have no common time window")

    return datasets


def build_production_signal_callback(datasets: Dict[str, Dict]):
    """Recreate live scanner confluence with closed candles and the same 250-bar cap."""
    if set(datasets) != set(REQUIRED_TIMEFRAMES):
        raise ValueError("Production callback requires 15m, 1h, 4h and 1d datasets")

    market = datasets["1h"]["market"]
    symbol = datasets["1h"]["symbol"]
    candles_by_timeframe = {
        timeframe: dataset["candles"]
        for timeframe, dataset in datasets.items()
    }
    close_times_by_timeframe = {
        timeframe: [
            row[0] + smc.TIMEFRAME_MILLISECONDS[timeframe]
            for row in candles
        ]
        for timeframe, candles in candles_by_timeframe.items()
    }

    def callback(callback_market, callback_symbol, callback_timeframe, history):
        if callback_market != market or callback_symbol != symbol:
            raise ValueError("Backtest callback market/symbol does not match its datasets")
        if callback_timeframe != "1h":
            raise ValueError("Production SI-AI entry setup is evaluated on 1h candles")
        if not history:
            return {"signal": "WAIT"}

        signal_close_ms = history[-1][0] + smc.TIMEFRAME_MILLISECONDS["1h"]
        results = {}
        for timeframe in REQUIRED_TIMEFRAMES:
            if timeframe == "1h":
                timeframe_history = history[-smc.CANDLE_LIMIT:]
            else:
                close_times = close_times_by_timeframe[timeframe]
                end_index = bisect.bisect_right(close_times, signal_close_ms)
                start_index = max(0, end_index - smc.CANDLE_LIMIT)
                timeframe_history = candles_by_timeframe[timeframe][start_index:end_index]

            if len(timeframe_history) < smc.MIN_CANDLES:
                return {"signal": "WAIT"}

            results[timeframe] = smc.analyze_candles(
                market, symbol, timeframe, timeframe_history
            )

        combined = smc.combine_timeframes(
            [results[timeframe] for timeframe in REQUIRED_TIMEFRAMES]
        )
        signal = scanner.confirm_signal(market, results, combined)
        reference = results["1h"]
        return {
            "signal": signal,
            "stop_loss": reference.get("stop_loss"),
            "take_profit": reference.get("take_profit"),
        }

    return callback


def run_dataset_backtest(
    dataset_paths,
    *,
    output_path: Optional[str | Path] = None,
    initial_equity: float = 100.0,
    funding_dataset_path: Optional[str | Path] = None,
) -> tuple[Dict, Path]:
    datasets = _load_timeframe_datasets(dataset_paths)
    market = datasets["1h"]["market"]
    symbol = datasets["1h"]["symbol"]
    primary_candles = datasets["1h"]["candles"]
    signal_fn = build_production_signal_callback(datasets)

    funding_dataset = None
    funding_events = None
    if funding_dataset_path is not None:
        funding_dataset = funding_data.load_funding_dataset(funding_dataset_path)
        if funding_dataset.get("market") != market or funding_dataset.get("symbol") != symbol:
            raise ValueError("Funding dataset market/symbol must match OHLCV datasets")
        required_start = min(item[0] for item in primary_candles)
        required_end = primary_candles[-1][0] + smc.TIMEFRAME_MILLISECONDS["1h"]
        if funding_dataset["start_ms"] > required_start or funding_dataset["end_ms"] < required_end:
            raise ValueError("Funding dataset must cover the complete primary 1h OHLCV time range")
        funding_events = funding_dataset["events"]

    options = {
        "initial_equity": initial_equity,
        "signal_fn": signal_fn,
        "funding_events": funding_events,
    }
    try:
        chronological = backtesting.evaluate_chronological_validation(
            primary_candles, market, symbol, "1h", **options
        )
    except (ValueError, RuntimeError) as exc:
        chronological = {
            "out_of_sample": {},
            "out_of_sample_trades": [],
            "status": "INCONCLUSIVE",
            "reason": f"Chronological validation unavailable: {type(exc).__name__}: {exc}",
            "automatic_orders": False,
        }

    try:
        walk_forward = backtesting.evaluate_walk_forward(
            primary_candles, market, symbol, "1h", **options
        )
    except (ValueError, RuntimeError) as exc:
        walk_forward = {
            "folds": [],
            "status": "INCONCLUSIVE",
            "reason": f"Walk-forward validation unavailable: {type(exc).__name__}: {exc}",
            "automatic_orders": False,
        }

    gate = profitability_gate.evaluate_profitability_evidence(
        chronological,
        walk_forward,
        market=market,
    )
    timeframe_manifest = {
        timeframe: {
            "candle_count": dataset["candle_count"],
            "data_sha256": dataset["data_sha256"],
            "start_ms": dataset["start_ms"],
            "end_ms": dataset["end_ms"],
        }
        for timeframe, dataset in datasets.items()
    }
    combined_hash_source = json.dumps(
        {timeframe: timeframe_manifest[timeframe]["data_sha256"]
         for timeframe in REQUIRED_TIMEFRAMES},
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    combined_hash = hashlib.sha256(combined_hash_source).hexdigest()

    report = {
        "report_schema_version": 2,
        "created_at_utc": datetime.now(timezone.utc).isoformat(),
        "dataset": {
            "market": market,
            "symbol": symbol,
            "primary_timeframe": "1h",
            "timeframes": timeframe_manifest,
            "combined_data_sha256": combined_hash,
            "funding": ({
                "event_count": funding_dataset["event_count"],
                "data_sha256": funding_dataset["data_sha256"],
                "start_ms": funding_dataset["start_ms"],
                "end_ms": funding_dataset["end_ms"],
                "source": funding_dataset["source"],
            } if funding_dataset is not None else None),
        },
        "strategy": (
            "Production scanner confluence: 15m, 1h, 4h and 1d; "
            "1h entry setup, 4h directional agreement, weighted all-timeframe confirmation"
        ),
        "execution_assumptions": {
            "entry": "next 1h candle open after confirmed signal candle close",
            "futures_short": "SELL opens a short; BUY reverses/closes it at next 1h open",
            "futures_reversal": "close existing position at next 1h open on opposite confirmed signal",
            "automatic_orders": False,
        },
        "chronological_validation": chronological,
        "walk_forward": walk_forward,
        "profitability_gate": gate,
        "automatic_orders": False,
        "limitations": [
            "Historical results do not guarantee future returns.",
            "No automatic orders are placed.",
            ("Timestamped Binance funding events and event-specific settlement mark prices are included; exchange-specific liquidation/maintenance-margin modelling is still required." if funding_dataset is not None else "Futures certification remains INCONCLUSIVE until timestamped historical funding and exchange-specific liquidation/maintenance-margin modelling are included."),
            "Signals are evaluated only when all required timeframe histories are available and closed by the 1h signal close.",
        ],
    }

    path = Path(output_path) if output_path is not None else (
        REPORT_DIR
        / f"{market.lower()}_{symbol.replace('/', '-')}_multiTF_{combined_hash[:12]}.json"
    )
    _atomic_write(path, report)
    return report, path



def main() -> int:
    parser = argparse.ArgumentParser(
        description="Run production-equivalent SI-AI multi-timeframe holdout and walk-forward validation"
    )
    parser.add_argument(
        "--dataset", action="append", required=True,
        help="Repeat four times: one verified JSON dataset each for 15m, 1h, 4h and 1d",
    )
    parser.add_argument("--output", default=None, help="Optional report JSON path")
    parser.add_argument("--funding-dataset", default=None, help="Verified Binance funding JSON covering the full 1h dataset range")
    parser.add_argument("--initial-equity", type=float, default=100.0)
    args = parser.parse_args()

    report, path = run_dataset_backtest(
        args.dataset,
        output_path=args.output,
        initial_equity=args.initial_equity,
        funding_dataset_path=args.funding_dataset,
    )
    print(f"Research report: {path}")
    print(f"Combined dataset SHA-256: {report['dataset']['combined_data_sha256']}")
    print(f"Chronological status: {report['chronological_validation']['status']}")
    print(f"Walk-forward status: {report['walk_forward']['status']}")
    print(f"Profitability gate: {report['profitability_gate']['status']}")
    print("Production-equivalent multi-timeframe signal logic. No automatic orders.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
