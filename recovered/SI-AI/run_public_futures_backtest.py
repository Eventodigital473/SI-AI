"""Download public Binance USD-M Futures OHLCV and funding history for backtests.

Funding cashflows use Binance's timestamped funding events and associated
settlement mark prices. Exchange-specific liquidation/maintenance-margin
modelling is still required for profitability certification.
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
import funding_data
import mark_price_data


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

        funding_events = funding_data.download_funding_history(
            "FUTURES", symbol, start_ms, end_ms, exchange=exchange,
        )
        funding_path = historical_data.DATA_DIR / "funding" / (
            f"{symbol.replace('/', '-')}_{start_ms}_{end_ms}.json"
        )
        funding_data.save_funding_dataset(
            "FUTURES", symbol, funding_events, start_ms, end_ms, funding_path,
        )
        verified_funding = funding_data.load_funding_dataset(funding_path)
        if verified_funding["data_sha256"] != funding_data.funding_events_sha256(verified_funding["events"]):
            raise RuntimeError(f"Funding dataset integrity check failed: {symbol}")

        mark_candles = mark_price_data.download_mark_price_ohlcv(
            symbol, "1h", start_ms, end_ms,
        )
        if len(mark_candles) < smc.MIN_CANDLES:
            raise RuntimeError(
                f"{symbol} 1h mark-price dataset has only {len(mark_candles)} closed candles; "
                f"at least {smc.MIN_CANDLES} required"
            )
        mark_price_path = mark_price_data.DATA_DIR / (
            f"{symbol.replace('/', '-')}_1h_{start_ms}_{end_ms}.json"
        )
        mark_price_data.save_mark_price_dataset(
            symbol, "1h", mark_candles, output_path=mark_price_path,
            start_ms=start_ms, end_ms=end_ms,
        )
        verified_mark = mark_price_data.load_mark_price_dataset(mark_price_path)
        if verified_mark["data_sha256"] != mark_price_data.mark_price_sha256(
            verified_mark["candles"], "1h"
        ):
            raise RuntimeError(f"Mark-price dataset integrity check failed: {symbol}")

        safe_symbol = symbol.replace("/", "-")
        stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        report_path = REPORT_DIR / f"futures_{safe_symbol}_{days}d_{stamp}.json"
        report, saved_path = historical_backtest.run_dataset_backtest(
            dataset_paths, output_path=report_path,
            initial_equity=initial_equity,
            funding_dataset_path=funding_path,
            mark_price_dataset_path=mark_price_path,
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
            "funding_event_count": assumptions.get("funding_event_count", 0),
            "funding_mark_price_exact": assumptions.get("funding_mark_price_exact", False),
            "funding_boundary_ambiguities": assumptions.get(
                "funding_settlement_boundary_ambiguities", 0
            ),
            "historical_mark_price_data_included": report["dataset"].get("mark_price") is not None,
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
            "Funding events with exact associated settlement mark prices are included; exact entry/exit settlement timestamp ties are flagged and block certification.",
            "Historical mark-price OHLC is archived for research, but liquidation events are not yet simulated because timestamp-matched historical maintenance-tier snapshots are unavailable.",
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
