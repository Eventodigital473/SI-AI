"""Strict, fail-closed profitability evidence gate for SI-AI.

A positive backtest is not sufficient. This module never labels a strategy
profitable unless chronological OOS and every walk-forward fold satisfy policy.
It does not promise or predict future returns.
"""
from __future__ import annotations

from typing import Dict


DEFAULT_POLICY = {
    "minimum_oos_trades": 100,
    "minimum_trades_per_fold": 20,
    "minimum_profit_factor": 1.20,
    "maximum_drawdown_percent": 15.0,
    "minimum_positive_walk_forward_folds": 3,
    "required_walk_forward_folds": 3,
}


def _finite_number(value):
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    if number != number or number in (float("inf"), float("-inf")):
        return None
    return number


def evaluate_profitability_evidence(
    chronological_report: Dict,
    walk_forward_report: Dict,
    *,
    market: str,
    policy: Dict | None = None,
) -> Dict:
    """Return PASS only when all minimum evidence and performance gates pass.

    Missing/invalid metrics are INCONCLUSIVE; observed threshold failures are
    FAIL. Futures cannot pass until historical funding and liquidation risk
    are explicitly modelled in the supplied evidence assumptions.
    """
    if market != "FUTURES":
        raise ValueError("Profitability certification supports FUTURES only")
    rules = dict(DEFAULT_POLICY)
    if policy:
        unknown = set(policy) - set(rules)
        if unknown:
            raise ValueError("Unknown profitability policy keys: " + ", ".join(sorted(unknown)))
        rules.update(policy)

    checks = []
    inconclusive = False
    failed = False

    oos = chronological_report.get("out_of_sample") if isinstance(chronological_report, dict) else None
    folds = walk_forward_report.get("folds") if isinstance(walk_forward_report, dict) else None
    if not isinstance(oos, dict) or not isinstance(folds, list):
        return {
            "status": "INCONCLUSIVE",
            "reason": "Missing chronological OOS or walk-forward evidence.",
            "checks": [{"name": "report_structure", "status": "INCONCLUSIVE"}],
            "policy": rules,
            "automatic_orders": False,
        }

    def check(name, passed, available=True, detail=""):
        nonlocal inconclusive, failed
        state = "PASS" if passed and available else "FAIL" if available else "INCONCLUSIVE"
        if state == "FAIL":
            failed = True
        elif state == "INCONCLUSIVE":
            inconclusive = True
        checks.append({"name": name, "status": state, "detail": detail})

    count = _finite_number(oos.get("trade_count"))
    enough_oos = count is not None and count >= rules["minimum_oos_trades"]
    check("minimum_oos_trades", enough_oos, enough_oos,
          f"observed={count}; required={rules['minimum_oos_trades']}")

    net = _finite_number(oos.get("net_pnl_usdt"))
    check("positive_oos_net_pnl", net is not None and net > 0, net is not None,
          f"observed={net}")

    expectancy = _finite_number(oos.get("expectancy_usdt"))
    check("positive_oos_expectancy", expectancy is not None and expectancy > 0,
          expectancy is not None, f"observed={expectancy}")

    pf = _finite_number(oos.get("profit_factor"))
    check("minimum_profit_factor", pf is not None and pf >= rules["minimum_profit_factor"],
          pf is not None, f"observed={pf}; required={rules['minimum_profit_factor']}")

    drawdown = _finite_number(oos.get("max_drawdown_percent"))
    check("maximum_drawdown", drawdown is not None and 0 <= drawdown <= rules["maximum_drawdown_percent"],
          drawdown is not None, f"observed={drawdown}; maximum={rules['maximum_drawdown_percent']}")

    required_folds = rules["required_walk_forward_folds"]
    valid_folds = [f for f in folds if isinstance(f, dict)]
    check("required_fold_count", len(valid_folds) >= required_folds,
          len(valid_folds) >= required_folds,
          f"observed={len(valid_folds)}; required={required_folds}")

    positive_folds = 0
    fold_evidence_complete = len(valid_folds) >= required_folds
    for index, fold in enumerate(valid_folds[:required_folds], start=1):
        trades = _finite_number(fold.get("trade_count"))
        pnl = _finite_number(fold.get("net_pnl_usdt"))
        enough = trades is not None and trades >= rules["minimum_trades_per_fold"]
        check(f"fold_{index}_minimum_trades", enough, trades is not None,
              f"observed={trades}; required={rules['minimum_trades_per_fold']}")
        positive = pnl is not None and pnl > 0
        if positive and enough:
            positive_folds += 1
        if not enough or pnl is None:
            fold_evidence_complete = False
        check(f"fold_{index}_positive_net_pnl", positive, enough and pnl is not None,
              f"observed={pnl}; sample_sufficient={enough}")

    check("positive_walk_forward_folds",
          positive_folds >= rules["minimum_positive_walk_forward_folds"],
          fold_evidence_complete,
          f"observed={positive_folds}; required={rules['minimum_positive_walk_forward_folds']}")

    assumptions = chronological_report.get("assumptions", {})
    if market == "FUTURES":
        funding_ok = isinstance(assumptions, dict) and assumptions.get("historical_funding_series_included") is True
        liquidation_ok = isinstance(assumptions, dict) and assumptions.get("liquidation_modelled") is True
        check("historical_funding_series", funding_ok, funding_ok,
              "Futures evidence must include timestamped historical funding events.")
        check("liquidation_model", liquidation_ok, liquidation_ok,
              "Futures evidence must model liquidation and maintenance margin.")

    status = "FAIL" if failed else "INCONCLUSIVE" if inconclusive else "PASS"
    return {
        "status": status,
        "checks": checks,
        "policy": rules,
        "interpretation": (
            "All configured historical evidence gates passed; this is not a guarantee of future profit."
            if status == "PASS" else
            "At least one required performance threshold failed." if status == "FAIL" else
            "Insufficient evidence or missing required market-cost/risk modelling; profitability is not certified."
        ),
        "automatic_orders": False,
    }
