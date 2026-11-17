"""Download public Binance USD-M Futures history and run SI-AI backtests.

Historical funding events and liquidation/maintenance-margin modelling are not
currently integrated. Reports therefore remain INCONCLUSIVE for profitability
certification until those required Futures costs and risks are modelled.
"""
from __future__ import annotations

import argparse
import json
import re
import time
from datetime import datetime, timezone
from pathlib import Path

import SI_AI_smc as smc
import historical_backtest
import historical_data


TIMEFRAMES = ("15m", "1h", "4h", "1d")
MAX_SYMBOLS = 50
REPORT_DIR = Path(__file__).resolve().parent / "data" / "reports"


def _validate_symbols(symbols):
    if not isinstance(symbols, (list, tuple)) or not symbols:
        raise ValueError("Provide at least one Futures symbol")
    normalized = []
    for symbol in symbols:
        if not isinstance(symbol, str) or not re.fullmatch(r"[A-Z0-9]+/USDT", symbol):
            raise ValueError(f"Invalid canonical USDT Futures symbol: {symbol!r}")
        if symbol not in normalized:
            normalized.append(symbol)
    if len(normalized) > MAX_SYMBOLS:
        raise ValueError(f"At most {MAX_SYMBOLS} symbols can be backtested per run")
    return normalized


def run_public_futures_backtest(*, symbols=("BTC/USDT",), days=180,
                                initial_equity=smc.PAPER_EQUITY_USDT):
    if isinstance(days, bool) or not isinstance(days, int) or not 120 <= days <= 730:
        raise ValueError("days must be an integer between 120 and 730")
    selected = _validate_symbols(symbols)
    exchange = smc.EXCHANGES["FUTURES"]
    end_ms = int(exchange.milliseconds())
    start_ms = end_ms - days * 24 * 60 * 60 * 1000
    REPORT_DIR.mkdir(parents=True, exist_ok=True)
    results = []

    for symbol in selected:
        dataset_paths = []
        for timeframe in TIMEFRAMES:
            candles = historical_data.download_ohlcv(
                "FUTURES", symbol, timeframe, start_ms, end_ms,
                exchange=exchange,
            )
            if len(candles) < smc.MIN_CANDLES:
                raise RuntimeError(
                    f"{symbol} {timeframe}: only {len(candles)} closed candles; "
                    f"at least {smc.MIN_CANDLES} required"
                )
            path = historical_data.save_dataset(
                "FUTURES", symbol, timeframe, candles,
                start_ms=start_ms, end_ms=end_ms,
            )
            verified = historical_data.load_dataset(path)
            if verified["data_sha256"] != historical_data.dataset_sha256(verified["candles"]):
                raise RuntimeError(f"Dataset integrity check failed: {symbol} {timeframe}")
            dataset_paths.append(path)

        safe_symbol = symbol.replace("/", "-")
        stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        report_path = REPORT_DIR / f"futures_{safe_symbol}_{days}d_{stamp}.json"
        report, saved_path = historical_backtest.run_dataset_backtest(
            dataset_paths, output_path=report_path,
            initial_equity=initial_equity,
        )
        chronological = report.get("chronological_validation", {})
        assumptions = chronological.get("assumptions", {})
        results.append({
            "symbol": symbol,
            "report_path": str(saved_path),
            "dataset_sha256": report["dataset"]["combined_data_sha256"],
            "out_of_sample": chronological.get("out_of_sample", {}),
            "walk_forward": report.get("walk_forward", {}),
            "profitability_gate": report["profitability_gate"]["status"],
            "funding_series_included": assumptions.get(
                "historical_funding_series_included", False
            ),
            "liquidation_modelled": assumptions.get(
                "liquidation_modelled", False
            ),
            "automatic_orders": False,
        })

    summary = {
        "market": "FUTURES",
        "exchange": "Binance USD-M",
        "days": days,
        "symbols": selected,
        "created_at_utc": datetime.now(timezone.utc).isoformat(),
        "results": results,
        "certification": "INCONCLUSIVE",
        "limitations": [
            "Timestamped historical Binance funding events are not yet integrated.",
            "Exchange-specific maintenance-margin and liquidation modelling is not implemented.",
            "Per-symbol reports use separate reference equity; results are not a shared-wallet portfolio simulation.",
            "Historical results do not guarantee future performance.",
        ],
        "automatic_orders": False,
    }
    summary_path = REPORT_DIR / f"futures_backtest_summary_{stamp}.json"
    summary_path.write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(summary, indent=2))
    print(f"Summary report: {summary_path}")
    return summary, summary_path


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--days", type=int, default=180)
    parser.add_argument("--symbol", action="append", dest="symbols",
                        help="Repeat for each Binance USD-M USDT perpetual symbol")
    parser.add_argument("--initial-equity", type=float, default=smc.PAPER_EQUITY_USDT)
    args = parser.parse_args()
    run_public_futures_backtest(
        symbols=args.symbols or ["BTC/USDT"],
        days=args.days,
        initial_equity=args.initial_equity,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
