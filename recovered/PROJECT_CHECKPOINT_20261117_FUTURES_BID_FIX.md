> **ARCHIVED CHECKPOINT — HISTORICAL ONLY.** SI-AI has since been migrated to Binance USD-M Futures-only. Any Spot code, Spot scanner settings, or Spot backtesting described below has been retired and removed from the active project. Do not use this checkpoint to restore Spot functionality.

# SI-AI Project Checkpoint — 2026-11-17 (Futures bid/ask discovery fix)

## Source of truth
- Repository: `Eventodigital473/SI-AI`
- Active working branch: `feature/dynamic-coin-universe`
- Canonical project directory: `recovered/SI-AI/`
- Latest code commit: `a7dcfd0ef4cb9284fc7cc86d29aeba80904a3340`
- PR #1 remains open and draft; do not merge to `main` until all validation gates are complete.
- The earlier uploaded ZIP was also extracted into `recovery/source-2026-11-17` as a preserved archive snapshot. That ZIP contains an older BTC/ETH-only scanner and is NOT the active source of truth.

## User requirements and safety
- SI-AI remains a signal provider only. The user manually reviews and executes any trade on Binance.
- No automatic order placement, cancellation, amendment, or leverage-setting.
- Public market data only; no API keys or private account endpoints.
- Preserve the active Termux project at `~/SI-AI_FINAL/recovered/SI-AI`, runtime state, logs, datasets, reports, and historical backups.
- Current scanner policy remains 0.5% risk, 20% margin allocation cap, and conservative 1x Futures leverage.
- Do not represent the strategy as profitable. Latest documented OOS profitability gate remains FAIL.

## Diagnosis carried forward
The latest Termux dry-run analyzed 47 pairs. SPOT had 49 eligible USDT symbols; FUTURES had 0 eligible symbols. The read-only Futures discovery diagnosis reported:
- 182 passed the quote-volume filter.
- 182 had missing/invalid bid.
- 0 had invalid/crossed books.
- 0 exceeded the spread threshold.
- 0 passed the spread filter.

The cause in the active source was that Futures discovery read `bid` and `ask` from `fetch_tickers()`. Binance USD-M 24-hour ticker responses do not reliably provide those fields. The spread calculation therefore rejected every otherwise volume-qualified Futures contract.

## Code change
Commit `02124d035d7de79fdf7e2eec5099eff8238111ea`:
- Updated `recovered/SI-AI/SI_AI_smc.py` to call CCXT `fetch_bids_asks()` once for the Futures market, using the bulk bookTicker data for bid/ask while retaining `fetch_tickers()` for 24-hour quote volume.
- Spot discovery continues to use the existing Spot ticker bid/ask fields.
- If the Futures bulk bookTicker method is unavailable or returns an empty/invalid mapping, the refresh fails closed and preserves the last-known-good Futures universe. It does not widen the spread threshold or fabricate candidates.
- Added regression tests for Futures bookTicker usage and empty-response preservation.

Commit `a7dcfd0ef4cb9284fc7cc86d29aeba80904a3340`:
- Added a compatibility test asserting that the installed CCXT Binance USD-M exchange exposes `fetch_bids_asks()`.

## Validation evidence
GitHub Actions PR run `44100790735`:
- Dependency installation: PASS (CCXT 4.5.93).
- `python -m compileall -q .`: PASS.
- `python -m pytest -q --junitxml=test-results.xml`: **114 passed, 4 subtests passed, 0 failures**.
- JUnit evidence artifact: `si-ai-test-evidence-123`, artifact ID `14335712924`.
- This is offline software/test-fixture validation. It does NOT yet prove that the live Binance Futures endpoint returns usable bookTicker data in the user's Termux environment.

## Files changed
- `recovered/SI-AI/SI_AI_smc.py`
- `recovered/SI-AI/test_dynamic_universe.py`
- This checkpoint document.

## Still pending
1. Sync the latest `feature/dynamic-coin-universe` commit into the existing Termux checkout at `~/SI-AI_FINAL/recovered/SI-AI`; do not clone over or overwrite the directory.
2. Run a read-only public Futures bookTicker smoke check in Termux and verify that CCXT returns a non-empty mapping with valid bid/ask for representative active USD-M symbols.
3. Run `python si_ai_scanner.py --once --dry-run` and confirm Futures symbols now pass discovery/spread checks. Record exact universe counts and any remaining exclusions.
4. Do not change `MAX_SPREAD_PERCENT` or other eligibility thresholds merely to increase the Futures count.
5. Keep liquidation-risk output explicitly unavailable unless a validated exchange-specific calculation is implemented.
6. Continue historical Futures funding/liquidation modelling and forward paper observation separately; do not use the failed Spot OOS holdout for parameter tuning.

## Operational notes
- The one-time GitHub ZIP recovery workflow was removed from the current `main` tree after successful extraction. Its add/remove commits remain in `main` history; no workflow file remains in the tree.
- The old ZIP extraction branch is retained as a source snapshot only. Continue coding from `feature/dynamic-coin-universe` and the canonical `recovered/SI-AI/` directory.
- No live trade, order placement, account access, or leverage change occurred during this work.
