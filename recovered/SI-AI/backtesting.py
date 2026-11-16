"""Deterministic, conservative OHLCV backtesting for SI-AI signals.

This module is offline-only: it never calls an exchange or places orders.
Signals are evaluated on data available at a candle close; entries occur no
earlier than the next candle open. If stop and target both trade in one bar,
the stop is assumed to execute first.
"""
from __future__ import annotations

import hashlib
import json
import math
from statistics import mean, pstdev
from typing import Callable, Dict, List, Optional

import SI_AI_smc as si


SignalFunction = Callable[[str, str, str, List[list]], Dict]


def _number(value, name: str, minimum: Optional[float] = None) -> float:
    try:
        result = float(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{name} must be numeric") from exc
    if not math.isfinite(result):
        raise ValueError(f"{name} must be finite")
    if minimum is not None and result < minimum:
        raise ValueError(f"{name} must be >= {minimum}")
    return result


def validate_ohlcv(candles: list) -> List[list]:
    """Validate ordered OHLCV rows without silently repairing the test data."""
    if not isinstance(candles, list) or len(candles) < si.MIN_CANDLES + 2:
        raise ValueError(f"At least {si.MIN_CANDLES + 2} candles are required")
    clean = []
    previous_ts = None
    for index, row in enumerate(candles):
        if not isinstance(row, (list, tuple)) or len(row) < 6:
            raise ValueError(f"Invalid OHLCV row at index {index}")
        ts, op, high, low, close, volume = row[:6]
        vals = [_number(v, f"candle[{index}]") for v in (ts, op, high, low, close, volume)]
        ts, op, high, low, close, volume = vals
        if ts <= 0 or (previous_ts is not None and ts <= previous_ts):
            raise ValueError("Candle timestamps must be positive and strictly increasing")
        if min(op, high, low, close) <= 0 or volume < 0:
            raise ValueError("OHLC prices must be positive and volume non-negative")
        if high < max(op, close, low) or low > min(op, close, high):
            raise ValueError("Invalid OHLC price relationships")
        clean.append([int(ts), op, high, low, close, volume])
        previous_ts = ts
    return clean


def _cost_adjusted_fill(price: float, side: str, is_entry: bool, slippage: float) -> float:
    adverse = 1.0 + slippage if (side == "LONG") == is_entry else 1.0 - slippage
    return price * adverse


def _metrics(trades: List[Dict], equity_curve: List[float], initial_equity: float) -> Dict:
    pnls = [t["net_pnl_usdt"] for t in trades]
    wins = [p for p in pnls if p > 0]
    losses = [p for p in pnls if p < 0]
    gross_profit, gross_loss = sum(wins), abs(sum(losses))
    returns = [t["return_on_entry_notional"] for t in trades]
    peak = initial_equity
    max_dd = 0.0
    for equity in equity_curve:
        peak = max(peak, equity)
        if peak > 0:
            max_dd = max(max_dd, (peak - equity) / peak)
    sharpe = None
    if len(returns) >= 2:
        deviation = pstdev(returns)
        if deviation > 0:
            sharpe = mean(returns) / deviation * math.sqrt(len(returns))
    return {
        "trade_count": len(trades),
        "win_rate_percent": (len(wins) / len(trades) * 100.0) if trades else 0.0,
        "gross_profit_usdt": round(gross_profit, 8),
        "gross_loss_usdt": round(gross_loss, 8),
        "profit_factor": round(gross_profit / gross_loss, 8) if gross_loss > 0 else None,
        "net_pnl_usdt": round(sum(pnls), 8),
        "expectancy_usdt": round(mean(pnls), 8) if pnls else 0.0,
        "max_drawdown_percent": round(max_dd * 100.0, 8),
        "sharpe_trade_based": round(sharpe, 8) if sharpe is not None else None,
        "ending_equity_usdt": round(equity_curve[-1] if equity_curve else initial_equity, 8),
        "profitable": bool(trades) and sum(pnls) > 0,
    }


def run_backtest(
    candles: list,
    market: str,
    symbol: str,
    timeframe: str,
    *,
    initial_equity: float = si.PAPER_EQUITY_USDT,
    risk_percent: float = si.RISK_PER_TRADE_PERCENT,
    fee_rate: Optional[float] = None,
    slippage_rate: float = si.PAPER_SLIPPAGE_RATE,
    max_holding_bars: int = 48,
    signal_fn: Optional[SignalFunction] = None,
    start_index: int = si.MIN_CANDLES,
) -> Dict:
    """Run a single-position, next-open backtest over chronological OHLCV.

    A strategy callback receives only the historical prefix ending at the
    signal candle. Default callback is SI-AI's current analyze_candles logic.
    """
    data = validate_ohlcv(candles)
    if market not in ("SPOT", "FUTURES"):
        raise ValueError("market must be SPOT or FUTURES")
    if timeframe not in si.TIMEFRAMES:
        raise ValueError("Unsupported timeframe")
    if not isinstance(symbol, str) or "/" not in symbol:
        raise ValueError("symbol must be a canonical BASE/QUOTE symbol")
    equity = _number(initial_equity, "initial_equity", 0.01)
    risk_pct = _number(risk_percent, "risk_percent", 0.001)
    if risk_pct > 5:
        raise ValueError("risk_percent above 5% is blocked")
    fee = _number(
        si.PAPER_TAKER_FEE_RATES[market] if fee_rate is None else fee_rate,
        "fee_rate", 0.0,
    )
    slippage = _number(slippage_rate, "slippage_rate", 0.0)
    if fee >= 0.05 or slippage >= 0.05:
        raise ValueError("Fee and slippage rates must each be below 5%")
    if isinstance(max_holding_bars, bool) or not isinstance(max_holding_bars, int) or max_holding_bars < 1:
        raise ValueError("max_holding_bars must be a positive integer")

    if isinstance(start_index, bool) or not isinstance(start_index, int) or start_index < si.MIN_CANDLES or start_index >= len(data) - 1:
        raise ValueError("start_index must leave enough warm-up and at least one future candle")
    callback = signal_fn or si.analyze_candles
    initial = equity
    equity_curve = [equity]
    trades = []
    i = start_index

    while i < len(data) - 1:
        history = data[:i]
        result = callback(market, symbol, timeframe, history)
        signal = result.get("signal") if isinstance(result, dict) else None
        if signal not in ("BUY", "SELL") or (market == "SPOT" and signal == "SELL"):
            i += 1
            continue

        side = "LONG" if signal == "BUY" else "SHORT"
        signal_close = history[-1][4]
        stop = _number(result.get("stop_loss"), "stop_loss", 0.00000001)
        target = _number(result.get("take_profit"), "take_profit", 0.00000001)
        if (side == "LONG" and not stop < signal_close < target) or (
            side == "SHORT" and not target < signal_close < stop
        ):
            i += 1
            continue

        entry_bar_index = i
        entry_raw = data[entry_bar_index][1]
        entry = _cost_adjusted_fill(entry_raw, side, True, slippage)
        if (side == "LONG" and not stop < entry < target) or (side == "SHORT" and not target < entry < stop):
            i += 1
            continue
        stop_distance = abs(entry - stop)
        round_trip_cost_per_unit = fee * (entry + stop) + slippage * (entry + stop)
        risk_per_unit = stop_distance + round_trip_cost_per_unit
        if risk_per_unit <= 0 or not math.isfinite(risk_per_unit):
            i += 1
            continue
        risk_budget = equity * risk_pct / 100.0
        quantity = min(
            risk_budget / risk_per_unit,
            equity * si.MAX_NOTIONAL_EQUITY_MULTIPLE / entry,
        )
        if quantity <= 0 or not math.isfinite(quantity):
            i += 1
            continue

        last_index = min(len(data) - 1, entry_bar_index + max_holding_bars - 1)
        exit_raw = None
        exit_reason = None
        exit_index = last_index
        for j in range(entry_bar_index, last_index + 1):
            bar = data[j]
            if side == "LONG":
                stop_hit, target_hit = bar[3] <= stop, bar[2] >= target
            else:
                stop_hit, target_hit = bar[2] >= stop, bar[3] <= target
            if stop_hit:
                exit_raw, exit_reason, exit_index = stop, "STOP", j
                break
            if target_hit:
                exit_raw, exit_reason, exit_index = target, "TARGET", j
                break
        if exit_raw is None:
            exit_raw, exit_reason = data[last_index][4], "TIME_EXIT"

        exit_fill = _cost_adjusted_fill(exit_raw, side, False, slippage)
        gross_pnl = (exit_fill - entry) * quantity
        if side == "SHORT":
            gross_pnl = (entry - exit_fill) * quantity
        fees = (entry + exit_fill) * quantity * fee
        net_pnl = gross_pnl - fees
        equity = max(0.0, equity + net_pnl)
        entry_notional = entry * quantity
        trades.append({
            "side": side,
            "signal_timestamp": history[-1][0],
            "entry_timestamp": data[entry_bar_index][0],
            "exit_timestamp": data[exit_index][0],
            "entry_price": round(entry, 10),
            "exit_price": round(exit_fill, 10),
            "stop_loss": round(stop, 10),
            "take_profit": round(target, 10),
            "quantity": round(quantity, 10),
            "gross_pnl_usdt": round(gross_pnl, 8),
            "fees_usdt": round(fees, 8),
            "net_pnl_usdt": round(net_pnl, 8),
            "return_on_entry_notional": net_pnl / entry_notional if entry_notional else 0.0,
            "exit_reason": exit_reason,
            "bars_held": exit_index - entry_bar_index + 1,
        })
        equity_curve.append(equity)
        i = exit_index + 1

    digest_source = json.dumps(data, separators=(",", ":"), allow_nan=False).encode()
    metrics = _metrics(trades, equity_curve, initial)
    return {
        "engine": "SI-AI conservative OHLCV backtest v1",
        "market": market,
        "symbol": symbol,
        "timeframe": timeframe,
        "data_start_timestamp": data[0][0],
        "data_end_timestamp": data[-1][0],
        "candle_count": len(data),
        "data_sha256": hashlib.sha256(digest_source).hexdigest(),
        "assumptions": {
            "entry": "next candle open after signal candle closes",
            "same_bar_stop_and_target": "stop first (conservative)",
            "fee_rate_per_side": fee,
            "slippage_rate_per_side": slippage,
            "risk_percent_per_trade": risk_pct,
            "max_notional_equity_multiple": si.MAX_NOTIONAL_EQUITY_MULTIPLE,
            "max_holding_bars": max_holding_bars,
            "funding_costs_included": False,
            "liquidation_modelled": False,
        },
        "metrics": metrics,
        "trades": trades,
        "equity_curve": [round(v, 8) for v in equity_curve],
        "status": "INCONCLUSIVE" if not trades else (
            "PROFITABLE_IN_SAMPLE_ONLY" if metrics["profitable"] else "NOT_PROFITABLE_IN_SAMPLE"
        ),
        "automatic_orders": False,
    }


def evaluate_chronological_validation(
    candles: list, market: str, symbol: str, timeframe: str, *,
    train_fraction: float = 0.70, **backtest_options,
) -> Dict:
    """Chronological holdout; OOS signals start at split with prior warm-up only."""
    data = validate_ohlcv(candles)
    fraction = _number(train_fraction, "train_fraction", 0.5)
    if fraction >= 0.9:
        raise ValueError("train_fraction must be below 0.9")
    split = int(len(data) * fraction)
    if split < si.MIN_CANDLES or len(data) - split < 3:
        raise ValueError("Not enough candles for chronological train/holdout split")
    train = run_backtest(data[:split], market, symbol, timeframe, **backtest_options)
    oos_options = dict(backtest_options)
    oos_options["start_index"] = split
    holdout = run_backtest(data, market, symbol, timeframe, **oos_options)
    oos_trades = holdout["trades"]
    initial = _number(oos_options.get("initial_equity", si.PAPER_EQUITY_USDT), "initial_equity", 0.01)
    curve = [initial]
    for trade in oos_trades:
        curve.append(max(0.0, curve[-1] + trade["net_pnl_usdt"]))
    oos_metrics = _metrics(oos_trades, curve, initial)
    return {
        "split_index": split,
        "split_timestamp": data[split][0],
        "train": train["metrics"],
        "out_of_sample": oos_metrics,
        "out_of_sample_trades": oos_trades,
        "status": "INCONCLUSIVE" if not oos_trades else (
            "OUT_OF_SAMPLE_PROFITABLE" if oos_metrics["profitable"] else "OUT_OF_SAMPLE_NOT_PROFITABLE"
        ),
        "automatic_orders": False,
    }
