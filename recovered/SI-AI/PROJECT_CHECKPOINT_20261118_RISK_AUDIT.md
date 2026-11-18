# SI-AI Project Checkpoint — 2026-11-18 Risk/Scanner Audit

## Active validation candidate

- Repository: `Eventodigital473/SI-AI`
- Candidate branch: `fix/scanner-risk-audit-2026-11-18`
- Draft PR: [#17 — Independently validate Futures risk sizing before alerts](https://github.com/Eventodigital473/SI-AI/pull/17)
- Latest code/test head at checkpoint creation: `004416f059bc1344fd23dc6ddc30bac390e4649d`
- Latest CI: [44247607772](https://github.com/Eventodigital473/SI-AI/actions/runs/44247607772) — 206 passed, 4 subtests passed; dependency consistency, minimal synchronous Termux CCXT profile, Widget shell validation and Python compilation passed.
- PR #17 is open, draft, mergeable and unmerged. No changes were made to `main` or the user's Termux checkout.

## Verified risk and scanner work

- Rechecked the fee-aware long/short formulas in `SI_AI_smc.py`; the engine's per-unit risk, net reward, quantity, notional, fees, slippage and margin calculations are algebraically consistent with the configured assumptions.
- Added independent tests for long and short net R:R and the `entry_slippage_included=True` backtest path.
- Hardened scanner `valid_risk()`: it now independently recomputes net R:R and theoretical position sizing, then verifies quantity, notional, gross/total risk, fees, slippage, net target reward, leverage and margin fields. Missing or inconsistent fields fail closed to WAIT.
- Added scanner regression tests for valid BUY/SELL, forged R:R, a claimed 2:1 value when actual net R:R is below 2:1, oversized sizing, inconsistent notional and missing sizing fields.
- Alerts now explicitly label net Reward/Risk after fees/slippage and include estimated net target reward.
- Updated the Termux runbook to clone this isolated candidate into `~/SI-AI_FINAL_VALIDATION`, preserving the existing checkout.
- Static code search across the active engine, scanner, API, backtest, data and liquidation modules found no order-placement, cancellation, leverage-setting, private endpoint or balance-fetch calls.

## Current policy and scope

- Futures-only; Spot remains excluded from the active engine, scanner and backtest.
- Signal and notification provider only. User manually executes any Binance trade.
- Reference paper equity: 100 USDT.
- Risk per trade: 0.5% (0.50 USDT).
- Maximum margin allocation: 20% (20 USDT).
- Conservative leverage guidance: 1x.
- Minimum fee/slippage-adjusted net Reward/Risk: 2:1.
- No private API keys, account endpoints or automatic order execution.

## Verified limitations — do not certify live trading or profitability

1. Live Binance amount/price precision, minimum quantity and minimum notional are not machine-validated in the signal alert. The alert explicitly tells the user to check filters, round quantity down only, and skip if exchange minimums or the risk budget would be violated.
2. Historical 1h mark-price candles are downloaded, integrity-checked and required to match primary 1h OHLCV timestamps exactly, but the backtest does not simulate liquidation events. Historical maintenance-tier snapshots with valid historical effective times are still missing. Profitability gate therefore remains INCONCLUSIVE.
3. `backtesting.py` currently builds its drawdown equity curve from realized trade exits; it does not mark open positions to market between entry and exit. Reported max drawdown can therefore understate intratrade adverse excursion. This needs a separate conservative mark-to-market audit before profitability certification.
4. No 180-day public Futures backtest has yet produced a reviewed report.
5. The prior live-universe diagnosis found 182 volume-qualified Futures contracts; a fresh Termux bookTicker/spread diagnosis remains pending.
6. Android notification delivery previously timed out. The separate Termux:API companion app and Android notification permission have not been confirmed. The candidate branch provides `python si_ai_scanner.py --test-notifications` for BUY/SELL/WAIT device-only smoke tests.

## Exact next steps

1. Run `recovered/SI-AI/TERMUX_FINAL_TEST_RUNBOOK.md` from the candidate branch in the separate validation folder. Return pytest, preflight, live dry-run and test-notification outputs.
2. Review the 180-day BTC Futures report; keep certification INCONCLUSIVE unless all required evidence gates pass.
3. Audit and correct conservative mark-to-market drawdown measurement before any profitability claim.
4. Resolve historical maintenance-tier coverage and liquidation-event simulation only when the timestamped source data can be validated.
5. Do not merge PR #17, PR #16, or any branch into `main` without explicit user approval.

**Safety remains unchanged:** SI-AI only generates signals and notifications. No Binance orders are ever placed by the project.
