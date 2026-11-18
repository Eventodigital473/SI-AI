"""Conservative shared-wallet replay for SI-AI Futures historical trade reports.

This is a research utility, not a live execution engine. It re-sizes candidate
trades against one shared equity/risk/margin budget, applies conservative
mark-price OHLC drawdown, and fails closed on missing/overlapping data.
Funding and liquidation are deliberately not claimed as modelled.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import tempfile
from collections import defaultdict
from pathlib import Path
from typing import Iterable, List, Mapping, Sequence

HOUR_MS = 60 * 60 * 1000


def _finite(value, name: str) -> float:
    if isinstance(value, bool):
        raise ValueError(f"{name} must be finite numeric data")
    try:
        result = float(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{name} must be finite numeric data") from exc
    if not math.isfinite(result):
        raise ValueError(f"{name} must be finite numeric data")
    return result


def _positive(value, name: str) -> float:
    result = _finite(value, name)
    if result <= 0:
        raise ValueError(f"{name} must be positive")
    return result


def _timestamp(value, name: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        raise ValueError(f"{name} must be a positive integer millisecond timestamp")
    if value % HOUR_MS:
        raise ValueError(f"{name} must be aligned to a 1h candle boundary")
    return value


def _normalize_trades(trades: Iterable[Mapping]) -> List[dict]:
    if isinstance(trades, (str, bytes)):
        raise ValueError("trades must be an iterable of trade objects")
    result = []
    for index, raw in enumerate(trades):
        if not isinstance(raw, Mapping):
            raise ValueError(f"trade {index} must be an object")
        symbol = raw.get("symbol")
        if not isinstance(symbol, str) or not symbol or symbol != symbol.strip():
            raise ValueError(f"trade {index} has an invalid symbol")
        side = raw.get("side")
        if side not in ("LONG", "SHORT"):
            raise ValueError(f"trade {index} side must be LONG or SHORT")
        entry_ts = _timestamp(raw.get("entry_timestamp"), f"trade {index} entry_timestamp")
        exit_ts = _timestamp(raw.get("exit_timestamp"), f"trade {index} exit_timestamp")
        if exit_ts < entry_ts:
            raise ValueError(f"trade {index} exits before entry")
        entry = _positive(raw.get("entry_price"), f"trade {index} entry_price")
        stop = _positive(raw.get("stop_loss"), f"trade {index} stop_loss")
        quantity = _positive(raw.get("quantity"), f"trade {index} quantity")
        pnl = _finite(raw.get("net_pnl_usdt"), f"trade {index} net_pnl_usdt")
        if (side == "LONG" and stop >= entry) or (side == "SHORT" and stop <= entry):
            raise ValueError(f"trade {index} stop-loss is on the wrong side of entry")
        item = dict(raw)
        item.update({
            "symbol": symbol, "side": side,
            "entry_timestamp": entry_ts, "exit_timestamp": exit_ts,
            "entry_price": entry, "stop_loss": stop,
            "quantity": quantity, "net_pnl_usdt": pnl,
        })
        result.append(item)
    if not result:
        raise ValueError("at least one trade is required")
    result.sort(key=lambda item: (item["entry_timestamp"], item["symbol"], item["exit_timestamp"]))
    previous_by_symbol = {}
    for trade in result:
        previous_exit = previous_by_symbol.get(trade["symbol"])
        if previous_exit is not None and trade["entry_timestamp"] <= previous_exit:
            raise ValueError(f"overlapping trades for {trade['symbol']} are not supported")
        previous_by_symbol[trade["symbol"]] = trade["exit_timestamp"]
    return result


def _normalize_marks(mark_candles_by_symbol: Mapping[str, Sequence[Sequence]]) -> dict:
    if not isinstance(mark_candles_by_symbol, Mapping):
        raise ValueError("mark_candles_by_symbol must be a mapping")
    result = {}
    for symbol, candles in mark_candles_by_symbol.items():
        if not isinstance(symbol, str) or not isinstance(candles, (list, tuple)):
            raise ValueError("each mark-price series must be a symbol-to-list mapping")
        indexed = {}
        previous = None
        for index, candle in enumerate(candles):
            if not isinstance(candle, (list, tuple)) or len(candle) < 5:
                raise ValueError(f"{symbol} mark candle {index} is malformed")
            ts = _timestamp(candle[0], f"{symbol} mark candle timestamp")
            if previous is not None and ts != previous + HOUR_MS:
                raise ValueError(f"{symbol} mark-price candles are not continuous")
            op = _positive(candle[1], f"{symbol} mark open")
            high = _positive(candle[2], f"{symbol} mark high")
            low = _positive(candle[3], f"{symbol} mark low")
            close = _positive(candle[4], f"{symbol} mark close")
            if high < max(op, low, close) or low > min(op, high, close):
                raise ValueError(f"{symbol} mark OHLC relationship is invalid")
            indexed[ts] = candle
            previous = ts
        result[symbol] = indexed
    return result


def _adverse_unrealized(position: Mapping, candle: Sequence, cost_rate: float) -> float:
    entry = position["entry"]
    qty = position["quantity"]
    if position["side"] == "LONG":
        adverse = float(candle[3])
        direction = 1.0
    else:
        adverse = float(candle[2])
        direction = -1.0
    return qty * (direction * (adverse - entry) - cost_rate * (entry + adverse))


def _metrics(trades: Sequence[Mapping], equity: float, initial_equity: float,
             max_drawdown_percent: float, executed: int, skipped: int,
             candidate_count: int) -> dict:
    pnls = [float(item["scaled_net_pnl_usdt"]) for item in trades]
    gross_profit = sum(value for value in pnls if value > 0)
    gross_loss = -sum(value for value in pnls if value < 0)
    return {
        "candidate_trade_count": candidate_count,
        "executed_trade_count": executed,
        "capacity_skipped_trade_count": skipped,
        "ending_equity_usdt": round(equity, 8),
        "net_pnl_usdt": round(equity - initial_equity, 8),
        "expectancy_usdt": round(sum(pnls) / executed, 8) if executed else 0.0,
        "gross_profit_usdt": round(gross_profit, 8),
        "gross_loss_usdt": round(gross_loss, 8),
        "profit_factor": round(gross_profit / gross_loss, 8) if gross_loss else None,
        "win_rate_percent": round(sum(value > 0 for value in pnls) / executed * 100, 8) if executed else 0.0,
        "max_drawdown_percent": round(max_drawdown_percent, 8),
        "peak_concurrent_positions": 0,
        "automatic_orders": False,
    }


def simulate_shared_wallet(
    trades: Iterable[Mapping],
    mark_candles_by_symbol: Mapping[str, Sequence[Sequence]],
    *,
    initial_equity: float = 100.0,
    risk_per_trade_percent: float = 0.5,
    margin_allocation_percent: float = 20.0,
    leverage: float = 1.0,
    fee_rate_per_side: float = 0.0005,
    slippage_rate_per_side: float = 0.0002,
) -> dict:
    """Replay one wallet; simultaneous entries are pro-rata capacity-scaled.

    All open positions consume one shared notional/margin budget. At each hour,
    existing positions are marked at the adverse OHLC extreme before new sizing.
    Entries are admitted before same-hour exits so released margin is not used
    prematurely. Existing positions are never force-reduced by this simulator.
    """
    initial = _positive(initial_equity, "initial_equity")
    risk_pct = _positive(risk_per_trade_percent, "risk_per_trade_percent")
    margin_pct = _positive(margin_allocation_percent, "margin_allocation_percent")
    leverage_value = _positive(leverage, "leverage")
    fee = _finite(fee_rate_per_side, "fee_rate_per_side")
    slippage = _finite(slippage_rate_per_side, "slippage_rate_per_side")
    if risk_pct > 100 or margin_pct > 100 or leverage_value > 125:
        raise ValueError("risk, margin or leverage setting exceeds supported bounds")
    if fee < 0 or fee >= 0.05 or slippage < 0 or slippage >= 0.05:
        raise ValueError("fee and slippage rates must be in [0, 0.05)")
    cost_rate = fee + slippage
    normalized = _normalize_trades(trades)
    marks = _normalize_marks(mark_candles_by_symbol)
    for symbol in {item["symbol"] for item in normalized}:
        if symbol not in marks:
            raise ValueError(f"missing mark-price series for {symbol}")

    entries = defaultdict(list)
    for trade in normalized:
        entries[trade["entry_timestamp"]].append(trade)

    start = min(entries)
    end = max(trade["exit_timestamp"] for trade in normalized)
    equity = initial
    peak_equity = initial
    max_drawdown = 0.0
    open_positions = []
    completed = []
    skipped = 0
    peak_concurrent = 0
    peak_open_notional = 0.0

    for timestamp in range(start, end + 1, HOUR_MS):
        # Existing positions are marked first; this is the equity used to size
        # new trades and calculate the remaining shared margin capacity.
        existing_unrealized = 0.0
        for position in open_positions:
            candle = marks[position["symbol"]].get(timestamp)
            if candle is None:
                raise ValueError(f"missing {position['symbol']} mark candle at {timestamp}")
            existing_unrealized += _adverse_unrealized(position, candle, cost_rate)
        sizing_equity = max(0.0, equity + existing_unrealized)

        simultaneous = entries.get(timestamp, [])
        desired = []
        for trade in simultaneous:
            entry = trade["entry_price"]
            stop = trade["stop_loss"]
            risk_per_unit = abs(entry - stop) + cost_rate * (entry + stop)
            if risk_per_unit <= 0 or not math.isfinite(risk_per_unit):
                raise ValueError("trade has invalid per-unit risk")
            risk_budget = sizing_equity * risk_pct / 100.0
            notional_budget = sizing_equity * margin_pct / 100.0 * leverage_value
            quantity = min(risk_budget / risk_per_unit, notional_budget / entry) if sizing_equity > 0 else 0.0
            desired.append((trade, quantity))

        used_notional = sum(position["quantity"] * position["entry"] for position in open_positions)
        available_notional = max(
            0.0,
            sizing_equity * margin_pct / 100.0 * leverage_value - used_notional,
        )
        requested_notional = sum(quantity * trade["entry_price"] for trade, quantity in desired)
        allocation_factor = min(1.0, available_notional / requested_notional) if requested_notional > 0 else 0.0

        for trade, desired_quantity in desired:
            quantity = desired_quantity * allocation_factor
            if quantity <= 0:
                skipped += 1
                continue
            open_positions.append({
                "symbol": trade["symbol"],
                "side": trade["side"],
                "entry": trade["entry_price"],
                "quantity": quantity,
                "trade": trade,
            })

        # Mark all active positions at the adverse extreme, including positions
        # that exit intrabar in this candle. This avoids assuming favourable
        # intrabar ordering for the drawdown calculation.
        unrealized = 0.0
        open_notional = 0.0
        for position in open_positions:
            candle = marks[position["symbol"]].get(timestamp)
            if candle is None:
                raise ValueError(f"missing {position['symbol']} mark candle at {timestamp}")
            unrealized += _adverse_unrealized(position, candle, cost_rate)
            open_notional += position["quantity"] * position["entry"]
        marked_equity = equity + unrealized
        peak_equity = max(peak_equity, marked_equity)
        if peak_equity > 0:
            max_drawdown = max(max_drawdown, (peak_equity - marked_equity) / peak_equity * 100.0)
        peak_concurrent = max(peak_concurrent, len(open_positions))
        peak_open_notional = max(peak_open_notional, open_notional)

        # Same-hour entries are opened before exits are settled, conservatively
        # retaining existing margin through the full candle.
        closing = [position for position in open_positions
                   if position["trade"]["exit_timestamp"] == timestamp]
        for position in closing:
            trade = position["trade"]
            scaled_pnl = trade["net_pnl_usdt"] * position["quantity"] / trade["quantity"]
            equity += scaled_pnl
            item = dict(trade)
            item["allocated_quantity"] = position["quantity"]
            item["scaled_net_pnl_usdt"] = scaled_pnl
            item["quantity_scale"] = position["quantity"] / trade["quantity"]
            completed.append(item)
            open_positions.remove(position)

    if open_positions:
        raise ValueError("simulation ended with open positions")
    if len(completed) + skipped != len(normalized):
        raise RuntimeError("internal trade accounting mismatch")

    result = _metrics(completed, equity, initial, max_drawdown,
                      len(completed), skipped, len(normalized))
    result.update({
        "peak_concurrent_positions": peak_concurrent,
        "peak_open_notional_usdt": round(peak_open_notional, 8),
        "risk_per_trade_percent": risk_pct,
        "margin_allocation_percent": margin_pct,
        "leverage": leverage_value,
        "fee_rate_per_side": fee,
        "slippage_rate_per_side": slippage,
        "funding_included": False,
        "liquidation_modelled": False,
        "certification": "INCONCLUSIVE",
        "limitations": [
            "Funding cashflows are not included; exact timestamped settlement mark prices are required.",
            "Exchange-specific maintenance-margin liquidation and exact intrabar liquidation sequencing are not modelled.",
            "Adverse mark-price OHLC drawdown is a conservative candle-level bound, not tick-level execution replay.",
            "Historical results do not guarantee future performance.",
        ],
        "automatic_orders": False,
        "completed_trades": completed,
    })
    return result


def _atomic_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w", encoding="utf-8", dir=path.parent,
            prefix=f".{path.name}.", suffix=".tmp", delete=False,
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
            temporary.unlink(missing_ok=True)


def _load_verified_mark_dataset(path: Path, symbol: str, expected: Mapping) -> list:
    with path.open("r", encoding="utf-8") as handle:
        dataset = json.load(handle)
    if (not isinstance(dataset, dict) or dataset.get("schema_version") != 1
            or dataset.get("source") != "BINANCE_USDM_MARK_PRICE_KLINES"
            or dataset.get("market") != "FUTURES" or dataset.get("symbol") != symbol
            or dataset.get("timeframe") != "1h"):
        raise ValueError(f"{symbol}: mark-price dataset metadata mismatch")
    if (dataset.get("start_ms") != expected.get("start_ms")
            or dataset.get("end_ms") != expected.get("end_ms")
            or dataset.get("data_sha256") != expected.get("data_sha256")
            or dataset.get("candle_count") != expected.get("candle_count")):
        raise ValueError(f"{symbol}: mark-price dataset does not match report manifest")
    candles = dataset.get("candles")
    if not isinstance(candles, list) or len(candles) != dataset["candle_count"]:
        raise ValueError(f"{symbol}: mark-price candle count mismatch")
    digest = hashlib.sha256(
        json.dumps(candles, separators=(",", ":"), allow_nan=False).encode("utf-8")
    ).hexdigest()
    if digest != dataset.get("data_sha256"):
        raise ValueError(f"{symbol}: mark-price SHA-256 mismatch")
    return candles


def _portfolio_gate(oos: Mapping, folds: Sequence[Mapping]) -> dict:
    checks = []

    def add(name: str, passed: bool, detail: str) -> None:
        checks.append({"name": name, "status": "PASS" if passed else "FAIL", "detail": detail})

    add("minimum_oos_trades", oos["executed_trade_count"] >= 100,
        f"executed={oos['executed_trade_count']}; required=100")
    add("positive_oos_net_pnl", oos["net_pnl_usdt"] > 0,
        f"net_pnl_usdt={oos['net_pnl_usdt']}")
    add("positive_oos_expectancy", oos["expectancy_usdt"] > 0,
        f"expectancy_usdt={oos['expectancy_usdt']}")
    pf = oos.get("profit_factor")
    add("minimum_profit_factor", pf is not None and pf >= 1.20,
        f"profit_factor={pf}; required=1.20")
    add("maximum_drawdown", oos["max_drawdown_percent"] <= 15.0,
        f"max_drawdown_percent={oos['max_drawdown_percent']}; maximum=15.0")
    add("required_fold_count", len(folds) == 3, f"observed={len(folds)}; required=3")
    enough = all(fold["executed_trade_count"] >= 20 for fold in folds)
    add("minimum_trades_per_fold", enough,
        "executed=" + ",".join(str(f["executed_trade_count"]) for f in folds) + "; required=20 each")
    positive = sum(fold["net_pnl_usdt"] > 0 for fold in folds)
    add("positive_walk_forward_folds", positive == 3, f"positive={positive}; required=3")
    performance_failed = any(item["status"] == "FAIL" for item in checks)
    return {
        "status": "FAIL" if performance_failed else "INCONCLUSIVE",
        "checks": checks,
        "funding_included": False,
        "liquidation_modelled": False,
        "interpretation": (
            "At least one shared-wallet performance threshold failed." if performance_failed
            else "Performance thresholds passed, but funding and liquidation evidence are still incomplete."
        ),
        "automatic_orders": False,
    }


def run_report_directory(reports_dir: str | Path, mark_price_dir: str | Path,
                         output_path: str | Path | None = None,
                         initial_equity: float = 100.0) -> tuple[dict, Path]:
    reports_root = Path(reports_dir)
    marks_root = Path(mark_price_dir)
    report_paths = sorted(reports_root.glob("futures_vision_*_730d_*.json"))
    if not report_paths:
        raise ValueError("No 730-day Binance Vision per-symbol reports were found")
    all_oos = []
    per_symbol = {}
    marks = {}
    fold_trades = None
    fold_windows = None
    for report_path in report_paths:
        with report_path.open("r", encoding="utf-8") as handle:
            report = json.load(handle)
        if (not isinstance(report, dict) or report.get("report_schema_version") != 2
                or report.get("automatic_orders") is not False):
            raise ValueError(f"{report_path.name}: unsupported report or safety metadata")
        dataset = report.get("dataset", {})
        symbol = dataset.get("symbol")
        if (dataset.get("market") != "FUTURES" or not isinstance(symbol, str)
                or symbol in per_symbol):
            raise ValueError(f"{report_path.name}: invalid/duplicate Futures symbol")
        chrono = report.get("chronological_validation", {})
        assumptions = chrono.get("assumptions", {})
        if assumptions.get("funding_costs_included") is not False:
            raise ValueError(f"{symbol}: Vision funding must remain explicitly excluded")
        oos_trades = chrono.get("out_of_sample_trades")
        folds = report.get("walk_forward", {}).get("folds")
        if not isinstance(oos_trades, list) or not isinstance(folds, list) or len(folds) != 3:
            raise ValueError(f"{symbol}: missing OOS trades or exactly three walk-forward folds")
        all_oos.extend(dict(trade, symbol=symbol) for trade in oos_trades)
        if fold_trades is None:
            fold_trades = [[] for _ in folds]
            fold_windows = []
        if len(folds) != len(fold_trades):
            raise ValueError("Symbols have inconsistent walk-forward fold counts")
        for index, fold in enumerate(folds):
            window = (fold.get("test_start_timestamp"), fold.get("test_end_timestamp"))
            if fold_windows is None or len(fold_windows) <= index:
                fold_windows.append(window)
            elif fold_windows[index] != window:
                raise ValueError("Symbols do not share identical walk-forward test windows")
            trades = fold.get("trades")
            if not isinstance(trades, list):
                raise ValueError(f"{symbol}: fold {index + 1} trades are malformed")
            fold_trades[index].extend(dict(trade, symbol=symbol) for trade in trades)
        mark_manifest = dataset.get("mark_price")
        if not isinstance(mark_manifest, dict):
            raise ValueError(f"{symbol}: report has no mark-price manifest")
        filename = (f"{symbol.replace('/', '-')}_1h_"
                    f"{mark_manifest.get('start_ms')}_{mark_manifest.get('end_ms')}.json")
        mark_path = marks_root / filename
        marks[symbol] = _load_verified_mark_dataset(mark_path, symbol, mark_manifest)
        per_symbol[symbol] = {
            "report": report_path.name,
            "oos_trade_count": len(oos_trades),
            "walk_forward_trade_counts": [len(fold.get("trades", [])) for fold in folds],
        }

    oos_result = simulate_shared_wallet(all_oos, marks, initial_equity=initial_equity)
    fold_results = []
    for index, trades in enumerate(fold_trades):
        result = simulate_shared_wallet(trades, marks, initial_equity=initial_equity)
        result["fold"] = index + 1
        result["test_start_timestamp"] = fold_windows[index][0]
        result["test_end_timestamp"] = fold_windows[index][1]
        fold_results.append(result)
    gate = _portfolio_gate(oos_result, fold_results)
    summary = {
        "schema_version": 1,
        "market": "FUTURES",
        "source": "SI-AI Binance Vision 730-day per-symbol reports; shared-wallet replay",
        "initial_equity_usdt": initial_equity,
        "symbols": sorted(per_symbol),
        "per_symbol_inputs": per_symbol,
        "out_of_sample": oos_result,
        "walk_forward_folds": fold_results,
        "profitability_gate": gate,
        "portfolio_simulation": True,
        "funding_included": False,
        "liquidation_modelled": False,
        "certification": "INCONCLUSIVE",
        "automatic_orders": False,
    }
    destination = Path(output_path) if output_path is not None else (
        reports_root / "futures_shared_wallet_730d.json"
    )
    _atomic_json(destination, summary)
    return summary, destination


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--reports-dir", default="data/reports")
    parser.add_argument("--mark-price-dir", default="data/historical/mark_price")
    parser.add_argument("--output", default="data/reports/futures_shared_wallet_730d.json")
    parser.add_argument("--initial-equity", type=float, default=100.0)
    args = parser.parse_args()
    summary, path = run_report_directory(
        args.reports_dir, args.mark_price_dir, args.output, args.initial_equity
    )
    print(json.dumps({
        "out_of_sample": {key: value for key, value in summary["out_of_sample"].items()
                          if key not in ("completed_trades", "limitations")},
        "walk_forward_folds": [{key: value for key, value in fold.items()
                                if key not in ("completed_trades", "limitations")}
                               for fold in summary["walk_forward_folds"]],
        "profitability_gate": summary["profitability_gate"],
        "certification": summary["certification"],
        "automatic_orders": summary["automatic_orders"],
        "summary_path": str(path),
    }, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
