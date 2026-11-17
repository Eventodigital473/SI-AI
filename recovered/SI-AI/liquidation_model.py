"""Fail-closed Binance USD-M isolated liquidation price calculator.

This module calculates a single one-way isolated position only. It does not
model cross margin, hedge mode, other positions, auto-add margin, ADL, or
historical liquidation events. Maintenance tiers must come from a recent,
symbol-specific Binance bracket snapshot supplied by the operator.
"""
from __future__ import annotations

from datetime import datetime, timezone
import math


SNAPSHOT_MAX_AGE_SECONDS = 24 * 60 * 60


def _finite(value, name, *, minimum=None):
    if isinstance(value, bool):
        raise ValueError(f"{name} must be numeric, not boolean")
    try:
        result = float(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{name} must be numeric") from exc
    if not math.isfinite(result):
        raise ValueError(f"{name} must be finite")
    if minimum is not None and result < minimum:
        raise ValueError(f"{name} must be >= {minimum}")
    return result


def _parse_utc(value):
    if not isinstance(value, str) or not value.strip():
        raise ValueError("snapshot retrieved_at must be an ISO-8601 timestamp")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ValueError("snapshot retrieved_at must be an ISO-8601 timestamp") from exc
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ValueError("snapshot retrieved_at must include a timezone")
    return parsed.astimezone(timezone.utc)


def validate_bracket_snapshot(snapshot, *, symbol, now=None):
    """Validate recent symbol-specific tiers; never invent fallback MMR values."""
    if not isinstance(snapshot, dict):
        raise ValueError("A verified Binance bracket snapshot is required")
    if snapshot.get("symbol") != symbol:
        raise ValueError("Maintenance bracket snapshot symbol mismatch")
    if snapshot.get("source") != "BINANCE_USDM_LEVERAGE_BRACKET":
        raise ValueError("Unsupported maintenance bracket snapshot source")
    retrieved = _parse_utc(snapshot.get("retrieved_at"))
    current = datetime.now(timezone.utc) if now is None else now
    if not isinstance(current, datetime) or current.tzinfo is None:
        raise ValueError("now must be timezone-aware")
    age = (current.astimezone(timezone.utc) - retrieved).total_seconds()
    if age < 0 or age > SNAPSHOT_MAX_AGE_SECONDS:
        raise ValueError("Maintenance bracket snapshot is future-dated or stale")

    raw_tiers = snapshot.get("tiers")
    if not isinstance(raw_tiers, list) or not raw_tiers:
        raise ValueError("Snapshot must contain maintenance tiers")
    tiers = []
    for index, item in enumerate(raw_tiers):
        if not isinstance(item, dict):
            raise ValueError(f"Invalid maintenance tier at index {index}")
        floor = _finite(item.get("notional_floor"), "notional_floor", minimum=0)
        cap_value = item.get("notional_cap")
        cap = None if cap_value is None else _finite(
            cap_value, "notional_cap", minimum=0
        )
        mmr = _finite(item.get("maintenance_margin_rate"),
                      "maintenance_margin_rate", minimum=0)
        cum = _finite(item.get("maintenance_amount"),
                      "maintenance_amount", minimum=0)
        max_lev = _finite(item.get("max_leverage"), "max_leverage", minimum=1)
        if mmr >= 1:
            raise ValueError("Maintenance margin rate must be below 1")
        if cap is not None and cap <= floor:
            raise ValueError("Tier cap must be greater than its floor")
        tiers.append({
            "notional_floor": floor,
            "notional_cap": cap,
            "maintenance_margin_rate": mmr,
            "maintenance_amount": cum,
            "max_leverage": max_lev,
        })

    tiers.sort(key=lambda tier: tier["notional_floor"])
    if tiers[0]["notional_floor"] != 0:
        raise ValueError("Maintenance tiers must start at zero notional")
    for previous, current_tier in zip(tiers, tiers[1:]):
        if previous["notional_cap"] != current_tier["notional_floor"]:
            raise ValueError("Maintenance tiers must be contiguous and non-overlapping")
    if tiers[-1]["notional_cap"] is not None:
        raise ValueError("Final maintenance tier must have an open-ended cap")
    return tiers


def calculate_isolated_liquidation_price(
    *,
    symbol,
    side,
    quantity,
    entry_price,
    isolated_wallet_balance,
    leverage,
    bracket_snapshot,
    now=None,
):
    """Calculate one-way isolated liquidation price using Binance's tier formula.

    The isolated wallet balance is the actual margin balance assigned to this
    position (initial margin plus/minus any added/removed margin and realized
    adjustments). It is not the user's total Futures wallet balance.
    """
    if side not in ("LONG", "SHORT"):
        raise ValueError("side must be LONG or SHORT")
    qty = _finite(quantity, "quantity", minimum=1e-16)
    entry = _finite(entry_price, "entry_price", minimum=1e-16)
    wallet = _finite(isolated_wallet_balance, "isolated_wallet_balance", minimum=1e-16)
    lev = _finite(leverage, "leverage", minimum=1)
    tiers = validate_bracket_snapshot(bracket_snapshot, symbol=symbol, now=now)

    entry_notional = qty * entry
    entry_tier = next(
        (tier for tier in tiers
         if entry_notional >= tier["notional_floor"]
         and (tier["notional_cap"] is None or entry_notional < tier["notional_cap"])),
        None,
    )
    if entry_tier is None:
        raise ValueError("Entry notional is outside the supplied maintenance tiers")
    if lev > entry_tier["max_leverage"]:
        raise ValueError("Selected leverage exceeds the bracket tier maximum")

    direction = 1.0 if side == "LONG" else -1.0
    candidates = []
    positive_prices = []
    for tier in tiers:
        mmr = tier["maintenance_margin_rate"]
        cum = tier["maintenance_amount"]
        denominator = qty * (mmr - direction)
        if abs(denominator) < 1e-15:
            continue
        # Binance USD-M one-way formula with isolated TMM=0 and UPNL=0:
        # LP = (isolatedWallet + maintenanceAmount - side*qty*entry)
        #      / (qty*MMR - side*qty)
        price = (wallet + cum - direction * qty * entry) / denominator
        if not math.isfinite(price) or price <= 0:
            continue
        liquidation_notional = qty * price
        positive_prices.append((price, tier, liquidation_notional))
        in_tier = (
            liquidation_notional >= tier["notional_floor"] - 1e-9
            and (tier["notional_cap"] is None
                 or liquidation_notional < tier["notional_cap"] + 1e-9)
        )
        if in_tier:
            candidates.append((price, tier, liquidation_notional))

    if not candidates and positive_prices:
        raise ValueError(
            "Could not uniquely resolve liquidation tier from this snapshot; "
            "refuse to display an uncertified liquidation price"
        )
    if not candidates:
        # At very low leverage an ideal isolated long can have no positive
        # liquidation threshold in the linear USDT price domain. This is not
        # equivalent to a guarantee against liquidation or exchange adjustments.
        return {
            "status": "NO_POSITIVE_LIQUIDATION_PRICE_IN_MODEL",
            "symbol": symbol,
            "side": side,
            "liquidation_price": None,
            "entry_price": entry,
            "quantity": qty,
            "entry_notional_usdt": round(entry_notional, 8),
            "isolated_wallet_balance_usdt": wallet,
            "leverage": lev,
            "margin_mode": "ISOLATED",
            "position_mode": "ONE_WAY",
            "bracket_snapshot_retrieved_at": bracket_snapshot["retrieved_at"],
            "automatic_orders": False,
            "limitations": [
                "The model produced no positive liquidation threshold under the supplied isolated-margin assumptions.",
                "This is not a guarantee against liquidation; fees, funding, margin adjustments and exchange rules can change the result.",
                "Recheck Binance's displayed liquidation price and margin ratio before manual execution.",
            ],
        }
    if len(candidates) != 1:
        raise ValueError(
            "Could not uniquely resolve liquidation tier from this snapshot; "
            "refuse to display an uncertified liquidation price"
        )
    price, tier, liquidation_notional = candidates[0]
    return {
        "status": "CALCULATED_ISOLATED_ESTIMATE",
        "symbol": symbol,
        "side": side,
        "liquidation_price": round(price, 12),
        "entry_price": entry,
        "quantity": qty,
        "entry_notional_usdt": round(entry_notional, 8),
        "liquidation_notional_usdt": round(liquidation_notional, 8),
        "isolated_wallet_balance_usdt": wallet,
        "leverage": lev,
        "margin_mode": "ISOLATED",
        "position_mode": "ONE_WAY",
        "maintenance_margin_rate": tier["maintenance_margin_rate"],
        "maintenance_amount_usdt": tier["maintenance_amount"],
        "tier_max_leverage": tier["max_leverage"],
        "bracket_snapshot_retrieved_at": bracket_snapshot["retrieved_at"],
        "automatic_orders": False,
        "limitations": [
            "Estimate is valid only for the supplied recent Binance symbol-specific tier snapshot.",
            "Use the actual isolated wallet balance, not total Futures wallet balance.",
            "Cross margin, hedge mode, other positions, auto-add margin, fees/funding adjustments, ADL and exchange-side changes are not modelled.",
            "Liquidation is triggered against mark price; a last-traded-price chart is not an exact liquidation trigger.",
            "Recheck Binance's displayed liquidation price and margin ratio before manual execution.",
        ],
    }
