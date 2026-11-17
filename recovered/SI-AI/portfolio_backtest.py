"""Conservative shared-equity portfolio replay for multi-symbol Spot research."""
from __future__ import annotations

import math
from typing import Dict, Iterable

import backtesting
import SI_AI_smc as smc


def _finite(value, name):
    try:
        result = float(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{name} must be numeric") from exc
    if not math.isfinite(result):
        raise ValueError(f"{name} must be finite")
    return result


def simulate_spot_portfolio(
    trades: Iterable[Dict],
    *,
    initial_equity: float = smc.PAPER_EQUITY_USDT,
    risk_percent: float = smc.RISK_PER_TRADE_PERCENT,
    max_notional_multiple: float = smc.MAX_NOTIONAL_EQUITY_MULTIPLE,
    fee_rate: float = smc.PAPER_TAKER_FEE_RATES["SPOT"],
    slippage_rate: float = smc.PAPER_SLIPPAGE_RATE,
) -> Dict:
    """Replay candidate Spot-long trades against one shared wallet.

    The simulator allows one open position at a time. Overlapping cross-symbol
    opportunities are skipped rather than pretending every symbol has its own
    independent wallet. Entry/exit prices already include the source backtest's
    adverse slippage fills; fees and position size are recalculated on shared
    portfolio equity.
    """
    equity = _finite(initial_equity, "initial_equity")
    risk_pct = _finite(risk_percent, "risk_percent")
    notional_multiple = _finite(max_notional_multiple, "max_notional_multiple")
    fee = _finite(fee_rate, "fee_rate")
    slippage = _finite(slippage_rate, "slippage_rate")
    if equity <= 0 or not 0 < risk_pct <= 5:
        raise ValueError("Invalid portfolio equity or risk percentage")
    if not 0 < notional_multiple <= 1:
        raise ValueError("max_notional_multiple must be in (0, 1]")
    if not 0 <= fee < 0.05 or not 0 <= slippage < 0.05:
        raise ValueError("Fee and slippage must be in [0, 5%)")

    candidates = [dict(item) for item in trades if isinstance(item, dict)]
    candidates.sort(key=lambda item: (
        int(item.get("entry_timestamp", 0)),
        int(item.get("_symbol_rank", 10**9)),
        str(item.get("symbol", "")),
    ))

    accepted = []
    equity_curve = [equity]
    last_exit_timestamp = None
    skipped_overlap = 0
    skipped_invalid = 0

    for candidate in candidates:
        try:
            entry_timestamp = int(candidate["entry_timestamp"])
            exit_timestamp = int(candidate["exit_timestamp"])
            entry = _finite(candidate["entry_price"], "entry_price")
            exit_price = _finite(candidate["exit_price"], "exit_price")
            stop = _finite(candidate["stop_loss"], "stop_loss")
            side = str(candidate.get("side", "")).upper()
        except (KeyError, TypeError, ValueError):
            skipped_invalid += 1
            continue

        if (
            entry_timestamp <= 0
            or exit_timestamp < entry_timestamp
            or entry <= 0
            or exit_price <= 0
            or stop <= 0
            or side != "LONG"
            or stop >= entry
        ):
            skipped_invalid += 1
            continue

        if last_exit_timestamp is not None and entry_timestamp <= last_exit_timestamp:
            skipped_overlap += 1
            continue

        # Entry prices already include adverse entry slippage in the source
        # backtest; reserve only the stop-exit slippage here.
        round_trip_cost_per_unit = fee * (entry + stop) + slippage * stop
        risk_per_unit = (entry - stop) + round_trip_cost_per_unit
        if risk_per_unit <= 0 or not math.isfinite(risk_per_unit):
            skipped_invalid += 1
            continue

        risk_budget = equity * risk_pct / 100.0
        notional_cap = equity * notional_multiple
        quantity = min(risk_budget / risk_per_unit, notional_cap / entry)
        if quantity <= 0 or not math.isfinite(quantity):
            skipped_invalid += 1
            continue

        gross_pnl = (exit_price - entry) * quantity
        fees = (entry + exit_price) * quantity * fee
        net_pnl = gross_pnl - fees
        entry_notional = entry * quantity
        equity = max(0.0, equity + net_pnl)

        accepted.append({
            **candidate,
            "side": "LONG",
            "quantity": round(quantity, 10),
            "entry_notional_usdt": round(entry_notional, 8),
            "gross_pnl_usdt": round(gross_pnl, 8),
            "fees_usdt": round(fees, 8),
            "funding_cost_usdt": 0.0,
            "net_pnl_usdt": round(net_pnl, 8),
            "return_on_entry_notional": net_pnl / entry_notional if entry_notional else 0.0,
            "portfolio_equity_after_usdt": round(equity, 8),
        })
        equity_curve.append(equity)
        last_exit_timestamp = exit_timestamp

    metrics = backtesting._metrics(accepted, equity_curve, initial_equity)
    return {
        "metrics": metrics,
        "trades": accepted,
        "equity_curve": equity_curve,
        "skipped_overlapping_trades": skipped_overlap,
        "skipped_invalid_trades": skipped_invalid,
        "max_concurrent_positions": 1,
        "automatic_orders": False,
    }
