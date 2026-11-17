"""Paper-only Binance USD-M Futures high-leverage risk planner.

This module never calls Binance, reads credentials, or places orders. The caller
must supply a current, account-appropriate leverage bracket snapshot obtained
securely outside this module. Missing/stale/unverified bracket data must fail
closed. Liquidation is an estimate under isolated-margin assumptions only.
"""
from __future__ import annotations

import math
from typing import Dict, List

TARGET_RISK_PERCENT = 10.0
DEFAULT_FEE_RATE = 0.0005
DEFAULT_SLIPPAGE_RATE = 0.0002
DEFAULT_LIQUIDATION_BUFFER_PERCENT = 0.5


def _positive(value, name: str) -> float:
    if isinstance(value, bool):
        raise ValueError(f"{name} must be a finite positive number")
    try:
        result = float(value)
    except (TypeError, ValueError):
        raise ValueError(f"{name} must be a finite positive number")
    if not math.isfinite(result) or result <= 0:
        raise ValueError(f"{name} must be a finite positive number")
    return result


def _bracket_for(notional: float, brackets: List[Dict]) -> Dict:
    valid = []
    for item in brackets:
        if not isinstance(item, dict):
            raise ValueError("Every Binance leverage bracket must be an object")
        floor = float(item.get("notionalFloor", 0))
        cap = _positive(item.get("notionalCap"), "notionalCap")
        leverage = _positive(item.get("initialLeverage"), "initialLeverage")
        try:
            mmr, cum = float(item["maintMarginRatio"]), float(item["cum"])
        except (KeyError, TypeError, ValueError):
            raise ValueError("Bracket must include maintenance margin ratio and cum")
        if not math.isfinite(floor) or floor < 0:
            raise ValueError("Invalid notional floor")
        if not math.isfinite(mmr) or not 0 <= mmr < 1:
            raise ValueError("Invalid maintenance margin ratio")
        if not math.isfinite(cum) or cum < 0:
            raise ValueError("Invalid maintenance margin amount")
        valid.append((floor, cap, leverage, mmr, cum, item))
    valid.sort(key=lambda row: row[0])
    for floor, cap, _, _, _, item in valid:
        if floor <= notional <= cap:
            return item
    raise ValueError("Position notional is outside supplied Binance leverage brackets")


def build_paper_plan(
    *,
    wallet_equity_usdt: float,
    entry_price: float,
    stop_loss: float,
    side: str,
    leverage_brackets: List[Dict],
    fee_rate: float = DEFAULT_FEE_RATE,
    slippage_rate: float = DEFAULT_SLIPPAGE_RATE,
    liquidation_buffer_percent: float = DEFAULT_LIQUIDATION_BUFFER_PERCENT,
) -> Dict:
    """Build a 10%-wallet-risk paper plan using the bracket's maximum leverage.

    side is BUY (long) or SELL (short). Brackets must be a current, verified
    Binance USD-M Futures snapshot for the exact symbol/account tier. This
    assumes isolated margin and rejects a plan if estimated liquidation is
    not beyond the stop plus the configured safety buffer.
    """
    equity = _positive(wallet_equity_usdt, "wallet_equity_usdt")
    entry = _positive(entry_price, "entry_price")
    stop = _positive(stop_loss, "stop_loss")
    fee = float(fee_rate)
    slip = float(slippage_rate)
    buffer_pct = float(liquidation_buffer_percent)
    if not all(math.isfinite(x) for x in (fee, slip, buffer_pct)):
        raise ValueError("Cost and buffer inputs must be finite")
    if not 0 <= fee < 0.05 or not 0 <= slip < 0.05:
        raise ValueError("Fee and slippage rates must be in [0, 5%)")
    if not 0 <= buffer_pct <= 20:
        raise ValueError("Liquidation buffer must be in [0, 20%]")
    direction = str(side).upper()
    if direction not in ("BUY", "SELL"):
        raise ValueError("side must be BUY or SELL")
    if (direction == "BUY" and stop >= entry) or (direction == "SELL" and stop <= entry):
        raise ValueError("Stop-loss is on the wrong side of entry")
    if not isinstance(leverage_brackets, list) or not leverage_brackets:
        raise ValueError("Verified Binance leverage brackets are required")

    risk_budget = equity * TARGET_RISK_PERCENT / 100.0
    round_trip_cost_per_unit = (fee + slip) * (entry + stop)
    risk_per_unit = abs(entry - stop) + round_trip_cost_per_unit
    if not math.isfinite(risk_per_unit) or risk_per_unit <= 0:
        raise ValueError("Invalid per-unit risk after estimated costs")

    quantity = risk_budget / risk_per_unit
    notional = quantity * entry
    bracket = _bracket_for(notional, leverage_brackets)
    max_notional = float(bracket["notionalCap"])
    if notional > max_notional:
        quantity = max_notional / entry
        notional = quantity * entry
        risk_budget_used = quantity * risk_per_unit
    else:
        risk_budget_used = risk_budget

    leverage = _positive(bracket["initialLeverage"], "initialLeverage")
    mmr = float(bracket["maintMarginRatio"])
    maintenance_cum = float(bracket["cum"])
    isolated_margin = notional / leverage

    if direction == "BUY":
        liquidation = (
            quantity * entry - isolated_margin + maintenance_cum
        ) / (quantity * (1.0 - mmr))
        stop_with_buffer = stop * (1.0 - buffer_pct / 100.0)
        safe = liquidation < stop_with_buffer
    else:
        liquidation = (
            quantity * entry + isolated_margin - maintenance_cum
        ) / (quantity * (1.0 + mmr))
        stop_with_buffer = stop * (1.0 + buffer_pct / 100.0)
        safe = liquidation > stop_with_buffer

    if not math.isfinite(liquidation) or liquidation <= 0:
        raise ValueError("Estimated liquidation price is invalid")
    if not safe:
        raise ValueError(
            "Maximum bracket leverage fails the liquidation buffer; signal must be WAIT"
        )

    return {
        "mode": "PAPER_ONLY_BINANCE_USDM_HIGH_LEVERAGE",
        "side": direction,
        "wallet_equity_usdt": equity,
        "risk_percent": TARGET_RISK_PERCENT,
        "risk_budget_usdt": risk_budget,
        "estimated_risk_usdt": risk_budget_used,
        "quantity": quantity,
        "notional_usdt": notional,
        "maximum_bracket_leverage": int(leverage),
        "estimated_isolated_margin_usdt": isolated_margin,
        "estimated_liquidation_price": liquidation,
        "stop_loss": stop,
        "liquidation_buffer_percent": buffer_pct,
        "maintenance_margin_ratio": mmr,
        "estimated_round_trip_fee_slippage_usdt": quantity * round_trip_cost_per_unit,
        "warning": (
            "Paper estimate only. Liquidation can differ due to funding, "
            "mark price, fee deductions, tier changes, and exchange rules. "
            "Never treat this estimate as a guaranteed liquidation price."
        ),
    }
