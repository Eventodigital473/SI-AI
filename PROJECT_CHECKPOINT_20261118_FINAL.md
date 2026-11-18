# SI-AI Resume Checkpoint — 2026-11-18

## Candidate and safety
- Repository: Eventodigital473/SI-AI
- Candidate branch: fix/scanner-risk-audit-2026-11-18
- Latest head: 853d758e3ea75ade96cd2bfdaad66dccd88cce61 (Termux runbook documentation correction only; validated Python code is unchanged from 3aa29bf61d934ca480915c64b910f2989aec617c).
- Draft PR: https://github.com/Eventodigital473/SI-AI/pull/17
- PR #17 is open, draft, mergeable and unmerged. Do not merge without explicit user approval.
- Futures-only; Spot excluded from the active scanner/backtest files.
- Signal/notification provider only. No automatic orders, private account endpoints or balance fetching.
- Reference equity 100 USDT; per-trade risk 0.5%; margin allocation cap 20%; leverage guidance 1x; minimum net R:R 2:1.

## Verified automated checks
- Latest candidate CI: https://github.com/Eventodigital473/SI-AI/actions/runs/44290166008
- Result: 221 passed, 4 subtests passed.
- Dependency consistency, minimal Termux CCXT profile, Widget shell validation and Python compilation passed.
- Core source static review found no Spot references in SI_AI_smc.py or si_ai_scanner.py and no create_order/cancel_order/set_leverage/private/balance calls in those files.

## Changes made in this continuation
- Added checksum-verified Binance Vision monthly archive loader for USD-M OHLCV, mark-price candles and funding-rate audit files.
- Added daily markPriceKlines archive fallback to repair missing 1h mark-price candles; no interpolation or synthetic candles are used.
- Added tests for checksum validation, path traversal, CSV parsing, symbol validation and daily archive gap repair.
- Added conservative intratrade mark-to-market drawdown from timestamp-aligned mark-price OHLC. The equity path assumes favourable extreme before adverse extreme per candle as a conservative intrabar bound.
- Chronological train and walk-forward folds now slice mark-price arrays to the same prefix length as their OHLCV data.
- Mark-price timestamps must exactly align; mismatch fails closed.
- Funding settlement ambiguity for open, intrabar and close exits is aligned with funding_data.py rules.
- Profitability gate cannot PASS with realized-only drawdown.

## Preliminary 180-day results (not final candidate)
A checksum-verified 180-day Binance Vision run completed on an earlier pre-mark-to-market code revision for BTC, ETH and SOL. Fees and slippage were included; funding costs were excluded because the archive does not include exact event-specific settlement markPrice. Walk-forward net P&L was negative for all three:
- BTC: -0.1661 USDT
- ETH: -0.8210 USDT
- SOL: -1.0589 USDT
The small ETH OOS gain did not persist in walk-forward. These results are preliminary and must not be treated as final candidate metrics.

## Current long-run validation
- Workflow: https://github.com/Eventodigital473/SI-AI/actions/runs/44290154788
- Run head: 3aa29bf61d934ca480915c64b910f2989aec617c
- Scope: 365 days, ten USD-M perpetuals: BTC, ETH, BNB, XRP, ADA, DOGE, LINK, AVAX, DOT, SOL.
- At checkpoint creation the workflow is in progress at the historical backtest step. Its result is not yet known.
- The obsolete intermediate run was cancelled; this latest run includes the mark-price prefix alignment and funding-boundary fixes.
- A later documentation-only commit corrected the Termux runbook's stale historical-backtest command and removed its incorrect claim that Binance Vision funding archives contain settlement mark prices. The correct optional local runner is `binance_vision_backtest.py`; funding rates are audit-only and are not applied to P&L.
- The documentation commit triggered fresh CI runs `44291060801` and `44291070721`, plus a queued historical workflow `44291060559`. These are not yet completed; do not count them as passed.
- Workflow artifacts are intended to preserve historical datasets and JSON reports.

## Known blockers — do not claim profitability
1. Binance Vision funding-rate archives do not include the exact settlement markPrice. Rates are archived for audit but not applied to P&L; exact funding cashflows remain missing.
2. Timestamp-matched historical maintenance-margin tier snapshots are unavailable, so historical liquidation events are not simulated.
3. The current multi-symbol run uses independent 100-USDT reference equity per symbol, not a shared-wallet portfolio simulation.
4. Termux runtime, live Binance public-data connectivity from the user's device, and Android notification delivery have not been tested on the user's phone.
5. Profitability requires adequate OOS/walk-forward sample size and every evidence gate; no profit guarantee or claim is permitted.

## Exact next steps
1. Check workflow 44290154788 until completion; inspect its artifact and per-symbol OOS/walk-forward metrics.
2. Fix any archive, data, backtest or CI failures, then rerun the full suite and long-run research.
3. Update the in-repo project checkpoint after the final long-run report is reviewed.
4. Only then prepare the single final Termux deployment/verification step. Do not ask the user to run Termux commands before the remote code and research checks are complete.
5. Keep PR #17 draft/unmerged until the user explicitly approves integration.

No live trading is enabled. No automatic orders are placed.
