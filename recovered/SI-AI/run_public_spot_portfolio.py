"""Read-only public Spot data collection and shared-wallet historical validation."""
from __future__ import annotations

import argparse
import json
import os
import time
from datetime import datetime, timezone
from pathlib import Path

import ccxt
import SI_AI_smc as smc
import historical_backtest
import historical_data


TIMEFRAMES = ("15m", "1h", "4h", "1d")
PUBLIC_SPOT_DATA_URL = "https://data-api.binance.vision/api/v3"


def _download_with_retries(exchange, symbol, timeframe, start_ms, end_ms):
    transient_names = (
        "RateLimitExceeded", "NetworkError", "ExchangeNotAvailable",
        "RequestTimeout", "DDoSProtection",
    )
    transient_types = tuple(
        getattr(ccxt, name) for name in transient_names if hasattr(ccxt, name)
    )
    last_error = None
    for attempt in range(3):
        try:
            return historical_data.download_ohlcv(
                "SPOT", symbol, timeframe, start_ms, end_ms, exchange=exchange
            )
        except transient_types as exc:
            last_error = exc
            if attempt == 2:
                raise
            time.sleep(3 * (attempt + 1))
    raise RuntimeError(f"Download failed for {symbol} {timeframe}: {last_error}")


def collect_and_backtest(
    *,
    days: int = 180,
    symbol_limit: int = 50,
    initial_equity: float = smc.PAPER_EQUITY_USDT,
    report_output: str | Path | None = None,
) -> dict:
    if isinstance(days, bool) or not isinstance(days, int) or days < 120 or days > 730:
        raise ValueError("days must be an integer between 120 and 730")
    if isinstance(symbol_limit, bool) or not isinstance(symbol_limit, int):
        raise ValueError("symbol_limit must be an integer")
    if symbol_limit < smc.MIN_ELIGIBLE_COINS:
        raise ValueError(f"symbol_limit must be >= {smc.MIN_ELIGIBLE_COINS}")
    symbol_limit = min(symbol_limit, smc.TARGET_UNIVERSE_SIZE)

    end_ms = int(time.time() * 1000)
    start_ms = end_ms - days * 24 * 60 * 60 * 1000
    universe_as_of = datetime.now(timezone.utc).isoformat()

    original_markets = list(smc.MARKETS)
    original_symbols = list(smc.SYMBOLS)
    original_market_symbols = {
        key: list(value) for key, value in smc.MARKET_SYMBOLS.items()
    }
    exchange = smc.EXCHANGES["SPOT"]
    original_public_url = exchange.urls["api"]["public"]
    original_fetch_markets = exchange.options.get("fetchMarkets")

    try:
        # Spot-only mode prevents CCXT from probing restricted Futures endpoints.
        smc.MARKETS = ["SPOT"]
        exchange.urls["api"]["public"] = PUBLIC_SPOT_DATA_URL
        exchange.options["fetchMarkets"] = ["spot"]

        universe = smc.refresh_symbol_universe(force=True)
        selected_symbols = universe.get("SPOT", [])[:symbol_limit]
        if len(selected_symbols) < smc.MIN_ELIGIBLE_COINS:
            raise RuntimeError(
                f"Only {len(selected_symbols)} eligible Spot symbols; "
                f"minimum is {smc.MIN_ELIGIBLE_COINS}"
            )

        dataset_paths_by_symbol = {}
        manifests = []
        skipped_symbols = {}

        for symbol in selected_symbols:
            candles_by_timeframe = {}
            insufficient = None
            for timeframe in TIMEFRAMES:
                candles = _download_with_retries(
                    exchange, symbol, timeframe, start_ms, end_ms
                )
                if len(candles) < smc.MIN_CANDLES:
                    insufficient = (
                        f"{timeframe} has {len(candles)} candles; "
                        f"requires at least {smc.MIN_CANDLES}"
                    )
                    break
                candles_by_timeframe[timeframe] = candles

            if insufficient:
                skipped_symbols[symbol] = insufficient
                continue

            paths = []
            pending_manifests = []
            for timeframe in TIMEFRAMES:
                path = historical_data.save_dataset(
                    "SPOT", symbol, timeframe, candles_by_timeframe[timeframe],
                    start_ms=start_ms, end_ms=end_ms,
                )
                verified = historical_data.load_dataset(path)
                expected_hash = historical_data.dataset_sha256(verified["candles"])
                if verified["data_sha256"] != expected_hash:
                    raise RuntimeError(
                        f"Dataset checksum verification failed: {symbol} {timeframe}"
                    )
                paths.append(str(path))
                pending_manifests.append({
                    "symbol": symbol,
                    "timeframe": timeframe,
                    "candle_count": verified["candle_count"],
                    "start_ms": verified["start_ms"],
                    "end_ms": verified["end_ms"],
                    "sha256": verified["data_sha256"],
                    "path": str(path),
                })

            dataset_paths_by_symbol[symbol] = paths
            manifests.extend(pending_manifests)

        if len(dataset_paths_by_symbol) < smc.MIN_ELIGIBLE_COINS:
            raise RuntimeError(
                f"Only {len(dataset_paths_by_symbol)} symbols have complete history; "
                f"minimum is {smc.MIN_ELIGIBLE_COINS}. "
                f"Skipped: {json.dumps(skipped_symbols, sort_keys=True)}"
            )

        report, report_path = historical_backtest.run_multi_symbol_portfolio_backtest(
            dataset_paths_by_symbol,
            output_path=report_output,
            initial_equity=initial_equity,
            universe_as_of_utc=universe_as_of,
        )
        summary = {
            "market": "SPOT",
            "requested_days": days,
            "universe_as_of_utc": universe_as_of,
            "selected_symbol_count": len(selected_symbols),
            "verified_symbol_count": len(dataset_paths_by_symbol),
            "verified_symbols": list(dataset_paths_by_symbol),
            "skipped_symbols": skipped_symbols,
            "dataset_manifest": manifests,
            "report_path": str(report_path),
            "combined_data_sha256": report["dataset"]["combined_data_sha256"],
            "out_of_sample": report["chronological_validation"]["out_of_sample"],
            "chronological_status": report["chronological_validation"]["status"],
            "walk_forward_metrics": report["walk_forward"]["metrics"],
            "walk_forward_status": report["walk_forward"]["status"],
            "profitability_gate": report["profitability_gate"]["status"],
            "profitability_checks": report["profitability_gate"]["checks"],
            "skipped_overlapping_trades": report["chronological_validation"]["skipped_overlapping_trades"],
            "max_concurrent_positions": 1,
            "automatic_orders": False,
            "limitations": report["limitations"],
        }
        summary_path = Path("data/reports/public_spot_portfolio_summary.json")
        summary_path.parent.mkdir(parents=True, exist_ok=True)
        summary_path.write_text(
            json.dumps(summary, indent=2) + "\n", encoding="utf-8"
        )

        step_summary = os.environ.get("GITHUB_STEP_SUMMARY")
        if step_summary:
            with open(step_summary, "a", encoding="utf-8") as handle:
                handle.write("# SI-AI dynamic-universe Spot historical validation\n\n")
                handle.write(f"- History: **{days} days**\n")
                handle.write(
                    f"- Verified Spot symbols: **{len(dataset_paths_by_symbol)} / "
                    f"{len(selected_symbols)}**\n"
                )
                handle.write(
                    f"- Out-of-sample trades: **{summary['out_of_sample']['trade_count']}**\n"
                )
                handle.write(
                    f"- Walk-forward trades: **{summary['walk_forward_metrics']['trade_count']}**\n"
                )
                handle.write(
                    f"- Profitability gate: **{summary['profitability_gate']}**\n"
                )
                handle.write(
                    f"- Combined data SHA-256: `{summary['combined_data_sha256']}`\n\n"
                )
                handle.write(
                    "Shared 100 USDT wallet; one concurrent position. Current universe "
                    "snapshot is applied retrospectively, so survivorship bias remains. "
                    "No automatic trading or future-profit claim.\n"
                )
        print(json.dumps(summary, indent=2))
        return summary
    finally:
        smc.MARKETS = original_markets
        smc.SYMBOLS = original_symbols
        smc.MARKET_SYMBOLS.clear()
        smc.MARKET_SYMBOLS.update(original_market_symbols)
        exchange.urls["api"]["public"] = original_public_url
        if original_fetch_markets is None:
            exchange.options.pop("fetchMarkets", None)
        else:
            exchange.options["fetchMarkets"] = original_fetch_markets


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--days", type=int, default=180)
    parser.add_argument("--symbol-limit", type=int, default=50)
    parser.add_argument("--initial-equity", type=float, default=smc.PAPER_EQUITY_USDT)
    parser.add_argument("--report-output", default=None)
    args = parser.parse_args()
    collect_and_backtest(
        days=args.days,
        symbol_limit=args.symbol_limit,
        initial_equity=args.initial_equity,
        report_output=args.report_output,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
