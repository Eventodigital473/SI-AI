"""Run reproducible chronological and walk-forward SI-AI research on a saved dataset."""
from __future__ import annotations

import argparse
import json
import os
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, Optional

import backtesting
import historical_data
import profitability_gate


REPORT_DIR = Path(__file__).resolve().parent / "data" / "reports"


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


def run_dataset_backtest(
    dataset_path: str | Path,
    *,
    output_path: Optional[str | Path] = None,
    initial_equity: float = 100.0,
) -> tuple[Dict, Path]:
    dataset = historical_data.load_dataset(dataset_path)
    candles = dataset["candles"]
    market = dataset["market"]
    symbol = dataset["symbol"]
    timeframe = dataset["timeframe"]

    options = {"initial_equity": initial_equity}
    try:
        chronological = backtesting.evaluate_chronological_validation(
            candles, market, symbol, timeframe, **options
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
            candles, market, symbol, timeframe, **options
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
    report = {
        "report_schema_version": 1,
        "created_at_utc": datetime.now(timezone.utc).isoformat(),
        "dataset": {
            "market": market,
            "symbol": symbol,
            "timeframe": timeframe,
            "candle_count": dataset["candle_count"],
            "data_sha256": dataset["data_sha256"],
            "start_ms": dataset["start_ms"],
            "end_ms": dataset["end_ms"],
        },
        "strategy": "SI-AI current SMC engine; signals at candle close, entries next candle open",
        "chronological_validation": chronological,
        "walk_forward": walk_forward,
        "profitability_gate": gate,
        "automatic_orders": False,
        "limitations": [
            "Historical results do not guarantee future returns.",
            "No automatic orders are placed.",
            "Futures certification remains INCONCLUSIVE until timestamped historical funding and exchange-specific liquidation/maintenance-margin modelling are included.",
        ],
    }

    path = Path(output_path) if output_path is not None else (
        REPORT_DIR
        / f"{market.lower()}_{symbol.replace('/', '-')}_{timeframe}_{dataset['data_sha256'][:12]}.json"
    )
    _atomic_write(path, report)
    return report, path


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Run SI-AI chronological and walk-forward validation on a saved dataset"
    )
    parser.add_argument("--dataset", required=True, help="Path to a verified historical_data.py JSON dataset")
    parser.add_argument("--output", default=None, help="Optional report JSON path")
    parser.add_argument("--initial-equity", type=float, default=100.0)
    args = parser.parse_args()

    report, path = run_dataset_backtest(
        args.dataset,
        output_path=args.output,
        initial_equity=args.initial_equity,
    )
    print(f"Research report: {path}")
    print(f"Dataset SHA-256: {report['dataset']['data_sha256']}")
    print(f"Chronological status: {report['chronological_validation']['status']}")
    print(f"Walk-forward status: {report['walk_forward']['status']}")
    print(f"Profitability gate: {report['profitability_gate']['status']}")
    print("Historical evidence only. No automatic orders.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
